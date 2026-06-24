"""executor 模块单元测试。

覆盖 _safe_int、PostmanTestExecutor 的认证管理、_build_result_base、
_build_passed_result、_extract_message_and_err_code，以及 execute_test
的成功/失败/异常三条路径。
"""

import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.executor import (
    PostmanTestExecutor,
    _safe_int,
)


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------

class TestSafeInt:
	def test_none_returns_zero(self) -> None:
		assert _safe_int(None) == 0

	def test_int_passthrough(self) -> None:
		assert _safe_int(42) == 42
		assert _safe_int(0) == 0
		assert _safe_int(-5) == -5

	def test_str_digits(self) -> None:
		assert _safe_int("123") == 123
		assert _safe_int("-7") == -7

	def test_str_invalid(self) -> None:
		assert _safe_int("abc") == 0
		assert _safe_int("") == 0

	def test_bytes_digits(self) -> None:
		assert _safe_int(b"99") == 99

	def test_unsupported_type(self) -> None:
		assert _safe_int(3.14) == 0
		assert _safe_int([1]) == 0
		assert _safe_int({"a": 1}) == 0


# ---------------------------------------------------------------------------
# 构造辅助
# ---------------------------------------------------------------------------

def _minimal_api_config(**overrides: Any) -> Dict[str, Any]:
	base: Dict[str, Any] = {
		"name": "Test API",
		"method": "GET",
		"full_url": "https://api.example.com/test",
		"folder": "TestFolder",
		"expected_status": 200,
	}
	base.update(overrides)
	return base


def _make_executor(
	api_config: Optional[Dict[str, Any]] = None,
	auth_token: Optional[str] = None,
	**kwargs: Any,
) -> PostmanTestExecutor:
	from postman_api_tester.parser import ApiConfig
	cfg: ApiConfig = api_config or _minimal_api_config()  # type: ignore[assignment]
	return PostmanTestExecutor(cfg, auth_token=auth_token, **kwargs)


# ---------------------------------------------------------------------------
# 认证管理
# ---------------------------------------------------------------------------

class TestAuthManagement:
	def test_no_token_initially(self) -> None:
		exc = _make_executor()
		assert exc.get_auth_token() is None

	def test_set_and_get(self) -> None:
		exc = _make_executor()
		exc.set_auth_token("abc123")
		assert exc.get_auth_token() == "abc123"

	def test_init_with_token(self) -> None:
		exc = _make_executor(auth_token="initial")
		assert exc.get_auth_token() == "initial"

	def test_overwrite_token(self) -> None:
		exc = _make_executor(auth_token="first")
		exc.set_auth_token("second")
		assert exc.get_auth_token() == "second"


# ---------------------------------------------------------------------------
# _build_result_base
# ---------------------------------------------------------------------------

class TestBuildResultBase:
	def test_default_fields(self) -> None:
		exc = _make_executor()
		result = exc._build_result_base(
			actual_request_url="https://api.example.com/test",
			status="PASSED",
			message="ok",
			err_code="",
			status_code=200,
			response_time_ms=42,
		)
		assert result["name"] == "Test API"
		assert result["method"] == "GET"
		assert result["url"] == "https://api.example.com/test"
		assert result["status"] == "PASSED"
		assert result["message"] == "ok"
		assert result["err_code"] == ""
		assert result["status_code"] == 200
		assert result["response_time_ms"] == 42
		assert result["folder"] == "TestFolder"
		assert result["expected_status"] == 200
		assert result["assertion_results"] == []
		assert result["assertion_engine_error"] == ""
		assert result["extracted_variables"] == {}
		assert result["data_index"] == 0
		assert result["request_info"] == {"headers": {}, "params": {}, "body": None}
		assert result["response_info"] == {"headers": {}, "body": ""}

	def test_with_custom_request_response_info(self) -> None:
		from postman_api_tester.executor import RequestInfo, ResponseInfo
		exc = _make_executor()
		req_info: RequestInfo = {"headers": {"X-Custom": "v"}, "params": {"q": "1"}, "body": None}
		resp_info: ResponseInfo = {"headers": {"Content-Type": "application/json"}, "body": {"ok": True}}
		result = exc._build_result_base(
			actual_request_url="https://api.example.com/test",
			status="PASSED",
			message="ok",
			err_code="",
			status_code=200,
			response_time_ms=10,
			request_info=req_info,
			response_info=resp_info,
		)
		assert result["request_info"] == req_info
		assert result["response_info"] == resp_info

	def test_data_index_from_api_config(self) -> None:
		exc = _make_executor(_minimal_api_config(data_index=7))
		result = exc._build_result_base(
			actual_request_url="",
			status="PASSED",
			message="",
			err_code="",
			status_code=200,
			response_time_ms=0,
		)
		assert result["data_index"] == 7

	def test_item_path_from_api_config(self) -> None:
		exc = _make_executor(_minimal_api_config(item_path=[0, 2, 1]))
		result = exc._build_result_base(
			actual_request_url="",
			status="PASSED",
			message="",
			err_code="",
			status_code=200,
			response_time_ms=0,
		)
		assert result["item_path"] == [0, 2, 1]

	def test_missing_expected_status_defaults_200(self) -> None:
		cfg = {"name": "X", "method": "GET", "full_url": "/x"}
		exc = _make_executor(cfg)
		result = exc._build_result_base(
			actual_request_url="",
			status="PASSED",
			message="",
			err_code="",
			status_code=200,
			response_time_ms=0,
		)
		assert result["expected_status"] == 200


# ---------------------------------------------------------------------------
# _build_passed_result
# ---------------------------------------------------------------------------

class TestBuildPassedResult:
	def test_assertions_pass(self) -> None:
		exc = _make_executor()
		result = exc._build_passed_result(
			actual_request_url="https://api.example.com/test",
			response_message="success",
			err_code="0",
			status_code=200,
			response_time_ms=5,
			request_info={"headers": {}, "params": {}, "body": None},
			response_info={"headers": {}, "body": {}},
			extracted_variables={"tok": "xyz"},
			assertion_results=[{"passed": True, "message": "ok"}],
			assertion_engine_error="",
		)
		assert result["status"] == "PASSED"
		assert result["message"] == "success"
		assert result["extracted_variables"] == {"tok": "xyz"}
		assert len(result["assertion_results"]) == 1

	def test_assertion_failure_switches_to_failed(self) -> None:
		exc = _make_executor()
		result = exc._build_passed_result(
			actual_request_url="https://api.example.com/test",
			response_message="success",
			err_code="0",
			status_code=200,
			response_time_ms=5,
			request_info={"headers": {}, "params": {}, "body": None},
			response_info={"headers": {}, "body": {}},
			extracted_variables={},
			assertion_results=[
				{"passed": True, "message": "ok"},
				{"passed": False, "message": "expect 200 got 404"},
			],
			assertion_engine_error="",
		)
		assert result["status"] == "FAILED"
		assert "断言失败" in result["message"]
		assert "expect 200 got 404" in result["message"]


# ---------------------------------------------------------------------------
# _extract_message_and_err_code
# ---------------------------------------------------------------------------

class TestExtractMessageAndErrCode:
	def test_standard_keys(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({
			"message": "操作成功",
			"errCode": "0",
		})
		assert msg == "操作成功"
		assert code == "0"

	def test_alternate_message_keys(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({
			"msg": "ok",
			"errorCode": "E001",
		})
		assert msg == "ok"
		assert code == "E001"

	def test_nested_data_fallback(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({
			"data": {"message": "nested msg", "errCode": "99"},
		})
		assert msg == "nested msg"
		assert code == "99"

	def test_top_level_takes_precedence_over_data(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({
			"message": "top",
			"errCode": "T01",
			"data": {"message": "nested", "errCode": "N01"},
		})
		assert msg == "top"
		assert code == "T01"

	def test_data_fills_only_missing_top_level(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({
			"message": "top only",
			"data": {"errCode": "D01"},
		})
		assert msg == "top only"
		assert code == "D01"

	def test_non_dict_returns_empty(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code("not a dict")
		assert msg == ""
		assert code == ""

	def test_missing_all_keys(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({"foo": "bar"})
		assert msg == ""
		assert code == ""

	def test_null_values_skipped(self) -> None:
		exc = _make_executor()
		msg, code = exc._extract_message_and_err_code({
			"message": None,
			"errCode": None,
			"msg": "fallback",
		})
		assert msg == "fallback"
		assert code == ""


# ---------------------------------------------------------------------------
# execute_test — 成功路径
# ---------------------------------------------------------------------------

class TestExecuteTestSuccessPath:
	def _mock_session_get(
		self,
		status_code: int = 200,
		json_body: Optional[Dict[str, Any]] = None,
		response_url: str = "https://api.example.com/test",
	) -> MagicMock:
		session = MagicMock()
		resp = MagicMock()
		resp.status_code = status_code
		resp.json.return_value = json_body if json_body is not None else {"message": "success", "errCode": "0"}
		resp.headers = {"Content-Type": "application/json"}
		resp.request = MagicMock()
		resp.request.url = response_url
		session.get.return_value = resp
		return session

	def test_simple_get_pass(self) -> None:
		session = self._mock_session_get()
		exc = _make_executor(session=session)
		result = exc.execute_test()
		assert result["status"] == "PASSED"
		assert result["status_code"] == 200
		assert result["response_time_ms"] >= 0
		session.get.assert_called_once()
		session.close.assert_not_called()

	def test_auth_token_added_as_token_header(self) -> None:
		session = self._mock_session_get()
		exc = _make_executor(auth_token="tok123", session=session)
		result = exc.execute_test()
		assert result["status"] == "PASSED"
		call_kwargs = session.get.call_args
		headers_sent = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
		assert headers_sent.get("token") == "tok123"

	def test_auth_token_overrides_existing_authorization(self) -> None:
		from postman_api_tester.parser import ApiConfig
		session = self._mock_session_get()
		cfg: ApiConfig = _minimal_api_config(headers={"Authorization": "Bearer old"})  # type: ignore[assignment]
		exc = PostmanTestExecutor(cfg, auth_token="new_tok", session=session)
		exc.execute_test()
		call_kwargs = session.get.call_args
		headers_sent = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
		assert headers_sent["Authorization"] == "Bearer new_tok"


# ---------------------------------------------------------------------------
# execute_test — 不支持的 HTTP 方法
# ---------------------------------------------------------------------------

class TestExecuteTestUnsupportedMethod:
	def test_unsupported_method_returns_failed(self) -> None:
		from postman_api_tester.parser import ApiConfig
		session = MagicMock()
		cfg: ApiConfig = _minimal_api_config(method="OPTIONS")  # type: ignore[assignment]
		exc = PostmanTestExecutor(cfg, session=session)
		result = exc.execute_test()
		assert result["status"] == "FAILED"
		assert "不支持的HTTP方法" in result["message"]
		session.get.assert_not_called()
		session.post.assert_not_called()


# ---------------------------------------------------------------------------
# execute_test — 请求异常
# ---------------------------------------------------------------------------

class TestExecuteTestRequestError:
	def test_connection_error_returns_error_status(self) -> None:
		import requests
		session = MagicMock()
		session.get.side_effect = requests.exceptions.ConnectionError("refused")
		exc = _make_executor(session=session)
		result = exc.execute_test()
		assert result["status"] == "ERROR"
		assert "请求异常" in result["message"]
		assert result["status_code"] is None
		assert result["response_time_ms"] == 0

	def test_timeout_returns_timeout_label(self) -> None:
		import requests
		session = MagicMock()
		session.get.side_effect = requests.exceptions.Timeout("timed out")
		exc = _make_executor(session=session)
		result = exc.execute_test()
		assert result["status"] == "ERROR"
		assert "请求超时" in result["message"]


# ---------------------------------------------------------------------------
# execute_test — 判定失败
# ---------------------------------------------------------------------------

class TestExecuteTestJudgmentFailure:
	def test_status_code_mismatch_fails(self) -> None:
		session = MagicMock()
		resp = MagicMock()
		resp.status_code = 500
		resp.json.return_value = {"message": "internal error", "errCode": "E500"}
		resp.headers = {}
		resp.request = MagicMock()
		resp.request.url = "https://api.example.com/test"
		session.get.return_value = resp
		exc = _make_executor(session=session)
		result = exc.execute_test()
		assert result["status"] == "FAILED"
		assert result["status_code"] == 500
		assert "db_feedback" in result


# ---------------------------------------------------------------------------
# __init__ 边界
# ---------------------------------------------------------------------------

class TestInit:
	def test_creates_private_session_when_none_passed(self) -> None:
		exc = _make_executor()
		assert exc._owns_session is True
		assert exc.session is not None

	def test_does_not_own_external_session(self) -> None:
		external_session = MagicMock()
		exc = _make_executor(session=external_session)
		assert exc._owns_session is False
		assert exc.session is external_session

	def test_default_timeout(self) -> None:
		exc = _make_executor()
		assert exc.request_timeout == (10, 30)

	def test_custom_timeout(self) -> None:
		exc = _make_executor(request_timeout=(5, 15))
		assert exc.request_timeout == (5, 15)

	def test_api_config_is_copied(self) -> None:
		original = _minimal_api_config()
		exc = _make_executor(api_config=original)
		exc.api_config["name"] = "Mutated"
		assert original["name"] == "Test API"
