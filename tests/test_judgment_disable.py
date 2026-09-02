"""v1.37.17 任务级关闭一级判定（方案 A）单元测试。

覆盖：
- W-5: job_routes 表单/payload 判定参数解析（disable 开关展开、bool 脏值防御、现状兼容）；
- W-6: executor 端到端钉桩——judgment_config 双 False 时一级判定短路解除、
  断言接管成败（复现"session 过期 + 断言"调试场景）。
"""

from typing import Any, Dict
from unittest.mock import MagicMock

from postman_api_tester.executor import PostmanTestExecutor
from postman_api_tester.handlers.job_routes import (
    _parse_judgment_config_from_form,
    _parse_judgment_config_from_payload,
)


# ---------------------------------------------------------------------------
# W-5: 表单解析
# ---------------------------------------------------------------------------


class TestParseJudgmentConfigFromForm:
    def test_empty_form_returns_none(self) -> None:
        assert _parse_judgment_config_from_form({}) is None

    def test_disable_flag_expands_to_two_false(self) -> None:
        config = _parse_judgment_config_from_form(
            {"judgment_disable_first_level": "1"}
        )
        assert config == {
            "enable_err_code_judgment": False,
            "enable_message_judgment": False,
        }

    def test_disable_flag_value_not_one_ignored(self) -> None:
        assert _parse_judgment_config_from_form(
            {"judgment_disable_first_level": "0"}
        ) is None
        assert _parse_judgment_config_from_form(
            {"judgment_disable_first_level": "true"}
        ) is None
        assert _parse_judgment_config_from_form(
            {"judgment_disable_first_level": ""}
        ) is None

    def test_disable_flag_merges_with_success_keys(self) -> None:
        config = _parse_judgment_config_from_form(
            {
                "judgment_disable_first_level": "1",
                "judgment_success_err_codes": " 0,200 ",
            }
        )
        assert config == {
            "success_err_codes": "0,200",
            "enable_err_code_judgment": False,
            "enable_message_judgment": False,
        }

    def test_success_keys_only_keeps_legacy_shape(self) -> None:
        config = _parse_judgment_config_from_form(
            {"judgment_success_messages": "ok"}
        )
        assert config == {"success_messages": "ok"}


# ---------------------------------------------------------------------------
# W-5: payload 解析
# ---------------------------------------------------------------------------


class TestParseJudgmentConfigFromPayload:
    def test_missing_or_empty_returns_none(self) -> None:
        assert _parse_judgment_config_from_payload({}) is None
        assert _parse_judgment_config_from_payload({"judgment_config": {}}) is None
        assert _parse_judgment_config_from_payload({"judgment_config": "x"}) is None

    def test_explicit_bool_false_passthrough(self) -> None:
        config = _parse_judgment_config_from_payload(
            {"judgment_config": {"enable_message_judgment": False}}
        )
        assert config == {"enable_message_judgment": False}

    def test_string_dirty_value_dropped(self) -> None:
        # 字符串 "false" 若透传会被 _opt_bool 误判 True，必须丢弃
        assert (
            _parse_judgment_config_from_payload(
                {"judgment_config": {"enable_message_judgment": "false"}}
            )
            is None
        )
        config = _parse_judgment_config_from_payload(
            {
                "judgment_config": {
                    "enable_err_code_judgment": "true",
                    "enable_message_judgment": False,
                }
            }
        )
        assert config == {"enable_message_judgment": False}

    def test_disable_first_level_combo_key(self) -> None:
        config = _parse_judgment_config_from_payload(
            {"judgment_config": {"disable_first_level": True}}
        )
        assert config == {
            "enable_err_code_judgment": False,
            "enable_message_judgment": False,
        }

    def test_disable_first_level_non_bool_true_ignored(self) -> None:
        assert (
            _parse_judgment_config_from_payload(
                {"judgment_config": {"disable_first_level": "true"}}
            )
            is None
        )


# ---------------------------------------------------------------------------
# W-6: executor 端到端钉桩
# ---------------------------------------------------------------------------


def _mock_session(body: Dict[str, Any]) -> MagicMock:
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
        "name": "订单查询",
        "method": "GET",
        "full_url": "https://api.example.com/test",
        "folder": "",
        "expected_status": 200,
    }
    base.update(overrides)
    return base


SESSION_EXPIRED_BODY = {"message": "session 已经过期", "errCode": 100001}
ASSERT_EQ_100002 = [{"path": "$.errCode", "op": "eq", "expected": 100002}]
_DISABLE_BOTH = {
    "enable_err_code_judgment": False,
    "enable_message_judgment": False,
}


class TestExecutorDisableFirstLevel:
    def test_disabled_judgment_assertion_decides_failed(self) -> None:
        # W-1 引擎侧等价：关判定 + session 过期 + 断言 eq 100002 → 断言执行并判 FAILED
        exc = PostmanTestExecutor(
            _api(x_assertions=ASSERT_EQ_100002),  # type: ignore[arg-type]
            session=_mock_session(SESSION_EXPIRED_BODY),
            judgment_config=dict(_DISABLE_BOTH),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert result.get("assertion_results"), "关闭一级判定后断言必须执行"
        assert all("判定失败" not in r.get("message", "") for r in result["assertion_results"])
        assert "断言失败" in result["message"]

    def test_disabled_judgment_assertion_passes(self) -> None:
        # 关判定 + 断言期望值正确 → PASSED（"断言接管成败"的正向半边）
        exc = PostmanTestExecutor(
            _api(
                x_assertions=[
                    {"path": "$.errCode", "op": "eq", "expected": 100001}
                ]
            ),  # type: ignore[arg-type]
            session=_mock_session(SESSION_EXPIRED_BODY),
            judgment_config=dict(_DISABLE_BOTH),
        )
        result = exc.execute_test()
        assert result["status"] == "PASSED"
        assert result.get("assertion_results")
        assert all(r["passed"] for r in result["assertion_results"])

    def test_judgment_on_session_expired_skips_assertions(self) -> None:
        # W-2 回归防线：不传 judgment_config，现状语义——判定层先 FAILED，断言不执行
        exc = PostmanTestExecutor(
            _api(x_assertions=ASSERT_EQ_100002),  # type: ignore[arg-type]
            session=_mock_session(SESSION_EXPIRED_BODY),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "不满足成功条件" in result["message"]
        assert not result.get("assertion_results")

    def test_no_judgment_config_and_no_assertion_status_code_only(self) -> None:
        # W-3 引擎侧：关判定 + 无断言 → 仅状态码，PASSED（近乎恒通过的钉桩）
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session(SESSION_EXPIRED_BODY),
            judgment_config=dict(_DISABLE_BOTH),
        )
        result = exc.execute_test()
        assert result["status"] == "PASSED"
