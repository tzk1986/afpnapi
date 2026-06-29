"""test_proxy_routes 单元测试。"""

from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.test_proxy_routes import (
    test_token as _test_token_handler,
    _build_request_response_info,
    _evaluate_and_build_result,
    _check_proxy_host_allowed,
    re_request_api,
    api_proxy_request,
)


@pytest.fixture
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


class TestBuildRequestResponseInfo:
    """_build_request_response_info 辅助函数测试。"""

    def test_builds_correct_structure(self) -> None:
        """测试构建正确的请求和响应信息结构。"""
        exec_result: Dict[str, Any] = {
            "headers_to_send": {"Content-Type": "application/json"},
            "normalized_params": {"key": "value"},
            "stored_body": {"data": "test"},
            "stored_body_mode": "raw",
            "stored_body_data": {"raw": "test"},
            "response_headers": {"X-Custom": "header"},
            "response_body": {"result": "success"},
        }

        request_info, response_info = _build_request_response_info(exec_result)

        assert request_info["headers"] == {"Content-Type": "application/json"}
        assert request_info["params"] == {"key": "value"}
        assert request_info["body"] == {"data": "test"}
        assert request_info["body_mode"] == "raw"
        assert response_info["headers"] == {"X-Custom": "header"}
        assert response_info["body"] == {"result": "success"}

    def test_handles_empty_data(self) -> None:
        """测试处理空数据。"""
        exec_result: Dict[str, Any] = {
            "headers_to_send": {},
            "normalized_params": {},
            "stored_body": None,
            "stored_body_mode": "none",
            "stored_body_data": None,
            "response_headers": {},
            "response_body": "",
        }

        request_info, response_info = _build_request_response_info(exec_result)

        assert request_info["headers"] == {}
        assert request_info["body"] is None
        assert response_info["body"] == ""


class TestEvaluateAndBuildResult:
    """_evaluate_and_build_result 辅助函数测试。"""

    @patch("postman_api_tester.handlers.test_proxy_routes._evaluate_result_judgment")
    @patch("postman_api_tester.handlers.test_proxy_routes._resolve_judgment_params_for_proxy")
    @patch("postman_api_tester.handlers.test_proxy_routes._utils_extract_msg_errcode")
    def test_passed_judgment(
        self,
        mock_extract: MagicMock,
        mock_resolve: MagicMock,
        mock_evaluate: MagicMock,
    ) -> None:
        """测试判定通过场景。"""
        mock_extract.return_value = ("Success", "")
        mock_resolve.return_value = {
            "success_err_codes": None,
            "success_messages": None,
            "enable_err_code_judgment": False,
            "enable_message_judgment": False,
        }
        mock_evaluate.return_value = (True, "")

        exec_result = {
            "response_body": {"message": "Success"},
            "status_code": 200,
            "normalized_url": "http://example.com/api",
            "actual_request_url": "http://example.com/api?key=value",
        }
        source = {"item_path": [0, 1]}

        status, message, err_code, result_fields = _evaluate_and_build_result(
            exec_result, source, "GET", 200
        )

        assert status == "PASSED"
        assert message == "Success"
        assert err_code == ""
        assert result_fields["status"] == "PASSED"
        assert result_fields["method"] == "GET"
        assert result_fields["item_path"] == [0, 1]

    @patch("postman_api_tester.handlers.test_proxy_routes._evaluate_result_judgment")
    @patch("postman_api_tester.handlers.test_proxy_routes._resolve_judgment_params_for_proxy")
    @patch("postman_api_tester.handlers.test_proxy_routes._utils_extract_msg_errcode")
    def test_failed_judgment(
        self,
        mock_extract: MagicMock,
        mock_resolve: MagicMock,
        mock_evaluate: MagicMock,
    ) -> None:
        """测试判定失败场景。"""
        mock_extract.return_value = ("Error occurred", "ERR001")
        mock_resolve.return_value = {
            "success_err_codes": None,
            "success_messages": None,
            "enable_err_code_judgment": True,
            "enable_message_judgment": False,
        }
        mock_evaluate.return_value = (False, "Error code mismatch")

        exec_result: Dict[str, Any] = {
            "response_body": {"message": "Error occurred", "errCode": "ERR001"},
            "status_code": 200,
            "normalized_url": "http://example.com/api",
            "actual_request_url": "http://example.com/api",
        }
        source: Dict[str, Any] = {}

        status, message, err_code, result_fields = _evaluate_and_build_result(
            exec_result, source, "POST", 200
        )

        assert status == "FAILED"
        assert message == "Error code mismatch"
        assert err_code == "ERR001"
        assert result_fields["status"] == "FAILED"


class TestCheckProxyHostAllowed:
    """_check_proxy_host_allowed 主机白名单测试。"""

    @patch("postman_api_tester.report_server_config.PROXY_ALLOWED_HOSTS", set())
    def test_no_whitelist_allows_all(self) -> None:
        """无白名单配置时允许所有主机。"""
        result = _check_proxy_host_allowed("http://any-domain.com/api")
        assert result is None

    @patch("postman_api_tester.report_server_config.PROXY_ALLOWED_HOSTS", {"allowed.com"})
    def test_whitelist_allows_matching_host(self) -> None:
        """白名单匹配时允许。"""
        result = _check_proxy_host_allowed("http://allowed.com/api")
        assert result is None

    @patch("postman_api_tester.report_server_config.PROXY_ALLOWED_HOSTS", {"allowed.com"})
    def test_whitelist_blocks_non_matching_host(self, app_context: None) -> None:
        """白名单不匹配时阻止。"""
        result = _check_proxy_host_allowed("http://blocked.com/api")
        assert result is not None
        assert isinstance(result, tuple)
        assert result[1] == 403
