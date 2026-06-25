"""report_meta_routes 单元测试。"""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.report_meta_routes import (
    api_manual_case_add,
    api_manual_case_delete,
    api_manual_cases,
    api_report_case_exclusion,
    api_report_detail,
    api_report_result_judgement,
    api_reports,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 请求上下文。"""
    app = Flask(__name__)
    with app.test_request_context():
        yield


class TestApiReports:
    """api_reports 端点测试。"""

    def test_api_reports(self, app_context: None) -> None:
        """返回报告列表。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes._repo_list_reports"
        ) as mock_list:
            mock_list.return_value = [{"report_name": "test"}]
            result = api_reports()
            from flask import Response
            assert isinstance(result, Response)


class TestApiReportDetail:
    """api_report_detail 端点测试。"""

    def test_report_not_found(self, app_context: None) -> None:
        """报告不存在返回 404。"""
        with patch(
            "postman_api_tester.report_repository.find_report"
        ) as mock_find:
            mock_find.side_effect = FileNotFoundError()
            result = api_report_detail("missing")
            assert isinstance(result, tuple)
            assert result[1] == 404


class TestApiManualCases:
    """api_manual_cases 端点测试。"""

    def test_report_not_found(self, app_context: None) -> None:
        """报告不存在返回 404。"""
        with patch(
            "postman_api_tester.report_repository.find_report"
        ) as mock_find:
            mock_find.side_effect = FileNotFoundError()
            result = api_manual_cases("missing")
            assert isinstance(result, tuple)
            assert result[1] == 404


class TestApiManualCaseAdd:
    """api_manual_case_add 端点测试。"""

    def test_missing_report_name(self, app_context: None) -> None:
        """缺少 report_name 返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={})
            result = api_manual_case_add()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_report_name_too_long(self, app_context: None) -> None:
        """report_name 超长返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            long_name = "x" * 300
            mock_request.get_json = MagicMock(return_value={"report_name": long_name, "case": {}})
            result = api_manual_case_add()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_missing_case(self, app_context: None) -> None:
        """缺少 case 返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"report_name": "test"})
            result = api_manual_case_add()
            assert isinstance(result, tuple)
            assert result[1] == 400


class TestApiManualCaseDelete:
    """api_manual_case_delete 端点测试。"""

    def test_missing_report_name(self, app_context: None) -> None:
        """缺少 report_name 返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={})
            result = api_manual_case_delete()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_report_name_too_long(self, app_context: None) -> None:
        """report_name 超长返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            long_name = "x" * 300
            mock_request.get_json = MagicMock(return_value={"report_name": long_name, "case_id": "c1"})
            result = api_manual_case_delete()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_case_id_too_long(self, app_context: None) -> None:
        """case_id 超长返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            long_id = "x" * 150
            mock_request.get_json = MagicMock(return_value={"report_name": "test", "case_id": long_id})
            result = api_manual_case_delete()
            assert isinstance(result, tuple)
            assert result[1] == 400


class TestApiReportCaseExclusion:
    """api_report_case_exclusion 端点测试。"""

    def test_missing_report_name(self, app_context: None) -> None:
        """缺少 report_name 返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={})
            result = api_report_case_exclusion()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_report_name_too_long(self, app_context: None) -> None:
        """report_name 超长返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            long_name = "x" * 300
            mock_request.get_json = MagicMock(return_value={"report_name": long_name, "exclusion_key": "key"})
            result = api_report_case_exclusion()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_exclusion_key_too_long(self, app_context: None) -> None:
        """exclusion_key 超长返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            long_key = "x" * 600
            mock_request.get_json = MagicMock(return_value={"report_name": "test", "exclusion_key": long_key})
            result = api_report_case_exclusion()
            assert isinstance(result, tuple)
            assert result[1] == 400


class TestApiReportResultJudgement:
    """api_report_result_judgement 端点测试。"""

    def test_missing_report_name(self, app_context: None) -> None:
        """缺少 report_name 返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={})
            result = api_report_result_judgement()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_missing_result_index(self, app_context: None) -> None:
        """缺少 result_index 返回 400。"""
        with patch(
            "postman_api_tester.handlers.report_meta_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"report_name": "test"})
            result = api_report_result_judgement()
            assert isinstance(result, tuple)
            assert result[1] == 400
