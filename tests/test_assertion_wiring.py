"""JSONPath 断言执行链接线测试（v1.37.14）。

覆盖三个断点的修复：
- B-1 ad-hoc payload.assertions_json → 临时 Collection request.x_assertions
- B-2 Collection request.x_assertions → parser → ApiConfig
- 归一化函数 normalize_assertion_rules 的脏数据过滤
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.assertions import SUPPORTED_OPS, normalize_assertion_rules
from postman_api_tester.parser import PostmanApiParser
from postman_api_tester.utils.collection_utils import (
    build_adhoc_collection,
    normalize_adhoc_case,
)


class TestNormalizeAssertionRules:
    def test_none_returns_empty(self) -> None:
        assert normalize_assertion_rules(None) == []

    def test_non_list_returns_empty(self) -> None:
        assert normalize_assertion_rules({"path": "$.a", "op": "eq"}) == []

    def test_valid_rules_kept_with_expected(self) -> None:
        raw = [
            {"path": "$.data.id", "op": "EQ", "expected": 7},
            {"path": "$.errCode", "op": "exists"},
        ]
        rules = normalize_assertion_rules(raw, source="test")
        assert rules == [
            {"path": "$.data.id", "op": "eq", "expected": 7},
            {"path": "$.errCode", "op": "exists", "expected": None},
        ]

    def test_invalid_items_dropped_valid_kept(self) -> None:
        raw = [
            {"path": "", "op": "eq", "expected": 1},
            {"path": "$.a", "op": "unknown_op"},
            {"op": "eq", "expected": 1},
            "not-a-dict",
            {"path": "$.ok", "op": "contains", "expected": "x"},
        ]
        rules = normalize_assertion_rules(raw, source="test")
        assert len(rules) == 1
        assert rules[0]["path"] == "$.ok"

    def test_all_ops_accepted(self) -> None:
        raw = [{"path": "$.x", "op": op} for op in sorted(SUPPORTED_OPS)]
        assert len(normalize_assertion_rules(raw)) == len(SUPPORTED_OPS)


def _make_collection(request_extra: Dict[str, Any]) -> Dict[str, Any]:
    request: Dict[str, Any] = {"method": "GET", "url": "http://svc.test/api"}
    request.update(request_extra)
    return {
        "info": {"name": "c", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [{"name": "api1", "request": request}],
    }


class TestParserWiring:
    def _extract(self, tmp_path: Path, collection: Dict[str, Any]) -> Any:
        path = tmp_path / "collection.json"
        path.write_text(json.dumps(collection), encoding="utf-8")
        parser = PostmanApiParser(str(path))
        return parser.extract_apis()

    def test_x_assertions_passthrough_and_filtered(self, tmp_path: Path) -> None:
        collection = _make_collection(
            {
                "x_assertions": [
                    {"path": "$.errCode", "op": "eq", "expected": 0},
                    {"path": "$.bad", "op": "no_such_op"},
                ]
            }
        )
        apis = self._extract(tmp_path, collection)
        assert apis[0].get("x_assertions") == [
            {"path": "$.errCode", "op": "eq", "expected": 0}
        ]

    def test_no_assertions_key_absent(self, tmp_path: Path) -> None:
        apis = self._extract(tmp_path, _make_collection({}))
        assert apis[0].get("x_assertions") is None

    def test_garbage_assertions_ignored(self, tmp_path: Path) -> None:
        apis = self._extract(
            tmp_path, _make_collection({"x_assertions": "not-a-list"})
        )
        assert apis[0].get("x_assertions") is None


class TestAdhocBuild:
    def test_build_writes_x_assertions(self) -> None:
        case = normalize_adhoc_case(
            {"method": "GET", "url": "http://svc.test/api"}, 0, None
        )
        case["x_assertions"] = [{"path": "$.errCode", "op": "exists"}]
        collection = build_adhoc_collection([case], "adhoc", None)
        request = collection["item"][0]["request"]
        assert request["x_assertions"] == [{"path": "$.errCode", "op": "exists"}]

    def test_build_skips_empty_assertions(self) -> None:
        case = normalize_adhoc_case(
            {"method": "GET", "url": "http://svc.test/api"}, 0, None
        )
        collection = build_adhoc_collection([case], "adhoc", None)
        request = collection["item"][0]["request"]
        assert "x_assertions" not in request


class TestAdhocHandlerWiring:
    """api_run_ad_hoc_tests：payload 顶层 assertions_json 注入每条用例。"""

    def test_global_assertions_applied_to_cases(self, tmp_path: Path) -> None:
        import postman_api_tester.handlers.job_routes as job_routes_module

        with Flask(__name__).test_request_context(), patch.object(
            job_routes_module, "ENABLE_ADHOC_RUN", True
        ), patch(
            "postman_api_tester.handlers.job_routes.request"
        ) as mock_request, patch.object(
            job_routes_module, "_svc_build_adhoc_collection", return_value={}
        ) as mock_build, patch.object(
            job_routes_module,
            "_build_saved_json_path",
            return_value=tmp_path / "adhoc.json",
        ), patch.object(
            job_routes_module, "_svc_save_collection_json"
        ), patch.object(
            job_routes_module, "_enqueue_job"
        ):
            mock_request.get_json = MagicMock(
                return_value={
                    "cases": [
                        {"method": "GET", "url": "http://svc.test/a"},
                        {"method": "GET", "url": "http://svc.test/b"},
                    ],
                    "assertions_json": [
                        {"path": "$.errCode", "op": "eq", "expected": 0},
                        {"path": "$.x", "op": "bogus"},
                    ],
                }
            )
            resp, status = job_routes_module.api_run_ad_hoc_tests()
        assert status == 200
        cases_arg = mock_build.call_args[0][0]
        assert len(cases_arg) == 2
        for case in cases_arg:
            assert case["x_assertions"] == [
                {"path": "$.errCode", "op": "eq", "expected": 0}
            ]
