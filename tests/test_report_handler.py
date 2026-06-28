"""Tests for postman_api_tester.handlers.report_handler."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from postman_api_tester.handlers.report_handler import (
    normalize_status_filter,
    filter_report_results,
    paginate_items,
    compare_report_data,
    _to_rate,
    _map_results,
)


class TestNormalizeStatusFilter:
    """Tests for normalize_status_filter."""

    def test_empty_string_returns_none(self):
        """Test empty string returns None."""
        assert normalize_status_filter("") is None

    def test_none_returns_none(self):
        """Test None returns None."""
        assert normalize_status_filter(None) is None  # type: ignore

    def test_all_aliases_return_none(self):
        """Test 'ALL' and aliases return None."""
        assert normalize_status_filter("ALL") is None
        assert normalize_status_filter("all") is None
        assert normalize_status_filter("RESULT") is None
        assert normalize_status_filter("全部") is None
        assert normalize_status_filter("结果") is None

    def test_passed_aliases(self):
        """Test PASSED and aliases."""
        assert normalize_status_filter("PASSED") == "PASSED"
        assert normalize_status_filter("passed") == "PASSED"
        assert normalize_status_filter("SUCCESS") == "PASSED"
        assert normalize_status_filter("成功") == "PASSED"

    def test_failed_aliases(self):
        """Test FAILED and aliases."""
        assert normalize_status_filter("FAILED") == "FAILED"
        assert normalize_status_filter("failed") == "FAILED"
        assert normalize_status_filter("FAIL") == "FAILED"
        assert normalize_status_filter("失败") == "FAILED"

    def test_error_aliases(self):
        """Test ERROR and aliases."""
        assert normalize_status_filter("ERROR") == "ERROR"
        assert normalize_status_filter("error") == "ERROR"
        assert normalize_status_filter("错误") == "ERROR"

    def test_unknown_status_returns_none(self):
        """Test unknown status returns None."""
        assert normalize_status_filter("UNKNOWN") is None
        assert normalize_status_filter("RANDOM") is None

    def test_whitespace_handling(self):
        """Test whitespace is trimmed."""
        assert normalize_status_filter("  PASSED  ") == "PASSED"
        assert normalize_status_filter("\tFAILED\n") == "FAILED"


class TestFilterReportResults:
    """Tests for filter_report_results."""

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_empty_report_returns_empty_list(self, mock_load):
        """Test empty report returns empty list."""
        mock_load.return_value = {}
        report = {"results": []}

        result = filter_report_results(report, "", None, "", "")

        assert result == []

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_no_filters_returns_all(self, mock_load):
        """Test no filters returns all results."""
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

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_status_filter(self, mock_load):
        """Test status filter."""
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

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_keyword_filter(self, mock_load):
        """Test keyword filter matches name/url/folder."""
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

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_message_keyword_filter(self, mock_load):
        """Test message keyword filter."""
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

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_err_code_keyword_filter(self, mock_load):
        """Test error code keyword filter."""
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

    @patch("postman_api_tester.handlers.report_handler._result_exclusion_key")
    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_exclude_excluded_items(self, mock_load, mock_exclusion_key):
        """Test excluded items are filtered out when include_excluded=False."""
        mock_load.return_value = {}
        mock_exclusion_key.side_effect = lambda item: f"{item.get('method')}:{item.get('url')}"

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

    @patch("postman_api_tester.handlers.report_handler._result_exclusion_key")
    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_include_excluded_items(self, mock_load, mock_exclusion_key):
        """Test excluded items are included when include_excluded=True."""
        mock_load.return_value = {}
        mock_exclusion_key.side_effect = lambda item: f"{item.get('method')}:{item.get('url')}"

        report = {
            "results": [
                {"name": "API1", "method": "GET", "url": "http://test.com/api1"},
            ],
            "manual_exclusions": ["GET:http://test.com/api1"],
        }

        result = filter_report_results(report, "", None, "", "", include_excluded=True)

        assert len(result) == 1
        assert result[0]["excluded"] is True

    @patch("postman_api_tester.handlers.report_handler.load_report_details_map")
    def test_result_fields(self, mock_load):
        """Test result contains expected fields."""
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
        assert item["detail_available"] is True


class TestPaginateItems:
    """Tests for paginate_items."""

    def test_empty_list(self):
        """Test empty list pagination."""
        result = paginate_items([], 1, 10)

        assert result["items"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 1
        assert result["page"] == 1

    def test_single_page(self):
        """Test single page pagination."""
        items = [{"id": i} for i in range(5)]

        result = paginate_items(items, 1, 10)

        assert len(result["items"]) == 5
        assert result["total"] == 5
        assert result["total_pages"] == 1
        assert result["page"] == 1

    def test_multiple_pages(self):
        """Test multiple pages pagination."""
        items = [{"id": i} for i in range(25)]

        result = paginate_items(items, 2, 10)

        assert len(result["items"]) == 10
        assert result["items"][0]["id"] == 10
        assert result["total"] == 25
        assert result["total_pages"] == 3
        assert result["page"] == 2

    def test_last_page(self):
        """Test last page with partial items."""
        items = [{"id": i} for i in range(25)]

        result = paginate_items(items, 3, 10)

        assert len(result["items"]) == 5
        assert result["items"][0]["id"] == 20
        assert result["page"] == 3

    def test_page_beyond_total(self):
        """Test page number beyond total pages."""
        items = [{"id": i} for i in range(10)]

        result = paginate_items(items, 5, 10)

        assert result["page"] == 1  # Clamped to last valid page
        assert len(result["items"]) == 10


class TestCompareReportData:
    """Tests for compare_report_data."""

    def test_identical_reports(self):
        """Test identical reports show no changes."""
        report = {
            "results": [
                {"key": "api1", "name": "API1", "status": "PASSED", "status_code": 200}
            ],
            "summary": {"success_rate": "100%"},
        }

        result = compare_report_data(report, report)

        assert result["summary"]["added_count"] == 0
        assert result["summary"]["removed_count"] == 0
        assert result["summary"]["changed_count"] == 0
        assert result["summary"]["success_rate_delta"] == 0.0

    def test_added_apis(self):
        """Test new APIs in right report."""
        left = {
            "results": [{"key": "api1", "name": "API1", "status": "PASSED"}],
            "summary": {"success_rate": "100%"},
        }
        right = {
            "results": [
                {"key": "api1", "name": "API1", "status": "PASSED"},
                {"key": "api2", "name": "API2", "status": "PASSED"},
            ],
            "summary": {"success_rate": "100%"},
        }

        result = compare_report_data(left, right)

        assert result["summary"]["added_count"] == 1
        assert len(result["added"]) == 1
        assert result["added"][0]["name"] == "API2"

    def test_removed_apis(self):
        """Test removed APIs in right report."""
        left = {
            "results": [
                {"key": "api1", "name": "API1", "status": "PASSED"},
                {"key": "api2", "name": "API2", "status": "PASSED"},
            ],
            "summary": {"success_rate": "100%"},
        }
        right = {
            "results": [{"key": "api1", "name": "API1", "status": "PASSED"}],
            "summary": {"success_rate": "100%"},
        }

        result = compare_report_data(left, right)

        assert result["summary"]["removed_count"] == 1
        assert len(result["removed"]) == 1
        assert result["removed"][0]["name"] == "API2"

    def test_status_changes(self):
        """Test status changes between reports."""
        left = {
            "results": [
                {"key": "api1", "name": "API1", "status": "PASSED", "status_code": 200},
                {"key": "api2", "name": "API2", "status": "PASSED", "status_code": 200},
            ],
            "summary": {"success_rate": "100%"},
        }
        right = {
            "results": [
                {"key": "api1", "name": "API1", "status": "FAILED", "status_code": 500},
                {"key": "api2", "name": "API2", "status": "PASSED", "status_code": 200},
            ],
            "summary": {"success_rate": "50%"},
        }

        result = compare_report_data(left, right)

        assert result["summary"]["changed_count"] == 1
        assert len(result["changed"]) == 1
        change = result["changed"][0]
        assert change["key"] == "api1"
        assert change["before_status"] == "PASSED"
        assert change["after_status"] == "FAILED"
        assert change["before_status_code"] == 200
        assert change["after_status_code"] == 500

    def test_success_rate_delta(self):
        """Test success rate delta calculation."""
        left = {
            "results": [],
            "summary": {"success_rate": "80%"},
        }
        right = {
            "results": [],
            "summary": {"success_rate": "90%"},
        }

        result = compare_report_data(left, right)

        assert result["summary"]["success_rate_delta"] == 10.0
        assert result["summary"]["success_rate_delta_text"] == "+10.00%"

    def test_negative_delta(self):
        """Test negative success rate delta."""
        left = {
            "results": [],
            "summary": {"success_rate": "90%"},
        }
        right = {
            "results": [],
            "summary": {"success_rate": "80%"},
        }

        result = compare_report_data(left, right)

        assert result["summary"]["success_rate_delta"] == -10.0
        assert result["summary"]["success_rate_delta_text"] == "-10.00%"


class TestHelpers:
    """Tests for helper functions."""

    def test_to_rate_valid_percentage(self):
        """Test _to_rate with valid percentage."""
        assert _to_rate("95%") == 95.0
        assert _to_rate("100%") == 100.0
        assert _to_rate("0%") == 0.0

    def test_to_rate_without_percent(self):
        """Test _to_rate without percent sign."""
        assert _to_rate("95") == 95.0

    def test_to_rate_invalid(self):
        """Test _to_rate with invalid input."""
        assert _to_rate("invalid") == 0.0
        assert _to_rate("") == 0.0

    def test_map_results(self):
        """Test _map_results creates key-based map."""
        report = {
            "results": [
                {"key": "api1", "name": "API1"},
                {"key": "api2", "name": "API2"},
            ]
        }

        result = _map_results(report)

        assert len(result) == 2
        assert result["api1"]["name"] == "API1"
        assert result["api2"]["name"] == "API2"

    def test_map_results_empty(self):
        """Test _map_results with empty results."""
        report = {"results": []}

        result = _map_results(report)

        assert result == {}
