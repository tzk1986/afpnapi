"""UI 测试模块路由处理函数。

提供页面渲染（首页、录制器、编辑器）和 API（代理、用例 CRUD、录制会话管理）。
"""

import logging
import time
import uuid
from typing import Any, Dict, Optional, Union, cast
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from flask import abort, make_response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from postman_api_tester.config import REPORT_SERVER_PORT
from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.ui_case_store import UiCaseStore
from postman_api_tester.services.ui_proxy_service import UiProxyService
from postman_api_tester.services.ui_recorder_inject import get_replayer_js
from postman_api_tester.services.ui_recording_store import RecordingSessionStore
from postman_api_tester.utils.security import sanitize_cookies

logger = logging.getLogger(__name__)

# 全局实例
_case_store = UiCaseStore()
_recording = RecordingSessionStore()

# 命名常量
MAX_PROXY_UNWRAP_DEPTH = 5
PROXY_COOKIE_MAX_AGE = 3600


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
    from postman_api_tester.utils.security import check_proxy_host_allowed

    result = check_proxy_host_allowed(url, PROXY_ALLOWED_HOSTS, "UIT_PROXY_005")
    if result:
        msg, status, code = result
        logger.warning(
            "ui_proxy_host_blocked",
            extra={"event": "ui.proxy.host_blocked", "url": url, "host": urlparse(url).hostname},
        )
        return json_error(msg, status, code)
    return None


def _extract_origin(url: str) -> str:
    """从 URL 提取 origin（scheme://netloc）。"""
    if not url:
        return ""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url


def _handle_cross_origin_session(
    sid: str,
    target_origin: str,
    session_origin: str,
) -> str:
    """跨域 Token 继承：查找或创建目标 origin 的 session，传递 Token。"""
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    logger.info(
        "proxy_session_origin_mismatch",
        extra={
            "event": "ui.proxy.session.origin_mismatch",
            "cookie_session_id": sid[:8],
            "cookie_session_origin": session_origin,
            "target_origin": target_origin,
        },
    )

    existing_sid = _proxy_session_store.find_session_by_base_url(target_origin)
    _subsystem_token = _proxy_session_store.get_subsystem_token(sid)

    if existing_sid:
        existing_jar = _proxy_session_store.get_cookie_jar(existing_sid)
        _cross_token = _subsystem_token or _proxy_session_store.get_token(sid)
        if _cross_token:
            target_token = _proxy_session_store.get_token(existing_sid)
            if not target_token or (_subsystem_token and target_token != _subsystem_token):
                _proxy_session_store.set_token(existing_sid, _cross_token)
                if _subsystem_token:
                    _proxy_session_store.set_subsystem_token(existing_sid, _subsystem_token)
                logger.info(
                    "proxy_session_shared_token_cross_origin",
                    extra={
                        "event": "ui.proxy.session.shared_token",
                        "source_session_id": sid[:8],
                        "target_session_id": existing_sid[:8],
                        "target_origin": target_origin,
                        "token_source": "subsystem" if _subsystem_token else "platform",
                    },
                )
        logger.info(
            "proxy_session_reuse_cross_origin",
            extra={
                "event": "ui.proxy.session.reuse_cross_origin",
                "session_id": existing_sid[:8],
                "base_url": target_origin,
                "cookies_in_jar": [c.name for c in existing_jar] if existing_jar else [],
            },
        )
        return existing_sid

    new_sid = _proxy_session_store.create_session(target_origin)
    _cross_token = _subsystem_token or _proxy_session_store.get_token(sid)
    if _cross_token:
        _proxy_session_store.set_token(new_sid, _cross_token)
        if _subsystem_token:
            _proxy_session_store.set_subsystem_token(new_sid, _subsystem_token)
        logger.info(
            "proxy_session_shared_token_new_cross_origin",
            extra={
                "event": "ui.proxy.session.shared_token_new",
                "source_session_id": sid[:8],
                "new_session_id": new_sid[:8],
                "target_origin": target_origin,
                "token_source": "subsystem" if _subsystem_token else "platform",
            },
        )
    logger.info(
        "proxy_session_created_cross_origin",
        extra={
            "event": "ui.proxy.session.new_cross_origin",
            "session_id": new_sid[:8],
            "base_url": target_origin,
        },
    )
    return new_sid


def _find_session_by_cookie(base_url: str, target_origin: str) -> "str | None":
    """从 Cookie 查找 session，处理 origin 匹配和跨域继承。"""
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    sid = request.cookies.get("_proxy_session")
    if not sid:
        return None

    jar = _proxy_session_store.get_cookie_jar(sid)
    if jar is None:
        logger.warning(
            "proxy_session_cookie_but_not_found",
            extra={
                "event": "ui.proxy.session.missing",
                "session_id": sid[:8],
                "browser_cookies": sanitize_cookies(dict(request.cookies)),
            },
        )
        return None

    session_base_url = _proxy_session_store.get_base_url(sid)
    session_origin = _extract_origin(session_base_url) if session_base_url else ""

    if target_origin and session_origin and target_origin != session_origin:
        return _handle_cross_origin_session(sid, target_origin, session_origin)

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


def _find_session_by_referer() -> "str | None":
    """从 Referer 提取目标 URL 以复用 session。"""
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    referer = request.headers.get("Referer", "")
    if not referer or "/ui-testing/proxy?url=" not in referer:
        return None

    try:
        ref_qs = referer.split("/ui-testing/proxy?url=", 1)[1].split("&")[0]
        ref_base_url = unquote(ref_qs)
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
        return None


def _create_new_session_with_inheritance(base_url: str) -> str:
    """创建新 session，继承同 origin Token 并加载浏览器 JSESSIONID。"""
    from http.cookiejar import Cookie as _Cookie

    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    logger.warning(
        "proxy_session_creating_new",
        extra={
            "event": "ui.proxy.session.creating_new",
            "base_url": base_url,
            "browser_cookies": sanitize_cookies(dict(request.cookies)),
            "referer": request.headers.get("Referer", "")[:100],
            "origin": request.headers.get("Origin", ""),
            "request_path": request.path,
        },
    )
    new_sid = _proxy_session_store.create_session(base_url)

    if base_url:
        origin = _extract_origin(base_url)
        _existing_sid = _proxy_session_store.find_session_by_base_url(origin)
        if _existing_sid and _existing_sid != new_sid:
            _inherited_token = _proxy_session_store.get_token(_existing_sid)
            if _inherited_token:
                _proxy_session_store.set_token(new_sid, _inherited_token)
                logger.info(
                    "proxy_session_token_inherited",
                    extra={
                        "event": "ui.proxy.session.token_inherited",
                        "new_session_id": new_sid[:8],
                        "source_session_id": _existing_sid[:8],
                        "base_url": base_url,
                    },
                )

    browser_jsessionid = request.cookies.get("JSESSIONID")
    if browser_jsessionid:
        cookie_jar = _proxy_session_store.get_cookie_jar(new_sid)
        if cookie_jar is not None:
            try:
                parsed = urlparse(base_url or "")
                domain = parsed.netloc if parsed.netloc else ""
                path = parsed.path if parsed.path else "/"
                c = _Cookie(
                    version=0,
                    name="JSESSIONID",
                    value=browser_jsessionid,
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=bool(domain),
                    domain_initial_dot=False,
                    path=path,
                    path_specified=True,
                    secure=False,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
                cookie_jar.set_cookie(c)
                logger.info(
                    "proxy_session_loaded_browser_cookie",
                    extra={
                        "event": "ui.proxy.session.browser_cookie_loaded",
                        "session_id": new_sid[:8],
                        "jsessionid_prefix": browser_jsessionid[:20] + "...",
                    },
                )
            except Exception as e:
                logger.warning(
                    "proxy_session_load_browser_cookie_failed",
                    extra={
                        "event": "ui.proxy.session.browser_cookie_failed",
                        "session_id": new_sid[:8],
                        "error": str(e),
                    },
                )

    logger.info(
        "proxy_session_created_new",
        extra={
            "event": "ui.proxy.session.new",
            "session_id": new_sid[:8],
            "base_url": base_url,
            "browser_cookies": sanitize_cookies(dict(request.cookies)),
        },
    )
    return new_sid


def _get_proxy_session_id(base_url: str = "") -> str:
    """从 Cookie 或新创建的代理会话中获取 session ID。

    查找顺序：Cookie -> Referer -> 新建。跨域时自动继承 Token。
    """
    target_origin = _extract_origin(base_url)

    result = _find_session_by_cookie(base_url, target_origin)
    if result:
        return result

    result = _find_session_by_referer()
    if result:
        return result

    return _create_new_session_with_inheritance(base_url)


def _prepare_proxy_context() -> "tuple[str, str, bool, bool] | ResponseReturnValue":
    """解析 URL 参数、解包嵌套代理、检测模式。

    Returns:
        (target_url, base_url, recording_mode, replay_mode) 或错误响应。
    """
    target_url = request.args.get("url", "")
    logger.info(
        "proxy_request_incoming",
        extra={
            "event": "ui.proxy.request_in",
            "raw_url_param": target_url[:100] if target_url else "(empty)",
            "full_request_url": request.url[:200],
            "method": request.method,
            "recording": request.args.get("recording", ""),
            "replay": request.args.get("replay", ""),
            "cookies": sanitize_cookies(dict(request.cookies)),
        },
    )

    if not target_url:
        return json_error("缺少 url 参数", 400, "UIT_PROXY_001")

    target_url = unquote(target_url)
    logger.info(
        "proxy_url_decoded",
        extra={"event": "ui.proxy.url_decoded", "decoded_url": target_url[:200]},
    )

    _max_unwrap = MAX_PROXY_UNWRAP_DEPTH
    for _ in range(_max_unwrap):
        _parsed = urlparse(target_url)
        if _parsed.hostname in ("127.0.0.1", "localhost") and _parsed.port == REPORT_SERVER_PORT:
            from urllib.parse import parse_qs as _pqs

            _qs = _pqs(_parsed.query)
            _inner_url = _qs.get("url", [""])[0]
            if _inner_url and _inner_url.startswith(("http://", "https://")):
                logger.debug(
                    "unwrap_nested_proxy",
                    extra={"from": target_url[:80], "to": _inner_url[:80]},
                )
                target_url = _inner_url
                continue
        break

    if not target_url.startswith(("http://", "https://")):
        return json_error("url 必须是 http/https 地址", 400, "UIT_PROXY_002")

    parsed_target = urlparse(target_url)
    if parsed_target.hostname in ("127.0.0.1", "localhost") and parsed_target.port == REPORT_SERVER_PORT:
        return json_error(
            f"目标地址不能是代理服务器自身: {target_url[:100]}", 400, "UIT_PROXY_005"
        )

    host_error = _check_ui_proxy_host_allowed(target_url)
    if host_error is not None:
        return host_error

    base_url = f"{parsed_target.scheme}://{parsed_target.netloc}"
    recording_mode = request.args.get("recording", "") == "1"
    replay_mode = request.args.get("replay", "") == "1"

    logger.info(
        "proxy_mode_detected",
        extra={
            "event": "ui.proxy.mode_detected",
            "base_url": base_url,
            "recording_mode": recording_mode,
            "replay_mode": replay_mode,
            "target_path": parsed_target.path,
        },
    )
    return target_url, base_url, recording_mode, replay_mode


def _get_or_create_proxy_session(base_url: str, recording_mode: bool) -> str:
    """获取或创建代理会话，录制模式下清除旧会话。"""
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    if recording_mode:
        old_sid = request.cookies.get("_proxy_session")
        if old_sid:
            _proxy_session_store.delete_session(old_sid)
            logger.info(
                "recording_clear_old_session",
                extra={
                    "event": "ui.recording.session_cleared",
                    "old_session_id": old_sid[:8],
                },
            )
        session_id = _proxy_session_store.create_session(base_url)
        logger.info(
            "recording_new_session_created",
            extra={
                "event": "ui.recording.session.new",
                "session_id": session_id[:8],
                "base_url": base_url,
            },
        )
    else:
        session_id = _get_proxy_session_id(base_url)

    session_cookie_jar = _proxy_session_store.get_cookie_jar(session_id)
    session_cookies_detail = {}
    if session_cookie_jar:
        for c in session_cookie_jar:
            session_cookies_detail[c.name] = {
                "value": c.value[:30] + "..." if len(c.value) > 30 else c.value,
                "domain": c.domain,
                "path": c.path,
            }
    else:
        logger.warning(
            "proxy_session_jar_is_none",
            extra={
                "event": "ui.proxy.session.jar_none",
                "session_id": session_id[:8],
                "target_url": request.args.get("url", "")[:100],
            },
        )

    logger.info(
        "proxy_session_ready",
        extra={
            "event": "ui.proxy.session_ready",
            "session_id": session_id[:8],
            "target_url": request.args.get("url", "")[:200],
            "base_url": base_url,
            "session_cookies": session_cookies_detail,
            "browser_cookies": sanitize_cookies(dict(request.cookies)),
            "_proxy_session_store_id": id(_proxy_session_store),
        },
    )
    return session_id


def _execute_proxy_fetch(
    target_url: str,
    session_id: str,
    base_url: str,
    replay_mode: bool,
    recording_mode: bool,
) -> "tuple[str | bytes, int, dict] | ResponseReturnValue":
    """执行 fetch_and_rewrite，返回 (body, status_code, headers) 或错误响应。"""
    started_at = time.perf_counter()
    logger.info(
        "proxy_fetch_start",
        extra={
            "event": "ui.proxy.fetch_start",
            "target_url": target_url[:200],
            "session_id": session_id[:8],
            "method": request.method,
        },
    )
    try:
        _replay_engine_js = ""
        if replay_mode:
            from postman_api_tester.services.ui_recorder_inject import get_replayer_js

            _replay_engine_js = get_replayer_js(base_url)
        body, status_code, headers = UiProxyService.fetch_and_rewrite(
            target_url,
            session_id,
            method=request.method,
            req_headers=dict(request.headers),
            req_body=request.get_data() if request.method != "GET" else None,
            replay_mode=replay_mode,
            recording_mode=recording_mode,
            replay_engine_js=_replay_engine_js,
        )
        logger.info(
            "proxy_fetch_completed",
            extra={
                "event": "ui.proxy.fetch_completed",
                "target_url": target_url[:200],
                "status_code": status_code,
                "body_size": len(body) if isinstance(body, (str, bytes)) else 0,
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            },
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
    return body, status_code, headers


def _build_proxy_response(
    body: "str | bytes",
    status_code: int,
    headers: dict,
    session_id: str,
    target_url: str,
    base_url: str,
) -> ResponseReturnValue:
    """重写 Location、构建响应、设置 Cookie。"""
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
    resp.headers.add(
        "Set-Cookie",
        f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age={PROXY_COOKIE_MAX_AGE}; Path=/",
    )

    logger.info(
        "proxy_page_response_to_browser",
        extra={
            "event": "ui.proxy.page.resp_to_browser",
            "session_id": session_id[:8],
            "url": target_url,
            "status_code": status_code,
            "browser_sent_cookies": sanitize_cookies(dict(request.cookies)),
            "set_cookies_returned": set_cookies_sent,
        },
    )
    return resp


def ui_testing_proxy() -> ResponseReturnValue:
    """反向代理端点：获取外部 URL 并改写 HTML。"""
    ctx = _prepare_proxy_context()
    if not isinstance(ctx, tuple) or len(ctx) != 4:
        return ctx
    target_url, base_url, recording_mode, replay_mode = ctx

    session_id = _get_or_create_proxy_session(base_url, recording_mode)

    fetch_result = _execute_proxy_fetch(
        target_url, session_id, base_url, replay_mode, recording_mode
    )
    if not isinstance(fetch_result, tuple) or len(fetch_result) != 3:
        return fetch_result
    body, status_code, headers = fetch_result

    return _build_proxy_response(
        cast("str | bytes", body), status_code, cast(dict, headers),
        session_id, target_url, base_url
    )


def ui_testing_proxy_resource() -> ResponseReturnValue:
    """代理子资源（CSS/JS/图片/API 调用），支持所有 HTTP 方法。"""
    target_url = request.args.get("url", "")
    if not target_url:
        return json_error("缺少 url 参数", 400, "UIT_RES_001")

    # 循环解码直到 URL 稳定（处理双重编码问题）
    _prev = target_url
    while True:
        target_url = unquote(target_url)
        if target_url == _prev:
            break
        _prev = target_url

    if not target_url.startswith(("http://", "https://")):
        return json_error("url 必须是 http/https 地址", 400, "UIT_RES_002")

    host_error = _check_ui_proxy_host_allowed(target_url)
    if host_error is not None:
        return host_error

    # 根据目标 URL 的 origin 匹配 session，确保跨系统资源使用正确的 session
    from urllib.parse import urlparse as _urlparse

    _resource_origin = (
        _urlparse(target_url).scheme + "://" + _urlparse(target_url).netloc
    )
    session_id = _get_proxy_session_id(_resource_origin)

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

    _ext = (
        _up(target_url).path.rsplit(".", 1)[-1].lower()
        if "." in _up(target_url).path
        else ""
    )
    _binary_exts = {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "ico",
        "webp",
        "bmp",
        "woff",
        "woff2",
        "ttf",
        "eot",
        "otf",
        "mp4",
        "webm",
        "ogg",
        "pdf",
        "zip",
    }
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
            css_text = UiProxyService._rewrite_css_urls(
                css_text, target_url, target_url
            )
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
            _target_base = (
                target_url.rsplit("/", 1)[0] if "/" in target_url else target_url
            )
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
    resp.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, PUT, DELETE, PATCH, OPTIONS"
    )
    resp.headers["Access-Control-Allow-Headers"] = "*"
    # 设置代理会话 Cookie
    resp.headers.add(
        "Set-Cookie",
        f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age={PROXY_COOKIE_MAX_AGE}; Path=/",
    )

    # 仅对 API 请求记录 cookie 详情（跳过静态资源）
    if "/api/" in target_url or target_url.endswith(("/login", "/kaptcha")):
        logger.info(
            "proxy_resource_response_to_browser",
            extra={
                "event": "ui.proxy.resource.resp_to_browser",
                "session_id": session_id[:8],
                "url": target_url,
                "method": request.method,
                "status_code": status_code,
                "browser_sent_cookies": sanitize_cookies(dict(request.cookies)),
                "set_cookies_returned": set_cookies_sent,
            },
        )
    return resp


def ui_testing_static_fallback(filename: str = "") -> ResponseReturnValue:
    """静态资源兜底：转发 SPA 动态 import() 加载的 /static/... 资源到目标服务器。

    通过 Referer 中的 proxy URL 或 Cookie session 提取目标地址。
    """
    from postman_api_tester.services.ui_proxy_service import (
        UiProxyService,
        _proxy_session_store,
    )

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
            latest_sid = max(
                all_sessions, key=lambda item: item[1].get("last_active", 0)
            )[0]
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

    _ext = (
        _up(full_url).path.rsplit(".", 1)[-1].lower()
        if "." in _up(full_url).path
        else ""
    )
    _binary_exts = {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "ico",
        "webp",
        "bmp",
        "woff",
        "woff2",
        "ttf",
        "eot",
        "otf",
    }
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
    resp.headers.add(
        "Set-Cookie",
        f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age={PROXY_COOKIE_MAX_AGE}; Path=/",
    )
    return resp


def ui_testing_spa_resource_fallback(resource_path: str) -> ResponseReturnValue:
    """SPA 资源/API 兜底：拦截所有未被其他路由处理的请求，转发到目标服务器。

    从 ``report_server.py`` 迁移，覆盖早期脚本 fetch 拦截器未覆盖的情况。
    """
    _ext = resource_path.rsplit(".", 1)[-1].lower() if "." in resource_path else ""
    _resource_exts = {
        "png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp",
        "woff", "woff2", "ttf", "eot", "otf", "css", "js",
    }
    _skip_prefixes = {"ui-testing/", "ui-recorder/", "favicon.ico"}
    for prefix in _skip_prefixes:
        if resource_path.startswith(prefix):
            abort(404)
    _proxy_api_prefixes = {"api/ui-testing/", "api/ui-recorder/", "api/postman/", "api/report/"}
    for prefix in _proxy_api_prefixes:
        if resource_path.startswith(prefix):
            abort(404)

    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        return resp

    is_resource = _ext in _resource_exts
    _req_accept = request.headers.get("Accept", "")
    _req_content_type = request.headers.get("Content-Type", "")
    _req_xhr = request.headers.get("X-Requested-With", "")
    _is_api_by_header = (
        "application/json" in _req_accept
        or "application/json" in _req_content_type
        or _req_xhr.lower() == "xmlhttprequest"
    )
    _is_api_by_path = "/api/" in resource_path or resource_path.startswith("api/")
    is_api = _is_api_by_header or _is_api_by_path
    is_page = not is_resource and not is_api

    params = parse_qs(request.query_string.decode("utf-8", errors="replace"))
    target_url = params.get("_proxy_url", [""])[0] or params.get("url", [""])[0]

    referer = request.headers.get("Referer", "")
    if not target_url and referer:
        try:
            parsed_ref = urlparse(referer)
            ref_params = parse_qs(parsed_ref.query)
            target_url = (
                ref_params.get("_proxy_url", [""])[0] or ref_params.get("url", [""])[0]
            )
        except Exception:
            pass

    _diag_headers = {
        k: v
        for k, v in request.headers
        if k.lower() in (
            "referer", "origin", "cookie", "accept", "content-type",
            "user-agent", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
        )
    }
    logger.warning(
        "spa_fallback_request",
        extra={
            "event": "ui.proxy.fallback_request",
            "method": request.method,
            "path": resource_path,
            "is_page": is_page,
            "referer": referer if referer else "(none)",
            "diag_headers": _diag_headers,
            "diag_cookies": sanitize_cookies(dict(request.cookies)),
            "diag_query_string": request.query_string.decode("utf-8", errors="replace")[:200],
        },
    )

    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    if not target_url:
        session_id_cookie = request.cookies.get("_proxy_session")
        if session_id_cookie:
            target_url = _proxy_session_store.get_base_url(session_id_cookie) or ""

    if not target_url:
        with _proxy_session_store._lock:
            all_sessions = list(_proxy_session_store._sessions.items())
        if all_sessions:
            latest_sid = max(
                all_sessions, key=lambda item: item[1].get("last_active", 0)
            )[0]
            target_url = _proxy_session_store.get_base_url(latest_sid) or ""

    if not target_url:
        abort(404)

    target_url = unquote(target_url)
    parsed_target = urlparse(target_url)
    full_url = f"{parsed_target.scheme}://{parsed_target.netloc}/{resource_path}"

    _proxy_params = {"_proxy_url", "url", "replay", "recording"}
    _forward_params = {k: v[0] for k, v in params.items() if k not in _proxy_params}
    if _forward_params:
        full_url += "?" + urlencode(_forward_params)
        logger.info(
            "spa_fallback_forward_params",
            extra={
                "event": "ui.proxy.fallback.forward_params",
                "params": list(_forward_params.keys()),
            },
        )

    base_url = f"{parsed_target.scheme}://{parsed_target.netloc}"
    replay_mode = params.get("replay", [""])[0] == "1"
    recording_mode = params.get("recording", [""])[0] == "1"

    if recording_mode:
        old_sid = request.cookies.get("_proxy_session")
        if old_sid:
            _proxy_session_store.delete_session(old_sid)
            logger.info(
                "spa_fallback_recording_clear_session",
                extra={
                    "event": "ui.proxy.fallback.recording_clear",
                    "old_session_id": old_sid[:8],
                },
            )
        session_id = _proxy_session_store.create_session(base_url)
        logger.info(
            "spa_fallback_recording_new_session",
            extra={
                "event": "ui.proxy.fallback.recording_new",
                "session_id": session_id[:8],
                "base_url": base_url,
            },
        )
    else:
        session_id = _get_proxy_session_id(base_url)

    try:
        body: Union[str, bytes]
        if is_page:
            replay_engine_js = ""
            if replay_mode:
                origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
                replay_engine_js = get_replayer_js(origin)
            body, status_code, headers = UiProxyService.fetch_and_rewrite(
                full_url,
                session_id if session_id else None,
                method=request.method,
                req_headers=dict(request.headers),
                req_body=request.get_data() if request.method != "GET" else None,
                replay_mode=replay_mode,
                recording_mode=recording_mode,
                replay_engine_js=replay_engine_js,
            )
        else:
            body, status_code, headers = UiProxyService.fetch_resource(
                full_url,
                method=request.method,
                req_headers=dict(request.headers),
                req_body=request.get_data() if request.method not in ("GET", "HEAD") else None,
                session_id=session_id if session_id else None,
            )
    except Exception:
        return make_response(b"", 404)

    if is_resource:
        content_type = headers.get("Content-Type", "")
        _binary_exts = {
            "png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp",
            "woff", "woff2", "ttf", "eot", "otf",
        }
        if _ext in _binary_exts and content_type.startswith("text/"):
            return make_response(b"", 404)

    if is_page and "Location" in headers and "_proxy_url" not in headers["Location"]:
        from urllib.parse import quote as _quote2

        loc = headers["Location"]
        if loc.startswith(("http://", "https://")):
            loc_parsed = urlparse(loc)
            loc_path = (
                loc_parsed.pathname
                + ("?" + loc_parsed.query if loc_parsed.query else "")
                + ("#" + loc_parsed.fragment if loc_parsed.fragment else "")
            )
            sep = "&" if "?" in loc_path else "?"
            headers["Location"] = loc_path + sep + "_proxy_url=" + _quote2(loc, safe="")
        elif loc.startswith("/"):
            full_loc = base_url + loc
            loc_path = loc
            sep = "&" if "?" in loc_path else "?"
            headers["Location"] = loc_path + sep + "_proxy_url=" + _quote2(full_loc, safe="")

    resp = make_response(body, status_code)
    for key, value in headers.items():
        if key == "_set_cookies":
            for cookie_str in value:
                resp.headers.add("Set-Cookie", cookie_str)
        else:
            resp.headers[key] = value
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    if session_id:
        resp.headers.add(
            "Set-Cookie",
            f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age={PROXY_COOKIE_MAX_AGE}; Path=/",
        )
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
        logger.warning(
            "Case not found: id=%s, available_files=%s",
            case_id,
            [f.name for f in _case_store._cases_dir.glob("case_*.json")],
        )
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
    return BaseHandler.json_response(
        {
            "session_id": session_id,
            "status": "recording",
            "started_at": session["started_at"],
        }
    )


def api_ui_testing_recording_step() -> ResponseReturnValue:
    """添加录制步骤或回填响应数据。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_REC_001")

    session_id = payload.get("session_id", "")
    step = payload.get("step", {})

    if not session_id:
        return json_error("缺少 session_id", 400, "UIT_REC_002")

    if payload.get("is_response_update"):
        net_id = step.get("_net_id")
        if net_id is not None:
            _recording.update_step_response(
                session_id, int(net_id), step.get("network_response", {})
            )
        return BaseHandler.json_response({"ok": True})

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
    return BaseHandler.json_response(
        {
            "session_id": session_id,
            "status": "completed",
            "step_count": step_count,
            "ended_at": session["ended_at"],
        }
    )


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
    return BaseHandler.json_response(
        {
            "active_sessions": len(sessions),
            "sessions": sessions,
        }
    )
