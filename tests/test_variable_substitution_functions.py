"""变量替换引擎函数调用测试。"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from postman_api_tester.utils.variable_substitution import (
    substitute_variables,
    _substitute_body,
    _substitute_params,
    extract_referenced_variables,
)


class TestFunctionSubstitution:

    def test_timestamp_replaced(self) -> None:
        result = substitute_variables("ts={{timestamp()}}", {})
        assert result.startswith("ts=")
        ts_value = result.split("=", 1)[1]
        assert ts_value.isdigit()
        assert len(ts_value) == 10

    def test_uuid_replaced(self) -> None:
        result = substitute_variables("id={{uuid()}}", {})
        assert "{{" not in result
        uuid_value = result.split("=", 1)[1]
        assert len(uuid_value) == 36

    def test_multiple_functions_in_text(self) -> None:
        result = substitute_variables("{{date()}}/{{timestamp()}}", {})
        parts = result.split("/")
        assert len(parts) == 2
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0])
        assert parts[1].isdigit()

    def test_function_and_variable_mixed(self) -> None:
        result = substitute_variables("{{date()}}-{{token}}", {"token": "abc123"})
        assert result.endswith("-abc123")
        assert "{{" not in result

    def test_unknown_function_preserved(self) -> None:
        result = substitute_variables("{{unknown_func()}}", {})
        assert result == "{{unknown_func()}}"

    def test_function_disabled_preserves_expression(self) -> None:
        with patch("postman_api_tester.utils.variable_substitution._is_functions_enabled", return_value=False):
            result = substitute_variables("{{timestamp()}}", {})
            assert result == "{{timestamp()}}"

    def test_empty_text(self) -> None:
        assert substitute_variables("", {}) == ""

    def test_no_functions_in_text(self) -> None:
        result = substitute_variables("hello {{name}}", {"name": "world"})
        assert result == "hello world"

    def test_base_url_not_replaced(self) -> None:
        result = substitute_variables("{{baseUrl}}/api", {})
        assert result == "{{baseUrl}}/api"

    def test_function_with_args_date_format(self) -> None:
        result = substitute_variables("{{date(%Y%m%d)}}", {})
        assert re.match(r"^\d{8}$", result)

    def test_function_with_args_random_int(self) -> None:
        result = substitute_variables("{{random_int(50,50)}}", {})
        assert result == "50"


class TestSubstituteBodyWithFunctions:

    def test_string_body_function_replaced(self) -> None:
        body = '{"ts": "{{timestamp()}}"}'
        result = _substitute_body(body, {})
        assert "{{" not in result
        assert "timestamp" not in result or result.index('"ts"') < result.index(":")

    def test_dict_body_function_replaced(self) -> None:
        body = {"key": "{{uuid()}}"}
        result = _substitute_body(body, {})
        assert "{{" not in str(result)

    def test_list_body_function_replaced(self) -> None:
        body = ["{{date()}}", "static"]
        result = _substitute_body(body, {})
        assert "{{" not in str(result)


class TestSubstituteParamsWithFunctions:

    def test_param_value_function_replaced(self) -> None:
        params = {"ts": "{{timestamp()}}"}
        result = _substitute_params(params, {})
        assert "{{" not in str(result)
        assert result["ts"].isdigit()

    def test_param_key_and_value_replaced(self) -> None:
        params = {"{{name}}": "{{uuid()}}"}
        result = _substitute_params(params, {"name": "key1"})
        assert "key1" in result


class TestExtractReferencedVariables:

    def test_extracts_simple_variables(self) -> None:
        result = extract_referenced_variables("hello {{name}} {{age}}")
        assert result == {"name", "age"}

    def test_excludes_functions(self) -> None:
        result = extract_referenced_variables("{{timestamp()}} {{name}}")
        assert result == {"name"}

    def test_empty_text(self) -> None:
        assert extract_referenced_variables("") == set()

    def test_no_variables(self) -> None:
        assert extract_referenced_variables("plain text") == set()
