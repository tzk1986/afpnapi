"""认证档案存储服务测试。

覆盖 UiAuthProfileStore 的文件持久化功能：
- CRUD 操作
- 过期检查
- storage_state 导出
- 过期清理
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from postman_api_tester.services.ui_auth_profile_store import UiAuthProfileStore


@pytest.fixture()
def tmp_profiles_dir(tmp_path: Path) -> Path:
    return tmp_path / "auth_profiles"


@pytest.fixture()
def store(tmp_profiles_dir: Path) -> Generator[UiAuthProfileStore, None, None]:
    yield UiAuthProfileStore(profiles_dir=tmp_profiles_dir)


def _write_profile_file(directory: Path, profile: Dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile['id']}.json"
    path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")


class TestSaveAndGetProfile:
    """保存和获取认证档案。"""

    def test_save_new_profile(self, store: UiAuthProfileStore) -> None:
        profile_id = store.save_profile(
            {
                "name": "测试档案",
                "base_url": "http://example.com",
                "cookies": [{"name": "session", "value": "abc123"}],
            }
        )
        assert profile_id.startswith("auth_")
        profile = store.get_profile(profile_id)
        assert profile is not None
        assert profile["name"] == "测试档案"
        assert profile["base_url"] == "http://example.com"
        assert len(profile["cookies"]) == 1

    def test_save_with_custom_id(self, store: UiAuthProfileStore) -> None:
        profile_id = store.save_profile({"id": "auth_custom123", "name": "自定义"})
        assert profile_id == "auth_custom123"
        profile = store.get_profile(profile_id)
        assert profile is not None
        assert profile["id"] == "auth_custom123"

    def test_get_nonexistent_profile(self, store: UiAuthProfileStore) -> None:
        assert store.get_profile("auth_nonexistent") is None

    def test_update_existing_profile(self, store: UiAuthProfileStore) -> None:
        profile_id = store.save_profile({"name": "初始名称"})
        store.save_profile({"id": profile_id, "name": "更新名称"})
        profile = store.get_profile(profile_id)
        assert profile is not None
        assert profile["name"] == "更新名称"


class TestListProfiles:
    """列出认证档案。"""

    def test_list_empty(self, store: UiAuthProfileStore) -> None:
        assert store.list_profiles() == []

    def test_list_multiple(self, store: UiAuthProfileStore) -> None:
        store.save_profile({"name": "档案1"})
        store.save_profile({"name": "档案2"})
        profiles = store.list_profiles()
        assert len(profiles) == 2
        names = {p["name"] for p in profiles}
        assert names == {"档案1", "档案2"}

    def test_list_summary_no_cookies(self, store: UiAuthProfileStore) -> None:
        store.save_profile(
            {
                "name": "测试",
                "cookies": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            }
        )
        profiles = store.list_profiles()
        assert len(profiles) == 1
        # 摘要只包含 cookie_count，不包含完整 cookies
        assert "cookies" not in profiles[0]
        assert profiles[0]["cookie_count"] == 3


class TestDeleteProfile:
    """删除认证档案。"""

    def test_delete_existing(self, store: UiAuthProfileStore) -> None:
        profile_id = store.save_profile({"name": "待删除"})
        assert store.delete_profile(profile_id) is True
        assert store.get_profile(profile_id) is None

    def test_delete_nonexistent(self, store: UiAuthProfileStore) -> None:
        assert store.delete_profile("auth_nonexistent") is False


class TestExpiration:
    """过期检查和清理。"""

    def test_not_expired_when_no_expires_at(self, store: UiAuthProfileStore) -> None:
        profile = {"name": "永不过期", "expires_at": None}
        assert store.is_expired(profile) is False

    def test_not_expired_when_future(self, store: UiAuthProfileStore) -> None:
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        profile = {"name": "未过期", "expires_at": future}
        assert store.is_expired(profile) is False

    def test_expired_when_past(self, store: UiAuthProfileStore) -> None:
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        profile = {"name": "已过期", "expires_at": past}
        assert store.is_expired(profile) is True

    def test_cleanup_expired(self, store: UiAuthProfileStore) -> None:
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        store.save_profile({"name": "已过期", "expires_at": past})
        store.save_profile({"name": "未过期", "expires_at": future})
        store.save_profile({"name": "永不过期", "expires_at": None})
        removed = store.cleanup_expired()
        assert removed == 1
        assert len(store.list_profiles()) == 2


class TestExportStorageState:
    """导出 Playwright storage_state 格式。"""

    def test_export_valid_profile(self, store: UiAuthProfileStore) -> None:
        profile_id = store.save_profile(
            {
                "name": "测试",
                "cookies": [{"name": "session", "value": "abc"}],
            }
        )
        state = store.export_storage_state(profile_id)
        assert state is not None
        assert "cookies" in state
        assert "origins" in state
        assert state["origins"] == []
        assert len(state["cookies"]) == 1

    def test_export_nonexistent_returns_none(self, store: UiAuthProfileStore) -> None:
        assert store.export_storage_state("auth_nonexistent") is None

    def test_export_expired_returns_none(self, store: UiAuthProfileStore) -> None:
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        profile_id = store.save_profile({"name": "过期", "expires_at": past})
        assert store.export_storage_state(profile_id) is None


class TestFindByBaseUrl:
    """按 base_url 查找认证档案。"""

    def test_find_matching(self, store: UiAuthProfileStore) -> None:
        store.save_profile({"name": "档案1", "base_url": "http://a.com"})
        store.save_profile({"name": "档案2", "base_url": "http://b.com"})
        found = store.find_by_base_url("http://b.com")
        assert found is not None
        assert found["name"] == "档案2"

    def test_find_no_match(self, store: UiAuthProfileStore) -> None:
        store.save_profile({"name": "档案1", "base_url": "http://a.com"})
        assert store.find_by_base_url("http://c.com") is None


class TestCorruptedFile:
    """损坏文件处理。"""

    def test_corrupted_file_skipped_in_list(self, tmp_profiles_dir: Path) -> None:
        tmp_profiles_dir.mkdir(parents=True, exist_ok=True)
        bad_path = tmp_profiles_dir / "auth_bad.json"
        bad_path.write_text("not valid json{{{", encoding="utf-8")
        store = UiAuthProfileStore(profiles_dir=tmp_profiles_dir)
        # 损坏的文件应被跳过，不抛异常
        profiles = store.list_profiles()
        assert profiles == []

    def test_corrupted_file_returns_none(self, tmp_profiles_dir: Path) -> None:
        tmp_profiles_dir.mkdir(parents=True, exist_ok=True)
        bad_path = tmp_profiles_dir / "auth_bad2.json"
        bad_path.write_text("not valid json{{{", encoding="utf-8")
        store = UiAuthProfileStore(profiles_dir=tmp_profiles_dir)
        assert store.get_profile("auth_bad2") is None
