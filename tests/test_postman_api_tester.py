"""postman_api_tester.py CLI 入口测试."""

import pytest
from postman_api_tester.postman_api_tester import (
    run_postman_tests,
    PostmanTestReport,
)


class TestPostmanTestReport:
    """PostmanTestReport 基础测试."""

    def test_report_initialization(self) -> None:
        """测试报告对象初始化."""
        report = PostmanTestReport()
        assert report.results == []
        assert report.collection_name == ""
        assert report.base_url == ""


class TestRunPostmanTestsApi:
    """run_postman_tests 公共 API 签名测试."""

    def test_run_postman_tests_signature(self) -> None:
        """测试 run_postman_tests 可被正确导入和调用（参数验证路径）."""
        import inspect

        sig = inspect.signature(run_postman_tests)
        params = list(sig.parameters.keys())
        assert "postman_file" in params
        assert "base_url" in params
        assert "output_dir" in params
        assert "token" in params
        assert "report_name" in params
