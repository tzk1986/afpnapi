"""VariableContext 单元测试."""

import pytest
from postman_api_tester.core.variable_context import VariableContext


class TestVariableContext:
    """VariableContext 生命周期测试."""

    def test_initial_empty(self) -> None:
        ctx = VariableContext()
        assert ctx.variables == {}

    def test_initial_variables(self) -> None:
        ctx = VariableContext({"token": "abc"})
        assert ctx.get("token") == "abc"

    def test_set_and_get(self) -> None:
        ctx = VariableContext()
        ctx.set("key", "value")
        assert ctx.get("key") == "value"

    def test_get_default(self) -> None:
        ctx = VariableContext()
        assert ctx.get("missing", "default") == "default"

    def test_variables_returns_copy(self) -> None:
        ctx = VariableContext({"x": "1"})
        copy = ctx.variables
        copy["x"] = "2"
        assert ctx.get("x") == "1"

    def test_update_from_extract_success(self) -> None:
        ctx = VariableContext()
        data = {"data": {"token": "abc"}}
        extracted = ctx.update_from_extract(
            {"token": "$.data.token"},
            data,
            {},
        )
        assert extracted == {"token": "abc"}
        assert ctx.get("token") == "abc"

    def test_update_from_extract_partial_failure(self) -> None:
        ctx = VariableContext({"existing": "keep"})
        data = {"data": {"token": "abc"}}
        extracted = ctx.update_from_extract(
            {"token": "$.data.token", "missing": "$.data.missing"},
            data,
            {},
        )
        assert extracted == {"token": "abc"}
        assert ctx.get("existing") == "keep"
        assert ctx.get("missing") == ""

    def test_update_overwrites_existing(self) -> None:
        ctx = VariableContext({"token": "old"})
        ctx.update_from_extract(
            {"token": "$.data.token"},
            {"data": {"token": "new"}},
            {},
        )
        assert ctx.get("token") == "new"

    def test_failed_extract_preserves_existing(self) -> None:
        ctx = VariableContext({"token": "old"})
        ctx.update_from_extract(
            {"token": "$.data.missing"},
            {"data": {}},
            {},
        )
        assert ctx.get("token") == "old"
