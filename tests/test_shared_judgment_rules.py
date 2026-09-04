"""v1.38.1 集合级共享判定规则（x_shared_judgment_rules，P1）单元测试。

覆盖：parser 根级注入与豁免、executor 三层合并顺序（任务→共享→接口）、
关闭一级判定联动、编辑器根级往返、并发副本键同步。
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock

from postman_api_tester.executor import PostmanTestExecutor
from postman_api_tester.parser import PostmanApiParser
from postman_api_tester.services.collection_editor_service import (
    build_collection_json,
    parse_collection_to_flat,
)
from postman_api_tester.utils.variable_substitution import _copy_api_config

OK_MSG_BODY = {"message": "success", "code": 1, "data": {"status": "bad"}}
RULE_CODE_ZERO = [{"path": "$.code", "op": "eq", "expected": 0}]
RULE_STATUS_OK = [{"path": "$.data.status", "op": "eq", "expected": "ok"}]
_MSG_ONLY_ON = {
    "enable_err_code_judgment": False,
    "enable_message_judgment": True,
}
_DISABLE_BOTH = {
    "enable_err_code_judgment": False,
    "enable_message_judgment": False,
}


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


def _collection(**root_extras: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "info": {"name": "c"},
        "item": [
            {"name": "api1", "request": {"method": "GET", "url": "https://api.example.com/t1"}},
            {
                "name": "api2",
                "request": {
                    "method": "GET",
                    "url": "https://api.example.com/t2",
                    "x_skip_shared_assertions": True,
                },
            },
        ],
    }
    data.update(root_extras)
    return data


def _write(tmp_path: Any, data: Dict[str, Any]) -> str:
    fp = tmp_path / "c.json"
    fp.write_text(json.dumps(data), encoding="utf-8")
    return str(fp)


class TestParserInjection:
    def test_root_rules_injected_to_all_items(self, tmp_path: Any) -> None:
        path = _write(
            tmp_path,
            _collection(x_shared_judgment_rules=RULE_CODE_ZERO),
        )
        apis = PostmanApiParser(path).extract_apis()
        assert apis[0]["x_shared_judgment_rules"] == RULE_CODE_ZERO

    def test_skip_shared_flag_exempts_judgment_too(self, tmp_path: Any) -> None:
        path = _write(
            tmp_path,
            _collection(x_shared_judgment_rules=RULE_CODE_ZERO),
        )
        apis = PostmanApiParser(path).extract_apis()
        assert "x_shared_judgment_rules" not in apis[1], (
            "x_skip_shared_assertions 豁免须同步覆盖共享判定"
        )

    def test_dirty_rules_normalized(self, tmp_path: Any) -> None:
        path = _write(
            tmp_path,
            _collection(
                x_shared_judgment_rules=[
                    {"path": "$.code", "op": "EQ", "expected": 0},
                    {"op": "eq"},
                    "dirty",
                ]
            ),
        )
        apis = PostmanApiParser(path).extract_apis()
        assert apis[0]["x_shared_judgment_rules"] == [
            {"path": "$.code", "op": "eq", "expected": 0}
        ]

    def test_absent_root_field_not_injected(self, tmp_path: Any) -> None:
        apis = PostmanApiParser(_write(tmp_path, _collection())).extract_apis()
        assert all("x_shared_judgment_rules" not in a for a in apis)


class TestExecutorMerge:
    def test_shared_rule_fail_short_circuits_assertions(self) -> None:
        exc = PostmanTestExecutor(
            _api(
                x_shared_judgment_rules=RULE_CODE_ZERO,
                x_assertions=[{"path": "$.message", "op": "exists"}],
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_MSG_ONLY_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]
        assert not result.get("assertion_results"), "判定失败必须短路断言"

    def test_merge_order_task_shared_item(self) -> None:
        # 任务级必败规则在前、共享其次、接口自有最后 → 失败消息按此顺序拼接
        task_rule = [{"path": "$.message", "op": "eq", "expected": "task-fail"}]
        item_rule = [{"path": "$.data.status", "op": "eq", "expected": "item-fail"}]
        exc = PostmanTestExecutor(
            _api(
                x_shared_judgment_rules=[
                    {"path": "$.code", "op": "eq", "expected": "shared-fail"}
                ],
                x_judgment_rules=item_rule,
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config={**_MSG_ONLY_ON, "custom_rules": task_rule},
        )
        result = exc.execute_test()
        msg = result["message"]
        pos_task = msg.index("task-fail")
        pos_shared = msg.index("shared-fail")
        pos_item = msg.index("item-fail")
        assert pos_task < pos_shared < pos_item

    def test_disable_first_level_skips_shared_rules(self) -> None:
        exc = PostmanTestExecutor(
            _api(x_shared_judgment_rules=RULE_CODE_ZERO),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_DISABLE_BOTH),
        )
        assert exc.execute_test()["status"] == "PASSED"

    def test_shared_pass_item_fail(self) -> None:
        # 共享规则通过（$.code 存在即可）→ 自有规则失败仍 FAILED
        exc = PostmanTestExecutor(
            _api(
                x_shared_judgment_rules=[
                    {"path": "$.code", "op": "exists", "expected": None}
                ],
                x_judgment_rules=RULE_STATUS_OK,
            ),  # type: ignore[arg-type]
            session=_mock_session(OK_MSG_BODY),
            judgment_config=dict(_MSG_ONLY_ON),
        )
        result = exc.execute_test()
        assert result["status"] == "FAILED"
        assert "自定义判定失败" in result["message"]

    def test_no_shared_rules_zero_regression(self) -> None:
        exc = PostmanTestExecutor(
            _api(),  # type: ignore[arg-type]
            session=_mock_session({"message": "success", "errCode": 0}),
            judgment_config=dict(_MSG_ONLY_ON),
        )
        assert exc.execute_test()["status"] == "PASSED"


class TestEditorRootRoundTrip:
    def test_parse_root_exposes_key(self) -> None:
        flat = parse_collection_to_flat(
            _collection(
                x_shared_judgment_rules=[
                    {"path": "$.code", "op": "eq", "expected": 0},
                    "dirty",
                ]
            )
        )
        assert flat["x_shared_judgment_rules"] == RULE_CODE_ZERO

    def test_build_writes_normalized_and_empty_dropped(self) -> None:
        built = build_collection_json(
            {
                "collection_info": {"name": "c"},
                "groups": [],
                "x_shared_judgment_rules": [
                    {"path": "$.code", "op": "eq", "expected": 0},
                    {"op": "bogus"},
                ],
            }
        )
        assert built["x_shared_judgment_rules"] == RULE_CODE_ZERO
        built_empty = build_collection_json(
            {"collection_info": {"name": "c"}, "groups": [], "x_shared_judgment_rules": []}
        )
        assert "x_shared_judgment_rules" not in built_empty


def test_copy_preserves_shared_judgment_rules() -> None:
    api = _api(x_shared_judgment_rules=RULE_CODE_ZERO)
    copied = _copy_api_config(api, url="https://api.example.com/new")
    assert copied["x_shared_judgment_rules"] == RULE_CODE_ZERO
