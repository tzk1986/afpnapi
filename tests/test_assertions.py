"""Tests for postman_api_tester.assertions module."""

import pytest

from postman_api_tester.assertions import (
    evaluate_assertions,
    _compare,
    _check_type,
    SUPPORTED_OPS,
)


class TestEvaluateAssertions:
    """Tests for evaluate_assertions function."""

    def test_empty_assertions(self):
        """Test empty assertions list returns empty results."""
        result = evaluate_assertions({"data": "value"}, [])
        assert result == []

    def test_exists_operator_pass(self):
        """Test exists operator with existing path."""
        assertions = [{"path": "$.data", "op": "exists"}]
        response = {"data": "value"}

        result = evaluate_assertions(response, assertions)

        assert len(result) == 1
        assert result[0]["passed"] is True
        assert result[0]["op"] == "exists"

    def test_exists_operator_fail(self):
        """Test exists operator with missing path."""
        assertions = [{"path": "$.missing", "op": "exists"}]
        response = {"data": "value"}

        result = evaluate_assertions(response, assertions)

        assert len(result) == 1
        assert result[0]["passed"] is False
        assert "不存在" in result[0]["message"]

    def test_not_exists_operator_pass(self):
        """Test not_exists operator with missing path."""
        assertions = [{"path": "$.missing", "op": "not_exists"}]
        response = {"data": "value"}

        result = evaluate_assertions(response, assertions)

        assert len(result) == 1
        assert result[0]["passed"] is True

    def test_not_exists_operator_fail(self):
        """Test not_exists operator with existing path."""
        assertions = [{"path": "$.data", "op": "not_exists"}]
        response = {"data": "value"}

        result = evaluate_assertions(response, assertions)

        assert len(result) == 1
        assert result[0]["passed"] is False

    def test_eq_operator(self):
        """Test equality operator."""
        assertions = [{"path": "$.count", "op": "eq", "expected": 10}]
        response = {"count": 10}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_ne_operator(self):
        """Test not-equal operator."""
        assertions = [{"path": "$.status", "op": "ne", "expected": "error"}]
        response = {"status": "success"}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_gt_operator(self):
        """Test greater-than operator."""
        assertions = [{"path": "$.score", "op": "gt", "expected": 50}]
        response = {"score": 75}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_contains_operator(self):
        """Test contains operator."""
        assertions = [{"path": "$.message", "op": "contains", "expected": "success"}]
        response = {"message": "Operation successful"}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_regex_operator_pass(self):
        """Test regex operator with matching pattern."""
        assertions = [{"path": "$.email", "op": "regex", "expected": r"^[\w.]+@[\w.]+\.\w+$"}]
        response = {"email": "test@example.com"}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_regex_operator_fail(self):
        """Test regex operator with non-matching pattern."""
        assertions = [{"path": "$.email", "op": "regex", "expected": r"^[\w.]+@[\w.]+\.\w+$"}]
        response = {"email": "invalid-email"}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is False
        assert "不匹配正则" in result[0]["message"]

    def test_length_eq_operator(self):
        """Test length_eq operator."""
        assertions = [{"path": "$.items", "op": "length_eq", "expected": 3}]
        response = {"items": [1, 2, 3]}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_type_operator_string(self):
        """Test type operator with string."""
        assertions = [{"path": "$.name", "op": "type", "expected": "string"}]
        response = {"name": "John"}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_type_operator_integer(self):
        """Test type operator with integer."""
        assertions = [{"path": "$.age", "op": "type", "expected": "integer"}]
        response = {"age": 30}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_type_operator_null(self):
        """Test type operator with null."""
        assertions = [{"path": "$.deleted_at", "op": "type", "expected": "null"}]
        response = {"deleted_at": None}

        result = evaluate_assertions(response, assertions)

        assert result[0]["passed"] is True

    def test_multiple_assertions(self):
        """Test multiple assertions."""
        assertions = [
            {"path": "$.status", "op": "eq", "expected": "ok"},
            {"path": "$.count", "op": "gt", "expected": 0},
            {"path": "$.data", "op": "exists"},
        ]
        response = {"status": "ok", "count": 5, "data": []}

        result = evaluate_assertions(response, assertions)

        assert len(result) == 3
        assert all(r["passed"] for r in result)

    def test_assertion_exception_handling(self):
        """Test assertion with invalid path."""
        assertions = [{"path": "$[invalid", "op": "exists"}]
        response = {"data": "value"}

        result = evaluate_assertions(response, assertions)

        assert len(result) == 1
        assert result[0]["passed"] is False
        assert "断言异常" in result[0]["message"]


class TestCompare:
    """Tests for _compare function."""

    def test_eq_true(self):
        """Test equality comparison."""
        passed, message = _compare(10, "eq", 10)
        assert passed is True
        assert message == ""

    def test_eq_false(self):
        """Test inequality comparison."""
        passed, message = _compare(10, "eq", 20)
        assert passed is False

    def test_unsupported_operator(self):
        """Test unsupported operator."""
        passed, message = _compare(10, "invalid_op", 10)
        assert passed is False
        assert "不支持的操作符" in message

    def test_comparison_exception(self):
        """Test comparison with incompatible types."""
        passed, message = _compare("text", "gt", 10)
        assert passed is False
        assert "比较异常" in message


class TestCheckType:
    """Tests for _check_type function."""

    def test_string_type(self):
        """Test string type check."""
        passed, message = _check_type("hello", "string")
        assert passed is True

    def test_integer_type(self):
        """Test integer type check."""
        passed, message = _check_type(42, "integer")
        assert passed is True

    def test_integer_rejects_bool(self):
        """Test integer type rejects boolean."""
        passed, message = _check_type(True, "integer")
        assert passed is False

    def test_number_type(self):
        """Test number type check."""
        passed, message = _check_type(3.14, "number")
        assert passed is True

    def test_number_rejects_bool(self):
        """Test number type rejects boolean."""
        passed, message = _check_type(False, "number")
        assert passed is False

    def test_boolean_type(self):
        """Test boolean type check."""
        passed, message = _check_type(True, "boolean")
        assert passed is True

    def test_array_type(self):
        """Test array type check."""
        passed, message = _check_type([1, 2, 3], "array")
        assert passed is True

    def test_object_type(self):
        """Test object type check."""
        passed, message = _check_type({"key": "value"}, "object")
        assert passed is True

    def test_null_type(self):
        """Test null type check."""
        passed, message = _check_type(None, "null")
        assert passed is True

    def test_null_type_fail(self):
        """Test null type check with non-null."""
        passed, message = _check_type("value", "null")
        assert passed is False
        assert "期望 null" in message

    def test_unknown_type(self):
        """Test unknown type."""
        passed, message = _check_type("value", "unknown_type")
        assert passed is False
        assert "未知类型" in message

    def test_type_mismatch_message(self):
        """Test type mismatch error message."""
        passed, message = _check_type(42, "string")
        assert passed is False
        assert "期望 string" in message
        assert "int" in message


class TestSupportedOps:
    """Tests for SUPPORTED_OPS."""

    def test_supported_ops_contains_13_operators(self):
        """Test that 13 operators are supported."""
        assert len(SUPPORTED_OPS) == 13

    def test_supported_ops_include_common_operators(self):
        """Test common operators are included."""
        expected_ops = {"eq", "ne", "gt", "lt", "gte", "lte", "exists", "not_exists"}
        assert expected_ops.issubset(SUPPORTED_OPS)
