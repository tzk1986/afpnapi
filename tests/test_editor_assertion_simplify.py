"""v1.38.2 断言页签 A+C 简化模板钉桩。

A：四键存储不动、渲染归并两卡片（本接口规则/集合共享规则），阶段徽标区分；
C：成功标准 radio 快捷双关/双继承，三态折叠 details 保留，空断言 confirm。
"""

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "collection_editor.html"
)


def _fn_source(start_marker: str, end_marker: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _tab_source() -> str:
    return _fn_source(
        "function renderAssertionTab", "function updateJudgmentField"
    )


def test_render_rule_rows_with_badge_exists() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "function renderRuleRowsWithBadge" in text


def test_tab_merged_into_two_cards() -> None:
    src = _tab_source()
    assert "本接口规则" in src
    assert "集合共享规则（作用于本集合全部接口）" in src
    # 旧五区块标题不得再直出
    for gone in (
        ">一级判定<",
        "自定义判定规则（内置判定通过后执行",
        "集合共享断言（统一判断",
        "集合共享判定（统一业务判定",
    ):
        assert gone not in src, f"旧区块标题仍直出: {gone}"


def test_storage_keys_untouched_in_tab() -> None:
    src = _tab_source()
    for key in (
        "x_judgment_rules",
        "x_assertions",
        "x_shared_assertions",
        "x_shared_judgment_rules",
        "x_skip_shared_assertions",
        "x_enable_err_code_judgment",
        "x_enable_message_judgment",
    ):
        assert key in src, f"存储键 {key} 应仍被页签读取（A 方案不动存储）"


def test_four_prefix_handlers_undispatched_in_merge() -> None:
    src = _tab_source()
    for prefix in ("prefix: 'Judgment'", "prefix: ''", "prefix: 'Shared'", "prefix: 'SharedJ'"):
        assert prefix in src, f"合并渲染应覆盖 {prefix} 的行 handler 分派"


def test_badge_and_phase_select() -> None:
    src = _tab_source()
    assert "badge: '判定'" in src and "badge: '断言'" in src
    assert "#f59e0b" in src and "#10b981" in src
    assert 'id="addPhaseSel"' in src and 'id="addSharedPhaseSel"' in src
    assert "addRuleWithPhase('addPhaseSel')" in src
    assert "addSharedRuleWithPhase('addSharedPhaseSel')" in src


def test_tristate_collapsed_but_kept() -> None:
    src = _tab_source()
    assert "<details" in src and "⚙ 精细控制" in src
    assert "renderJudgmentTriState('x_enable_err_code_judgment'" in src
    assert "renderJudgmentTriState('x_enable_message_judgment'" in src


def test_success_mode_radio() -> None:
    src = _tab_source()
    assert 'name="ifSuccessMode"' in src
    assert "updateJudgmentMode('builtin')" in src
    assert "updateJudgmentMode('assert')" in src
    # 接管态判定 = 三态双 false 的等价快捷
    assert "x_enable_err_code_judgment === false && req.x_enable_message_judgment === false" in src


def test_update_judgment_mode_semantics() -> None:
    src = _fn_source("function updateJudgmentMode", "// v1.37.22")
    assert "x_enable_err_code_judgment = false" in src
    assert "x_enable_message_judgment = false" in src
    assert "x_enable_err_code_judgment = null" in src
    assert "x_enable_message_judgment = null" in src
    assert "confirm(" in src
    # 空断言口径只计自有+共享断言，判定规则不计（三态双关时判定一并跳过）
    assert "x_assertions" in src and "x_shared_assertions" in src
    assert "x_judgment_rules" not in src and "x_shared_judgment_rules" not in src


def test_phase_dispatch_functions() -> None:
    src = _fn_source("function addRuleWithPhase", "function addSharedRuleWithPhase")
    assert "addJudgmentRule()" in src and "addAssertion()" in src
    src2 = _fn_source("function addSharedRuleWithPhase", "function renderPreRequestTab")
    assert "addSharedJudgmentRule()" in src2 and "addSharedAssertion()" in src2


def test_legacy_row_handlers_preserved() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for fn in (
        "function addJudgmentRule(",
        "function removeJudgmentAssertion(",
        "function updateJudgmentAssertionField(",
        "function updateJudgmentAssertionOp(",
        "function addSharedJudgmentRule(",
        "function removeSharedJAssertion(",
        "function updateSharedJAssertionField(",
        "function updateSharedJAssertionOp(",
        "function addSharedAssertion(",
        "function removeSharedAssertion(",
        "function updateSharedAssertionField(",
        "function updateSharedAssertionOp(",
        "function addAssertion(",
    ):
        assert fn in text, f"既有 handler {fn} 必须保留（存储与行编辑零变化）"
