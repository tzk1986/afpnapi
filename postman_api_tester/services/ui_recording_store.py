"""录制会话存储（线程安全 + 文件持久化）。

合并原 ``ui_testing_routes._RecordingSession`` 与
``ui_recorder_routes._RecordingSessionStore`` 两个内联类，
同时支持浏览器回放录制和 Chrome 扩展录制两种场景。

v1.33.35 新增文件持久化：
- 每 30 秒自动保存到 JSON 文件（原子写入）
- 服务启动时自动恢复未完成的录制会话
- 会话结束或删除时同步清理磁盘文件
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from postman_api_tester.config import UI_RECORDING_SESSIONS_DIR

logger = logging.getLogger(__name__)

# 自动保存间隔（秒）
_AUTO_SAVE_INTERVAL = 30


class RecordingSessionStore:
    """录制会话存储，支持内存 + 文件持久化。

    当 ``storage_dir`` 为空时仅使用内存模式（无文件 I/O、无后台线程）。
    生产环境通过 ``config.UI_RECORDING_SESSIONS_DIR`` 传入目录开启持久化。
    """

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._storage_dir: str = (storage_dir or UI_RECORDING_SESSIONS_DIR or "").strip()
        self._stop_event = threading.Event()
        self._auto_save_started = False
        if self._storage_dir:
            self._ensure_storage_dir()
            self._restore_sessions()
            self._start_auto_save()

    def _ensure_storage_dir(self) -> None:
        """确保存储目录存在。"""
        if not self._storage_dir:
            return
        try:
            os.makedirs(self._storage_dir, exist_ok=True)
        except OSError:
            logger.exception(
                "Failed to create recording storage dir: %s",
                self._storage_dir,
                extra={"event": "ui.proxy.session.dir_create_failed"},
            )
            self._storage_dir = ""

    def _session_file_path(self, session_id: str) -> str:
        """返回会话 JSON 文件的完整路径。"""
        safe_id = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in session_id
        )
        return os.path.join(self._storage_dir, f"{safe_id}.json")

    def _save_session_to_disk(self, session: Dict[str, Any]) -> None:
        """原子写入会话 JSON 文件（调用方须持有 _lock）。"""
        if not self._storage_dir:
            return
        file_path = self._session_file_path(session["session_id"])
        tmp_path = file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(session, f, ensure_ascii=False, default=str)
            os.replace(tmp_path, file_path)
        except OSError:
            logger.exception(
                "Failed to persist recording session: %s",
                session["session_id"],
                extra={"event": "ui.proxy.session.save_failed"},
            )
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _delete_session_file(self, session_id: str) -> None:
        """删除会话 JSON 文件（调用方须持有 _lock）。"""
        if not self._storage_dir:
            return
        file_path = self._session_file_path(session_id)
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except OSError:
            logger.exception(
                "Failed to delete recording session file: %s",
                session_id,
                extra={"event": "ui.proxy.session.file_delete_failed"},
            )

    def _restore_sessions(self) -> None:
        """从磁盘恢复未完成的录制会话。"""
        if not os.path.isdir(self._storage_dir):
            return
        restored = 0
        failed = 0
        try:
            entries = os.listdir(self._storage_dir)
        except OSError:
            logger.exception(
                "Failed to scan recording storage dir: %s",
                self._storage_dir,
                extra={"event": "ui.proxy.session.dir_scan_failed"},
            )
            return
        for fname in entries:
            if not fname.endswith(".json"):
                continue
            file_path = os.path.join(self._storage_dir, fname)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    session = json.load(f)
                sid = session.get("session_id")
                if not sid:
                    continue
                # 仅恢复 recording 状态的会话；completed 的标记为 completed
                if session.get("status") == "recording":
                    session["status"] = "restored"
                self._sessions[sid] = session
                restored += 1
            except (OSError, json.JSONDecodeError, KeyError):
                logger.exception(
                    "Failed to restore recording session from: %s",
                    file_path,
                    extra={"event": "ui.proxy.session.load_failed"},
                )
                failed += 1
        if restored or failed:
            logger.info(
                "Recording sessions restored: %d ok, %d failed",
                restored,
                failed,
                extra={"event": "ui.proxy.session.sessions_restored"},
            )

    def _start_auto_save(self) -> None:
        """启动自动保存后台线程。"""
        if self._auto_save_started or not self._storage_dir:
            return
        self._auto_save_started = True
        t = threading.Thread(
            target=self._auto_save_loop, daemon=True, name="recording-auto_save"
        )
        t.start()

    def _auto_save_loop(self) -> None:
        """每 30 秒自动保存所有活跃会话。"""
        while not self._stop_event.wait(_AUTO_SAVE_INTERVAL):
            self._do_auto_save()

    def _do_auto_save(self) -> None:
        """执行一次自动保存。"""
        if not self._storage_dir:
            return
        with self._lock:
            for session in self._sessions.values():
                self._save_session_to_disk(session)

    def shutdown(self) -> None:
        """停止自动保存线程并执行最终保存。"""
        self._stop_event.set()
        if self._auto_save_started:
            self._do_auto_save()

    def start(self, session_id: str, base_url: str = "") -> Dict[str, Any]:
        session: Dict[str, Any] = {
            "session_id": session_id,
            "base_url": base_url,
            "steps": [],
            "navigations": [],
            "status": "recording",
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
            "total_steps": 0,
        }
        with self._lock:
            self._sessions[session_id] = session
            self._save_session_to_disk(session)
        return session

    create_session = start

    def add_event(
        self, session_id: str, event_type: str, data: Dict[str, Any]
    ) -> Optional[int]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            if event_type == "step":
                session["steps"].append(data)
                session["total_steps"] = len(session["steps"])
                return session["total_steps"]
            elif event_type == "navigation":
                session["navigations"].append(data)
                return len(session["navigations"])
            return 0

    def add_step(self, session_id: str, step: Dict[str, Any]) -> Optional[int]:
        return self.add_event(session_id, "step", step)

    def stop(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session["status"] = "completed"
            session["ended_at"] = datetime.now().isoformat()
            self._delete_session_file(session_id)
            return dict(session)

    def end_session(self, session_id: str, total_steps: int = 0) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session["status"] = "completed"
            session["ended_at"] = datetime.now().isoformat()
            if total_steps:
                session["total_steps"] = total_steps
            self._delete_session_file(session_id)
            return True

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                return dict(session)
            return None

    get_session = get

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            result = [
                {
                    "session_id": s["session_id"],
                    "base_url": s.get("base_url", ""),
                    "status": s["status"],
                    "step_count": s.get("total_steps", len(s.get("steps", []))),
                    "total_steps": s.get("total_steps", len(s.get("steps", []))),
                    "started_at": s["started_at"],
                    "ended_at": s.get("ended_at"),
                }
                for s in self._sessions.values()
            ]
            result.sort(key=lambda x: x["started_at"], reverse=True)
            return result

    def update_step_response(
        self, session_id: str, net_id: int, network_response: Dict[str, Any]
    ) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            for step in reversed(session["steps"]):
                if (
                    step.get("action") == "api_call"
                    and step.get("_net_id") == net_id
                ):
                    step["network_response"] = network_response
                    return True
            return False

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(session_id, None)
            if removed is not None:
                self._delete_session_file(session_id)
                return True
            return False
