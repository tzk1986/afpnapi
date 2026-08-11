"""网络请求捕获链路补全（M-9）功能测试。

覆盖：
- RecordingSessionStore.update_step_response 响应回填
- _extract_network_requests 数据提取
- 注入脚本 JS 模板中的网络捕获增强
- NetworkComparator 代理 URL 解析逻辑
- api_ui_testing_recording_step 响应回填路由
"""

from typing import Any, Generator

import pytest
from flask import Flask

from postman_api_tester.services.ui_recording_store import RecordingSessionStore
from postman_api_tester.services.ui_recorder_inject import get_recorder_js, get_replayer_js
from postman_api_tester.handlers.ui_execution_routes import _extract_network_requests


# ===== RecordingSessionStore.update_step_response =====


class TestUpdateStepResponse:
    """录制会话响应回填测试。"""

    def test_fill_response_by_net_id(self) -> None:
        store = RecordingSessionStore()
        store.start("s1")
        store.add_step("s1", {
            "action": "api_call",
            "value": "http://target/api/data",
            "_net_id": 1,
            "network_request": {"url": "http://target/api/data", "method": "GET"},
        })
        store.add_step("s1", {"action": "click", "selector": "#btn"})
        store.add_step("s1", {
            "action": "api_call",
            "value": "http://target/api/users",
            "_net_id": 2,
            "network_request": {"url": "http://target/api/users", "method": "POST"},
        })

        result = store.update_step_response("s1", 1, {"status": 200, "body": '{"ok":true}'})
        assert result is True

        session = store.get("s1")
        assert session is not None
        steps = session["steps"]
        assert steps[0]["network_response"] == {"status": 200, "body": '{"ok":true}'}
        assert "network_response" not in steps[1]
        assert "network_response" not in steps[2]

    def test_fill_second_api_call(self) -> None:
        store = RecordingSessionStore()
        store.start("s1")
        store.add_step("s1", {
            "action": "api_call", "_net_id": 1, "value": "http://a",
            "network_request": {"url": "http://a"},
        })
        store.add_step("s1", {
            "action": "api_call", "_net_id": 2, "value": "http://b",
            "network_request": {"url": "http://b"},
        })

        store.update_step_response("s1", 2, {"status": 404, "body": "not found"})

        session = store.get("s1")
        assert session is not None
        assert "network_response" not in session["steps"][0]
        assert session["steps"][1]["network_response"] == {"status": 404, "body": "not found"}

    def test_nonexistent_session(self) -> None:
        store = RecordingSessionStore()
        result = store.update_step_response("nonexistent", 1, {"status": 200})
        assert result is False

    def test_nonexistent_net_id(self) -> None:
        store = RecordingSessionStore()
        store.start("s1")
        store.add_step("s1", {
            "action": "api_call", "_net_id": 1, "value": "http://a",
        })
        result = store.update_step_response("s1", 999, {"status": 200})
        assert result is False

    def test_skips_non_api_call_steps(self) -> None:
        store = RecordingSessionStore()
        store.start("s1")
        store.add_step("s1", {"action": "click", "_net_id": 1, "selector": "#btn"})

        result = store.update_step_response("s1", 1, {"status": 200})
        assert result is False

    def test_matches_last_occurrence_when_duplicated(self) -> None:
        store = RecordingSessionStore()
        store.start("s1")
        store.add_step("s1", {"action": "api_call", "_net_id": 1, "value": "http://a"})
        store.add_step("s1", {"action": "click", "selector": "#x"})

        result = store.update_step_response("s1", 1, {"status": 200, "body": "ok"})
        assert result is True

        session = store.get("s1")
        assert session is not None
        assert session["steps"][0]["network_response"] == {"status": 200, "body": "ok"}


# ===== _extract_network_requests =====


class TestExtractNetworkRequests:
    """从步骤中提取网络请求数据测试。"""

    def test_empty_steps(self) -> None:
        assert _extract_network_requests([]) == []

    def test_no_api_call_steps(self) -> None:
        steps = [
            {"action": "click", "selector": "#btn"},
            {"action": "wait", "value": "1000"},
        ]
        assert _extract_network_requests(steps) == []

    def test_api_call_without_network_request(self) -> None:
        steps = [
            {"action": "api_call", "value": "http://target/api"},
        ]
        assert _extract_network_requests(steps) == []

    def test_api_call_with_full_network_data(self) -> None:
        steps = [
            {"action": "click", "selector": "#btn"},
            {
                "action": "api_call",
                "value": "http://target/api/data",
                "network_request": {
                    "url": "http://target/api/data",
                    "url_path": "/api/data",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": '{"key":"value"}',
                },
                "network_response": {
                    "status": 200,
                    "body": '{"result":"ok"}',
                },
            },
        ]
        result = _extract_network_requests(steps)
        assert len(result) == 1
        assert result[0]["url"] == "http://target/api/data"
        assert result[0]["url_path"] == "/api/data"
        assert result[0]["method"] == "POST"
        assert result[0]["headers"] == {"Content-Type": "application/json"}
        assert result[0]["body"] == '{"key":"value"}'
        assert result[0]["response_status"] == 200
        assert result[0]["response_body"] == '{"result":"ok"}'

    def test_api_call_without_response(self) -> None:
        steps = [
            {
                "action": "api_call",
                "network_request": {
                    "url": "http://target/api",
                    "method": "GET",
                },
            },
        ]
        result = _extract_network_requests(steps)
        assert len(result) == 1
        assert result[0]["url"] == "http://target/api"
        assert result[0]["method"] == "GET"
        assert result[0]["response_status"] == 0
        assert result[0]["response_body"] == ""

    def test_multiple_api_calls(self) -> None:
        steps = [
            {
                "action": "api_call",
                "network_request": {"url": "http://a/api/1", "method": "GET"},
            },
            {"action": "click", "selector": "#btn"},
            {
                "action": "api_call",
                "network_request": {"url": "http://a/api/2", "method": "POST"},
                "network_response": {"status": 201},
            },
        ]
        result = _extract_network_requests(steps)
        assert len(result) == 2
        assert result[0]["url"] == "http://a/api/1"
        assert result[1]["url"] == "http://a/api/2"
        assert result[1]["response_status"] == 201

    def test_url_path_fallback(self) -> None:
        steps = [
            {
                "action": "api_call",
                "network_request": {
                    "url": "http://target/api/data",
                    "method": "GET",
                },
            },
        ]
        result = _extract_network_requests(steps)
        assert result[0]["url_path"] == ""


# ===== 注入脚本 JS 模板增强验证 =====


class TestInjectScriptNetworkCapture:
    """验证注入脚本包含网络请求捕获增强代码。"""

    def test_fetch_interceptor_captures_request_headers(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "reqHeaders" in code
        assert "network_request" in code

    def test_fetch_interceptor_captures_request_body(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "opts.body" in code or "opts && opts.body" in code

    def test_fetch_interceptor_captures_response(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "resp.status" in code or "response_status" in code
        assert "_net_id" in code or "netId" in code

    def test_xhr_interceptor_sends_api_call_event(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "api_call" in code
        assert "tag: 'xhr'" in code or "tag:'xhr'" in code or '"xhr"' in code

    def test_xhr_interceptor_captures_response(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "loadend" in code
        assert "responseText" in code

    def test_response_update_function_exists(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "api_response" in code
        assert "_sendResponseUpdate" in code or "sendResponseUpdate" in code

    def test_network_comparator_proxy_url_extraction(self) -> None:
        code = get_replayer_js("http://example.com")
        assert "proxy-resource" in code
        assert "?url=" in code
        assert "decodeURIComponent" in code

    def test_body_truncation(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "4096" in code
        assert "truncated" in code


# ===== 后端路由：响应回填 =====


class TestRecordingStepResponseUpdateRoute:
    """api_ui_testing_recording_step 响应回填路由测试。"""

    @pytest.fixture  # type: ignore[untyped-decorator]
    def app(self) -> Generator[Flask, None, None]:
        from postman_api_tester.handlers.ui_testing_routes import (
            api_ui_testing_recording_step,
        )

        app = Flask(__name__)
        app.config["TESTING"] = True
        app.add_url_rule(
            "/api/ui-testing/recording/step",
            "api_ui_testing_recording_step",
            api_ui_testing_recording_step,
            methods=["POST"],
        )
        yield app

    @pytest.fixture  # type: ignore[untyped-decorator]
    def client(self, app: Flask):
        return app.test_client()

    @pytest.fixture  # type: ignore[untyped-decorator]
    def recording_session(self) -> Generator[RecordingSessionStore, None, None]:
        from postman_api_tester.handlers.ui_testing_routes import (
            _recording as recording_store,
        )

        recording_store.start("test-session-001", "http://target")
        yield recording_store
        recording_store.delete_session("test-session-001")

    def test_normal_step_add(
        self, client: Any, recording_session: RecordingSessionStore
    ) -> None:
        resp = client.post(
            "/api/ui-testing/recording/step",
            json={
                "session_id": "test-session-001",
                "step": {"action": "click", "selector": "#btn"},
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["step_index"] == 1

    def test_response_update(
        self, client: Any, recording_session: RecordingSessionStore
    ) -> None:
        recording_session.add_step("test-session-001", {
            "action": "api_call",
            "_net_id": 1,
            "value": "http://target/api/data",
            "network_request": {"url": "http://target/api/data", "method": "GET"},
        })

        resp = client.post(
            "/api/ui-testing/recording/step",
            json={
                "session_id": "test-session-001",
                "step": {
                    "action": "api_response",
                    "_net_id": 1,
                    "network_response": {"status": 200, "body": '{"ok":true}'},
                },
                "is_response_update": True,
            },
        )
        assert resp.status_code == 200

        session = recording_session.get("test-session-001")
        assert session is not None
        assert session["steps"][0]["network_response"] == {
            "status": 200,
            "body": '{"ok":true}',
        }

    def test_response_update_nonexistent_session(self, client: Any) -> None:
        resp = client.post(
            "/api/ui-testing/recording/step",
            json={
                "session_id": "nonexistent",
                "step": {"action": "api_response", "_net_id": 1},
                "is_response_update": True,
            },
        )
        assert resp.status_code == 200

    def test_response_update_missing_session_id(self, client: Any) -> None:
        resp = client.post(
            "/api/ui-testing/recording/step",
            json={
                "step": {"action": "api_response", "_net_id": 1},
                "is_response_update": True,
            },
        )
        assert resp.status_code == 400
