"""job_routes 单元测试。"""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.job_routes import (
    api_run_ad_hoc_tests,
    api_run_postman,
    api_run_postman_status,
    clamp_run_results_per_page,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 请求上下文。"""
    app = Flask(__name__)
    with app.test_request_context():
        yield


class TestClampRunResultsPerPage:
    """分页大小钳制测试。"""

    def test_default(self) -> None:
        """默认值返回配置默认值。"""
        result = clamp_run_results_per_page(None)
        assert result >= 1

    def test_valid(self) -> None:
        """有效值直接返回。"""
        assert clamp_run_results_per_page(50) == 50

    def test_below_min(self) -> None:
        """低于最小值返回最小值。"""
        assert clamp_run_results_per_page(0) == 1

    def test_invalid(self) -> None:
        """非数字返回默认值。"""
        assert clamp_run_results_per_page("abc") >= 1


class TestApiRunPostman:
    """run-postman 端点测试。"""

    def test_no_file(self, app_context: None) -> None:
        """未上传文件返回 400。"""
        with patch(
            "postman_api_tester.handlers.job_routes.request"
        ) as mock_request:
            mock_request.files = MagicMock()
            mock_request.files.get.return_value = None
            result = api_run_postman()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_non_json_file(self, app_context: None) -> None:
        """非 JSON 文件返回 400。"""
        with patch(
            "postman_api_tester.handlers.job_routes.request"
        ) as mock_request:
            mock_request.files = MagicMock()
            mock_file = MagicMock()
            mock_file.filename = "test.txt"
            mock_request.files.get.return_value = mock_file
            result = api_run_postman()
            assert isinstance(result, tuple)
            assert result[1] == 400


class TestApiRunAdHocTests:
    """run-ad-hoc-tests 端点测试。"""

    def test_disabled(self, app_context: None) -> None:
        """禁用时返回 403。"""
        with patch(
            "postman_api_tester.handlers.job_routes.ENABLE_ADHOC_RUN", False
        ):
            result = api_run_ad_hoc_tests()
            assert isinstance(result, tuple)
            assert result[1] == 403

    def test_empty_cases(self, app_context: None) -> None:
        """空 cases 返回 400。"""
        with patch(
            "postman_api_tester.handlers.job_routes.ENABLE_ADHOC_RUN", True
        ), patch(
            "postman_api_tester.handlers.job_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"cases": []})
            result = api_run_ad_hoc_tests()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_cases_not_list(self, app_context: None) -> None:
        """cases 非数组返回 400。"""
        with patch(
            "postman_api_tester.handlers.job_routes.ENABLE_ADHOC_RUN", True
        ), patch(
            "postman_api_tester.handlers.job_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"cases": "not_list"})
            result = api_run_ad_hoc_tests()
            assert isinstance(result, tuple)
            assert result[1] == 400


class TestApiRunPostmanStatus:
    """run-postman-status 端点测试。"""

    def test_job_not_found(self, app_context: None) -> None:
        """任务不存在返回 404。"""
        with patch(
            "postman_api_tester.handlers.job_routes.get_run_job"
        ) as mock_get:
            mock_get.return_value = None
            result = api_run_postman_status("nonexistent_job")
            assert isinstance(result, tuple)
            assert result[1] == 404

    def test_job_found(self, app_context: None) -> None:
        """任务存在返回任务状态。"""
        with patch(
            "postman_api_tester.handlers.job_routes.get_run_job"
        ) as mock_get:
            mock_get.return_value = {"status": "running"}
            result = api_run_postman_status("existing_job")
            from flask import Response
            assert isinstance(result, Response)
