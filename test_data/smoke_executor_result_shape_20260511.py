#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Executor result-shape smoke test.

验证点：
1. PASSED / FAILED / ERROR 三态结果均包含统一边界字段
2. FAILED / ERROR 保留 db_feedback 字段
"""

from typing import Any, Dict, Set

import requests

from postman_api_tester.executor import PostmanTestExecutor


_REQUIRED_KEYS: Set[str] = {
    "name",
    "method",
    "url",
    "actual_request_url",
    "item_path",
    "expected_status",
    "status",
    "message",
    "err_code",
    "status_code",
    "folder",
    "response_time_ms",
    "request_info",
    "response_info",
    "assertion_results",
    "assertion_engine_error",
}


class _FakeRequest:
    def __init__(self, url: str):
        self.url = url


class _FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any], url: str):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"Content-Type": "application/json"}
        self.request = _FakeRequest(url)

    def json(self) -> Dict[str, Any]:
        return self._payload


class _PassedSession:
    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(200, {"message": "success", "data": {"ok": True}}, url)

    def close(self) -> None:
        return None


class _FailedSession:
    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(500, {"message": "failed", "errCode": "E500"}, url)

    def close(self) -> None:
        return None


class _ErrorSession:
    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        raise requests.exceptions.Timeout("simulated-timeout")

    def close(self) -> None:
        return None


def _build_api(expected_status: int = 200) -> Dict[str, Any]:
    return {
        "name": "shape-smoke",
        "method": "GET",
        "url": "/shape",
        "full_url": "http://example.local/shape",
        "headers": {},
        "params": {},
        "expected_status": expected_status,
        "item_path": [0, 1],
        "folder": "smoke",
    }


def _assert_shape(result: Dict[str, Any], status: str) -> None:
    missing = sorted(_REQUIRED_KEYS - set(result.keys()))
    assert not missing, f"{status} missing keys: {missing}; result={result}"
    assert result.get("status") == status, f"unexpected status: {result}"


def main() -> None:
    passed_result = PostmanTestExecutor(_build_api(200), session=_PassedSession()).execute_test()
    _assert_shape(passed_result, "PASSED")

    failed_result = PostmanTestExecutor(_build_api(200), session=_FailedSession()).execute_test()
    _assert_shape(failed_result, "FAILED")
    assert "db_feedback" in failed_result, f"FAILED should keep db_feedback: {failed_result}"

    error_result = PostmanTestExecutor(_build_api(200), session=_ErrorSession()).execute_test()
    _assert_shape(error_result, "ERROR")
    assert "db_feedback" in error_result, f"ERROR should keep db_feedback: {error_result}"

    print("executor-result-shape-ok")


if __name__ == "__main__":
    main()
