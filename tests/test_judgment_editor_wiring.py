"""v1.37.18 接口级判定字段编辑器往返 + 集合级共享断言测试。

覆盖：
- service 五字段 parse/build 往返（缺口 ② 回归防线）与归一化防御；
- 根级 x_shared_assertions 往返（parse normalize / build 空不写）；
- parser 共享断言挂键（不污染 item 自有、skip 豁免）；
- executor 合并语义（shared 在前、失败短路翻 FAILED、豁免仅自有）。
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

from postman_api_tester.executor import PostmanTestExecutor
from postman_api_tester.parser import PostmanApiParser
from postman_api_tester.services.collection_editor_service import (
    build_collection_json,
    parse_collection_to_flat,
)
from postman_api_tester.utils.variable_substitution import _copy_api_config

_JUDGMENT_BOOL_KEYS = (
    "x_enable_err_code_judgment",
    "x_enable_message_judgment",
    "x_skip_shared_assertions",
)


def _request_node(**extra: Any) -> Dict[str, Any]:
    request: Dict[str, Any] = {"method": "GET", "url": "https://api.example.com/x"}
    request.update(extra)
    return {"name": "case", "request": request}


def _collection(*items: Dict[str, Any], **root: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "info": {"name": "C", "schema": "s", "_postman_id": "p"},
        "item": list(items),
    }
    data.update(root)
    return data


class TestServiceParseJudgmentFields:
    def test_missing_fields_defaults(self) -> None:
        flat = parse_collection_to_flat(_collection(_request_node()))
        req = flat["groups"][-1]["requests"][0]
        for key in _JUDGMENT_BOOL_KEYS:
            assert req[key] is None
        assert req["x_success_err_codes"] == ""
        assert req["x_success_messages"] == ""

    def test_bool_and_string_normalization(self) -> None:
        node = _request_node(
            x_enable_message_judgment=False,
            x_enable_err_code_judgment="true",
            x_skip_shared_assertions="1",
            x_success_err_codes=" 0,200 ",
            x_success_messages="success,ok",
        )
        req = parse_collection_to_flat(_collection(node))["groups"][-1]["requests"][0]
        assert req["x_enable_message_judgment"] is False
        assert req["x_enable_err_code_judgment"] is True
        assert req["x_skip_shared_assertions"] is True
        assert req["x_success_err_codes"] == "0,200"
        assert req["x_success_messages"] == "success,ok"

    def test_dirty_string_bool_maps_like_parser(self) -> None:
        # 与 parser 同口径："no" 不在 truthy 白名单 → False
        node = _request_node(x_enable_err_code_judgment="no")
        req = parse_collection_to_flat(_collection(node))["groups"][-1]["requests"][0]
        assert req["x_enable_err_code_judgment"] is False


class TestServiceBuildJudgmentFields:
    def _build_req(self, **fields: Any) -> Dict[str, Any]:
        req = {
            "id": "r1",
            "name": "n",
            "method": "GET",
            "url": "http://x",
            "headers": [],
            "params": [],
            "body_mode": "none",
            "body_data": None,
        }
        req.update(fields)
        return build_collection_json(
            {"collection_info": {"name": "c"}, "groups": [
                {"group_name": "", "requests": [req], "subgroups": []}
            ]}
        )["item"][0]["request"]

    def test_none_not_written_bool_written(self) -> None:
        built = self._build_req(
            x_enable_message_judgment=False, x_skip_shared_assertions=None
        )
        assert built["x_enable_message_judgment"] is False
        assert "x_enable_err_code_judgment" not in built
        assert "x_skip_shared_assertions" not in built

    def test_non_bool_dropped(self) -> None:
        built = self._build_req(x_enable_message_judgment="false")
        assert "x_enable_message_judgment" not in built

    def test_success_str_written_and_blank_dropped(self) -> None:
        built = self._build_req(x_success_messages=" ok ", x_success_err_codes="  ")
        assert built["x_success_messages"] == "ok"
        assert "x_success_err_codes" not in built

    def test_full_roundtrip_preserves_fields(self) -> None:
        # 缺口 ② 复现防线：手工 5 字段 parse→build 逐字段一致
        node = _request_node(
            x_enable_err_code_judgment=False,
            x_enable_message_judgment=False,
            x_skip_shared_assertions=True,
            x_success_err_codes="0",
            x_success_messages="success",
        )
        collection = _collection(node)
        flat = parse_collection_to_flat(collection)
        rebuilt = build_collection_json(flat)
        built_req = rebuilt["item"][-1]["request"]
        for key in _JUDGMENT_BOOL_KEYS:
            assert built_req[key] == collection["item"][-1]["request"][key]
        assert built_req["x_success_err_codes"] == "0"
        assert built_req["x_success_messages"] == "success"


class TestServiceSharedAssertionsRoundtrip:
    def test_parse_normalizes_shared(self) -> None:
        collection = _collection(
            _request_node(),
            x_shared_assertions=[
                {"path": "$.errCode", "op": "eq", "expected": 0},
                {"path": "", "op": "eq", "expected": 1},  # 脏项应被过滤
            ],
        )
        flat = parse_collection_to_flat(collection)
        assert flat["x_shared_assertions"] == [
            {"path": "$.errCode", "op": "eq", "expected": 0}
        ]

    def test_build_writes_root_and_empty_omits(self) -> None:
        flat = parse_collection_to_flat(
            _collection(
                _request_node(),
                x_shared_assertions=[
                    {"path": "$.data", "op": "exists", "expected": None}
                ],
            )
        )
        rebuilt = build_collection_json(flat)
        assert rebuilt["x_shared_assertions"] == [
            {"path": "$.data", "op": "exists", "expected": None}
        ]
        empty_flat = parse_collection_to_flat(_collection(_request_node()))
        assert build_collection_json(empty_flat).get("x_shared_assertions") is None

    def test_shared_not_leaked_into_items(self) -> None:
        collection = _collection(
            _request_node(),
            x_shared_assertions=[{"path": "$.errCode", "op": "eq", "expected": 0}],
        )
        rebuilt = build_collection_json(parse_collection_to_flat(collection))
        req = rebuilt["item"][-1]["request"]
        assert "x_assertions" not in req  # 共享不并入 item 自有


class TestParserSharedAssertionAttach:
    def _write(self, tmp_path: Path, data: Dict[str, Any]) -> str:
        p = tmp_path / "c.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    def test_attached_to_each_item_and_exempt(self, tmp_path: Path) -> None:
        shared = [{"path": "$.errCode", "op": "eq", "expected": 0}]
        normal = _request_node()
        exempt = _request_node(x_skip_shared_assertions=True)
        own = _request_node(
            x_assertions=[{"path": "$.data", "op": "exists", "expected": None}]
        )
        path = self._write(
            tmp_path, _collection(normal, exempt, own, x_shared_assertions=shared)
        )
        apis = PostmanApiParser(path).extract_apis()
        assert apis[0]["x_shared_assertions"] == shared
        assert "x_shared_assertions" not in apis[1]  # 豁免
        assert apis[2]["x_shared_assertions"] == shared
        # 不污染 item 自有断言
        assert apis[2]["x_assertions"] == [
            {"path": "$.data", "op": "exists", "expected": None}
        ]
        assert apis[1]["x_skip_shared_assertions"] is True

    def test_no_shared_root_means_no_key(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, _collection(_request_node()))
        apis = PostmanApiParser(path).extract_apis()
        assert "x_shared_assertions" not in apis[0]


class TestExecutorSharedMerge:
    _DISABLE = {
        "enable_err_code_judgment": False,
        "enable_message_judgment": False,
    }

    def _run(self, api: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = body
        resp.headers = {"Content-Type": "application/json"}
        resp.request = MagicMock()
        resp.request.url = "https://api.example.com/test"
        session.get.return_value = resp
        exc = PostmanTestExecutor(  # type: ignore[arg-type]
            api, session=session, judgment_config=dict(self._DISABLE)
        )
        return exc.execute_test()

    def _api(self, **overrides: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "name": "n",
            "method": "GET",
            "full_url": "https://api.example.com/test",
            "folder": "",
            "expected_status": 200,
        }
        base.update(overrides)
        return base

    def test_shared_runs_first_and_and_semantics(self) -> None:
        body = {"errCode": 0, "data": "x"}
        result = self._run(
            self._api(
                x_shared_assertions=[
                    {"path": "$.errCode", "op": "eq", "expected": 0}
                ],
                x_assertions=[
                    {"path": "$.data", "op": "exists", "expected": None}
                ],
            ),
            body,
        )
        rows = result["assertion_results"]
        assert len(rows) == 2
        assert all(r["passed"] for r in rows)
        assert rows[0]["path"] == "$.errCode"  # 共享在前
        assert rows[1]["path"] == "$.data"

    def test_shared_failure_flips_failed(self) -> None:
        result = self._run(
            self._api(
                x_shared_assertions=[
                    {"path": "$.errCode", "op": "eq", "expected": 0}
                ]
            ),
            {"errCode": 100002, "message": "参数缺失"},
        )
        assert result["status"] == "FAILED"
        assert "断言失败" in result["message"]
        assert len(result["assertion_results"]) == 1

    def test_own_failure_after_shared_pass(self) -> None:
        result = self._run(
            self._api(
                x_shared_assertions=[
                    {"path": "$.errCode", "op": "eq", "expected": 0}
                ],
                x_assertions=[
                    {"path": "$.errCode", "op": "eq", "expected": 100002}
                ],
            ),
            {"errCode": 100002, "message": "参数缺失"},
        )
        rows = result["assertion_results"]
        assert len(rows) == 2
        # 共享 eq 0 对 100002 响应失败在前；自有 eq 100002 通过在后（AND 语义整体 FAILED）
        assert rows[0]["passed"] is False and rows[0]["expected"] == 0
        assert rows[1]["passed"] is True and rows[1]["expected"] == 100002
        assert result["status"] == "FAILED"
        assert "断言失败" in result["message"]


class TestCopyApiConfigPassthrough:
    def test_new_keys_survive_substitution_copy(self) -> None:
        api: Dict[str, Any] = {
            "name": "n",
            "method": "GET",
            "full_url": "http://x",
            "url": "http://x",
            "x_shared_assertions": [{"path": "$.a", "op": "eq", "expected": 1}],
            "x_skip_shared_assertions": True,
            "x_enable_message_judgment": False,
        }
        copied = _copy_api_config(api, url="http://y", full_url="http://y")
        assert copied["x_shared_assertions"] == api["x_shared_assertions"]
        assert copied["x_skip_shared_assertions"] is True
        assert copied["x_enable_message_judgment"] is False
