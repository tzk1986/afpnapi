#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Auth token missing-field fallback smoke test.

验证点：
1. 当首个 login 响应 200 但缺少 token 字段时，会继续尝试后续 login
2. 最终可从后续候选项获取 token
3. 无 login 候选时应直接返回 None
"""

from typing import Any, Dict, List

from postman_api_tester.auth import get_auth_token


class _FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, responses: List[_FakeResponse]):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "post", "url": url, "kwargs": kwargs})
        return self._responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "get", "url": url, "kwargs": kwargs})
        return self._responses.pop(0)

    def close(self) -> None:
        return None


def _build_login_apis() -> List[Dict[str, Any]]:
    return [
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
    fake = _FakeSession(
        responses=[
            _FakeResponse(200, {"message": "ok", "data": {"user_id": 1}}),
            _FakeResponse(200, {"data": {"token": "fallback-token-xyz"}}),
        ]
    )
    token = get_auth_token(_build_login_apis(), "http://example.local", session=fake, request_timeout=(8, 18))
    assert token == "fallback-token-xyz", token
    assert len(fake.calls) == 2, fake.calls
    assert fake.calls[0]["kwargs"].get("timeout") == (8, 18)

    no_login_apis = [
        {
            "name": "health",
            "url": "/health",
            "full_url": "http://example.local/health",
            "method": "GET",
            "headers": {},
            "params": {},
        }
    ]
    token_none = get_auth_token(no_login_apis, "http://example.local", session=_FakeSession([]), request_timeout=(8, 18))
    assert token_none is None, token_none

    print("auth-token-missing-field-fallback-ok")


if __name__ == "__main__":
    main()
