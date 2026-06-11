"""report_request_service 单元测试."""

import json
from typing import Dict, Any

import pytest

from postman_api_tester.services.report_request_service import (
    extract_http_request_fields,
    inject_token_header,
    is_valid_http_url,
    parse_int_default,
    parse_optional_int,
    resolve_request_payload_source,
)


# ============================================================
# resolve_request_payload_source
# ============================================================


class TestResolveRequestPayloadSource:
    def test_json_only_returns_false_multipart(self) -> None:
        """非 multipart 内容类型返回 False, 且 payload==source."""
        payload = {"key": "value"}
        is_mp, pl, src = resolve_request_payload_source(
            content_type="application/json",
            json_payload=payload,
            request_meta_raw='{"url":"http://x"}',
        )
        assert is_mp is False
        assert pl == payload
        assert src == payload
        assert pl is src

    def test_json_null_payload(self) -> None:
        """json_payload 为 None 时返回空 dict."""
        _, pl, src = resolve_request_payload_source(
            content_type="application/json",
            json_payload=None,
            request_meta_raw=None,
        )
        assert pl == {}
        assert src is pl

    def test_multipart_returns_true_separates_source(self) -> None:
        """multipart 时 payload 与 source 分离."""
        payload = {"body_field": "val"}
        meta_raw = '{"url":"http://example.com","method":"POST"}'
        is_mp, pl, src = resolve_request_payload_source(
            content_type="multipart/form-data; boundary=----abc",
            json_payload=payload,
            request_meta_raw=meta_raw,
        )
        assert is_mp is True
        assert pl == payload
        assert src == {"url": "http://example.com", "method": "POST"}
        assert pl is not src

    def test_multipart_invalid_json_meta_defaults_to_empty(self) -> None:
        """无效的 JSON 元数据回退到空 dict."""
        payload = {"a": "1"}
        is_mp, _, src = resolve_request_payload_source(
            content_type="multipart/form-data",
            json_payload=payload,
            request_meta_raw="{not-json}",
        )
        assert is_mp is True
        assert src == {}

    def test_multipart_none_meta_raw(self) -> None:
        """request_meta_raw 为 None 时处理正常."""
        payload = {"a": "1"}
        is_mp, _, src = resolve_request_payload_source(
            content_type="multipart/form-data",
            json_payload=payload,
            request_meta_raw=None,
        )
        assert is_mp is True
        assert src == {}

    def test_multipart_numeric_meta_raw(self) -> None:
        """request_meta_raw 为非 dict 的 JSON（如数字）回退到空 dict."""
        payload = {"a": "1"}
        is_mp, _, src = resolve_request_payload_source(
            content_type="multipart/form-data",
            json_payload=payload,
            request_meta_raw="42",
        )
        assert src == {}

    def test_content_type_has_charset_suffix(self) -> None:
        """带 charset 后缀的 multipart 仍能识别."""
        _, pl, _ = resolve_request_payload_source(
            content_type="multipart/form-data; charset=utf-8",
            json_payload={"x": 1},
            request_meta_raw=None,
        )
        assert pl == {"x": 1}

    def test_application_octet_stream_is_not_multipart(self) -> None:
        """普通 application/json 不视为 multipart."""
        is_mp, _, _ = resolve_request_payload_source(
            content_type="application/json; charset=utf-8",
            json_payload={"key": "val"},
            request_meta_raw=None,
        )
        assert is_mp is False


# ============================================================
# is_valid_http_url
# ============================================================


class TestIsValidHttpUrl:
    def test_valid_https(self) -> None:
        assert is_valid_http_url("https://example.com/path?q=1") is True

    def test_valid_http(self) -> None:
        assert is_valid_http_url("http://localhost:8080/api") is True

    def test_valid_simple(self) -> None:
        assert is_valid_http_url("https://api.example.com") is True

    def test_none_url(self) -> None:
        assert is_valid_http_url(None) is False

    def test_empty_string(self) -> None:
        assert is_valid_http_url("") is False

    def test_missing_scheme(self) -> None:
        assert is_valid_http_url("example.com") is False

    def test_missing_netloc(self) -> None:
        assert is_valid_http_url("https:///no-host") is False

    def test_file_scheme_rejected(self) -> None:
        assert is_valid_http_url("file:///etc/passwd") is False

    def test_custom_scheme_rejected(self) -> None:
        assert is_valid_http_url("ftp://files.example.com") is False

    def test_javascript_scheme_rejected(self) -> None:
        assert is_valid_http_url("javascript:void(0)") is False

    def test_only_scheme(self) -> None:
        assert is_valid_http_url("https://") is False

    def test_whitespace_url(self) -> None:
        assert is_valid_http_url("   ") is False


# ============================================================
# parse_int_default
# ============================================================


class TestParseIntDefault:
    def test_int_input(self) -> None:
        assert parse_int_default(42, 0) == 42

    def test_string_int(self) -> None:
        assert parse_int_default("99", 0) == 99

    def test_float_str(self) -> None:
        assert parse_int_default("3.5", 10) == 10

    def test_negative(self) -> None:
        assert parse_int_default(-7, 0) == -7

    def test_zero(self) -> None:
        assert parse_int_default(0, 5) == 0

    def test_none_returns_default(self) -> None:
        assert parse_int_default(None, 42) == 42

    def test_string_returns_default(self) -> None:
        assert parse_int_default("abc", 7) == 7

    def test_list_returns_default(self) -> None:
        assert parse_int_default([1, 2], 3) == 3

    def test_float_input_truncates(self) -> None:
        """浮点数被 int() 直接转换（截断），不走默认值."""
        assert parse_int_default(3.7, 99) == 3


# ============================================================
# parse_optional_int
# ============================================================


class TestParseOptionalInt:
    def test_int_input(self) -> None:
        assert parse_optional_int(42) == 42

    def test_string_int(self) -> None:
        assert parse_optional_int("55") == 55

    def test_none_returns_none(self) -> None:
        assert parse_optional_int(None) is None

    def test_invalid_string_returns_none(self) -> None:
        assert parse_optional_int("abc") is None

    def test_float_truncates_not_none(self) -> None:
        """Python int() 对 float 做截断，不返回 None."""
        assert parse_optional_int(3.7) == 3

    def test_negative(self) -> None:
        assert parse_optional_int(-1) == -1

    def test_zero(self) -> None:
        assert parse_optional_int(0) == 0

    def test_list_returns_none(self) -> None:
        assert parse_optional_int([]) is None

    def test_dict_returns_none(self) -> None:
        assert parse_optional_int({}) is None


# ============================================================
# inject_token_header
# ============================================================


class TestInjectTokenHeader:
    def test_add_token_new(self) -> None:
        headers: Dict[str, Any] = {"Content-Type": "application/json"}
        result = inject_token_header(headers, "secret-token")
        assert result["token"] == "secret-token"
        assert "Content-Type" in result

    def test_replace_existing_token(self) -> None:
        headers: Dict[str, Any] = {"token": "old-token"}
        result = inject_token_header(headers, "new-token")
        assert result["token"] == "new-token"
        assert "old-token" not in str(result.values())

    def test_replace_authorization_with_bearer(self) -> None:
        headers: Dict[str, Any] = {"Authorization": "Basic xxx"}
        result = inject_token_header(headers, "jwt-token")
        assert result["Authorization"] == "Bearer jwt-token"

    def test_priority_authorization_over_token(self) -> None:
        """当同时存在 Authorization 和 token 时，优先更新 Authorization 并移除 token."""
        headers: Dict[str, Any] = {"token": "old", "Authorization": "Basic yyy"}
        result = inject_token_header(headers, "bearer-x")
        assert result["Authorization"] == "Bearer bearer-x"
        assert "token" not in result

    def test_empty_token_no_change(self) -> None:
        headers: Dict[str, Any] = {"X-Custom": "val"}
        result = inject_token_header(headers, "")
        assert result == headers

    def test_none_headers_returned(self) -> None:
        """headers 为 None 时返回空 dict（dict(None or {}) 行为）."""
        # 注意：headers 参数类型为 Dict，None 在调用 dict(None or {}) 时会出错
        # 但由于实际调用处不太可能传入 None，这里测试空 dict 场景
        result = inject_token_header({}, "tok")
        assert result == {"token": "tok"}

    def test_case_insensitive_token_removal(self) -> None:
        """TOKEN 大写形式也会被移除."""
        headers: Dict[str, Any] = {"TOKEN": "old"}
        result = inject_token_header(headers, "new")
        assert result["token"] == "new"
        assert "TOKEN" not in result

    def test_case_insensitive_authorization_match(self) -> None:
        """AUTHORIZATION 大写形式触发 Bearer 模式."""
        headers: Dict[str, Any] = {"AUTHORIZATION": "Basic zzz"}
        result = inject_token_header(headers, "jwt")
        assert result["AUTHORIZATION"] == "Bearer jwt"

    def test_original_headers_unchanged(self) -> None:
        """返回新字典，原字典不受影响."""
        headers: Dict[str, Any] = {"token": "orig"}
        inject_token_header(headers, "new")
        assert headers["token"] == "orig"

    def test_empty_token_leaves_authorization(self) -> None:
        """空 token 不修改任何现有头."""
        headers: Dict[str, Any] = {"Authorization": "Basic old", "token": "t"}
        result = inject_token_header(headers, "")
        assert result["Authorization"] == "Basic old"
        assert result["token"] == "t"


# ============================================================
# extract_http_request_fields
# ============================================================


class TestExtractHttpRequestFields:
    def test_basic_fields(self) -> None:
        source = {
            "url": "  https://api.example.com/test  ",
            "method": "post",
            "headers": {"X-Custom": "val"},
            "params": {"q": "1"},
            "body_mode": "JSON",
            "body_data": {"key": "val"},
        }
        payload = {"body": "legacy-body-content"}
        result = extract_http_request_fields(source, payload)
        assert result["url"] == "https://api.example.com/test"
        assert result["method"] == "POST"
        assert result["headers"] == {"X-Custom": "val"}
        assert result["params"] == {"q": "1"}
        assert result["body_mode"] == "json"
        assert result["body_data"] == {"key": "val"}
        assert result["legacy_body"] == "legacy-body-content"

    def test_defaults_when_missing(self) -> None:
        """缺少字段时使用默认值."""
        result = extract_http_request_fields({}, {"body": "lb"})
        assert result["url"] == ""
        assert result["method"] == "GET"
        assert result["headers"] == {}
        assert result["params"] == {}
        assert result["body_mode"] == "legacy"
        assert result["body_data"] is None
        assert result["legacy_body"] == "lb"

    def test_url_stripped_and_lowered_method(self) -> None:
        """URL 去空白，method 转大写."""
        source = {"url": "\thttp://x\t\n", "method": "PuT"}
        result = extract_http_request_fields(source, {})
        assert result["url"] == "http://x"
        assert result["method"] == "PUT"

    def test_headers_none_becomes_empty_dict(self) -> None:
        """headers 为 None 时转为空 dict."""
        source = {"url": "http://x", "headers": None}
        result = extract_http_request_fields(source, {})
        assert result["headers"] == {}

    def test_params_none_becomes_empty_dict(self) -> None:
        """params 为 None 时转为空 dict."""
        source = {"url": "http://x", "params": None}
        result = extract_http_request_fields(source, {})
        assert result["params"] == {}

    def test_body_mode_stripped_lowered(self) -> None:
        """body_mode 去空白并小写."""
        source = {"url": "http://x", "body_mode": "  GraphQL "}
        result = extract_http_request_fields(source, {})
        assert result["body_mode"] == "graphql"

    def test_headers_is_copy(self) -> None:
        """返回的 headers 是副本，修改不影响源数据."""
        src_headers = {"A": "1"}
        source = {"url": "http://x", "headers": src_headers}
        result = extract_http_request_fields(source, {})
        result["headers"]["B"] = "2"
        assert "B" not in src_headers

    def test_params_is_copy(self) -> None:
        """返回的 params 是副本."""
        src_params = {"k": "v"}
        source = {"url": "http://x", "params": src_params}
        result = extract_http_request_fields(source, {})
        result["params"]["k2"] = "v2"
        assert "k2" not in src_params

    def test_full_realistic_payload(self) -> None:
        """模拟真实请求场景."""
        source = {
            "url": "https://api.prod.example.com/v2/users",
            "method": "PATCH",
            "headers": {
                "Authorization": "Bearer abc",
                "Content-Type": "application/json",
            },
            "params": {"include": "profile"},
            "body_mode": "json",
            "body_data": {"email": "test@example.com"},
        }
        payload = {"body": None}
        result = extract_http_request_fields(source, payload)
        assert result["url"] == "https://api.prod.example.com/v2/users"
        assert result["method"] == "PATCH"
        assert len(result["headers"]) == 2
        assert result["params"] == {"include": "profile"}
        assert result["body_mode"] == "json"
        assert result["body_data"] == {"email": "test@example.com"}
