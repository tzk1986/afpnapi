"""UI 测试无头浏览器执行引擎。

使用 Playwright 在后台线程中执行 UI 测试步骤。
需要安装 playwright: pip install playwright && playwright install chromium
"""

import contextlib
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 无头执行日志目录
_HEADLESS_LOG_DIR = Path("logs/headless")
_HEADLESS_LOG_RETENTION_DAYS = 10


def _cleanup_old_logs() -> None:
    """清理超过保留天数的无头执行日志。"""
    if not _HEADLESS_LOG_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=_HEADLESS_LOG_RETENTION_DAYS)
    cleaned = 0
    for f in _HEADLESS_LOG_DIR.glob("exec_*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                cleaned += 1
        except OSError:
            pass
    if cleaned > 0:
        logger.info("headless_log_cleanup: removed %d old log files", cleaned)


def _log_request(job_id: str, step_index: int, request_data: Dict[str, Any]) -> None:
    """将无头执行中的网络请求追加到日志文件。"""
    _HEADLESS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _HEADLESS_LOG_DIR / f"exec_{job_id}.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "step_index": step_index,
        **request_data,
    }
    try:
        with Path(log_file).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        sync_playwright,
    )

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


def is_playwright_available() -> bool:
    """检查 Playwright 是否已安装。"""
    return _HAS_PLAYWRIGHT


class HeadlessExecutionError(Exception):
    """无头执行异常。"""


class UiHeadlessEngine:
    """Playwright 无头执行引擎。"""

    def __init__(
        self,
        browser_type: str = "chromium",
        screenshots_dir: Optional[Path] = None,
    ) -> None:
        if not _HAS_PLAYWRIGHT:
            raise HeadlessExecutionError(
                "Playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )
        self._browser_type = browser_type
        self._screenshots_dir = screenshots_dir

    def execute(
        self,
        steps: List[Dict[str, Any]],
        base_url: str,
        options: Dict[str, Any],
        job_id: str,
        cancel_flag: Optional[Any] = None,
        on_step_complete: Optional[Any] = None,
        on_browser_ready: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """执行所有步骤，返回摘要。

        Args:
            steps: 步骤列表
            base_url: 基础 URL（导航步骤的相对路径会拼接此值）
            options: 执行选项（timeout, delay_between_steps）
            job_id: 任务 ID（用于截图命名）
            cancel_flag: threading.Event，被 set 时中止执行
            on_step_complete: 回调 (step_index, step_result_dict) -> None
            on_browser_ready: 浏览器启动完成回调 () -> None
        """
        timeout_ms = options.get("timeout", 30000)
        delay_ms = options.get("delay_between_steps", 200)
        viewport_w = options.get("viewport_width", 1280)
        viewport_h = options.get("viewport_height", 720)

        pw = sync_playwright().start()
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        steps_passed = 0
        steps_failed = 0
        _step_results: List[Dict[str, Any]] = []

        _cleanup_old_logs()

        current_step_index = [-1]  # 用 list 以便在闭包中修改

        def _on_request(request: Any) -> None:
            """拦截并记录无头执行中的网络请求。"""
            url = request.url
            # 只记录 API 请求，跳过静态资源
            if "/api/" not in url:
                return
            _log_request(
                job_id,
                current_step_index[0],
                {
                    "event": "request",
                    "method": request.method,
                    "url": url,
                    "headers": dict(request.headers),
                },
            )

        def _on_response(response: Any) -> None:
            """记录响应状态。"""
            url = response.url
            if "/api/" not in url:
                return
            _log_request(
                job_id,
                current_step_index[0],
                {
                    "event": "response",
                    "method": response.request.method,
                    "url": url,
                    "status": response.status,
                    "status_text": response.status_text,
                },
            )

        try:
            launcher = getattr(pw, self._browser_type, pw.chromium)
            browser = launcher.launch(headless=True)
            context = browser.new_context(
                viewport={"width": viewport_w, "height": viewport_h}
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            # 监听网络请求
            page.on("request", _on_request)
            page.on("response", _on_response)

            # 自动导航到 base_url（回放模式下 iframe 已指向 base_url，无头模式需要显式跳转）
            if base_url:
                page.goto(base_url, wait_until="load")

            # 浏览器启动完成，开始计时
            start_time = time.time()
            if on_browser_ready is not None:
                on_browser_ready()

            # 监听新页面/弹窗（用于 new_tab 处理）
            popup_page: Any = None
            captured_new_tab_url: str = ""

            def _on_popup(p: Any) -> None:
                nonlocal popup_page
                # 忽略无效 URL 的 popup（如 null、about:blank）
                if p.url and p.url != "about:blank" and "/null" not in p.url:
                    popup_page = p
                    logger.info(
                        "headless_popup_detected",
                        extra={"event": "headless.popup", "url": p.url},
                    )

            context.on("page", _on_popup)

            for i, step in enumerate(steps):
                if cancel_flag is not None and cancel_flag.is_set():
                    break

                step_start = time.time()
                action = step.get("action", "").lower()
                url_before_step = page.url

                # new_tab：导航到新页面（与浏览器回放引擎行为一致）
                if action == "new_tab":
                    # 优先级：弹窗页面 > 步骤数据解析
                    if popup_page is not None:
                        try:
                            popup_page.wait_for_load_state("networkidle")
                            actual_url = popup_page.url
                            page.close()
                            page = popup_page
                            popup_page = None
                        except Exception as e:
                            logger.warning("headless_popup_error: %s", e)
                            actual_url = ""
                    elif captured_new_tab_url:
                        actual_url = captured_new_tab_url
                        captured_new_tab_url = ""
                        page.goto(actual_url, wait_until="domcontentloaded")
                        page.wait_for_load_state("networkidle")
                        logger.info(
                            "headless_new_tab_captured_url",
                            extra={
                                "event": "headless.new_tab.captured_url",
                                "url": actual_url,
                            },
                        )
                    else:
                        actual_url = self._resolve_new_tab_url(step, steps, i, base_url)
                        if actual_url:
                            page.goto(actual_url, wait_until="domcontentloaded")
                            page.wait_for_load_state("networkidle")

                    step_result = {
                        "action": "new_tab",
                        "selector": {},
                        "value": actual_url,
                        "status": "passed" if actual_url else "failed",
                        "error": "" if actual_url else "无法解析 new_tab 导航 URL",
                    }
                else:
                    # 如果下一步是 new_tab，当前 click 前注入 window.open 拦截
                    next_is_new_tab = (
                        i + 1 < len(steps)
                        and steps[i + 1].get("action", "").lower() == "new_tab"
                    )
                    if action == "click" and next_is_new_tab:
                        url_before = page.url
                        popup_page = None
                        # 执行 click（不等待 popup，让 new_tab 步骤用 fallback URL 导航）
                        step_result = self._execute_step(
                            page, step, base_url, timeout_ms
                        )
                        # 短暂等待 popup 触发（_on_popup 异步回调）
                        time.sleep(0.5)
                        # 检测页面 URL 是否已跳转到新系统
                        try:
                            page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass
                        url_after = page.url
                        if url_after != url_before and self._is_different_origin(url_before, url_after):
                            captured_new_tab_url = url_after
                            logger.info(
                                "headless_navigation_captured",
                                extra={
                                    "event": "headless.navigation.captured",
                                    "url_before": url_before[:80],
                                    "url_after": url_after[:120],
                                },
                            )
                    else:
                        step_result = self._execute_step(
                            page, step, base_url, timeout_ms
                        )
                step_duration_ms = int((time.time() - step_start) * 1000)

                step_result["index"] = i
                step_result["duration_ms"] = step_duration_ms

                if step_result["status"] == "passed":
                    steps_passed += 1
                else:
                    steps_failed += 1
                    self._take_screenshot(page, job_id, i)

                # 步骤勾选了截图，无论通过/失败都截图
                if step.get("screenshot"):
                    self._take_screenshot(page, job_id, i, suffix="")
                    step_result["screenshot"] = True

                if on_step_complete is not None:
                    on_step_complete(i, step_result)

                _step_results.append(step_result)

                # 同页面操作跳过步骤间延迟，只有页面导航后才等待
                if delay_ms > 0 and i < len(steps) - 1 and page.url != url_before_step:
                    time.sleep(delay_ms / 1000.0)

        except Exception as e:
            logger.error("headless_engine_fatal_error: %s", e, exc_info=True)
        finally:
            if context is not None:
                with contextlib.suppress(Exception):
                    context.close()
            if browser is not None:
                with contextlib.suppress(Exception):
                    browser.close()
            pw.stop()

        total_duration_ms = int((time.time() - start_time) * 1000)
        status = "passed" if steps_failed == 0 else "failed"
        if cancel_flag is not None and cancel_flag.is_set():
            status = "cancelled"

        return {
            "status": status,
            "steps_total": len(steps),
            "steps_passed": steps_passed,
            "steps_failed": steps_failed,
            "total_duration_ms": total_duration_ms,
            "_step_results": _step_results,
        }

    def _execute_step(
        self, page: "Page", step: Dict[str, Any], base_url: str, timeout_ms: int
    ) -> Dict[str, Any]:
        """执行单个步骤，返回 step_result dict。"""
        action = step.get("action", "").lower()
        selector = step.get("selector", "")
        value = step.get("value", "")

        try:
            if action == "navigate":
                return self._action_navigate(page, value, base_url)
            elif action == "click":
                return self._action_click(page, selector, timeout_ms)
            elif action in ("type", "input"):
                return self._action_type(page, selector, value, timeout_ms)
            elif action == "clear":
                return self._action_clear(page, selector, timeout_ms)
            elif action == "select":
                return self._action_select(page, selector, value, timeout_ms)
            elif action == "hover":
                return self._action_hover(page, selector, timeout_ms)
            elif action == "wait":
                return self._action_wait(page, value)
            elif action == "assert_text":
                return self._action_assert_text(page, selector, value, timeout_ms)
            elif action == "assert_visible":
                return self._action_assert_visible(page, selector, timeout_ms)
            elif action == "assert_url":
                return self._action_assert_url(page, value)
            elif action == "scroll":
                return self._action_scroll(page, value)
            elif action in ("select_radio", "check", "uncheck"):
                return self._action_check(page, selector, action, timeout_ms)
            elif action == "screenshot":
                return self._action_screenshot(page)
            else:
                return {
                    "action": action,
                    "selector": self._selector_to_dict(selector),
                    "value": value,
                    "status": "failed",
                    "error": f"未知操作: {action}",
                }
        except Exception as e:
            return {
                "action": action,
                "selector": self._selector_to_dict(selector),
                "value": value,
                "status": "failed",
                "error": str(e)[:200],
            }

    def _classify_strategy(self, selector: str) -> Tuple[str, str]:
        """解析单个选择器字符串，返回 (strategy, value)。"""
        s = selector.strip()
        if not s:
            return ("css", "")
        if s.startswith(("/", "(")):
            return ("xpath", s)
        if s.startswith("text="):
            return ("text", s[5:])
        if s.startswith("role="):
            return ("role", s[5:])
        return ("css", s)

    def _resolve_selector_chain(self, selector: Any) -> List[Tuple[str, str]]:
        """解析选择器回退链，返回 [(strategy, value), ...] 按优先级排列。

        优先级：primary → fallback_css → fallback_xpath（去重，与浏览器引擎一致）
        """
        if not isinstance(selector, dict):
            s = str(selector) if selector else ""
            return [self._classify_strategy(s)] if s else []

        candidates: List[Tuple[str, str]] = []
        seen: set = set()
        for key in ("primary", "fallback_css", "fallback_xpath"):
            s = (selector.get(key, "") or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            candidates.append(self._classify_strategy(s))

        return candidates

    def _build_locator(self, page: "Page", strategy: str, value: str) -> Any:
        """根据 strategy 构建 Playwright locator。

        对 XPath 使用 .first 避免多元素匹配时 strict mode 报错，
        与浏览器回放引擎 querySelector / FIRST_ORDERED_NODE_TYPE 行为一致。
        """
        if strategy == "xpath":
            return page.locator(f"xpath={value}").first
        elif strategy == "text":
            return page.get_by_text(value)
        elif strategy == "role":
            return page.get_by_role(value)  # type: ignore[arg-type]
        else:
            return page.locator(value).first

    def _resolve_selector(self, selector: Any) -> Tuple[str, str]:
        """解析选择器（兼容旧接口），返回 (strategy, value)。"""
        chain = self._resolve_selector_chain(selector)
        if chain:
            return chain[0]
        return ("css", "")

    def _resolve_new_tab_url(
        self, step: Dict[str, Any], steps: List[Dict[str, Any]], index: int, base_url: str
    ) -> str:
        """解析 new_tab 导航 URL，与浏览器回放引擎优先级一致。

        优先级：step.value → step.tab_url → 下一步 tab_url/page_url
        """
        # 1. 当前步骤的 value 或 tab_url
        url = step.get("value", "") or step.get("tab_url", "")
        if url:
            return url

        # 2. 下一步的 tab_url 或 page_url
        if index + 1 < len(steps):
            next_step = steps[index + 1]
            url = next_step.get("tab_url", "") or next_step.get("page_url", "")
            if url:
                return url

        return ""

    @staticmethod
    def _is_different_origin(url_a: str, url_b: str) -> bool:
        """判断两个 URL 是否属于不同源（host:port 不同）。"""
        try:
            from urllib.parse import urlparse

            pa = urlparse(url_a)
            pb = urlparse(url_b)
            return pa.netloc != pb.netloc
        except Exception:
            return url_a != url_b

    def _find_element(self, page: "Page", selector: Any, timeout_ms: int) -> Any:
        """查找元素，支持选择器回退链（primary → fallback_css → fallback_xpath）。

        与浏览器回放引擎 SelectorEngine.find 保持一致的回退策略：
        每个候选选择器分配较短超时，最后一个用完整超时。
        """
        candidates = self._resolve_selector_chain(selector)
        if not candidates:
            raise HeadlessExecutionError("选择器为空")

        per_timeout = 1000

        last_error: Optional[Exception] = None
        for i, (strategy, value) in enumerate(candidates):
            is_last = i == len(candidates) - 1
            wait_ms = timeout_ms if is_last else per_timeout

            try:
                locator = self._build_locator(page, strategy, value)
                if locator.is_visible():
                    return locator
                locator.wait_for(state="visible", timeout=wait_ms)
                return locator
            except Exception as e:
                last_error = e
                if is_last:
                    raise

        raise last_error or HeadlessExecutionError("元素未找到")

    def _selector_to_dict(self, selector: Any) -> Any:
        """确保 selector 在结果中以 dict 形式返回。"""
        if isinstance(selector, dict):
            return selector
        return {
            "primary": str(selector) if selector else "",
            "fallback_css": "",
            "fallback_xpath": "",
        }

    # ---- Action implementations ----

    def _action_navigate(self, page: "Page", url: str, base_url: str) -> Dict[str, Any]:
        target = url
        if url and not url.startswith(("http://", "https://", "about:")) and base_url:
            target = base_url.rstrip("/") + "/" + url.lstrip("/")
        page.goto(target, wait_until="domcontentloaded")
        return {
            "action": "navigate",
            "selector": {},
            "value": target,
            "status": "passed",
            "error": "",
        }

    def _action_click(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.click()
        return {
            "action": "click",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_type(
        self, page: "Page", selector: Any, value: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        try:
            el.fill(value)
        except Exception as e:
            err = str(e)
            if "cannot be filled" in err:
                el.click()
                return {
                    "action": "type",
                    "selector": self._selector_to_dict(selector),
                    "value": value,
                    "status": "passed",
                    "error": "",
                }
            raise
        return {
            "action": "type",
            "selector": self._selector_to_dict(selector),
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_clear(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.fill("")
        return {
            "action": "clear",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_select(
        self, page: "Page", selector: Any, value: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.select_option(value)
        return {
            "action": "select",
            "selector": self._selector_to_dict(selector),
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_hover(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.hover()
        return {
            "action": "hover",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_check(
        self, page: "Page", selector: Any, action: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        if action == "check":
            el.check()
        elif action == "uncheck":
            el.uncheck()
        else:
            el.click()
        return {
            "action": action,
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_wait(self, page: "Page", value: str) -> Dict[str, Any]:
        try:
            ms = int(float(value))
        except (ValueError, TypeError):
            ms = 1000
        time.sleep(ms / 1000.0)
        return {
            "action": "wait",
            "selector": {},
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_assert_text(
        self, page: "Page", selector: Any, expected: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        actual = (el.inner_text() or "").strip()
        if expected in actual:
            return {
                "action": "assert_text",
                "selector": self._selector_to_dict(selector),
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_text",
            "selector": self._selector_to_dict(selector),
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望包含 '{expected}', 实际 '{actual[:80]}'",
        }

    def _action_assert_visible(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        self._find_element(page, selector, timeout_ms)
        return {
            "action": "assert_visible",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_assert_url(self, page: "Page", expected: str) -> Dict[str, Any]:
        actual = page.url
        if expected in actual:
            return {
                "action": "assert_url",
                "selector": {},
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_url",
            "selector": {},
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望 URL 包含 '{expected}', 实际 '{actual}'",
        }

    def _action_scroll(self, page: "Page", value: str) -> Dict[str, Any]:
        try:
            px = int(float(value)) if value else 300
        except (ValueError, TypeError):
            px = 300
        page.evaluate(f"window.scrollBy(0, {px})")
        return {
            "action": "scroll",
            "selector": {},
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_screenshot(self, page: "Page") -> Dict[str, Any]:
        return {
            "action": "screenshot",
            "selector": {},
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _take_screenshot(self, page: "Page", job_id: str, step_index: int, suffix: str = "_fail") -> None:
        """截图保存。suffix 为空时保存为 step_{i}.png，否则 step_{i}{suffix}.png。"""
        if not self._screenshots_dir:
            return
        try:
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = self._screenshots_dir / f"step_{step_index}{suffix}.png"
            page.screenshot(path=str(path))
        except Exception as e:
            logger.warning("screenshot_failed: %s", e)
