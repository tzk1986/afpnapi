"""JSONPath 提取工具单元测试."""

import pytest
from postman_api_tester.utils.extract_utils import (
    extract_by_jsonpath,
    extract_from_header,
    extract_from_response,
)


class TestExtractByJsonpath:
    """extract_by_jsonpath() 测试."""

    def test_simple_field(self) -> None:
        assert extract_by_jsonpath({"name": "Alice"}, "$.name") == "Alice"

    def test_nested_field(self) -> None:
        data = {"data": {"token": "abc123"}}
        assert extract_by_jsonpath(data, "$.data.token") == "abc123"

    def test_array_index(self) -> None:
        data = {"items": [{"id": 1}, {"id": 2}]}
        assert extract_by_jsonpath(data, "$.items[0].id") == "1"

    def test_array_negative_index(self) -> None:
        data = {"items": [10, 20, 30]}
        assert extract_by_jsonpath(data, "$.items[-1]") == "30"

    def test_integer_value(self) -> None:
        assert extract_by_jsonpath({"count": 42}, "$.count") == "42"

    def test_boolean_true(self) -> None:
        assert extract_by_jsonpath({"active": True}, "$.active") == "true"

    def test_boolean_false(self) -> None:
        assert extract_by_jsonpath({"active": False}, "$.active") == "false"

    def test_null_value(self) -> None:
        assert extract_by_jsonpath({"x": None}, "$.x") == "None"

    def test_dict_value_serialized(self) -> None:
        data = {"info": {"a": 1}}
        result = extract_by_jsonpath(data, "$.info")
        assert result is not None
        assert '"a"' in result

    def test_missing_field(self) -> None:
        assert extract_by_jsonpath({"name": "Alice"}, "$.age") is None

    def test_missing_nested(self) -> None:
        assert extract_by_jsonpath({"data": {}}, "$.data.token") is None

    def test_array_out_of_bounds(self) -> None:
        assert extract_by_jsonpath({"items": [1]}, "$.items[5]") is None

    def test_invalid_expression_no_dollar(self) -> None:
        assert extract_by_jsonpath({"x": 1}, "x") is None

    def test_invalid_expression_wildcard(self) -> None:
        assert extract_by_jsonpath({"x": 1}, "$.*") is None

    def test_invalid_expression_recursive(self) -> None:
        assert extract_by_jsonpath({"x": {"y": 1}}, "$..y") is None

    def test_invalid_expression_filter(self) -> None:
        assert extract_by_jsonpath({"x": [1]}, "$.x[?(@>0)]") is None

    def test_empty_expression(self) -> None:
        assert extract_by_jsonpath({"x": 1}, "") is None

    def test_dollar_dot_only(self) -> None:
        assert extract_by_jsonpath({"x": 1}, "$.") is None

    def test_deeply_nested(self) -> None:
        data = {"a": {"b": {"c": {"d": "deep"}}}}
        assert extract_by_jsonpath(data, "$.a.b.c.d") == "deep"


class TestExtractFromHeader:
    """extract_from_header() 测试."""

    def test_exact_match(self) -> None:
        headers = {"Content-Type": "application/json"}
        assert extract_from_header(headers, "Content-Type") == "application/json"

    def test_case_insensitive(self) -> None:
        headers = {"Content-Type": "text/html"}
        assert extract_from_header(headers, "content-type") == "text/html"

    def test_missing_header(self) -> None:
        assert extract_from_header({}, "X-Missing") is None


class TestExtractFromResponse:
    """extract_from_response() 批量提取测试."""

    def test_mixed_extraction(self) -> None:
        data = {"data": {"token": "abc", "userId": 42}}
        headers = {"session-id": "sess-123"}
        config = {
            "token": "$.data.token",
            "userId": "$.data.userId",
            "sessionId": "$header.session-id",
        }
        result = extract_from_response(data, headers, config)
        assert result == {"token": "abc", "userId": "42", "sessionId": "sess-123"}

    def test_partial_failure(self) -> None:
        data = {"data": {"token": "abc"}}
        config = {"token": "$.data.token", "missing": "$.data.missing"}
        result = extract_from_response(data, {}, config)
        assert result == {"token": "abc"}
        assert "missing" not in result

    def test_empty_config(self) -> None:
        assert extract_from_response({}, {}, {}) == {}
