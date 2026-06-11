"""Collection utility implementations used by export/query flows.

开发导读：
- 职责：collection 树遍历、路径裁剪、人工用例追加、排除项剔除、ad-hoc 用例归一化、预览项提取。
- 入口：item_by_path()/prune_collection_to_paths()/append_manual_cases_to_collection()、
       normalize_adhoc_case()/build_adhoc_collection()/extract_collection_preview_items()。
- 使用方：report_export_service、collection 查询相关服务、adhoc_handler、collection_handler。
"""

import copy
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, cast
from urllib.parse import urlparse, urlsplit

from postman_api_tester.report_server_utils import (
    build_exclusion_key,
    normalize_manual_case,
    normalize_manual_exclusions,
    strip_auth_headers,
)
from postman_api_tester.utils.request_builder import (
    set_request_body,
    set_request_headers,
    set_request_url,
)

logger = logging.getLogger(__name__)


def item_by_path(collection_data: Dict[str, Any], item_path: List[int]) -> Optional[Dict[str, Any]]:
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


def iter_request_items(items: List[Dict[str, Any]], folder: str = "") -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "request" in item:
            request = item.get("request") or {}
            flattened.append(
                {
                    "item": item,
                    "name": str(item.get("name", "")),
                    "folder": folder,
                    "method": str(request.get("method", "")).upper(),
                }
            )
            continue
        children = item.get("item")
        if isinstance(children, list):
            next_folder = str(item.get("name", ""))
            flattened.extend(iter_request_items(children, next_folder))
    return flattened


def find_item_fallback(collection_data: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = collection_data.get("item")
    if not isinstance(items, list):
        return None

    candidates = iter_request_items(items)
    name = str(result.get("name", ""))
    method = str(result.get("method", "")).upper()
    folder = str(result.get("folder", ""))

    exact = [
        row
        for row in candidates
        if row["name"] == name and row["method"] == method and row["folder"] == folder
    ]
    if len(exact) == 1:
        return cast(Optional[Dict[str, Any]], exact[0]["item"])

    loose = [row for row in candidates if row["name"] == name and row["method"] == method]
    if len(loose) == 1:
        return cast(Optional[Dict[str, Any]], loose[0]["item"])
    return None


def collect_report_item_paths(report: Dict[str, Any]) -> Set[Tuple[int, ...]]:
    path_set: Set[Tuple[int, ...]] = set()
    for result in report.get("results", []):
        path = result.get("item_path")
        if isinstance(path, list) and path and all(isinstance(i, int) and i >= 0 for i in path):
            path_set.add(tuple(path))
    return path_set


def prune_collection_to_paths(collection_data: Dict[str, Any], selected_paths: Set[Tuple[int, ...]]) -> Dict[str, Any]:
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


def remove_excluded_items(collection_data: Dict[str, Any], manual_exclusions: List[str]) -> int:
    excluded = set(normalize_manual_exclusions(manual_exclusions))
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
                key = build_exclusion_key(
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


def append_manual_cases_to_collection(
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

    folder_name = str(default_folder).strip() or default_folder
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
        case = normalize_manual_case(raw, folder_name)
        if not case.get("name") or not case.get("url"):
            continue

        method = str(case.get("method") or "GET").strip().upper() or "GET"
        url = str(case.get("url") or "").strip()
        case_name = str(case.get("name") or "").strip()
        raw_request_info = case.get("request_info")
        request_info: Dict[str, Any] = raw_request_info if isinstance(raw_request_info, dict) else {}
        raw_headers = request_info.get("headers")
        headers: Dict[str, Any] = raw_headers if isinstance(raw_headers, dict) else {}
        if not include_auth:
            headers = strip_auth_headers(headers)
        raw_params = request_info.get("params")
        params: Dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        body = request_info.get("body")
        body_mode = request_info.get("body_mode")
        body_data = request_info.get("body_data")

        request_obj = {
            "method": method,
            "header": [],
            "url": {"raw": url},
        }

        set_request_url(request_obj, url, params)
        set_request_headers(request_obj, headers)
        set_request_body(request_obj, body, body_mode=body_mode, body_data=body_data)

        children.append({"name": case_name, "request": request_obj, "response": []})
        appended += 1

    return appended

# ---------------------------------------------------------------------------
# Collection 预览项提取（原 collection_handler）
# ---------------------------------------------------------------------------

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

    raw_query_list = url_obj.get("query")
    query_list: List[Any] = raw_query_list if isinstance(raw_query_list, list) else []
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


def extract_collection_preview_items(
    collection_data: Dict[str, Any], max_items: int
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    root_items = collection_data.get("item")
    if not isinstance(root_items, list):
        return result

    def walk(items: List[Any], folder_chain: List[str], path_prefix: List[int]) -> None:
        for index, item in enumerate(items):
            if len(result) >= max_items:
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
                result.append(
                    {
                        "index": len(result),
                        "name": name,
                        "folder": folder,
                        "method": method,
                        "url": url,
                        "item_path": current_path,
                        "item_path_text": ".".join(str(x) for x in current_path),
                    }
                )
                continue

            children = item.get("item")
            if isinstance(children, list):
                walk(children, folder_chain + [name], current_path)

    walk(root_items, [], [])
    logger.info(
        "collection preview extracted",
        extra={
            "event": "handler.collection.preview.extracted",
            "preview_count": len(result),
            "max_items": max_items,
        },
    )
    return result


# ---------------------------------------------------------------------------
# Ad-hoc 用例归一化（原 adhoc_handler / collection_handler）
# ---------------------------------------------------------------------------

def _parse_json_text(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc
    return value


def _normalize_folder_chain(folder: Any) -> List[str]:
    text = str(folder or "").strip()
    if not text:
        return []
    normalized = text.replace("\\", "/").replace("|", "/").strip("/")
    return [part.strip() for part in normalized.split("/") if part.strip()]


def _get_or_create_folder(
    items: List[Dict[str, Any]], folder_chain: List[str]
) -> List[Dict[str, Any]]:
    current_items = items
    for folder_name in folder_chain:
        target = None
        for item in current_items:
            if (
                isinstance(item, dict)
                and "request" not in item
                and str(item.get("name") or "") == folder_name
            ):
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


def normalize_adhoc_case(
    raw: Dict[str, Any], index: int, base_url: Optional[str]
) -> Dict[str, Any]:
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
            raise ValueError(
                f"第 {index + 1} 条接口变量 URL 仅支持 {{baseUrl}} 或 {{base_url}}"
            )
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

    # 解析可配置结果判定扩展字段
    x_success_err_codes = raw.get("x_success_err_codes")
    if x_success_err_codes is not None:
        x_success_err_codes = str(x_success_err_codes).strip() or None

    x_success_messages = raw.get("x_success_messages")
    if x_success_messages is not None:
        x_success_messages = str(x_success_messages).strip() or None

    x_enable_err_code = raw.get("x_enable_err_code_judgment")
    if x_enable_err_code is not None and not isinstance(x_enable_err_code, bool):
        x_enable_err_code = str(x_enable_err_code).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    x_enable_message = raw.get("x_enable_message_judgment")
    if x_enable_message is not None and not isinstance(x_enable_message, bool):
        x_enable_message = str(x_enable_message).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    logger.info(
        "adhoc case normalized",
        extra={
            "event": "handler.collection.adhoc_case.normalized",
            "case_index": index,
            "method": method,
            "has_base_url": bool(base_url),
        },
    )
    result: Dict[str, Any] = {
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

    # 仅在存在时写入 x_* 扩展字段
    if x_success_err_codes is not None:
        result["x_success_err_codes"] = x_success_err_codes
    if x_success_messages is not None:
        result["x_success_messages"] = x_success_messages
    if x_enable_err_code is not None:
        result["x_enable_err_code_judgment"] = x_enable_err_code
    if x_enable_message is not None:
        result["x_enable_message_judgment"] = x_enable_message

    return result


def build_adhoc_collection(
    cases: List[Dict[str, Any]], collection_name: str, base_url: Optional[str]
) -> Dict[str, Any]:
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
        # 写入可配置结果判定扩展字段（x_* 系列）
        if case.get("x_success_err_codes") is not None:
            request_obj["x_success_err_codes"] = case["x_success_err_codes"]
        if case.get("x_success_messages") is not None:
            request_obj["x_success_messages"] = case["x_success_messages"]
        if case.get("x_enable_err_code_judgment") is not None:
            request_obj["x_enable_err_code_judgment"] = case["x_enable_err_code_judgment"]
        if case.get("x_enable_message_judgment") is not None:
            request_obj["x_enable_message_judgment"] = case["x_enable_message_judgment"]

        set_request_url(request_obj, case["url"], case["params"])
        set_request_headers(request_obj, case["headers"])
        set_request_body(
            request_obj,
            case.get("body_data"),
            body_mode=case.get("body_mode"),
            body_data=case.get("body_data"),
        )

        item_node = {"name": case["name"], "request": request_obj, "response": []}
        folder_chain = _normalize_folder_chain(case.get("folder"))
        parent_items = _get_or_create_folder(root_items, folder_chain)
        parent_items.append(item_node)

    logger.info(
        "adhoc collection built",
        extra={
            "event": "handler.collection.adhoc_collection.built",
            "collection_name": collection_name,
            "case_count": len(cases),
            "has_base_url": bool(base_url),
        },
    )
    return collection


__all__ = [
    "item_by_path",
    "find_item_fallback",
    "iter_request_items",
    "collect_report_item_paths",
    "prune_collection_to_paths",
    "append_manual_cases_to_collection",
    "remove_excluded_items",
    "extract_collection_preview_items",
    "normalize_adhoc_case",
    "build_adhoc_collection",
]

