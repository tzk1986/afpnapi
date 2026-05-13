import re
from pathlib import Path
from typing import Dict, List, Optional, SupportsInt, cast

from postman_api_tester.utils.security import strip_sensitive_headers


JsonDict = Dict[str, object]


def _coerce_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(cast(SupportsInt | str | bytes | bytearray, value))
    except (TypeError, ValueError):
        return None


def build_exclusion_key(folder: object, name: object, method: object, url: object) -> str:
    folder_text = str(folder or "").strip()
    name_text = str(name or "").strip()
    method_text = str(method or "").strip().upper()
    url_text = str(url or "").strip()
    return "|".join([folder_text, name_text, method_text, url_text])


def normalize_exclusion_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "|" not in text:
        return text

    parts = [part.strip() for part in text.split("|")]
    if len(parts) < 4:
        return text
    folder_text = parts[0]
    name_text = parts[1]
    method_text = parts[2]
    url_text = "|".join(parts[3:]).strip()
    return build_exclusion_key(folder_text, name_text, method_text, url_text)


def result_exclusion_key(result: JsonDict) -> str:
    return build_exclusion_key(
        result.get("folder", ""),
        result.get("name", ""),
        result.get("method", ""),
        result.get("url", ""),
    )


def manual_case_exclusion_key(case: JsonDict) -> str:
    return build_exclusion_key(
        case.get("folder", ""),
        case.get("name", ""),
        case.get("method", ""),
        case.get("url", ""),
    )


def normalize_manual_exclusions(values: object) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    seen = set()
    for value in values:
        text = normalize_exclusion_key(value)
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def strip_auth_headers(headers: JsonDict) -> JsonDict:
    return strip_sensitive_headers(headers)


def normalize_manual_case(case: JsonDict, default_folder: str) -> JsonDict:
    case_id = str(case.get("id") or "").strip()
    method = str(case.get("method") or "GET").strip().upper() or "GET"
    url = str(case.get("url") or "").strip()
    name = str(case.get("name") or "").strip()
    folder = str(case.get("folder") or default_folder).strip() or default_folder
    message = str(case.get("message") or "").strip()
    status = str(case.get("status") or "FAILED").strip().upper() or "FAILED"
    actual_request_url = str(case.get("actual_request_url") or url).strip() or url
    err_code = str(case.get("err_code") or "").strip()
    created_at = str(case.get("created_at") or "").strip()

    expected_status = _coerce_int(case.get("expected_status")) or 200

    status_code = _coerce_int(case.get("status_code"))

    elapsed_ms = _coerce_int(case.get("elapsed_ms"))

    raw_request_info_value = case.get("request_info")
    raw_request_info: JsonDict = raw_request_info_value if isinstance(raw_request_info_value, dict) else {}
    req_headers = raw_request_info.get("headers")
    if not isinstance(req_headers, dict):
        req_headers = case.get("headers") if isinstance(case.get("headers"), dict) else {}
    req_params = raw_request_info.get("params")
    if not isinstance(req_params, dict):
        req_params = case.get("params") if isinstance(case.get("params"), dict) else {}
    req_body = raw_request_info.get("body") if "body" in raw_request_info else case.get("body")
    request_info = {
        "headers": req_headers,
        "params": req_params,
        "body": req_body,
    }

    raw_response_info_value = case.get("response_info")
    raw_response_info: JsonDict = raw_response_info_value if isinstance(raw_response_info_value, dict) else {}
    resp_headers = raw_response_info.get("headers")
    if not isinstance(resp_headers, dict):
        resp_headers = case.get("response_headers") if isinstance(case.get("response_headers"), dict) else {}
    if "body" in raw_response_info:
        resp_body = raw_response_info.get("body")
    else:
        resp_body = case.get("response_body")
    response_info = {
        "headers": resp_headers,
        "body": resp_body,
        "status_code": raw_response_info.get("status_code", status_code),
        "elapsed_ms": raw_response_info.get("elapsed_ms", elapsed_ms),
    }

    return {
        "id": case_id,
        "created_at": created_at,
        "name": name,
        "folder": folder,
        "method": method,
        "url": url,
        "actual_request_url": actual_request_url,
        "expected_status": expected_status,
        "status": status,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "message": message,
        "err_code": err_code,
        "retried": bool(case.get("retried", False)),
        "retry_history": case.get("retry_history") if isinstance(case.get("retry_history"), list) else [],
        "item_path": case.get("item_path") if isinstance(case.get("item_path"), list) else [],
        "request_info": request_info,
        "response_info": response_info,
    }


def to_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def sanitize_export_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/").split("/")[-1]
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized).strip(' .')
    return normalized or "collection"


def safe_report_artifact(reports_dir: Path, name: str) -> Optional[Path]:
    normalized = Path(str(name or "").strip()).name
    if not normalized:
        return None
    candidate = (reports_dir / normalized).resolve()
    try:
        candidate.relative_to(reports_dir)
    except ValueError:
        return None
    return candidate
