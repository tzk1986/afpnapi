#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告服务端，支持历史报告浏览、单报告查询、分页、详情与局域网访问。"""

import json
import logging
import os
import re
import socket
import threading
import uuid
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import requests
from flask import Flask, jsonify, make_response, redirect, render_template, request, send_from_directory, url_for

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

try:
    from postman_api_tester import config as _cfg
except Exception:
    _cfg = None


def _cfg_int(name: str, default: int) -> int:
    if _cfg is None:
        return int(default)
    try:
        return int(getattr(_cfg, name, default))
    except (TypeError, ValueError):
        return int(default)


def _cfg_bool(name: str, default: bool) -> bool:
    if _cfg is None:
        return bool(default)
    value = getattr(_cfg, name, default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _cfg_str(name: str, default: str) -> str:
    if _cfg is None:
        return str(default)
    value = getattr(_cfg, name, default)
    return str(value).strip() if value is not None else str(default)


RUN_RESULTS_PER_PAGE_DEFAULT = _cfg_int("RUN_RESULTS_PER_PAGE_DEFAULT", 30)
RUN_RESULTS_PER_PAGE_MIN = _cfg_int("RUN_RESULTS_PER_PAGE_MIN", 1)
RUN_RESULTS_PER_PAGE_MAX = _cfg_int("RUN_RESULTS_PER_PAGE_MAX", 100)

REPORT_VIEW_PAGE_SIZE_DEFAULT = _cfg_int("REPORT_VIEW_PAGE_SIZE_DEFAULT", 20)
REPORT_VIEW_PAGE_SIZE_MIN = _cfg_int("REPORT_VIEW_PAGE_SIZE_MIN", 1)
REPORT_VIEW_PAGE_SIZE_MAX = _cfg_int("REPORT_VIEW_PAGE_SIZE_MAX", 100)

RUN_STATUS_POLL_INTERVAL_MS = _cfg_int("RUN_STATUS_POLL_INTERVAL_MS", 3000)
ENABLE_SELECTIVE_RUN = _cfg_bool("ENABLE_SELECTIVE_RUN", True)
COLLECTION_PREVIEW_MAX_ITEMS = _cfg_int("COLLECTION_PREVIEW_MAX_ITEMS", 3000)

REPORT_EXPORT_DEFAULT_SCOPE = _cfg_str("REPORT_EXPORT_DEFAULT_SCOPE", "full").lower() or "full"
if REPORT_EXPORT_DEFAULT_SCOPE not in {"full", "report_only"}:
    REPORT_EXPORT_DEFAULT_SCOPE = "full"
REPORT_EXPORT_ALLOW_REPORT_ONLY = _cfg_bool("REPORT_EXPORT_ALLOW_REPORT_ONLY", True)
REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = _cfg_bool("REPORT_EXPORT_INCLUDE_AUTH_DEFAULT", False)
ENABLE_MANUAL_CASES = _cfg_bool("ENABLE_MANUAL_CASES", True)
MANUAL_CASE_FOLDER_NAME = _cfg_str("MANUAL_CASE_FOLDER_NAME", "人工补录") or "人工补录"
ENABLE_ADHOC_RUN = _cfg_bool("ENABLE_ADHOC_RUN", True)
ADHOC_MAX_ITEMS = _cfg_int("ADHOC_MAX_ITEMS", 200)
ADHOC_DEFAULT_COLLECTION_NAME = _cfg_str("ADHOC_DEFAULT_COLLECTION_NAME", "报告中心临时测试") or "报告中心临时测试"


def resolve_reports_dir() -> Path:
    env_dir = (os.environ.get("POSTMAN_REPORTS_DIR") or os.environ.get("REPORTS_DIR") or "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    try:
        from postman_api_tester import config as cfg
        cfg_dir = getattr(cfg, "REPORT_OUTPUT_DIR", "").strip()
        if cfg_dir:
            return Path(cfg_dir).expanduser().resolve()
    except Exception:
        pass

    return (PROJECT_ROOT / "reports").resolve()


REPORTS_DIR = resolve_reports_dir()
UPLOADS_DIR = (PROJECT_ROOT / "uploaded_collections").resolve()
EXPORTS_DIR = (UPLOADS_DIR / "exports").resolve()


_REPORTS_CACHE_TTL = 30.0
_REPORTS_CACHE = {"data": None, "by_name": None, "ts": 0.0}
RUN_JOBS: Dict[str, Dict[str, Any]] = {}
RUN_JOBS_LOCK = threading.Lock()

# 按报告名维护独立写锁，避免并发回写同一报告时发生覆盖。
REPORT_WRITE_LOCKS: Dict[str, threading.Lock] = {}
_REPORT_WRITE_LOCKS_META = threading.Lock()


def get_report_write_lock(report_name: str) -> threading.Lock:
    with _REPORT_WRITE_LOCKS_META:
        if report_name not in REPORT_WRITE_LOCKS:
            REPORT_WRITE_LOCKS[report_name] = threading.Lock()
        return REPORT_WRITE_LOCKS[report_name]


app = Flask(__name__, template_folder=str((PROJECT_ROOT / "templates").resolve()))



def get_local_ip() -> str:
    """Return LAN IP and fallback to loopback when detection fails."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def find_report(report_name: str) -> Dict[str, Any]:
    reports_by_name = _REPORTS_CACHE.get("by_name")
    if reports_by_name is None or _REPORTS_CACHE.get("data") is None:
        list_reports()
        reports_by_name = _REPORTS_CACHE.get("by_name")
    if reports_by_name and report_name in reports_by_name:
        return reports_by_name[report_name]
    raise FileNotFoundError(report_name)

def _invalidate_reports_cache() -> None:
    """主动清理报告列表缓存。"""
    _REPORTS_CACHE["data"] = None
    _REPORTS_CACHE["by_name"] = None
    _REPORTS_CACHE["ts"] = 0.0

def load_report_details_map(report: Dict[str, Any]) -> Dict[str, Any]:
    details_file = str(report.get("details_file") or "").strip()
    if not details_file:
        return {}
    details_path = REPORTS_DIR / details_file
    if not details_path.exists():
        return {}
    try:
        with details_path.open("r", encoding="utf-8") as file:
            details = json.load(file)
        return details if isinstance(details, dict) else {}
    except Exception:
        return {}

def list_report_summaries() -> List[Dict[str, Any]]:
    return [_report_list_item(report) for report in list_reports()]

def list_reports() -> List[Dict[str, Any]]:
    _now = _time.monotonic()
    if _REPORTS_CACHE["data"] is not None and (_now - _REPORTS_CACHE["ts"]) < _REPORTS_CACHE_TTL:
        return list(_REPORTS_CACHE["data"])

    reports: List[Dict[str, Any]] = []
    seen_report_names = set()

    for meta_path in report_meta_files():
        try:
            report = load_report_meta(meta_path)
            report["meta_file"] = meta_path.name
            reports.append(report)
            seen_report_names.add(report.get("report_name"))
        except Exception as exc:
            reports.append({
                "report_name": meta_path.name,
                "generated_at": "",
                "host_name": "",
                "collection_name": "",
                "source_file": "",
                "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "success_rate": "0%"},
                "load_error": str(exc),
                "results": [],
            })

    for html_path in legacy_postman_html_files():
        if html_path.name in seen_report_names:
            continue
        try:
            reports.append(load_legacy_postman_report(html_path))
        except Exception:
            continue

    # Final guard: regardless of data source, do not expose paged child reports.
    reports = [item for item in reports if is_total_report_name(item.get("report_name", ""))]

    reports.sort(key=lambda item: item.get("generated_at", ""), reverse=True)

    _REPORTS_CACHE["data"] = reports
    _REPORTS_CACHE["by_name"] = {str(item.get("report_name") or ""): item for item in reports}
    _REPORTS_CACHE["ts"] = _time.monotonic()
    return list(reports)

def _extract_collection_preview_items(collection_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    root_items = collection_data.get("item")
    if not isinstance(root_items, list):
        return result

    def walk(items: List[Any], folder_chain: List[str], path_prefix: List[int]) -> None:
        for index, item in enumerate(items):
            if len(result) >= COLLECTION_PREVIEW_MAX_ITEMS:
                return
            if not isinstance(item, dict):
                continue
            current_path = path_prefix + [index]
            name = str(item.get("name") or "")
            request_obj = item.get("request")
            if isinstance(request_obj, dict):
                method = str(request_obj.get("method") or "GET").upper()
                url = _build_preview_url(request_obj.get("url"))
                folder = " / ".join([x for x in folder_chain if x])
                result.append({
                    "index": len(result),
                    "name": name,
                    "folder": folder,
                    "method": method,
                    "url": url,
                    "item_path": current_path,
                    "item_path_text": ".".join(str(x) for x in current_path),
                })
                continue

            children = item.get("item")
            if isinstance(children, list):
                walk(children, folder_chain + [name], current_path)

    walk(root_items, [], [])
    return result


def _parse_json_text(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc
    return value


def _normalize_folder_chain(folder: Any) -> List[str]:
    text = str(folder or "").strip()
    if not text:
        return []
    normalized = text.replace('\\', '/').replace('|', '/').strip('/')
    return [part.strip() for part in normalized.split('/') if part.strip()]


def _get_or_create_folder(items: List[Dict[str, Any]], folder_chain: List[str]) -> List[Dict[str, Any]]:
    current_items = items
    for folder_name in folder_chain:
        target = None
        for item in current_items:
            if isinstance(item, dict) and "request" not in item and str(item.get("name") or "") == folder_name:
                if isinstance(item.get("item"), list):
                    target = item
                    break
        if target is None:
            target = {"name": folder_name, "item": []}
            current_items.append(target)
        child = target.setdefault("item", [])
        if not isinstance(child, list):
            child = []
            target["item"] = child
        current_items = child
    return current_items


def _is_placeholder_case_name(name: str) -> bool:
    """Treat all-question-mark names as placeholders caused by bad input/encoding."""
    text = str(name or "").strip()
    return bool(text) and bool(re.fullmatch(r"[?？\s_]+", text))


def _derive_case_name(raw_name: Any, method: str, url: str, index: int) -> str:
    text = str(raw_name or "").strip()
    if text and not _is_placeholder_case_name(text):
        return text

    raw_url = str(url or "").strip()
    if raw_url:
        if raw_url.startswith("{{baseUrl}}"):
            raw_url = raw_url[len("{{baseUrl}}"):] or "/"
        elif raw_url.startswith("{{base_url}}"):
            raw_url = raw_url[len("{{base_url}}"):] or "/"

        parsed = urlsplit(raw_url)
        if parsed.scheme and parsed.netloc:
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
        else:
            path = raw_url

        if path:
            return f"{method} {path}".strip()

    return f"接口{index + 1}"


def _normalize_adhoc_case(raw: Dict[str, Any], index: int, base_url: Optional[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"第 {index + 1} 条接口配置不是对象")

    method = str(raw.get("method") or "GET").strip().upper() or "GET"
    if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
        raise ValueError(f"第 {index + 1} 条接口 method 不支持: {method}")

    url = str(raw.get("url") or "").strip()
    if not url:
        raise ValueError(f"第 {index + 1} 条接口缺少 url")

    parsed = urlparse(url)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"第 {index + 1} 条接口 url 仅允许合法 http/https 地址")
    elif url.startswith("{{"):
        if not url.startswith("{{baseUrl}}") and not url.startswith("{{base_url}}"):
            raise ValueError(f"第 {index + 1} 条接口变量 URL 仅支持 {{baseUrl}} 或 {{base_url}}")
        if not base_url:
            raise ValueError(f"第 {index + 1} 条接口使用了变量 URL，但未提供 base_url")
    elif not base_url:
        raise ValueError(f"第 {index + 1} 条接口使用相对路径时必须提供 base_url")

    name = _derive_case_name(raw.get("name"), method, url, index)

    headers = _parse_json_text(raw.get("headers"), {})
    if not isinstance(headers, dict):
        raise ValueError(f"第 {index + 1} 条接口 headers 必须是 JSON 对象")

    params = _parse_json_text(raw.get("params"), {})
    if not isinstance(params, dict):
        raise ValueError(f"第 {index + 1} 条接口 params 必须是 JSON 对象")

    body_mode = str(raw.get("body_mode") or "none").strip().lower() or "none"
    if body_mode not in {"none", "raw", "urlencoded", "formdata", "graphql", "binary"}:
        raise ValueError(f"第 {index + 1} 条接口 body_mode 不支持: {body_mode}")

    raw_body_data = raw.get("body_data")
    if body_mode == "raw":
        body_data = raw_body_data
    else:
        body_data = _parse_json_text(raw_body_data, None)
    body_value = raw.get("body")
    if body_mode == "raw" and body_data is None and body_value is not None:
        body_data = body_value

    try:
        expected_status = int(raw.get("expected_status") or 200)
    except (TypeError, ValueError):
        expected_status = 200

    return {
        "name": name,
        "folder": str(raw.get("folder") or "").strip(),
        "method": method,
        "url": url,
        "headers": headers,
        "params": params,
        "body_mode": body_mode,
        "body_data": body_data,
        "expected_status": expected_status,
    }


def _build_adhoc_collection(cases: List[Dict[str, Any]], collection_name: str, base_url: Optional[str]) -> Dict[str, Any]:
    now_iso = datetime.utcnow().isoformat() + "Z"
    collection: Dict[str, Any] = {
        "info": {
            "name": collection_name,
            "description": "Generated by report center ad-hoc run",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "_postman_id": uuid.uuid4().hex,
        },
        "item": [],
        "variable": [],
    }
    if base_url:
        collection["variable"] = [{"key": "baseUrl", "value": base_url}]

    root_items = collection["item"]
    for case in cases:
        request_obj: Dict[str, Any] = {
            "method": case["method"],
            "header": [],
            "url": {"raw": case["url"]},
            "x_expected_status": case["expected_status"],
            "description": f"adhoc_generated_at={now_iso}",
        }
        _set_request_url(request_obj, case["url"], case["params"])
        _set_request_headers(request_obj, case["headers"])
        _set_request_body(request_obj, case.get("body_data"), body_mode=case.get("body_mode"), body_data=case.get("body_data"))

        item_node = {
            "name": case["name"],
            "request": request_obj,
            "response": [],
        }

        folder_chain = _normalize_folder_chain(case.get("folder"))
        parent_items = _get_or_create_folder(root_items, folder_chain)
        parent_items.append(item_node)

    return collection

def _to_bool(value: Any, default: bool = False) -> bool:
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


def _build_exclusion_key(folder: Any, name: Any, method: Any, url: Any) -> str:
    folder_text = str(folder or "").strip()
    name_text = str(name or "").strip()
    method_text = str(method or "").strip().upper()
    url_text = str(url or "").strip()
    return " | ".join([folder_text, name_text, method_text, url_text])


def _result_exclusion_key(result: Dict[str, Any]) -> str:
    return _build_exclusion_key(
        result.get("folder", ""),
        result.get("name", ""),
        result.get("method", ""),
        result.get("url", ""),
    )


def _manual_case_exclusion_key(case: Dict[str, Any]) -> str:
    return _build_exclusion_key(
        case.get("folder", ""),
        case.get("name", ""),
        case.get("method", ""),
        case.get("url", ""),
    )


def _normalize_manual_exclusions(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _normalize_manual_case(case: Dict[str, Any], default_folder: str) -> Dict[str, Any]:
    case_id = str(case.get("id") or "").strip()
    method = str(case.get("method") or "GET").strip().upper() or "GET"
    url = str(case.get("url") or "").strip()
    name = str(case.get("name") or "").strip()
    folder = str(case.get("folder") or default_folder or MANUAL_CASE_FOLDER_NAME).strip() or MANUAL_CASE_FOLDER_NAME
    message = str(case.get("message") or "").strip()
    status = str(case.get("status") or "FAILED").strip().upper() or "FAILED"
    actual_request_url = str(case.get("actual_request_url") or url).strip() or url
    err_code = str(case.get("err_code") or "").strip()

    try:
        expected_status = int(case.get("expected_status") or 200)
    except (TypeError, ValueError):
        expected_status = 200

    status_code = case.get("status_code")
    if status_code is not None:
        try:
            status_code = int(status_code)
        except (TypeError, ValueError):
            status_code = None

    elapsed_ms = case.get("elapsed_ms")
    if elapsed_ms is not None:
        try:
            elapsed_ms = int(elapsed_ms)
        except (TypeError, ValueError):
            elapsed_ms = None

    raw_request_info = case.get("request_info") if isinstance(case.get("request_info"), dict) else {}
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

    raw_response_info = case.get("response_info") if isinstance(case.get("response_info"), dict) else {}
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


def _remove_excluded_items(collection_data: Dict[str, Any], manual_exclusions: List[str]) -> int:
    excluded = set(_normalize_manual_exclusions(manual_exclusions))
    if not excluded:
        return 0

    removed = 0

    def walk(items: List[Dict[str, Any]], parent_folder: str) -> List[Dict[str, Any]]:
        nonlocal removed
        kept: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            name = str(item.get("name") or "")
            request = item.get("request") if isinstance(item.get("request"), dict) else None
            children = item.get("item") if isinstance(item.get("item"), list) else None

            if request is not None:
                key = _build_exclusion_key(
                    parent_folder,
                    name,
                    request.get("method", ""),
                    (request.get("url") or {}).get("raw", "") if isinstance(request.get("url"), dict) else request.get("url", ""),
                )
                if key in excluded:
                    removed += 1
                    continue
                kept.append(item)
                continue

            if children is not None:
                # 与报告结果中的 folder 保持一致，只使用直接父级目录名，而不是完整链路。
                next_folder = name
                item["item"] = walk(children, next_folder)
                if item["item"]:
                    kept.append(item)
                continue

            kept.append(item)
        return kept

    root_items = collection_data.get("item")
    if isinstance(root_items, list):
        collection_data["item"] = walk(root_items, "")
    return removed


def _append_manual_cases_to_collection(
    collection_data: Dict[str, Any],
    manual_cases: List[Dict[str, Any]],
    default_folder: str,
    include_auth: bool = False,
) -> int:
    if not manual_cases:
        return 0

    root_items = collection_data.get("item")
    if not isinstance(root_items, list):
        collection_data["item"] = []
        root_items = collection_data["item"]

    folder_name = str(default_folder or MANUAL_CASE_FOLDER_NAME).strip() or MANUAL_CASE_FOLDER_NAME
    folder_item = None
    for item in root_items:
        if isinstance(item, dict) and "request" not in item and str(item.get("name") or "") == folder_name:
            if isinstance(item.get("item"), list):
                folder_item = item
                break

    if folder_item is None:
        folder_item = {"name": folder_name, "item": []}
        root_items.append(folder_item)

    children = folder_item.setdefault("item", [])
    if not isinstance(children, list):
        children = []
        folder_item["item"] = children

    appended = 0
    for raw in manual_cases:
        if not isinstance(raw, dict):
            continue
        case = _normalize_manual_case(raw, folder_name)
        if not case.get("name") or not case.get("url"):
            continue

        method = case.get("method", "GET")
        url = case.get("url", "")
        request_info = case.get("request_info") if isinstance(case.get("request_info"), dict) else {}
        headers = request_info.get("headers") if isinstance(request_info.get("headers"), dict) else {}
        if not include_auth:
            headers = _strip_auth_headers(headers)
        params = request_info.get("params") if isinstance(request_info.get("params"), dict) else {}
        body = request_info.get("body")
        body_mode = request_info.get("body_mode")
        body_data = request_info.get("body_data")

        request_obj = {
            "method": method,
            "header": [],
            "url": {"raw": url},
        }

        _set_request_url(request_obj, url, params)
        _set_request_headers(request_obj, headers)
        _set_request_body(request_obj, body, body_mode=body_mode, body_data=body_data)

        children.append({"name": case.get("name", ""), "request": request_obj, "response": []})
        appended += 1

    return appended

def export_collection_with_latest_params(
    report: Dict[str, Any],
    include_auth: bool = False,
    export_scope: str = "full",
) -> Dict[str, Any]:
    source_file = str(report.get("source_file") or "").strip()
    if not source_file:
        raise ValueError("报告缺少 source_file，无法导出集合。")

    source_path = Path(source_file)
    if not source_path.exists():
        raise FileNotFoundError(f"源集合文件不存在: {source_file}")

    with source_path.open("r", encoding="utf-8") as f:
        collection_data = json.load(f)

    scope = str(export_scope or "full").strip().lower()
    if scope not in {"full", "report_only"}:
        scope = "full"
    if scope == "report_only" and not REPORT_EXPORT_ALLOW_REPORT_ONLY:
        scope = "full"

    details_map = load_report_details_map(report)
    updated_count = 0
    skipped_count = 0
    warnings: List[str] = []

    for index, result in enumerate(report.get("results", [])):
        detail = details_map.get(str(index)) or {}
        request_info = detail.get("request_info") or {}

        item = _item_by_path(collection_data, result.get("item_path") or [])
        if item is None:
            item = _find_item_fallback(collection_data, result)
            if item is None:
                skipped_count += 1
                warnings.append(f"索引 {index} 无法定位到集合节点: {result.get('name', '-')}")
                continue

        request_obj = item.setdefault("request", {})
        if not isinstance(request_obj, dict):
            skipped_count += 1
            warnings.append(f"索引 {index} 的 request 结构异常: {result.get('name', '-')}")
            continue

        method = str(result.get("method") or request_obj.get("method") or "GET").upper()
        url = str(result.get("url") or request_obj.get("url") or "").strip()
        headers = dict(request_info.get("headers") or {})
        if not include_auth:
            headers = _strip_auth_headers(headers)
        params = dict(request_info.get("params") or {})
        body = request_info.get("body")
        body_mode = request_info.get("body_mode")
        body_data = request_info.get("body_data")

        request_obj["method"] = method
        _set_request_url(request_obj, url, params)
        _set_request_headers(request_obj, headers)
        _set_request_body(request_obj, body, body_mode=body_mode, body_data=body_data)
        updated_count += 1

    final_collection = collection_data
    report_only_count = 0
    if scope == "report_only":
        selected_paths = _collect_report_item_paths(report)
        if not selected_paths:
            raise ValueError("导出范围为 report_only 时，报告中缺少可用 item_path。")
        final_collection = _prune_collection_to_paths(collection_data, selected_paths)
        pruned_items = _extract_collection_preview_items(final_collection)
        report_only_count = len(pruned_items)

    manual_cases: List[Dict[str, Any]] = []
    if ENABLE_MANUAL_CASES:
        for case in report.get("manual_cases", []):
            if isinstance(case, dict):
                manual_cases.append(_normalize_manual_case(case, str(case.get("folder") or MANUAL_CASE_FOLDER_NAME)))

    manual_exclusions = _normalize_manual_exclusions(report.get("manual_exclusions") or [])
    appended_manual_count = _append_manual_cases_to_collection(
        final_collection,
        manual_cases,
        MANUAL_CASE_FOLDER_NAME,
        include_auth=include_auth,
    )
    removed_excluded_count = _remove_excluded_items(final_collection, manual_exclusions)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    preferred_name = report.get("source_original_file") or source_path.name
    source_name = _sanitize_export_name(preferred_name)
    stem = Path(source_name).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "latest" if scope == "full" else "report_only"
    export_name = f"{stem}_{suffix}_{timestamp}.json"
    export_path = EXPORTS_DIR / export_name

    with export_path.open("w", encoding="utf-8") as f:
        json.dump(final_collection, f, indent=2, ensure_ascii=False)

    return {
        "file_name": export_name,
        "file_path": str(export_path),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "export_scope": scope,
        "report_only_count": report_only_count,
        "manual_cases_count": len(manual_cases),
        "manual_case_count": len(manual_cases),
        "appended_manual_count": appended_manual_count,
        "manual_case_exported_count": appended_manual_count,
        "excluded_count": len(manual_exclusions),
        "removed_excluded_count": removed_excluded_count,
        "composition": {
            "updated_requests": updated_count,
            "manual_cases_added": appended_manual_count,
            "excluded_removed": removed_excluded_count,
        },
        "warnings": warnings,
    }

def collect_report_artifacts(report: Dict[str, Any]) -> List[Path]:
    artifacts: List[Path] = []
    seen: set[str] = set()

    for file_name in (
        report.get("report_name", ""),
        report.get("details_file", ""),
        report.get("meta_file", ""),
    ):
        path = _safe_report_artifact(str(file_name or ""))
        if path is not None and path.name not in seen:
            artifacts.append(path)
            seen.add(path.name)

    report_name = str(report.get("report_name") or "").strip()
    report_stem = Path(report_name).stem
    if report_stem:
        for page_path in sorted(REPORTS_DIR.glob(f"{report_stem}_page_*.html")):
            resolved = page_path.resolve()
            try:
                resolved.relative_to(REPORTS_DIR)
            except ValueError:
                continue
            if resolved.name not in seen:
                artifacts.append(resolved)
                seen.add(resolved.name)

    return artifacts

def clamp_page(value: Any) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        page = 1
    return max(1, page)

def clamp_page_size(value: Any) -> int:
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        page_size = REPORT_VIEW_PAGE_SIZE_DEFAULT
    return max(REPORT_VIEW_PAGE_SIZE_MIN, min(page_size, REPORT_VIEW_PAGE_SIZE_MAX))

def normalize_status_filter(value: str) -> Optional[str]:
    normalized = str(value or "").strip().upper()
    if normalized in {"", "ALL", "RESULT", "全部", "结果"}:
        return None
    if normalized in {"PASSED", "SUCCESS", "成功"}:
        return "PASSED"
    if normalized in {"FAILED", "FAIL", "失败"}:
        return "FAILED"
    if normalized in {"ERROR", "错误"}:
        return "ERROR"
    return None

def filter_report_results(
    report: Dict[str, Any],
    keyword: str,
    status_filter: Optional[str],
    message_keyword: str,
    err_code_keyword: str,
    include_excluded: bool = True,
) -> List[Dict[str, Any]]:
    lowered_keyword = str(keyword or "").strip().lower()
    lowered_message_keyword = str(message_keyword or "").strip().lower()
    lowered_err_code_keyword = str(err_code_keyword or "").strip().lower()
    exclusion_set = set(_normalize_manual_exclusions(report.get("manual_exclusions") or []))
    details_map = load_report_details_map(report)
    filtered_items: List[Dict[str, Any]] = []

    for index, item in enumerate(report.get("results", [])):
        exclusion_key = _result_exclusion_key(item)
        excluded = exclusion_key in exclusion_set
        if excluded and not include_excluded:
            continue
        if status_filter and item.get("status") != status_filter:
            continue
        if lowered_keyword:
            search_text = " ".join([
                str(item.get("name", "")),
                str(item.get("url", "")),
                str(item.get("folder", "")),
                str(item.get("key", "")),
            ]).lower()
            if lowered_keyword not in search_text:
                continue
        if lowered_message_keyword:
            message_text = str(item.get("message", "")).lower()
            if lowered_message_keyword not in message_text:
                continue
        if lowered_err_code_keyword:
            err_code_text = str(item.get("err_code", "")).lower()
            if lowered_err_code_keyword not in err_code_text:
                continue
        filtered_items.append({
            "index": index,
            "name": item.get("name", ""),
            "folder": item.get("folder", ""),
            "method": item.get("method", ""),
            "url": item.get("url", ""),
            "status": item.get("status", ""),
            "status_code": item.get("status_code"),
            "message": item.get("message", ""),
            "err_code": item.get("err_code", ""),
            "excluded": excluded,
            "exclusion_key": exclusion_key,
            "detail_available": str(index) in details_map,
        })
    return filtered_items

def paginate_items(items: List[Dict[str, Any]], page: int, page_size: int) -> Dict[str, Any]:
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": current_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }

def compare_report_data(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_map = map_results(left)
    right_map = map_results(right)
    left_keys = set(left_map.keys())
    right_keys = set(right_map.keys())

    added_keys = sorted(right_keys - left_keys)
    removed_keys = sorted(left_keys - right_keys)
    common_keys = sorted(left_keys & right_keys)
    changed: List[Dict[str, Any]] = []

    for key in common_keys:
        before = left_map[key]
        after = right_map[key]
        if before.get("status") != after.get("status") or before.get("status_code") != after.get("status_code"):
            changed.append({
                "key": key,
                "name": after.get("name") or before.get("name"),
                "folder": after.get("folder") or before.get("folder"),
                "method": after.get("method") or before.get("method"),
                "url": after.get("url") or before.get("url"),
                "before_status": before.get("status"),
                "after_status": after.get("status"),
                "before_status_code": before.get("status_code"),
                "after_status_code": after.get("status_code"),
            })

    left_rate = _to_rate(left.get("summary", {}).get("success_rate", "0%"))
    right_rate = _to_rate(right.get("summary", {}).get("success_rate", "0%"))
    delta = right_rate - left_rate

    return {
        "left": left,
        "right": right,
        "summary": {
            "added_count": len(added_keys),
            "removed_count": len(removed_keys),
            "changed_count": len(changed),
            "success_rate_delta": round(delta, 2),
            "success_rate_delta_text": f"{delta:+.2f}%",
        },
        "added": [right_map[key] for key in added_keys],
        "removed": [left_map[key] for key in removed_keys],
        "changed": changed,
    }

def clamp_run_results_per_page(value: Any) -> int:
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        page_size = RUN_RESULTS_PER_PAGE_DEFAULT
    return max(RUN_RESULTS_PER_PAGE_MIN, min(page_size, RUN_RESULTS_PER_PAGE_MAX))


_RUN_JOBS_MAX = _cfg_int("RUN_JOBS_MAX", 200)

def _parse_selected_item_paths(raw: Any) -> List[List[int]]:
    if raw is None:
        return []

    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"selected_item_paths 不是有效 JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("selected_item_paths 必须是数组。")

    normalized: List[List[int]] = []
    seen = set()
    for item in data:
        if not isinstance(item, list) or not item:
            continue
        if not all(isinstance(index, int) and index >= 0 for index in item):
            raise ValueError("selected_item_paths 的每条路径必须是非负整数数组。")
        key = tuple(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(list(item))
    return normalized

def set_run_job(job_id: str, **updates: Any) -> None:
    with RUN_JOBS_LOCK:
        RUN_JOBS[job_id] = {**RUN_JOBS.get(job_id, {}), **updates}
        _evict_old_jobs()

def run_postman_job(
    job_id: str,
    postman_file: str,
    base_url: Optional[str],
    output_dir: str,
    token: Optional[str],
    report_name: Optional[str],
    source_original_file: Optional[str],
    results_per_page: int,
    selected_item_paths: Optional[List[List[int]]],
) -> None:
    set_run_job(job_id, status="running", message="任务正在执行中...")
    try:
        from postman_api_tester.postman_api_tester import run_postman_tests

        def on_progress(progress: Dict[str, Any]) -> None:
            total = int(progress.get("total") or 0)
            completed = int(progress.get("completed") or 0)
            percent = int(progress.get("percent") or 0)
            current_name = str(progress.get("current_name") or "")
            current_method = str(progress.get("current_method") or "")
            current_url = str(progress.get("current_url") or "")

            message = "任务正在执行中..."
            if total > 0:
                message = f"任务正在执行中: {completed}/{total} ({percent}%)"
                if current_name:
                    message = f"{message}，当前接口: {current_name}"

            set_run_job(
                job_id,
                status="running",
                message=message,
                total=total,
                completed=completed,
                percent=percent,
                current_name=current_name,
                current_method=current_method,
                current_url=current_url,
                last_status=str(progress.get("last_status") or ""),
            )

        report = run_postman_tests(
            postman_file=postman_file,
            base_url=base_url,
            output_dir=output_dir,
            token=token,
            report_name=report_name,
            source_original_file=source_original_file,
            results_per_page=results_per_page,
            selected_item_paths=selected_item_paths,
            progress_callback=on_progress,
        )
        set_run_job(
            job_id,
            status="success",
            message="执行完成，正在刷新报告索引。",
            report_name=os.path.basename(str(report.generated_report_file or "")),
            report_meta_name=os.path.basename(str(report.generated_meta_file or "")),
        )
        # 执行成功后立即使报告列表缓存失效
        _invalidate_reports_cache()
    except Exception as exc:
        set_run_job(job_id, status="failed", message=str(exc))

def get_run_job(job_id: str) -> Optional[Dict[str, Any]]:
    with RUN_JOBS_LOCK:
        job = RUN_JOBS.get(job_id)
        return dict(job) if job else None

def _report_list_item(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(report.get("summary") or {})
    return {
        "report_name": report.get("report_name", ""),
        "generated_at": report.get("generated_at", ""),
        "host_name": report.get("host_name", ""),
        "collection_name": report.get("collection_name", ""),
        "source_file": report.get("source_file", ""),
        "source_original_file": report.get("source_original_file", ""),
        "summary": {
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "error": summary.get("error", 0),
            "success_rate": summary.get("success_rate", "0%"),
        },
        "load_error": report.get("load_error", ""),
        "legacy": bool(report.get("legacy", False)),
    }

def report_meta_files() -> List[Path]:
    if not REPORTS_DIR.exists():
        return []
    return [path for path in sorted(REPORTS_DIR.glob("*_meta.json"), reverse=True) if is_total_report_file(path)]

def load_report_meta(meta_path: Path) -> Dict[str, Any]:
    with meta_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if "summary" not in data:
        data["summary"] = {}
    return data

def legacy_postman_html_files() -> List[Path]:
    if not REPORTS_DIR.exists():
        return []
    return [path for path in sorted(REPORTS_DIR.glob("*.html"), reverse=True) if is_total_report_file(path)]

def load_legacy_postman_report(report_path: Path) -> Dict[str, Any]:
    content = report_path.read_text(encoding="utf-8")
    results_match = re.search(r"let\s+allResults\s*=\s*(\[.*?\]);", content, re.S)
    total_match = re.search(r"<label>总计</label>\s*<span>(\d+)</span>", content)
    passed_match = re.search(r"<label>? 通过</label>\s*<span>(\d+)</span>", content)
    failed_match = re.search(r"<label>? 失败</label>\s*<span>(\d+)</span>", content)
    error_match = re.search(r"<label>! 错误</label>\s*<span>(\d+)</span>", content)
    rate_match = re.search(r"<label>成功率</label>\s*<span>([^<]+)</span>", content)
    duration_match = re.search(r"<label>耗时</label>\s*<span>([^<]+)</span>", content)
    time_match = re.search(r"开始:\s*([^|<]+)\s*\|\s*结束:\s*([^<]+)", content)

    raw_results = json.loads(results_match.group(1)) if results_match else []
    results = [
        {
            "key": " | ".join([
                item.get("folder", "") or "-",
                item.get("name", "") or "-",
                item.get("method", "") or "-",
                item.get("url", "") or "-",
            ]),
            "name": item.get("name", ""),
            "folder": item.get("folder", ""),
            "method": item.get("method", ""),
            "url": item.get("url", ""),
            "status": item.get("status", ""),
            "status_code": item.get("status_code"),
            "message": item.get("message", ""),
            "err_code": item.get("err_code", ""),
        }
        for item in raw_results
    ]

    generated_at = time_match.group(2).strip() if time_match else ""
    return {
        "report_name": report_path.name,
        "generated_at": generated_at,
        "host_name": "legacy-html",
        "collection_name": "",
        "source_file": str(report_path),
        "summary": {
            "total": int(total_match.group(1)) if total_match else len(results),
            "passed": int(passed_match.group(1)) if passed_match else len([item for item in results if item.get("status") == "PASSED"]),
            "failed": int(failed_match.group(1)) if failed_match else len([item for item in results if item.get("status") == "FAILED"]),
            "error": int(error_match.group(1)) if error_match else len([item for item in results if item.get("status") == "ERROR"]),
            "success_rate": rate_match.group(1).strip() if rate_match else "0.00%",
            "duration": duration_match.group(1).strip() if duration_match else "",
            "start_time": time_match.group(1).strip() if time_match else "",
            "end_time": time_match.group(2).strip() if time_match else "",
        },
        "details_file": f"{report_path.stem}_details.json",
        "results": results,
        "meta_file": "",
        "legacy": True,
    }


def is_total_report_name(report_name: str) -> bool:
    return "_page_" not in str(report_name or "").lower()

def _build_preview_url(url_obj: Any) -> str:
    if isinstance(url_obj, str):
        return url_obj
    if not isinstance(url_obj, dict):
        return ""

    raw = str(url_obj.get("raw") or "").strip()
    if raw:
        return raw

    path = url_obj.get("path")
    if isinstance(path, list):
        path_text = "/" + "/".join(str(part) for part in path if str(part).strip())
    else:
        path_text = str(path or "")
    if path_text and not path_text.startswith("/"):
        path_text = "/" + path_text

    query_list = url_obj.get("query") if isinstance(url_obj.get("query"), list) else []
    query_parts = []
    for query in query_list:
        if not isinstance(query, dict) or query.get("disabled"):
            continue
        key = str(query.get("key") or "")
        if not key:
            continue
        query_parts.append(f"{key}={str(query.get('value') or '')}")
    query_text = ("?" + "&".join(query_parts)) if query_parts else ""
    return f"{path_text}{query_text}" if path_text else query_text

def _item_by_path(collection_data: Dict[str, Any], item_path: List[int]) -> Optional[Dict[str, Any]]:
    if not isinstance(item_path, list) or not item_path:
        return None

    items = collection_data.get("item")
    if not isinstance(items, list):
        return None

    current: Optional[Dict[str, Any]] = None
    for depth, index in enumerate(item_path):
        if not isinstance(index, int) or index < 0 or index >= len(items):
            return None
        current = items[index]
        if depth < len(item_path) - 1:
            child_items = current.get("item") if isinstance(current, dict) else None
            if not isinstance(child_items, list):
                return None
            items = child_items
    if not isinstance(current, dict):
        return None
    if "request" not in current:
        return None
    return current

def _find_item_fallback(collection_data: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = collection_data.get("item")
    if not isinstance(items, list):
        return None

    candidates = _iter_request_items(items)
    name = str(result.get("name", ""))
    method = str(result.get("method", "")).upper()
    folder = str(result.get("folder", ""))

    exact = [
        row for row in candidates
        if row["name"] == name and row["method"] == method and row["folder"] == folder
    ]
    if len(exact) == 1:
        return exact[0]["item"]

    loose = [row for row in candidates if row["name"] == name and row["method"] == method]
    if len(loose) == 1:
        return loose[0]["item"]
    return None

def _strip_auth_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in (headers or {}).items():
        lower_key = str(key).lower()
        if lower_key in {
            "authorization",
            "token",
            "access_token",
            "auth_token",
            "x-token",
            "x-access-token",
            "access-token",
        }:
            continue
        cleaned[key] = value
    return cleaned

def _set_request_url(request_obj: Dict[str, Any], raw_url: str, params: Dict[str, Any]) -> None:
    merged_url = _merge_url_with_params(raw_url, params)
    url_obj = request_obj.get("url")
    if isinstance(url_obj, dict):
        request_obj["url"]["raw"] = merged_url
        request_obj["url"]["query"] = [
            {"key": str(key), "value": "" if value is None else str(value)}
            for key, value in (params or {}).items()
        ]
    else:
        request_obj["url"] = merged_url

def _set_request_headers(request_obj: Dict[str, Any], headers: Dict[str, Any]) -> None:
    request_obj["header"] = [
        {"key": str(key), "value": "" if value is None else str(value)}
        for key, value in (headers or {}).items()
    ]

def _normalize_urlencoded_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("urlencoded"), list):
        rows = data.get("urlencoded")
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = [{"key": key, "value": value} for key, value in data.items()]
    else:
        rows = []

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        value = "" if row.get("value") is None else str(row.get("value"))
        normalized.append({"key": key, "value": value})
    return normalized


def _normalize_formdata_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("formdata"), list):
        rows = data.get("formdata")
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        row_type = "file" if str(row.get("type") or "text").strip().lower() == "file" else "text"
        item: Dict[str, Any] = {"key": key, "type": row_type}
        if row_type == "file":
            file_name = str(row.get("file_name") or row.get("src") or "").strip()
            if file_name:
                item["src"] = file_name
                item["file_name"] = file_name
        else:
            item["value"] = "" if row.get("value") is None else str(row.get("value"))
        normalized.append(item)
    return normalized


def _normalize_graphql_data(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"query": "", "variables": {}}
    query = str(data.get("query") or "")
    variables_raw = data.get("variables")
    if isinstance(variables_raw, str):
        try:
            variables = json.loads(variables_raw or "{}")
        except Exception as exc:
            raise ValueError(f"GraphQL Variables 必须是合法 JSON: {exc}") from exc
    elif isinstance(variables_raw, dict):
        variables = variables_raw
    else:
        variables = {}
    return {"query": query, "variables": variables}


def _infer_body_mode_from_stored_body(body: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(body, dict):
        return None
    manual_mode = str(body.get("__manual_body_mode") or "").strip().lower()
    if manual_mode == "raw":
        return {
            "mode": "raw",
            "data": {
                "raw_language": str(body.get("raw_language") or "json"),
                "raw_content_type": str(body.get("raw_content_type") or "application/json"),
                "raw_content": str(body.get("raw_content") or ""),
            },
        }
    if manual_mode == "urlencoded":
        return {"mode": "urlencoded", "data": {"urlencoded": body.get("urlencoded") or []}}
    if manual_mode == "formdata":
        return {"mode": "formdata", "data": {"formdata": body.get("formdata") or []}}
    if manual_mode == "graphql":
        return {"mode": "graphql", "data": body.get("graphql") or {}}
    if manual_mode == "binary":
        return {"mode": "binary", "data": body.get("binary") or {}}
    if manual_mode == "none":
        return {"mode": "none", "data": None}

    if "formdata" in body:
        return {"mode": "formdata", "data": body}
    if "urlencoded" in body:
        return {"mode": "urlencoded", "data": body}
    if "query" in body and "variables" in body:
        return {"mode": "graphql", "data": body}
    if "file_name" in body and len(body.keys()) <= 3:
        return {"mode": "binary", "data": body}
    return None


def _set_request_body(request_obj: Dict[str, Any], body: Any, body_mode: Optional[str] = None, body_data: Any = None) -> None:
    mode = str(body_mode or "legacy").strip().lower()
    data = body_data

    if mode == "legacy":
        inferred = _infer_body_mode_from_stored_body(body)
        if inferred:
            mode = str(inferred.get("mode") or "legacy")
            data = inferred.get("data")

    if mode == "none":
        request_obj.pop("body", None)
        return

    if mode == "raw":
        if isinstance(data, dict):
            raw_content = str(data.get("raw_content") or "")
            raw_language = str(data.get("raw_language") or "text").strip().lower() or "text"
        else:
            raw_content = "" if data is None else str(data)
            raw_language = "text"
        request_obj["body"] = {
            "mode": "raw",
            "raw": raw_content,
            "options": {"raw": {"language": raw_language}},
        }
        return

    if mode == "urlencoded":
        rows = _normalize_urlencoded_rows(data)
        request_obj["body"] = {
            "mode": "urlencoded",
            "urlencoded": rows,
        }
        return

    if mode == "formdata":
        rows = _normalize_formdata_rows(data)
        request_obj["body"] = {
            "mode": "formdata",
            "formdata": rows,
        }
        return

    if mode == "graphql":
        gql = _normalize_graphql_data(data)
        request_obj["body"] = {
            "mode": "graphql",
            "graphql": {
                "query": gql["query"],
                "variables": json.dumps(gql["variables"], ensure_ascii=False),
            },
        }
        return

    if mode == "binary":
        file_name = ""
        if isinstance(data, dict):
            file_name = str(data.get("file_name") or data.get("src") or "").strip()
        request_obj["body"] = {
            "mode": "file",
            "file": {"src": file_name or None},
        }
        return

    if isinstance(body, (dict, list)):
        request_obj["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, ensure_ascii=False),
            "options": {"raw": {"language": "json"}},
        }
        return

    request_obj["body"] = {
        "mode": "raw",
        "raw": str(body),
    }


def _build_request_kwargs(
    *,
    is_multipart: bool,
    body_mode: str,
    body_data: Any,
    legacy_body: Any,
    headers: Dict[str, Any],
    files_source: Any,
) -> Dict[str, Any]:
    request_kwargs: Dict[str, Any] = {}
    headers_to_send = dict(headers or {})
    normalized_mode = str(body_mode or "legacy").strip().lower() or "legacy"
    normalized_data: Any = body_data
    stored_body: Any = None

    if is_multipart:
        if normalized_mode == "formdata":
            rows = _normalize_formdata_rows(body_data)
            data_rows = []
            file_rows = []
            for row in rows:
                key = row["key"]
                row_type = row["type"]
                if row_type == "file":
                    upload_key = str(row.get("upload_key") or "").strip()
                    if not upload_key:
                        upload_key = "upload_0"
                    file_obj = files_source.get(upload_key) if files_source is not None else None
                    if file_obj and str(file_obj.filename or "").strip():
                        file_rows.append((key, (file_obj.filename, file_obj.stream, file_obj.mimetype or "application/octet-stream")))
                        row["file_name"] = str(file_obj.filename or row.get("file_name") or "")
                else:
                    data_rows.append((key, "" if row.get("value") is None else str(row.get("value"))))
            headers_to_send.pop("Content-Type", None)
            request_kwargs["data"] = data_rows
            request_kwargs["files"] = file_rows
            normalized_data = {"formdata": rows}
            stored_body = normalized_data
        elif normalized_mode == "binary":
            upload_key = "upload_0"
            if isinstance(body_data, dict):
                upload_key = str(body_data.get("upload_key") or upload_key).strip() or "upload_0"
            file_obj = files_source.get(upload_key) if files_source is not None else None
            if not file_obj:
                raise ValueError("binary 模式缺少上传文件")
            payload_bytes = file_obj.read()
            request_kwargs["data"] = payload_bytes
            headers_to_send.setdefault("Content-Type", file_obj.mimetype or "application/octet-stream")
            normalized_data = {"file_name": str(file_obj.filename or "")}
            stored_body = normalized_data
        else:
            raise ValueError(f"multipart 请求不支持 body_mode={normalized_mode}")
    else:
        if normalized_mode == "none":
            request_kwargs["data"] = None
            normalized_data = None
            stored_body = None
        elif normalized_mode == "raw":
            raw_content = ""
            raw_language = "text"
            raw_ct = ""
            if isinstance(body_data, dict):
                raw_content = str(body_data.get("raw_content") or "")
                raw_language = str(body_data.get("raw_language") or "text").strip().lower() or "text"
                raw_ct = str(body_data.get("raw_content_type") or "").strip()
            if raw_ct:
                headers_to_send.setdefault("Content-Type", raw_ct)
            request_kwargs["data"] = raw_content
            normalized_data = {
                "raw_language": raw_language,
                "raw_content_type": raw_ct,
                "raw_content": raw_content,
            }
            stored_body = raw_content
        elif normalized_mode == "urlencoded":
            rows = _normalize_urlencoded_rows(body_data)
            params_list = [(row["key"], row["value"]) for row in rows]
            request_kwargs["data"] = urlencode(params_list, doseq=True)
            headers_to_send.setdefault("Content-Type", "application/x-www-form-urlencoded")
            normalized_data = {"urlencoded": rows}
            stored_body = {key: value for key, value in params_list}
        elif normalized_mode == "graphql":
            gql = _normalize_graphql_data(body_data)
            gql_payload = {"query": gql["query"], "variables": gql["variables"]}
            request_kwargs["json"] = gql_payload
            headers_to_send.setdefault("Content-Type", "application/json")
            normalized_data = gql_payload
            stored_body = gql_payload
        elif normalized_mode == "legacy":
            if legacy_body is not None:
                request_kwargs["json"] = legacy_body
            else:
                request_kwargs["data"] = None
            normalized_data = legacy_body
            stored_body = legacy_body
        else:
            raise ValueError(f"不支持的 body_mode: {normalized_mode}")

    return {
        "request_kwargs": request_kwargs,
        "headers_to_send": headers_to_send,
        "stored_body": stored_body,
        "stored_body_mode": normalized_mode,
        "stored_body_data": normalized_data,
    }

def _collect_report_item_paths(report: Dict[str, Any]) -> set:
    path_set = set()
    for result in report.get("results", []):
        path = result.get("item_path")
        if isinstance(path, list) and path and all(isinstance(i, int) and i >= 0 for i in path):
            path_set.add(tuple(path))
    return path_set

def _prune_collection_to_paths(collection_data: Dict[str, Any], selected_paths: set) -> Dict[str, Any]:
    import copy

    root_items = collection_data.get("item")
    if not isinstance(root_items, list):
        return copy.deepcopy(collection_data)

    def walk(items: List[Any], prefix: List[int]) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            current_path = prefix + [idx]
            if "request" in item:
                if tuple(current_path) in selected_paths:
                    kept.append(copy.deepcopy(item))
                continue

            children = item.get("item")
            if isinstance(children, list):
                kept_children = walk(children, current_path)
                if kept_children:
                    copied = copy.deepcopy(item)
                    copied["item"] = kept_children
                    kept.append(copied)
        return kept

    copied_collection = copy.deepcopy(collection_data)
    copied_collection["item"] = walk(root_items, [])
    return copied_collection

def _sanitize_export_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/").split("/")[-1]
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized).strip(' .')
    return normalized or "collection"

def _safe_report_artifact(name: str) -> Optional[Path]:
    normalized = Path(str(name or "").strip()).name
    if not normalized:
        return None
    candidate = (REPORTS_DIR / normalized).resolve()
    try:
        candidate.relative_to(REPORTS_DIR)
    except ValueError:
        return None
    return candidate

def map_results(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["key"]: item for item in report.get("results", [])}

def _to_rate(value: str) -> float:
    try:
        return float(str(value).replace("%", ""))
    except ValueError:
        return 0.0

def _evict_old_jobs() -> None:
    """已在 RUN_JOBS_LOCK 持有下调用：超出上限时清理最早完成的任务。"""
    if len(RUN_JOBS) <= _RUN_JOBS_MAX:
        return
    terminal_statuses = {"success", "failed"}
    finished = [
        jid for jid, job in RUN_JOBS.items()
        if job.get("status") in terminal_statuses
    ]
    # 按写入顺序保留最新一半已完成任务
    to_evict = finished[: max(0, len(finished) - _RUN_JOBS_MAX // 2)]
    for jid in to_evict:
        del RUN_JOBS[jid]

def is_total_report_file(path: Path) -> bool:
    name = path.name.lower()
    return "_page_" not in name

def _iter_request_items(items: List[Dict[str, Any]], folder: str = "") -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "request" in item:
            request = item.get("request") or {}
            flattened.append({
                "item": item,
                "name": str(item.get("name", "")),
                "folder": folder,
                "method": str(request.get("method", "")).upper(),
            })
            continue
        children = item.get("item")
        if isinstance(children, list):
            next_folder = str(item.get("name", ""))
            flattened.extend(_iter_request_items(children, next_folder))
    return flattened

def _merge_url_with_params(raw_url: str, params: Dict[str, Any]) -> str:
    raw_url = str(raw_url or "").strip()
    if not params:
        return raw_url

    split = urlsplit(raw_url)
    existing_pairs = parse_qsl(split.query, keep_blank_values=True)
    merged = {key: value for key, value in existing_pairs}
    for key, value in (params or {}).items():
        merged[str(key)] = "" if value is None else str(value)

    new_query = urlencode(merged, doseq=False)
    return urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))

def _extract_msg_errcode(body: Any) -> tuple:
    """从 JSON body 中提取 message 和 errCode，兼容 data 嵌套结构。"""
    if not isinstance(body, dict):
        return "", ""

    def pick(obj: dict, keys: List[str]) -> str:
        for key in keys:
            val = obj.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    msg_keys = ["message", "msg", "error_message", "errorMessage", "errMsg"]
    err_keys = ["errCode", "errcode", "errorCode", "error_code", "code"]

    message = pick(body, msg_keys)
    err_code = pick(body, err_keys)

    nested = body.get("data")
    if isinstance(nested, dict):
        if not message:
            message = pick(nested, msg_keys)
        if not err_code:
            err_code = pick(nested, err_keys)

    return message, err_code


def _compute_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按结果重算 summary，避免回写后统计字段不一致。"""
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASSED")
    failed = sum(1 for r in results if r.get("status") == "FAILED")
    error = sum(1 for r in results if r.get("status") == "ERROR")
    rate = f"{(passed / total * 100):.2f}%" if total > 0 else "0.00%"
    return {"total": total, "passed": passed, "failed": failed, "error": error, "success_rate": rate}


def _update_report_meta(report_name: str, updater) -> Dict[str, Any]:
    lock = get_report_write_lock(report_name)
    with lock:
        report = find_report(report_name)
        meta_file_name = str(report.get("meta_file") or "").strip()
        if not meta_file_name:
            raise ValueError("报告缺少 meta_file，无法更新元数据。")
        meta_path = REPORTS_DIR / meta_file_name
        if not meta_path.exists():
            raise FileNotFoundError(f"元数据文件不存在: {meta_file_name}")

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        if not isinstance(meta.get("manual_cases"), list):
            meta["manual_cases"] = []
        if not isinstance(meta.get("manual_exclusions"), list):
            meta["manual_exclusions"] = []

        updated_meta = updater(meta)
        if not isinstance(updated_meta, dict):
            raise ValueError("meta 更新回调必须返回 dict")

        tmp_meta = meta_path.with_suffix(".tmp")
        with tmp_meta.open("w", encoding="utf-8") as f:
            json.dump(updated_meta, f, indent=2, ensure_ascii=False)
        os.replace(str(tmp_meta), str(meta_path))

        _invalidate_reports_cache()
        return updated_meta


def add_manual_case(report_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_MANUAL_CASES:
        raise ValueError("当前环境未启用人工用例能力。")

    case = _normalize_manual_case(payload, str(payload.get("folder") or MANUAL_CASE_FOLDER_NAME))
    if not case.get("id"):
        case["id"] = uuid.uuid4().hex
    if not case.get("name"):
        raise ValueError("name 不能为空")
    if not case.get("url"):
        raise ValueError("url 不能为空")

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        manual_cases = [c for c in meta.get("manual_cases", []) if isinstance(c, dict)]
        manual_cases.append(case)
        meta["manual_cases"] = manual_cases
        return meta

    updated_meta = _update_report_meta(report_name, updater)
    return {"case": case, "manual_cases": updated_meta.get("manual_cases", [])}


def update_manual_case(report_name: str, case_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_MANUAL_CASES:
        raise ValueError("当前环境未启用人工用例能力。")
    case_id = str(case_id or "").strip()
    if not case_id:
        raise ValueError("case_id 不能为空")

    holder: Dict[str, Any] = {}

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        manual_cases = [c for c in meta.get("manual_cases", []) if isinstance(c, dict)]
        found = False
        updated: List[Dict[str, Any]] = []
        for raw in manual_cases:
            if str(raw.get("id") or "") != case_id:
                updated.append(raw)
                continue
            merged = dict(raw)
            merged.update(payload)
            normalized = _normalize_manual_case(merged, str(merged.get("folder") or MANUAL_CASE_FOLDER_NAME))
            normalized["id"] = case_id
            updated.append(normalized)
            holder["case"] = normalized
            found = True
        if not found:
            raise FileNotFoundError(f"未找到指定人工用例: {case_id}")
        meta["manual_cases"] = updated
        return meta

    updated_meta = _update_report_meta(report_name, updater)
    return {"case": holder.get("case"), "manual_cases": updated_meta.get("manual_cases", [])}


def delete_manual_case(report_name: str, case_id: str) -> Dict[str, Any]:
    if not ENABLE_MANUAL_CASES:
        raise ValueError("当前环境未启用人工用例能力。")
    case_id = str(case_id or "").strip()
    if not case_id:
        raise ValueError("case_id 不能为空")

    removed_key = ""

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal removed_key
        manual_cases = [c for c in meta.get("manual_cases", []) if isinstance(c, dict)]
        kept: List[Dict[str, Any]] = []
        found = False
        for item in manual_cases:
            if str(item.get("id") or "") == case_id:
                removed_key = _manual_case_exclusion_key(item)
                found = True
                continue
            kept.append(item)
        if not found:
            raise FileNotFoundError(f"未找到指定人工用例: {case_id}")
        meta["manual_cases"] = kept
        # 删除人工用例时同步移除该用例对应的 exclusion 标记
        exclusions = [x for x in _normalize_manual_exclusions(meta.get("manual_exclusions") or []) if x != removed_key]
        meta["manual_exclusions"] = exclusions
        return meta

    updated_meta = _update_report_meta(report_name, updater)
    return {"manual_cases": updated_meta.get("manual_cases", [])}


def set_case_exclusion(report_name: str, exclusion_key: str, excluded: bool) -> Dict[str, Any]:
    exclusion_key = str(exclusion_key or "").strip()
    if not exclusion_key:
        raise ValueError("exclusion_key 不能为空")

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        exclusions = _normalize_manual_exclusions(meta.get("manual_exclusions") or [])
        exclusion_set = set(exclusions)
        if excluded:
            exclusion_set.add(exclusion_key)
        else:
            exclusion_set.discard(exclusion_key)
        meta["manual_exclusions"] = sorted(exclusion_set)
        return meta

    updated_meta = _update_report_meta(report_name, updater)
    return {"manual_exclusions": updated_meta.get("manual_exclusions", [])}


def patch_report_result(
    report_name: str,
    result_index: int,
    new_result_fields: Dict[str, Any],
    new_request_info: Dict[str, Any],
    new_response_info: Dict[str, Any],
) -> Dict[str, Any]:
    """
    同步更新 _meta.json 与 _details.json。
    - 按 result_index 覆盖主结果并保留 retry_history 追踪
    - 自动重算 summary，保持 duration/time 等字段一致
    - 返回最新 summary
    """
    lock = get_report_write_lock(report_name)
    with lock:
        try:
            report = find_report(report_name)
        except FileNotFoundError:
            return {}

        meta_file_name = str(report.get("meta_file") or "").strip()
        if not meta_file_name:
            return {}

        meta_path = REPORTS_DIR / meta_file_name
        if not meta_path.exists():
            return {}

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        results: List[Dict[str, Any]] = meta.get("results", [])
        if result_index < 0 or result_index >= len(results):
            return {}

        # 记录本次重试历史到 retry_history
        old_result = dict(results[result_index])
        old_history: List[Dict[str, Any]] = old_result.pop("retry_history", [])
        retry_history = old_history + [old_result]

        # 若结果来自人工补录，则优先使用 meta 中保存的 request_info/response_info
        merged = {
            "name": old_result.get("name", ""),
            "folder": old_result.get("folder", ""),
            "method": new_result_fields.get("method", old_result.get("method", "")),
            "url": new_result_fields.get("url", old_result.get("url", "")),
            "item_path": new_result_fields.get("item_path", old_result.get("item_path", [])),
            "expected_status": new_result_fields.get("expected_status", old_result.get("expected_status", 200)),
            **new_result_fields,
            "retry_history": retry_history,
            "retried": True,
        }
        merged["key"] = " | ".join([
            merged.get("folder", "") or "-",
            merged.get("name", "") or "-",
            merged.get("method", "") or "-",
            merged.get("url", "") or "-",
        ])
        results[result_index] = merged
        meta["results"] = results

        # 更新 summary，确保统计值与结果集一致
        new_stats = _compute_summary(results)

        old_summary = meta.get("summary", {})
        meta["summary"] = {
            **old_summary,
            "total": new_stats["total"],
            "passed": new_stats["passed"],
            "failed": new_stats["failed"],
            "error": new_stats["error"],
            "success_rate": new_stats["success_rate"],
        }

        # 回写 meta
        tmp_meta = meta_path.with_suffix(".tmp")
        with tmp_meta.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.replace(str(tmp_meta), str(meta_path))

        # 回写 details
        details_file_name = str(report.get("details_file") or "").strip()
        if details_file_name:
            details_path = REPORTS_DIR / details_file_name
            details: Dict[str, Any] = {}
            if details_path.exists():
                try:
                    with details_path.open("r", encoding="utf-8") as f:
                        details = json.load(f)
                except Exception:
                    pass
            details[str(result_index)] = {
                "request_info": new_request_info,
                "response_info": new_response_info,
            }
            tmp_details = details_path.with_suffix(".tmp")
            with tmp_details.open("w", encoding="utf-8") as f:
                json.dump(details, f, indent=2, ensure_ascii=False)
            os.replace(str(tmp_details), str(details_path))

        # 统一使报告列表缓存失效，避免页面看到旧 summary / stats
        _invalidate_reports_cache()

        return meta["summary"]


def build_result_detail(report: Dict[str, Any], result_index: int) -> Dict[str, Any]:
    results = report.get("results", [])
    if result_index < 0 or result_index >= len(results):
        raise IndexError(result_index)

    result = dict(results[result_index])
    exclusion_key = _result_exclusion_key(result)
    exclusion_set = set(_normalize_manual_exclusions(report.get("manual_exclusions") or []))
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


@app.route("/health")
def health():
    """健康检查端点，用于监控系统存活状态。"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/")
def index():
    reports = list_report_summaries()
    port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
    return render_template(
        "index.html",
        host_name=socket.gethostname(),
        self_url=f"http://127.0.0.1:{port}",
        lan_url=f"http://{get_local_ip()}:{port}",
        reports_json=json.dumps(reports, ensure_ascii=False),
        run_results_per_page_default=RUN_RESULTS_PER_PAGE_DEFAULT,
        run_results_per_page_min=RUN_RESULTS_PER_PAGE_MIN,
        run_results_per_page_max=RUN_RESULTS_PER_PAGE_MAX,
        run_status_poll_interval_ms=RUN_STATUS_POLL_INTERVAL_MS,
        enable_selective_run=ENABLE_SELECTIVE_RUN,
        collection_preview_max_items=COLLECTION_PREVIEW_MAX_ITEMS,
        enable_adhoc_run=ENABLE_ADHOC_RUN,
        adhoc_max_items=ADHOC_MAX_ITEMS,
        adhoc_default_collection_name=ADHOC_DEFAULT_COLLECTION_NAME,
    )


@app.route("/adhoc-run")
def adhoc_run_page():
    if not ENABLE_ADHOC_RUN:
        return redirect(url_for("index"))
    return render_template(
        "adhoc_run.html",
        run_results_per_page_default=RUN_RESULTS_PER_PAGE_DEFAULT,
        run_results_per_page_min=RUN_RESULTS_PER_PAGE_MIN,
        run_results_per_page_max=RUN_RESULTS_PER_PAGE_MAX,
        run_status_poll_interval_ms=RUN_STATUS_POLL_INTERVAL_MS,
        adhoc_max_items=ADHOC_MAX_ITEMS,
        adhoc_default_collection_name=ADHOC_DEFAULT_COLLECTION_NAME,
    )


@app.route("/report-view")
def report_view():
    report_name = request.args.get("name", "")
    if not report_name:
        reports = list_reports()
        if reports:
            return redirect(url_for("report_view", name=reports[0]["report_name"]))
        return redirect(url_for("index"))

    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return render_template("report_not_found.html", name=report_name), 404

    template_updated_at = "-"
    try:
        template_path = (PROJECT_ROOT / "templates" / "report_view.html").resolve()
        template_updated_at = datetime.fromtimestamp(template_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        template_updated_at = "-"

    html = render_template(
        "report_view.html",
        report_name=report.get("report_name", ""),
        report_name_json=json.dumps(report.get("report_name", ""), ensure_ascii=False),
        collection_name=report.get("collection_name", ""),
        source_file=report.get("source_file", ""),
        generated_at=report.get("generated_at", ""),
        summary=report.get("summary", {}),
        report_view_page_size_default=REPORT_VIEW_PAGE_SIZE_DEFAULT,
        report_export_default_scope=REPORT_EXPORT_DEFAULT_SCOPE,
        report_export_allow_report_only=REPORT_EXPORT_ALLOW_REPORT_ONLY,
        report_export_include_auth_default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT,
        enable_manual_cases=ENABLE_MANUAL_CASES,
        manual_case_folder_name=MANUAL_CASE_FOLDER_NAME,
        template_updated_at=template_updated_at,
    )
    response = make_response(html)
    # 避免浏览器缓存旧版页面，确保模板改动即时生效。
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/reports/<path:filename>")
def serve_report(filename: str):
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/exports/<path:filename>")
def serve_export(filename: str):
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)


@app.route("/api/reports")
def api_reports():
    return jsonify(list_reports())


@app.route("/api/collection-preview", methods=["POST"])
def api_collection_preview():
    if not ENABLE_SELECTIVE_RUN:
        return jsonify({"error": "当前环境未启用接口选择执行功能。"}), 403

    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return jsonify({"error": "请上传有效的 Postman JSON 文件"}), 400

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return jsonify({"error": "上传文件必须是 .json 格式"}), 400

    try:
        collection_data = json.load(collection_file.stream)
    except Exception as exc:
        return jsonify({"error": f"JSON 解析失败: {exc}"}), 400

    preview_items = _extract_collection_preview_items(collection_data)
    total = len(preview_items)
    truncated = False
    if total >= COLLECTION_PREVIEW_MAX_ITEMS:
        truncated = True

    return jsonify({
        "file_name": original_name,
        "total": total,
        "truncated": truncated,
        "max_items": COLLECTION_PREVIEW_MAX_ITEMS,
        "items": preview_items,
    })


@app.route("/api/export-collection", methods=["POST"])
def api_export_collection():
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    include_auth = _to_bool(payload.get("include_auth"), default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT)
    export_scope = str(payload.get("export_scope", REPORT_EXPORT_DEFAULT_SCOPE)).strip().lower() or REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope not in {"full", "report_only"}:
        export_scope = REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope == "report_only" and not REPORT_EXPORT_ALLOW_REPORT_ONLY:
        export_scope = "full"
    if not report_name:
        return jsonify({"error": "report_name 不能为空"}), 400

    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    try:
        exported = export_collection_with_latest_params(
            report,
            include_auth=include_auth,
            export_scope=export_scope,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "report_name": report_name,
        "file_name": exported["file_name"],
        "download_url": f"/exports/{exported['file_name']}",
        "updated_count": exported["updated_count"],
        "skipped_count": exported["skipped_count"],
        "manual_case_count": exported.get("manual_case_count", 0),
        "manual_case_exported_count": exported.get("manual_case_exported_count", 0),
        "excluded_count": exported.get("excluded_count", 0),
        "include_auth": include_auth,
        "export_scope": exported["export_scope"],
        "report_only_count": exported["report_only_count"],
        "warnings": exported["warnings"],
    })


@app.route("/api/report-meta/<path:report_name>")
def api_report_detail(report_name: str):
    try:
        return jsonify(find_report(report_name))
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404


@app.route("/api/manual-cases/<path:report_name>")
def api_manual_cases(report_name: str):
    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    manual_cases = [
        _normalize_manual_case(case, str(case.get("folder") or MANUAL_CASE_FOLDER_NAME))
        for case in (report.get("manual_cases") or [])
        if isinstance(case, dict)
    ]
    manual_exclusions = _normalize_manual_exclusions(report.get("manual_exclusions") or [])
    exclusion_set = set(manual_exclusions)
    response_cases = []
    for case in manual_cases:
        key = _manual_case_exclusion_key(case)
        response_cases.append({
            **case,
            "exclusion_key": key,
            "excluded": key in exclusion_set,
        })
    return jsonify({
        "report_name": report_name,
        "enabled": ENABLE_MANUAL_CASES,
        "default_folder": MANUAL_CASE_FOLDER_NAME,
        "manual_cases": response_cases,
        "manual_exclusions": manual_exclusions,
    })


@app.route("/api/manual-cases/add", methods=["POST"])
def api_manual_case_add():
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    if not report_name:
        return jsonify({"error": "report_name 不能为空"}), 400
    case_payload = dict(payload.get("case") or {})
    if not case_payload:
        return jsonify({"error": "case 不能为空"}), 400
    try:
        result = add_manual_case(report_name, case_payload)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "report_name": report_name,
        "case": result.get("case"),
        "manual_cases": result.get("manual_cases", []),
    })


@app.route("/api/manual-cases/update", methods=["PUT"])
def api_manual_case_update():
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    case_payload = dict(payload.get("case") or {})
    if not report_name:
        return jsonify({"error": "report_name 不能为空"}), 400
    if not case_id:
        return jsonify({"error": "case_id 不能为空"}), 400
    try:
        result = update_manual_case(report_name, case_id, case_payload)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "report_name": report_name,
        "case": result.get("case"),
        "manual_cases": result.get("manual_cases", []),
    })


@app.route("/api/manual-cases/delete", methods=["DELETE"])
def api_manual_case_delete():
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    if not report_name:
        return jsonify({"error": "report_name 不能为空"}), 400
    if not case_id:
        return jsonify({"error": "case_id 不能为空"}), 400
    try:
        result = delete_manual_case(report_name, case_id)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "report_name": report_name,
        "manual_cases": result.get("manual_cases", []),
    })


@app.route("/api/report-case-exclusion", methods=["POST"])
def api_report_case_exclusion():
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    exclusion_key = str(payload.get("exclusion_key") or "").strip()
    excluded = _to_bool(payload.get("excluded"), default=True)
    if not report_name:
        return jsonify({"error": "report_name 不能为空"}), 400
    if not exclusion_key:
        return jsonify({"error": "exclusion_key 不能为空"}), 400
    try:
        result = set_case_exclusion(report_name, exclusion_key, excluded)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "report_name": report_name,
        "excluded": excluded,
        "manual_exclusions": result.get("manual_exclusions", []),
    })


@app.route("/api/report-delete/<path:report_name>", methods=["DELETE"])
def api_report_delete(report_name: str):
    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    artifacts = collect_report_artifacts(report)
    deleted_files: List[str] = []
    for artifact in artifacts:
        if artifact.exists() and artifact.is_file():
            artifact.unlink()
            deleted_files.append(artifact.name)

    _invalidate_reports_cache()
    logger.info("删除报告产物成功: report=%s files=%s", report_name, deleted_files)
    return jsonify({
        "success": True,
        "report_name": report_name,
        "deleted_files": deleted_files,
    })


@app.route("/api/report-results/<path:report_name>")
def api_report_results(report_name: str):
    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    page = clamp_page(request.args.get("page", 1))
    page_size = clamp_page_size(request.args.get("page_size", REPORT_VIEW_PAGE_SIZE_DEFAULT))
    keyword = request.args.get("query", "")
    message_keyword = request.args.get("message_query", "")
    err_code_keyword = request.args.get("err_code_query", "")
    status_filter = normalize_status_filter(request.args.get("status", "all"))
    include_excluded = _to_bool(request.args.get("include_excluded"), default=True)
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
    return jsonify(paged)


@app.route("/api/report-result-detail/<path:report_name>/<int:result_index>")
def api_report_result_detail(report_name: str, result_index: int):
    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    try:
        return jsonify(build_result_detail(report, result_index))
    except IndexError:
        return jsonify({"error": f"结果索引不存在: {result_index}"}), 404


@app.route("/api/compare")
def api_compare():
    left_name = request.args.get("left", "")
    right_name = request.args.get("right", "")
    if not left_name or not right_name:
        return jsonify({"error": "left 和 right 参数不能为空"}), 400
    try:
        left = find_report(left_name)
        right = find_report(right_name)
    except FileNotFoundError as exc:
        return jsonify({"error": f"报告不存在: {exc}"}), 404
    return jsonify(compare_report_data(left, right))


@app.route("/test-token", methods=["POST"])
def test_token():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", "")).strip()
    if not token:
        return jsonify({"success": False, "message": "token 不能为空"}), 400
    return jsonify({"success": True, "message": "token 格式有效，可用于后续请求"})


@app.route("/re-request-api", methods=["POST"])
def re_request_api():
    is_multipart = bool(request.content_type and request.content_type.startswith("multipart/form-data"))
    payload = request.get_json(silent=True) or {}
    req_meta: Dict[str, Any] = {}
    if is_multipart:
        try:
            req_meta = json.loads(str(request.form.get("request_meta") or "{}"))
        except Exception:
            req_meta = {}

    source = req_meta if is_multipart else payload
    url = str(source.get("url", "")).strip()
    method = str(source.get("method", "GET")).upper()
    headers = dict(source.get("headers") or {})
    params = dict(source.get("params") or {})
    body_mode = str(source.get("body_mode") or "legacy").strip().lower()
    body_data = source.get("body_data")
    legacy_body = payload.get("body")
    token = str(source.get("token", "")).strip()
    # 是否将重试结果回写到报告文件
    save_to_report = bool(source.get("save_to_report", False))
    rpt_name = str(source.get("report_name", "")).strip()
    rpt_index_raw = source.get("result_index")
    try:
        rpt_index: Optional[int] = int(rpt_index_raw) if rpt_index_raw is not None else None
    except (TypeError, ValueError):
        rpt_index = None
    try:
        expected_status = int(source.get("expected_status") or 200)
    except (TypeError, ValueError):
        expected_status = 200

    if not url:
        return jsonify({"error": "url 不能为空"}), 400
    _parsed = urlparse(url)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        return jsonify({"error": "url 仅允许合法的 http/https 地址"}), 400

    try:
        import postman_api_tester.config as _cfg
        connect_timeout = int(getattr(_cfg, "REQUEST_CONNECT_TIMEOUT", 10))
        read_timeout = int(getattr(_cfg, "REQUEST_READ_TIMEOUT", 30))
    except Exception:
        connect_timeout, read_timeout = 10, 30

    if token:
        header_key = None
        for existing_key in list(headers.keys()):
            if existing_key.lower() == "authorization":
                header_key = existing_key
            if existing_key.lower() == "token":
                headers.pop(existing_key)
        if header_key:
            headers[header_key] = f"Bearer {token}"
        else:
            headers["token"] = token

    try:
        prepared = _build_request_kwargs(
            is_multipart=is_multipart,
            body_mode=body_mode,
            body_data=body_data,
            legacy_body=legacy_body,
            headers=headers,
            files_source=request.files,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    request_kwargs = prepared["request_kwargs"]
    headers_to_send = prepared["headers_to_send"]
    stored_body = prepared["stored_body"]
    stored_body_mode = prepared["stored_body_mode"]
    stored_body_data = prepared["stored_body_data"]

    try:
        response = requests.request(
            method=method, url=url, headers=headers_to_send, params=params,
            **request_kwargs, timeout=(connect_timeout, read_timeout)
        )
        try:
            response_body: Any = response.json()
        except ValueError:
            response_body = response.text
        actual_request_url = str(getattr(response.request, "url", "") or "")

        # 读取响应中的 message/errCode 作为判定依据
        response_message, err_code = _extract_msg_errcode(response_body)
        status_code_ok = response.status_code == expected_status
        normalized_msg = str(response_message or "").strip().lower()
        message_ok = normalized_msg == "" or normalized_msg == "success"

        if status_code_ok and message_ok:
            result_status = "PASSED"
            result_message = response_message
        else:
            result_status = "FAILED"
            if not status_code_ok:
                result_message = f"状态码不匹配: 期望 {expected_status}, 实际 {response.status_code}; message: {response_message}"
            else:
                result_message = f"message 校验未通过(期望为空或 success), 实际为: {response_message}"

        new_request_info = {
            "headers": headers_to_send,
            "params": params,
            "body": stored_body,
            "body_mode": stored_body_mode,
            "body_data": stored_body_data,
        }
        new_response_info = {"headers": dict(response.headers), "body": response_body}

        result_fields = {
            "method": method,
            "url": url,
            "actual_request_url": actual_request_url,
            "item_path": source.get("item_path", []),
            "expected_status": expected_status,
            "status": result_status,
            "status_code": response.status_code,
            "message": result_message,
            "err_code": err_code,
        }

        new_summary: Dict[str, Any] = {}
        if save_to_report and rpt_name and rpt_index is not None:
            new_summary = patch_report_result(rpt_name, rpt_index, result_fields, new_request_info, new_response_info)

        return jsonify({
            "name": source.get("name", url),
            "folder": source.get("folder", ""),
            "method": method,
            "url": url,
            "actual_request_url": actual_request_url,
            **result_fields,
            "request_info": new_request_info,
            "response_info": new_response_info,
            "new_summary": new_summary,
            "saved": bool(new_summary),
        })
    except Exception as exc:
        return jsonify({
            "name": source.get("name", url),
            "folder": source.get("folder", ""),
            "method": method,
            "url": url,
            "actual_request_url": url,
            "status": "ERROR",
            "status_code": None,
            "message": str(exc),
            "err_code": "",
            "request_info": {
                "headers": headers_to_send,
                "params": params,
                "body": stored_body,
                "body_mode": stored_body_mode,
                "body_data": stored_body_data,
            },
            "response_info": {"headers": {}, "body": str(exc)},
            "new_summary": {},
            "saved": False,
        })


@app.route("/api/proxy-request", methods=["POST"])
def api_proxy_request():
    """代理执行 HTTP 请求，供人工用例「发送」功能调用。仅允许 http/https。"""
    is_multipart = bool(request.content_type and request.content_type.startswith("multipart/form-data"))
    payload = request.get_json(silent=True) or {}
    req_meta: Dict[str, Any] = {}
    if is_multipart:
        try:
            req_meta = json.loads(str(request.form.get("request_meta") or "{}"))
        except Exception:
            req_meta = {}

    source = req_meta if is_multipart else payload
    url = str(source.get("url") or "").strip()
    method = str(source.get("method") or "GET").upper()
    req_headers = dict(source.get("headers") or {})
    req_params = dict(source.get("params") or {})
    body_mode = str(source.get("body_mode") or "legacy").strip().lower()
    body_data = source.get("body_data")
    legacy_body = payload.get("body")

    if not url:
        return jsonify({"error": "url 不能为空"}), 400
    _parsed = urlparse(url)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        return jsonify({"error": "url 仅允许合法的 http/https 地址"}), 400
    try:
        import postman_api_tester.config as _cfg
        connect_timeout = int(getattr(_cfg, "REQUEST_CONNECT_TIMEOUT", 10))
        read_timeout = int(getattr(_cfg, "REQUEST_READ_TIMEOUT", 30))
    except Exception:
        connect_timeout, read_timeout = 10, 30

    try:
        prepared = _build_request_kwargs(
            is_multipart=is_multipart,
            body_mode=body_mode,
            body_data=body_data,
            legacy_body=legacy_body,
            headers=req_headers,
            files_source=request.files,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    request_kwargs = prepared["request_kwargs"]
    headers_to_send = prepared["headers_to_send"]

    try:
        t0 = _time.time()
        resp = requests.request(
            method=method,
            url=url,
            headers=headers_to_send,
            params=req_params,
            **request_kwargs,
            timeout=(connect_timeout, read_timeout),
        )
        elapsed_ms = round((_time.time() - t0) * 1000)
        try:
            response_body: Any = resp.json()
        except ValueError:
            response_body = resp.text
        return jsonify({
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "response_headers": dict(resp.headers),
            "response_body": response_body,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/run-postman", methods=["POST"])
def api_run_postman():
    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return jsonify({"error": "请上传有效的 Postman JSON 文件"}), 400

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return jsonify({"error": "上传文件必须是 .json 格式"}), 400

    # 清洗文件名，避免路径穿越或注入
    import re as _re
    _safe_name = _re.sub(r'[^\w\u4e00-\u9fff\-. ()（）【】]', '_', original_name).strip('. ')
    original_name = _safe_name if _safe_name else "collection.json"

    base_url = str(request.form.get("base_url", "")).strip() or None
    # 严格校验 base_url，仅允许 http/https，阻断 SSRF 风险
    if base_url is not None:
        from urllib.parse import urlparse as _urlparse
        _parsed = _urlparse(base_url)
        if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
            return jsonify({"error": "base_url 仅允许合法的 http/https 地址"}), 400
    token = str(request.form.get("token", "")).strip() or None
    output_dir = str(request.form.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(request.form.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(request.form.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    run_scope = str(request.form.get("run_scope", "all")).strip().lower() or "all"
    raw_selected_paths = request.form.get("selected_item_paths", "")
    selected_item_paths: List[List[int]] = []
    if ENABLE_SELECTIVE_RUN and run_scope == "selected":
        try:
            selected_item_paths = _parse_selected_item_paths(raw_selected_paths)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not selected_item_paths:
            return jsonify({"error": "选择了仅执行已选接口，但未提供有效 selected_item_paths"}), 400

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name).suffix or ".json"
    job_id = uuid.uuid4().hex
    saved_file = UPLOADS_DIR / f"{job_id}{suffix}"
    collection_file.save(str(saved_file))

    set_run_job(
        job_id,
        id=job_id,
        status="queued",
        message="任务已入队，等待执行。",
        total=0,
        completed=0,
        percent=0,
        current_name="",
        file_name=original_name,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name or "",
        run_scope=("selected" if selected_item_paths else "all"),
        selected_count=len(selected_item_paths),
    )

    worker = threading.Thread(
        target=run_postman_job,
        args=(
            job_id,
            str(saved_file),
            base_url,
            output_dir,
            token,
            report_name,
            original_name,
            results_per_page,
            selected_item_paths,
        ),
        daemon=True,
    )
    worker.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "任务已创建，请轮询状态接口获取执行进度。",
    })


@app.route("/api/run-ad-hoc-tests", methods=["POST"])
def api_run_ad_hoc_tests():
    if not ENABLE_ADHOC_RUN:
        return jsonify({"error": "当前环境未启用直接新增接口测试能力。"}), 403

    payload = request.get_json(silent=True) or {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        return jsonify({"error": "cases 不能为空，且必须是数组。"}), 400
    if len(raw_cases) > ADHOC_MAX_ITEMS:
        return jsonify({"error": f"单次最多支持 {ADHOC_MAX_ITEMS} 条接口。"}), 400

    base_url = str(payload.get("base_url", "")).strip() or None
    if base_url is not None:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return jsonify({"error": "base_url 仅允许合法的 http/https 地址"}), 400

    token = str(payload.get("token", "")).strip() or None
    output_dir = str(payload.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(payload.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(payload.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    collection_name = str(payload.get("collection_name", "")).strip() or ADHOC_DEFAULT_COLLECTION_NAME

    try:
        normalized_cases = [_normalize_adhoc_case(item, idx, base_url) for idx, item in enumerate(raw_cases)]
        collection_data = _build_adhoc_collection(normalized_cases, collection_name, base_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    saved_file = UPLOADS_DIR / f"{job_id}.json"
    with saved_file.open("w", encoding="utf-8") as f:
        json.dump(collection_data, f, indent=2, ensure_ascii=False)

    source_original_file = _sanitize_export_name(f"{collection_name}.json")
    set_run_job(
        job_id,
        id=job_id,
        status="queued",
        message="任务已入队，等待执行。",
        total=0,
        completed=0,
        percent=0,
        current_name="",
        file_name=source_original_file,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name or "",
        run_scope="all",
        selected_count=0,
        collection_name=collection_name,
        adhoc=True,
    )

    worker = threading.Thread(
        target=run_postman_job,
        args=(
            job_id,
            str(saved_file),
            base_url,
            output_dir,
            token,
            report_name,
            source_original_file,
            results_per_page,
            None,
        ),
        daemon=True,
    )
    worker.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "ad-hoc 任务已创建，请轮询状态接口获取执行进度。",
    })


@app.route("/api/run-postman-status/<path:job_id>")
def api_run_postman_status(job_id: str):
    job = get_run_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在。"}), 404
    return jsonify(job)


@app.route("/latest")
def latest_report():
    reports = list_reports()
    if not reports:
        return redirect(url_for("index"))
    return redirect(url_for("report_view", name=reports[0]["report_name"]))


if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
    host = os.environ.get("REPORT_SERVER_HOST", "0.0.0.0")
    print(f"报告目录: {REPORTS_DIR}")
    logger.info("报告服务启动: http://127.0.0.1:%d", port)
    logger.info("局域网访问地址: http://%s:%d", get_local_ip(), port)
    try:
        from waitress import serve
        logger.info("使用 waitress WSGI 服务器（生产模式）")
        serve(app, host=host, port=port)
    except ImportError:
        logger.warning("waitress 未安装，降级使用 Flask 开发服务器（建议 pip install waitress）")
        app.run(host=host, port=port, debug=False)
