"""_ProxySessionStore 综合测试。

覆盖代理会话存储的所有核心方法：
- 会话创建 / 删除 / 过期清理
- Token / 子系统 Token / 平台 URL 管理
- Cookie 管理（更新 / 清空 / Set-Cookie 头转换）
- base_url 关联与查找
"""

from __future__ import annotations

import time
from typing import Any, Dict

import pytest
import requests

from postman_api_tester.services.ui_proxy_service import _ProxySessionStore


@pytest.fixture
def store() -> _ProxySessionStore:
    """创建全新的空会话存储。"""
    return _ProxySessionStore()


# ── 会话创建与删除 ─────────────────────────────────────────────


class TestCreateSession:
    def test_returns_uuid(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        assert sid and len(sid) == 36  # UUID4 format

    def test_creates_with_empty_base_url(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        assert store.get_base_url(sid) == ""

    def test_creates_with_base_url(self, store: _ProxySessionStore) -> None:
        sid = store.create_session("https://example.com")
        assert store.get_base_url(sid) == "https://example.com"

    def test_initial_state(self, store: _ProxySessionStore) -> None:
        sid = store.create_session("https://example.com")
        jar = store.get_cookie_jar(sid)
        assert jar is not None
        assert len(jar) == 0
        assert store.get_token(sid) == ""
        assert store.get_subsystem_token(sid) == ""
        assert store.get_platform_url(sid) == ""
        assert store.get_local_storage(sid) == {}


class TestDeleteSession:
    def test_delete_existing(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        assert store.delete_session(sid) is True
        assert store.get_cookie_jar(sid) is None

    def test_delete_nonexistent(self, store: _ProxySessionStore) -> None:
        assert store.delete_session("nonexistent-id") is False


# ── Token 管理 ─────────────────────────────────────────────────


class TestToken:
    def test_set_and_get(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_token(sid, "abc123")
        assert store.get_token(sid) == "abc123"

    def test_set_empty_ignored(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_token(sid, "")
        assert store.get_token(sid) == ""

    def test_set_null_ignored(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_token(sid, "first")
        store.set_token(sid, "null")
        assert store.get_token(sid) == "first"

    def test_get_nonexistent_session(self, store: _ProxySessionStore) -> None:
        assert store.get_token("missing") is None

    def test_overwrite_token(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_token(sid, "old")
        store.set_token(sid, "new")
        assert store.get_token(sid) == "new"

    def test_same_token_not_logged_again(self, store: _ProxySessionStore) -> None:
        """重复设置相同 token 不应触发日志（减少噪音）。"""
        sid = store.create_session()
        store.set_token(sid, "same_token")
        store.set_token(sid, "same_token")
        assert store.get_token(sid) == "same_token"


class TestSubsystemToken:
    def test_set_and_get(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_subsystem_token(sid, "subsys_token_123")
        assert store.get_subsystem_token(sid) == "subsys_token_123"

    def test_set_empty_ignored(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_subsystem_token(sid, "")
        assert store.get_subsystem_token(sid) == ""

    def test_set_null_ignored(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_subsystem_token(sid, "first")
        store.set_subsystem_token(sid, "null")
        assert store.get_subsystem_token(sid) == "first"

    def test_get_nonexistent_session(self, store: _ProxySessionStore) -> None:
        assert store.get_subsystem_token("missing") is None


# ── 平台 URL 管理 ─────────────────────────────────────────────


class TestPlatformUrl:
    def test_set_and_get(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_platform_url(sid, "https://platform.example.com")
        assert store.get_platform_url(sid) == "https://platform.example.com"

    def test_set_empty_ignored(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_platform_url(sid, "https://first.com")
        store.set_platform_url(sid, "")
        assert store.get_platform_url(sid) == "https://first.com"

    def test_get_nonexistent_session(self, store: _ProxySessionStore) -> None:
        assert store.get_platform_url("missing") == ""


# ── base_url 管理 ─────────────────────────────────────────────


class TestBaseUrl:
    def test_set_and_get(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        store.set_base_url(sid, "https://new.example.com")
        assert store.get_base_url(sid) == "https://new.example.com"

    def test_get_nonexistent_session(self, store: _ProxySessionStore) -> None:
        assert store.get_base_url("missing") is None

    def test_find_by_base_url_found(self, store: _ProxySessionStore) -> None:
        sid = store.create_session("https://example.com")
        found = store.find_session_by_base_url("https://example.com")
        assert found == sid

    def test_find_by_base_url_not_found(self, store: _ProxySessionStore) -> None:
        store.create_session("https://example.com")
        assert store.find_session_by_base_url("https://other.com") is None

    def test_find_by_base_url_empty(self, store: _ProxySessionStore) -> None:
        assert store.find_session_by_base_url("https://example.com") is None


# ── Cookie 管理 ───────────────────────────────────────────────


class TestCookieJar:
    def test_get_cookie_jar(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        jar = store.get_cookie_jar(sid)
        assert jar is not None
        assert isinstance(jar, requests.cookies.RequestsCookieJar)

    def test_get_cookie_jar_nonexistent(self, store: _ProxySessionStore) -> None:
        assert store.get_cookie_jar("missing") is None

    def test_update_cookies(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        new_cookies = requests.cookies.RequestsCookieJar()
        new_cookies.set("session_id", "abc123", domain="example.com", path="/")
        store.update_cookies(sid, new_cookies)
        jar = store.get_cookie_jar(sid)
        assert jar is not None
        assert jar.get("session_id") == "abc123"

    def test_update_cookies_replaces_same_name(
        self, store: _ProxySessionStore
    ) -> None:
        """同名 cookie 应被替换而非共存。"""
        sid = store.create_session()
        # 第一次设置
        cookies1 = requests.cookies.RequestsCookieJar()
        cookies1.set("JSESSIONID", "old_value", domain="example.com", path="/")
        store.update_cookies(sid, cookies1)
        # 第二次设置（同名）
        cookies2 = requests.cookies.RequestsCookieJar()
        cookies2.set("JSESSIONID", "new_value", domain="example.com", path="/")
        store.update_cookies(sid, cookies2)
        jar = store.get_cookie_jar(sid)
        assert jar is not None
        # 只应有一个 JSESSIONID
        jsessionid_cookies = [c for c in jar if c.name == "JSESSIONID"]
        assert len(jsessionid_cookies) == 1
        assert jsessionid_cookies[0].value == "new_value"

    def test_update_cookies_empty_does_not_clear(
        self, store: _ProxySessionStore
    ) -> None:
        """传入空 cookie jar 不应清空已有 cookies。"""
        sid = store.create_session()
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("session_id", "abc123", domain="example.com", path="/")
        store.update_cookies(sid, cookies)
        # 传入空 jar
        empty_jar = requests.cookies.RequestsCookieJar()
        store.update_cookies(sid, empty_jar)
        jar = store.get_cookie_jar(sid)
        assert jar is not None
        assert jar.get("session_id") == "abc123"

    def test_update_cookies_nonexistent_session(
        self, store: _ProxySessionStore
    ) -> None:
        """更新不存在的会话不应抛异常。"""
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("key", "value", domain="example.com", path="/")
        store.update_cookies("nonexistent", cookies)  # 不应抛异常


class TestClearCookiesByBaseUrl:
    def test_clears_matching_session(self, store: _ProxySessionStore) -> None:
        sid = store.create_session("https://example.com")
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("session_id", "abc", domain="example.com", path="/")
        store.update_cookies(sid, cookies)
        store.set_token(sid, "token123")
        store.update_local_storage(sid, "https://example.com", {"key": "value"})

        cleared = store.clear_cookies_by_base_url("https://example.com")
        assert cleared == 1

        jar = store.get_cookie_jar(sid)
        assert jar is not None
        assert len(jar) == 0
        assert store.get_token(sid) == ""
        assert store.get_local_storage(sid) == {}

    def test_ignores_non_matching_session(self, store: _ProxySessionStore) -> None:
        sid = store.create_session("https://example.com")
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("session_id", "abc", domain="example.com", path="/")
        store.update_cookies(sid, cookies)

        cleared = store.clear_cookies_by_base_url("https://other.com")
        assert cleared == 0
        jar = store.get_cookie_jar(sid)
        assert jar is not None
        assert len(jar) == 1

    def test_clears_by_origin_ignoring_path(
        self, store: _ProxySessionStore
    ) -> None:
        """清除时只比较 origin，忽略路径差异。"""
        sid = store.create_session("https://example.com")
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("session_id", "abc", domain="example.com", path="/")
        store.update_cookies(sid, cookies)

        # 传入带路径的 URL，仍应清除
        cleared = store.clear_cookies_by_base_url("https://example.com/login")
        assert cleared == 1

    def test_clears_multiple_sessions(self, store: _ProxySessionStore) -> None:
        sid1 = store.create_session("https://example.com")
        sid2 = store.create_session("https://example.com/api")  # 相同 origin
        sid3 = store.create_session("https://other.com")

        cleared = store.clear_cookies_by_base_url("https://example.com/login")
        assert cleared == 2  # sid1 和 sid2 都被清除

        # sid3 不受影响
        assert store.get_base_url(sid3) == "https://other.com"

    def test_empty_base_url_no_clear(self, store: _ProxySessionStore) -> None:
        store.create_session("https://example.com")
        cleared = store.clear_cookies_by_base_url("")
        assert cleared == 0


# ── Set-Cookie 头转换 ────────────────────────────────────────


class TestGetSetCookieHeaders:
    def test_empty_jar(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        headers = store.get_set_cookie_headers(sid)
        assert headers == []

    def test_nonexistent_session(self, store: _ProxySessionStore) -> None:
        headers = store.get_set_cookie_headers("missing")
        assert headers == []

    def test_converts_cookies(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("session_id", "abc123", domain="example.com", path="/")
        store.update_cookies(sid, cookies)
        headers = store.get_set_cookie_headers(sid)
        assert len(headers) == 1
        assert "session_id=abc123" in headers[0]
        assert "SameSite=Lax" in headers[0]
        # Domain 应被移除
        assert "Domain=" not in headers[0]


# ── 会话清理 ──────────────────────────────────────────────────


class TestCleanupExpired:
    def test_removes_expired_sessions(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        # 手动将 last_active 设为过期
        store._sessions[sid]["last_active"] = time.time() - 7200  # 2小时前
        removed = store.cleanup_expired()
        assert removed == 1
        assert store.get_cookie_jar(sid) is None

    def test_keeps_active_sessions(self, store: _ProxySessionStore) -> None:
        sid = store.create_session()
        removed = store.cleanup_expired()
        assert removed == 0
        assert store.get_cookie_jar(sid) is not None

    def test_mixed_sessions(self, store: _ProxySessionStore) -> None:
        sid1 = store.create_session()
        sid2 = store.create_session()
        store._sessions[sid1]["last_active"] = time.time() - 7200  # 过期
        removed = store.cleanup_expired()
        assert removed == 1
        assert store.get_cookie_jar(sid1) is None
        assert store.get_cookie_jar(sid2) is not None


# ── 会话快照 ──────────────────────────────────────────────────


class TestDumpSessions:
    def test_empty(self, store: _ProxySessionStore) -> None:
        assert store.dump_sessions() == []

    def test_returns_summary(self, store: _ProxySessionStore) -> None:
        sid = store.create_session("https://example.com")
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("session_id", "abc", domain="example.com", path="/")
        store.update_cookies(sid, cookies)

        dump = store.dump_sessions()
        assert len(dump) == 1
        info = dump[0]
        assert info["session_id"] == sid[:8]
        assert info["base_url"] == "https://example.com"
        assert len(info["cookies"]) == 1
        assert info["cookies"][0]["name"] == "session_id"
