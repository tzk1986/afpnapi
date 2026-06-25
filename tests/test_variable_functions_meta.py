"""变量函数元数据测试。"""

from __future__ import annotations

from postman_api_tester.utils.variable_functions import get_function_metadata


class TestGetFunctionMetadata:

    def test_returns_list(self) -> None:
        result = get_function_metadata()
        assert isinstance(result, list)

    def test_twelve_functions(self) -> None:
        result = get_function_metadata()
        assert len(result) == 12

    def test_each_has_required_keys(self) -> None:
        result = get_function_metadata()
        required_keys = {"name", "syntax", "params", "description", "example"}
        for fn in result:
            assert required_keys.issubset(fn.keys()), f"missing keys in {fn}"

    def test_timestamp_included(self) -> None:
        result = get_function_metadata()
        names = [fn["name"] for fn in result]
        assert "timestamp" in names

    def test_uuid_included(self) -> None:
        result = get_function_metadata()
        names = [fn["name"] for fn in result]
        assert "uuid" in names

    def test_random_int_has_params(self) -> None:
        result = get_function_metadata()
        random_int = next(fn for fn in result if fn["name"] == "random_int")
        assert "low" in random_int["params"]
        assert "high" in random_int["params"]

    def test_date_has_format_param(self) -> None:
        result = get_function_metadata()
        date_fn = next(fn for fn in result if fn["name"] == "date")
        assert "fmt" in date_fn["params"]

    def test_syntax_contains_braces(self) -> None:
        result = get_function_metadata()
        for fn in result:
            assert "{{" in fn["syntax"]
            assert "}}" in fn["syntax"]
