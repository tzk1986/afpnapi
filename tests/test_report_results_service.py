"""Tests for postman_api_tester.services.report_results_service."""

import pytest
from unittest.mock import patch, MagicMock

from postman_api_tester.services.report_results_service import (
    build_report_results_payload,
    build_compare_payload,
    build_result_detail_payload,
    build_manual_cases_payload,
    build_manual_case_upsert_payload,
    build_manual_case_delete_payload,
    build_case_exclusion_payload,
    build_result_judgement_payload,
    build_export_collection_payload,
    build_report_meta_payload,
    build_report_delete_payload,
    build_retry_queued_payload,
    build_health_payload,
    build_test_token_payload,
    build_environments_payload,
    build_collection_preview_payload,
    build_job_queued_payload,
    build_re_request_success_payload,
    build_proxy_response_payload,
    build_re_request_error_payload,
    build_error_payload,
)


class TestBuildReportResultsPayload:
    """Tests for build_report_results_payload."""

    @patch("postman_api_tester.services.report_results_service.paginate_items")
    @patch("postman_api_tester.services.report_results_service.filter_report_results")
    def test_basic_filter_and_paginate(self, mock_filter, mock_paginate):
        """Test basic filtering and pagination flow."""
        mock_filter.return_value = [{"name": "test1"}, {"name": "test2"}]
        mock_paginate.return_value = {"items": [{"name": "test1"}], "total": 2}

        report = {"report_name": "Test Report", "results": []}
        result = build_report_results_payload(
            report=report,
            page=1,
            page_size=10,
            keyword="test",
            message_keyword="",
            err_code_keyword="",
            status_filter="passed",
            include_excluded=False,
        )

        mock_filter.assert_called_once_with(
            report, "test", "passed", "", "", include_excluded=False
        )
        mock_paginate.assert_called_once_with(mock_filter.return_value, 1, 10)
        assert result["report_name"] == "Test Report"
        assert result["query"] == "test"
        assert result["status"] == "passed"
        assert result["include_excluded"] is False

    @patch("postman_api_tester.services.report_results_service.paginate_items")
    @patch("postman_api_tester.services.report_results_service.filter_report_results")
    def test_status_filter_none_becomes_all(self, mock_filter, mock_paginate):
        """Test that None status_filter becomes 'all'."""
        mock_filter.return_value = []
        mock_paginate.return_value = {"items": [], "total": 0}

        report = {"report_name": "R1", "results": []}
        result = build_report_results_payload(
            report, 1, 10, "", "", "", None, False
        )

        assert result["status"] == "all"


class TestBuildComparePayload:
    """Tests for build_compare_payload."""

    @patch("postman_api_tester.services.report_results_service.compare_report_data")
    def test_delegates_to_compare_function(self, mock_compare):
        """Test that compare payload delegates to compare_report_data."""
        mock_compare.return_value = {"diff": "data"}
        left = {"results": []}
        right = {"results": []}

        result = build_compare_payload(left, right)

        mock_compare.assert_called_once_with(left, right)
        assert result == {"diff": "data"}


class TestBuildResultDetailPayload:
    """Tests for build_result_detail_payload."""

    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_valid_index_returns_detail(self, mock_load):
        """Test valid index returns complete detail payload."""
        mock_load.return_value = {
            "0": {
                "request_info": {"headers": {"X-Test": "value"}},
                "response_info": {"headers": {}, "body": "ok"},
            }
        }

        report = {
            "results": [
                {
                    "name": "API1",
                    "folder": "Folder1",
                    "method": "GET",
                    "url": "http://example.com",
                    "status": "passed",
                    "status_code": 200,
                }
            ],
            "manual_exclusions": [],
        }

        result = build_result_detail_payload(report, 0)

        assert result["index"] == 0
        assert result["name"] == "API1"
        assert result["folder"] == "Folder1"
        assert result["method"] == "GET"
        assert result["detail_available"] is True
        assert result["request_info"]["headers"]["X-Test"] == "value"
        assert result["response_info"]["body"] == "ok"

    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_invalid_index_raises_index_error(self, mock_load):
        """Test negative index raises IndexError."""
        report = {"results": [{"name": "API1"}], "manual_exclusions": []}

        with pytest.raises(IndexError):
            build_result_detail_payload(report, -1)

    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_out_of_range_index_raises_index_error(self, mock_load):
        """Test out-of-range index raises IndexError."""
        report = {"results": [{"name": "API1"}], "manual_exclusions": []}

        with pytest.raises(IndexError):
            build_result_detail_payload(report, 5)

    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_missing_detail_returns_defaults(self, mock_load):
        """Test missing detail returns default request/response info."""
        mock_load.return_value = {}

        report = {
            "results": [{"name": "API1", "method": "POST", "url": "http://test.com"}],
            "manual_exclusions": [],
        }

        result = build_result_detail_payload(report, 0)

        assert result["detail_available"] is False
        assert result["request_info"] == {"headers": {}, "params": {}, "body": None}
        assert result["response_info"] == {"headers": {}, "body": None}

    @patch("postman_api_tester.services.report_results_service.result_exclusion_key")
    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_exclusion_check(self, mock_load, mock_exclusion_key):
        """Test exclusion status is correctly computed."""
        mock_load.return_value = {}
        mock_exclusion_key.return_value = "GET:http://test.com/api1"

        report = {
            "results": [
                {"name": "API1", "method": "GET", "url": "http://test.com/api1"}
            ],
            "manual_exclusions": ["GET:http://test.com/api1"],
        }

        result = build_result_detail_payload(report, 0)

        assert result["excluded"] is True

    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_judgement_source_manual(self, mock_load):
        """Test judgement_source is 'manual' when manual_judgement is active."""
        mock_load.return_value = {}

        report = {
            "results": [
                {
                    "name": "API1",
                    "method": "GET",
                    "url": "http://test.com",
                    "manual_judgement": {"active": True, "status": "passed"},
                }
            ],
            "manual_exclusions": [],
        }

        result = build_result_detail_payload(report, 0)

        assert result["judgement_source"] == "manual"

    @patch("postman_api_tester.services.report_results_service.load_report_details_map")
    def test_judgement_source_auto(self, mock_load):
        """Test judgement_source is 'auto' when no manual judgement."""
        mock_load.return_value = {}

        report = {
            "results": [
                {"name": "API1", "method": "GET", "url": "http://test.com"}
            ],
            "manual_exclusions": [],
        }

        result = build_result_detail_payload(report, 0)

        assert result["judgement_source"] == "auto"


class TestBuildManualCasesPayload:
    """Tests for build_manual_cases_payload."""

    @patch("postman_api_tester.services.report_results_service.normalize_manual_exclusions")
    @patch("postman_api_tester.services.report_results_service.normalize_manual_case")
    def test_basic_flow(self, mock_normalize_case, mock_normalize_exclusions):
        """Test basic manual cases payload building."""
        mock_normalize_case.side_effect = lambda c, f: {**c, "normalized": True}
        mock_normalize_exclusions.return_value = ["key1"]

        report = {
            "manual_cases": [{"name": "Case1", "folder": "F1"}],
            "manual_exclusions": ["key1"],
        }

        result = build_manual_cases_payload("Report1", report, "DefaultFolder", True)

        assert result["report_name"] == "Report1"
        assert result["enabled"] is True
        assert result["default_folder"] == "DefaultFolder"
        assert len(result["manual_cases"]) == 1
        assert result["manual_cases"][0]["normalized"] is True

    @patch("postman_api_tester.services.report_results_service.manual_case_exclusion_key")
    @patch("postman_api_tester.services.report_results_service.normalize_manual_exclusions")
    @patch("postman_api_tester.services.report_results_service.normalize_manual_case")
    def test_exclusion_matching(self, mock_normalize_case, mock_normalize_exclusions, mock_exclusion_key):
        """Test exclusion status is correctly matched."""
        mock_normalize_case.side_effect = lambda c, f: {**c, "normalized": True}
        mock_normalize_exclusions.return_value = ["key1", "key2"]
        mock_exclusion_key.return_value = "key1"

        report = {
            "manual_cases": [{"name": "Case1"}],
            "manual_exclusions": ["key1"],
        }

        result = build_manual_cases_payload("R1", report, "F1", True)

        assert result["manual_cases"][0]["excluded"] is True


class TestPayloadBuilders:
    """Tests for simple payload builder functions."""

    def test_build_manual_case_upsert_payload(self):
        """Test manual case upsert payload structure."""
        result = build_manual_case_upsert_payload(
            "Report1", {"case": {"name": "Case1"}, "manual_cases": [{"name": "Case1"}]}
        )

        assert result["report_name"] == "Report1"
        assert result["case"]["name"] == "Case1"
        assert len(result["manual_cases"]) == 1

    def test_build_manual_case_delete_payload(self):
        """Test manual case delete payload structure."""
        result = build_manual_case_delete_payload(
            "Report1", {"manual_cases": []}
        )

        assert result["report_name"] == "Report1"
        assert result["manual_cases"] == []

    def test_build_case_exclusion_payload(self):
        """Test case exclusion payload structure."""
        result = build_case_exclusion_payload(
            "Report1", True, {"manual_exclusions": ["key1"]}
        )

        assert result["report_name"] == "Report1"
        assert result["excluded"] is True
        assert result["manual_exclusions"] == ["key1"]

    def test_build_result_judgement_payload(self):
        """Test result judgement payload structure."""
        result = build_result_judgement_payload(
            "Report1",
            5,
            "mark_passed",
            {"summary": {"passed": 10}, "result": {"status": "passed"}},
        )

        assert result["report_name"] == "Report1"
        assert result["result_index"] == 5
        assert result["action"] == "mark_passed"
        assert result["summary"]["passed"] == 10

    def test_build_export_collection_payload(self):
        """Test export collection payload structure."""
        exported = {
            "file_name": "export.json",
            "updated_count": 5,
            "skipped_count": 2,
            "manual_case_count": 3,
            "manual_case_exported_count": 3,
            "excluded_count": 1,
            "source_total_count": 20,
            "scope_effective_same_as_full": False,
            "export_scope": "full",
            "report_only_count": 15,
            "warnings": [],
        }

        result = build_export_collection_payload("Report1", exported, True)

        assert result["report_name"] == "Report1"
        assert result["file_name"] == "export.json"
        assert result["download_url"] == "/exports/export.json"
        assert result["updated_count"] == 5
        assert result["include_auth"] is True
        assert result["export_scope"] == "full"

    def test_build_report_meta_payload(self):
        """Test report meta payload is a copy of the report."""
        report = {"report_name": "R1", "total": 10}
        result = build_report_meta_payload(report)

        assert result == report
        # Ensure it's a copy, not the same object
        assert result is not report

    def test_build_report_delete_payload(self):
        """Test report delete payload structure."""
        result = build_report_delete_payload("Report1", ["file1.json", "file2.html"])

        assert result["success"] is True
        assert result["report_name"] == "Report1"
        assert len(result["deleted_files"]) == 2

    def test_build_retry_queued_payload(self):
        """Test retry queued payload structure."""
        result = build_retry_queued_payload("job-123", 3, "Retry queued")

        assert result["job_id"] == "job-123"
        assert result["status"] == "queued"
        assert result["retry_count"] == 3
        assert result["message"] == "Retry queued"

    def test_build_health_payload_without_alert(self):
        """Test health payload without log alert."""
        result = build_health_payload("2026-06-26T20:30:00")

        assert result["status"] == "ok"
        assert result["timestamp"] == "2026-06-26T20:30:00"
        assert "log_alert" not in result

    def test_build_health_payload_with_alert(self):
        """Test health payload with log alert."""
        alert = {"level": "warning", "message": "High error rate"}
        result = build_health_payload("2026-06-26T20:30:00", alert)

        assert result["status"] == "ok"
        assert result["log_alert"] == alert

    def test_build_test_token_payload(self):
        """Test test token payload structure."""
        result = build_test_token_payload(True, "Token valid")

        assert result["success"] is True
        assert result["message"] == "Token valid"

    def test_build_environments_payload(self):
        """Test environments payload structure."""
        env_list = [{"name": "dev"}, {"name": "prod"}]
        result = build_environments_payload(env_list, "dev")

        assert result["environments"] == env_list
        assert result["default"] == "dev"

    def test_build_collection_preview_payload(self):
        """Test collection preview payload structure."""
        items = [{"name": "API1"}, {"name": "API2"}]
        result = build_collection_preview_payload("collection.json", 10, False, 5, items)

        assert result["file_name"] == "collection.json"
        assert result["total"] == 10
        assert result["truncated"] is False
        assert result["max_items"] == 5
        assert len(result["items"]) == 2

    def test_build_job_queued_payload(self):
        """Test job queued payload structure."""
        result = build_job_queued_payload("job-456", "Job queued successfully")

        assert result["job_id"] == "job-456"
        assert result["status"] == "queued"
        assert result["message"] == "Job queued successfully"

    def test_build_re_request_success_payload(self):
        """Test re-request success payload structure."""
        source = {"name": "API1", "folder": "Folder1"}
        result_fields = {"status": "passed", "status_code": 200}
        request_info = {"headers": {}, "params": {}, "body": None}
        response_info = {"headers": {}, "body": "ok"}
        new_summary = {"passed": 1}

        result = build_re_request_success_payload(
            source,
            "GET",
            "http://test.com",
            "http://test.com",
            result_fields,
            request_info,
            response_info,
            new_summary,
        )

        assert result["name"] == "API1"
        assert result["folder"] == "Folder1"
        assert result["method"] == "GET"
        assert result["status"] == "passed"
        assert result["saved"] is True

    def test_build_proxy_response_payload(self):
        """Test proxy response payload structure."""
        result = build_proxy_response_payload(
            200, 150, {"Content-Type": "application/json"}, {"data": "test"}
        )

        assert result["status_code"] == 200
        assert result["elapsed_ms"] == 150
        assert result["response_headers"]["Content-Type"] == "application/json"
        assert result["response_body"]["data"] == "test"

    def test_build_re_request_error_payload(self):
        """Test re-request error payload structure."""
        source = {"name": "API1", "folder": "Folder1"}

        result = build_re_request_error_payload(
            source,
            "http://test.com",
            "POST",
            "http://test.com",
            "http://test.com",
            "Connection timeout",
            {"Authorization": "Bearer token"},
            {"param1": "value1"},
            {"key": "value"},
            "raw",
            None,
        )

        assert result["name"] == "API1"
        assert result["status"] == "ERROR"
        assert result["status_code"] is None
        assert result["message"] == "Connection timeout"
        assert result["request_info"]["headers"]["Authorization"] == "Bearer token"
        assert result["saved"] is False

    def test_build_error_payload(self):
        """Test error payload structure."""
        result = build_error_payload("Something went wrong")

        assert result["error"] == "Something went wrong"
