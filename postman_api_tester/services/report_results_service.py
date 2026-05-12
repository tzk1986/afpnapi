from typing import Any, Dict, List, Optional

from postman_api_tester.models import compare_report_data, filter_report_results, paginate_items
from postman_api_tester.report_repository import load_report_details_map
from postman_api_tester.report_server_utils import (
    manual_case_exclusion_key,
    normalize_manual_case,
    normalize_manual_exclusions,
    result_exclusion_key,
)


def build_report_results_payload(
    report: Dict[str, Any],
    page: int,
    page_size: int,
    keyword: str,
    message_keyword: str,
    err_code_keyword: str,
    status_filter: Optional[str],
    include_excluded: bool,
) -> Dict[str, Any]:
    filtered_items = filter_report_results(
        report,
        keyword,
        status_filter,
        message_keyword,
        err_code_keyword,
        include_excluded=include_excluded,
    )
    paged = paginate_items(filtered_items, page, page_size)
    paged.update({
        "report_name": report.get("report_name", ""),
        "query": keyword,
        "message_query": message_keyword,
        "err_code_query": err_code_keyword,
        "status": status_filter or "all",
        "include_excluded": include_excluded,
    })
    return paged


def build_compare_payload(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    return compare_report_data(left, right)


def build_result_detail_payload(report: Dict[str, Any], result_index: int) -> Dict[str, Any]:
    results = report.get("results", [])
    if result_index < 0 or result_index >= len(results):
        raise IndexError(result_index)

    result = dict(results[result_index])
    exclusion_key = result_exclusion_key(result)
    exclusion_set = set(normalize_manual_exclusions(report.get("manual_exclusions") or []))
    details_map = load_report_details_map(report)
    detail = details_map.get(str(result_index))
    response = {
        "index": result_index,
        "name": result.get("name", ""),
        "folder": result.get("folder", ""),
        "method": result.get("method", ""),
        "url": result.get("url", ""),
        "actual_request_url": result.get("actual_request_url", ""),
        "item_path": result.get("item_path", []),
        "expected_status": result.get("expected_status", 200),
        "status": result.get("status", ""),
        "status_code": result.get("status_code"),
        "message": result.get("message", ""),
        "err_code": result.get("err_code", ""),
        "retried": result.get("retried", False),
        "retry_history": result.get("retry_history", []),
        "manual_judgement": result.get("manual_judgement", {}),
        "judgement_source": "manual" if isinstance(result.get("manual_judgement"), dict) and result.get("manual_judgement", {}).get("active") else "auto",
        "excluded": exclusion_key in exclusion_set,
        "exclusion_key": exclusion_key,
        "detail_available": bool(detail),
        "request_info": {"headers": {}, "params": {}, "body": None},
        "response_info": {"headers": {}, "body": None},
    }
    if detail:
        response["request_info"] = detail.get("request_info") or {"headers": {}, "params": {}, "body": None}
        response["response_info"] = detail.get("response_info") or {"headers": {}, "body": None}
    return response


def build_manual_cases_payload(
    report_name: str,
    report: Dict[str, Any],
    default_folder: str,
    enabled: bool,
) -> Dict[str, Any]:
    manual_cases = [
        normalize_manual_case(case, str(case.get("folder") or default_folder))
        for case in (report.get("manual_cases") or [])
        if isinstance(case, dict)
    ]
    manual_exclusions = normalize_manual_exclusions(report.get("manual_exclusions") or [])
    exclusion_set = set(manual_exclusions)
    response_cases: List[Dict[str, Any]] = []
    for case in manual_cases:
        key = manual_case_exclusion_key(case)
        response_cases.append({
            **case,
            "exclusion_key": key,
            "excluded": key in exclusion_set,
        })
    return {
        "report_name": report_name,
        "enabled": enabled,
        "default_folder": default_folder,
        "manual_cases": response_cases,
        "manual_exclusions": manual_exclusions,
    }


def build_manual_case_upsert_payload(report_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_name": report_name,
        "case": result.get("case"),
        "manual_cases": result.get("manual_cases", []),
    }


def build_manual_case_delete_payload(report_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_name": report_name,
        "manual_cases": result.get("manual_cases", []),
    }


def build_case_exclusion_payload(report_name: str, excluded: bool, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_name": report_name,
        "excluded": excluded,
        "manual_exclusions": result.get("manual_exclusions", []),
    }


def build_result_judgement_payload(
    report_name: str,
    result_index: int,
    action: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "report_name": report_name,
        "result_index": result_index,
        "action": action,
        "summary": result.get("summary", {}),
        "result": result.get("result", {}),
    }


def build_export_collection_payload(
    report_name: str,
    exported: Dict[str, Any],
    include_auth: bool,
) -> Dict[str, Any]:
    return {
        "report_name": report_name,
        "file_name": exported["file_name"],
        "download_url": f"/exports/{exported['file_name']}",
        "updated_count": exported["updated_count"],
        "skipped_count": exported["skipped_count"],
        "manual_case_count": exported.get("manual_case_count", 0),
        "manual_case_exported_count": exported.get("manual_case_exported_count", 0),
        "excluded_count": exported.get("excluded_count", 0),
        "source_total_count": exported.get("source_total_count", 0),
        "scope_effective_same_as_full": exported.get("scope_effective_same_as_full", False),
        "include_auth": include_auth,
        "export_scope": exported["export_scope"],
        "report_only_count": exported["report_only_count"],
        "warnings": exported["warnings"],
    }


def build_report_meta_payload(report: Dict[str, Any]) -> Dict[str, Any]:
    return report


def build_report_delete_payload(report_name: str, deleted_files: List[str]) -> Dict[str, Any]:
    return {
        "success": True,
        "report_name": report_name,
        "deleted_files": deleted_files,
    }


def build_retry_queued_payload(job_id: str, retry_count: int, message: str) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "queued",
        "retry_count": retry_count,
        "message": message,
    }


def build_health_payload(timestamp: str) -> Dict[str, Any]:
    return {
        "status": "ok",
        "timestamp": timestamp,
    }


def build_test_token_payload(success: bool, message: str) -> Dict[str, Any]:
    return {
        "success": success,
        "message": message,
    }


def build_environments_payload(env_list: List[Dict[str, Any]], default_env_name: str) -> Dict[str, Any]:
    return {
        "environments": env_list,
        "default": default_env_name,
    }


def build_collection_preview_payload(
    file_name: str,
    total: int,
    truncated: bool,
    max_items: int,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "file_name": file_name,
        "total": total,
        "truncated": truncated,
        "max_items": max_items,
        "items": items,
    }


def build_job_queued_payload(job_id: str, message: str) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "queued",
        "message": message,
    }


def build_re_request_success_payload(
    source: Dict[str, Any],
    method: str,
    normalized_url: str,
    actual_request_url: str,
    result_fields: Dict[str, Any],
    new_request_info: Dict[str, Any],
    new_response_info: Dict[str, Any],
    new_summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "name": source.get("name", normalized_url),
        "folder": source.get("folder", ""),
        "method": method,
        "url": normalized_url,
        "actual_request_url": actual_request_url,
        **result_fields,
        "request_info": new_request_info,
        "response_info": new_response_info,
        "new_summary": new_summary,
        "saved": bool(new_summary),
    }


def build_proxy_response_payload(
    status_code: int,
    elapsed_ms: int,
    response_headers: Dict[str, Any],
    response_body: Any,
) -> Dict[str, Any]:
    return {
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "response_headers": response_headers,
        "response_body": response_body,
    }


def build_re_request_error_payload(
    source: Dict[str, Any],
    url: str,
    method: str,
    normalized_url: str,
    actual_request_url: str,
    message: str,
    headers_to_send: Dict[str, Any],
    normalized_params: Dict[str, Any],
    stored_body: Any,
    stored_body_mode: str,
    stored_body_data: Any,
) -> Dict[str, Any]:
    return {
        "name": source.get("name", url),
        "folder": source.get("folder", ""),
        "method": method,
        "url": normalized_url,
        "actual_request_url": actual_request_url,
        "status": "ERROR",
        "status_code": None,
        "message": message,
        "err_code": "",
        "request_info": {
            "headers": headers_to_send,
            "params": normalized_params,
            "body": stored_body,
            "body_mode": stored_body_mode,
            "body_data": stored_body_data,
        },
        "response_info": {"headers": {}, "body": message},
        "new_summary": {},
        "saved": False,
    }


def build_error_payload(message: str) -> Dict[str, Any]:
    return {
        "error": message,
    }
