"""UI 测试反向代理服务。

获取外部 URL 的 HTML 内容，改写所有资源引用指向代理端点，
并注入录制器脚本，使目标页面可在 iframe 中安全展示和交互。
"""

import logging
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

PROXY_PREFIX = "/ui-testing/proxy"
RESOURCE_PROXY_PREFIX = "/ui-testing/proxy-resource"

_SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav",
    ".pdf", ".zip", ".tar", ".gz",
}

_CONTENT_TYPE_MAP = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}

# ── 代理 Cookie 会话管理 ──

class _ProxySessionStore:
    """代理 Cookie 会话存储 — 将目标服务器的 Cookie 转发给浏览器，反之亦然。"""

    _TTL = 3600  # 会话 1 小时过期

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict] = {}

    def create_session(self, base_url: str = "") -> str:
        sid = str(uuid.uuid4())
        with self._lock:
            self._sessions[sid] = {
                "cookies": requests.cookies.RequestsCookieJar(),
                "base_url": base_url,
                "last_active": time.time(),
                "token": "",  # 存储从 API 请求捕获的 Token
            }
        return sid

    def get_cookie_jar(self, session_id: str) -> Optional[requests.cookies.RequestsCookieJar]:
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                s["last_active"] = time.time()
                return s["cookies"]
            return None

    def set_token(self, session_id: str, token: str) -> None:
        """存储 Token（从 API 请求捕获，用于后续页面请求）。"""
        if not token or token == "null":
            return
        with self._lock:
            s = self._sessions.get(session_id)
            if s and s.get("token") != token:
                s["token"] = token
                s["last_active"] = time.time()
                logger.info(
                    "proxy_session_token_stored",
                    extra={
                        "event": "ui.proxy.session.token_stored",
                        "session_id": session_id[:8],
                        "token_preview": token[:30] + "..." if len(token) > 30 else token,
                    },
                )

    def get_token(self, session_id: str) -> Optional[str]:
        """获取存储的 Token。"""
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                s["last_active"] = time.time()
                return s.get("token", "")
            return None

    def get_base_url(self, session_id: str) -> Optional[str]:
        """获取会话关联的目标基础 URL。"""
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                s["last_active"] = time.time()
                return s.get("base_url", "")
            return None

    def set_base_url(self, session_id: str, base_url: str) -> None:
        """更新会话关联的目标基础 URL。"""
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                s["base_url"] = base_url
                s["last_active"] = time.time()

    def find_session_by_base_url(self, base_url: str) -> Optional[str]:
        """根据目标基础 URL 查找已有会话 ID。"""
        with self._lock:
            for sid, s in self._sessions.items():
                if s.get("base_url") == base_url:
                    s["last_active"] = time.time()
                    return sid
            return None

    def clear_cookies_by_base_url(self, base_url: str) -> int:
        """清除指定 base_url 对应的所有 session cookie（回放前清理旧登录态）。
        返回清除的 session 数量。

        注意：base_url 可能带路径（如 /login），但 session 存的是 origin。
        所以只比较 origin（scheme + netloc），忽略路径差异。
        """
        cleared = 0
        # 提取 origin 用于匹配（忽略路径）
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        target_origin = f"{parsed.scheme}://{parsed.netloc}"

        with self._lock:
            for sid, s in self._sessions.items():
                session_base = s.get("base_url", "")
                # 比较 origin
                session_parsed = urlparse(session_base)
                session_origin = f"{session_parsed.scheme}://{session_parsed.netloc}"
                if session_origin == target_origin and target_origin:
                    old_count = len(s["cookies"])
                    s["cookies"] = requests.cookies.RequestsCookieJar()
                    s["last_active"] = time.time()
                    logger.info(
                        "proxy_session_cookies_cleared",
                        extra={
                            "event": "ui.proxy.session.cookies_cleared",
                            "session_id": sid[:8],
                            "session_base_url": session_base,
                            "target_base_url": base_url,
                            "cookies_cleared": old_count,
                        },
                    )
                    cleared += 1
        if cleared > 0:
            logger.info(
                "proxy_session_clear_summary",
                extra={
                    "event": "ui.proxy.session.clear_summary",
                    "target_origin": target_origin,
                    "sessions_cleared": cleared,
                },
            )
        return cleared

    def update_cookies(self, session_id: str, resp_cookies: requests.cookies.RequestsCookieJar) -> None:
        """更新 session cookie，确保同名 cookie 被替换而非共存。

        解决问题：浏览器 JSESSIONID 加载后，目标服务器响应 Set-Cookie 返回新 JSESSIONID，
        如果直接 update() 会因 domain/path 不同导致 jar 中出现两个同名 JSESSIONID。
        """
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return
            s["last_active"] = time.time()
            jar = s["cookies"]

            # 诊断日志：记录更新前的 jar 状态
            jar_before = [c.name for c in jar]
            resp_names = [c.name for c in resp_cookies]
            logger.info(
                "proxy_update_cookies_debug",
                extra={
                    "event": "ui.proxy.update_cookies.debug",
                    "session_id": session_id[:8],
                    "jar_before": jar_before,
                    "resp_cookies": resp_names,
                    "resp_cookies_len": len(resp_names),
                },
            )

            # 如果没有新 cookie，直接返回（避免意外清空）
            if not resp_names:
                logger.info(
                    "proxy_update_cookies_skip",
                    extra={
                        "event": "ui.proxy.update_cookies.skip",
                        "session_id": session_id[:8],
                        "jar_unchanged": jar_before,
                    },
                )
                return

            # 先清除 jar 中与新 cookie 同名的所有旧 cookie（按名称匹配，不依赖 domain/path）
            new_cookie_names = set(resp_names)
            for domain in list(jar._cookies.keys()):
                for path in list(jar._cookies[domain].keys()):
                    for name in new_cookie_names:
                        jar._cookies[domain][path].pop(name, None)
                    if not jar._cookies[domain][path]:
                        del jar._cookies[domain][path]
                if not jar._cookies[domain]:
                    del jar._cookies[domain]

            # 添加新的 cookies
            for c in resp_cookies:
                jar.set_cookie(c)

            # 诊断日志：记录更新后的 jar 状态
            jar_after = [c.name for c in jar]
            logger.info(
                "proxy_update_cookies_done",
                extra={
                    "event": "ui.proxy.update_cookies.done",
                    "session_id": session_id[:8],
                    "jar_after": jar_after,
                    "added": resp_names,
                },
            )

    def delete_session(self, session_id: str) -> bool:
        """删除指定会话。"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def get_set_cookie_headers(self, session_id: str) -> List[str]:
        """将存储的 Cookie 转为浏览器可接收的 Set-Cookie 头列表。

        移除 Domain 属性（让浏览器默认为代理域），
        移除 Secure 标志（代理可能通过 HTTP 服务）。
        """
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return []
            result = []
            for cookie in s["cookies"]:
                parts = [f"{cookie.name}={cookie.value}"]
                if cookie.path:
                    parts.append(f"Path={cookie.path}")
                if cookie.expires:
                    from email.utils import formatdate
                    parts.append(f"Expires={formatdate(cookie.expires, usegmt=True)}")
                if cookie.has_nonstandard_attr("HttpOnly"):
                    parts.append("HttpOnly")
                parts.append("SameSite=Lax")
                result.append("; ".join(parts))
            return result

    def dump_sessions(self) -> List[Dict]:
        """导出所有活跃会话的摘要（调试用）。"""
        with self._lock:
            result = []
            for sid, s in self._sessions.items():
                jar = s["cookies"]
                result.append({
                    "session_id": sid[:8],
                    "base_url": s.get("base_url", ""),
                    "last_active_ago": round(time.time() - s["last_active"]),
                    "cookies": [{
                        "name": c.name,
                        "value_preview": c.value[:30] + "..." if len(c.value) > 30 else c.value,
                        "domain": c.domain,
                        "path": c.path,
                    } for c in jar],
                })
            return result

    def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            expired = [sid for sid, s in self._sessions.items()
                       if now - s["last_active"] > self._TTL]
            for sid in expired:
                del self._sessions[sid]
                removed += 1
        return removed


_proxy_session_store = _ProxySessionStore()

# 定时清理过期会话
def _start_session_cleanup() -> None:
    def _cleanup_loop() -> None:
        while True:
            time.sleep(300)
            try:
                removed = _proxy_session_store.cleanup_expired()
                if removed:
                    logger.debug("Cleaned up %d expired proxy sessions", removed)
            except Exception:
                pass
    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()

_start_session_cleanup()


class UiProxyService:
    """反向代理：获取外部 URL 并改写 HTML 以支持 iframe 嵌入。"""

    REQUEST_TIMEOUT = 15
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB

    @classmethod
    def fetch_and_rewrite(
        cls,
        url: str,
        session_id: Optional[str] = None,
        method: str = "GET",
        req_headers: Optional[Dict[str, str]] = None,
        req_body: Optional[bytes] = None,
        replay_mode: bool = False,
        recording_mode: bool = False,
        replay_engine_js: str = "",
    ) -> Tuple[str, int, Dict[str, Any]]:
        """获取外部 URL 并改写 HTML。

        Args:
            url: 目标 URL
            session_id: 代理会话 ID（用于 Cookie 转发）
            method: HTTP 方法（GET/POST）
            req_headers: 原始请求头（转发 Content-Type 等）
            req_body: 原始请求体（POST 时使用）
            replay_mode: 是否为回放模式
            recording_mode: 是否为录制模式
            replay_engine_js: 回放引擎 JavaScript 代码（回放模式时注入）

        Returns:
            (body, status_code, response_headers)

        Raises:
            requests.RequestException: 网络请求失败
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"仅支持 http/https 协议: {url}")

        target_origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": target_origin + "/",
        }
        if req_headers:
            for key in ("Content-Type",):
                if key in req_headers:
                    headers[key] = req_headers[key]
            # 转发 Token 请求头（用于目标服务器认证）
            token_value = req_headers.get("Token", "")
            # 如果浏览器没有发送 Token，从 session store 获取之前 API 请求捕获的 Token
            if (not token_value or token_value == "null") and session_id:
                stored_token = _proxy_session_store.get_token(session_id)
                if stored_token:
                    token_value = stored_token
                    logger.info(
                        "proxy_page_token_from_store",
                        extra={
                            "event": "ui.proxy.page.token_from_store",
                            "session_id": session_id[:8],
                            "url": url,
                            "token_preview": token_value[:30] + "..." if len(token_value) > 30 else token_value,
                        },
                    )
            logger.info(
                "proxy_page_token_debug",
                extra={
                    "event": "ui.proxy.page.token_debug",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "token_in_req_headers": token_value[:20] + "..." if len(token_value) > 20 else token_value,
                    "token_is_null": token_value == "null" or not token_value,
                },
            )
            if token_value and token_value != "null":
                headers["Token"] = token_value

        session = requests.Session()
        if session_id:
            cookie_jar = _proxy_session_store.get_cookie_jar(session_id)
            logger.info(
                "proxy_page_request_cookies_debug",
                extra={
                    "event": "ui.proxy.page.req.cookies_debug",
                    "session_id": session_id[:8],
                    "url": url,
                    "cookie_jar_is_none": cookie_jar is None,
                    "cookie_jar_len": len(cookie_jar) if cookie_jar else 0,
                    "cookie_names": [c.name for c in cookie_jar] if cookie_jar else [],
                },
            )
            if cookie_jar and len(cookie_jar) > 0:
                session.cookies = cookie_jar
                logger.info(
                    "proxy_page_request_cookies",
                    extra={
                        "event": "ui.proxy.page.req.cookies",
                        "session_id": session_id[:8],
                        "url": url,
                        "method": method,
                        "cookies_sent": {c.name: c.value[:20] + "..." if len(c.value) > 20 else c.value for c in cookie_jar},
                    },
                )

        # 记录发送给目标服务器的完整请求头
        logger.info(
            "proxy_page_request_headers",
            extra={
                "event": "ui.proxy.page.req.headers",
                "session_id": session_id[:8] if session_id else None,
                "url": url,
                "method": method,
                "headers_sent": headers,
            },
        )

        resp = session.request(
            method, url, headers=headers, data=req_body,
            timeout=cls.REQUEST_TIMEOUT, allow_redirects=False,
        )

        # 诊断：记录是否有重定向发生
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            logger.info(
                "proxy_page_redirect_detected",
                extra={
                    "event": "ui.proxy.page.redirect",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "status_code": resp.status_code,
                    "location": location,
                },
            )

        # 记录目标服务器返回的完整响应头
        resp_headers_dict = dict(resp.headers)
        logger.info(
            "proxy_page_response_headers",
            extra={
                "event": "ui.proxy.page.resp.headers",
                "session_id": session_id[:8] if session_id else None,
                "url": url,
                "status_code": resp.status_code,
                "response_headers": resp_headers_dict,
            },
        )

        # 记录目标服务器返回的 Set-Cookie
        resp_set_cookies = []
        for k, v in resp.headers.items():
            if k.lower() == "set-cookie":
                resp_set_cookies.append(v)
        if resp_set_cookies:
            logger.info(
                "proxy_page_response_set_cookie",
                extra={
                    "event": "ui.proxy.page.resp.set_cookie",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "status_code": resp.status_code,
                    "set_cookie_headers": resp_set_cookies[:5],
                },
            )

        # 存储目标服务器返回的 Cookie（仅传响应中的新 cookie，不传整个 session jar）
        if session_id:
            _proxy_session_store.update_cookies(session_id, resp.cookies)
            updated_jar = _proxy_session_store.get_cookie_jar(session_id)
            logger.debug(
                "proxy_page_cookies_after_update",
                extra={
                    "event": "ui.proxy.page.cookies.updated",
                    "session_id": session_id[:8],
                    "url": url,
                    "cookies_in_jar": [c.name for c in updated_jar] if updated_jar else [],
                },
            )

        # 处理重定向响应：改写 Location 为代理 URL，返回给浏览器处理
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            # 改写 Location 为代理 URL
            if location:
                from urllib.parse import urlparse as _urlparse
                parsed_loc = _urlparse(location)
                if parsed_loc.scheme and parsed_loc.netloc:
                    # 绝对 URL：改写为代理 URL
                    rewritten_location = f"/ui-testing/proxy?url={location}&replay=1" if replay_mode else f"/ui-testing/proxy?url={location}"
                else:
                    # 相对 URL：拼接为基础 URL 再改写
                    from urllib.parse import urljoin
                    abs_location = urljoin(url, location)
                    rewritten_location = f"/ui-testing/proxy?url={abs_location}&replay=1" if replay_mode else f"/ui-testing/proxy?url={abs_location}"

                logger.info(
                    "proxy_page_redirect_rewrite",
                    extra={
                        "event": "ui.proxy.page.redirect.rewrite",
                        "session_id": session_id[:8] if session_id else None,
                        "original_location": location,
                        "rewritten_location": rewritten_location,
                    },
                )
            else:
                rewritten_location = "/"

            response_headers: Dict[str, Any] = {
                "Location": rewritten_location,
            }
            if session_id:
                response_headers["_set_cookies"] = _proxy_session_store.get_set_cookie_headers(session_id)
            return "", resp.status_code, response_headers

        content_type = resp.headers.get("Content-Type", "")
        is_html = "text/html" in content_type or "application/xhtml" in content_type

        response_headers = {}
        for key in ("Content-Type", "Cache-Control", "ETag"):
            if key in resp.headers:
                response_headers[key] = resp.headers[key]

        # 转发 Set-Cookie 给浏览器（返回列表，由 route handler 逐个设置）
        if session_id:
            response_headers["_set_cookies"] = _proxy_session_store.get_set_cookie_headers(session_id)

        response_headers.pop("X-Frame-Options", None)
        response_headers.pop("Content-Security-Policy", None)

        if is_html:
            body = cls.rewrite_html(resp.text, resp.url, replay_mode=replay_mode, recording_mode=recording_mode, replay_engine_js=replay_engine_js)
            response_headers["Content-Type"] = "text/html; charset=utf-8"
        else:
            body = resp.text if isinstance(resp.text, str) else resp.content.decode("utf-8", errors="replace")

        # 记录响应内容摘要（用于诊断 new_tab 返回登录页问题）
        if is_html and len(body) < 10000:
            logger.info(
                "proxy_page_response_content_preview",
                extra={
                    "event": "ui.proxy.page.resp.content_preview",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "status_code": resp.status_code,
                    "body_size": len(body),
                    "content_preview": body[:500],
                },
            )

        return body, resp.status_code, response_headers

    @classmethod
    def fetch_resource(
        cls,
        url: str,
        method: str = "GET",
        req_headers: Optional[Dict[str, str]] = None,
        req_body: Optional[bytes] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[bytes, int, Dict[str, Any]]:
        """获取子资源（CSS/JS/图片/API），不改写内容。

        Args:
            url: 目标 URL
            method: HTTP 方法（GET/POST/PUT/DELETE 等）
            req_headers: 原始请求头（转发 Content-Type 等）
            req_body: 原始请求体
            session_id: 代理会话 ID（用于 Cookie 转发）

        Returns:
            (body_bytes, status_code, headers)
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"仅支持 http/https 协议: {url}")

        _HOP_BY_HOP = frozenset({
            "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
            "te", "trailers", "transfer-encoding", "upgrade",
            "host", "content-length", "cookie",
            "x-forwarded-for", "x-forwarded-proto", "x-real-ip",
        })
        headers: Dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        }
        target_origin = f"{parsed.scheme}://{parsed.netloc}"
        headers["Referer"] = target_origin + "/"
        if req_headers:
            for key, value in req_headers.items():
                if key.lower() not in _HOP_BY_HOP:
                    headers[key] = value

        # 修正 Origin：设为目标服务器 origin（非代理 origin），模拟浏览器同源请求
        if "Origin" in headers and "/api/" in url:
            headers["Origin"] = target_origin

        # 捕获 Token 并存储到 session（用于后续页面请求）
        if session_id and req_headers:
            token_value = req_headers.get("Token", "")
            if token_value and token_value != "null":
                _proxy_session_store.set_token(session_id, token_value)

        # 记录 API 请求的完整请求头
        if "/api/" in url:
            logger.info(
                "proxy_resource_request_headers",
                extra={
                    "event": "ui.proxy.resource.req.headers",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "method": method,
                    "headers_sent": {k: v[:60] if len(v) > 60 else v for k, v in headers.items()},
                },
            )

        session = requests.Session()
        if session_id:
            cookie_jar = _proxy_session_store.get_cookie_jar(session_id)
            if cookie_jar:
                session.cookies = cookie_jar
                logger.info(
                    "proxy_resource_request_cookies",
                    extra={
                        "event": "ui.proxy.resource.req.cookies",
                        "session_id": session_id[:8],
                        "url": url,
                        "method": method,
                        "cookies_sent": {c.name: c.value[:20] + "..." if len(c.value) > 20 else c.value for c in cookie_jar},
                    },
                )

        # 记录 POST 请求体（仅 API 请求）
        if method == "POST" and req_body and "/api/" in url:
            body_preview = req_body[:500].decode("utf-8", errors="replace") if isinstance(req_body, bytes) else str(req_body)[:500]
            logger.info(
                "proxy_resource_request_body",
                extra={
                    "event": "ui.proxy.resource.req.body",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "content_type": headers.get("Content-Type", ""),
                    "body_preview": body_preview,
                },
            )

        resp = session.request(
            method, url, headers=headers, data=req_body,
            timeout=cls.REQUEST_TIMEOUT, allow_redirects=True,
        )

        # 记录目标服务器返回的 Set-Cookie
        resp_set_cookies = []
        for k, v in resp.headers.items():
            if k.lower() == "set-cookie":
                resp_set_cookies.append(v)
        if resp_set_cookies:
            logger.info(
                "proxy_resource_response_set_cookie",
                extra={
                    "event": "ui.proxy.resource.resp.set_cookie",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "status_code": resp.status_code,
                    "set_cookie_headers": resp_set_cookies[:5],
                },
            )

        # 记录 API 响应体（仅非二进制内容）
        resp_ct = resp.headers.get("Content-Type", "")
        if "/api/" in url and ("json" in resp_ct or "text" in resp_ct):
            resp_body_preview = resp.text[:500] if resp.text else ""
            logger.info(
                "proxy_resource_response_body",
                extra={
                    "event": "ui.proxy.resource.resp.body",
                    "session_id": session_id[:8] if session_id else None,
                    "url": url,
                    "status_code": resp.status_code,
                    "body_preview": resp_body_preview,
                },
            )

        # 存储目标服务器返回的 Cookie（仅传响应中的新 cookie，不传整个 session jar）
        if session_id:
            _proxy_session_store.update_cookies(session_id, resp.cookies)
            updated_jar = _proxy_session_store.get_cookie_jar(session_id)
            logger.debug(
                "proxy_resource_cookies_after_update",
                extra={
                    "event": "ui.proxy.resource.cookies.updated",
                    "session_id": session_id[:8],
                    "url": url,
                    "cookies_in_jar": [c.name for c in updated_jar] if updated_jar else [],
                },
            )

        response_headers: Dict[str, Any] = {}
        for key in ("Content-Type", "Cache-Control", "ETag"):
            if key in resp.headers:
                response_headers[key] = resp.headers[key]

        # 转发 Set-Cookie 给浏览器（返回列表，由 route handler 逐个设置）
        if session_id:
            response_headers["_set_cookies"] = _proxy_session_store.get_set_cookie_headers(session_id)

        body = resp.content
        if "javascript" in resp_ct:
            try:
                js_text = body.decode("utf-8", errors="replace")
                rewritten = UiProxyService._rewrite_js_imports(js_text, url)
                body = rewritten.encode("utf-8")
            except Exception:
                pass

        return body, resp.status_code, response_headers

    @staticmethod
    def rewrite_html(html: str, base_url: str, replay_mode: bool = False, recording_mode: bool = False, replay_engine_js: str = "") -> str:
        """改写 HTML 中的所有 URL 引用。

        处理：
        - 添加/改写 <base href>
        - 改写 href, src, action, poster, data 属性
        - 改写内联 style 中的 url()
        - 改写 <style> 标签中的 url()
        - 注入录制器脚本
        """
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        result = html

        result = UiProxyService._inject_early_script(result, origin, base_url, replay_mode=replay_mode, recording_mode=recording_mode)
        result = UiProxyService._rewrite_base_tag(result, base_url)
        result = UiProxyService._rewrite_attr_urls(result, base_url, origin)
        result = UiProxyService._rewrite_inline_style_urls(result, base_url, origin)
        result = UiProxyService._rewrite_style_tag_urls(result, base_url, origin)
        result = UiProxyService._remove_frame_busting(result)

        # 回放模式：注入回放引擎脚本（确保新页面加载后也能继续执行）
        if replay_mode and replay_engine_js:
            result = UiProxyService._inject_replay_engine_script(result, replay_engine_js)
        else:
            result = UiProxyService._inject_recorder_script(result, origin)

        return result

    @staticmethod
    def to_proxy_url(url: str) -> str:
        """将原始 URL 转为代理 URL。"""
        return f"{PROXY_PREFIX}?url={quote(url, safe='')}"

    @staticmethod
    def to_resource_proxy_url(url: str) -> str:
        """将资源 URL 转为资源代理 URL。"""
        return f"{RESOURCE_PROXY_PREFIX}?url={quote(url, safe='')}"

    @staticmethod
    def _resolve_url(href: str, base_url: str) -> Optional[str]:
        """将相对 URL 解析为绝对 URL。"""
        if not href or href.startswith(("javascript:", "data:", "blob:", "#", "mailto:", "tel:")):
            return None
        if href.startswith("//"):
            parsed_base = urlparse(base_url)
            return f"{parsed_base.scheme}:{href}"
        return urljoin(base_url, href)

    @staticmethod
    def _rewrite_base_tag(html: str, base_url: str) -> str:
        """移除或替换 <base href> 标签。"""
        html = re.sub(r'<base\s+[^>]*>', '', html, flags=re.IGNORECASE)
        return html

    @staticmethod
    def _outside_scripts(html: str, transform: Callable[[str], str]) -> str:
        """对 <script> 标签外部的 HTML 内容应用变换，保持脚本内容不变。

        分割结果: [前文本, 开标签, 脚本内容, 闭标签, 后文本, 开标签, ...]
        索引 0,1,3 需要变换（开标签含 src 等属性），索引 2（脚本内容）跳过。
        """
        pattern = re.compile(r'(<script\b[^>]*>)(.*?)(</script>)', re.IGNORECASE | re.DOTALL)
        parts = pattern.split(html)
        result = []
        for i, part in enumerate(parts):
            if i % 4 == 2:
                # 脚本内容，不处理
                result.append(part)
            else:
                result.append(transform(part))
        return "".join(result)

    @staticmethod
    def _rewrite_js_imports(js_content: str, js_url: str) -> str:
        """改写 JS 模块中的 import/export 相对路径。

        Vite 等打包工具生成的 JS 使用静态 import/export 和动态 import()
        加载子模块，代理后相对路径解析错误，需改写为代理资源 URL。
        覆盖：import from, export from, import(), new URL()。
        """
        base_dir = js_url.rsplit("/", 1)[0] + "/" if "/" in js_url else js_url

        def _rewrite_relative(m: re.Match) -> str:
            prefix = m.group(1)
            rel_path = m.group(2)
            suffix = m.group(3)
            abs_url = urljoin(base_dir, rel_path)
            proxy_url = UiProxyService.to_resource_proxy_url(abs_url)
            return f"{prefix}{proxy_url}{suffix}"

        # 静态 import/export from: import{...}from"./chunk.js" 或 export * from './chunk.js'
        result = re.sub(
            r'((?:import|export)\s*[^"\']*?from\s*["\'])(\.[^"\']+)(["\'])',
            _rewrite_relative,
            js_content,
        )
        # 动态 import(): import("./chunk.js")
        result = re.sub(
            r'(import\(\s*["\'])(\.[^"\']+)(["\'])',
            _rewrite_relative,
            result,
        )
        # new URL(): new URL("./chunk.js", import.meta.url)
        result = re.sub(
            r'(new\s+URL\(\s*["\'])(\.[^"\']+)(["\']\s*,\s*import\.meta\.url)',
            _rewrite_relative,
            result,
        )
        return result

    @staticmethod
    def _rewrite_attr_urls(html: str, base_url: str, origin: str) -> str:
        """改写 HTML 属性中的 URL 引用。"""
        attr_patterns = [
            (r'(<(?:a|area)\s[^>]*?)href\s*=\s*"([^"]*)"', "href", True),
            (r"(<(?:a|area)\s[^>]*?)href\s*=\s*'([^']*)'", "href", True),
            (r'(<(?:img|script|video|audio|source|embed|iframe|track)\s[^>]*?)src\s*=\s*"([^"]*)"', "src", False),
            (r"(<(?:img|script|video|audio|source|embed|iframe|track)\s[^>]*?)src\s*=\s*'([^']*)'", "src", False),
            (r'(<link\s[^>]*?)href\s*=\s*"([^"]*)"', "href", False),
            (r"(<link\s[^>]*?)href\s*=\s*'([^']*)'", "href", False),
            (r'(<form\s[^>]*?)action\s*=\s*"([^"]*)"', "action", True),
            (r"(<form\s[^>]*?)action\s*=\s*'([^']*)'", "action", True),
            (r'(<(?:object|video)\s[^>]*?)data\s*=\s*"([^"]*)"', "data", False),
            (r'(<(?:video|img)\s[^>]*?)poster\s*=\s*"([^"]*)"', "poster", False),
        ]

        def _replace_attr(match: re.Match, attr_name: str, is_page: bool) -> str:
            prefix = match.group(1)
            url_value = match.group(2)
            resolved = UiProxyService._resolve_url(url_value, base_url)
            if resolved is None:
                return match.group(0)
            if is_page:
                proxy_url = UiProxyService.to_proxy_url(resolved)
            else:
                proxy_url = UiProxyService.to_resource_proxy_url(resolved)
            return f'{prefix}{attr_name}="{proxy_url}"'

        def _make_replacer(attr_name: str, is_page: bool) -> Callable[[re.Match], str]:
            def _replacer(match: re.Match) -> str:
                return _replace_attr(match, attr_name, is_page)
            return _replacer

        def _rewrite_outside(outside: str) -> str:
            for pattern, attr_name, is_page_url in attr_patterns:
                outside = re.sub(
                    pattern,
                    _make_replacer(attr_name, is_page_url),
                    outside,
                    flags=re.IGNORECASE,
                )
            return outside

        return UiProxyService._outside_scripts(html, _rewrite_outside)

    @staticmethod
    def _rewrite_inline_style_urls(html: str, base_url: str, origin: str) -> str:
        """改写内联 style 属性中的 url()。"""
        def _replace_style_attr(match: re.Match) -> str:
            prefix = match.group(1)
            style_content = match.group(2)
            rewritten = UiProxyService._rewrite_css_urls(style_content, base_url, origin)
            return f'{prefix}"{rewritten}"'

        def _rewrite_outside(outside: str) -> str:
            return re.sub(
                r'(style\s*=\s*)"((?:[^"\\]|\\.)*)"',
                _replace_style_attr,
                outside,
                flags=re.IGNORECASE,
            )

        return UiProxyService._outside_scripts(html, _rewrite_outside)

    @staticmethod
    def _rewrite_style_tag_urls(html: str, base_url: str, origin: str) -> str:
        """改写 <style> 标签中的 url()。"""
        def _replace_style_tag(match: re.Match) -> str:
            open_tag = match.group(1)
            css_content = match.group(2)
            close_tag = match.group(3)
            rewritten = UiProxyService._rewrite_css_urls(css_content, base_url, origin)
            return f"{open_tag}{rewritten}{close_tag}"

        def _rewrite_outside(outside: str) -> str:
            return re.sub(
                r'(<style[^>]*>)(.*?)(</style>)',
                _replace_style_tag,
                outside,
                flags=re.IGNORECASE | re.DOTALL,
            )

        return UiProxyService._outside_scripts(html, _rewrite_outside)

    @staticmethod
    def _rewrite_css_urls(css: str, base_url: str, origin: str) -> str:
        """改写 CSS 中的 url() 引用。"""
        def _replace_css_url(match: re.Match) -> str:
            url_value = match.group(1) or match.group(2)
            if url_value.startswith(("data:", "blob:", "#")):
                return match.group(0)
            resolved = UiProxyService._resolve_url(url_value, base_url)
            if resolved is None:
                return match.group(0)
            proxy_url = UiProxyService.to_resource_proxy_url(resolved)
            return f"url('{proxy_url}')"

        css = re.sub(
            r"""url\(\s*(?:'([^']*)'|"([^"]*)")\s*\)""",
            _replace_css_url,
            css,
        )
        css = re.sub(
            r"""url\(\s*([^'")\s]+)\s*\)""",
            _replace_css_url,
            css,
        )
        return css

    @staticmethod
    def _remove_frame_busting(html: str) -> str:
        """移除常见的 frame-busting 脚本。"""
        patterns = [
            r'if\s*\(\s*top\s*!==?\s*self\s*\)\s*top\.location\s*=\s*self\.location',
            r'if\s*\(\s*window\.top\s*!==?\s*window\s*\)\s*.*?;',
            r'if\s*\(\s*self\s*!=\s*top\s*\)\s*.*?;',
        ]
        for pattern in patterns:
            html = re.sub(pattern, '/* frame-busting removed */', html, flags=re.IGNORECASE)
        return html

    @staticmethod
    def _inject_early_script(html: str, origin: str, target_url: str, replay_mode: bool = False, recording_mode: bool = False) -> str:
        """在 <head> 后立即注入早期脚本，拦截动态脚本/资源创建。

        拦截机制（8 层防护）：
        1. document.write / writeln — 替换字符串中的目标 URL
        2. document.createElement — 拦截所有元素的 src/href/data/poster 属性
        3. Element.innerHTML setter — 重写 HTML 字符串中的属性 URL
        4. Element.insertAdjacentHTML — 同上
        5. DOMParser.parseFromString — 同上
        6. HTMLImageElement.prototype.src — 拦截图片 src
        7. CSS style 属性 — 拦截 background-image 等 CSS url()
        8. fetch/XHR — 拦截网络请求
        """
        # _rwHtml: 重写 HTML 字符串中 src/href/data/poster 属性的 URL
        rw_html = (
            'function _rwHtml(s){'
            'if(typeof s!=="string")return s;'
            'return s.replace(/([ \\t\\n\\r])(src|href|data|poster)([ \\t\\n\\r]*=[ \\t\\n\\r]*)(["\\x27])([^"\\x27]*?)(\\4)/gi,'
            'function(m,pre,attr,eq,q,val,qe){'
            'if(val.indexOf(_F)===0)return pre+attr+eq+q+_T+val.substring(_F.length)+qe;'
            'return m;});}'
        )

        # _toProxy: 将任意 URL 转为代理 URL（处理绝对路径、根路径、相对路径、代理域名路径）
        # 注意：/api/ 路径需要区分代理自身 API（/api/ui-testing/ 等）和目标服务器 API（/api/uims/ 等）
        to_proxy = (
            'function _toProxy(v){'
            'if(typeof v!=="string"||!v)return v;'
            'if(v.indexOf("data:")===0||v.indexOf("blob:")===0||v.indexOf("javascript:")===0)return v;'
            'if(v.indexOf(_PROXY_PATH)===0||v.indexOf("/ui-testing/")===0)return v;'
            'if(v.indexOf("/api/ui-testing/")===0||v.indexOf("/api/ui-recorder/")===0||v.indexOf("/api/postman/")===0||v.indexOf("/api/report/")===0)return v;'
            'if(v.indexOf("proxy-resource")>=0)return v;'
            'if(v.indexOf(_T)===0)return"/ui-testing/proxy-resource?url="+encodeURIComponent(v);'
            'if(v.indexOf("/")===0)return"/ui-testing/proxy-resource?url="+encodeURIComponent(_T+v);'
            'if(v.indexOf(_F)===0&&!_isProxyUrl(v))return"/ui-testing/proxy-resource?url="+encodeURIComponent(_T+v.substring(_F.length));'
            'return"/ui-testing/proxy-resource?url="+encodeURIComponent(_T+"/"+v);'
            '}'
        )

        storage_clear = ''
        if replay_mode or recording_mode:
            # 回放模式：仅登录页清空 storage 和 cookie（确保初始状态干净），其他页面保留（Token 等认证信息）
            # 录制模式：所有页面都清空
            is_login_check = 'true' if recording_mode else '(_targetLoc.pathname.indexOf("/login")>=0)'
            storage_clear = (
                'try{'
                'if(' + is_login_check + '){'
                'var _lsKeys=Object.keys(localStorage);'
                'var _ssKeys=Object.keys(sessionStorage);'
                'if(window.parent&&window.parent.postMessage){'
                'window.parent.postMessage({type:"_proxy_nav",data:{event:"storage_before_clear",lsKeys:_lsKeys,ssKeys:_ssKeys}},"*");'
                '}'
                'localStorage.clear();sessionStorage.clear();'
                'document.cookie.split(";").forEach(function(c){document.cookie=c.replace(/^ +/,"").replace(/=.*/,"=;expires="+new Date().toUTCString()+";path=/;");});'
                'if(window.parent&&window.parent.postMessage){'
                'window.parent.postMessage({type:"_proxy_nav",data:{event:"storage_after_clear",lsKeys:Object.keys(localStorage),ssKeys:Object.keys(sessionStorage),cookies_cleared:true}},"*");'
                '}'
                '}'
                '}catch(e){'
                'if(window.parent&&window.parent.postMessage){'
                'window.parent.postMessage({type:"_proxy_nav",data:{event:"storage_clear_error",error:String(e)}},"*");'
                '}'
                '}'
            )

        early_js = (
            '(function(){'
            + storage_clear +
            'var _T="' + origin + '";'
            'var _TURL="' + target_url + '";'
            'var _F=location.protocol+"//"+location.host;'
            'var _PROXY_PATH="/ui-testing/";'
            'if(!_T||_T===_F)return;'
            'var _targetLoc=document.createElement("a");_targetLoc.href=_TURL;'
            'try{'
            'var _locProto=Location&&Location.prototype;'
            'if(_locProto){'
            'var _locNames=["host","hostname","origin","protocol"];'
            'for(var _li=0;_li<_locNames.length;_li++){(function(p){'
            'var d=Object.getOwnPropertyDescriptor(_locProto,p);'
            'if(d&&d.get){var g=d.get;'
            'Object.defineProperty(_locProto,p,{get:function(){return _targetLoc[p];},set:d.set,configurable:true});}'
            '})(_locNames[_li]);}'
            '}'
            'var _locPD=Object.getOwnPropertyDescriptor(window.location,"pathname");'
            'if(_locPD&&_locPD.configurable){Object.defineProperty(window.location,"pathname",{get:function(){return _targetLoc.pathname;},set:function(v){_targetLoc.pathname=v;},configurable:true});}'
            'else{try{Object.defineProperty(window.location,"pathname",{get:function(){return _targetLoc.pathname;},set:function(v){_targetLoc.pathname=v;},configurable:true});}catch(e){}}'
            'var _locSD=Object.getOwnPropertyDescriptor(window.location,"search");'
            'if(_locSD&&_locSD.configurable){Object.defineProperty(window.location,"search",{get:function(){return _targetLoc.search;},set:function(v){_targetLoc.search=v;},configurable:true});}'
            'var _locHD=Object.getOwnPropertyDescriptor(window.location,"hash");'
            'if(_locHD&&_locHD.configurable){Object.defineProperty(window.location,"hash",{get:function(){return _targetLoc.hash;},set:function(v){_targetLoc.hash=v;},configurable:true});}'
            'var _locWinDesc=Object.getOwnPropertyDescriptor(window,"location");'
            'var _locOverridden=false;var _locOverrideError="";var _winLocCfg=!!_locWinDesc&&!!_locWinDesc.configurable;'
            'if(!(_locPD&&_locPD.configurable)){try{Object.defineProperty(window,"location",{get:function(){return{pathname:_targetLoc.pathname,search:_targetLoc.search,hash:_targetLoc.hash,host:_targetLoc.host,hostname:_targetLoc.hostname,protocol:_targetLoc.protocol,port:_targetLoc.port,origin:_targetLoc.origin,href:_targetLoc.href,assign:function(u){location.href=u;},replace:function(u){location.replace(u);},reload:function(){location.reload();}};},configurable:true});_locOverridden=true;}catch(e){_locOverrideError=String(e);}}'
            'if(!_locOverridden){try{window.__defineGetter__("location",function(){return{pathname:_targetLoc.pathname,search:_targetLoc.search,hash:_targetLoc.hash,host:_targetLoc.host,hostname:_targetLoc.hostname,protocol:_targetLoc.protocol,port:_targetLoc.port,origin:_targetLoc.origin,href:_targetLoc.href,assign:function(u){location.href=u;},replace:function(u){location.replace(u);},reload:function(){location.reload();}};});_locOverridden=true;}catch(e){_locOverrideError=_locOverrideError||String(e);}}'
            'window.parent.postMessage({type:"_proxy_nav",data:{event:"early_script_loaded",pathname:_targetLoc.pathname,href:_targetLoc.href,realPathname:window.location.pathname,pathnameConfigurable:!!_locPD&&!!_locPD.configurable,locOverridden:_locOverridden,locOverrideError:_locOverrideError,winLocConfigurable:_winLocCfg}},"*");'
            '}catch(e){try{window.parent.postMessage({type:"_proxy_nav",data:{event:"early_script_error",error:String(e)}},"*");}catch(e2){}}'
            'try{fetch("/api/ui-testing/replay-log",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({event:"early_script_loaded",pathname:_targetLoc.pathname,href:_targetLoc.href,realPathname:window.location.pathname,pathnameConfigurable:!!_locPD&&!!_locPD.configurable,locOverridden:_locOverridden,locOverrideError:_locOverrideError,winLocConfigurable:_winLocCfg})}).catch(function(){});}catch(e){}'
            'function _isProxyUrl(v){return typeof v==="string"&&v.indexOf(_PROXY_PATH)>=0;}'
            'function _rw(s){return typeof s==="string"?s.split(_F).join(_T):s}'
            'function _rwProxy(s){return typeof s==="string"?s.split(_T).join(_F):s}'
            'function _rewriteUrl(v){'
            'if(typeof v!=="string")return v;'
            'if(v.indexOf(_PROXY_PATH)===0||v.indexOf("/api/ui-testing/")===0||v.indexOf("/api/ui-recorder/")===0||v.indexOf("/api/postman/")===0||v.indexOf("/api/report/")===0)return v;'
            'if(v.indexOf(_F)===0)return _T+v.substring(_F.length);'
            'if(v.indexOf("/")===0)return _T+v;'
            'return v;}'
            + to_proxy +
            rw_html +
            'function _rwTargetToProxy(s){return typeof s==="string"?s.replace(new RegExp(_T.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&")+"(?=[/])","g"),"/ui-testing/proxy-resource?url="+encodeURIComponent(_T)):s;}'
            'var _dw=document.write.bind(document);document.write=function(h){return _dw(_rwTargetToProxy(_rw(h)))};'
            'var _dwl=document.writeln.bind(document);document.writeln=function(h){return _dwl(_rwTargetToProxy(_rw(h)))};'
            'var _ac=Element.prototype.appendChild;'
            'Element.prototype.appendChild=function(child){'
            'if(child&&child.tagName==="SCRIPT"&&child.src)child.src=_toProxy(child.src);'
            'if(child&&child.tagName==="LINK"&&child.href)child.href=_toProxy(child.href);'
            'return _ac.call(this,child);};'
            'var _ib=Element.prototype.insertBefore;'
            'Element.prototype.insertBefore=function(child,ref){'
            'if(child&&child.tagName==="SCRIPT"&&child.src)child.src=_toProxy(child.src);'
            'if(child&&child.tagName==="LINK"&&child.href)child.href=_toProxy(child.href);'
            'return _ib.call(this,child,ref);};'
            'var _ce=document.createElement.bind(document);'
            'document.createElement=function(t){'
            'var el=_ce(t);'
            '["src","href","data","poster"].forEach(function(p){'
            'var d=Object.getOwnPropertyDescriptor(el.constructor.prototype,p);'
            'if(d&&d.set){var o=d.set;'
            'Object.defineProperty(el,p,{set:function(v){'
            'if(typeof v==="string")v=_toProxy(v);'
            'o.call(this,v);},get:d.get});}});'
            'return el;};'
            'var _ihp=Object.getOwnPropertyDescriptor(Element.prototype,"innerHTML");'
            'if(_ihp&&_ihp.set){var _ihs=_ihp.set;'
            'Object.defineProperty(Element.prototype,"innerHTML",{set:function(h){_ihs.call(this,_rwHtml(h));},get:_ihp.get});}'
            'var _iah=Element.prototype.insertAdjacentHTML;'
            'Element.prototype.insertAdjacentHTML=function(p,h){return _iah.call(this,p,_rwHtml(h))};'
            'var _pd=DOMParser.prototype.parseFromString;'
            'DOMParser.prototype.parseFromString=function(s,t){return _pd.call(this,_rwHtml(s),t)};'
            'if(typeof HTMLImageElement!=="undefined"){'
            'var _imgDesc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,"src");'
            'if(_imgDesc&&_imgDesc.set){var _imgSet=_imgDesc.set;'
            'Object.defineProperty(HTMLImageElement.prototype,"src",{set:function(v){'
            'if(typeof v==="string")v=_toProxy(v);'
            '_imgSet.call(this,v);},get:_imgDesc.get});}}'
            'if(typeof HTMLElement!=="undefined"){'
            'var _sa=Element.prototype.setAttribute;'
            'Element.prototype.setAttribute=function(n,v){'
            'if(n==="src"&&typeof v==="string"&&this instanceof HTMLImageElement)v=_toProxy(v);'
            'return _sa.call(this,n,v);};}'
            'var _saSet=Object.getOwnPropertyDescriptor(Element.prototype,"setAttribute");'
            'if(_saSet&&_saSet.value){var _saOrig=_saSet.value;'
            'Element.prototype.setAttribute=function(n,v){'
            'if(n==="src"&&typeof v==="string")v=_toProxy(v);'
            'return _saOrig.call(this,n,v);};}'
            'var _origFetch=window.fetch;'
            'var _proxyFetch=function(url,opts){'
            'var _url=typeof url==="string"?url:(url&&url.href?String(url.href):String(url));'
            'var _origUrl=_url;'
            'if(_url.indexOf("data:")===0||_url.indexOf("blob:")===0||_url.indexOf("javascript:")===0)return _origFetch.call(this,url,opts);'
            'if(_url.indexOf("/ui-testing/")===0)return _origFetch.call(this,url,opts);'
            'if(_url.indexOf("/api/ui-testing/")===0||_url.indexOf("/api/ui-recorder/")===0||_url.indexOf("/api/postman/")===0||_url.indexOf("/api/report/")===0)return _origFetch.call(this,url,opts);'
            'if(_url.indexOf("proxy-resource")>=0)return _origFetch.call(this,url,opts);'
            'if(_url.indexOf(_T)===0)_url="/ui-testing/proxy-resource?url="+encodeURIComponent(_url);'
            'else if(_url.indexOf("/")===0)_url="/ui-testing/proxy-resource?url="+encodeURIComponent(_T+_url);'
            'else if(_url.indexOf(_F)===0&&!_isProxyUrl(_url))_url="/ui-testing/proxy-resource?url="+encodeURIComponent(_T+_url.substring(_F.length));'
            'else _url="/ui-testing/proxy-resource?url="+encodeURIComponent(_T+"/"+_url);'
            'console.log("[EarlyScript] fetch:", _url.substring(0,100));'
            'opts=opts||{};opts.credentials="include";arguments[1]=opts;'
            'return _origFetch.apply(this,[_url].concat(Array.prototype.slice.call(arguments,1))).then(function(resp){'
            'if(!resp.ok)console.warn("[EarlyScript] fetch failed:", _origUrl.substring(0,80), "->", resp.status, resp.statusText);'
            'return resp;}).catch(function(err){console.error("[EarlyScript] fetch error:", _origUrl.substring(0,80), err.message);throw err;});};'
            'try{Object.defineProperty(window,"fetch",{value:_proxyFetch,writable:false,configurable:false});}catch(e){window.fetch=_proxyFetch;}'
            'var _xhrOpen=XMLHttpRequest.prototype.open;'
            'var _proxyXhrOpen=function(m,url){'
            'var _url=typeof url==="string"?url:(url&&url.href?String(url.href):String(url));'
            'var _origUrl=_url;'
            'if(_url.indexOf("data:")===0||_url.indexOf("blob:")===0||_url.indexOf("javascript:")===0)return _xhrOpen.apply(this,arguments);'
            'if(_url.indexOf("/ui-testing/")===0)return _xhrOpen.apply(this,arguments);'
            'if(_url.indexOf("/api/ui-testing/")===0||_url.indexOf("/api/ui-recorder/")===0||_url.indexOf("/api/postman/")===0||_url.indexOf("/api/report/")===0)return _xhrOpen.apply(this,arguments);'
            'if(_url.indexOf(_T)===0)_url="/ui-testing/proxy-resource?url="+encodeURIComponent(_url);'
            'else if(_url.indexOf("/")===0)_url="/ui-testing/proxy-resource?url="+encodeURIComponent(_T+_url);'
            'else if(_url.indexOf(_F)===0&&!_isProxyUrl(_url))_url="/ui-testing/proxy-resource?url="+encodeURIComponent(_T+_url.substring(_F.length));'
            'else _url="/ui-testing/proxy-resource?url="+encodeURIComponent(_T+"/"+_url);'
            'console.log("[EarlyScript] XHR:", m, _url.substring(0,100));'
            'arguments[1]=_url;'
            'var xhr=this;'
            'xhr.addEventListener("load",function(){'
            'if(xhr.status>=400)console.warn("[EarlyScript] XHR failed:", m, _origUrl.substring(0,80), "->", xhr.status, xhr.statusText);});'
            'xhr.addEventListener("error",function(){'
            'console.error("[EarlyScript] XHR error:", m, _origUrl.substring(0,80));});'
            'return _xhrOpen.apply(this,arguments);};'
            'try{Object.defineProperty(XMLHttpRequest.prototype,"open",{value:_proxyXhrOpen,writable:false,configurable:false});}catch(e){XMLHttpRequest.prototype.open=_proxyXhrOpen;}'
            'window.addEventListener("error",function(e){'
            'console.error("[EarlyScript] Uncaught error:", e.message, "at", e.filename, ":", e.lineno);});'
            'window.addEventListener("unhandledrejection",function(e){'
            'console.error("[EarlyScript] Unhandled promise rejection:", e.reason);});'
            'function _toPageProxy(v){'
            'if(typeof v!=="string"||!v)return v;'
            'if(v.indexOf("data:")===0||v.indexOf("blob:")===0||v.indexOf("javascript:")===0)return v;'
            'if(v.indexOf(_PROXY_PATH)===0||v.indexOf("/ui-testing/")===0)return v;'
            'if(v.indexOf("/api/ui-testing/")===0||v.indexOf("/api/ui-recorder/")===0||v.indexOf("/api/postman/")===0||v.indexOf("/api/report/")===0)return v;'
            'if(v.indexOf("proxy-resource")>=0)return v;'
            'var _fullUrl=v.indexOf(_T)===0?v:(v.indexOf("/")===0?_T+v:(v.indexOf(_F)===0?_T+v.substring(_F.length):_T+"/"+v));'
            'var _pathUrl=v.indexOf("/")===0?v:(v.indexOf(_F)===0?v.substring(_F.length):"/"+v);'
            'var _sep=_pathUrl.indexOf("?")>=0?"&":"?";'
            'return _pathUrl+_sep+"_proxy_url="+encodeURIComponent(_fullUrl);'
            '}'
            'if(window.history&&window.history.pushState){'
            'var _origPush=window.history.pushState.bind(window.history);'
            'window.history.pushState=function(state,title,url){'
            'if(typeof url==="string"){try{window.parent.postMessage({type:"_proxy_nav",data:{method:"pushState",href:url,loc:location.href}},"*");}catch(e){}'
            'if(url.indexOf(_PROXY_PATH)===0||url.indexOf("/api/ui-testing/")===0||url.indexOf("/api/ui-recorder/")===0||url.indexOf("/api/postman/")===0||url.indexOf("/api/report/")===0){return _origPush(state,title,url);}'
            'try{var _r=new URL(url,url.indexOf("/")===0?_T:_targetLoc.href);_targetLoc.href=_r.href;var _path=_r.pathname+(_r.search?_r.search:"")+(_r.hash?_r.hash:"");var _sep=(_r.search||_r.hash)?"&":"?";url=_path+_sep+"_proxy_url="+encodeURIComponent(_r.href);}catch(e){}}'
            'return _origPush(state,title,url);};}'
            'if(window.history&&window.history.replaceState){'
            'var _origReplace=window.history.replaceState.bind(window.history);'
            'window.history.replaceState=function(state,title,url){'
            'if(typeof url==="string"){try{window.parent.postMessage({type:"_proxy_nav",data:{method:"replaceState",href:url,loc:location.href}},"*");}catch(e){}'
            'if(url.indexOf(_PROXY_PATH)===0||url.indexOf("/api/ui-testing/")===0||url.indexOf("/api/ui-recorder/")===0||url.indexOf("/api/postman/")===0||url.indexOf("/api/report/")===0){return _origReplace(state,title,url);}'
            'try{var _r=new URL(url,url.indexOf("/")===0?_T:_targetLoc.href);_targetLoc.href=_r.href;var _path=_r.pathname+(_r.search?_r.search:"")+(_r.hash?_r.hash:"");var _sep=(_r.search||_r.hash)?"&":"?";url=_path+_sep+"_proxy_url="+encodeURIComponent(_r.href);}catch(e){}}'
            'return _origReplace(state,title,url);};}'
            'var _origOpen=window.open;'
            'if(_origOpen){'
            + (
                'window.open=function(url,name,features){'
                'console.log("[ProxyEarly] window.open blocked in replay mode, url:",url);'
                'return{closed:false,close:function(){},focus:function(){},postMessage:function(){}};'
                '};'
            if replay_mode else (
                'window.open=function(url,name,features){'
                'if(typeof url==="string"){url=_toPageProxy(url);}'
                'return _origOpen.call(this,url,name,features);};'
            ))
            + '}'
            'try{if(typeof window.__PROXY_SETUP__==="undefined"){window.__PROXY_SETUP__=true;var _tPath=_targetLoc.pathname+(_targetLoc.search||"")+(_targetLoc.hash||"");window.history.replaceState(null,"",_tPath);try{window.dispatchEvent(new PopStateEvent("popstate",{}));}catch(e){var _pe=document.createEvent("HTMLEvents");_pe.initEvent("popstate",true,true);window.dispatchEvent(_pe);}}}catch(e){}'
            + (
                'function _convertBlank(){'
                'var links=document.querySelectorAll("a[target=\\"_blank\\"]");'
                'for(var i=0;i<links.length;i++)links[i].setAttribute("target","_self");'
                '}'
                'document.addEventListener("click",function(e){'
                'var link=e.target.closest("a");'
                'if(!link||!link.href||link.href.indexOf("javascript:")===0)return;'
                'if(link.getAttribute("target")==="_blank"){'
                'link.setAttribute("target","_self");'
                'try{'
                'var _u=new URL(link.href,location.href);'
                'var _fullUrl=_u.href;'
                'var _pathUrl=_u.pathname+(_u.search?_u.search:"")+(_u.hash?_u.hash:"");'
                'var _sep=_pathUrl.indexOf("?")>=0?"&":"?";'
                'link.href=_pathUrl+_sep+"_proxy_url="+encodeURIComponent(_fullUrl);'
                '}catch(ex){}'
                '}'
                '},true);'
                'if(document.readyState==="loading"){'
                'document.addEventListener("DOMContentLoaded",function(){_convertBlank()});'
                '}else{_convertBlank();}'
                'if(window.MutationObserver){'
                'var _mo=new MutationObserver(function(mutations){'
                'for(var i=0;i<mutations.length;i++){'
                'for(var j=0;j<mutations[i].addedNodes.length;j++){'
                'var node=mutations[i].addedNodes[j];'
                'if(node.nodeType===1){'
                'if(node.tagName==="A"&&node.getAttribute("target")==="_blank")node.setAttribute("target","_self");'
                'var descs=node.querySelectorAll("a[target=\\"_blank\\"]");'
                'for(var k=0;k<descs.length;k++)descs[k].setAttribute("target","_self");'
                '}}}});'
                '_mo.observe(document.documentElement,{childList:true,subtree:true});'
                '}'
                'console.log("[ProxyEarly] new_tab prevention installed (click intercept + href proxy conversion)");'
            if replay_mode else '')
            + '})();'
        )
        early_script = f"<script>{early_js}</script>"

        # 诊断：确认早期脚本已注入
        logger.info(f"early_script_injected: len={len(early_js)}, target_url={target_url}, replay_mode={replay_mode}")

        lower = html.lower()
        if "<head>" in lower:
            idx = lower.index("<head>") + len("<head>")
            html = html[:idx] + early_script + html[idx:]
        elif "<html>" in lower:
            idx = lower.index("<html>") + len("<html>")
            html = html[:idx] + early_script + html[idx:]
        else:
            html = early_script + html

        return html

    @staticmethod
    def _inject_recorder_script(html: str, origin: str = "") -> str:
        """在 <head> 注入早期事件捕获脚本，在 </body> 前注入主录制器脚本。"""
        from postman_api_tester.services.ui_recorder_inject import get_recorder_js, get_early_recorder_js

        # 早期脚本：在 <head> 中注入，在 Vue.js 之前捕获事件
        early_js = get_early_recorder_js()
        early_script_tag = f"<script>\n{early_js}\n</script>"

        lower = html.lower()
        if "<head>" in lower:
            idx = lower.index("<head>") + len("<head>")
            html = html[:idx] + early_script_tag + html[idx:]
            lower = html.lower()  # 重新计算索引
        elif "<html>" in lower:
            idx = lower.index("<html>") + len("<html>")
            html = html[:idx] + early_script_tag + html[idx:]
            lower = html.lower()

        # 主脚本：在 </body> 前注入
        recorder_js = get_recorder_js(origin)
        logger.info(f"recorder_script_injected: len={len(recorder_js)}, origin={origin}")
        script_tag = f"<script>\n{recorder_js}\n</script>"

        if "</body>" in lower:
            idx = lower.index("</body>")
            html = html[:idx] + script_tag + html[idx:]
        elif "</html>" in lower:
            idx = lower.index("</html>")
            html = html[:idx] + script_tag + html[idx:]
        else:
            html += script_tag

        return html
    @staticmethod
    def _inject_replay_engine_script(html: str, replay_engine_js: str) -> str:
        """在 </body> 前注入回放引擎脚本。"""
        script_tag = f"<script>\n{replay_engine_js}\n</script>"

        lower = html.lower()
        if "</body>" in lower:
            idx = lower.index("</body>")
            html = html[:idx] + script_tag + html[idx:]
        elif "</html>" in lower:
            idx = lower.index("</html>")
            html = html[:idx] + script_tag + html[idx:]
        else:
            html += script_tag

        return html
