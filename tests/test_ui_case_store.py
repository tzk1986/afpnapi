"""UI 用例存储服务单元测试。"""

import json
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from postman_api_tester.services.ui_case_store import UiCaseStore


@pytest.fixture  # type: ignore[untyped-decorator]
def store() -> Generator[UiCaseStore, None, None]:
    """创建临时目录的用例存储。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield UiCaseStore(cases_dir=Path(tmp_dir))


class TestCreateCase:
    """创建用例测试。"""

    def test_create_basic_case(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "测试用例", "base_url": "https://example.com"})
        assert case_id
        case = store.get_case(case_id)
        assert case is not None
        assert case["name"] == "测试用例"
        assert case["base_url"] == "https://example.com"

    def test_create_with_custom_id(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"id": "custom-id", "name": "自定义ID"})
        assert case_id == "custom-id"

    def test_create_with_steps(self, store: UiCaseStore) -> None:
        steps = [
            {"action": "click", "selector": "#btn", "value": ""},
            {"action": "type", "selector": "#input", "value": "hello"},
        ]
        case_id = store.create_case({"name": "有步骤", "steps": steps})
        case = store.get_case(case_id)
        assert case is not None
        assert len(case["steps"]) == 2

    def test_create_sets_timestamps(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "时间戳"})
        case = store.get_case(case_id)
        assert case is not None
        assert "created_at" in case
        assert "updated_at" in case


class TestListCases:
    """用例列表测试。"""

    def test_empty_list(self, store: UiCaseStore) -> None:
        cases = store.list_cases()
        assert cases == []

    def test_list_multiple(self, store: UiCaseStore) -> None:
        store.create_case({"name": "用例 A", "steps": [{"action": "click"}]})
        store.create_case({"name": "用例 B", "steps": [{"action": "type"}, {"action": "click"}]})
        cases = store.list_cases()
        assert len(cases) == 2
        names = {c["name"] for c in cases}
        assert "用例 A" in names
        assert "用例 B" in names

    def test_list_returns_summary(self, store: UiCaseStore) -> None:
        store.create_case({"name": "有步骤", "steps": [{"action": "click"}, {"action": "type"}]})
        cases = store.list_cases()
        assert len(cases) == 1
        assert cases[0]["step_count"] == 2
        # 列表不应包含完整 steps
        assert "steps" not in cases[0]


class TestGetCase:
    """获取用例测试。"""

    def test_get_existing(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "查找我", "description": "描述"})
        case = store.get_case(case_id)
        assert case is not None
        assert case["name"] == "查找我"
        assert case["description"] == "描述"

    def test_get_nonexistent(self, store: UiCaseStore) -> None:
        case = store.get_case("nonexistent")
        assert case is None


class TestUpdateCase:
    """更新用例测试。"""

    def test_update_name(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "原名"})
        result = store.update_case(case_id, {"name": "新名"})
        assert result is True
        case = store.get_case(case_id)
        assert case is not None
        assert case["name"] == "新名"

    def test_update_steps(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "更新步骤", "steps": [{"action": "click"}]})
        new_steps = [{"action": "type", "value": "new"}]
        store.update_case(case_id, {"steps": new_steps})
        case = store.get_case(case_id)
        assert case is not None
        assert len(case["steps"]) == 1
        assert case["steps"][0]["action"] == "type"

    def test_update_updates_timestamp(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "时间"})
        case_before = store.get_case(case_id)
        assert case_before is not None

        store.update_case(case_id, {"name": "更新后"})
        case_after = store.get_case(case_id)
        assert case_after is not None
        assert case_after["updated_at"] >= case_before["updated_at"]

    def test_update_nonexistent(self, store: UiCaseStore) -> None:
        result = store.update_case("nonexistent", {"name": "x"})
        assert result is False


class TestDeleteCase:
    """删除用例测试。"""

    def test_delete_existing(self, store: UiCaseStore) -> None:
        case_id = store.create_case({"name": "删除我"})
        result = store.delete_case(case_id)
        assert result is True
        assert store.get_case(case_id) is None

    def test_delete_nonexistent(self, store: UiCaseStore) -> None:
        result = store.delete_case("nonexistent")
        assert result is False

    def test_delete_removes_from_list(self, store: UiCaseStore) -> None:
        id1 = store.create_case({"name": "保留"})
        id2 = store.create_case({"name": "删除"})
        store.delete_case(id2)
        cases = store.list_cases()
        assert len(cases) == 1
        assert cases[0]["id"] == id1


class TestFilePersistence:
    """文件持久化测试。"""

    def test_data_survives_new_store_instance(self) -> None:
        """数据在新 store 实例中仍然存在。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir)
            store1 = UiCaseStore(cases_dir=path)
            store1.create_case({"id": "persist-test", "name": "持久化测试"})

            store2 = UiCaseStore(cases_dir=path)
            case = store2.get_case("persist-test")
            assert case is not None
            assert case["name"] == "持久化测试"

    def test_case_file_is_valid_json(self, store: UiCaseStore) -> None:
        """用例文件是有效的 JSON。"""
        store.create_case({"id": "json-test", "name": "JSON测试"})
        # 直接读取文件验证
        cases_dir = store._cases_dir
        file_path = cases_dir / "case_json-test.json"
        assert file_path.exists()
        data = json.loads(file_path.read_text(encoding="utf-8"))
        assert data["id"] == "json-test"
