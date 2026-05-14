"""开发导读：
- 职责：按 item_path/回退规则在 collection 中定位接口节点。
- 入口：item_by_path()、find_item_fallback()、collect_report_item_paths() 等。
- 使用方：导出与重试相关服务，确保“报告结果 -> 集合节点”可追溯。
"""

import copy
from typing import Any, Dict, List, Optional, Set, Tuple


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
