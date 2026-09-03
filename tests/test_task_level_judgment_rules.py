"""v1.37.23 任务级自定义判定规则（judgment_config.custom_rules）单元测试。

覆盖：表单/payload 解析归一化、非法 JSON 抛错、executor 任务规则合并
（任务在前、与接口级规则 AND、关闭一级判定时一并跳过、无规则零回归）。
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from postman_api_tester.executor import PostmanTestExecutor
from postman_api_tester.handlers.job_routes import (
    _parse_judgment_config_from_form,
    _parse_judgment_config_from_payload,
)


def _mock_session(body: Any) -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    resp.headers = {"Content-Type": "application/json"}
    resp.request = MagicMock()
    resp.request.url = "https://api.example.com/test"
    session.get.return_value = resp
    return session


def _api(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": "查询",
        "method": "GET",
        "full_url": "https://api.example.com/test",
        "folder": "",
        "expected_status": 200,
    }
    base.update(overrides)
    return base


OK_MSG_BODY = {"message": "success", "data": {"status": "bad"}}
RULE_DATA_OK = [{"path": "$.data.status", "op": "eq", "expected": "ok"}]
RULE_DATA_BAD = [{"path": "$.data.status", "op": "eq", "expected": "bad"}]
_DISABLE_BOTH = {
    "enable_err_code_judgment": False,
    "enable_message_judgment": False,
}


class TestFormParsing:
    def test_valid_rules_json_normalized(self) -> None:
        raw = json.dumps(
            [
                {"path": "$.code", "op": "EQ", "expected": 1},
                {"op": "eq"},
                {"path": "$.x", "op": "bogus"},
            ]
        )
        config = _parse_judgment_config_from_form({"judgment_rules_json": raw})
        assert config == {
            "custom_rules": [{"path": "$.code", "op": "eq", "expected": 1}]
        }

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError):
            _parse_judgment_config_from_form({"judgment_rules_json": "not-json"})

    def test_absent_or_blank_keeps_none(self) -> None:
        assert _parse_judgment_config_from_form({}) is None
        assert _parse_judgment_config_from_form({"judgment_rules_json": "  "}) is None

    def test_rules_all_dirty_not_written(self) -> None:
        config = _parse_judgment_config_from_form(
            {"judgment_rules_json": json.dumps([{"path": "$.a", "op": "bogus"}])}
        )
        assert config is None

    def test_rules_combine_with_disable_flag(self) -> None:
        raw = json.dumps(RULE_DATA_OK)
        config = _parse_judgment_config_from_form(
            {"judgment_rules_json": raw, "judgment_disable_first_level": "1"}
        )
        assert config is not None
        assert config["custom_rules"] == RULE_DATA_OK
        assert config["enable_err_code_judgment"] is False
        assert config["enable_message_judgment"] is False


class TestPayloadParsing:
    def test_custom_rules_normalized(self) -> None:
        config = _parse_judgment_config_from_payload(
            {"judgment_config": {"custom_rules": [{"path": "$.a", "op": "NE"}]}}
        )
        assert config == {"custom_rules": [{"path": "$.a", "op": "ne", "expected": None}]}

    def test_dirty_custom_rules_dropped(self) -> None:
        assert (
            _parse_judgment_config_from_payload(
                {"judgment_config": {"custom_rules": "dirty"}}
            )
            is None
        )


class TestExecutorMerge:
    def test_task_rules_apply_without_item_rules(self) -> None:
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config={"custom_rules": RULE_DATA_OK},
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]

    def test_task_and_item_rules_both_and_semantics(self) -> None:
        # 任务规则通过、接口级失败 → FAILED；反之亦然
        exc = PostmanTestExecutor(
            _api(x_judgment_rules=RULE_DATA_OK),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config={"custom_rules": RULE_DATA_BAD},
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]

    def test_both_pass_then_assertions_run(self) -> None:
        exc = PostmanTestExecutor(
            _api(
                x_judgment_rules=RULE_DATA_BAD,
                x_assertions=[{"path": "$.message", "op": "eq", "expected": "nope"}],
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config={"custom_rules": RULE_DATA_BAD},
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "断言失败" in result["message"]
        assert result.get("assertion_results")

    def test_disable_first_level_skips_task_rules(self) -> None:
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session({"message": "session 已经过期"}),
            judgment_config={**_DISABLE_BOTH, "custom_rules": RULE_DATA_OK},
        )
        assert exc.execute_test()["status"] == "PASSED"

    def test_builtin_fail_not_mixed_with_task_rules(self) -> None:
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session({"message": "session 已经过期", "errCode": 100001}),
            judgment_config={"custom_rules": RULE_DATA_OK},
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "不满足成功条件" in result["message"]
        assert "自定义判定失败" not in result["message"]

    def test_no_task_rules_zero_regression(self) -> None:
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session({"message": "success"}),
            judgment_config={"custom_rules": []},
        )
        assert exc.execute_test()["status"] == "PASSED"
