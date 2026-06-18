"""http_handler.execute_http_request 单元测试。

覆盖 URL 安全校验、请求参数归一化、响应分类处理与异常路径。
"""

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.handlers.http_handler import execute_http_request


def _mock_response(
	*,
	status_code: int = 200,
	content_type: str = "application/json",
	json_body: Any = None,
	text_body: str = "",
	content: bytes | None = None,
	headers: Dict[str, str] | None = None,
) -> MagicMock:
	resp = MagicMock()
	resp.status_code = status_code
	resp.headers = headers or {"content-type": content_type}
	resp.request = MagicMock()
	resp.request.url = "https://example.com/api/test"
	if json_body is not None:
		resp.json.return_value = json_body
	else:
		resp.json.side_effect = ValueError("not json")
	resp.text = text_body
	resp.content = content if content is not None else text_body.encode()
	return resp


class TestUrlValidation:
	"""URL 安全校验测试。"""

	def test_rejects_ftp_scheme(self) -> None:
		result = execute_http_request(
			url="ftp://example.com/file",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)
		assert result["success"] is False
		assert result["error_code"] == 400
		assert "http/https" in result["error_message"]

	def test_rejects_javascript_scheme(self) -> None:
		result = execute_http_request(
			url="javascript:alert(1)",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)
		assert result["success"] is False
		assert result["error_code"] == 400

	def test_rejects_empty_url(self) -> None:
		result = execute_http_request(
			url="",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)
		assert result["success"] is False
		assert result["error_code"] == 400

	def test_rejects_no_scheme(self) -> None:
		result = execute_http_request(
			url="example.com/api",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)
		assert result["success"] is False
		assert result["error_code"] == 400


class TestSuccessfulRequests:
	"""成功请求路径测试。"""

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_json_response(self, mock_request: MagicMock) -> None:
		mock_request.return_value = _mock_response(
			json_body={"key": "value"},
			content_type="application/json",
		)

		result = execute_http_request(
			url="https://example.com/api/test",
			method="GET",
			headers={"Authorization": "Bearer token"},
			params={"page": "1"},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is True
		assert result["status_code"] == 200
		assert result["response_body"] == {"key": "value"}
		assert result["response_body_is_binary"] is False
		assert result["elapsed_ms"] >= 0
		assert result["normalized_url"] == "https://example.com/api/test"

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_text_response(self, mock_request: MagicMock) -> None:
		mock_request.return_value = _mock_response(
			text_body="<html>Hello</html>",
			content_type="text/html",
		)

		result = execute_http_request(
			url="https://example.com/page",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is True
		assert result["response_body"] == "<html>Hello</html>"
		assert result["response_content_type"] == "text/html"
		assert result["response_body_is_binary"] is False

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_image_response_base64_encoded(self, mock_request: MagicMock) -> None:
		image_bytes = b"\x89PNG\r\n\x1a\nfakedata"
		mock_request.return_value = _mock_response(
			content_type="image/png",
			content=image_bytes,
		)

		result = execute_http_request(
			url="https://example.com/logo.png",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is True
		assert result["response_body_is_binary"] is True
		assert result["response_content_type"] == "image/png"
		import base64
		assert result["response_body"] == base64.b64encode(image_bytes).decode("ascii")

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_url_with_params_merged(self, mock_request: MagicMock) -> None:
		mock_request.return_value = _mock_response(json_body={"ok": True})

		result = execute_http_request(
			url="https://example.com/api?existing=1",
			method="GET",
			headers={},
			params={"added": "2"},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is True
		assert result["normalized_params"]["existing"] == "1"
		assert result["normalized_params"]["added"] == "2"


class TestErrorHandling:
	"""异常路径测试。"""

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_connection_error_returns_502(self, mock_request: MagicMock) -> None:
		import requests as req
		mock_request.side_effect = req.ConnectionError("Connection refused")

		result = execute_http_request(
			url="https://example.com/api",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is False
		assert result["error_code"] == 502
		assert "Connection refused" in result["error_message"]

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_timeout_returns_502(self, mock_request: MagicMock) -> None:
		import requests as req
		mock_request.side_effect = req.Timeout("Read timed out")

		result = execute_http_request(
			url="https://example.com/api",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is False
		assert result["error_code"] == 502

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_json_parse_fallback_to_text(self, mock_request: MagicMock) -> None:
		resp = _mock_response(text_body="not json", content_type="application/json")
		resp.json.side_effect = ValueError("invalid json")
		mock_request.return_value = resp

		result = execute_http_request(
			url="https://example.com/api",
			method="GET",
			headers={},
			params={},
			body_mode="none",
			body_data=None,
			legacy_body=None,
			is_multipart=False,
			files_source=None,
		)

		assert result["success"] is True
		assert result["response_body"] == "not json"


class TestBuildRequestValidation:
	"""请求构建阶段校验测试。"""

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_binary_mode_without_file_returns_400(self, mock_request: MagicMock) -> None:
		result = execute_http_request(
			url="https://example.com/api",
			method="POST",
			headers={},
			params={},
			body_mode="binary",
			body_data={"upload_key": "upload_0"},
			legacy_body=None,
			is_multipart=True,
			files_source=None,
		)

		assert result["success"] is False
		assert result["error_code"] == 400
		assert "上传文件" in result["error_message"]
		mock_request.assert_not_called()

	@patch("postman_api_tester.handlers.http_handler.requests.request")
	def test_multipart_unsupported_mode_returns_400(self, mock_request: MagicMock) -> None:
		result = execute_http_request(
			url="https://example.com/api",
			method="POST",
			headers={},
			params={},
			body_mode="raw",
			body_data=None,
			legacy_body=None,
			is_multipart=True,
			files_source=None,
		)

		assert result["success"] is False
		assert result["error_code"] == 400
		mock_request.assert_not_called()
