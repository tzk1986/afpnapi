"""report_server_utils 模块单元测试。

覆盖 _coerce_int、build_exclusion_key、normalize_exclusion_key、
result_exclusion_key、normalize_manual_exclusions、to_bool。
"""

from typing import Any, Dict, List

import pytest

from postman_api_tester.report_server_utils import (
	_coerce_int,
	build_exclusion_key,
	normalize_exclusion_key,
	normalize_manual_exclusions,
	result_exclusion_key,
	to_bool,
)


class TestCoerceInt:
	"""_coerce_int() 整数强转测试。"""

	def test_int_passthrough(self) -> None:
		assert _coerce_int(42) == 42

	def test_string_int(self) -> None:
		assert _coerce_int("100") == 100

	def test_none_returns_none(self) -> None:
		assert _coerce_int(None) is None

	def test_invalid_string_returns_none(self) -> None:
		assert _coerce_int("abc") is None

	def test_float_string_returns_none(self) -> None:
		assert _coerce_int("3.14") is None

	def test_zero(self) -> None:
		assert _coerce_int(0) == 0

	def test_negative(self) -> None:
		assert _coerce_int(-5) == -5

	def test_bool_true_is_1(self) -> None:
		assert _coerce_int(True) == 1

	def test_bool_false_is_0(self) -> None:
		assert _coerce_int(False) == 0


class TestBuildExclusionKey:
	"""build_exclusion_key() 排除键构建测试。"""

	def test_basic_key(self) -> None:
		result = build_exclusion_key("Auth", "Login", "POST", "/api/login")
		assert result == "Auth|Login|POST|/api/login"

	def test_method_uppercased(self) -> None:
		result = build_exclusion_key("", "Test", "get", "/api/test")
		assert "GET" in result

	def test_none_values_become_empty(self) -> None:
		result = build_exclusion_key(None, None, None, None)
		assert result == "|||"

	def test_empty_strings(self) -> None:
		result = build_exclusion_key("", "", "", "")
		assert result == "|||"

	def test_whitespace_stripped(self) -> None:
		result = build_exclusion_key(" Auth ", " Login ", " POST ", " /api ")
		assert result == "Auth|Login|POST|/api"


class TestNormalizeExclusionKey:
	"""normalize_exclusion_key() 排除键规范化测试。"""

	def test_pipe_separated_key(self) -> None:
		result = normalize_exclusion_key("Auth|Login|POST|/api/login")
		assert result == "Auth|Login|POST|/api/login"

	def test_no_pipe_returns_as_is(self) -> None:
		result = normalize_exclusion_key("simple_key")
		assert result == "simple_key"

	def test_empty_returns_empty(self) -> None:
		assert normalize_exclusion_key("") == ""

	def test_none_returns_empty(self) -> None:
		assert normalize_exclusion_key(None) == ""

	def test_url_with_pipe_preserved(self) -> None:
		result = normalize_exclusion_key("F|N|GET|/api?a=1|b=2")
		assert result == "F|N|GET|/api?a=1|b=2"

	def test_too_few_parts_returns_as_is(self) -> None:
		result = normalize_exclusion_key("A|B|C")
		assert result == "A|B|C"


class TestResultExclusionKey:
	"""result_exclusion_key() 结果排除键测试。"""

	def test_from_result_dict(self) -> None:
		result = result_exclusion_key({
			"folder": "Auth",
			"name": "Login",
			"method": "POST",
			"url": "/api/login",
		})
		assert result == "Auth|Login|POST|/api/login"

	def test_missing_fields_default_empty(self) -> None:
		result = result_exclusion_key({})
		assert result == "|||"

	def test_partial_fields(self) -> None:
		result = result_exclusion_key({"name": "Test", "method": "GET"})
		assert result == "|Test|GET|"


class TestNormalizeManualExclusions:
	"""normalize_manual_exclusions() 手动排除列表规范化测试。"""

	def test_basic_list(self) -> None:
		result = normalize_manual_exclusions(["A|B|POST|/api", "C|D|GET|/test"])
		assert len(result) == 2

	def test_dedup(self) -> None:
		result = normalize_manual_exclusions(["A|B|POST|/api", "A|B|POST|/api"])
		assert len(result) == 1

	def test_non_list_returns_empty(self) -> None:
		assert normalize_manual_exclusions("string") == []
		assert normalize_manual_exclusions(None) == []
		assert normalize_manual_exclusions(42) == []

	def test_empty_values_skipped(self) -> None:
		result = normalize_manual_exclusions(["", "  ", "A|B|POST|/api"])
		assert len(result) == 1

	def test_normalizes_each_entry(self) -> None:
		result = normalize_manual_exclusions([" Auth | Login | post | /api "])
		assert result == ["Auth|Login|POST|/api"]


class TestToBool:
	"""to_bool() 布尔值转换测试。"""

	def test_true_strings(self) -> None:
		for val in ["1", "true", "True", "TRUE", "yes", "Yes", "y", "Y", "on", "ON"]:
			assert to_bool(val) is True, f"Expected True for {val!r}"

	def test_false_strings(self) -> None:
		for val in ["0", "false", "False", "FALSE", "no", "No", "n", "N", "off", "OFF"]:
			assert to_bool(val) is False, f"Expected False for {val!r}"

	def test_none_returns_default(self) -> None:
		assert to_bool(None) is False
		assert to_bool(None, default=True) is True

	def test_bool_passthrough(self) -> None:
		assert to_bool(True) is True
		assert to_bool(False) is False

	def test_unknown_returns_default(self) -> None:
		assert to_bool("maybe") is False
		assert to_bool("maybe", default=True) is True

	def test_int_values(self) -> None:
		assert to_bool(1) is True
		assert to_bool(0) is False

	def test_whitespace_stripped(self) -> None:
		assert to_bool("  true  ") is True
		assert to_bool("  false  ") is False
