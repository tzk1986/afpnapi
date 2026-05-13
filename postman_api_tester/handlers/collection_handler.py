"""Collection handler implementations for route-level orchestration."""

import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlsplit

from postman_api_tester.utils.request_builder import (
    set_request_body,
    set_request_headers,
    set_request_url,
)


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


def extract_collection_preview_items(collection_data: Dict[str, Any], max_items: int) -> List[Dict[str, Any]]:
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
    normalized = text.replace("\\", "/").replace("|", "/").strip("/")
    return [part.strip() for part in normalized.split("/") if part.strip()]


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
    text = str(name or "").strip()
    return bool(text) and bool(re.fullmatch(r"[?？\s_]+", text))


def _derive_case_name(raw_name: Any, method: str, url: str, index: int) -> str:
    text = str(raw_name or "").strip()
    if text and not _is_placeholder_case_name(text):
        return text

    raw_url = str(url or "").strip()
    if raw_url:
        if raw_url.startswith("{{baseUrl}}"):
            raw_url = raw_url[len("{{baseUrl}}") :] or "/"
        elif raw_url.startswith("{{base_url}}"):
            raw_url = raw_url[len("{{base_url}}") :] or "/"

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


def normalize_adhoc_case(raw: Dict[str, Any], index: int, base_url: Optional[str]) -> Dict[str, Any]:
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


def build_adhoc_collection(cases: List[Dict[str, Any]], collection_name: str, base_url: Optional[str]) -> Dict[str, Any]:
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
        set_request_url(request_obj, case["url"], case["params"])
        set_request_headers(request_obj, case["headers"])
        set_request_body(
            request_obj,
            case.get("body_data"),
            body_mode=case.get("body_mode"),
            body_data=case.get("body_data"),
        )

        item_node = {
            "name": case["name"],
            "request": request_obj,
            "response": [],
        }

        folder_chain = _normalize_folder_chain(case.get("folder"))
        parent_items = _get_or_create_folder(root_items, folder_chain)
        parent_items.append(item_node)

    return collection


def parse_selected_item_paths(raw: Any) -> List[List[int]]:
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
        raise ValueError("selected_item_paths 必须是数组")

    normalized: List[List[int]] = []
    seen = set()
    for item in data:
        if not isinstance(item, list) or not item:
            continue
        if not all(isinstance(index, int) and index >= 0 for index in item):
            raise ValueError("selected_item_paths 的每条路径必须是非负整数数组")
        key = tuple(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(list(item))
    return normalized


__all__ = [
    "extract_collection_preview_items",
    "normalize_adhoc_case",
    "build_adhoc_collection",
    "parse_selected_item_paths",
]

