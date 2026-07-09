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
    resp = make_response(render_template("ui_testing_editor.html", case_id=case_id))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


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


def _get_proxy_session_id(base_url: str = "") -> str:
    """从 Cookie 或新创建的代理会话中获取 session ID。

    Args:
        base_url: 目标基础 URL（创建新会话时保存）
    """
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store
    from urllib.parse import parse_qs as _parse_qs

    sid = request.cookies.get("_proxy_session")
    if sid:
        jar = _proxy_session_store.get_cookie_jar(sid)
        if jar is not None:
            if base_url:
                _proxy_session_store.set_base_url(sid, base_url)
            logger.info(
                "proxy_session_reuse",
                extra={
                    "event": "ui.proxy.session.reuse",
                    "session_id": sid[:8],
                    "base_url": base_url or _proxy_session_store.get_base_url(sid),
                    "cookies_in_jar": [c.name for c in jar],
                },
            )
            return sid
        logger.warning(
            "proxy_session_cookie_but_not_found",
            extra={
                "event": "ui.proxy.session.missing",
                "session_id": sid[:8],
                "browser_cookies": dict(request.cookies),
            },
        )

    # Cookie 尚未存储时，从 Referer 提取目标 URL 以复用 session
    referer = request.headers.get("Referer", "")
    if referer and "/ui-testing/proxy?url=" in referer:
        try:
            ref_qs = referer.split("/ui-testing/proxy?url=", 1)[1].split("&")[0]
            from urllib.parse import unquote as _uq2
            ref_base_url = _uq2(ref_qs)
            # 查找已有该 base_url 的 session
            existing_sid = _proxy_session_store.find_session_by_base_url(ref_base_url)
            if existing_sid:
                existing_jar = _proxy_session_store.get_cookie_jar(existing_sid)
                logger.info(
                    "proxy_session_reuse_via_referer",
                    extra={
                        "event": "ui.proxy.session.reuse_referer",
                        "session_id": existing_sid[:8],
                        "base_url": ref_base_url,
                        "cookies_in_jar": [c.name for c in existing_jar] if existing_jar else [],
                    },
                )
                return existing_sid
            # 没有则创建并关联 base_url
            new_sid = _proxy_session_store.create_session(ref_base_url)
            logger.info(
                "proxy_session_created_via_referer",
                extra={
                    "event": "ui.proxy.session.new_referer",
                    "session_id": new_sid[:8],
                    "base_url": ref_base_url,
                },
            )
            return new_sid
        except Exception:
            pass

    # 创建新会话并保存 base_url
    new_sid = _proxy_session_store.create_session(base_url)
    logger.info(
        "proxy_session_created_new",
        extra={
            "event": "ui.proxy.session.new",
            "session_id": new_sid[:8],
            "base_url": base_url,
            "browser_cookies": dict(request.cookies),
        },
    )
    return new_sid


def ui_testing_proxy() -> ResponseReturnValue:
    """反向代理端点：获取外部 URL 并改写 HTML。"""
    target_url = request.args.get("url", "")
    if not target_url:
        return json_error("缺少 url 参数", 400, "UIT_PROXY_001")

    target_url = unquote(target_url)

    # 自动解包嵌套代理 URL：当 target_url 本身也是代理 URL 时，提取真实目标
    _max_unwrap = 5
    for _ in range(_max_unwrap):
        from urllib.parse import urlparse as _up2
        _parsed = _up2(target_url)
        if _parsed.hostname in ("127.0.0.1", "localhost") and _parsed.port == 5000:
            # 任何指向代理自身的路径，都尝试提取 url 参数
            from urllib.parse import parse_qs as _pqs
            _qs = _pqs(_parsed.query)
            _inner_url = _qs.get("url", [""])[0]
            if _inner_url and _inner_url.startswith(("http://", "https://")):
                logger.debug("unwrap_nested_proxy", extra={"from": target_url[:80], "to": _inner_url[:80]})
                target_url = _inner_url
                continue
        break

    if not target_url.startswith(("http://", "https://")):
        return json_error("url 必须是 http/https 地址", 400, "UIT_PROXY_002")

    # 检测循环引用：目标地址不能是代理服务器自身
    parsed_target = _up2(target_url)
    if parsed_target.hostname in ("127.0.0.1", "localhost") and parsed_target.port == 5000:
        return json_error(f"目标地址不能是代理服务器自身: {target_url[:100]}", 400, "UIT_PROXY_005")

    host_error = _check_ui_proxy_host_allowed(target_url)
    if host_error is not None:
        return host_error

    # 提取基础 URL（scheme + netloc）作为会话的 base_url
    base_url = f"{parsed_target.scheme}://{parsed_target.netloc}"
    session_id = _get_proxy_session_id(base_url)
    replay_mode = request.args.get("replay", "") == "1"

    started_at = time.perf_counter()
    try:
        body, status_code, headers = UiProxyService.fetch_and_rewrite(
            target_url,
            session_id,
            method=request.method,
            req_headers=dict(request.headers),
            req_body=request.get_data() if request.method != "GET" else None,
            replay_mode=replay_mode,
        )
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

    # 重写 Location 响应头：将目标服务器的重定向 URL 改为代理 URL
    if "Location" in headers:
        loc = headers["Location"]
        from urllib.parse import quote as _quote2
        if loc.startswith(("http://", "https://")):
            headers["Location"] = "/ui-testing/proxy?url=" + _quote2(loc, safe="")
        elif loc.startswith("/"):
            full_loc = base_url + loc
            headers["Location"] = "/ui-testing/proxy?url=" + _quote2(full_loc, safe="")

    resp = make_response(body, status_code)
    set_cookies_sent = []
    for key, value in headers.items():
        if key == "_set_cookies":
            for cookie_str in value:
                resp.headers.add("Set-Cookie", cookie_str)
                set_cookies_sent.append(cookie_str[:80])
        else:
            resp.headers[key] = value
    resp.headers.pop("X-Frame-Options", None)
    resp.headers.pop("Content-Security-Policy", None)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    # 设置代理会话 Cookie（手动设置 header，避免 set_cookie 可能被覆盖）
    resp.headers.add("Set-Cookie", f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age=3600; Path=/")

    logger.info(
        "proxy_page_response_to_browser",
        extra={
            "event": "ui.proxy.page.resp_to_browser",
            "session_id": session_id[:8],
            "url": target_url,
            "status_code": status_code,
            "browser_sent_cookies": dict(request.cookies),
            "set_cookies_returned": set_cookies_sent,
        },
    )
    return resp


def ui_testing_proxy_resource() -> ResponseReturnValue:
    """代理子资源（CSS/JS/图片/API 调用），支持所有 HTTP 方法。"""
    target_url = request.args.get("url", "")
    if not target_url:
        return json_error("缺少 url 参数", 400, "UIT_RES_001")

    target_url = unquote(target_url)

    if not target_url.startswith(("http://", "https://")):
        return json_error("url 必须是 http/https 地址", 400, "UIT_RES_002")

    host_error = _check_ui_proxy_host_allowed(target_url)
    if host_error is not None:
        return host_error

    session_id = _get_proxy_session_id()

    started_at = time.perf_counter()
    try:
        body, status_code, headers = UiProxyService.fetch_resource(
            target_url,
            method=request.method,
            req_headers=dict(request.headers),
            req_body=request.get_data(),
            session_id=session_id,
        )
    except Exception as e:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        logger.error(
            "ui_proxy_resource_failed",
            extra={
                "event": "ui.proxy.resource_failed",
                "url": target_url,
                "method": request.method,
                "error": str(e),
                "duration_ms": duration_ms,
            },
        )
        return make_response(b"", 404)

    duration_ms = round((time.perf_counter() - started_at) * 1000)
    content_type = headers.get("Content-Type", "")
    log_level = logging.DEBUG
    log_event = "ui.proxy.resource_success"
    log_message = "ui_proxy_resource_ok"
    if status_code >= 400:
        log_level = logging.WARNING
        log_event = "ui.proxy.resource_failed"
        log_message = "ui_proxy_resource_error"
    logger.log(
        log_level,
        log_message,
        extra={
            "event": log_event,
            "url": target_url,
            "method": request.method,
            "status_code": status_code,
            "content_type": content_type,
            "body_size": len(body),
            "duration_ms": duration_ms,
        },
    )

    # 内容类型告警：请求静态资源但返回 text/html 说明目标服务器可能返回了错误页面
    # 不直接拦截返回 404，让原始响应返回给浏览器（可能是验证码等动态生成的资源）
    from urllib.parse import urlparse as _up
    _ext = _up(target_url).path.rsplit(".", 1)[-1].lower() if "." in _up(target_url).path else ""
    _binary_exts = {"png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp", "woff", "woff2", "ttf", "eot", "otf", "mp4", "webm", "ogg", "pdf", "zip"}
    if _ext in _binary_exts and content_type.startswith("text/"):
        logger.warning(
            "ui_proxy_resource_wrong_content_type",
            extra={
                "event": "ui.proxy.resource.wrong_content_type",
                "url": target_url,
                "expected_ext": _ext,
                "actual_content_type": content_type,
                "body_preview": body[:200].decode("utf-8", errors="replace"),
            },
        )

    # CSS 文件改写：改写其中的 url() 引用为代理 URL
    if content_type.startswith("text/css") or _ext == "css":
        try:
            css_text = body.decode("utf-8", errors="replace")
            css_text = UiProxyService._rewrite_css_urls(css_text, target_url, target_url)
            body = css_text.encode("utf-8")
            content_type = "text/css; charset=utf-8"
            headers["Content-Type"] = content_type
        except Exception as e:
            logger.warning("css_rewrite_failed: %s", e)

    # 重写 Location 响应头：将目标服务器的重定向 URL 改为代理 URL
    if "Location" in headers:
        loc = headers["Location"]
        from urllib.parse import quote as _quote
        if loc.startswith(("http://", "https://")):
            headers["Location"] = "/ui-testing/proxy?url=" + _quote(loc, safe="")
        elif loc.startswith("/"):
            _target_base = target_url.rsplit("/", 1)[0] if "/" in target_url else target_url
            full_loc = _target_base + loc
            headers["Location"] = "/ui-testing/proxy?url=" + _quote(full_loc, safe="")

    resp = make_response(body, status_code)
    set_cookies_sent = []
    for key, value in headers.items():
        if key == "_set_cookies":
            for cookie_str in value:
                resp.headers.add("Set-Cookie", cookie_str)
                set_cookies_sent.append(cookie_str[:80])
        else:
            resp.headers[key] = value
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    # 设置代理会话 Cookie
    resp.headers.add("Set-Cookie", f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age=3600; Path=/")

    # 仅对 API 请求记录 cookie 详情（跳过静态资源）
    if "/api/" in target_url or target_url.endswith("/login") or target_url.endswith("/kaptcha"):
        logger.info(
            "proxy_resource_response_to_browser",
            extra={
                "event": "ui.proxy.resource.resp_to_browser",
                "session_id": session_id[:8],
                "url": target_url,
                "method": request.method,
                "status_code": status_code,
                "browser_sent_cookies": dict(request.cookies),
                "set_cookies_returned": set_cookies_sent,
            },
        )
    return resp


def ui_testing_static_fallback(filename: str = "") -> ResponseReturnValue:
    """静态资源兜底：转发 SPA 动态 import() 加载的 /static/... 资源到目标服务器。

    通过 Referer 中的 proxy URL 或 Cookie session 提取目标地址。
    """
    from postman_api_tester.services.ui_proxy_service import UiProxyService, _proxy_session_store

    # 从请求路径构造目标 URL（移除前导 /）
    resource_path = request.path.lstrip("/")
    if not resource_path:
        return make_response(b"", 404)

    # 从 Referer 提取目标 URL（Referer 应包含 proxy?url=... 参数）
    referer = request.headers.get("Referer", "")
    target_url = ""
    if referer:
        parsed_ref = urlparse(referer)
        url_param = parsed_ref.query
        if "url=" in url_param:
            from urllib.parse import parse_qs
            params = parse_qs(url_param)
            target_url = params.get("url", [""])[0]

    # 如果 Referer 没有 proxy URL，从 Cookie session 中获取 base_url
    if not target_url:
        session_id = request.cookies.get("_proxy_session")
        if session_id:
            base_url = _proxy_session_store.get_base_url(session_id)
            if base_url:
                target_url = base_url

    # 如果还是没有 target_url，使用最近一次会话的 base_url
    if not target_url:
        with _proxy_session_store._lock:
            all_sessions = list(_proxy_session_store._sessions.items())
        if all_sessions:
            # 取最近活跃的会话
            latest_sid = max(all_sessions, key=lambda item: item[1].get("last_active", 0))[0]
            base_url = _proxy_session_store.get_base_url(latest_sid)
            if base_url:
                target_url = base_url

    if not target_url:
        return make_response(b"", 404)

    target_url = unquote(target_url)
    parsed_target = urlparse(target_url)
    full_url = f"{parsed_target.scheme}://{parsed_target.netloc}/{resource_path}"

    session_id = _get_proxy_session_id()

    try:
        body, status_code, headers = UiProxyService.fetch_resource(
            full_url,
            method="GET",
            session_id=session_id,
        )
    except Exception:
        return make_response(b"", 404)

    # 内容类型校验
    content_type = headers.get("Content-Type", "")
    from urllib.parse import urlparse as _up
    _ext = _up(full_url).path.rsplit(".", 1)[-1].lower() if "." in _up(full_url).path else ""
    _binary_exts = {"png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp", "woff", "woff2", "ttf", "eot", "otf"}
    if _ext in _binary_exts and content_type.startswith("text/"):
        return make_response(b"", 404)

    resp = make_response(body, status_code)
    for key, value in headers.items():
        if key == "_set_cookies":
            for cookie_str in value:
                resp.headers.add("Set-Cookie", cookie_str)
        else:
            resp.headers[key] = value
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers.add("Set-Cookie", f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age=3600; Path=/")
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
        logger.warning("Case not found: id=%s, available_files=%s", case_id,
                       [f.name for f in _case_store._cases_dir.glob("case_*.json")])
        return json_error(f"用例不存在: {case_id}", 404, "UIT_CASE_002")
    logger.info("Case loaded: id=%s, steps=%d", case_id, len(case.get("steps", [])))
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


def ui_proxy_sessions_debug() -> ResponseReturnValue:
    """调试端点：导出所有活跃代理会话的 cookie 状态。"""
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store
    sessions = _proxy_session_store.dump_sessions()
    return BaseHandler.json_response({
        "active_sessions": len(sessions),
        "sessions": sessions,
    })

