"""report_list_service 单元测试。"""

from typing import Any, Dict

from postman_api_tester.services.report_list_service import (
    is_total_report_name,
    report_list_item,
)


class TestReportListItem:
    """report_list_item 测试。"""

    def test_basic_fields(self) -> None:
        """基本字段正确提取。"""
        report: Dict[str, Any] = {
            "report_name": "test_report",
            "generated_at": "2026-06-16 10:00:00",
            "host_name": "localhost",
            "collection_name": "API Collection",
            "source_file": "api.json",
            "source_original_file": "api.json",
            "summary": {"total": 10, "passed": 8, "failed": 1, "error": 1, "success_rate": "80%"},
        }
        item = report_list_item(report)
        assert item["report_name"] == "test_report"
        assert item["generated_at"] == "2026-06-16 10:00:00"
        assert item["host_name"] == "localhost"
        assert item["collection_name"] == "API Collection"
        assert item["summary"]["total"] == 10
        assert item["summary"]["passed"] == 8
        assert item["summary"]["failed"] == 1
        assert item["summary"]["error"] == 1
        assert item["summary"]["success_rate"] == "80%"

    def test_missing_summary(self) -> None:
        """缺少 summary 时使用默认值。"""
        report: Dict[str, Any] = {"report_name": "test"}
        item = report_list_item(report)
        assert item["summary"]["total"] == 0
        assert item["summary"]["passed"] == 0
        assert item["summary"]["failed"] == 0
        assert item["summary"]["error"] == 0
        assert item["summary"]["success_rate"] == "0%"

    def test_none_summary(self) -> None:
        """summary 为 None 时使用默认值。"""
        report: Dict[str, Any] = {"report_name": "test", "summary": None}
        item = report_list_item(report)
        assert item["summary"]["total"] == 0

    def test_legacy_flag(self) -> None:
        """legacy 标志正确传递。"""
        report: Dict[str, Any] = {"report_name": "old", "legacy": True, "summary": {}}
        item = report_list_item(report)
        assert item["legacy"] is True

    def test_not_legacy(self) -> None:
        """非 legacy 报告。"""
        report: Dict[str, Any] = {"report_name": "new", "summary": {}}
        item = report_list_item(report)
        assert item["legacy"] is False

    def test_load_error(self) -> None:
        """load_error 字段传递。"""
        report: Dict[str, Any] = {"report_name": "broken", "load_error": "parse failed", "summary": {}}
        item = report_list_item(report)
        assert item["load_error"] == "parse failed"

    def test_does_not_include_full_results(self) -> None:
        """不包含完整 results 数据。"""
        report: Dict[str, Any] = {
            "report_name": "test",
            "results": [{"name": "req1"}, {"name": "req2"}],
            "summary": {"total": 2},
        }
        item = report_list_item(report)
        assert "results" not in item
        assert "request_info" not in item
        assert "response_info" not in item


class TestIsTotalReportName:
    """is_total_report_name 测试。"""

    def test_total_name(self) -> None:
        """总报告名（无 _page_ 标记）返回 True。"""
        assert is_total_report_name("postman_report_20260616") is True

    def test_page_name(self) -> None:
        """分页报告名（含 _page_）返回 False。"""
        assert is_total_report_name("postman_report_20260616_page_1") is False

    def test_case_insensitive(self) -> None:
        """大小写不敏感。"""
        assert is_total_report_name("report_PAGE_2") is False

    def test_empty_string(self) -> None:
        """空字符串返回 True。"""
        assert is_total_report_name("") is True

    def test_none(self) -> None:
        """None 返回 True。"""
        assert is_total_report_name(None) is True  # type: ignore[arg-type]
