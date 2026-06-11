"""测试 token、重新请求与代理请求路由处理函数。"""

from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error
from postman_api_tester.handlers.http_handler import execute_http_request as _http_execute_http_request
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_repository import (
    find_report as _repo_find_report,
    invalidate_reports_cache as _repo_invalidate_reports_cache,
)
from postman_api_tester.services.report_patch_service import (
    patch_report_result as _patch_report_result,
)
from postman_api_tester.services.report_request_service import (
    extract_http_request_fields as _svc_extract_http_request_fields,
    inject_token_header as _svc_inject_token_header,
    is_valid_http_url as _svc_is_valid_http_url,
    parse_int_default as _svc_parse_int_default,
    parse_optional_int as _svc_parse_optional_int,
    resolve_request_payload_source as _svc_resolve_request_payload_source,
)
from postman_api_tester.services.report_results_service import (
    build_proxy_response_payload,
    build_re_request_error_payload,
    build_re_request_success_payload,
    build_test_token_payload,
)
from postman_api_tester.services.report_lock_service import get_report_write_lock
from postman_api_tester.utils.report_utils import compute_summary as _utils_compute_summary
from postman_api_tester.utils.response_parser import extract_msg_errcode as _utils_extract_msg_errcode
from postman_api_tester.utils.url_utils import (
    merge_url_with_params as _merge_url_with_params,
    normalize_url_and_params as _normalize_url_and_params,
)

REPORTS_DIR = ReportServerApp._resolve_reports_dir()


def _check_proxy_host_allowed(url: str) -> ResponseReturnValue | None:
    """若配置了 PROXY_ALLOWED_HOSTS，校验 url 的域名是否在白名单内。返回 None 表示通过。"""
    try:
        from postman_api_tester.config import PROXY_ALLOWED_HOSTS
    except ImportError:
        return None
    if not PROXY_ALLOWED_HOSTS:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host and host not in PROXY_ALLOWED_HOSTS:
        return _json_error(f"proxy 域名不在白名单内: {host}", 403)
    return None


def test_token() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", "")).strip()
    if not token:
        return jsonify(build_test_token_payload(success=False, message="token 不能为空")), 400
    return jsonify(build_test_token_payload(success=True, message="token 格式有效，可用于后续请求"))


def re_request_api() -> ResponseReturnValue:
    is_multipart, payload, source = _svc_resolve_request_payload_source(
        content_type=request.content_type,
        json_payload=request.get_json(silent=True),
        request_meta_raw=request.form.get("request_meta"),
    )
    request_fields = _svc_extract_http_request_fields(source, payload)
    url = request_fields["url"]
    method = request_fields["method"]
    headers = request_fields["headers"]
    params = request_fields["params"]
    body_mode = request_fields["body_mode"]
    body_data = request_fields["body_data"]
    legacy_body = request_fields["legacy_body"]
    token = str(source.get("token", "")).strip()
    save_to_report = bool(source.get("save_to_report", False))
    rpt_name = str(source.get("report_name", "")).strip()
    rpt_index = _svc_parse_optional_int(source.get("result_index"))
    expected_status = _svc_parse_int_default(source.get("expected_status") or 200, 200)

    if not url:
        return _json_error("url 不能为空", 400)
    if not _svc_is_valid_http_url(url):
        return _json_error("url 仅允许合法的 http/https 地址", 400)
    host_check = _check_proxy_host_allowed(url)
    if host_check is not None:
        return host_check

    headers = _svc_inject_token_header(headers, token)

    exec_result = _http_execute_http_request(
        url=url,
        method=method,
        headers=headers,
        params=params,
        body_mode=body_mode,
        body_data=body_data,
        legacy_body=legacy_body,
        is_multipart=is_multipart,
        files_source=request.files,
    )

    if not exec_result["success"]:
        normalized_url, normalized_params = _normalize_url_and_params(url, params)
        return jsonify(
            build_re_request_error_payload(
                source=source,
                url=url,
                method=method,
                normalized_url=normalized_url,
                actual_request_url=_merge_url_with_params(normalized_url, normalized_params),
                message=exec_result["error_message"],
                headers_to_send={},
                normalized_params=normalized_params,
                stored_body=None,
                stored_body_mode="legacy",
                stored_body_data=None,
            )
        )

    response_body = exec_result["response_body"]
    response_message, err_code = _utils_extract_msg_errcode(response_body)
    status_code_ok = exec_result["status_code"] == expected_status
    normalized_msg = str(response_message or "").strip().lower()
    message_ok = normalized_msg == "" or normalized_msg == "success"

    if status_code_ok and message_ok:
        result_status = "PASSED"
        result_message = response_message
    else:
        result_status = "FAILED"
        if not status_code_ok:
            result_message = f"状态码不匹配: 期望 {expected_status}, 实际 {exec_result['status_code']}; message: {response_message}"
        else:
            result_message = f"message 校验未通过(期望为空或 success), 实际为: {response_message}"

    new_request_info = {
        "headers": exec_result["headers_to_send"],
        "params": exec_result["normalized_params"],
        "body": exec_result["stored_body"],
        "body_mode": exec_result["stored_body_mode"],
        "body_data": exec_result["stored_body_data"],
    }
    new_response_info = {"headers": exec_result["response_headers"], "body": response_body}

    result_fields = {
        "method": method,
        "url": exec_result["normalized_url"],
        "actual_request_url": exec_result["actual_request_url"],
        "item_path": source.get("item_path", []),
        "expected_status": expected_status,
        "status": result_status,
        "status_code": exec_result["status_code"],
        "message": result_message,
        "err_code": err_code,
    }

    new_summary: Dict[str, Any] = {}
    if save_to_report and rpt_name and rpt_index is not None:
        new_summary = _patch_report_result(
            rpt_name,
            rpt_index,
            result_fields,
            new_request_info,
            new_response_info,
            reports_dir=REPORTS_DIR,
            get_report_write_lock=get_report_write_lock,
            find_report=_repo_find_report,
            compute_summary=_utils_compute_summary,
            invalidate_reports_cache=_repo_invalidate_reports_cache,
        )

    return jsonify(
        build_re_request_success_payload(
            source=source,
            method=method,
            normalized_url=exec_result["normalized_url"],
            actual_request_url=exec_result["actual_request_url"],
            result_fields=result_fields,
            new_request_info=new_request_info,
            new_response_info=new_response_info,
            new_summary=new_summary,
        )
    )


def api_proxy_request() -> ResponseReturnValue:
    is_multipart, payload, source = _svc_resolve_request_payload_source(
        content_type=request.content_type,
        json_payload=request.get_json(silent=True),
        request_meta_raw=request.form.get("request_meta"),
    )
    request_fields = _svc_extract_http_request_fields(source, payload)
    url = request_fields["url"]
    method = request_fields["method"]
    req_headers = request_fields["headers"]
    req_params = request_fields["params"]
    body_mode = request_fields["body_mode"]
    body_data = request_fields["body_data"]
    legacy_body = request_fields["legacy_body"]

    if not url:
        return _json_error("url 不能为空", 400)
    host_check = _check_proxy_host_allowed(url)
    if host_check is not None:
        return host_check

    exec_result = _http_execute_http_request(
        url=url,
        method=method,
        headers=req_headers,
        params=req_params,
        body_mode=body_mode,
        body_data=body_data,
        legacy_body=legacy_body,
        is_multipart=is_multipart,
        files_source=request.files,
    )

    if not exec_result["success"]:
        return _json_error(exec_result["error_message"], exec_result.get("error_code", 502))

    return jsonify(
        build_proxy_response_payload(
            status_code=exec_result["status_code"],
            elapsed_ms=exec_result["elapsed_ms"],
            response_headers=exec_result["response_headers"],
            response_body=exec_result["response_body"],
        )
    )
