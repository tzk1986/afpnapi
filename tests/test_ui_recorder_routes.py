"""UI 录制器路由单元测试。"""

import json
from typing import Generator

import pytest
from flask import Flask

from postman_api_tester.handlers.ui_recorder_routes import (
    _RecordingSessionStore,
    api_ui_recorder_event,
    api_ui_recorder_session_delete,
    api_ui_recorder_session_detail,
    api_ui_recorder_session_export,
    api_ui_recorder_sessions,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Generator[Flask, None, None]:
    """提供 Flask 测试应用（注册 UI 录制器路由）。"""
    app = Flask(__name__)
    app.config["TESTING"] = True

    from postman_api_tester.handlers.ui_recorder_routes import (
        api_ui_recorder_event,
        api_ui_recorder_sessions,
        api_ui_recorder_session_detail,
        api_ui_recorder_session_delete,
        api_ui_recorder_session_export,
    )

    app.add_url_rule("/api/ui-recorder/event", "api_ui_recorder_event", api_ui_recorder_event, methods=["POST"])
    app.add_url_rule("/api/ui-recorder/sessions", "api_ui_recorder_sessions", api_ui_recorder_sessions)
    app.add_url_rule("/api/ui-recorder/session/<path:session_id>", "api_ui_recorder_session_detail", api_ui_recorder_session_detail)
    app.add_url_rule("/api/ui-recorder/session/<path:session_id>", "api_ui_recorder_session_delete", api_ui_recorder_session_delete, methods=["DELETE"])
    app.add_url_rule("/api/ui-recorder/session/<path:session_id>/export", "api_ui_recorder_session_export", api_ui_recorder_session_export)

    yield app


@pytest.fixture  # type: ignore[untyped-decorator]
def client(app: Flask):
    """Flask 测试客户端。"""
    return app.test_client()


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context(app: Flask) -> Generator[None, None, None]:
    """Flask 应用上下文。"""
    with app.test_request_context():
        yield


class TestRecordingSessionStore:
    """录制会话存储单元测试。"""

    def test_create_session(self) -> None:
        store = _RecordingSessionStore()
        session = store.create_session("test_001")
        assert session["session_id"] == "test_001"
        assert session["status"] == "recording"
        assert session["steps"] == []

    def test_add_step_event(self) -> None:
        store = _RecordingSessionStore()
        store.create_session("test_001")
        idx = store.add_event("test_001", "step", {"action": "click", "selector": "#btn"})
        assert idx == 1
        session = store.get_session("test_001")
        assert session is not None
        assert len(session["steps"]) == 1
        assert session["steps"][0]["action"] == "click"

    def test_add_navigation_event(self) -> None:
        store = _RecordingSessionStore()
        store.create_session("test_001")
        idx = store.add_event("test_001", "navigation", {"from_url": "/a", "to_url": "/b"})
        assert idx == 1
        session = store.get_session("test_001")
        assert session is not None
        assert len(session["navigations"]) == 1

    def test_add_event_to_nonexistent_session(self) -> None:
        store = _RecordingSessionStore()
        idx = store.add_event("nonexistent", "step", {"action": "click"})
        assert idx is None

    def test_end_session(self) -> None:
        store = _RecordingSessionStore()
        store.create_session("test_001")
        result = store.end_session("test_001", total_steps=5)
        assert result is True
        session = store.get_session("test_001")
        assert session is not None
        assert session["status"] == "completed"
        assert session["total_steps"] == 5

    def test_end_nonexistent_session(self) -> None:
        store = _RecordingSessionStore()
        result = store.end_session("nonexistent")
        assert result is False

    def test_list_sessions(self) -> None:
        store = _RecordingSessionStore()
        store.create_session("s1")
        store.create_session("s2")
        sessions = store.list_sessions()
        assert len(sessions) == 2

    def test_delete_session(self) -> None:
        store = _RecordingSessionStore()
        store.create_session("test_001")
        assert store.delete_session("test_001") is True
        assert store.get_session("test_001") is None

    def test_delete_nonexistent_session(self) -> None:
        store = _RecordingSessionStore()
        assert store.delete_session("nonexistent") is False

    def test_multiple_steps_increment_count(self) -> None:
        store = _RecordingSessionStore()
        store.create_session("test_001")
        store.add_event("test_001", "step", {"action": "click"})
        store.add_event("test_001", "step", {"action": "type"})
        store.add_event("test_001", "step", {"action": "submit"})
        session = store.get_session("test_001")
        assert session is not None
        assert session["total_steps"] == 3
        assert len(session["steps"]) == 3


class TestApiUiRecorderEvent:
    """录制事件 API 端点测试。"""

    def test_session_start(self, client) -> None:
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": "rec_test_001",
            "event_type": "session_start",
            "timestamp": 1000000,
            "data": {},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["status"] == "created"

    def test_step_event(self, client) -> None:
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_test_002",
            "event_type": "session_start",
            "timestamp": 1000000,
            "data": {},
        })
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": "rec_test_002",
            "event_type": "step",
            "timestamp": 1000001,
            "data": {"action": "click", "selector": {"primary": "#btn"}},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["ok"] is True

    def test_session_end(self, client) -> None:
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_test_003",
            "event_type": "session_start",
            "timestamp": 1000000,
            "data": {},
        })
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": "rec_test_003",
            "event_type": "session_end",
            "timestamp": 1000010,
            "data": {"total_steps": 5},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["status"] == "completed"

    def test_invalid_json(self, client) -> None:
        resp = client.post("/api/ui-recorder/event", data="not json", content_type="text/plain")
        assert resp.status_code == 400

    def test_missing_fields(self, client) -> None:
        resp = client.post("/api/ui-recorder/event", json={})
        assert resp.status_code == 400

    def test_unknown_event_type(self, client) -> None:
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": "rec_test",
            "event_type": "unknown_type",
            "data": {},
        })
        assert resp.status_code == 400

    def test_auto_create_session_on_step(self, client) -> None:
        """步骤事件到达时如果 session 不存在，自动创建。"""
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": "rec_auto",
            "event_type": "step",
            "timestamp": 1000000,
            "data": {"action": "click"},
        })
        assert resp.status_code == 200


class TestApiUiRecorderSessions:
    """会话列表 API 端点测试。"""

    def test_list_sessions_empty(self, client) -> None:
        resp = client.get("/api/ui-recorder/sessions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["data"], list)

    def test_list_sessions_with_data(self, client) -> None:
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_list_1",
            "event_type": "session_start",
            "data": {},
        })
        resp = client.get("/api/ui-recorder/sessions")
        data = resp.get_json()
        session_ids = [s["session_id"] for s in data["data"]]
        assert "rec_list_1" in session_ids


class TestApiUiRecorderSessionDetail:
    """会话详情 API 端点测试。"""

    def test_get_session_detail(self, client) -> None:
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_detail",
            "event_type": "session_start",
            "data": {},
        })
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_detail",
            "event_type": "step",
            "data": {"action": "click", "selector": {"primary": "#btn"}, "page_url": "http://example.com"},
        })
        resp = client.get("/api/ui-recorder/session/rec_detail")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["session_id"] == "rec_detail"
        assert len(data["data"]["steps"]) == 1

    def test_get_nonexistent_session(self, client) -> None:
        resp = client.get("/api/ui-recorder/session/nonexistent_xyz")
        assert resp.status_code == 404


class TestApiUiRecorderSessionDelete:
    """会话删除 API 端点测试。"""

    def test_delete_session(self, client) -> None:
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_del",
            "event_type": "session_start",
            "data": {},
        })
        resp = client.delete("/api/ui-recorder/session/rec_del")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["ok"] is True

    def test_delete_nonexistent(self, client) -> None:
        resp = client.delete("/api/ui-recorder/session/nonexistent_xyz")
        assert resp.status_code == 404


class TestApiUiRecorderSessionExport:
    """会话导出 API 端点测试。"""

    def test_export_session(self, client) -> None:
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_export",
            "event_type": "session_start",
            "data": {},
        })
        client.post("/api/ui-recorder/event", json={
            "session_id": "rec_export",
            "event_type": "step",
            "data": {"action": "click", "selector": {"primary": "#submit"}, "value": ""},
        })
        resp = client.get("/api/ui-recorder/session/rec_export/export")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["version"] == "1.0"
        assert data["session_id"] == "rec_export"
        assert len(data["steps"]) == 1

    def test_export_nonexistent(self, client) -> None:
        resp = client.get("/api/ui-recorder/session/nonexistent_xyz/export")
        assert resp.status_code == 404


class TestFullRecordingFlow:
    """完整录制流程集成测试。"""

    def test_complete_recording_flow(self, client) -> None:
        """模拟完整录制流程：开始 → 多个步骤 → 结束 → 查看 → 导出。"""
        session_id = "rec_flow_test"

        # 1. 开始录制
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": session_id,
            "event_type": "session_start",
            "data": {"start_time": 1000000},
        })
        assert resp.status_code == 200

        # 2. 发送多个步骤
        steps = [
            {"action": "click", "selector": {"primary": "#login-btn"}, "value": "", "page_url": "http://example.com/login"},
            {"action": "type", "selector": {"primary": "[name=username]"}, "value": "admin", "page_url": "http://example.com/login"},
            {"action": "type", "selector": {"primary": "[name=password]"}, "value": "{{password}}", "page_url": "http://example.com/login", "is_password": True},
            {"action": "submit", "selector": {"primary": "form"}, "value": "", "page_url": "http://example.com/login"},
            {"action": "click", "selector": {"primary": "#dashboard-link"}, "value": "", "page_url": "http://example.com/dashboard"},
        ]
        for step in steps:
            resp = client.post("/api/ui-recorder/event", json={
                "session_id": session_id,
                "event_type": "step",
                "data": step,
            })
            assert resp.status_code == 200

        # 3. 发送导航事件
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": session_id,
            "event_type": "navigation",
            "data": {"action": "navigate", "from_url": "http://example.com/login", "to_url": "http://example.com/dashboard"},
        })
        assert resp.status_code == 200

        # 4. 结束录制
        resp = client.post("/api/ui-recorder/event", json={
            "session_id": session_id,
            "event_type": "session_end",
            "data": {"total_steps": 5},
        })
        assert resp.status_code == 200

        # 5. 查看会话详情
        resp = client.get(f"/api/ui-recorder/session/{session_id}")
        assert resp.status_code == 200
        session = resp.get_json()["data"]
        assert session["status"] == "completed"
        assert len(session["steps"]) == 5
        assert len(session["navigations"]) == 1

        # 6. 导出
        resp = client.get(f"/api/ui-recorder/session/{session_id}/export")
        assert resp.status_code == 200
        exported = resp.get_json()
        assert exported["version"] == "1.0"
        assert len(exported["steps"]) == 5
        assert exported["metadata"]["total_steps"] == 5

        # 7. 删除
        resp = client.delete(f"/api/ui-recorder/session/{session_id}")
        assert resp.status_code == 200

        # 8. 确认已删除
        resp = client.get(f"/api/ui-recorder/session/{session_id}")
        assert resp.status_code == 404
