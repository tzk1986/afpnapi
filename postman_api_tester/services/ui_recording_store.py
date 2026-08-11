"""录制会话内存存储（线程安全）。

合并原 ``ui_testing_routes._RecordingSession`` 与
``ui_recorder_routes._RecordingSessionStore`` 两个内联类，
同时支持浏览器回放录制和 Chrome 扩展录制两种场景。
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class RecordingSessionStore:
    """录制会话内存存储。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

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
            return self._sessions.pop(session_id, None) is not None
