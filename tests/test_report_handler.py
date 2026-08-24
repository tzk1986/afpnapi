"""Tests for postman_api_tester.handlers.report_handler.

仅覆盖 normalize_status_filter（唯一保留的函数）。
其他报告展示函数已统一至 models.py，测试见 test_models.py。
"""

from __future__ import annotations

from postman_api_tester.handlers.report_handler import normalize_status_filter


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
