#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Collection query service smoke test.

楠岃瘉鐐癸細
1. item_path 鍙ǔ瀹氬畾浣嶈姹傝妭鐐?
2. fallback 鍙寜 name+method(+folder) 瀹氫綅
3. 鎸?selected_paths 瑁佸壀闆嗗悎淇濈暀姝ｇ‘灞傜骇
"""

from typing import Any, Dict

from postman_api_tester.services.report_collection_query_service import (
    collect_report_item_paths,
    find_item_fallback,
    item_by_path,
    prune_collection_to_paths,
)


def _collection() -> Dict[str, Any]:
    return {
        "item": [
            {
                "name": "FolderA",
                "item": [
                    {"name": "GetUser", "request": {"method": "GET", "url": {"raw": "/user"}}},
                    {"name": "CreateUser", "request": {"method": "POST", "url": {"raw": "/user"}}},
                ],
            },
            {
                "name": "FolderB",
                "item": [
                    {"name": "GetOrder", "request": {"method": "GET", "url": {"raw": "/order"}}},
                ],
            },
        ]
    }


def main() -> None:
    collection = _collection()

    node = item_by_path(collection, [0, 1])
    assert node is not None and node.get("name") == "CreateUser", node

    fallback = find_item_fallback(
        collection,
        {
            "name": "GetOrder",
            "method": "GET",
            "folder": "FolderB",
        },
    )
    assert fallback is not None and fallback.get("name") == "GetOrder", fallback

    report = {"results": [{"item_path": [0, 1]}, {"item_path": [1, 0]}]}
    selected_paths = collect_report_item_paths(report)
    pruned = prune_collection_to_paths(collection, selected_paths)

    folder_a_items = ((pruned.get("item") or [])[0]).get("item") or []
    folder_b_items = ((pruned.get("item") or [])[1]).get("item") or []

    assert len(folder_a_items) == 1 and folder_a_items[0].get("name") == "CreateUser", folder_a_items
    assert len(folder_b_items) == 1 and folder_b_items[0].get("name") == "GetOrder", folder_b_items

    print("collection-query-service-ok")


if __name__ == "__main__":
    main()

