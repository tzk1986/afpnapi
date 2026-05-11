import time as _time
from typing import Any, Dict
from urllib.parse import urlparse

import requests

from postman_api_tester.runtime_utils import normalize_url_and_params
from postman_api_tester.utils.request_utils import build_request_kwargs


def execute_http_request(
    *,
    url: str,
    method: str,
    headers: Dict[str, Any],
    params: Dict[str, Any],
    body_mode: str,
    body_data: Any,
    legacy_body: Any,
    is_multipart: bool,
    files_source: Any,
) -> Dict[str, Any]:
    """Execute HTTP request for re-request/proxy routes with consistent normalization and timeout semantics."""
    try:
        normalized_url, normalized_params = normalize_url_and_params(url, params)

        parsed = urlparse(normalized_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {
                "success": False,
                "error_message": "url 仅允许合法的 http/https 地址",
                "error_code": 400,
            }

        try:
            import postman_api_tester.config as _cfg
            connect_timeout = int(getattr(_cfg, "REQUEST_CONNECT_TIMEOUT", 10))
            read_timeout = int(getattr(_cfg, "REQUEST_READ_TIMEOUT", 30))
        except Exception:
            connect_timeout, read_timeout = 10, 30

        try:
            prepared = build_request_kwargs(
                is_multipart=is_multipart,
                body_mode=body_mode,
                body_data=body_data,
                legacy_body=legacy_body,
                headers=headers,
                files_source=files_source,
            )
        except ValueError as exc:
            return {
                "success": False,
                "error_message": str(exc),
                "error_code": 400,
            }

        request_kwargs = prepared["request_kwargs"]
        headers_to_send = prepared["headers_to_send"]
        stored_body = prepared["stored_body"]
        stored_body_mode = prepared["stored_body_mode"]
        stored_body_data = prepared["stored_body_data"]

        t0 = _time.time()
        response = requests.request(
            method=method,
            url=normalized_url,
            headers=headers_to_send,
            params=normalized_params,
            **request_kwargs,
            timeout=(connect_timeout, read_timeout),
        )
        elapsed_ms = round((_time.time() - t0) * 1000)

        try:
            response_body: Any = response.json()
        except ValueError:
            response_body = response.text

        actual_request_url = str(getattr(response.request, "url", "") or "")

        return {
            "success": True,
            "status_code": response.status_code,
            "response_body": response_body,
            "response_headers": dict(response.headers),
            "elapsed_ms": elapsed_ms,
            "normalized_url": normalized_url,
            "normalized_params": normalized_params,
            "actual_request_url": actual_request_url,
            "headers_to_send": headers_to_send,
            "stored_body": stored_body,
            "stored_body_mode": stored_body_mode,
            "stored_body_data": stored_body_data,
        }
    except Exception as exc:
        return {
            "success": False,
            "error_message": str(exc),
            "error_code": 502,
        }
