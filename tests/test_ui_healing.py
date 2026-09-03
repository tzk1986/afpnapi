"""v1.38.0 UI 自愈单元测试（方案 v4 F 矩阵 + v5 V5-8 九函数人工对照）。

覆盖函数清单（M8 骨架 9 项）：HealResult / STRATEGY_SPECS / classify_failure /
_heal_by_testid / _heal_by_role_text / _heal_by_text / _heal_by_xpath_lcs /
try_heal / _emit ——每项 ≥1 用例。
"""

from typing import Any, Dict, List, Optional, Tuple

import pytest

from postman_api_tester.services import ui_headless_engine as engine_mod
from postman_api_tester.services import ui_healing
from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine
from postman_api_tester.services.ui_healing import (
    HealResult,
    STRATEGY_SPECS,
    _emit,
    _heal_by_role_text,
    _heal_by_testid,
    _heal_by_text,
    _heal_by_xpath_lcs,
    classify_failure,
    configure_log_sink,
    try_heal,
)

# ---------------------------------------------------------------- fakes


class FakeLocator:
    def __init__(
        self,
        count: int = 1,
        visible: bool = True,
        raise_on_count: bool = False,
        strict_visible: bool = False,
    ) -> None:
        self._count = count
        self._visible = visible
        self._raise_on_count = raise_on_count
        self._strict_visible = strict_visible

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        if self._raise_on_count:
            raise RuntimeError("detached while counting")
        return self._count

    def is_visible(self) -> bool:
        # V5-7 锁序：多匹配时 is_visible 抛 strict 异常（若实现先调它会炸）
        if self._strict_visible and self._count != 1:
            raise RuntimeError("strict mode violation")
        return self._visible

    def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        raise TimeoutError("wait_for timeout")

    def get_by_text(self, text: str, exact: bool = False) -> "FakeLocator":
        return self


class FakePage:
    def __init__(
        self,
        locators: Optional[Dict[str, FakeLocator]] = None,
        default: Optional[FakeLocator] = None,
        evaluate_result: Any = None,
        evaluate_raises: bool = False,
    ) -> None:
        self.locators = locators or {}
        self.default = default
        self.evaluate_result = evaluate_result
        self.evaluate_raises = evaluate_raises
        self.evaluate_calls: List[Tuple[Any, Any]] = []
        self.role_calls: List[Tuple[str, Any]] = []

    def locator(self, selector: str, **kw: Any) -> FakeLocator:
        return self.locators.get(selector, self.default or FakeLocator(count=0))

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        key = f"text::{text}"
        return self.locators.get(key, self.default or FakeLocator(count=0))

    def get_by_role(self, role: str, name: Optional[str] = None) -> FakeLocator:
        self.role_calls.append((role, name))
        key = f"role::{role}::{name}"
        return self.locators.get(key, self.default or FakeLocator(count=0))

    def evaluate(self, js: str, arg: Any = None) -> Any:
        self.evaluate_calls.append((js, arg))
        if self.evaluate_raises:
            raise RuntimeError("evaluate boom")
        return self.evaluate_result


def _step(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "action": "click",
        "selector": {"primary": "#old", "fallback_css": "", "fallback_xpath": ""},
        "element_info": {},
    }
    base.update(overrides)
    return base


@pytest.fixture
def sink_events() -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    original = ui_healing._LOG_SINK
    configure_log_sink(lambda jid, idx, data: events.append({"job": jid, "idx": idx, **data}))
    yield events
    configure_log_sink(original)


# ---------------------------------------------------------------- classify_failure


class TestClassifyFailure:
    def test_all_zero_not_found(self) -> None:
        page = FakePage(default=FakeLocator(count=0))
        kind, detail = classify_failure(page, [("css", "#a"), ("text", "hi")])  # type: ignore[arg-type]
        assert kind == "not_found"
        assert sum(detail.values()) == 0

    def test_any_positive_exists(self) -> None:
        page = FakePage(locators={"#a": FakeLocator(count=2)})
        kind, _ = classify_failure(page, [("css", "#a")])  # type: ignore[arg-type]
        assert kind == "exists"

    def test_probe_exception_unknown(self) -> None:
        page = FakePage(default=FakeLocator(raise_on_count=True))
        kind, _ = classify_failure(page, [("css", "#a")])  # type: ignore[arg-type]
        assert kind == "unknown"

    def test_role_probe_with_name_parsed(self) -> None:
        page = FakePage()
        classify_failure(page, [("role", 'button[name="提交"]')])  # type: ignore[arg-type]
        assert ("button", "提交") in page.role_calls

    def test_empty_value_skipped(self) -> None:
        page = FakePage()
        kind, detail = classify_failure(page, [("css", "")])  # type: ignore[arg-type]
        assert kind == "not_found" and detail == {}


# ---------------------------------------------------------------- 策略①②③④ / V5-7


class TestHealByTestid:
    def test_hit_confidence_95(self) -> None:
        step = _step(element_info={"test_id": "save-btn"})
        page = FakePage(locators={'[data-testid="save-btn"]': FakeLocator(count=1)})
        res = _heal_by_testid(page, step)  # type: ignore[arg-type]
        assert res is not None and res.confidence == 95 and res.strategy == "test_id"

    def test_missing_testid_none(self) -> None:
        assert _heal_by_testid(FakePage(), _step()) is None  # type: ignore[arg-type]

    def test_multi_match_rejected_visible_not_called(self) -> None:
        # V5-7：count!=1 直接拒，is_visible 不被调用（strict_visible=True 会炸）
        step = _step(element_info={"test_id": "x"})
        page = FakePage(locators={'[data-testid="x"]': FakeLocator(count=3, strict_visible=True)})
        assert _heal_by_testid(page, step) is None  # type: ignore[arg-type]

    def test_invisible_rejected(self) -> None:
        step = _step(element_info={"test_id": "x"})
        page = FakePage(locators={'[data-testid="x"]': FakeLocator(count=1, visible=False)})
        assert _heal_by_testid(page, step) is None  # type: ignore[arg-type]

    def test_quote_escaped(self) -> None:
        step = _step(element_info={"test_id": 'a"b'})
        page = FakePage(locators={'[data-testid="a\\"b"]': FakeLocator(count=1)})
        res = _heal_by_testid(page, step)  # type: ignore[arg-type]
        assert res is not None and res.new_selector_desc == '[data-testid="a\\"b"]'


class TestHealByRoleText:
    def test_primary_role_prefix_with_name(self) -> None:
        step = _step(
            selector={"primary": 'role=button[name="保存"]', "fallback_css": "", "fallback_xpath": ""},
            element_info={},
        )
        page = FakePage(locators={"role::button::保存": FakeLocator(count=1)})
        res = _heal_by_role_text(page, step)  # type: ignore[arg-type]
        assert res is not None and res.confidence == 85

    def test_tag_mapping_with_text_name(self) -> None:
        step = _step(element_info={"tag": "button", "text": "确定", "aria_label": "", "test_id": ""})
        page = FakePage(locators={"role::button::确定": FakeLocator(count=1)})
        res = _heal_by_role_text(page, step)  # type: ignore[arg-type]
        assert res is not None and res.strategy == "role_text"

    def test_aria_label_preferred_over_text(self) -> None:
        step = _step(element_info={"tag": "button", "text": "确定", "aria_label": "确认按钮"})
        page = FakePage()
        _heal_by_role_text(page, step)  # type: ignore[arg-type]
        assert ("button", "确认按钮") in page.role_calls

    def test_no_role_or_name_none(self) -> None:
        assert _heal_by_role_text(FakePage(), _step()) is None  # type: ignore[arg-type]


class TestHealByText:
    def test_hit_with_tag_filter_75(self) -> None:
        step = _step(element_info={"tag": "span", "text": "订单号"})
        page = FakePage(default=FakeLocator(count=1))
        res = _heal_by_text(page, step)  # type: ignore[arg-type]
        assert res is not None and res.confidence == 75 and res.strategy == "text"

    def test_no_text_none(self) -> None:
        assert _heal_by_text(FakePage(), _step()) is None  # type: ignore[arg-type]

    def test_multi_rejected(self) -> None:
        step = _step(element_info={"tag": "", "text": "x"})
        page = FakePage(default=FakeLocator(count=2, strict_visible=True))
        assert _heal_by_text(page, step) is None  # type: ignore[arg-type]


class TestHealByXpathLcs:
    _TARGET = "//div[1]/section[2]/button[3]"

    def _hit_step(self) -> Dict[str, Any]:
        return _step(
            selector={"primary": "#gone", "fallback_css": "", "fallback_xpath": self._TARGET},
            element_info={"tag": "button"},
        )

    def test_lcs_hit_continuous_score(self) -> None:
        page = FakePage(
            evaluate_result=[{"xpath": "/html[1]/body[1]/div[1]/section[2]/button[3]"}],
            default=FakeLocator(count=1),
        )
        res = _heal_by_xpath_lcs(page, self._hit_step())  # type: ignore[arg-type]
        assert res is not None and res.strategy == "xpath_lcs"
        assert res.confidence > 0

    def test_evaluate_arg_no_string_concat(self) -> None:
        page = FakePage(evaluate_result=[], default=FakeLocator(count=0))
        _heal_by_xpath_lcs(page, self._hit_step())  # type: ignore[arg-type]
        js, arg = page.evaluate_calls[0]
        assert isinstance(arg, dict) and arg["max"] == 200 and arg["tag"] == "button"
        assert "button[3]" not in js  # 目标 xpath 不拼进 JS 源码

    def test_tag_from_xpath_tail_when_info_missing(self) -> None:
        step = _step(
            selector={"primary": "", "fallback_css": "", "fallback_xpath": self._TARGET},
            element_info={},
        )
        page = FakePage(evaluate_result=[], default=FakeLocator(count=0))
        _heal_by_xpath_lcs(page, step)  # type: ignore[arg-type]
        assert page.evaluate_calls[0][1]["tag"] == "button"

    def test_non_xpath_selector_none(self) -> None:
        assert _heal_by_xpath_lcs(FakePage(), _step()) is None  # type: ignore[arg-type]

    def test_evaluate_exception_none(self) -> None:
        page = FakePage(evaluate_raises=True)
        assert _heal_by_xpath_lcs(page, self._hit_step()) is None  # type: ignore[arg-type]

    def test_low_score_pruned(self) -> None:
        # 完全不相干的现场 xpath（LCS 分 <75）不采纳
        page = FakePage(
            evaluate_result=[{"xpath": "/html[1]/body[1]/p[9]/em[1]"}],
            default=FakeLocator(count=1),
        )
        assert _heal_by_xpath_lcs(page, self._hit_step()) is None  # type: ignore[arg-type]

    def test_many_candidates_best_first(self) -> None:
        cands = [{"xpath": f"/html[1]/body[1]/div[1]/span[{i}]"} for i in range(300)]
        cands.append({"xpath": "/html[1]/body[1]/div[1]/section[2]/button[3]"})
        page = FakePage(evaluate_result=cands, default=FakeLocator(count=0, visible=False))
        page.locators["xpath=/html[1]/body[1]/div[1]/section[2]/button[3]"] = FakeLocator(count=1)
        res = _heal_by_xpath_lcs(page, self._hit_step())  # type: ignore[arg-type]
        assert res is not None and "section[2]/button[3]" in res.new_selector_desc


# ---------------------------------------------------------------- try_heal 链 / 契约


class TestTryHealChain:
    def test_strategy_table_four_levels(self) -> None:
        assert [s[0] for s in STRATEGY_SPECS] == ["test_id", "role_text", "text", "xpath_lcs"]

    def test_first_hit_wins_order(self) -> None:
        step = _step(element_info={"test_id": "t", "tag": "button", "text": "确"})
        page = FakePage(locators={'[data-testid="t"]': FakeLocator(count=1)})
        res = try_heal(page, step, "case-1", 0)
        assert res is not None and res.strategy == "test_id"

    def test_testid_miss_then_role_hit(self) -> None:
        step = _step(element_info={"test_id": "gone", "tag": "button", "text": "确"})
        page = FakePage(locators={"role::button::确": FakeLocator(count=1)})
        res = try_heal(page, step, "case-1", 0)
        assert res is not None and res.strategy == "role_text"

    def test_all_miss_none(self) -> None:
        step = _step(element_info={"test_id": "gone", "text": "no"})
        assert try_heal(FakePage(default=FakeLocator(count=0)), step, "c", 0) is None

    def test_element_info_missing_falls_to_lcs(self) -> None:
        step = _step(
            element_info={},
            selector={
                "primary": "",
                "fallback_css": "",
                "fallback_xpath": "//div[1]/section[2]/button[3]",
            },
        )
        page = FakePage(
            evaluate_result=[{"xpath": "/html[1]/body[1]/div[1]/section[2]/button[3]"}],
            default=FakeLocator(count=1),
        )
        res = try_heal(page, step, "c", 0)
        assert res is not None and res.strategy == "xpath_lcs"


class TestEmitAndInfo:
    def test_sink_receives_event_with_truncation(self, sink_events: List[Dict[str, Any]]) -> None:
        _emit("job-9", 2, "self_healing.attempt", original_selector="x" * 500)
        assert len(sink_events) == 1
        ev = sink_events[0]
        assert ev["job"] == "job-9" and ev["idx"] == 2
        assert len(ev["original_selector"]) == 200

    def test_sink_exception_swallowed(self) -> None:
        def bad_sink(*_a: Any) -> None:
            raise RuntimeError("disk full")

        configure_log_sink(bad_sink)
        try:
            _emit("j", 0, "self_healing.healed", strategy="test_id", confidence=95)
        finally:
            configure_log_sink(None)

    def test_no_sink_ok(self) -> None:
        configure_log_sink(None)
        _emit("j", 0, "self_healing.rejected", reason="unknown")

    def test_build_heal_info_shape(self) -> None:
        res = HealResult(
            locator=None, strategy="test_id", confidence=95, new_selector_desc="y" * 500
        )
        info = ui_healing.build_heal_info("old-sel", res)
        assert info == {
            "old_selector": "old-sel",
            "new_selector": "y" * 200,
            "strategy": "test_id",
            "confidence": 95,
        }

    def test_original_selector_desc(self) -> None:
        step = _step(selector={"primary": "#p", "fallback_css": "c", "fallback_xpath": "x"})
        assert ui_healing.original_selector_desc(step) == "#p"
        assert ui_healing.original_selector_desc({"selector": "plain"}) == "plain"


# ---------------------------------------------------------------- 引擎钩子（F 矩阵）


def _engine(action: str = "click", active: bool = True) -> UiHeadlessEngine:
    eng = UiHeadlessEngine.__new__(UiHeadlessEngine)
    eng._browser_type = "chromium"
    eng._screenshots_dir = None
    eng._job_id = "job-test"
    eng._healing_active = active
    eng._heal_ctx = "case-test"
    eng._current_step_index = 3
    eng._current_action = action
    eng._current_step = _step(element_info={"test_id": "t"})
    eng._last_heal = None
    eng._heal_attempts = 0
    eng._healed_steps = 0
    eng._heal_once = set()
    return eng


@pytest.fixture
def env_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_mod, "UI_SELF_HEALING_ENABLED", True)


@pytest.fixture
def counted_classify(monkeypatch: pytest.MonkeyPatch) -> List[int]:
    calls: List[int] = []

    def fake_classify(_page: Any, _c: Any) -> Tuple[str, Dict[str, int]]:
        calls.append(1)
        return "not_found", {}

    monkeypatch.setattr(ui_healing, "classify_failure", fake_classify)
    return calls


class TestEngineHookGate:
    def test_f1a_env_off_zero_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(engine_mod, "UI_SELF_HEALING_ENABLED", False)
        eng = _engine()
        calls: List[int] = []

        def spy(*_a: Any) -> Tuple[str, Dict[str, int]]:
            calls.append(1)
            return "exists", {}

        monkeypatch.setattr(ui_healing, "classify_failure", spy)
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is None
        assert calls == [] and eng._heal_attempts == 0

    def test_f1b_env_on_without_headless_flag(self, env_on: None, counted_classify: List[int], monkeypatch: pytest.MonkeyPatch) -> None:
        # V5-1 回归专防：门控不引用 UI_HEADLESS_ENABLED，仅 env 即通
        monkeypatch.setattr(ui_healing, "try_heal", lambda *a: None)
        eng = _engine()
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is None
        assert len(counted_classify) == 1

    def test_f4_assert_exempt(self, env_on: None, counted_classify: List[int]) -> None:
        eng = _engine(action="assert_visible")
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is None
        assert counted_classify == [] and eng._heal_attempts == 0

    def test_f6_login_inactive(self, env_on: None, counted_classify: List[int]) -> None:
        eng = _engine(active=False)  # execute_login_config 全程默认 False
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is None
        assert counted_classify == []

    def test_f8_retry_dedup_once(self, env_on: None, counted_classify: List[int], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ui_healing, "try_heal", lambda *a: None)
        eng = _engine()
        eng._try_self_heal(FakePage(), [("css", "#a")])
        eng._try_self_heal(FakePage(), [("css", "#a")])  # monitored 重入同步骤
        assert len(counted_classify) == 1 and eng._heal_attempts == 1

    def test_f7_f15_circuit_breaker_cap(self, env_on: None, counted_classify: List[int], monkeypatch: pytest.MonkeyPatch, sink_events: List[Dict[str, Any]]) -> None:
        monkeypatch.setattr(ui_healing, "try_heal", lambda *a: None)
        eng = _engine()
        for idx in range(10):  # 10 个不同步骤
            eng._current_step_index = idx
            eng._try_self_heal(FakePage(), [("css", "#a")])
        assert len(counted_classify) == 5  # MAX_PER_CASE 默认 5
        assert eng._heal_attempts == 5
        capped = [e for e in sink_events if e["event"] == "self_healing.capped"]
        assert len(capped) == 1 and capped[0]["heal_count"] == 5

    def test_f2_rejected_events(self, env_on: None, monkeypatch: pytest.MonkeyPatch, sink_events: List[Dict[str, Any]]) -> None:
        monkeypatch.setattr(ui_healing, "classify_failure", lambda *_a: ("exists", {}))
        eng = _engine()
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is None
        assert sink_events[0]["event"] == "self_healing.rejected" and sink_events[0]["reason"] == "exists"
        eng._heal_once.clear()
        eng._current_step_index = 4
        monkeypatch.setattr(ui_healing, "classify_failure", lambda *_a: ("unknown", {}))
        eng._try_self_heal(FakePage(), [("css", "#a")])
        assert sink_events[-1]["reason"] == "unknown"

    def test_f5_low_confidence_rejected(self, env_on: None, monkeypatch: pytest.MonkeyPatch, sink_events: List[Dict[str, Any]]) -> None:
        monkeypatch.setattr(ui_healing, "classify_failure", lambda *_a: ("not_found", {}))
        monkeypatch.setattr(
            ui_healing,
            "try_heal",
            lambda *a: HealResult(locator=FakeLocator(), strategy="xpath_lcs", confidence=50, new_selector_desc="/x"),
        )
        eng = _engine()
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is None
        assert sink_events[-1]["reason"] == "low_confidence" and eng._last_heal is None

    def test_f3_healed_flow_sets_last_heal_and_counter(self, env_on: None, monkeypatch: pytest.MonkeyPatch, sink_events: List[Dict[str, Any]]) -> None:
        monkeypatch.setattr(ui_healing, "classify_failure", lambda *_a: ("not_found", {}))
        hit = FakeLocator(count=1)
        monkeypatch.setattr(
            ui_healing,
            "try_heal",
            lambda *a: HealResult(locator=hit, strategy="test_id", confidence=95, new_selector_desc='[data-testid="t"]'),
        )
        eng = _engine()
        assert eng._try_self_heal(FakePage(), [("css", "#a")]) is hit
        assert eng._healed_steps == 1
        assert eng._last_heal is not None and eng._last_heal["strategy"] == "test_id"
        assert sink_events[-1]["event"] == "self_healing.healed"
        assert sink_events[-1]["confidence"] == 95


class TestStoreHealKeys:
    """S2.1/M4：store 四处键增量 + 旧记录 .get 兼容。"""

    def _store(self, tmp_path: Any) -> Any:
        from postman_api_tester.services.ui_execution_store import UiExecutionStore

        return UiExecutionStore(base_dir=tmp_path)

    def test_create_record_zero_default(self, tmp_path: Any) -> None:
        store = self._store(tmp_path)
        job = store.create_job("c1", "headless", "用例")
        assert store.get_result(job)["healed_steps"] == 0  # type: ignore[index]

    def test_finalize_small_summary_default(self, tmp_path: Any) -> None:
        # M4 风险 1：manager 异常分支固定小 dict 无 healed_steps 键 → 默认 0 不 KeyError
        store = self._store(tmp_path)
        job = store.create_job("c1", "headless", "用例")
        store.finalize_job(job, "failed", {"status": "failed"})
        assert store.get_result(job)["healed_steps"] == 0  # type: ignore[index]

    def test_finalize_reads_summary(self, tmp_path: Any) -> None:
        store = self._store(tmp_path)
        job = store.create_job("c1", "headless", "用例")
        store.finalize_job(job, "passed", {"healed_steps": 3})
        assert store.get_result(job)["healed_steps"] == 3  # type: ignore[index]

    def test_update_step_conditional_double_write(self, tmp_path: Any) -> None:
        store = self._store(tmp_path)
        job = store.create_job("c1", "headless", "用例")
        heal_info = {"old_selector": "#a", "new_selector": "#b", "strategy": "test_id", "confidence": 95}
        store.update_step(job, {"index": 0, "status": "passed", "healed": True, "heal_info": heal_info})
        # post-check 二次回写（不含 heal 键）：合并分支保留 heal 字段
        store.update_step(job, {"index": 0, "status": "failed", "error": "重定向"})
        step = store.get_result(job)["steps"][0]  # type: ignore[index]
        assert step["healed"] is True and step["heal_info"] == heal_info
        assert step["status"] == "failed"

    def test_update_step_no_heal_keys_untouched(self, tmp_path: Any) -> None:
        # browser 模式步骤不产 heal 键 → 不得凭空加字段
        store = self._store(tmp_path)
        job = store.create_job("c1", "browser_replay", "用例")
        store.update_step(job, {"index": 0, "status": "passed"})
        store.update_step(job, {"index": 0, "status": "passed", "duration_ms": 5})
        assert "healed" not in store.get_result(job)["steps"][0]  # type: ignore[index]

    def test_list_results_projection_old_record(self, tmp_path: Any) -> None:
        import json as _json

        store = self._store(tmp_path)
        job = store.create_job("c1", "headless", "旧记录")
        legacy = {"job_id": job, "case_id": "c1", "status": "passed", "steps": []}
        (store.base_dir / f"exec_{job}" / "result.json").write_text(
            _json.dumps(legacy), encoding="utf-8"
        )
        items = store.list_results()
        assert items and items[0]["healed_steps"] == 0  # F-10 旧记录兼容


class TestFindElementHookProtection:
    """V6-1/V6-2：钩子经 _find_element 的端到端保护。"""

    def _failing_page(self) -> FakePage:
        return FakePage(default=FakeLocator(count=0, visible=False))  # is_visible False + wait_for 抛

    def test_default_off_original_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(engine_mod, "UI_SELF_HEALING_ENABLED", False)
        eng = _engine()
        with pytest.raises(TimeoutError):
            eng._find_element(self._failing_page(), "#gone", 1000)  # type: ignore[arg-type]

    def test_heal_chain_crash_keeps_original_exception(self, env_on: None, monkeypatch: pytest.MonkeyPatch, sink_events: List[Dict[str, Any]]) -> None:
        def boom(*_a: Any) -> Any:
            raise RuntimeError("heal infra down")

        monkeypatch.setattr(ui_healing, "classify_failure", boom)
        eng = _engine()
        with pytest.raises(TimeoutError):
            eng._find_element(self._failing_page(), "#gone", 1000)  # type: ignore[arg-type]
        ev = sink_events[-1]
        assert ev["event"] == "self_healing.probe_error" and "heal infra down" in ev["error"]

    def test_heal_hit_returns_locator_through_host(self, env_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ui_healing, "classify_failure", lambda *_a: ("not_found", {}))
        hit = FakeLocator(count=1)
        monkeypatch.setattr(
            ui_healing,
            "try_heal",
            lambda *a: HealResult(locator=hit, strategy="test_id", confidence=95, new_selector_desc='[data-testid="t"]'),
        )
        eng = _engine()
        assert eng._find_element(self._failing_page(), "#gone", 1000) is hit  # type: ignore[arg-type]
