"""可配置结果判定工具单元测试."""

import pytest
from postman_api_tester.utils.judgment_utils import (
    evaluate_result_judgment,
    parse_success_list,
    resolve_judgment_params,
)


class TestParseSuccessList:
    """parse_success_list 测试."""

    def test_empty_string(self) -> None:
        assert parse_success_list("") == frozenset()

    def test_whitespace_only(self) -> None:
        assert parse_success_list("   ") == frozenset()

    def test_single_value(self) -> None:
        assert parse_success_list("0") == frozenset({"0"})

    def test_multiple_values(self) -> None:
        result = parse_success_list("0,200,success")
        assert result == frozenset({"0", "200", "success"})

    def test_values_with_spaces(self) -> None:
        result = parse_success_list(" 0 , 200 , Success ")
        assert result == frozenset({"0", "200", "success"})

    def test_trailing_comma_includes_empty(self) -> None:
        result = parse_success_list("0,200,")
        assert "" in result
        assert "0" in result
        assert "200" in result

    def test_case_insensitive(self) -> None:
        result = parse_success_list("Success,OK")
        assert result == frozenset({"success", "ok"})


class TestEvaluateResultJudgment:
    """evaluate_result_judgment 测试."""

    def test_default_backward_compatible_pass(self) -> None:
        """默认配置下向后兼容：状态码 200 + message 为空 → PASSED."""
        passed, reason = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="",
        )
        assert passed is True
        assert reason == ""

    def test_default_backward_compatible_success_message(self) -> None:
        """默认配置下：message 为 success → PASSED."""
        passed, reason = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="success",
        )
        assert passed is True
        assert reason == ""

    def test_default_backward_compatible_fail_status(self) -> None:
        """默认配置下：状态码不匹配 → FAILED."""
        passed, reason = evaluate_result_judgment(
            status_code=500,
            expected_status=200,
            err_code="0",
            response_message="",
        )
        assert passed is False
        assert "期望状态码: 200" in reason
        assert "实际: 500" in reason

    def test_default_backward_compatible_fail_message(self) -> None:
        """默认配置下：message 不为空且不为 success → FAILED."""
        passed, reason = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="系统错误",
        )
        assert passed is False
        assert "message" in reason

    def test_err_code_judgment_disabled_by_default(self) -> None:
        """errCode 判定默认关闭，即使 errCode 不匹配也 PASSED."""
        passed, _ = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="9999",
            response_message="",
        )
        assert passed is True

    def test_err_code_judgment_enabled_pass(self) -> None:
        """errCode 判定开启：errCode 在成功列表中 → PASSED."""
        passed, reason = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="",
            enable_err_code_judgment=True,
            success_err_codes=frozenset({"0"}),
        )
        assert passed is True
        assert reason == ""

    def test_err_code_judgment_enabled_fail(self) -> None:
        """errCode 判定开启：errCode 不在成功列表中 → FAILED."""
        passed, reason = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="1001",
            response_message="",
            enable_err_code_judgment=True,
            success_err_codes=frozenset({"0", "200"}),
        )
        assert passed is False
        assert "errCode" in reason
        assert "1001" in reason

    def test_message_judgment_disabled(self) -> None:
        """message 判定关闭：即使 message 不匹配也 PASSED."""
        passed, _ = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="操作失败",
            enable_message_judgment=False,
        )
        assert passed is True

    def test_message_custom_list_pass(self) -> None:
        """自定义 message 成功列表：匹配 → PASSED."""
        passed, _ = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="ok",
            success_messages=frozenset({"success", "ok", "操作成功"}),
        )
        assert passed is True

    def test_message_custom_list_fail(self) -> None:
        """自定义 message 成功列表：不匹配 → FAILED."""
        passed, reason = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="系统错误",
            success_messages=frozenset({"success", "ok"}),
        )
        assert passed is False
        assert "message" in reason

    def test_multi_dimension_all_fail(self) -> None:
        """多维度全部不通过：失败原因用分号拼接."""
        passed, reason = evaluate_result_judgment(
            status_code=500,
            expected_status=200,
            err_code="9999",
            response_message="系统错误",
            enable_err_code_judgment=True,
            success_err_codes=frozenset({"0"}),
            success_messages=frozenset({"success"}),
        )
        assert passed is False
        assert "期望状态码" in reason
        assert "errCode" in reason
        assert "message" in reason
        assert "; " in reason

    def test_empty_message_always_pass(self) -> None:
        """message 为空字符串时，无论配置如何都通过 message 维度."""
        passed, _ = evaluate_result_judgment(
            status_code=200,
            expected_status=200,
            err_code="0",
            response_message="",
            success_messages=frozenset({"ok"}),
        )
        assert passed is True


class TestResolveJudgmentParams:
    """resolve_judgment_params 优先级测试."""

    def test_global_defaults(self) -> None:
        """无覆盖时使用全局配置."""
        result = resolve_judgment_params(
            global_enable_err_code=True,
            global_success_err_codes=frozenset({"0"}),
            global_enable_message=True,
            global_success_messages=frozenset({"success"}),
        )
        assert result["enable_err_code_judgment"] is True
        assert result["success_err_codes"] == frozenset({"0"})
        assert result["enable_message_judgment"] is True
        assert result["success_messages"] == frozenset({"success"})

    def test_item_overrides_global(self) -> None:
        """集合接口级覆盖全局配置."""
        result = resolve_judgment_params(
            global_enable_err_code=False,
            global_success_err_codes=frozenset({"0"}),
            global_enable_message=True,
            global_success_messages=frozenset({"success"}),
            item_x_enable_err_code=True,
            item_x_success_err_codes="0,200",
        )
        assert result["enable_err_code_judgment"] is True
        assert result["success_err_codes"] == frozenset({"0", "200"})

    def test_task_overrides_item_and_global(self) -> None:
        """任务级覆盖集合接口级和全局配置."""
        result = resolve_judgment_params(
            global_enable_err_code=False,
            global_success_err_codes=frozenset({"0"}),
            global_enable_message=True,
            global_success_messages=frozenset({"success"}),
            item_x_enable_err_code=True,
            item_x_success_err_codes="0,200",
            task_enable_err_code=True,
            task_success_err_codes="0,200,ok",
        )
        assert result["enable_err_code_judgment"] is True
        assert result["success_err_codes"] == frozenset({"0", "200", "ok"})

    def test_task_can_disable(self) -> None:
        """任务级可以关闭判定."""
        result = resolve_judgment_params(
            global_enable_err_code=True,
            global_success_err_codes=frozenset({"0"}),
            global_enable_message=True,
            global_success_messages=frozenset({"success"}),
            task_enable_err_code=False,
            task_enable_message=False,
        )
        assert result["enable_err_code_judgment"] is False
        assert result["enable_message_judgment"] is False

    def test_item_empty_string_does_not_override(self) -> None:
        """集合接口级空字符串不覆盖全局."""
        result = resolve_judgment_params(
            global_enable_err_code=True,
            global_success_err_codes=frozenset({"0"}),
            global_enable_message=True,
            global_success_messages=frozenset({"success"}),
            item_x_success_err_codes="   ",
        )
        assert result["success_err_codes"] == frozenset({"0"})
