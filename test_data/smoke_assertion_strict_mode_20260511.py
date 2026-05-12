#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Assertion strict mode smoke test.

验证点：
1. 断言引擎异常 + 非严格模式 => 接口保持 PASSED，并记录 assertion_engine_error
2. 断言引擎异常 + 严格模式 => 接口标记 FAILED
"""

from typing import Any, Dict

from postman_api_tester.executor import PostmanTestExecutor
import postman_api_tester.executor as executor_module


class _FakeRequest:
    def __init__(self, url: str):
        self.url = url


class _FakeResponse:
    def __init__(self, url: str):
        self.status_code = 200
        self.headers = {"Content-Type": "application/json"}
        self.request = _FakeRequest(url)

    def json(self) -> Dict[str, Any]:
        return {"message": "success", "data": {"id": 1}}


class _FakeSession:
    def __init__(self):
        self.calls = 0

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(url)

    def close(self) -> None:
        return None


def _build_api() -> Dict[str, Any]:
    return {
        "name": "assertion-smoke",
        "method": "GET",
        "url": "/smoke",
        "full_url": "http://example.local/smoke",
        "headers": {},
        "params": {},
        "expected_status": 200,
        "x_assertions": [{"path": "$.data.id", "op": "eq", "value": 1}],
    }


def _raise_assertion_error(response_body: Any, assertions: Any) -> Any:
    raise RuntimeError("assertion-engine-boom")


def main() -> None:
    old_eval = executor_module._evaluate_assertions
    old_flag = executor_module._ASSERTIONS_AVAILABLE

    try:
        executor_module._ASSERTIONS_AVAILABLE = True
        executor_module._evaluate_assertions = _raise_assertion_error

        result_non_strict = PostmanTestExecutor(
            _build_api(),
            session=_FakeSession(),
            assertion_strict_mode=False,
        ).execute_test()
        assert result_non_strict["status"] == "PASSED", result_non_strict
        assert result_non_strict.get("assertion_engine_error") == "assertion-engine-boom", result_non_strict

        result_strict = PostmanTestExecutor(
            _build_api(),
            session=_FakeSession(),
            assertion_strict_mode=True,
        ).execute_test()
        assert result_strict["status"] == "FAILED", result_strict
        assert "断言失败" in str(result_strict.get("message", "")), result_strict
        assert result_strict.get("assertion_engine_error") == "assertion-engine-boom", result_strict

        print("assertion-strict-mode-ok")
    finally:
        executor_module._evaluate_assertions = old_eval
        executor_module._ASSERTIONS_AVAILABLE = old_flag


if __name__ == "__main__":
    main()
