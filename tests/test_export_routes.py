"""export_routes 单元测试。"""

from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask

from postman_api_tester.handlers.export_routes import api_export_junit


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 应用上下文。"""
    app = Flask(__name__)
    with app.test_request_context():
        yield


class TestApiExportJUnit:
    """JUnit XML 导出端点测试。"""

    def test_export_junit_disabled(self, app_context: None) -> None:
        """禁用时返回 403。"""
        with patch(
            "postman_api_tester.handlers.export_routes.ENABLE_JUNIT_EXPORT", False
        ):
            result = api_export_junit("test_report")
            assert isinstance(result, tuple)
            assert result[1] == 403

    def test_export_junit_report_not_found(self, app_context: None) -> None:
        """报告不存在返回 404。"""
        with patch(
            "postman_api_tester.handlers.export_routes.ENABLE_JUNIT_EXPORT", True
        ), patch(
            "postman_api_tester.report_repository.find_report"
        ) as mock_find:
            mock_find.side_effect = FileNotFoundError()
            result = api_export_junit("missing_report")
            assert isinstance(result, tuple)
            assert result[1] == 404

    def test_export_junit_success(self, app_context: None) -> None:
        """成功导出返回 XML 响应。"""
        with patch(
            "postman_api_tester.handlers.export_routes.ENABLE_JUNIT_EXPORT", True
        ), patch(
            "postman_api_tester.report_repository.find_report"
        ) as mock_find, patch(
            "postman_api_tester.handlers.export_routes._svc_build_junit_xml"
        ) as mock_build:
            mock_find.return_value = {"report_name": "test_report"}
            mock_build.return_value = '<testsuite name="test"></testsuite>'
            result = api_export_junit("test_report")
            from flask import Response
            assert isinstance(result, Response)
            assert result.content_type == "application/xml; charset=utf-8"
