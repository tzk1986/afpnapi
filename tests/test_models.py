"""models 模块单元测试。

覆盖 filter_report_results、paginate_items、map_results、_to_rate、compare_report_data。
"""

from typing import Any, Dict, List
from unittest.mock import patch

from postman_api_tester.models import (
    _to_rate,
    compare_report_data,
    filter_report_results,
    map_results,
    paginate_items,
)


class TestPaginateItems:
    """paginate_items() 分页测试。"""

    def _make_items(self, n: int) -> List[Dict[str, Any]]:
        return [{"id": i, "name": f"item_{i}"} for i in range(n)]

    def test_first_page(self) -> None:
        items = self._make_items(25)
        result = paginate_items(items, page=1, page_size=10)
        assert len(result["items"]) == 10
        assert result["items"][0]["id"] == 0
        assert result["items"][9]["id"] == 9
        assert result["page"] == 1
        assert result["total"] == 25
        assert result["total_pages"] == 3
        assert result["page_size"] == 10

    def test_middle_page(self) -> None:
        items = self._make_items(25)
        result = paginate_items(items, page=2, page_size=10)
        assert len(result["items"]) == 10
        assert result["items"][0]["id"] == 10
        assert result["page"] == 2

    def test_last_page_partial(self) -> None:
        items = self._make_items(25)
        result = paginate_items(items, page=3, page_size=10)
        assert len(result["items"]) == 5
        assert result["items"][0]["id"] == 20

    def test_page_beyond_total(self) -> None:
        items = self._make_items(5)
        result = paginate_items(items, page=10, page_size=10)
        assert result["page"] == 1
        assert len(result["items"]) == 5

    def test_empty_list(self) -> None:
        result = paginate_items([], page=1, page_size=10)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 1
        assert result["page"] == 1

    def test_exact_page_boundary(self) -> None:
        items = self._make_items(20)
        result = paginate_items(items, page=2, page_size=10)
        assert len(result["items"]) == 10
        assert result["total_pages"] == 2

    def test_single_item(self) -> None:
        items = self._make_items(1)
        result = paginate_items(items, page=1, page_size=10)
        assert len(result["items"]) == 1
        assert result["total_pages"] == 1


class TestMapResults:
    """map_results() 结果映射测试。"""

    def test_basic_mapping(self) -> None:
        report = {
            "results": [
                {"key": "a", "name": "Alpha"},
                {"key": "b", "name": "Beta"},
            ]
        }
        result = map_results(report)
        assert result["a"]["name"] == "Alpha"
        assert result["b"]["name"] == "Beta"

    def test_empty_results(self) -> None:
        assert map_results({"results": []}) == {}

    def test_missing_results_key(self) -> None:
        assert map_results({}) == {}

    def test_duplicate_key_last_wins(self) -> None:
        report = {
            "results": [
                {"key": "a", "name": "first"},
                {"key": "a", "name": "second"},
            ]
        }
        result = map_results(report)
        assert result["a"]["name"] == "second"


class TestToRate:
    """_to_rate() 百分比字符串解析测试。"""

    def test_normal_percentage(self) -> None:
        assert _to_rate("66.67%") == 66.67

    def test_hundred_percent(self) -> None:
        assert _to_rate("100%") == 100.0

    def test_zero_percent(self) -> None:
        assert _to_rate("0%") == 0.0

    def test_plain_number_string(self) -> None:
        assert _to_rate("42.5") == 42.5

    def test_invalid_returns_zero(self) -> None:
        assert _to_rate("abc") == 0.0

    def test_empty_string_returns_zero(self) -> None:
        assert _to_rate("") == 0.0


class TestCompareReportData:
    """compare_report_data() 报告对比测试。"""

    def _make_report(
        self, results: List[Dict[str, Any]], rate: str = "100%"
    ) -> Dict[str, Any]:
        return {
            "results": results,
            "summary": {"success_rate": rate},
        }

    def test_identical_reports(self) -> None:
        results = [{"key": "a", "status": "PASSED", "status_code": 200, "name": "A"}]
        report = self._make_report(results, "100%")
        result = compare_report_data(report, report)
        assert result["summary"]["added_count"] == 0
        assert result["summary"]["removed_count"] == 0
        assert result["summary"]["changed_count"] == 0
        assert result["summary"]["success_rate_delta"] == 0.0

    def test_added_keys(self) -> None:
        left = self._make_report([{"key": "a", "status": "PASSED", "status_code": 200}])
        right = self._make_report(
            [
                {"key": "a", "status": "PASSED", "status_code": 200},
                {"key": "b", "status": "PASSED", "status_code": 200},
            ]
        )
        result = compare_report_data(left, right)
        assert result["summary"]["added_count"] == 1
        assert len(result["added"]) == 1
        assert result["added"][0]["key"] == "b"

    def test_removed_keys(self) -> None:
        left = self._make_report(
            [
                {"key": "a", "status": "PASSED", "status_code": 200},
                {"key": "b", "status": "PASSED", "status_code": 200},
            ]
        )
        right = self._make_report(
            [{"key": "a", "status": "PASSED", "status_code": 200}]
        )
        result = compare_report_data(left, right)
        assert result["summary"]["removed_count"] == 1
        assert len(result["removed"]) == 1
        assert result["removed"][0]["key"] == "b"

    def test_changed_status(self) -> None:
        left = self._make_report(
            [{"key": "a", "status": "PASSED", "status_code": 200, "name": "A"}]
        )
        right = self._make_report(
            [{"key": "a", "status": "FAILED", "status_code": 500, "name": "A"}]
        )
        result = compare_report_data(left, right)
        assert result["summary"]["changed_count"] == 1
        changed = result["changed"][0]
        assert changed["before_status"] == "PASSED"
        assert changed["after_status"] == "FAILED"
        assert changed["before_status_code"] == 200
        assert changed["after_status_code"] == 500

    def test_status_code_change_only(self) -> None:
        left = self._make_report([{"key": "a", "status": "PASSED", "status_code": 200}])
        right = self._make_report(
            [{"key": "a", "status": "PASSED", "status_code": 201}]
        )
        result = compare_report_data(left, right)
        assert result["summary"]["changed_count"] == 1

    def test_no_change_when_same(self) -> None:
        left = self._make_report([{"key": "a", "status": "PASSED", "status_code": 200}])
        right = self._make_report(
            [{"key": "a", "status": "PASSED", "status_code": 200}]
        )
        result = compare_report_data(left, right)
        assert result["summary"]["changed_count"] == 0

    def test_success_rate_delta(self) -> None:
        left = self._make_report([], rate="80%")
        right = self._make_report([], rate="95%")
        result = compare_report_data(left, right)
        assert result["summary"]["success_rate_delta"] == 15.0
        assert result["summary"]["success_rate_delta_text"] == "+15.00%"

    def test_negative_delta(self) -> None:
        left = self._make_report([], rate="90%")
        right = self._make_report([], rate="70%")
        result = compare_report_data(left, right)
        assert result["summary"]["success_rate_delta"] == -20.0
        assert result["summary"]["success_rate_delta_text"] == "-20.00%"

    def test_empty_reports(self) -> None:
        left = self._make_report([])
        right = self._make_report([])
        result = compare_report_data(left, right)
        assert result["summary"]["added_count"] == 0
        assert result["summary"]["removed_count"] == 0
        assert result["summary"]["changed_count"] == 0

    def test_added_keys_sorted(self) -> None:
        left = self._make_report([])
        right = self._make_report(
            [
                {"key": "c", "status": "PASSED", "status_code": 200},
                {"key": "a", "status": "PASSED", "status_code": 200},
                {"key": "b", "status": "PASSED", "status_code": 200},
            ]
        )
        result = compare_report_data(left, right)
        added_keys = [item["key"] for item in result["added"]]
        assert added_keys == ["a", "b", "c"]


class TestFilterReportResults:
    """filter_report_results() 筛选测试。"""

    @patch("postman_api_tester.models.load_report_details_map")
    def test_empty_report_returns_empty_list(self, mock_load: Any) -> None:
        mock_load.return_value = {}
        report = {"results": []}
        result = filter_report_results(report, "", None, "", "")
        assert result == []

    @patch("postman_api_tester.models.load_report_details_map")
    def test_no_filters_returns_all(self, mock_load: Any) -> None:
        mock_load.return_value = {}
        report = {
            "results": [
                {"name": "API1", "status": "PASSED"},
                {"name": "API2", "status": "FAILED"},
            ]
        }
        result = filter_report_results(report, "", None, "", "")
        assert len(result) == 2
        assert result[0]["name"] == "API1"
        assert result[1]["name"] == "API2"

    @patch("postman_api_tester.models.load_report_details_map")
    def test_status_filter(self, mock_load: Any) -> None:
        mock_load.return_value = {}
        report = {
            "results": [
                {"name": "API1", "status": "PASSED"},
                {"name": "API2", "status": "FAILED"},
                {"name": "API3", "status": "PASSED"},
            ]
        }
        result = filter_report_results(report, "", "PASSED", "", "")
        assert len(result) == 2
        assert all(item["status"] == "PASSED" for item in result)

    @patch("postman_api_tester.models.load_report_details_map")
    def test_keyword_filter(self, mock_load: Any) -> None:
        mock_load.return_value = {}
        report = {
            "results": [
                {"name": "User API", "url": "http://test.com", "folder": "Users"},
                {"name": "Order API", "url": "http://test.com", "folder": "Orders"},
            ]
        }
        result = filter_report_results(report, "user", None, "", "")
        assert len(result) == 1
        assert result[0]["name"] == "User API"

    @patch("postman_api_tester.models.load_report_details_map")
    def test_message_keyword_filter(self, mock_load: Any) -> None:
        mock_load.return_value = {}
        report = {
            "results": [
                {"name": "API1", "message": "Success"},
                {"name": "API2", "message": "Connection timeout"},
            ]
        }
        result = filter_report_results(report, "", None, "timeout", "")
        assert len(result) == 1
        assert result[0]["name"] == "API2"

    @patch("postman_api_tester.models.load_report_details_map")
    def test_err_code_keyword_filter(self, mock_load: Any) -> None:
        mock_load.return_value = {}
        report = {
            "results": [
                {"name": "API1", "err_code": "E001"},
                {"name": "API2", "err_code": "E002"},
            ]
        }
        result = filter_report_results(report, "", None, "", "E002")
        assert len(result) == 1
        assert result[0]["name"] == "API2"

    @patch("postman_api_tester.models._result_exclusion_key")
    @patch("postman_api_tester.models.load_report_details_map")
    def test_exclude_excluded_items(
        self, mock_load: Any, mock_exclusion_key: Any
    ) -> None:
        mock_load.return_value = {}
        mock_exclusion_key.side_effect = (
            lambda item: f"{item.get('method')}:{item.get('url')}"
        )
        report = {
            "results": [
                {"name": "API1", "method": "GET", "url": "http://test.com/api1"},
                {"name": "API2", "method": "GET", "url": "http://test.com/api2"},
            ],
            "manual_exclusions": ["GET:http://test.com/api1"],
        }
        result = filter_report_results(report, "", None, "", "", include_excluded=False)
        assert len(result) == 1
        assert result[0]["name"] == "API2"

    @patch("postman_api_tester.models._result_exclusion_key")
    @patch("postman_api_tester.models.load_report_details_map")
    def test_include_excluded_items(
        self, mock_load: Any, mock_exclusion_key: Any
    ) -> None:
        mock_load.return_value = {}
        mock_exclusion_key.side_effect = (
            lambda item: f"{item.get('method')}:{item.get('url')}"
        )
        report = {
            "results": [
                {"name": "API1", "method": "GET", "url": "http://test.com/api1"},
            ],
            "manual_exclusions": ["GET:http://test.com/api1"],
        }
        result = filter_report_results(report, "", None, "", "", include_excluded=True)
        assert len(result) == 1
        assert result[0]["excluded"] is True

    @patch("postman_api_tester.models.load_report_details_map")
    def test_result_fields_include_repeat_info(self, mock_load: Any) -> None:
        mock_load.return_value = {"0": {}}
        report = {
            "results": [
                {
                    "name": "API1",
                    "folder": "Folder1",
                    "method": "GET",
                    "url": "http://test.com",
                    "status": "PASSED",
                    "status_code": 200,
                    "message": "OK",
                    "err_code": "",
                    "response_time_ms": 150,
                    "data_index": 0,
                    "repeat_index": 1,
                    "repeat_total": 3,
                    "repeat_group": "data-driven-1",
                }
            ]
        }
        result = filter_report_results(report, "", None, "", "")
        assert len(result) == 1
        item = result[0]
        assert item["index"] == 0
        assert item["name"] == "API1"
        assert item["folder"] == "Folder1"
        assert item["method"] == "GET"
        assert item["url"] == "http://test.com"
        assert item["status"] == "PASSED"
        assert item["status_code"] == 200
        assert item["message"] == "OK"
        assert item["response_time_ms"] == 150
        assert item["repeat_index"] == 1
        assert item["repeat_total"] == 3
        assert item["repeat_group"] == "data-driven-1"
        assert item["detail_available"] is True

    @patch("postman_api_tester.models.load_report_details_map")
    def test_repeat_fields_default(self, mock_load: Any) -> None:
        """当 item 缺少 repeat_* 字段时使用默认值。"""
        mock_load.return_value = {}
        report = {"results": [{"name": "API1", "status": "PASSED"}]}
        result = filter_report_results(report, "", None, "", "")
        assert result[0]["repeat_index"] == 0
        assert result[0]["repeat_total"] == 1
        assert result[0]["repeat_group"] == ""
