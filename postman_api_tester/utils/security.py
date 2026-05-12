"""Security utility implementations for sensitive-header handling."""

from typing import Any, Dict, Iterable, Set


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

__all__ = [
    "sanitize_headers",
    "strip_sensitive_headers",
    "strip_auth_headers",
]
