"""retry_routes 单元测试。"""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.retry_routes import (
    api_retry_all,
    api_retry_failures,
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

    def test_above_max(self) -> None:
        """超过最大值返回最大值。"""
        assert clamp_run_results_per_page(999) == 100

    def test_invalid(self) -> None:
        """非数字返回默认值。"""
        assert clamp_run_results_per_page("abc") >= 1


class TestApiRetryFailures:
    """重试失败用例端点测试。"""

    def test_retry_disabled(self, app_context: None) -> None:
        """禁用时返回 403。"""
        with patch(
            "postman_api_tester.handlers.retry_routes.ENABLE_RETRY_FAILURES", False
        ):
            result = api_retry_failures()
            assert isinstance(result, tuple)
            assert result[1] == 403

    def test_missing_report_name(self, app_context: None) -> None:
        """缺少 report_name 返回 400。"""
        with patch(
            "postman_api_tester.handlers.retry_routes.ENABLE_RETRY_FAILURES", True
        ), patch(
            "postman_api_tester.handlers.retry_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"report_name": "  "})
            result = api_retry_failures()
            assert isinstance(result, tuple)
            assert result[1] == 400


class TestApiRetryAll:
    """全量重试端点测试。"""

    def test_retry_all_disabled(self, app_context: None) -> None:
        """禁用时返回 403。"""
        with patch(
            "postman_api_tester.handlers.retry_routes.ENABLE_RETRY_FAILURES", False
        ):
            result = api_retry_all()
            assert isinstance(result, tuple)
            assert result[1] == 403

    def test_missing_report_name(self, app_context: None) -> None:
        """缺少 report_name 返回 400。"""
        with patch(
            "postman_api_tester.handlers.retry_routes.ENABLE_RETRY_FAILURES", True
        ), patch(
            "postman_api_tester.handlers.retry_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"report_name": "  "})
            result = api_retry_all()
            assert isinstance(result, tuple)
            assert result[1] == 400
