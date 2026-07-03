"""UI 测试模块路由处理函数。

提供页面渲染（首页、录制器、编辑器）和 API（代理、用例 CRUD、录制会话管理）。
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from flask import make_response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.ui_case_store import UiCaseStore
from postman_api_tester.services.ui_proxy_service import UiProxyService

logger = logging.getLogger(__name__)

# 全局实例
_case_store = UiCaseStore()


class _RecordingSession:
    """录制会话内存管理。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def start(self, session_id: str, base_url: str) -> Dict[str, Any]:
        session: Dict[str, Any] = {
            "session_id": session_id,
            "base_url": base_url,
            "steps": [],
            "status": "recording",
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
        }
        with self._lock:
            self._sessions[session_id] = session
        return session

    def add_step(self, session_id: str, step: Dict[str, Any]) -> Optional[int]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session["steps"].append(step)
            return len(session["steps"])

    def stop(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session["status"] = "completed"
            session["ended_at"] = datetime.now().isoformat()
            return dict(session)

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                return dict(session)
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "session_id": s["session_id"],
                    "base_url": s["base_url"],
                    "status": s["status"],
                    "step_count": len(s["steps"]),
                    "started_at": s["started_at"],
                }
                for s in self._sessions.values()
            ]


_recording = _RecordingSession()


# ── 页面路由 ──


def ui_testing_index_page() -> ResponseReturnValue:
    """UI 测试首页。"""
    return render_template("ui_testing_index.html")


def ui_testing_recorder_page() -> ResponseReturnValue:
    """录制器页面。"""
    return render_template("ui_testing_recorder.html")


def ui_testing_editor_page(case_id: str) -> ResponseReturnValue:
    """用例编辑器页面。"""
    case = _case_store.get_case(case_id)
    if not case:
        return redirect(url_for("ui_testing_index_page"))
    return render_template("ui_testing_editor.html", case_id=case_id)


# ── 代理端点 ──


def _check_ui_proxy_host_allowed(url: str) -> Optional[ResponseReturnValue]:
    """若配置了 PROXY_ALLOWED_HOSTS，校验 url 的域名是否在白名单内。

    返回 None 表示通过，否则返回 403 错误响应。
    """
    from postman_api_tester.report_server_config import PROXY_ALLOWED_HOSTS
    if not PROXY_ALLOWED_HOSTS:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host and host not in PROXY_ALLOWED_HOSTS:
        logger.warning(
            "ui_proxy_host_blocked",
            extra={"event": "ui.proxy.host_blocked", "url": url, "host": host},
        )
        return json_error(f"proxy 域名不在白名单内：{host}", 403, "UIT_PROXY_005")
    return None


def ui_testing_proxy() -> ResponseReturnValue:
    """反向代理端点：获取外部 URL 并改写 HTML。"""
    target_url = request.args.get("url", "")
    if not target_url:
        return json_error("缺少 url 参数", 400, "UIT_PROXY_001")

    target_url = unquote(target_url)

    if not target_url.startswith(("http://", "https://")):
        return json_error("url 必须是 http/https 地址", 400, "UIT_PROXY_002")

    host_error = _check_ui_proxy_host_allowed(target_url)
    if host_error is not None:
        return host_error

    started_at = time.perf_counter()
    try:
        body, status_code, headers = UiProxyService.fetch_and_rewrite(target_url)
    except ValueError as e:
        logger.warning(
            "ui_proxy_invalid_url",
            extra={"event": "ui.proxy.invalid_url", "url": target_url, "error": str(e)},
        )
        return json_error(str(e), 400, "UIT_PROXY_003")
    except Exception as e:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        logger.error(
            "ui_proxy_fetch_failed",
            extra={
                "event": "ui.proxy.fetch_failed",
                "url": target_url,
                "error": str(e),
                "duration_ms": duration_ms,
            },
        )
        return json_error(f"获取目标页面失败: {e}", 502, "UIT_PROXY_004")

    duration_ms = round((time.perf_counter() - started_at) * 1000)
    body_size = len(body) if isinstance(body, str) else len(body)
    logger.info(
        "ui_proxy_ok",
        extra={
            "event": "ui.proxy.success",
            "url": target_url,
            "status_code": status_code,
            "body_size": body_size,
            "duration_ms": duration_ms,
        },
    )

    resp = make_response(body, status_code)
    for key, value in headers.items():
        resp.headers[key] = value
    resp.headers.pop("X-Frame-Options", None)
    resp.headers.pop("Content-Security-Policy", None)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def ui_testing_proxy_resource() -> ResponseReturnValue:
    """代理子资源（CSS/JS/图片等）。"""
    target_url = request.args.get("url", "")
    if not target_url:
        return json_error("缺少 url 参数", 400, "UIT_RES_001")

    target_url = unquote(target_url)

    if not target_url.startswith(("http://", "https://")):
        return json_error("url 必须是 http/https 地址", 400, "UIT_RES_002")

    host_error = _check_ui_proxy_host_allowed(target_url)
    if host_error is not None:
        return host_error

    started_at = time.perf_counter()
    try:
        body, status_code, headers = UiProxyService.fetch_resource(target_url)
    except Exception as e:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        logger.error(
            "ui_proxy_resource_failed",
            extra={
                "event": "ui.proxy.resource_failed",
                "url": target_url,
                "error": str(e),
                "duration_ms": duration_ms,
            },
        )
        return make_response(b"", 404)

    duration_ms = round((time.perf_counter() - started_at) * 1000)
    content_type = headers.get("Content-Type", "")
    logger.debug(
        "ui_proxy_resource_ok",
        extra={
            "event": "ui.proxy.resource_success",
            "url": target_url,
            "status_code": status_code,
            "content_type": content_type,
            "body_size": len(body),
            "duration_ms": duration_ms,
        },
    )

    resp = make_response(body, status_code)
    for key, value in headers.items():
        resp.headers[key] = value
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ── 用例 CRUD API ──


def api_ui_testing_cases_list() -> ResponseReturnValue:
    """获取用例列表。"""
    cases = _case_store.list_cases()
    return BaseHandler.json_response(cases)


def api_ui_testing_cases_create() -> ResponseReturnValue:
    """创建用例。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_CASE_001")

    case_id = _case_store.create_case(payload)
    case_name = payload.get("name", "")
    step_count = len(payload.get("steps", []))
    logger.info(
        "ui_case_created",
        extra={
            "event": "ui.case.created",
            "case_id": case_id,
            "case_name": case_name,
            "step_count": step_count,
        },
    )
    return BaseHandler.json_response({"id": case_id}, 201, "Created")


def api_ui_testing_case_get(case_id: str) -> ResponseReturnValue:
    """获取用例详情。"""
    case = _case_store.get_case(case_id)
    if not case:
        return json_error(f"用例不存在: {case_id}", 404, "UIT_CASE_002")
    return BaseHandler.json_response(case)


def api_ui_testing_case_update(case_id: str) -> ResponseReturnValue:
    """更新用例。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_CASE_003")

    if not _case_store.update_case(case_id, payload):
        logger.warning(
            "ui_case_update_not_found",
            extra={"event": "ui.case.update_not_found", "case_id": case_id},
        )
        return json_error(f"用例不存在: {case_id}", 404, "UIT_CASE_004")
    logger.info(
        "ui_case_updated",
        extra={
            "event": "ui.case.updated",
            "case_id": case_id,
            "case_name": payload.get("name", ""),
            "step_count": len(payload.get("steps", [])),
        },
    )
    return BaseHandler.json_response({"ok": True})


def api_ui_testing_case_delete(case_id: str) -> ResponseReturnValue:
    """删除用例。"""
    if not _case_store.delete_case(case_id):
        logger.warning(
            "ui_case_delete_not_found",
            extra={"event": "ui.case.delete_not_found", "case_id": case_id},
        )
        return json_error(f"用例不存在: {case_id}", 404, "UIT_CASE_005")
    logger.info(
        "ui_case_deleted",
        extra={"event": "ui.case.deleted", "case_id": case_id},
    )
    return BaseHandler.json_response({"ok": True})


# ── 录制会话 API ──


def api_ui_testing_recording_start() -> ResponseReturnValue:
    """开始录制会话。"""
    payload = request.get_json(silent=True) or {}
    session_id = str(uuid.uuid4())[:12]
    base_url = payload.get("base_url", "")

    session = _recording.start(session_id, base_url)
    logger.info(
        "ui_recording_started",
        extra={
            "event": "ui.recording.started",
            "session_id": session_id,
            "base_url": base_url,
        },
    )
    return BaseHandler.json_response({
        "session_id": session_id,
        "status": "recording",
        "started_at": session["started_at"],
    })


def api_ui_testing_recording_step() -> ResponseReturnValue:
    """添加录制步骤。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_REC_001")

    session_id = payload.get("session_id", "")
    step = payload.get("step", {})

    if not session_id:
        return json_error("缺少 session_id", 400, "UIT_REC_002")

    idx = _recording.add_step(session_id, step)
    if idx is None:
        return json_error(f"录制会话不存在: {session_id}", 404, "UIT_REC_003")

    return BaseHandler.json_response({"ok": True, "step_index": idx})


def api_ui_testing_recording_stop() -> ResponseReturnValue:
    """停止录制会话。"""
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id", "")

    if not session_id:
        return json_error("缺少 session_id", 400, "UIT_REC_004")

    session = _recording.stop(session_id)
    if not session:
        return json_error(f"录制会话不存在: {session_id}", 404, "UIT_REC_005")

    step_count = len(session["steps"])
    logger.info(
        "ui_recording_stopped",
        extra={
            "event": "ui.recording.stopped",
            "session_id": session_id,
            "step_count": step_count,
        },
    )
    return BaseHandler.json_response({
        "session_id": session_id,
        "status": "completed",
        "step_count": step_count,
        "ended_at": session["ended_at"],
    })


def api_ui_testing_recording_get(session_id: str) -> ResponseReturnValue:
    """获取录制会话数据。"""
    session = _recording.get(session_id)
    if not session:
        return json_error(f"录制会话不存在: {session_id}", 404, "UIT_REC_006")
    return BaseHandler.json_response(session)


def api_ui_testing_recording_save_as_case(session_id: str = "") -> ResponseReturnValue:
    """将录制会话保存为用例。"""
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id", "") or session_id
    name = payload.get("name", "未命名用例")

    if not session_id:
        return json_error("缺少 session_id", 400, "UIT_REC_007")

    session = _recording.get(session_id)
    if not session:
        return json_error(f"录制会话不存在: {session_id}", 404, "UIT_REC_008")

    case_data = {
        "name": name,
        "description": f"从录制会话 {session_id} 创建",
        "base_url": session.get("base_url", ""),
        "steps": session.get("steps", []),
        "assertions": [],
        "variables": {},
        "tags": ["recorded"],
    }

    case_id = _case_store.create_case(case_data)
    logger.info(
        "ui_recording_saved_as_case",
        extra={
            "event": "ui.recording.saved_as_case",
            "session_id": session_id,
            "case_id": case_id,
            "case_name": name,
            "step_count": len(case_data["steps"]),
        },
    )
    return BaseHandler.json_response({"case_id": case_id}, 201, "Created")
