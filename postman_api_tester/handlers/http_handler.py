"""HTTP handler real implementations for re-request/proxy flows."""

"""开发导读：
- 职责：执行重试/代理请求前的 URL 安全校验、请求参数归一化与统一响应封装。
- 入口：execute_http_request()。
- 输出：固定 success/error 结构，供前端调试、编辑重试与报告写回复用。
- 安全：仅允许 http/https，超时配置从 config 动态读取，避免硬编码。
"""

import logging
import time as _time
from typing import Any, Dict
from urllib.parse import urlparse

import requests

from postman_api_tester.runtime_utils import normalize_url_and_params
from postman_api_tester.utils.request_builder import build_request_kwargs


logger = logging.getLogger(__name__)


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
	# 统一在 handler 层完成请求前置校验与请求参数归一化，
	# 让路由层保持轻量、服务层可复用。
	logger.info(
		"http request received",
		extra={
			"event": "handler.http.execute.received",
			"method": method,
			"url": url,
			"is_multipart": bool(is_multipart),
		},
	)
	try:
		normalized_url, normalized_params = normalize_url_and_params(url, params)

		parsed = urlparse(normalized_url)
		if parsed.scheme not in ("http", "https") or not parsed.netloc:
			logger.warning(
				"http request validation failed",
				extra={
					"event": "handler.http.execute.invalid_url",
					"url": normalized_url,
				},
			)
			return {
				"success": False,
				"error_message": "url 仅允许合法的 http/https 地址",
				"error_code": 400,
			}

		from postman_api_tester.report_server_config import (
			REQUEST_CONNECT_TIMEOUT as _connect_timeout,
			REQUEST_READ_TIMEOUT as _read_timeout,
		)
		connect_timeout = _connect_timeout
		read_timeout = _read_timeout

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
			logger.warning(
				"http request build failed",
				extra={
					"event": "handler.http.execute.invalid_body",
					"method": method,
					"url": normalized_url,
					"error": str(exc),
				},
			)
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

		content_type = response.headers.get('content-type', '')
		response_body_is_binary = False
		try:
			if 'application/json' in content_type:
				response_body: Any = response.json()
			elif content_type.startswith('image/'):
				import base64 as _base64
				response_body = _base64.b64encode(response.content).decode('ascii')
				response_body_is_binary = True
			else:
				response_body = response.text
		except ValueError:
			response_body = response.text

		actual_request_url = str(getattr(response.request, "url", "") or "")
		# 返回统一结构，供重试编辑、代理调试、报告写入链路复用。
		logger.info(
			"http request completed",
			extra={
				"event": "handler.http.execute.completed",
				"method": method,
				"url": normalized_url,
				"status_code": int(response.status_code),
				"elapsed_ms": elapsed_ms,
			},
		)

		return {
			"success": True,
			"status_code": response.status_code,
			"response_body": response_body,
			"response_headers": dict(response.headers),
			"response_content_type": content_type,
			"response_body_is_binary": response_body_is_binary,
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
		logger.exception(
			"http request failed",
			extra={
				"event": "handler.http.execute.failed",
				"method": method,
				"url": url,
			},
		)
		return {
			"success": False,
			"error_message": str(exc),
			"error_code": 502,
		}


__all__ = ["execute_http_request"]

