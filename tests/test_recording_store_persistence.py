"""录制会话持久化测试。

覆盖 RecordingSessionStore 的文件持久化功能：
- 创建会话自动写磁盘
- 停止/删除会话清理磁盘文件
- 服务重启后恢复会话
- 损坏文件优雅降级
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Generator

import pytest

from postman_api_tester.services.ui_recording_store import RecordingSessionStore


@pytest.fixture()
def tmp_storage(tmp_path) -> str:
    return str(tmp_path / "sessions")


@pytest.fixture()
def store(tmp_storage) -> Generator[RecordingSessionStore, None, None]:
    s = RecordingSessionStore(storage_dir=tmp_storage)
    try:
        yield s
    finally:
        s.shutdown()


def _write_session_file(directory: str, session: Dict[str, Any]) -> None:
    os.makedirs(directory, exist_ok=True)
    safe_id = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in session["session_id"]
    )
    path = os.path.join(directory, f"{safe_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False)


class TestMemoryOnlyMode:
    """无 storage_dir 时纯内存模式。"""

    def test_no_persistence_by_default(self) -> None:
        s = RecordingSessionStore()
        s.start("sess-1", "http://example.com")
        assert s.get("sess-1") is not None
        # 不应创建任何文件
        assert not hasattr(s, "_storage_dir") or not s._storage_dir

    def test_start_and_get(self) -> None:
        s = RecordingSessionStore()
        result = s.start("sess-1", "http://example.com")
        assert result["session_id"] == "sess-1"
        assert result["status"] == "recording"
        assert s.get("sess-1") is not None

    def test_list_sessions(self) -> None:
        s = RecordingSessionStore()
        s.start("sess-1")
        s.start("sess-2")
        sessions = s.list_sessions()
        assert len(sessions) == 2

    def test_stop_session(self) -> None:
        s = RecordingSessionStore()
        s.start("sess-1")
        result = s.stop("sess-1")
        assert result is not None
        assert result["status"] == "completed"

    def test_delete_session(self) -> None:
        s = RecordingSessionStore()
        s.start("sess-1")
        assert s.delete_session("sess-1") is True
        assert s.get("sess-1") is None
        assert s.delete_session("sess-1") is False


class TestFilePersistence:
    """带 storage_dir 时文件持久化。"""

    def test_start_creates_file(self, store: RecordingSessionStore, tmp_storage: str) -> None:
        store.start("sess-1", "http://example.com")
        expected = os.path.join(tmp_storage, "sess-1.json")
        assert os.path.exists(expected)
        with open(expected, encoding="utf-8") as f:
            data = json.load(f)
        assert data["session_id"] == "sess-1"
        assert data["base_url"] == "http://example.com"
        assert data["status"] == "recording"

    def test_stop_deletes_file(self, store: RecordingSessionStore, tmp_storage: str) -> None:
        store.start("sess-1")
        file_path = os.path.join(tmp_storage, "sess-1.json")
        assert os.path.exists(file_path)
        store.stop("sess-1")
        assert not os.path.exists(file_path)

    def test_end_session_deletes_file(self, store: RecordingSessionStore, tmp_storage: str) -> None:
        store.start("sess-1")
        file_path = os.path.join(tmp_storage, "sess-1.json")
        assert os.path.exists(file_path)
        store.end_session("sess-1", total_steps=5)
        assert not os.path.exists(file_path)

    def test_delete_session_deletes_file(self, store: RecordingSessionStore, tmp_storage: str) -> None:
        store.start("sess-1")
        file_path = os.path.join(tmp_storage, "sess-1.json")
        assert os.path.exists(file_path)
        store.delete_session("sess-1")
        assert not os.path.exists(file_path)

    def test_restore_sessions_on_startup(self, tmp_storage: str) -> None:
        session_data = {
            "session_id": "restore-test",
            "base_url": "http://test.com",
            "steps": [{"action": "click", "selector": "#btn"}],
            "navigations": [],
            "status": "recording",
            "started_at": "2026-01-01T00:00:00",
            "ended_at": None,
            "total_steps": 1,
        }
        _write_session_file(tmp_storage, session_data)

        s = RecordingSessionStore(storage_dir=tmp_storage)
        try:
            restored = s.get("restore-test")
            assert restored is not None
            assert restored["status"] == "restored"
            assert restored["base_url"] == "http://test.com"
            assert len(restored["steps"]) == 1
        finally:
            s.shutdown()

    def test_restore_completed_session_keeps_status(self, tmp_storage: str) -> None:
        session_data = {
            "session_id": "completed-test",
            "base_url": "",
            "steps": [],
            "navigations": [],
            "status": "completed",
            "started_at": "2026-01-01T00:00:00",
            "ended_at": "2026-01-01T00:01:00",
            "total_steps": 0,
        }
        _write_session_file(tmp_storage, session_data)

        s = RecordingSessionStore(storage_dir=tmp_storage)
        try:
            restored = s.get("completed-test")
            assert restored is not None
            assert restored["status"] == "completed"
        finally:
            s.shutdown()

    def test_corrupted_file_skipped(self, tmp_storage: str, caplog) -> None:
        import logging

        os.makedirs(tmp_storage, exist_ok=True)
        bad_path = os.path.join(tmp_storage, "bad-session.json")
        with open(bad_path, "w") as f:
            f.write("not valid json{{{")

        with caplog.at_level(logging.ERROR, logger="postman_api_tester.services.ui_recording_store"):
            s = RecordingSessionStore(storage_dir=tmp_storage)
            try:
                assert s.get("bad-session") is None
                assert any(
                    getattr(r, "event", "") == "ui.proxy.session.load_failed"
                    for r in caplog.records
                )
            finally:
                s.shutdown()

    def test_missing_session_id_skipped(self, tmp_storage: str) -> None:
        os.makedirs(tmp_storage, exist_ok=True)
        path = os.path.join(tmp_storage, "no-id.json")
        with open(path, "w") as f:
            json.dump({"status": "recording", "steps": []}, f)

        s = RecordingSessionStore(storage_dir=tmp_storage)
        try:
            assert s.list_sessions() == []
        finally:
            s.shutdown()

    def test_add_step_persisted_via_autosave(self, store: RecordingSessionStore, tmp_storage: str) -> None:
        store.start("sess-1")
        store.add_step("sess-1", {"action": "click", "selector": "#btn"})
        # 手动触发 auto-save
        store._do_auto_save()
        file_path = os.path.join(tmp_storage, "sess-1.json")
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["steps"]) == 1
        assert data["steps"][0]["action"] == "click"

    def test_special_chars_in_session_id(self, store: RecordingSessionStore, tmp_storage: str) -> None:
        store.start("sess/with:special<>chars")
        expected_files = [f for f in os.listdir(tmp_storage) if f.endswith(".json")]
        assert len(expected_files) == 1
        # 文件名应只包含安全字符
        fname = expected_files[0]
        assert "/" not in fname
        assert ":" not in fname

    def test_shutdown_saves_final_state(self, tmp_storage: str) -> None:
        s = RecordingSessionStore(storage_dir=tmp_storage)
        s.start("final-save")
        s.add_step("final-save", {"action": "type"})
        s.shutdown()

        file_path = os.path.join(tmp_storage, "final-save.json")
        assert os.path.exists(file_path)
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["steps"]) == 1

    def test_storage_dir_creation_failure_disables_persistence(
        self, tmp_path, monkeypatch
    ) -> None:
        # 让 makedirs 失败
        import postman_api_tester.services.ui_recording_store as mod

        def fake_makedirs(path: str, **kwargs: Any) -> None:
            raise OSError("Permission denied")

        monkeypatch.setattr(mod.os, "makedirs", fake_makedirs)
        s = RecordingSessionStore(storage_dir="/readonly/path")
        try:
            assert s._storage_dir == ""
            s.start("sess-1")
            assert s.get("sess-1") is not None
        finally:
            s.shutdown()
