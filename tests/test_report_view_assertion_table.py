"""report_view.html 断言结果表布局回归钉桩。

v1.37.21：断言表必须 table-layout:fixed + colgroup 定宽，
长断言内容在单元格内换行，不得撑破执行详情弹窗布局。
"""

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "report_view.html"
)


def _assertion_fn_source() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("function renderAssertionResultsHtml")
    end = text.index("function toggleHistory", start)
    return text[start:end]


def test_table_uses_fixed_layout() -> None:
    src = _assertion_fn_source()
    assert "table-layout:fixed" in src


def test_table_has_colgroup_columns() -> None:
    src = _assertion_fn_source()
    assert "<colgroup>" in src
    assert src.count("<col ") + src.count("<col>") >= 6


def test_cells_wrap_long_content() -> None:
    src = _assertion_fn_source()
    assert "word-break:break-all" in src
    assert "overflow-wrap:anywhere" in src


def test_dialog_has_min_width_zero_guard() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert ".detail-dialog" in text
    dialog_rule = text[text.index(".detail-dialog {") : text.index("\n", text.index(".detail-dialog {"))]
    assert "min-width: 0" in dialog_rule
