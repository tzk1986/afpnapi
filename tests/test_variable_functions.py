"""变量函数单元测试。"""

from __future__ import annotations

import re
import time
from unittest.mock import patch

import pytest

from postman_api_tester.utils.variable_functions import (
    _BUILT_IN_FUNCTIONS,
    evaluate_function,
    get_registered_names,
    register,
)


class TestBuiltInFunctions:

    def test_timestamp_returns_integer_string(self) -> None:
        result = _BUILT_IN_FUNCTIONS["timestamp"]()
        assert result.isdigit()
        assert len(result) == 10

    def test_timestamp_ms_returns_integer_string(self) -> None:
        result = _BUILT_IN_FUNCTIONS["timestamp_ms"]()
        assert result.isdigit()
        assert len(result) == 13

    def test_uuid_format(self) -> None:
        result = _BUILT_IN_FUNCTIONS["uuid"]()
        pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        assert pattern.match(result) is not None

    def test_uuid_uniqueness(self) -> None:
        results = {_BUILT_IN_FUNCTIONS["uuid"]() for _ in range(100)}
        assert len(results) == 100

    def test_random_int_default_range(self) -> None:
        result = _BUILT_IN_FUNCTIONS["random_int"]()
        value = int(result)
        assert 0 <= value <= 100

    def test_random_int_custom_range(self) -> None:
        result = _BUILT_IN_FUNCTIONS["random_int"]("10", "20")
        value = int(result)
        assert 10 <= value <= 20

    def test_random_int_same_value(self) -> None:
        result = _BUILT_IN_FUNCTIONS["random_int"]("5", "5")
        assert result == "5"

    def test_date_default_format(self) -> None:
        result = _BUILT_IN_FUNCTIONS["date"]()
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        assert pattern.match(result) is not None

    def test_date_custom_format(self) -> None:
        result = _BUILT_IN_FUNCTIONS["date"]("%Y%m%d")
        pattern = re.compile(r"^\d{8}$")
        assert pattern.match(result) is not None

    def test_datetime_default_format(self) -> None:
        result = _BUILT_IN_FUNCTIONS["datetime"]()
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        assert pattern.match(result) is not None

    def test_datetime_custom_format(self) -> None:
        result = _BUILT_IN_FUNCTIONS["datetime"]("%H:%M")
        pattern = re.compile(r"^\d{2}:\d{2}$")
        assert pattern.match(result) is not None


class TestEvaluateFunction:

    def test_known_function_returns_result(self) -> None:
        result = evaluate_function("timestamp", "")
        assert result is not None
        assert result.isdigit()

    def test_unknown_function_returns_none(self) -> None:
        result = evaluate_function("nonexistent_func", "")
        assert result is None

    def test_function_with_args(self) -> None:
        result = evaluate_function("random_int", "1,10")
        assert result is not None
        assert 1 <= int(result) <= 10

    def test_function_invalid_args_returns_empty(self) -> None:
        result = evaluate_function("random_int", "abc,def")
        assert result == ""

    def test_timestamp_ms_args_cause_empty(self) -> None:
        result = evaluate_function("timestamp_ms", "ignored")
        assert result == ""


class TestRegister:

    def test_register_new_function(self) -> None:
        @register("test_func_unique_123")
        def _test_fn() -> str:
            return "test_result"

        assert "test_func_unique_123" in get_registered_names()
        assert evaluate_function("test_func_unique_123", "") == "test_result"

        del _BUILT_IN_FUNCTIONS["test_func_unique_123"]


class TestGetRegisteredNames:

    def test_contains_all_builtins(self) -> None:
        names = get_registered_names()
        assert "timestamp" in names
        assert "timestamp_ms" in names
        assert "uuid" in names
        assert "random_int" in names
        assert "date" in names
        assert "datetime" in names

    def test_returns_list(self) -> None:
        names = get_registered_names()
        assert isinstance(names, list)
        assert len(names) >= 6
