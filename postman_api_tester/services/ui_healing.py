"""v1.38.0 UI 自愈核心模块（方案 v3 §四-M8 设计；门控在引擎钩子侧）。

铁律：
- 顶层禁止 import playwright / 引擎符号（T-2 / N-9，依赖单向 engine→healing），
  page/locator 全部 duck-typing（`Any` 标注）。
- 每级采纳固定为先 `count()==1` 再 `is_visible()`（V5-7，多匹配时
  is_visible 会抛 strict 异常，顺序不可反）。
- 策略特征全部来自录制时的 element_info，现场不读 value 类属性（§五字段红线）。
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, cast

if TYPE_CHECKING:  # mypy 用，运行期不导入（T-2）
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# 置信度分值（v2 N-5：①②③ 固定分，④ xpath-LCS 为连续分，S1.5 接入）
CONF_TESTID = 95
CONF_ROLE = 85
CONF_TEXT = 75

_FIELD_MAX_LEN = 200

# element_info.tag → ARIA role 映射（②role+text 策略；仅收录录制常见标签）
_TAG_ROLE_MAP = {
    "button": "button",
    "a": "link",
    "label": "label",
    "select": "combobox",
    "textarea": "textbox",
    "option": "option",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
}

# 录制器 role 选择器格式：role=<role>[name="<text>"] 的 value 部分（v6 走查实证）
_ROLE_SELECTOR_RE = re.compile(
    r'^(?P<role>\w+)(?:\[name="(?P<name>.*)"\])?$'
)


@dataclass
class HealResult:
    """一次自愈命中结果（v3 §三契约表）。"""

    locator: Any
    strategy: str
    confidence: int
    new_selector_desc: str


# ---------------------------------------------------------------- 事件双通道

# 引擎注入的 jsonl 落盘回调（签名同 _log_request(job_id, step_index, data)）；
# 未注入时仅走中央日志通道，不报错。
_LOG_SINK: Optional[Callable[[str, int, Dict[str, Any]], None]] = None


def configure_log_sink(
    sink: Optional[Callable[[str, int, Dict[str, Any]], None]]
) -> None:
    """引擎侧注册 per-job jsonl 写入回调（M8：双通道之一）。"""
    global _LOG_SINK
    _LOG_SINK = sink


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _FIELD_MAX_LEN:
        return value[:_FIELD_MAX_LEN]
    return value


def _emit(job_id: str, step_index: int, event: str, **fields: Any) -> None:
    """自愈事件双通道：per-job jsonl（引擎回调）+ 中央日志（M8/§五）。

    字符串字段统一 [:200] 截断（字段红线）；留痕失败绝不影响主流程。
    """
    payload: Dict[str, Any] = {
        "event": event,
        **{key: _truncate(val) for key, val in fields.items()},
    }
    if _LOG_SINK is not None:
        try:
            _LOG_SINK(job_id, step_index, payload)
        except Exception:  # noqa: BLE001 - 留痕失败静默，自愈语义不变
            pass
    try:
        logger.info(
            "%s job_id=%s step_index=%s %s",
            event,
            job_id,
            step_index,
            payload,
            extra={"event": event},
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 失败分型探针


def _build_probe_locator(page: "Page", strategy: str, value: str) -> Any:
    """T-4：与引擎 _build_locator 同型的裸 locator 构建（探针专用，不加 .first）。

    count() 对多匹配不抛 strict 异常，可安全求和。
    """
    if strategy == "xpath":
        return page.locator(f"xpath={value}")
    if strategy == "text":
        return page.get_by_text(value)
    if strategy == "role":
        role, name = _parse_role_value(value)
        role_any = cast("Any", role)  # 动态 role 非 Literal，与引擎同款处理
        if name is not None:
            return page.get_by_role(role_any, name=name)
        return page.get_by_role(role_any)
    return page.locator(value)


def _parse_role_value(value: str) -> Tuple[str, Optional[str]]:
    """解析 role 策略 value：`button[name="确认"]` → ('button', '确认')。"""
    match = _ROLE_SELECTOR_RE.match(value.strip())
    if not match:
        return value, None
    name = match.group("name")
    return match.group("role"), name


def classify_failure(
    page: "Page", candidates: List[Tuple[str, str]]
) -> Tuple[str, Dict[str, int]]:
    """失败分型（N-4）：("not_found" | "exists" | "unknown", {strategy: count})。

    - 任一候选 count>0 → exists（元素在位，非选择器腐化，拒自愈）
    - 探测过程抛异常 → unknown（保守拒绝自愈，宁漏勿误修）
    - 全部候选探测成功且计数和为 0 → not_found（进入四级策略）
    """
    detail: Dict[str, int] = {}
    total = 0
    saw_error = False
    for strategy, value in candidates:
        if not value:
            continue
        try:
            count = int(_build_probe_locator(page, strategy, value).count())
        except Exception:  # noqa: BLE001 - 探针异常按 unknown 保守处理
            saw_error = True
            continue
        detail[strategy] = detail.get(strategy, 0) + count
        total += count
    if total > 0:
        return "exists", detail
    if saw_error:
        return "unknown", detail
    return "not_found", detail


# ---------------------------------------------------------------- 采纳与策略


def _adopt_candidate(locator: Any) -> bool:
    """采纳铁律（N-5/V5-7）：先 count()==1 再 is_visible()，顺序不可反。"""
    try:
        if int(locator.count()) != 1:
            return False
        return bool(locator.is_visible())
    except Exception:  # noqa: BLE001 - 校验失败视为未命中
        return False


def _element_info(step: Dict[str, Any]) -> Dict[str, Any]:
    info = step.get("element_info")
    return info if isinstance(info, dict) else {}


def _escape_css_attr_value(value: str) -> str:
    """CSS 属性选择器值转义（T-5）：反斜杠与双引号。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _heal_by_testid(page: "Page", step: Dict[str, Any]) -> Optional[HealResult]:
    """策略①（置信 95）：录制 element_info.test_id → [data-testid="…"] CSS 属性法。"""
    test_id = str(_element_info(step).get("test_id") or "")
    if not test_id:
        return None
    selector = f'[data-testid="{_escape_css_attr_value(test_id)}"]'
    locator = page.locator(selector)
    if not _adopt_candidate(locator):
        return None
    return HealResult(
        locator=locator,
        strategy="test_id",
        confidence=CONF_TESTID,
        new_selector_desc=selector,
    )


def _heal_by_role_text(page: "Page", step: Dict[str, Any]) -> Optional[HealResult]:
    """策略②（置信 85）：primary 的 role= 前缀或 tag→role 映射 + aria_label/text。"""
    role, name = _resolve_role_and_name(step)
    if not role or not name:
        return None
    try:
        locator = page.get_by_role(cast("Any", role), name=name)
    except Exception:  # noqa: BLE001 - 非法 role 等构建失败视为未命中
        return None
    if not _adopt_candidate(locator):
        return None
    return HealResult(
        locator=locator,
        strategy="role_text",
        confidence=CONF_ROLE,
        new_selector_desc=f'role={role}[name="{name}"]',
    )


def _resolve_role_and_name(step: Dict[str, Any]) -> Tuple[str, str]:
    """从选择器链 primary 或 element_info 提取 (role, name)。"""
    info = _element_info(step)
    selector = step.get("selector")
    primary = ""
    if isinstance(selector, dict):
        primary = str(selector.get("primary") or "").strip()
    elif selector:
        primary = str(selector).strip()

    name = str(info.get("aria_label") or info.get("text") or "").strip()
    if primary.startswith("role="):
        role, parsed_name = _parse_role_value(primary[5:])
        return role, (parsed_name or name)
    role = _TAG_ROLE_MAP.get(str(info.get("tag") or "").lower(), "")
    return role, name


def _heal_by_text(page: "Page", step: Dict[str, Any]) -> Optional[HealResult]:
    """策略③（置信 75）：get_by_text(text, exact=False) + tag 过滤（M8）。"""
    info = _element_info(step)
    text = str(info.get("text") or "").strip()
    if not text:
        return None
    tag = str(info.get("tag") or "").lower()
    try:
        if re.fullmatch(r"[a-z][a-z0-9]*", tag):
            locator = page.locator(tag).get_by_text(text, exact=False)
        else:
            locator = page.get_by_text(text, exact=False)
    except Exception:  # noqa: BLE001 - 构建失败视为未命中
        return None
    if not _adopt_candidate(locator):
        return None
    return HealResult(
        locator=locator,
        strategy="text",
        confidence=CONF_TEXT,
        new_selector_desc=f"text={text}"[:_FIELD_MAX_LEN],
    )


# 策略④现场 xpath 采集 JS（v2 N-13 仅主文档；M8 风险 2：走 arg 传参零拼接）
_XPATH_PROBE_JS = """(args) => {
  const out = [];
  const els = document.getElementsByTagName(args.tag);
  const limit = Math.min(els.length, args.max);
  for (let i = 0; i < limit; i++) {
    const el = els[i];
    const segs = [];
    let node = el;
    while (node && node.nodeType === 1 && node.parentNode) {
      let idx = 1;
      let sib = node.previousElementSibling;
      while (sib) {
        if (sib.tagName === node.tagName) idx++;
        sib = sib.previousElementSibling;
      }
      segs.push(node.tagName.toLowerCase() + '[' + idx + ']');
      node = node.parentNode;
    }
    segs.reverse();
    const cls = (el.className || '');
    out.push({
      tag: el.tagName.toLowerCase(),
      id: el.id || '',
      cls: String(cls).split(/\\s+/).slice(0, 2).join(' '),
      text: (el.textContent || '').trim().slice(0, 80),
      testid: el.getAttribute('data-testid') || '',
      xpath: '/' + segs.join('/'),
    });
  }
  return out;
}"""

# 路径段结构（tag+index 序列）提取：不含 class/text 加分（M8 风险 4 规避）
_XPATH_SEGMENT_RE = re.compile(r"([a-zA-Z][\w:-]*)")


def _xpath_segments(xpath: str) -> List[str]:
    """xpath → 段结构列表：`//div[1]/button[2]` → ['div[1]', 'button[2]']。"""
    segs: List[str] = []
    for part in xpath.split("/"):
        part = part.strip()
        if not part:
            continue
        segs.append(part)
    return segs


def _score_xpath(target: str, candidate: str) -> int:
    """difflib LCS 连续分（0~100），只比对路径段结构序列。"""
    ratio = difflib.SequenceMatcher(
        None, _xpath_segments(target), _xpath_segments(candidate)
    ).ratio()
    return int(ratio * 100)


def _heal_by_xpath_lcs(page: "Page", step: Dict[str, Any]) -> Optional[HealResult]:
    """策略④（连续分）：fallback_xpath 与现场同 tag 元素 xpath 做 LCS，取最优唯一。"""
    selector = step.get("selector")
    target = ""
    if isinstance(selector, dict):
        target = str(
            selector.get("fallback_xpath") or selector.get("primary") or ""
        ).strip()
    elif selector:
        target = str(selector).strip()
    if not target.startswith(("/", "(")):
        return None

    info = _element_info(step)
    tag = str(info.get("tag") or "").lower()
    if not re.fullmatch(r"[a-z][a-z0-9]*", tag):
        tail = [s for s in _xpath_segments(target) if s]
        match = _XPATH_SEGMENT_RE.match(tail[-1]) if tail else None
        tag = match.group(1).lower() if match else ""
    if not tag:
        return None

    try:
        candidates = page.evaluate(_XPATH_PROBE_JS, {"tag": tag, "max": 200})
    except Exception:  # noqa: BLE001 - 采集失败视为未命中
        return None
    if not isinstance(candidates, list):
        return None

    scored = sorted(
        (c for c in candidates if isinstance(c, dict) and c.get("xpath")),
        key=lambda c: -_score_xpath(target, str(c["xpath"])),
    )
    for cand in scored:
        cand_xpath = str(cand["xpath"])
        score = _score_xpath(target, cand_xpath)
        if score < CONF_TEXT:  # 低于 ③ 固定分即无继续价值（降序剪枝）
            break
        try:
            locator = page.locator(f"xpath={cand_xpath}")
        except Exception:  # noqa: BLE001
            continue
        if _adopt_candidate(locator):
            return HealResult(
                locator=locator,
                strategy="xpath_lcs",
                confidence=score,
                new_selector_desc=cand_xpath[:_FIELD_MAX_LEN],
            )
    return None


# 四级策略声明表（v2 N-5 表驱动；④ xpath-lcs 为连续分，表内分值仅为序占位）
STRATEGY_SPECS: List[Tuple[str, int, Callable[["Page", Dict[str, Any]], Optional[HealResult]]]] = [
    ("test_id", CONF_TESTID, _heal_by_testid),
    ("role_text", CONF_ROLE, _heal_by_role_text),
    ("text", CONF_TEXT, _heal_by_text),
    ("xpath_lcs", 0, _heal_by_xpath_lcs),
]


def original_selector_desc(step: Dict[str, Any]) -> str:
    """事件/heal_info 用原始选择器摘要（primary 优先，[:200] 字段红线）。"""
    sel = step.get("selector", "")
    primary = (
        str(sel.get("primary") or "") if isinstance(sel, dict) else str(sel or "")
    )
    return primary[:_FIELD_MAX_LEN]


def build_heal_info(old_selector: str, result: HealResult) -> Dict[str, Any]:
    """step_result["heal_info"] 结构（v3 §二 I-2：old/new/strategy/confidence）。"""
    return {
        "old_selector": old_selector[:_FIELD_MAX_LEN],
        "new_selector": str(result.new_selector_desc)[:_FIELD_MAX_LEN],
        "strategy": result.strategy,
        "confidence": result.confidence,
    }


def try_heal(
    page: "Page", step: Dict[str, Any], case_id: str, step_index: int
) -> Optional[HealResult]:
    """依序跑策略链，返回首个满足采纳铁律的结果；全落空返回 None。

    置信度阈值比较与事件发送在引擎钩子侧（那里才有 job_id）；
    element_info 缺失时 ①②③ 天然不命中，直落 ④（S1.5）。
    """
    for _name, _confidence, heal_fn in STRATEGY_SPECS:
        result = heal_fn(page, step)
        if result is not None:
            return result
    return None
