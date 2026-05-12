"""Collection utility implementations used by export/query flows."""

import copy
from typing import Any, Dict, List, Optional, Set, Tuple

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
        return exact[0]["item"]

    loose = [row for row in candidates if row["name"] == name and row["method"] == method]
    if len(loose) == 1:
        return loose[0]["item"]
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

        method = case.get("method", "GET")
        url = case.get("url", "")
        request_info = case.get("request_info") if isinstance(case.get("request_info"), dict) else {}
        headers = request_info.get("headers") if isinstance(request_info.get("headers"), dict) else {}
        if not include_auth:
            headers = strip_auth_headers(headers)
        params = request_info.get("params") if isinstance(request_info.get("params"), dict) else {}
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

        children.append({"name": case.get("name", ""), "request": request_obj, "response": []})
        appended += 1

    return appended

__all__ = [
    "item_by_path",
    "find_item_fallback",
    "iter_request_items",
    "collect_report_item_paths",
    "prune_collection_to_paths",
    "append_manual_cases_to_collection",
    "remove_excluded_items",
]

