"""变量替换引擎单元测试."""

import pytest
from postman_api_tester.parser import ApiConfig
from postman_api_tester.utils.variable_substitution import (
    api_references_variables,
    extract_referenced_variables,
    substitute_in_api_config,
    substitute_variables,
)


class TestSubstituteVariables:
    """substitute_variables() 基础替换测试."""

    def test_basic_substitution(self) -> None:
        assert substitute_variables("Hello {{name}}", {"name": "World"}) == "Hello World"

    def test_multiple_variables(self) -> None:
        result = substitute_variables(
            "{{greeting}} {{name}}!",
            {"greeting": "Hi", "name": "Alice"},
        )
        assert result == "Hi Alice!"

    def test_unmatched_variable_preserved(self) -> None:
        result = substitute_variables("{{known}} {{unknown}}", {"known": "yes"})
        assert result == "yes {{unknown}}"

    def test_no_recursion(self) -> None:
        result = substitute_variables("{{a}}", {"a": "{{b}}"})
        assert result == "{{b}}"

    def test_base_url_excluded(self) -> None:
        result = substitute_variables(
            "{{baseUrl}}/api/{{path}}",
            {"baseUrl": "http://evil.com", "path": "users"},
        )
        assert result == "{{baseUrl}}/api/users"

    def test_base_url_underscore_excluded(self) -> None:
        result = substitute_variables(
            "{{base_url}}/items/{{id}}",
            {"base_url": "http://evil.com", "id": "42"},
        )
        assert result == "{{base_url}}/items/42"

    def test_empty_text(self) -> None:
        assert substitute_variables("", {"x": "y"}) == ""

    def test_empty_variables(self) -> None:
        assert substitute_variables("{{x}}", {}) == "{{x}}"

    def test_none_text(self) -> None:
        assert substitute_variables(None, {"x": "y"}) is None  # type: ignore[arg-type]

    def test_numeric_value_coerced(self) -> None:
        result = substitute_variables("count={{n}}", {"n": 42})  # type: ignore[dict-item]
        assert result == "count=42"

    def test_adjacent_variables(self) -> None:
        result = substitute_variables("{{a}}{{b}}", {"a": "X", "b": "Y"})
        assert result == "XY"

    def test_repeated_same_variable(self) -> None:
        result = substitute_variables("{{x}} and {{x}}", {"x": "val"})
        assert result == "val and val"


class TestSubstituteInApiConfig:
    """substitute_in_api_config() 集成替换测试."""

    def test_url_substitution(self) -> None:
        api = ApiConfig(url="/api/users/{{userId}}", method="GET", name="test")
        result = substitute_in_api_config(api, {"userId": "123"})
        assert result["url"] == "/api/users/123"

    def test_full_url_substitution(self) -> None:
        api = ApiConfig(
            url="/api/{{resource}}",
            full_url="http://example.com/api/{{resource}}",
            method="GET",
            name="test",
        )
        result = substitute_in_api_config(api, {"resource": "orders"})
        assert result["url"] == "/api/orders"
        assert result["full_url"] == "http://example.com/api/orders"

    def test_headers_substitution(self) -> None:
        api = ApiConfig(
            url="/api/test",
            method="GET",
            name="test",
            headers={"Authorization": "Bearer {{token}}", "X-Custom": "{{value}}"},
        )
        result = substitute_in_api_config(api, {"token": "abc", "value": "xyz"})
        assert result["headers"] == {"Authorization": "Bearer abc", "X-Custom": "xyz"}

    def test_params_substitution(self) -> None:
        api = ApiConfig(
            url="/api/test",
            method="GET",
            name="test",
            params={"id": "{{userId}}", "status": "active"},
        )
        result = substitute_in_api_config(api, {"userId": "456"})
        assert result["params"] == {"id": "456", "status": "active"}

    def test_body_string_substitution(self) -> None:
        api = ApiConfig(
            url="/api/test",
            method="POST",
            name="test",
            body='{"name":"{{name}}","qty":{{qty}}}',
        )
        result = substitute_in_api_config(api, {"name": "Widget", "qty": "10"})
        assert result["body"] == '{"name":"Widget","qty":10}'

    def test_body_dict_substitution(self) -> None:
        api = ApiConfig(
            url="/api/test",
            method="POST",
            name="test",
            body={"name": "{{name}}", "count": 5, "nested": {"id": "{{id}}"}},
        )
        result = substitute_in_api_config(api, {"name": "Test", "id": "99"})
        body = result["body"]
        assert isinstance(body, dict)
        assert body["name"] == "Test"
        assert body["count"] == 5
        assert body["nested"]["id"] == "99"

    def test_body_list_substitution(self) -> None:
        api = ApiConfig(
            url="/api/test",
            method="POST",
            name="test",
            body=["{{a}}", "static", "{{b}}"],
        )
        result = substitute_in_api_config(api, {"a": "X", "b": "Y"})
        assert result["body"] == ["X", "static", "Y"]

    def test_original_not_mutated(self) -> None:
        api = ApiConfig(url="/api/{{id}}", method="GET", name="test")
        _ = substitute_in_api_config(api, {"id": "1"})
        assert api["url"] == "/api/{{id}}"

    def test_empty_variables_returns_copy(self) -> None:
        api = ApiConfig(url="/api/test", method="GET", name="test")
        result = substitute_in_api_config(api, {})
        assert result["url"] == "/api/test"
        assert result is not api

    def test_none_body_preserved(self) -> None:
        api = ApiConfig(url="/api/test", method="GET", name="test", body=None)
        result = substitute_in_api_config(api, {"x": "y"})
        assert result.get("body") is None


class TestExtractReferencedVariables:
    """extract_referenced_variables() 测试."""

    def test_extract_basic(self) -> None:
        assert extract_referenced_variables("{{a}} {{b}}") == {"a", "b"}

    def test_extract_empty(self) -> None:
        assert extract_referenced_variables("no vars") == set()

    def test_extract_repeated(self) -> None:
        assert extract_referenced_variables("{{a}} {{a}}") == {"a"}

    def test_extract_none(self) -> None:
        assert extract_referenced_variables("") == set()


class TestApiReferencesVariables:
    """api_references_variables() 检测测试."""

    def test_url_match(self) -> None:
        api = ApiConfig(url="/api/{{orderId}}", method="GET", name="test")
        assert api_references_variables(api, {"orderId"}) is True

    def test_no_match(self) -> None:
        api = ApiConfig(url="/api/users", method="GET", name="test")
        assert api_references_variables(api, {"orderId"}) is False

    def test_base_url_not_counted(self) -> None:
        api = ApiConfig(url="{{baseUrl}}/api", method="GET", name="test")
        assert api_references_variables(api, {"baseUrl"}) is False

    def test_header_match(self) -> None:
        api = ApiConfig(
            url="/api",
            method="GET",
            name="test",
            headers={"Authorization": "Bearer {{token}}"},
        )
        assert api_references_variables(api, {"token"}) is True

    def test_body_string_match(self) -> None:
        api = ApiConfig(
            url="/api",
            method="POST",
            name="test",
            body='{"id": "{{orderId}}"}',
        )
        assert api_references_variables(api, {"orderId"}) is True

    def test_body_dict_match(self) -> None:
        api = ApiConfig(
            url="/api",
            method="POST",
            name="test",
            body={"nested": {"deep": "{{value}}"}},
        )
        assert api_references_variables(api, {"value"}) is True

    def test_empty_variable_set(self) -> None:
        api = ApiConfig(url="/api/{{x}}", method="GET", name="test")
        assert api_references_variables(api, set()) is False
