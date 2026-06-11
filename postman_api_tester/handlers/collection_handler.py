"""Collection handler implementations for route-level orchestration."""

"""开发导读：
- 职责：处理 Collection 预览、ad-hoc case 归一化、ad-hoc collection 组装、选择路径解析。
- 入口：extract_collection_preview_items()、normalize_adhoc_case()、build_adhoc_collection()、parse_selected_item_paths()。
- 关系：ad-hoc 归一化与 collection 构建的实现已统一到 utils/collection_utils.py，
       本文件保留 parse_selected_item_paths() 的路由层职责。
"""

import json
import logging
from typing import Any, Dict, List

from postman_api_tester.utils.collection_utils import (
    build_adhoc_collection as build_adhoc_collection,
    extract_collection_preview_items as extract_collection_preview_items,
    normalize_adhoc_case as normalize_adhoc_case,
)

logger = logging.getLogger(__name__)


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
    logger.info(
        "selected item paths parsed",
        extra={
            "event": "handler.collection.selected_paths.parsed",
            "path_count": len(normalized),
        },
    )
    return normalized


__all__ = [
    "extract_collection_preview_items",
    "normalize_adhoc_case",
    "build_adhoc_collection",
    "parse_selected_item_paths",
]
