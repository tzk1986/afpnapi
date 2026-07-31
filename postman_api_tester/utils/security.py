"""Security utility implementations for sensitive-header handling.

开发导读：
- 职责：敏感头识别、脱敏与导出鉴权字段裁剪。
- 入口：merge_sensitive_headers()/strip_auth_headers() 等。
- 目标：详情写入与导出链路使用同一敏感头规则。
"""

import ipaddress
from typing import Any, Dict, Iterable, Set
from urllib.parse import urlparse

DEFAULT_SENSITIVE_HEADERS = {
    "authorization",
    "token",
    "access_token",
    "auth_token",
    "x-token",
    "x-access-token",
    "access-token",
    "cookie",
    "set-cookie",
    "session",
    "x-csrf-token",
    "api-key",
    "apikey",
    "secret",
}


def _normalize_header_names(values: Iterable[Any]) -> Set[str]:
    normalized: Set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if text:
            normalized.add(text)
    return normalized


def _load_config_sensitive_headers() -> Set[str]:
    try:
        from postman_api_tester import config as _cfg
    except Exception:
        return set(DEFAULT_SENSITIVE_HEADERS)
    config_value = getattr(_cfg, "SENSITIVE_HEADERS", None)
    if config_value is None:
        return set(DEFAULT_SENSITIVE_HEADERS)
    if isinstance(config_value, str):
        configured = _normalize_header_names(config_value.split(","))
    elif isinstance(config_value, (list, tuple, set, frozenset)):
        configured = _normalize_header_names(config_value)
    else:
        configured = set()
    if not configured:
        return set(DEFAULT_SENSITIVE_HEADERS)
    return set(DEFAULT_SENSITIVE_HEADERS) | configured


SENSITIVE_HEADERS = frozenset(_load_config_sensitive_headers())


def sanitize_headers(headers: Dict[str, Any], *, mask: str = "***") -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in (headers or {}).items():
        if str(key).strip().lower() in SENSITIVE_HEADERS:
            sanitized[key] = mask
        else:
            sanitized[key] = value
    return sanitized


def strip_sensitive_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in (headers or {}).items():
        if str(key).strip().lower() in SENSITIVE_HEADERS:
            continue
        cleaned[key] = value
    return cleaned


def strip_auth_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    return strip_sensitive_headers(headers)


def is_safe_url(url: str) -> bool:
    """检查 URL 是否安全（非内网地址）。

    防止 SSRF 攻击，禁止访问私有网络地址段。

    Args:
        url: 待检查的 URL

    Returns:
        True 表示安全（公网地址），False 表示不安全（内网地址或无效）
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False

        # 禁止访问常见内网地址
        if hostname in ('127.0.0.1', 'localhost', '0.0.0.0', '[::1]'):
            return False

        # 禁止私有 IP 段
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # 非 IP 地址（域名），允许

        return True
    except Exception:
        return False


__all__ = [
    "sanitize_headers",
    "strip_sensitive_headers",
    "strip_auth_headers",
    "is_safe_url",
]
