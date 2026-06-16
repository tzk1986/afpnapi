"""collection_utils 单元测试。"""

from typing import Any, Dict, List

from postman_api_tester.utils.collection_utils import (
    extract_collection_preview_items,
    iter_request_items,
    item_by_path,
)


SAMPLE_COLLECTION: Dict[str, Any] = {
    "info": {"name": "test"},
    "item": [
        {
            "name": "folder1",
            "item": [
                {
                    "name": "req1",
                    "request": {"method": "GET", "url": {"raw": "https://example.com/api/1"}},
                },
                {
                    "name": "req2",
                    "request": {"method": "POST", "url": {"raw": "https://example.com/api/2"}},
                },
            ],
        },
        {
            "name": "req3",
            "request": {"method": "PUT", "url": {"raw": "https://example.com/api/3"}},
        },
    ],
}


class TestItemByPath:
    """item_by_path 测试。"""

    def test_root_level_item(self) -> None:
        """顶层请求通过路径访问。"""
        result = item_by_path(SAMPLE_COLLECTION, [1])
        assert result is not None
        assert result["name"] == "req3"

    def test_nested_item(self) -> None:
        """嵌套请求通过路径访问。"""
        result = item_by_path(SAMPLE_COLLECTION, [0, 0])
        assert result is not None
        assert result["name"] == "req1"

    def test_nested_second_item(self) -> None:
        """嵌套第二个请求。"""
        result = item_by_path(SAMPLE_COLLECTION, [0, 1])
        assert result is not None
        assert result["name"] == "req2"

    def test_invalid_path_returns_none(self) -> None:
        """无效路径返回 None。"""
        assert item_by_path(SAMPLE_COLLECTION, [5]) is None

    def test_empty_path_returns_none(self) -> None:
        """空路径返回 None。"""
        assert item_by_path(SAMPLE_COLLECTION, []) is None

    def test_non_list_path_returns_none(self) -> None:
        """非列表路径返回 None。"""
        assert item_by_path(SAMPLE_COLLECTION, "invalid") is None  # type: ignore[arg-type]

    def test_folder_without_request_returns_none(self) -> None:
        """文件夹（无 request 字段）返回 None。"""
        result = item_by_path(SAMPLE_COLLECTION, [0])
        assert result is None

    def test_missing_collection_items(self) -> None:
        """Collection 缺少 item 返回 None。"""
        assert item_by_path({"info": {}}, [0]) is None


class TestIterRequestItems:
    """iter_request_items 测试。"""

    def test_flat_requests(self) -> None:
        """扁平请求列表。"""
        items = [{"name": "req1", "request": {}}, {"name": "req2", "request": {}}]
        result = iter_request_items(items)
        assert len(result) == 2

    def test_nested_folders(self) -> None:
        """嵌套文件夹展平。"""
        items = SAMPLE_COLLECTION["item"]
        result = iter_request_items(items)
        assert len(result) == 3

    def test_folder_name_in_result(self) -> None:
        """结果包含文件夹名。"""
        items = SAMPLE_COLLECTION["item"]
        result = iter_request_items(items)
        folders = [r.get("folder") for r in result]
        assert "folder1" in folders

    def test_empty_items(self) -> None:
        """空列表返回空。"""
        assert iter_request_items([]) == []


class TestExtractCollectionPreviewItems:
    """extract_collection_preview_items 测试。"""

    def test_basic_extraction(self) -> None:
        """基本提取功能。"""
        items = extract_collection_preview_items(SAMPLE_COLLECTION, max_items=100)
        assert len(items) == 3

    def test_item_has_name(self) -> None:
        """提取项包含名称。"""
        items = extract_collection_preview_items(SAMPLE_COLLECTION, max_items=100)
        names = [i.get("name") for i in items]
        assert "req1" in names
        assert "req2" in names
        assert "req3" in names

    def test_item_has_method(self) -> None:
        """提取项包含方法。"""
        items = extract_collection_preview_items(SAMPLE_COLLECTION, max_items=100)
        methods = [i.get("method") for i in items]
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods

    def test_max_items_limit(self) -> None:
        """max_items 限制生效。"""
        items = extract_collection_preview_items(SAMPLE_COLLECTION, max_items=2)
        assert len(items) <= 2

    def test_empty_collection(self) -> None:
        """空 Collection 返回空列表。"""
        items = extract_collection_preview_items({"info": {}, "item": []}, max_items=100)
        assert items == []

    def test_missing_item_field(self) -> None:
        """缺少 item 字段返回空列表。"""
        items = extract_collection_preview_items({"info": {}}, max_items=100)
        assert items == []
