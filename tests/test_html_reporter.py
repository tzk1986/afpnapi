"""Tests for HtmlReporter class in core/html_reporter.py."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.core.html_reporter import HtmlReporter


def _make_mock_report(
    results: List[Dict[str, Any]],
    collection_name: str = "test_collection",
    source_file: str = "test.json",
    base_url: str = "https://api.example.com",
) -> MagicMock:
    """Create a mock report object with given results."""
    report = MagicMock()
    report.results = results
    report.collection_name = collection_name
    report.source_file = source_file
    report.source_original_file = source_file
    report.base_url = base_url
    report.execution_mode = "sequential"
    report.interrupted = False
    report.interrupt_reason = ""
    report.assertion_strict_mode = False
    report.generate_summary.return_value = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("status") == "PASSED"),
        "failed": sum(1 for r in results if r.get("status") == "FAILED"),
        "error": sum(1 for r in results if r.get("status") == "ERROR"),
        "success_rate": f"{sum(1 for r in results if r.get('status') == 'PASSED') / max(len(results), 1) * 100:.1f}%",
        "duration": "1.5s",
        "start_time": "2026-06-25 10:00:00",
        "end_time": "2026-06-25 10:00:01",
    }
    return report


def _make_result(
    name: str = "test_api",
    folder: str = "folder1",
    method: str = "GET",
    url: str = "https://api.example.com/test",
    status: str = "PASSED",
    status_code: int = 200,
    message: str = "OK",
    err_code: str = "0",
) -> Dict[str, Any]:
    """Create a single test result dict."""
    return {
        "name": name,
        "folder": folder,
        "method": method,
        "url": url,
        "status": status,
        "status_code": status_code,
        "message": message,
        "err_code": err_code,
        "response_time_ms": 100,
        "item_path": [0, 1],
        "expected_status": 200,
        "actual_request_url": url,
        "request_info": {
            "headers": {"Authorization": "Bearer secret", "Content-Type": "application/json"},
            "params": {"key": "value"},
            "body": {"data": "test"},
        },
        "response_info": {
            "headers": {"Content-Type": "application/json"},
            "body": {"result": "success"},
        },
    }


class TestBuildDetailsData:
    """Tests for _build_details_data static method."""

    def test_empty_results(self) -> None:
        report = _make_mock_report([])
        details = HtmlReporter._build_details_data(report)
        assert details == {}

    def test_single_result_headers_sanitized(self) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        details = HtmlReporter._build_details_data(report)

        assert "0" in details
        req_headers = details["0"]["request_info"]["headers"]
        assert req_headers.get("Authorization") == "***"
        assert req_headers.get("Content-Type") == "application/json"

    def test_multiple_results_indexed_by_string(self) -> None:
        results = [_make_result(name=f"api_{i}") for i in range(3)]
        report = _make_mock_report(results)
        details = HtmlReporter._build_details_data(report)

        assert set(details.keys()) == {"0", "1", "2"}

    def test_response_info_preserved(self) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        details = HtmlReporter._build_details_data(report)

        resp_info = details["0"]["response_info"]
        assert resp_info["headers"]["Content-Type"] == "application/json"
        assert resp_info["body"]["result"] == "success"

    def test_missing_request_info(self) -> None:
        result = _make_result()
        del result["request_info"]
        report = _make_mock_report([result])
        details = HtmlReporter._build_details_data(report)

        assert details["0"]["request_info"]["headers"] == {}

    def test_none_headers_treated_as_empty(self) -> None:
        result = _make_result()
        result["request_info"]["headers"] = None
        report = _make_mock_report([result])
        details = HtmlReporter._build_details_data(report)

        assert details["0"]["request_info"]["headers"] == {}


class TestBuildIndexResultsData:
    """Tests for _build_index_results_data static method."""

    def test_empty_results(self) -> None:
        report = _make_mock_report([])
        data = HtmlReporter._build_index_results_data(report)
        assert data == []

    def test_result_fields_preserved(self) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        data = HtmlReporter._build_index_results_data(report)

        assert len(data) == 1
        assert data[0]["name"] == "test_api"
        assert data[0]["folder"] == "folder1"
        assert data[0]["method"] == "GET"
        assert data[0]["status"] == "PASSED"
        assert data[0]["status_code"] == 200

    def test_missing_fields_default_empty(self) -> None:
        result: Dict[str, Any] = {"name": "api", "status": "PASSED"}
        report = _make_mock_report([result])
        data = HtmlReporter._build_index_results_data(report)

        assert data[0]["folder"] == ""
        assert data[0]["method"] == ""
        assert data[0]["url"] == ""


class TestNormalizeIndexPageSize:
    """Tests for _normalize_index_page_size static method."""

    @pytest.mark.parametrize("size", [20, 30, 50, 100, 200])
    def test_valid_page_sizes_preserved(self, size: int) -> None:
        report = _make_mock_report([])
        assert HtmlReporter._normalize_index_page_size(report, size) == size

    @pytest.mark.parametrize("size", [1, 10, 25, 99, 300, 0, -1])
    def test_invalid_page_sizes_default_to_20(self, size: int) -> None:
        report = _make_mock_report([])
        assert HtmlReporter._normalize_index_page_size(report, size) == 20


class TestRenderPageSizeOptions:
    """Tests for _render_page_size_options static method."""

    def test_selected_option_has_selected_attribute(self) -> None:
        report = _make_mock_report([])
        html = HtmlReporter._render_page_size_options(report, 30)
        assert 'selected' in html
        assert '<option value="30" selected>' in html

    def test_non_selected_options_no_selected_attribute(self) -> None:
        report = _make_mock_report([])
        html = HtmlReporter._render_page_size_options(report, 30)
        assert '<option value="20">' in html
        assert '<option value="20" selected>' not in html

    def test_all_five_options_present(self) -> None:
        report = _make_mock_report([])
        html = HtmlReporter._render_page_size_options(report, 20)
        for value in [20, 30, 50, 100, 200]:
            assert f'value="{value}"' in html


class TestGetPageWindow:
    """Tests for _get_page_window static method."""

    def test_first_page(self) -> None:
        results = [_make_result(name=f"api_{i}") for i in range(10)]
        report = _make_mock_report(results)
        start, end, page_results = HtmlReporter._get_page_window(report, 1, 3)

        assert start == 0
        assert end == 3
        assert len(page_results) == 3

    def test_last_page_partial(self) -> None:
        results = [_make_result(name=f"api_{i}") for i in range(10)]
        report = _make_mock_report(results)
        start, end, page_results = HtmlReporter._get_page_window(report, 4, 3)

        assert start == 9
        assert end == 10
        assert len(page_results) == 1

    def test_empty_results(self) -> None:
        report = _make_mock_report([])
        start, end, page_results = HtmlReporter._get_page_window(report, 1, 30)

        assert start == 0
        assert end == 0
        assert len(page_results) == 0


class TestBuildPageTableRows:
    """Tests for _build_page_table_rows static method."""

    def test_empty_page_results(self) -> None:
        report = _make_mock_report([])
        html = HtmlReporter._build_page_table_rows(report, [], 0)
        assert html.strip() == ""

    def test_result_row_contains_name(self) -> None:
        result = _make_result(name="my_special_api")
        report = _make_mock_report([result])
        html = HtmlReporter._build_page_table_rows(report, [result], 0)
        assert "my_special_api" in html

    def test_status_class_applied(self) -> None:
        result = _make_result(status="FAILED")
        report = _make_mock_report([result])
        html = HtmlReporter._build_page_table_rows(report, [result], 0)
        assert "status-failed" in html

    def test_html_escape_special_chars(self) -> None:
        result = _make_result(name="<script>alert('xss')</script>")
        report = _make_mock_report([result])
        html = HtmlReporter._build_page_table_rows(report, [result], 0)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_detail_id_uses_global_index(self) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        html = HtmlReporter._build_page_table_rows(report, [result], 5)
        assert 'id="detail-5"' in html


class TestBuildReportMetadata:
    """Tests for _build_report_metadata static method."""

    def test_metadata_structure(self) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        summary = report.generate_summary()
        meta = HtmlReporter._build_report_metadata(
            report, summary, "/tmp/report.html", "/tmp/report_details.json"
        )

        assert meta["report_name"] == "report.html"
        assert meta["collection_name"] == "test_collection"
        assert meta["details_file"] == "report_details.json"
        assert len(meta["results"]) == 1

    def test_result_key_uses_pipe_separator(self) -> None:
        result = _make_result(folder="f1", name="api1", method="GET", url="http://x.com")
        report = _make_mock_report([result])
        summary = report.generate_summary()
        meta = HtmlReporter._build_report_metadata(
            report, summary, "/tmp/r.html", "/tmp/r_details.json"
        )

        assert "f1 | api1 | GET | http://x.com" in meta["results"][0]["key"]

    def test_interrupted_flag_preserved(self) -> None:
        report = _make_mock_report([])
        report.interrupted = True
        report.interrupt_reason = "timeout"
        summary = report.generate_summary()
        meta = HtmlReporter._build_report_metadata(
            report, summary, "/tmp/r.html", "/tmp/r_details.json"
        )

        assert meta["interrupted"] is True
        assert meta["interrupt_reason"] == "timeout"


class TestGenerateHtmlReport:
    """Tests for generate_html_report static method."""

    def test_generates_three_files(self, tmp_path: Path) -> None:
        results = [_make_result() for _ in range(3)]
        report = _make_mock_report(results)
        output_path = str(tmp_path / "report.html")

        with patch.object(HtmlReporter, '_generate_index_html', return_value="<html></html>"):
            with patch.object(HtmlReporter, '_generate_page_html', return_value="<html></html>"):
                HtmlReporter.generate_html_report(report, output_path, results_per_page=30)

        assert (tmp_path / "report.html").exists()
        assert (tmp_path / "report_details.json").exists()
        assert (tmp_path / "report_meta.json").exists()

    def test_details_json_contains_sanitized_headers(self, tmp_path: Path) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        output_path = str(tmp_path / "report.html")

        with patch.object(HtmlReporter, '_generate_index_html', return_value="<html></html>"):
            with patch.object(HtmlReporter, '_generate_page_html', return_value="<html></html>"):
                HtmlReporter.generate_html_report(report, output_path, results_per_page=30)

        details_file = tmp_path / "report_details.json"
        with open(details_file, "r", encoding="utf-8") as f:
            details = json.load(f)

        assert details["0"]["request_info"]["headers"]["Authorization"] == "***"

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        result = _make_result()
        report = _make_mock_report([result])
        output_dir = tmp_path / "subdir" / "nested"
        output_path = str(output_dir / "report.html")

        with patch.object(HtmlReporter, '_generate_index_html', return_value="<html></html>"):
            with patch.object(HtmlReporter, '_generate_page_html', return_value="<html></html>"):
                HtmlReporter.generate_html_report(report, output_path, results_per_page=30)

        assert output_dir.exists()

    def test_pagination_calculated_correctly(self, tmp_path: Path) -> None:
        results = [_make_result(name=f"api_{i}") for i in range(50)]
        report = _make_mock_report(results)
        output_path = str(tmp_path / "report.html")

        with patch.object(HtmlReporter, '_generate_index_html', return_value="<html></html>") as mock_idx:
            with patch.object(HtmlReporter, '_generate_page_html', return_value="<html></html>") as mock_page:
                HtmlReporter.generate_html_report(report, output_path, results_per_page=20)

                assert mock_page.call_count == 3
