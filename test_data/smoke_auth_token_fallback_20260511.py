#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Auth token fallback smoke test.

验证点：
1. 仅 login 候选会被尝试
2. 首个 login 失败后会继续尝试后续 login
3. 可从 data.access_token 提取 token
"""

from typing import Any, Dict, List, Optional

from postman_api_tester.auth import get_auth_token


class _FakeResponse:
    def __init__(self, status_code: int, payload: Optional[Dict[str, Any]] = None, raise_json: bool = False):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_json = raise_json

    def json(self) -> Dict[str, Any]:
        if self._raise_json:
            raise ValueError("invalid json")
        return self._payload


class _FakeSession:
    def __init__(self, responses: List[_FakeResponse]):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "get", "url": url, "kwargs": kwargs})
        return self._responses.pop(0)

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "post", "url": url, "kwargs": kwargs})
        return self._responses.pop(0)

    def close(self) -> None:
        self.closed = True


def _build_apis() -> List[Dict[str, Any]]:
    return [
        {
            "name": "health check",
            "url": "/health",
            "full_url": "http://example.local/health",
            "method": "GET",
            "headers": {},
            "params": {},
        },
        {
            "name": "login-primary",
            "url": "/auth/login",
            "full_url": "http://example.local/auth/login",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "u", "password": "p"},
            "params": {},
        },
        {
            "name": "login-secondary",
            "url": "/user/login",
            "full_url": "http://example.local/user/login",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "u", "password": "p"},
            "params": {},
        },
    ]


def main() -> None:
    apis = _build_apis()
    fake = _FakeSession(
        responses=[
            _FakeResponse(status_code=500, payload={"msg": "failed"}),
            _FakeResponse(status_code=200, payload={"data": {"access_token": "abc-token-123"}}),
        ]
    )

    token = get_auth_token(apis, "http://example.local", session=fake, request_timeout=(9, 19))

    assert token == "abc-token-123", f"unexpected token: {token}"
    assert len(fake.calls) == 2, f"unexpected call count: {len(fake.calls)}"
    assert fake.calls[0]["method"] == "post"
    assert fake.calls[1]["method"] == "post"

    first_timeout = fake.calls[0]["kwargs"].get("timeout")
    assert first_timeout == (9, 19), f"unexpected timeout: {first_timeout}"

    print("auth-token-fallback-ok")


if __name__ == "__main__":
    main()
