"""UI 录制器路由处理函数。

接收 Chrome 扩展通过 HTTP POST 发送的录制事件，
提供录制会话管理和录制器页面渲染。
"""

import logging
from datetime import datetime
from typing import Any

from flask import jsonify, make_response, render_template, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import BaseHandler
from postman_api_tester.services.ui_recording_store import RecordingSessionStore

logger = logging.getLogger(__name__)


def _add_cors_headers(resp: Any) -> Any:
    """为响应添加 CORS 头，允许 Chrome 扩展跨域调用。"""
    if hasattr(resp, "headers"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    # BaseHandler.json_response 返回 tuple，先用 make_response 包装
    wrapped = make_response(resp)
    wrapped.headers["Access-Control-Allow-Origin"] = "*"
    wrapped.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    wrapped.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return wrapped


_store = RecordingSessionStore()


# ── API 端点 ──


def api_ui_recorder_event() -> ResponseReturnValue:
    """接收 Chrome 扩展发送的录制事件。

    POST JSON body:
    {
        "session_id": "rec_xxx",
        "event_type": "step" | "navigation" | "session_start" | "session_end",
        "timestamp": 1234567890,
        "data": { ... }
    }
    """
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        return _add_cors_headers(resp)

    payload = request.get_json(silent=True)
    if not payload:
        return _add_cors_headers(BaseHandler.json_response(None, 400, "Invalid JSON"))

    session_id = payload.get("session_id", "")
    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    if not session_id or not event_type:
        return _add_cors_headers(
            BaseHandler.json_response(None, 400, "Missing session_id or event_type")
        )

    if event_type == "session_start":
        _store.create_session(session_id)
        logger.info("Recording session started: %s", session_id)
        return _add_cors_headers(
            BaseHandler.json_response({"session_id": session_id, "status": "created"})
        )

    if event_type == "session_end":
        total = data.get("total_steps", 0)
        _store.end_session(session_id, total)
        logger.info("Recording session ended: %s, steps=%d", session_id, total)
        return _add_cors_headers(
            BaseHandler.json_response({"session_id": session_id, "status": "completed"})
        )

    if event_type in ("step", "navigation"):
        idx = _store.add_event(session_id, event_type, data)
        if idx is None:
            _store.create_session(session_id)
            _store.add_event(session_id, event_type, data)
        return _add_cors_headers(BaseHandler.json_response({"ok": True, "index": idx}))

    return _add_cors_headers(
        BaseHandler.json_response(None, 400, f"Unknown event_type: {event_type}")
    )


def api_ui_recorder_sessions() -> ResponseReturnValue:
    """获取所有录制会话列表。"""
    sessions = _store.list_sessions()
    return BaseHandler.json_response(sessions)


def api_ui_recorder_session_detail(session_id: str) -> ResponseReturnValue:
    """获取单个录制会话的完整数据。"""
    session = _store.get_session(session_id)
    if not session:
        return BaseHandler.json_response(None, 404, "Session not found")
    return BaseHandler.json_response(session)


def api_ui_recorder_session_delete(session_id: str) -> ResponseReturnValue:
    """删除录制会话。"""
    if _store.delete_session(session_id):
        return BaseHandler.json_response({"ok": True})
    return BaseHandler.json_response(None, 404, "Session not found")


def api_ui_recorder_clear_recording() -> ResponseReturnValue:
    """批量清除所有状态为 recording 的脏数据。"""
    sessions = _store.list_sessions()
    removed = 0
    for s in sessions:
        if s.get("status") == "recording" and _store.delete_session(s["session_id"]):
            removed += 1
    logger.info("Cleared %d stuck recording sessions", removed)
    return BaseHandler.json_response({"ok": True, "cleared": removed})


def api_ui_recorder_session_export(session_id: str) -> ResponseReturnValue:
    """导出录制会话为 JSON，兼容 UI 测试模块导入格式。"""
    session = _store.get_session(session_id)
    if not session:
        return BaseHandler.json_response(None, 404, "Session not found")

    base_url = ""
    for nav in session.get("navigations", []):
        url = nav.get("url", "")
        if url:
            base_url = url
            break
    if not base_url and session.get("steps"):
        base_url = session["steps"][0].get("page_url", "")

    export_data = {
        "version": "1.0",
        "id": session["session_id"],
        "session_id": session["session_id"],
        "name": f"录制 - {session['session_id']}",
        "base_url": base_url,
        "steps": session["steps"],
        "exported_at": datetime.now().isoformat(),
        "navigations": session["navigations"],
        "metadata": {
            "total_steps": session["total_steps"],
            "started_at": session["started_at"],
            "ended_at": session["ended_at"],
        },
    }
    return jsonify(export_data)


# ── 页面路由 ──


def ui_recorder_page() -> ResponseReturnValue:
    """UI 录制器页面。"""
    return render_template("ui_recorder.html")


def ui_recorder_demo_page() -> ResponseReturnValue:
    """Demo 页面，用于练习录制操作。"""
    return render_template("ui_recorder_demo.html")
