"""v1.37.22 自定义一级判定规则（x_judgment_rules）单元测试。

覆盖提案验收矩阵 Y-1~Y-6 与风险 K-2/K-4 行为钉桩。
"""

from typing import Any, Dict
from unittest.mock import MagicMock, patch

from postman_api_tester.assertions import normalize_assertion_rules
from postman_api_tester.executor import PostmanTestExecutor
from postman_api_tester.parser import PostmanApiParser
from postman_api_tester.services.collection_editor_service import (
    _build_request_object,
    _parse_request_node,
)
from postman_api_tester.utils.variable_substitution import _copy_api_config


def _mock_session(body: Any) -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    if isinstance(body, str):
        resp.json.side_effect = ValueError("not json")
        resp.text = body
    else:
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
RULE_DATA_OK_PASS = [{"path": "$.data.status", "op": "eq", "expected": "bad"}]
_ERR_ONLY_MSG_ON = {
    "enable_err_code_judgment": False,
    "enable_message_judgment": True,
}
_DISABLE_BOTH = {
    "enable_err_code_judgment": False,
    "enable_message_judgment": False,
}


class TestExecutorMatrix:
    def test_y1_builtin_pass_custom_fail_short_circuits_assertions(self) -> None:
        exc = PostmanTestExecutor(
            _api(
                x_judgment_rules=RULE_DATA_OK,
                x_assertions=[{"path": "$.message", "op": "exists"}],
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]
        assert not result.get("assertion_results"), "判定失败必须短路断言"

    def test_y2_custom_pass_then_assertions_run(self) -> None:
        exc = PostmanTestExecutor(
            _api(
                x_judgment_rules=RULE_DATA_OK_PASS,
                x_assertions=[
                    {"path": "$.data.status", "op": "eq", "expected": "ok"}
                ],
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "断言失败" in result["message"]
        assert result.get("assertion_results"), "判定通过后断言必须执行"

    def test_y3_builtin_fail_does_not_evaluate_custom(self) -> None:
        body = {"message": "session 已经过期", "errCode": 100001}
        exc = PostmanTestExecutor(
            _api(x_judgment_rules=RULE_DATA_OK),  # type: ignore[arg-type]
            session=_mock_session(body),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "不满足成功条件" in result["message"]
        assert "自定义判定失败" not in result["message"], "内置已失败不得混排自定义结果"

    def test_y4_task_level_disable_skips_custom_rules(self) -> None:
        exc = PostmanTestExecutor(
            _api(x_judgment_rules=RULE_DATA_OK),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_DISABLE_BOTH),
        )
        assert exc.execute_test()["status"] == "PASSED"

    def test_y4_item_level_disable_skips_custom_rules(self) -> None:
        exc = PostmanTestExecutor(
            _api(
                x_judgment_rules=RULE_DATA_OK,
                x_enable_err_code_judgment=False,
                x_enable_message_judgment=False,
            ),  # type: ignore[arg-type]
            session=_mock_session({"message": "session 已经过期"}),
        )
        assert exc.execute_test()["status"] == "PASSED"

    def test_partial_disable_still_evaluates_custom(self) -> None:
        # errCode 关、message 开 = 主判定未整体关闭，自定义规则照常执行
        exc = PostmanTestExecutor(
            _api(x_judgment_rules=RULE_DATA_OK),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        assert exc.execute_test()["status"] == "FAILED"

    def test_y6_no_rules_zero_regression(self) -> None:
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session({"message": "success"}),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        assert exc.execute_test()["status"] == "PASSED"

    def test_k4_non_json_response_fails_custom(self) -> None:
        exc = PostmanTestExecutor(
            _api(x_judgment_rules=RULE_DATA_OK),  # type: ignore[arg-type]
            session=_mock_session("<html>not json</html>"),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]

    def test_k2_invalid_path_fail_closed(self) -> None:
        exc = PostmanTestExecutor(
            _api(
                x_judgment_rules=[{"path": "$[", "op": "exists", "expected": None}]
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_ERR_ONLY_MSG_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]

    def test_jsonpath_missing_fail_closed(self) -> None:
        with patch("postman_api_tester.executor._ASSERTIONS_AVAILABLE", False):
            exc = PostmanTestExecutor(
                _api(x_judgment_rules=RULE_DATA_OK),  # type: ignore[arg-type]
                session=_mock_session(OK_MSG_BODY),
                judgment_config=dict(_ERR_ONLY_MSG_ON),
            )
            result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "jsonpath_ng 未安装" in result["message"]


class TestParserRoundTrip:
    def test_x_judgment_rules_parsed_and_normalized(self, tmp_path: Any) -> None:
        collection = {
            "info": {"name": "c"},
            "item": [
                {
                    "name": "api",
                    "request": {
                        "method": "GET",
                        "url": "https://api.example.com/x",
                        "x_judgment_rules": [
                            {"path": "$.data.ok", "op": "eq", "expected": True},
                            {"op": "eq"},
                            {"path": "$.x", "op": "bogus"},
                        ],
                    },
                }
            ],
        }
        fp = tmp_path / "c.json"
        fp.write_text(__import__("json").dumps(collection), encoding="utf-8")
        apis = PostmanApiParser(str(fp)).extract_apis()
        rules = apis[0]["x_judgment_rules"]
        assert rules == [{"path": "$.data.ok", "op": "eq", "expected": True}]

    def test_absent_field_not_written(self, tmp_path: Any) -> None:
        collection = {
            "info": {"name": "c"},
            "item": [
                {"name": "api", "request": {"method": "GET", "url": "u"}}
            ],
        }
        fp = tmp_path / "c.json"
        fp.write_text(__import__("json").dumps(collection), encoding="utf-8")
        apis = PostmanApiParser(str(fp)).extract_apis()
        assert "x_judgment_rules" not in apis[0]


class TestEditorServiceRoundTrip:
    def test_parse_flat_contains_rules(self) -> None:
        request_obj = {
            "method": "GET",
            "url": "u",
            "x_judgment_rules": [
                {"path": "$.code", "op": "ne", "expected": 500}
            ],
        }
        flat = _parse_request_node({"name": "n"}, request_obj, "r1")
        assert flat["x_judgment_rules"] == [
            {"path": "$.code", "op": "ne", "expected": 500}
        ]

    def test_build_writes_normalized_and_drops_dirty(self) -> None:
        req = {
            "method": "GET",
            "url": "u",
            "x_judgment_rules": [
                {"path": "$.code", "op": "ne", "expected": 500},
                "dirty",
            ],
        }
        built = _build_request_object(req)
        assert built["x_judgment_rules"] == [
            {"path": "$.code", "op": "ne", "expected": 500}
        ]

    def test_build_empty_not_written(self) -> None:
        built = _build_request_object(
            {"method": "GET", "url": "u", "x_judgment_rules": []}
        )
        assert "x_judgment_rules" not in built


class TestVariableSubstitutionCopy:
    def test_copy_preserves_judgment_rules(self) -> None:
        api = _api(x_judgment_rules=RULE_DATA_OK)
        copied = _copy_api_config(api, url="https://api.example.com/new")
        assert copied["x_judgment_rules"] == RULE_DATA_OK


def test_normalize_shared_with_assertions() -> None:
    # 与断言共用同一归一化口径
    assert normalize_assertion_rules(
        [{"path": "$.a", "op": "EQ", "expected": 1}], source="test"
    ) == [{"path": "$.a", "op": "eq", "expected": 1}]
