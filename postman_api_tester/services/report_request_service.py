"""开发导读：
- 职责：统一解析路由请求体来源（JSON 与 multipart）并做 URL/base_url 安全校验。
- 入口：resolve_request_payload_source()、validate_base_url_scheme() 等。
- 目标：收敛输入差异，降低路由层参数解析复杂度。
"""

import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


def resolve_request_payload_source(
    *,
    content_type: Optional[str],
    json_payload: Optional[Dict[str, Any]],
    request_meta_raw: Optional[str],
) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """Parse request payload/meta for JSON and multipart forms with unified fallback behavior."""
    is_multipart = bool(content_type and content_type.startswith("multipart/form-data"))
    payload: Dict[str, Any] = dict(json_payload or {})
    if not is_multipart:
        return False, payload, payload

    try:
        req_meta = json.loads(str(request_meta_raw or "{}"))
    except (json.JSONDecodeError, ValueError):
        req_meta = {}

    source = req_meta if isinstance(req_meta, dict) else {}
    return True, payload, source


def is_valid_http_url(url: Optional[str]) -> bool:
    """校验给定字符串是否为合法的 http/https URL。"""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_int_default(value: Any, default: int) -> int:
    """尝试将 value 转换为 int，失败则返回默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_optional_int(value: Any) -> Optional[int]:
    """尝试将 value 转换为 int；None 或转换失败时返回 None。"""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def inject_token_header(headers: Dict[str, Any], token: str) -> Dict[str, Any]:
    """在请求头中注入 token，优先覆盖已有的 Authorization 头。"""
    if not token:
        return headers

    out_headers = dict(headers)
    auth_key: Optional[str] = None
    for existing_key in list(out_headers.keys()):
        lower_key = str(existing_key).lower()
        if lower_key == "authorization":
            auth_key = existing_key
        if lower_key == "token":
            out_headers.pop(existing_key)

    if auth_key:
        out_headers[auth_key] = f"Bearer {token}"
    else:
        out_headers["token"] = token
    return out_headers


def extract_http_request_fields(source: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """从源数据与载荷中提取 HTTP 请求相关字段并统一格式。"""
    return {
        "url": str(source.get("url", "")).strip(),
        "method": str(source.get("method", "GET")).upper(),
        "headers": dict(source.get("headers") or {}),
        "params": dict(source.get("params") or {}),
        "body_mode": str(source.get("body_mode") or "legacy").strip().lower(),
        "body_data": source.get("body_data"),
        "legacy_body": payload.get("body"),
    }
