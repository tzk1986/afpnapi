"""Tests for postman_api_tester.report_meta_repository module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from postman_api_tester.report_meta_repository import (
    configure_reports_dir,
    configure_scan_excludes,
    _is_excluded,
    is_total_report_file,
    report_meta_files,
    _extract_json_value,
    _load_report_meta_summary,
    load_report_meta,
    legacy_postman_html_files,
    load_legacy_postman_report,
    _REPORTS_DIR,
    _EXCLUDE_DIRS,
)


class TestConfigureReportsDir:
    """Tests for configure_reports_dir."""

    def test_configure_reports_dir(self, tmp_path):
        """Test configuring reports directory."""
        original_dir = _REPORTS_DIR
        try:
            configure_reports_dir(tmp_path)
            from postman_api_tester.report_meta_repository import _REPORTS_DIR as new_dir
            assert new_dir == tmp_path.resolve()
        finally:
            configure_reports_dir(original_dir)


class TestConfigureScanExcludes:
    """Tests for configure_scan_excludes."""

    def test_configure_scan_excludes(self):
        """Test configuring excluded directories."""
        original_excludes = _EXCLUDE_DIRS.copy()
        try:
            configure_scan_excludes(["node_modules", ".git", ""])
            from postman_api_tester.report_meta_repository import _EXCLUDE_DIRS as new_excludes
            assert "node_modules" in new_excludes
            assert ".git" in new_excludes
            assert "" not in new_excludes
        finally:
            configure_scan_excludes(list(original_excludes))


class TestIsExcluded:
    """Tests for _is_excluded."""

    def test_path_outside_reports_dir(self, tmp_path):
        """Test path outside reports dir is excluded."""
        configure_reports_dir(tmp_path / "reports")
        path = tmp_path / "other" / "file.json"
        assert _is_excluded(path) is True

    def test_path_in_excluded_dir(self, tmp_path):
        """Test path in excluded directory."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        configure_reports_dir(reports_dir)
        configure_scan_excludes(["node_modules"])

        path = reports_dir / "node_modules" / "package" / "file.json"
        assert _is_excluded(path) is True

    def test_path_not_excluded(self, tmp_path):
        """Test path not in excluded directory."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        configure_reports_dir(reports_dir)
        configure_scan_excludes(["node_modules"])

        path = reports_dir / "valid" / "file.json"
        assert _is_excluded(path) is False


class TestIsTotalReportFile:
    """Tests for is_total_report_file."""

    def test_total_report_file(self):
        """Test total report file detection."""
        path = Path("report_meta.json")
        assert is_total_report_file(path) is True

    def test_page_report_file(self):
        """Test page report file is not total."""
        path = Path("report_page_1_meta.json")
        assert is_total_report_file(path) is False

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        path = Path("REPORT_META.JSON")
        assert is_total_report_file(path) is True


class TestReportMetaFiles:
    """Tests for report_meta_files."""

    def test_reports_dir_not_exists(self, tmp_path):
        """Test when reports dir doesn't exist."""
        configure_reports_dir(tmp_path / "nonexistent")
        result = report_meta_files()
        assert result == []

    def test_finds_meta_files(self, tmp_path):
        """Test finding meta files."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        configure_reports_dir(reports_dir)
        configure_scan_excludes([])

        # Create meta files
        (reports_dir / "report1_meta.json").write_text("{}")
        (reports_dir / "report2_meta.json").write_text("{}")

        result = report_meta_files()
        assert len(result) == 2

    def test_excludes_page_files(self, tmp_path):
        """Test page files are excluded."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        configure_reports_dir(reports_dir)
        configure_scan_excludes([])

        (reports_dir / "report_meta.json").write_text("{}")
        (reports_dir / "report_page_1_meta.json").write_text("{}")

        result = report_meta_files()
        assert len(result) == 1
        assert "_page_" not in result[0].name


class TestExtractJsonValue:
    """Tests for _extract_json_value."""

    def test_extract_string(self):
        """Test extracting string value."""
        result = _extract_json_value('"hello",')
        assert result == "hello"

    def test_extract_number(self):
        """Test extracting number value."""
        result = _extract_json_value("42")
        assert result == 42

    def test_extract_boolean(self):
        """Test extracting boolean value."""
        result = _extract_json_value("true,")
        assert result is True

    def test_extract_null(self):
        """Test extracting null value."""
        result = _extract_json_value("null")
        assert result is None

    def test_strip_whitespace(self):
        """Test whitespace is stripped."""
        result = _extract_json_value('  "value"  ')
        assert result == "value"


class TestLoadReportMetaSummary:
    """Tests for _load_report_meta_summary."""

    def test_load_basic_meta(self, tmp_path):
        """Test loading basic meta file."""
        meta_file = tmp_path / "report_meta.json"
        # _load_report_meta_summary parses line-by-line, so format with newlines
        meta_text = """{
  "report_name": "report.html",
  "generated_at": "2026-06-28 10:00:00",
  "summary": {
    "total": 10,
    "passed": 8,
    "failed": 1,
    "error": 1,
    "success_rate": "80%"
  },
  "results": []
}"""
        meta_file.write_text(meta_text)

        result = _load_report_meta_summary(meta_file)

        assert result["report_name"] == "report.html"
        assert result["generated_at"] == "2026-06-28 10:00:00"
        assert result["summary"]["total"] == 10
        assert result["_summary_only"] is True

    def test_empty_summary_fallback(self, tmp_path):
        """Test empty summary gets default values."""
        meta_file = tmp_path / "report_meta.json"
        meta_data = {"report_name": "report.html", "results": []}
        meta_file.write_text(json.dumps(meta_data))

        result = _load_report_meta_summary(meta_file)

        assert result["summary"]["total"] == 0
        assert result["summary"]["success_rate"] == "0%"


class TestLoadReportMeta:
    """Tests for load_report_meta."""

    def test_load_full_meta(self, tmp_path):
        """Test loading full meta with results."""
        meta_file = tmp_path / "report_meta.json"
        meta_data = {
            "report_name": "report.html",
            "summary": {"total": 5},
            "results": [{"name": "API1"}],
        }
        meta_file.write_text(json.dumps(meta_data))

        result = load_report_meta(meta_file, include_results=True)

        assert result["_summary_only"] is False
        assert len(result["results"]) == 1

    def test_load_summary_only(self, tmp_path):
        """Test loading summary only."""
        meta_file = tmp_path / "report_meta.json"
        meta_data = {
            "report_name": "report.html",
            "summary": {"total": 5},
            "results": [{"name": "API1"}, {"name": "API2"}],
        }
        meta_file.write_text(json.dumps(meta_data))

        result = load_report_meta(meta_file, include_results=False)

        assert result["_summary_only"] is True
        assert "results" not in result or result.get("results") == []


class TestLegacyPostmanHtmlFiles:
    """Tests for legacy_postman_html_files."""

    def test_reports_dir_not_exists(self, tmp_path):
        """Test when reports dir doesn't exist."""
        configure_reports_dir(tmp_path / "nonexistent")
        result = legacy_postman_html_files()
        assert result == []


class TestLoadLegacyPostmanReport:
    """Tests for load_legacy_postman_report."""

    def test_load_legacy_report(self, tmp_path):
        """Test loading legacy HTML report."""
        configure_reports_dir(tmp_path)

        html_file = tmp_path / "report.html"
        html_content = """<html>
<label>总计</label><span>10</span>
<label> 通过</label><span>8</span>
<label> 失败</label><span>1</span>
<label>! 错误</label><span>1</span>
<label>成功率</label><span>80%</span>
<label>耗时</label><span>5.2s</span>
开始: 2026-06-28 10:00:00 | 结束: 2026-06-28 10:00:05
<script>let allResults = [{"name": "API1", "folder": "F1", "method": "GET", "url": "http://test.com", "status": "PASSED", "status_code": 200, "message": "OK", "err_code": ""}];</script>
</html>"""
        html_file.write_text(html_content, encoding="utf-8")

        result = load_legacy_postman_report(html_file)

        assert result["report_name"] == "report.html"
        assert result["summary"]["total"] == 10
        assert result["summary"]["passed"] == 8
        assert result["summary"]["success_rate"] == "80%"
        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "API1"
        assert result["legacy"] is True
