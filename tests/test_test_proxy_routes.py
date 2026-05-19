"""test_proxy_routes 单元测试。"""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.test_proxy_routes import test_token as _test_token_handler


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 请求上下文。"""
    app = Flask(__name__)
    with app.test_request_context():
        yield


class TestTestToken:
    """test-token 端点测试。"""

    def test_test_token_empty(self, app_context: None) -> None:
        """空 token 返回 400。"""
        with patch(
            "postman_api_tester.handlers.test_proxy_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"token": "  "})
            result = _test_token_handler()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_test_token_valid(self, app_context: None) -> None:
        """有效 token 返回 200。"""
        with patch(
            "postman_api_tester.handlers.test_proxy_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={"token": "abc123"})
            result = _test_token_handler()
            from flask import Response
            assert isinstance(result, Response)
            assert result.status_code == 200

    def test_test_token_missing(self, app_context: None) -> None:
        """缺少 token 返回 400。"""
        with patch(
            "postman_api_tester.handlers.test_proxy_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value={})
            result = _test_token_handler()
            assert isinstance(result, tuple)
            assert result[1] == 400

    def test_test_token_none(self, app_context: None) -> None:
        """None token 返回 400。"""
        with patch(
            "postman_api_tester.handlers.test_proxy_routes.request"
        ) as mock_request:
            mock_request.get_json = MagicMock(return_value=None)
            result = _test_token_handler()
            assert isinstance(result, tuple)
            assert result[1] == 400
