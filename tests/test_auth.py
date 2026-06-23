"""auth 模块单元测试。

覆盖 _is_login_candidate、_extract_token_from_payload、get_auth_token。
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from postman_api_tester.auth import (
	_extract_token_from_payload,
	_is_login_candidate,
	get_auth_token,
)


class TestIsLoginCandidate:
	"""_is_login_candidate() 登录接口识别测试。"""

	def test_name_contains_login(self) -> None:
		assert _is_login_candidate({"name": "User Login", "url": "/api/users"}) is True

	def test_url_contains_login(self) -> None:
		assert _is_login_candidate({"name": "Get Users", "url": "/api/login"}) is True

	def test_both_contain_login(self) -> None:
		assert _is_login_candidate({"name": "Login", "url": "/login"}) is True

	def test_case_insensitive(self) -> None:
		assert _is_login_candidate({"name": "USER LOGIN", "url": "/API/USERS"}) is True

	def test_no_login_in_name_or_url(self) -> None:
		assert _is_login_candidate({"name": "Get Users", "url": "/api/users"}) is False

	def test_empty_fields(self) -> None:
		assert _is_login_candidate({"name": "", "url": ""}) is False

	def test_missing_fields(self) -> None:
		assert _is_login_candidate({}) is False

	def test_login_as_substring(self) -> None:
		assert _is_login_candidate({"name": "do-login-action", "url": "/api"}) is True


class TestExtractTokenFromPayload:
	"""_extract_token_from_payload() token 提取测试。"""

	def test_top_level_token(self) -> None:
		assert _extract_token_from_payload({"token": "abc123"}) == "abc123"

	def test_top_level_access_token(self) -> None:
		assert _extract_token_from_payload({"access_token": "xyz"}) == "xyz"

	def test_top_level_accessToken_camelcase(self) -> None:
		assert _extract_token_from_payload({"accessToken": "camel"}) == "camel"

	def test_top_level_auth_token(self) -> None:
		assert _extract_token_from_payload({"auth_token": "auth123"}) == "auth123"

	def test_top_level_authorization(self) -> None:
		assert _extract_token_from_payload({"authorization": "Bearer xxx"}) == "Bearer xxx"

	def test_nested_in_data(self) -> None:
		assert _extract_token_from_payload({"data": {"token": "nested"}}) == "nested"

	def test_nested_access_token(self) -> None:
		assert _extract_token_from_payload({"data": {"access_token": "nested_xyz"}}) == "nested_xyz"

	def test_top_level_priority_over_data(self) -> None:
		payload = {"token": "top", "data": {"token": "nested"}}
		assert _extract_token_from_payload(payload) == "top"

	def test_token_field_priority_order(self) -> None:
		payload = {"access_token": "first", "token": "second"}
		assert _extract_token_from_payload(payload) == "second"

	def test_non_dict_returns_none(self) -> None:
		assert _extract_token_from_payload("string") is None

	def test_none_returns_none(self) -> None:
		assert _extract_token_from_payload(None) is None

	def test_list_returns_none(self) -> None:
		assert _extract_token_from_payload([1, 2]) is None

	def test_empty_dict_returns_none(self) -> None:
		assert _extract_token_from_payload({}) is None

	def test_data_not_dict_returns_none(self) -> None:
		assert _extract_token_from_payload({"data": "string"}) is None

	def test_no_token_fields_returns_none(self) -> None:
		assert _extract_token_from_payload({"name": "test", "data": {"value": 1}}) is None

	def test_token_value_none_returned_as_none(self) -> None:
		assert _extract_token_from_payload({"token": None}) is None


class TestGetAuthToken:
	"""get_auth_token() 完整流程测试（mock session）。"""

	def _make_api(self, name: str = "Login", url: str = "/login", method: str = "POST") -> Dict[str, Any]:
		return {"name": name, "url": url, "method": method}

	def test_no_login_candidates_returns_none(self) -> None:
		apis = [{"name": "Get Users", "url": "/api/users", "method": "GET"}]
		mock_session = MagicMock()
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result is None
		mock_session.post.assert_not_called()
		mock_session.get.assert_not_called()

	def test_post_login_success(self) -> None:
		apis = [self._make_api()]
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"token": "my_token_123"}
		mock_session = MagicMock()
		mock_session.post.return_value = mock_response
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result == "my_token_123"

	def test_get_login_success(self) -> None:
		apis = [self._make_api(method="GET")]
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"access_token": "get_token"}
		mock_session = MagicMock()
		mock_session.get.return_value = mock_response
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result == "get_token"

	def test_non_200_skips_candidate(self) -> None:
		apis = [self._make_api()]
		mock_response = MagicMock()
		mock_response.status_code = 401
		mock_session = MagicMock()
		mock_session.post.return_value = mock_response
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result is None

	def test_invalid_json_skips_candidate(self) -> None:
		apis = [self._make_api()]
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.side_effect = ValueError("invalid json")
		mock_session = MagicMock()
		mock_session.post.return_value = mock_response
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result is None

	def test_no_token_in_response_returns_none(self) -> None:
		apis = [self._make_api()]
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"message": "ok"}
		mock_session = MagicMock()
		mock_session.post.return_value = mock_response
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result is None

	def test_uses_full_url_when_present(self) -> None:
		api = {"name": "Login", "full_url": "https://auth.example.com/login", "url": "/login", "method": "POST"}
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"token": "full_url_token"}
		mock_session = MagicMock()
		mock_session.post.return_value = mock_response
		result = get_auth_token([api], "https://api.example.com", session=mock_session)
		assert result == "full_url_token"
		call_args = mock_session.post.call_args
		assert "auth.example.com" in call_args[0][0]

	def test_request_exception_continues_to_next(self) -> None:
		import requests as req
		apis = [self._make_api(name="Login1"), self._make_api(name="Login2")]
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"token": "second_token"}
		mock_session = MagicMock()
		mock_session.post.side_effect = [req.ConnectionError("fail"), mock_response]
		result = get_auth_token(apis, "https://api.example.com", session=mock_session)
		assert result == "second_token"

	def test_empty_apis_returns_none(self) -> None:
		mock_session = MagicMock()
		result = get_auth_token([], "https://api.example.com", session=mock_session)
		assert result is None
