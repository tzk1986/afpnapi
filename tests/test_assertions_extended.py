"""断言引擎扩展操作符测试（v1.10.0）。"""

from __future__ import annotations

import pytest

from postman_api_tester.assertions import (
    SUPPORTED_OPS,
    _check_type,
    _compare,
    evaluate_assertions,
)


class TestRegexOp:

    def test_regex_match_success(self) -> None:
        passed, msg = _compare("13800138000", "regex", r"^1[3-9]\d{9}$")
        assert passed is True
        assert msg == ""

    def test_regex_match_failure(self) -> None:
        passed, msg = _compare("12345", "regex", r"^\d{11}$")
        assert passed is False
        assert "不匹配正则" in msg

    def test_regex_empty_pattern(self) -> None:
        passed, msg = _compare("anything", "regex", "")
        assert passed is True

    def test_regex_partial_match(self) -> None:
        passed, msg = _compare("hello world 42", "regex", r"\d+")
        assert passed is True


class TestLengthEqOp:

    def test_array_length_match(self) -> None:
        passed, msg = _compare([1, 2, 3], "length_eq", 3)
        assert passed is True

    def test_array_length_mismatch(self) -> None:
        passed, msg = _compare([1, 2], "length_eq", 3)
        assert passed is False
        assert "实际长度 2" in msg

    def test_string_length_match(self) -> None:
        passed, msg = _compare("hello", "length_eq", 5)
        assert passed is True

    def test_string_length_mismatch(self) -> None:
        passed, msg = _compare("hi", "length_eq", 5)
        assert passed is False

    def test_none_length(self) -> None:
        passed, msg = _compare(None, "length_eq", 0)
        assert passed is True

    def test_string_expected_converted(self) -> None:
        passed, msg = _compare("abc", "length_eq", "3")
        assert passed is True


class TestTypeOp:

    def test_type_string(self) -> None:
        passed, msg = _compare("hello", "type", "string")
        assert passed is True

    def test_type_integer(self) -> None:
        passed, msg = _compare(42, "type", "integer")
        assert passed is True

    def test_type_number_int(self) -> None:
        passed, msg = _compare(42, "type", "number")
        assert passed is True

    def test_type_number_float(self) -> None:
        passed, msg = _compare(3.14, "type", "number")
        assert passed is True

    def test_type_number_rejects_bool(self) -> None:
        passed, msg = _compare(True, "type", "number")
        assert passed is False

    def test_type_boolean(self) -> None:
        passed, msg = _compare(True, "type", "boolean")
        assert passed is True

    def test_type_array(self) -> None:
        passed, msg = _compare([1, 2], "type", "array")
        assert passed is True

    def test_type_object(self) -> None:
        passed, msg = _compare({"a": 1}, "type", "object")
        assert passed is True

    def test_type_null(self) -> None:
        passed, msg = _compare(None, "type", "null")
        assert passed is True

    def test_type_mismatch(self) -> None:
        passed, msg = _compare("hello", "type", "integer")
        assert passed is False
        assert "期望 integer" in msg

    def test_type_unknown(self) -> None:
        passed, msg = _compare("hello", "type", "unknown_type")
        assert passed is False
        assert "未知类型" in msg


class TestCheckType:

    def test_string_pass(self) -> None:
        assert _check_type("abc", "string") == (True, "")

    def test_integer_pass(self) -> None:
        assert _check_type(42, "integer") == (True, "")

    def test_bool_is_not_integer(self) -> None:
        passed, _ = _check_type(True, "integer")
        assert passed is False


class TestSchemaOp:

    def test_schema_valid(self) -> None:
        schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
        passed, msg = _compare({"id": 42, "name": "test"}, "schema", schema)
        assert passed is True

    def test_schema_missing_required(self) -> None:
        pytest.importorskip("jsonschema")
        schema = {"type": "object", "required": ["id"]}
        passed, msg = _compare({"name": "test"}, "schema", schema)
        assert passed is False
        assert "Schema 验证失败" in msg

    def test_schema_wrong_type(self) -> None:
        pytest.importorskip("jsonschema")
        schema = {"type": "string"}
        passed, msg = _compare(42, "schema", schema)
        assert passed is False

    def test_schema_available_flag(self) -> None:
        from postman_api_tester.assertions import _JSONSCHEMA_AVAILABLE
        assert isinstance(_JSONSCHEMA_AVAILABLE, bool)


class TestEvaluateAssertionsWithNewOps:

    def test_regex_in_evaluate(self) -> None:
        body = {"phone": "13800138000"}
        assertions = [{"path": "$.phone", "op": "regex", "expected": r"^1[3-9]\d{9}$"}]
        results = evaluate_assertions(body, assertions)
        assert len(results) == 1
        assert results[0]["passed"] is True

    def test_type_in_evaluate(self) -> None:
        body = {"count": 42}
        assertions = [{"path": "$.count", "op": "type", "expected": "integer"}]
        results = evaluate_assertions(body, assertions)
        assert results[0]["passed"] is True

    def test_length_eq_in_evaluate(self) -> None:
        body = {"items": [1, 2, 3]}
        assertions = [{"path": "$.items", "op": "length_eq", "expected": 3}]
        results = evaluate_assertions(body, assertions)
        assert results[0]["passed"] is True

    def test_schema_in_evaluate(self) -> None:
        pytest.importorskip("jsonschema")
        body = {"data": {"id": 1, "name": "test"}}
        assertions = [{
            "path": "$.data",
            "op": "schema",
            "expected": {"type": "object", "required": ["id", "name"]},
        }]
        results = evaluate_assertions(body, assertions)
        assert results[0]["passed"] is True


class TestSupportedOpsUpdated:

    def test_new_ops_in_supported(self) -> None:
        assert "regex" in SUPPORTED_OPS
        assert "length_eq" in SUPPORTED_OPS
        assert "type" in SUPPORTED_OPS
        assert "schema" in SUPPORTED_OPS

    def test_total_ops_count(self) -> None:
        assert len(SUPPORTED_OPS) == 13
