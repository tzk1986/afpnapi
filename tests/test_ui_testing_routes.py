"""UI 测试模块路由测试。"""

import json
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask

from postman_api_tester.handlers import ui_testing_routes
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_case_delete,
    api_ui_testing_case_get,
    api_ui_testing_case_update,
    api_ui_testing_cases_create,
    api_ui_testing_cases_list,
    ui_testing_proxy,
    ui_testing_proxy_resource,
    api_ui_testing_recording_get,
    api_ui_testing_recording_save_as_case,
    api_ui_testing_recording_start,
    api_ui_testing_recording_step,
    api_ui_testing_recording_stop,
    ui_testing_editor_page,
    ui_testing_index_page,
    ui_testing_recorder_page,
)
from postman_api_tester.services.ui_case_store import UiCaseStore


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Generator[Flask, None, None]:
    """提供 Flask 测试应用。"""
    app = Flask(__name__, template_folder=str(Path(__file__).parent.parent / "templates"))
    app.config["TESTING"] = True

    app.add_url_rule("/ui-testing", "ui_testing_index_page", ui_testing_index_page)
    app.add_url_rule("/ui-testing/recorder", "ui_testing_recorder_page", ui_testing_recorder_page)
    app.add_url_rule("/ui-testing/editor/<path:case_id>", "ui_testing_editor_page", ui_testing_editor_page)
    app.add_url_rule("/ui-testing/proxy", "ui_testing_proxy", ui_testing_proxy)
    app.add_url_rule("/ui-testing/proxy-resource", "ui_testing_proxy_resource", ui_testing_proxy_resource)
    app.add_url_rule("/api/ui-testing/recording/<path:session_id>/save", "api_ui_testing_recording_save_as_case", api_ui_testing_recording_save_as_case, methods=["POST"])
    app.add_url_rule("/api/ui-testing/cases", "api_ui_testing_cases_list", api_ui_testing_cases_list)
    app.add_url_rule("/api/ui-testing/cases", "api_ui_testing_cases_create", api_ui_testing_cases_create, methods=["POST"])
    app.add_url_rule("/api/ui-testing/cases/<path:case_id>", "api_ui_testing_case_get", api_ui_testing_case_get)
    app.add_url_rule("/api/ui-testing/cases/<path:case_id>", "api_ui_testing_case_update", api_ui_testing_case_update, methods=["PUT"])
    app.add_url_rule("/api/ui-testing/cases/<path:case_id>", "api_ui_testing_case_delete", api_ui_testing_case_delete, methods=["DELETE"])
    app.add_url_rule("/api/ui-testing/recording/start", "api_ui_testing_recording_start", api_ui_testing_recording_start, methods=["POST"])
    app.add_url_rule("/api/ui-testing/recording/step", "api_ui_testing_recording_step", api_ui_testing_recording_step, methods=["POST"])
    app.add_url_rule("/api/ui-testing/recording/stop", "api_ui_testing_recording_stop", api_ui_testing_recording_stop, methods=["POST"])
    app.add_url_rule("/api/ui-testing/recording/<path:session_id>", "api_ui_testing_recording_get", api_ui_testing_recording_get)

    yield app


@pytest.fixture  # type: ignore[untyped-decorator]
def client(app: Flask):
    """Flask 测试客户端。"""
    return app.test_client()


@pytest.fixture  # type: ignore[untyped-decorator]
def temp_store() -> Generator[UiCaseStore, None, None]:
    """临时用例存储。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = UiCaseStore(cases_dir=Path(tmp_dir))
        with patch.object(ui_testing_routes, "_case_store", store):
            yield store


class TestPageRoutes:
    """页面路由测试。"""

    def test_index_page(self, client) -> None:
        resp = client.get("/ui-testing")
        assert resp.status_code == 200
        assert b"Web UI" in resp.data

    def test_recorder_page(self, client) -> None:
        resp = client.get("/ui-testing/recorder")
        assert resp.status_code == 200
        assert b"recorder" in resp.data.lower() or b"\xe5\xbd\x95\xe5\x88\xb6" in resp.data

    def test_editor_page_redirects_when_case_not_found(self, client, temp_store) -> None:
        resp = client.get("/ui-testing/editor/nonexistent", follow_redirects=False)
        assert resp.status_code == 302


class TestProxyEndpoint:
    """代理端点测试。"""

    def test_missing_url_param(self, client) -> None:
        resp = client.get("/ui-testing/proxy")
        assert resp.status_code == 400

    def test_invalid_protocol(self, client) -> None:
        resp = client.get("/ui-testing/proxy?url=ftp://example.com")
        assert resp.status_code == 400

    def test_proxy_resource_missing_url(self, client) -> None:
        resp = client.get("/ui-testing/proxy-resource")
        assert resp.status_code == 400


class TestCaseCrudApi:
    """用例 CRUD API 测试。"""

    def test_list_empty(self, client, temp_store) -> None:
        resp = client.get("/api/ui-testing/cases")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == []

    def test_create_case(self, client, temp_store) -> None:
        resp = client.post("/api/ui-testing/cases", json={
            "name": "测试用例",
            "base_url": "https://example.com",
            "steps": [{"action": "click", "selector": "#btn"}],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data["data"]

    def test_get_case(self, client, temp_store) -> None:
        case_id = temp_store.create_case({"id": "test-get", "name": "查找"})
        resp = client.get(f"/api/ui-testing/cases/{case_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["name"] == "查找"

    def test_get_nonexistent_case(self, client, temp_store) -> None:
        resp = client.get("/api/ui-testing/cases/nonexistent")
        assert resp.status_code == 404

    def test_update_case(self, client, temp_store) -> None:
        case_id = temp_store.create_case({"id": "test-update", "name": "原名"})
        resp = client.put(f"/api/ui-testing/cases/{case_id}", json={"name": "新名"})
        assert resp.status_code == 200
        case = temp_store.get_case(case_id)
        assert case is not None
        assert case["name"] == "新名"

    def test_update_nonexistent(self, client, temp_store) -> None:
        resp = client.put("/api/ui-testing/cases/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_case(self, client, temp_store) -> None:
        case_id = temp_store.create_case({"id": "test-del", "name": "删除"})
        resp = client.delete(f"/api/ui-testing/cases/{case_id}")
        assert resp.status_code == 200
        assert temp_store.get_case(case_id) is None

    def test_delete_nonexistent(self, client, temp_store) -> None:
        resp = client.delete("/api/ui-testing/cases/nonexistent")
        assert resp.status_code == 404

    def test_create_invalid_json(self, client, temp_store) -> None:
        resp = client.post("/api/ui-testing/cases", data="not json", content_type="text/plain")
        assert resp.status_code == 400


class TestRecordingApi:
    """录制会话 API 测试。"""

    def test_start_recording(self, client) -> None:
        resp = client.post("/api/ui-testing/recording/start", json={"base_url": "https://example.com"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "session_id" in data["data"]
        assert data["data"]["status"] == "recording"

    def test_add_step(self, client) -> None:
        # 先启动录制
        start_resp = client.post("/api/ui-testing/recording/start", json={})
        session_id = start_resp.get_json()["data"]["session_id"]

        resp = client.post("/api/ui-testing/recording/step", json={
            "session_id": session_id,
            "step": {"action": "click", "selector": "#btn"},
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["step_index"] == 1

    def test_add_step_to_nonexistent_session(self, client) -> None:
        resp = client.post("/api/ui-testing/recording/step", json={
            "session_id": "nonexistent",
            "step": {"action": "click"},
        })
        assert resp.status_code == 404

    def test_stop_recording(self, client) -> None:
        start_resp = client.post("/api/ui-testing/recording/start", json={})
        session_id = start_resp.get_json()["data"]["session_id"]

        resp = client.post("/api/ui-testing/recording/stop", json={"session_id": session_id})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "completed"

    def test_stop_nonexistent(self, client) -> None:
        resp = client.post("/api/ui-testing/recording/stop", json={"session_id": "nonexistent"})
        assert resp.status_code == 404

    def test_get_session(self, client) -> None:
        start_resp = client.post("/api/ui-testing/recording/start", json={"base_url": "https://example.com"})
        session_id = start_resp.get_json()["data"]["session_id"]

        resp = client.get(f"/api/ui-testing/recording/{session_id}")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["base_url"] == "https://example.com"

    def test_save_as_case(self, client, temp_store) -> None:
        # 启动录制，添加步骤，保存
        start_resp = client.post("/api/ui-testing/recording/start", json={"base_url": "https://example.com"})
        session_id = start_resp.get_json()["data"]["session_id"]

        client.post("/api/ui-testing/recording/step", json={
            "session_id": session_id,
            "step": {"action": "click", "selector": "#btn"},
        })

        resp = client.post(f"/api/ui-testing/recording/{session_id}/save", json={
            "session_id": session_id,
            "name": "从录制创建",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert "case_id" in data["data"]


class TestFullRecordingFlow:
    """完整录制流程集成测试。"""

    def test_full_flow(self, client, temp_store) -> None:
        """录制 → 添加步骤 → 停止 → 保存为用例。"""
        # 1. 开始录制
        resp = client.post("/api/ui-testing/recording/start", json={"base_url": "https://example.com"})
        session_id = resp.get_json()["data"]["session_id"]

        # 2. 添加多个步骤
        steps = [
            {"action": "click", "selector": {"primary": "#login-btn"}},
            {"action": "type", "selector": {"primary": "#username"}, "value": "admin"},
            {"action": "type", "selector": {"primary": "#password"}, "value": "{{password}}"},
            {"action": "submit", "selector": {"primary": "form"}},
        ]
        for step in steps:
            r = client.post("/api/ui-testing/recording/step", json={"session_id": session_id, "step": step})
            assert r.status_code == 200

        # 3. 停止录制
        resp = client.post("/api/ui-testing/recording/stop", json={"session_id": session_id})
        assert resp.get_json()["data"]["step_count"] == 4

        # 4. 保存为用例
        resp = client.post(f"/api/ui-testing/recording/{session_id}/save", json={
            "session_id": session_id,
            "name": "登录流程测试",
        })
        case_id = resp.get_json()["data"]["case_id"]

        # 5. 验证用例
        resp = client.get(f"/api/ui-testing/cases/{case_id}")
        case = resp.get_json()["data"]
        assert case["name"] == "登录流程测试"
        assert len(case["steps"]) == 4

        # 6. 用例出现在列表中
        resp = client.get("/api/ui-testing/cases")
        cases = resp.get_json()["data"]
        assert any(c["id"] == case_id for c in cases)
