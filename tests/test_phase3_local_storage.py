"""Phase 3: localStorage 提取、存储、导出和注入全链路测试。

覆盖：
- _ProxySessionStore 的 localStorage 方法
- UiAuthProfileStore 的 localStorage 字段支持
- _write_auth_state_temp 的 localStorage 写入
- api_ui_testing_recording_local_storage 端点
- api_ui_testing_recording_stop 的 localStorage 导出
- 录制时 JS 注入逻辑验证
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.services.ui_auth_profile_store import UiAuthProfileStore
from postman_api_tester.services.ui_proxy_service import _ProxySessionStore


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture()
def proxy_store() -> _ProxySessionStore:
    return _ProxySessionStore()


@pytest.fixture()
def tmp_profiles_dir(tmp_path: Path) -> Path:
    return tmp_path / "auth_profiles"


@pytest.fixture()
def auth_store(tmp_profiles_dir: Path) -> Generator[UiAuthProfileStore, None, None]:
    yield UiAuthProfileStore(profiles_dir=tmp_profiles_dir)


# ============================================================
# 1. _ProxySessionStore localStorage 方法测试
# ============================================================

class TestProxySessionStoreLocalStorage:
    """代理会话 localStorage 存储测试。"""

    def test_create_session_has_empty_local_storage(self, proxy_store: _ProxySessionStore) -> None:
        sid = proxy_store.create_session("http://example.com")
        ls = proxy_store.get_local_storage(sid)
        assert ls == {}

    def test_update_local_storage(self, proxy_store: _ProxySessionStore) -> None:
        sid = proxy_store.create_session("http://example.com")
        storage_data = {"token": "abc123", "user": "test_user", "theme": "dark"}
        proxy_store.update_local_storage(sid, "http://example.com", storage_data)
        ls = proxy_store.get_local_storage(sid)
        assert ls == {"http://example.com": storage_data}

    def test_update_local_storage_multiple_origins(self, proxy_store: _ProxySessionStore) -> None:
        sid = proxy_store.create_session("http://example.com")
        proxy_store.update_local_storage(
            sid, "http://example.com", {"token": "abc"}
        )
        proxy_store.update_local_storage(
            sid, "http://api.example.com", {"api_key": "xyz"}
        )
        ls = proxy_store.get_local_storage(sid)
        assert len(ls) == 2
        assert ls["http://example.com"] == {"token": "abc"}
        assert ls["http://api.example.com"] == {"api_key": "xyz"}

    def test_update_local_storage_overwrites_same_origin(self, proxy_store: _ProxySessionStore) -> None:
        sid = proxy_store.create_session("http://example.com")
        proxy_store.update_local_storage(
            sid, "http://example.com", {"token": "old"}
        )
        proxy_store.update_local_storage(
            sid, "http://example.com", {"token": "new", "extra": "value"}
        )
        ls = proxy_store.get_local_storage(sid)
        assert ls["http://example.com"] == {"token": "new", "extra": "value"}

    def test_update_local_storage_empty_data_ignored(self, proxy_store: _ProxySessionStore) -> None:
        sid = proxy_store.create_session("http://example.com")
        proxy_store.update_local_storage(sid, "http://example.com", {})
        ls = proxy_store.get_local_storage(sid)
        assert ls == {}

    def test_update_local_storage_invalid_session(self, proxy_store: _ProxySessionStore) -> None:
        # Should not raise
        proxy_store.update_local_storage("nonexistent", "http://example.com", {"k": "v"})

    def test_get_local_storage_invalid_session(self, proxy_store: _ProxySessionStore) -> None:
        ls = proxy_store.get_local_storage("nonexistent")
        assert ls == {}

    def test_clear_cookies_also_clears_local_storage(self, proxy_store: _ProxySessionStore) -> None:
        sid = proxy_store.create_session("http://example.com")
        proxy_store.update_local_storage(
            sid, "http://example.com", {"token": "abc"}
        )
        # Clear cookies by base_url
        cleared = proxy_store.clear_cookies_by_base_url("http://example.com/login")
        assert cleared >= 1
        # Local storage should also be cleared
        ls = proxy_store.get_local_storage(sid)
        assert ls == {}


# ============================================================
# 2. UiAuthProfileStore localStorage 字段测试
# ============================================================

class TestAuthProfileStoreLocalStorage:
    """认证档案 localStorage 字段支持测试。"""

    def test_save_profile_with_local_storage(self, auth_store: UiAuthProfileStore) -> None:
        profile_id = auth_store.save_profile({
            "name": "带 localStorage 的档案",
            "base_url": "http://example.com",
            "cookies": [{"name": "session", "value": "abc"}],
            "local_storage": {"token": "abc123", "user": "test"},
        })
        profile = auth_store.get_profile(profile_id)
        assert profile is not None
        assert profile["local_storage"] == {"token": "abc123", "user": "test"}

    def test_save_profile_without_local_storage(self, auth_store: UiAuthProfileStore) -> None:
        profile_id = auth_store.save_profile({
            "name": "仅 Cookie 档案",
            "base_url": "http://example.com",
            "cookies": [{"name": "session", "value": "abc"}],
        })
        profile = auth_store.get_profile(profile_id)
        assert profile is not None
        assert profile["local_storage"] == {}

    def test_list_profiles_includes_local_storage_count(self, auth_store: UiAuthProfileStore) -> None:
        auth_store.save_profile({
            "name": "档案1",
            "base_url": "http://a.com",
            "cookies": [],
            "local_storage": {"k1": "v1", "k2": "v2"},
        })
        auth_store.save_profile({
            "name": "档案2",
            "base_url": "http://b.com",
            "cookies": [],
            "local_storage": {"k1": "v1"},
        })
        profiles = auth_store.list_profiles()
        assert len(profiles) == 2
        # Sort by name for deterministic assertions
        profiles.sort(key=lambda p: p["name"])
        assert profiles[0]["local_storage_count"] == 2
        assert profiles[1]["local_storage_count"] == 1

    def test_export_storage_state_with_local_storage(self, auth_store: UiAuthProfileStore) -> None:
        profile_id = auth_store.save_profile({
            "name": "导出测试",
            "base_url": "http://example.com",
            "cookies": [{"name": "session", "value": "abc"}],
            "local_storage": {"token": "xyz", "theme": "dark"},
        })
        state = auth_store.export_storage_state(profile_id)
        assert state is not None
        assert len(state["cookies"]) == 1
        assert len(state["origins"]) == 1
        assert state["origins"][0]["origin"] == "http://example.com"
        ls_items = state["origins"][0]["localStorage"]
        assert len(ls_items) == 2
        names = {item["name"] for item in ls_items}
        assert "token" in names
        assert "theme" in names

    def test_export_storage_state_without_local_storage(self, auth_store: UiAuthProfileStore) -> None:
        profile_id = auth_store.save_profile({
            "name": "无 localStorage",
            "base_url": "http://example.com",
            "cookies": [{"name": "session", "value": "abc"}],
        })
        state = auth_store.export_storage_state(profile_id)
        assert state is not None
        assert state["origins"] == []

    def test_export_storage_state_empty_local_storage(self, auth_store: UiAuthProfileStore) -> None:
        """local_storage 为空字典时，origins 应为空。"""
        profile_id = auth_store.save_profile({
            "name": "空 localStorage",
            "base_url": "http://example.com",
            "cookies": [],
            "local_storage": {},
        })
        state = auth_store.export_storage_state(profile_id)
        assert state is not None
        assert state["origins"] == []


# ============================================================
# 3. _write_auth_state_temp localStorage 写入测试
# ============================================================

class TestWriteAuthStateTemp:
    """_write_auth_state_temp localStorage 写入测试。"""

    def test_write_auth_state_with_local_storage(self, tmp_path: Path) -> None:
        from postman_api_tester.handlers.ui_execution_routes import _write_auth_state_temp

        profile: Dict[str, Any] = {
            "cookies": [{"name": "session", "value": "abc"}],
            "base_url": "http://example.com",
            "local_storage": {"token": "xyz", "theme": "dark"},
        }

        # Patch temp dir to use tmp_path
        with patch("postman_api_tester.handlers.ui_execution_routes.os.getcwd", return_value=str(tmp_path)):
            path = _write_auth_state_temp("test-job", profile)

        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["cookies"]) == 1
        assert len(data["origins"]) == 1
        assert data["origins"][0]["origin"] == "http://example.com"
        ls_names = {item["name"] for item in data["origins"][0]["localStorage"]}
        assert "token" in ls_names
        assert "theme" in ls_names

        # Cleanup
        os.unlink(path)

    def test_write_auth_state_without_local_storage(self, tmp_path: Path) -> None:
        from postman_api_tester.handlers.ui_execution_routes import _write_auth_state_temp

        profile: Dict[str, Any] = {
            "cookies": [{"name": "session", "value": "abc"}],
            "base_url": "http://example.com",
        }

        with patch("postman_api_tester.handlers.ui_execution_routes.os.getcwd", return_value=str(tmp_path)):
            path = _write_auth_state_temp("test-job-2", profile)

        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["origins"] == []

        # Cleanup
        os.unlink(path)

    def test_write_auth_state_local_storage_without_base_url(self, tmp_path: Path) -> None:
        """有 local_storage 但无 base_url 时，origins 应为空。"""
        from postman_api_tester.handlers.ui_execution_routes import _write_auth_state_temp

        profile: Dict[str, Any] = {
            "cookies": [],
            "base_url": "",
            "local_storage": {"token": "xyz"},
        }

        with patch("postman_api_tester.handlers.ui_execution_routes.os.getcwd", return_value=str(tmp_path)):
            path = _write_auth_state_temp("test-job-3", profile)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["origins"] == []

        # Cleanup
        os.unlink(path)


# ============================================================
# 4. 录制 localStorage 端点测试
# ============================================================

class TestRecordingLocalStorageEndpoint:
    """api_ui_testing_recording_local_storage 端点测试。"""

    def _get_app(self) -> Any:
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    def test_endpoint_missing_session_id(self) -> None:
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_local_storage,
        )

        app = self._get_app()
        with app.test_request_context(
            "/api/ui-testing/recording/local-storage",
            method="POST",
            json={"origin": "http://example.com", "local_storage": {}},
        ):
            resp = api_ui_testing_recording_local_storage()
            assert resp[1] == 400

    def test_endpoint_missing_origin(self) -> None:
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_local_storage,
        )

        app = self._get_app()
        with app.test_request_context(
            "/api/ui-testing/recording/local-storage",
            method="POST",
            json={"session_id": "test-sid", "local_storage": {}},
        ):
            resp = api_ui_testing_recording_local_storage()
            assert resp[1] == 400

    def test_endpoint_stores_directly_to_proxy_session(self) -> None:
        """新行为：session_id 直接作为代理会话 ID，无需录制会话存在。"""
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_local_storage,
        )
        from postman_api_tester.services.ui_proxy_service import _ProxySessionStore

        app = self._get_app()
        # 手动创建一个代理会话
        proxy_store = _ProxySessionStore()
        proxy_sid = proxy_store.create_session("http://example.com")

        with app.test_request_context(
            "/api/ui-testing/recording/local-storage",
            method="POST",
            json={
                "session_id": proxy_sid,
                "origin": "http://example.com",
                "local_storage": {"token": "abc"},
            },
        ):
            # 需要临时替换全局 _proxy_session_store
            import postman_api_tester.handlers.ui_testing_routes as routes_module
            original_store = routes_module._proxy_session_store
            routes_module._proxy_session_store = proxy_store
            try:
                resp = api_ui_testing_recording_local_storage()
                # Should return 200 with stored=True
                assert resp[1] == 200
                # Verify localStorage was stored
                stored = proxy_store.get_local_storage(proxy_sid)
                assert stored == {"http://example.com": {"token": "abc"}}
            finally:
                routes_module._proxy_session_store = original_store

    def test_endpoint_creates_proxy_session_if_missing(self) -> None:
        """代理会话不存在时自动创建。"""
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_local_storage,
        )
        from postman_api_tester.services.ui_recording_store import RecordingSessionStore
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_recording = RecordingSessionStore(storage_dir=tmp_dir)
            # 手动创建一个录制会话
            test_session = test_recording.start("test-sid-123", "http://example.com")
            assert test_session is not None

            app = self._get_app()
            with app.test_request_context(
                "/api/ui-testing/recording/local-storage",
                method="POST",
                json={
                    "session_id": "test-sid-123",
                    "origin": "http://example.com",
                    "local_storage": {"token": "abc"},
                },
            ), patch("postman_api_tester.handlers.ui_testing_routes._recording", test_recording):
                resp = api_ui_testing_recording_local_storage()
                resp_data = json.loads(resp[0].get_data(as_text=True))
                assert resp_data["data"]["ok"] is True
                assert resp_data["data"]["stored"] is True


# ============================================================
# 5. 录制停止 localStorage 导出测试
# ============================================================

class TestRecordingStopLocalStorageExport:
    """api_ui_testing_recording_stop localStorage 导出测试。"""

    def _get_app(self) -> Any:
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    def test_stop_returns_local_storage_for_export(self) -> None:
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_stop,
        )

        mock_session = {
            "steps": [{"action": "click"}],
            "base_url": "http://example.com/login",
            "ended_at": "2026-08-25T00:00:00",
        }

        app = self._get_app()
        with app.test_request_context(
            "/api/ui-testing/recording/stop",
            method="POST",
            json={"session_id": "test-sid"},
        ), \
             patch("postman_api_tester.handlers.ui_testing_routes._recording") as mock_rec, \
             patch("postman_api_tester.handlers.ui_testing_routes._proxy_session_store") as mock_store:
            mock_rec.stop.return_value = mock_session
            mock_store.find_session_by_base_url.return_value = "proxy-sid"
            mock_store.get_cookie_jar.return_value = []
            mock_store.get_local_storage.return_value = {
                "http://example.com": {"token": "abc123", "user": "test"},
            }

            resp = api_ui_testing_recording_stop()
            resp_data = json.loads(resp[0].get_data(as_text=True))
            data = resp_data["data"]
            assert "local_storage_for_export" in data
            assert data["local_storage_for_export"] == {"token": "abc123", "user": "test"}

    def test_stop_returns_empty_local_storage(self) -> None:
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_stop,
        )

        mock_session = {
            "steps": [],
            "base_url": "http://example.com",
            "ended_at": "2026-08-25T00:00:00",
        }

        app = self._get_app()
        with app.test_request_context(
            "/api/ui-testing/recording/stop",
            method="POST",
            json={"session_id": "test-sid"},
        ), \
             patch("postman_api_tester.handlers.ui_testing_routes._recording") as mock_rec, \
             patch("postman_api_tester.handlers.ui_testing_routes._proxy_session_store") as mock_store:
            mock_rec.stop.return_value = mock_session
            mock_store.find_session_by_base_url.return_value = "proxy-sid"
            mock_store.get_cookie_jar.return_value = []
            mock_store.get_local_storage.return_value = {}

            resp = api_ui_testing_recording_stop()
            resp_data = json.loads(resp[0].get_data(as_text=True))
            data = resp_data["data"]
            assert data["local_storage_for_export"] == {}


# ============================================================
# 6. 录制时 JS 注入逻辑测试
# ============================================================

class TestStorageCollectInjection:
    """录制模式 localStorage 收集 JS 注入验证。"""

    def test_recording_mode_injects_storage_collect(self) -> None:
        from postman_api_tester.services.ui_proxy_service import UiProxyService

        html = "<html><head></head><body></body></html>"
        result = UiProxyService._inject_early_script(
            html=html,
            origin="http://proxy.example.com",
            target_url="http://example.com",
            recording_mode=True,
            session_id="test-session-123",
        )
        # Should contain localStorage collection code
        assert "localStorage" in result
        assert "recording/local-storage" in result
        assert "test-session-123" in result
        assert "beforeunload" in result

    def test_replay_mode_no_storage_collect(self) -> None:
        from postman_api_tester.services.ui_proxy_service import UiProxyService

        html = "<html><head></head><body></body></html>"
        result = UiProxyService._inject_early_script(
            html=html,
            origin="http://proxy.example.com",
            target_url="http://example.com",
            replay_mode=True,
            session_id="test-session-456",
        )
        # Replay mode should NOT contain storage collection endpoint call
        assert "recording/local-storage" not in result

    def test_no_mode_no_storage_collect(self) -> None:
        from postman_api_tester.services.ui_proxy_service import UiProxyService

        html = "<html><head></head><body></body></html>"
        result = UiProxyService._inject_early_script(
            html=html,
            origin="http://proxy.example.com",
            target_url="http://example.com",
        )
        assert "recording/local-storage" not in result

    def test_recording_mode_session_id_escaped(self) -> None:
        """session_id 中的特殊字符应被正确转义。"""
        from postman_api_tester.services.ui_proxy_service import UiProxyService

        html = "<html><head></head><body></body></html>"
        result = UiProxyService._inject_early_script(
            html=html,
            origin="http://proxy.example.com",
            target_url="http://example.com",
            recording_mode=True,
            session_id='session"with"quotes',
        )
        # The quotes in session_id should be escaped
        assert 'session\\"with\\"quotes' in result


# ============================================================
# 7. 端到端集成测试（模拟完整录制流程）
# ============================================================

class TestEndToEndLocalStorageFlow:
    """端到端 localStorage 流程模拟测试。"""

    def test_full_flow_collect_store_export(self) -> None:
        """模拟完整流程：收集 → 存储 → 导出 → 写入 storage_state。"""
        # Step 1: 创建代理会话并存储 localStorage
        proxy_store = _ProxySessionStore()
        proxy_sid = proxy_store.create_session("http://example.com")
        proxy_store.update_local_storage(
            proxy_sid,
            "http://example.com",
            {"token": "jwt-token-123", "user_name": "test_user"},
        )

        # Step 2: 导出 localStorage
        all_ls = proxy_store.get_local_storage(proxy_sid)
        merged_ls: Dict[str, str] = {}
        for origin_data in all_ls.values():
            merged_ls.update(origin_data)

        assert merged_ls == {"token": "jwt-token-123", "user_name": "test_user"}

        # Step 3: 保存为认证档案
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_store = UiAuthProfileStore(profiles_dir=Path(tmp_dir))
            profile_id = auth_store.save_profile({
                "name": "测试档案",
                "base_url": "http://example.com",
                "cookies": [{"name": "session", "value": "abc"}],
                "local_storage": merged_ls,
            })

            # Step 4: 导出 storage_state
            state = auth_store.export_storage_state(profile_id)
            assert state is not None
            assert len(state["origins"]) == 1
            assert state["origins"][0]["origin"] == "http://example.com"
            ls_items = state["origins"][0]["localStorage"]
            names = {item["name"] for item in ls_items}
            assert "token" in names
            assert "user_name" in names

            # Step 5: 写入临时文件（模拟 _write_auth_state_temp）
            state_path = os.path.join(tmp_dir, "auth_state_test.json")
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)

            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert len(loaded["origins"]) == 1
            assert loaded["origins"][0]["origin"] == "http://example.com"
