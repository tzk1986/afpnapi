"""report_manual_case_service 单元测试."""

import logging
from typing import Any, Callable, Dict, Generator, List

import pytest

from postman_api_tester.services.report_manual_case_service import (
    add_manual_case,
    delete_manual_case,
    set_case_exclusion,
    update_manual_case,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def caplog_fixture(caplog: pytest.LogCaptureFixture) -> Generator[pytest.LogCaptureFixture, None, None]:
    """提供日志捕获 fixture."""
    caplog.set_level(logging.INFO, logger="postman_api_tester.services.report_manual_case_service")
    yield caplog


# ---- 辅助工厂 ----


def _make_mock_update_report_meta() -> "Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]]":
    """返回一个默认 meta 字典，通过 updater 可变引用共享状态."""
    meta_holder: Dict[str, Any] = {"manual_cases": [], "manual_exclusions": []}

    def update_report_meta(
        _report_name: str, updater: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> Dict[str, Any]:
        return updater(meta_holder)

    return update_report_meta, meta_holder  # type: ignore[return-value]


def _identity_normalize(payload: Dict[str, Any], folder: str) -> Dict[str, Any]:
    """恒等归一化（仅补 folder）."""
    result = dict(payload)
    result.setdefault("folder", folder)
    return result


def _identity_create_id() -> str:
    return "auto-generated-id"


def _exclusion_key(case: Dict[str, Any]) -> str:
    return f"{case.get('folder', '')}:{case.get('name', '')}"


def _normalize_exclusions(exclusions: List[str]) -> List[str]:
    return [str(x).strip() for x in exclusions if x]


def _normalize_exclusion_key(key: str) -> str:
    return key.strip().lower()


# ============================================================
# add_manual_case
# ============================================================


class TestAddManualCase:
    def test_add_success(self) -> None:
        """正常添加用例."""
        update_fn, meta = _make_mock_update_report_meta()
        result = add_manual_case(
            report_name="report_1",
            payload={"name": "Test Case 1", "url": "https://api.example.com/test"},
            enable_manual_cases=True,
            default_folder_name="default",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert result["case"]["id"] == "auto-generated-id"
        assert result["case"]["name"] == "Test Case 1"
        assert result["case"]["url"] == "https://api.example.com/test"
        assert len(result["manual_cases"]) == 1

    def test_add_with_preassigned_id(self) -> None:
        """payload 已包含 id 时不覆盖."""
        update_fn, meta = _make_mock_update_report_meta()
        result = add_manual_case(
            report_name="r1",
            payload={"id": "custom-001", "name": "C", "url": "http://x"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert result["case"]["id"] == "custom-001"

    def test_add_auto_timestamp(self) -> None:
        """未提供 created_at 时自动生成."""
        update_fn, meta = _make_mock_update_report_meta()
        result = add_manual_case(
            report_name="r1",
            payload={"name": "C", "url": "http://x"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert "created_at" in result["case"]

    def test_add_preserves_provided_timestamp(self) -> None:
        """payload 已提供 created_at 时不覆盖."""
        ts = "2026-01-01T00:00:00"
        update_fn, meta = _make_mock_update_report_meta()
        result = add_manual_case(
            report_name="r1",
            payload={"name": "C", "url": "http://x", "created_at": ts},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert result["case"]["created_at"] == ts

    def test_add_folder_from_payload(self) -> None:
        """使用 payload 中的 folder."""
        update_fn, meta = _make_mock_update_report_meta()
        result = add_manual_case(
            report_name="r1",
            payload={"name": "C", "url": "http://x", "folder": "my-folder"},
            enable_manual_cases=True,
            default_folder_name="default",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert result["case"]["folder"] == "my-folder"

    def test_add_folder_fallback_to_default(self) -> None:
        """folder 缺失时使用默认值."""
        update_fn, meta = _make_mock_update_report_meta()
        result = add_manual_case(
            report_name="r1",
            payload={"name": "C", "url": "http://x"},
            enable_manual_cases=True,
            default_folder_name="fallback",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert result["case"]["folder"] == "fallback"

    def test_add_disabled_raises(self) -> None:
        """未启用 manual_cases 时抛出 ValueError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="未启用人工用例能力"):
            add_manual_case(
                report_name="r1",
                payload={},
                enable_manual_cases=False,
                default_folder_name="d",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
                create_id=_identity_create_id,
            )

    def test_add_missing_name_raises(self) -> None:
        """name 为空时抛出 ValueError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="name 不能为空"):
            add_manual_case(
                report_name="r1",
                payload={"url": "http://x"},
                enable_manual_cases=True,
                default_folder_name="d",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
                create_id=_identity_create_id,
            )

    def test_add_empty_string_name_raises(self) -> None:
        """name 为空字符串时也抛错."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="name 不能为空"):
            add_manual_case(
                report_name="r1",
                payload={"name": "", "url": "http://x"},
                enable_manual_cases=True,
                default_folder_name="d",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
                create_id=_identity_create_id,
            )

    def test_add_missing_url_raises(self) -> None:
        """url 为空时抛出 ValueError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="url 不能为空"):
            add_manual_case(
                report_name="r1",
                payload={"name": "C"},
                enable_manual_cases=True,
                default_folder_name="d",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
                create_id=_identity_create_id,
            )

    def test_add_multiple_cases_accumulate(self) -> None:
        """多次添加后列表累积."""
        update_fn, meta = _make_mock_update_report_meta()
        for i in range(3):
            add_manual_case(
                report_name="r1",
                payload={"name": f"C{i}", "url": f"http://x{i}"},
                enable_manual_cases=True,
                default_folder_name="f",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
                create_id=lambda vals=[i]: f"id-{vals[0]}",
            )
        assert len(meta["manual_cases"]) == 3

    def test_add_filters_non_dict_in_existing_cases(self) -> None:
        """meta 中已有非 dict 元素时会被过滤."""
        update_fn, meta = _make_mock_update_report_meta()
        meta["manual_cases"].append("garbage")
        add_manual_case(
            report_name="r1",
            payload={"name": "C", "url": "http://x"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert all(isinstance(c, dict) for c in meta["manual_cases"])
        assert len(meta["manual_cases"]) == 1

    def test_add_logs_event(self, caplog_fixture: pytest.LogCaptureFixture) -> None:
        """验证添加了日志事件."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"name": "C", "url": "http://x"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        assert "manual case added" in caplog_fixture.text


# ============================================================
# update_manual_case
# ============================================================


class TestUpdateManualCase:
    def test_update_success(self) -> None:
        """正常更新已有用例."""
        update_fn, meta = _make_mock_update_report_meta()
        # 先添加一个用例
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "Old", "url": "http://old"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        result = update_manual_case(
            report_name="r1",
            case_id="c1",
            payload={"name": "New"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        assert result["case"]["name"] == "New"
        assert result["case"]["url"] == "http://old"
        assert result["case"]["id"] == "c1"

    def test_update_preserves_other_fields(self) -> None:
        """更新只合并 payload 字段，其他字段保留."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u", "status": "pending"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        update_manual_case(
            report_name="r1",
            case_id="c1",
            payload={"name": "Updated"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        entry = meta["manual_cases"][0]
        assert entry["name"] == "Updated"
        assert entry["url"] == "http://u"
        assert entry["status"] == "pending"

    def test_update_not_found_raises(self) -> None:
        """更新不存在的 case_id 时抛出 FileNotFoundError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(FileNotFoundError, match="未找到指定人工用例"):
            update_manual_case(
                report_name="r1",
                case_id="nonexistent",
                payload={"name": "X"},
                enable_manual_cases=True,
                default_folder_name="f",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
            )

    def test_update_disabled_raises(self) -> None:
        """未启用时抛出 ValueError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="未启用人工用例能力"):
            update_manual_case(
                report_name="r1",
                case_id="c1",
                payload={"name": "X"},
                enable_manual_cases=False,
                default_folder_name="f",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
            )

    def test_update_empty_case_id_raises(self) -> None:
        """case_id 为空字符串时抛错."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="case_id 不能为空"):
            update_manual_case(
                report_name="r1",
                case_id="",
                payload={"name": "X"},
                enable_manual_cases=True,
                default_folder_name="f",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
            )

    def test_update_none_case_id_raises(self) -> None:
        """case_id 为 None 时转化为空串后抛错."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="case_id 不能为空"):
            update_manual_case(
                report_name="r1",
                case_id=None,
                payload={"name": "X"},
                enable_manual_cases=True,
                default_folder_name="f",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
            )

    def test_update_strips_whitespace_case_id(self) -> None:
        """case_id 去空白后匹配（payload 中 id 无空白，更新用含空白 case_id）."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        result = update_manual_case(
            report_name="r1",
            case_id="  c1  ",
            payload={"name": "Updated"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        assert result["case"]["name"] == "Updated"

    def test_update_case_id_types_are_compared_as_str(self) -> None:
        """数字型 id 与字符串比较时正确匹配."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": 123, "name": "N", "url": "http://u"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        result = update_manual_case(
            report_name="r1",
            case_id="123",
            payload={"name": "Updated"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        assert result["case"]["name"] == "Updated"

    def test_update_other_cases_unchanged(self) -> None:
        """更新一个用例不影响其他用例."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "a", "name": "A", "url": "http://a"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        add_manual_case(
            report_name="r1",
            payload={"id": "b", "name": "B", "url": "http://b"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        update_manual_case(
            report_name="r1",
            case_id="a",
            payload={"name": "A-updated"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        b_entry = [c for c in meta["manual_cases"] if c["id"] == "b"][0]
        assert b_entry["name"] == "B"

    def test_update_with_folder_change(self) -> None:
        """更新时修改 folder 字段，归一化会生效."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u"},
            enable_manual_cases=True,
            default_folder_name="old-f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        update_manual_case(
            report_name="r1",
            case_id="c1",
            payload={"folder": "new-f"},
            enable_manual_cases=True,
            default_folder_name="old-f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        assert meta["manual_cases"][0]["folder"] == "new-f"

    def test_update_logs_event(self, caplog_fixture: pytest.LogCaptureFixture) -> None:
        """验证更新了日志事件."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        update_manual_case(
            report_name="r1",
            case_id="c1",
            payload={"name": "X"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
        )
        assert "manual case updated" in caplog_fixture.text


# ============================================================
# delete_manual_case
# ============================================================


class TestDeleteManualCase:
    def test_delete_success(self) -> None:
        """正常删除用例."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        result = delete_manual_case(
            report_name="r1",
            case_id="c1",
            enable_manual_cases=True,
            manual_case_exclusion_key=_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert result["manual_cases"] == []
        assert meta["manual_cases"] == []

    def test_delete_removes_matching_exclusion(self) -> None:
        """删除时同步移除对应的 exclusion key."""
        update_fn, meta = _make_mock_update_report_meta()
        meta["manual_exclusions"] = ["f:N", "other-key"]
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u", "folder": "f"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        delete_manual_case(
            report_name="r1",
            case_id="c1",
            enable_manual_cases=True,
            manual_case_exclusion_key=_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert "f:N" not in meta["manual_exclusions"]
        assert "other-key" in meta["manual_exclusions"]

    def test_delete_not_found_raises(self) -> None:
        """删除不存在的 case_id 时抛出 FileNotFoundError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(FileNotFoundError, match="未找到指定人工用例"):
            delete_manual_case(
                report_name="r1",
                case_id="missing",
                enable_manual_cases=True,
                manual_case_exclusion_key=_exclusion_key,
                normalize_manual_exclusions=_normalize_exclusions,
                update_report_meta=update_fn,
            )

    def test_delete_disabled_raises(self) -> None:
        """未启用时抛出 ValueError."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="未启用人工用例能力"):
            delete_manual_case(
                report_name="r1",
                case_id="c1",
                enable_manual_cases=False,
                manual_case_exclusion_key=_exclusion_key,
                normalize_manual_exclusions=_normalize_exclusions,
                update_report_meta=update_fn,
            )

    def test_delete_empty_case_id_raises(self) -> None:
        """空 case_id 抛错."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="case_id 不能为空"):
            delete_manual_case(
                report_name="r1",
                case_id="",
                enable_manual_cases=True,
                manual_case_exclusion_key=_exclusion_key,
                normalize_manual_exclusions=_normalize_exclusions,
                update_report_meta=update_fn,
            )

    def test_delete_multiple_keeps_others(self) -> None:
        """删除其中一个，其余保留."""
        update_fn, meta = _make_mock_update_report_meta()
        for i in range(3):
            add_manual_case(
                report_name="r1",
                payload={"id": f"c{i}", "name": f"N{i}", "url": f"http://{i}"},
                enable_manual_cases=True,
                default_folder_name="f",
                normalize_manual_case=_identity_normalize,
                update_report_meta=update_fn,
                create_id=lambda vals=[i]: f"id-{vals[0]}",
            )
        delete_manual_case(
            report_name="r1",
            case_id="c1",
            enable_manual_cases=True,
            manual_case_exclusion_key=_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert len(meta["manual_cases"]) == 2
        ids = {c["id"] for c in meta["manual_cases"]}
        assert ids == {"c0", "c2"}

    def test_delete_logs_event(self, caplog_fixture: pytest.LogCaptureFixture) -> None:
        """验证删除时记录了日志事件."""
        update_fn, meta = _make_mock_update_report_meta()
        add_manual_case(
            report_name="r1",
            payload={"id": "c1", "name": "N", "url": "http://u"},
            enable_manual_cases=True,
            default_folder_name="f",
            normalize_manual_case=_identity_normalize,
            update_report_meta=update_fn,
            create_id=_identity_create_id,
        )
        delete_manual_case(
            report_name="r1",
            case_id="c1",
            enable_manual_cases=True,
            manual_case_exclusion_key=_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert "manual case deleted" in caplog_fixture.text


# ============================================================
# set_case_exclusion
# ============================================================


class TestSetCaseExclusion:
    def test_add_exclusion(self) -> None:
        """添加排除标记."""
        update_fn, meta = _make_mock_update_report_meta()
        result = set_case_exclusion(
            report_name="r1",
            exclusion_key="f:N",
            excluded=True,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert "f:n" in result["manual_exclusions"]
        assert "f:n" in meta["manual_exclusions"]

    def test_remove_exclusion(self) -> None:
        """取消排除标记."""
        update_fn, meta = _make_mock_update_report_meta()
        meta["manual_exclusions"] = ["f:n", "other"]
        result = set_case_exclusion(
            report_name="r1",
            exclusion_key="f:N",
            excluded=False,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert "f:n" not in result["manual_exclusions"]
        assert "other" in meta["manual_exclusions"]

    def test_add_duplicate_exclusion_no_effect(self) -> None:
        """重复添加同一 key 不会重复."""
        update_fn, meta = _make_mock_update_report_meta()
        meta["manual_exclusions"] = ["key-a"]
        set_case_exclusion(
            report_name="r1",
            exclusion_key="key-a",
            excluded=True,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert meta["manual_exclusions"].count("key-a") == 1

    def test_empty_exclusion_key_raises(self) -> None:
        """空 exclusion_key 抛错."""
        update_fn, meta = _make_mock_update_report_meta()
        with pytest.raises(ValueError, match="exclusion_key 不能为空"):
            set_case_exclusion(
                report_name="r1",
                exclusion_key="",
                excluded=True,
                normalize_exclusion_key=_normalize_exclusion_key,
                normalize_manual_exclusions=_normalize_exclusions,
                update_report_meta=update_fn,
            )

    def test_normalized_key_lowercase(self) -> None:
        """key 经 normalize 后会转小写并去空白."""
        update_fn, meta = _make_mock_update_report_meta()
        set_case_exclusion(
            report_name="r1",
            exclusion_key="  My-Key  ",
            excluded=True,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert "my-key" in meta["manual_exclusions"]

    def test_sorted_result(self) -> None:
        """结果列表按字母排序."""
        update_fn, meta = _make_mock_update_report_meta()
        for key in ["c", "a", "b"]:
            set_case_exclusion(
                report_name="r1",
                exclusion_key=key,
                excluded=True,
                normalize_exclusion_key=_normalize_exclusion_key,
                normalize_manual_exclusions=_normalize_exclusions,
                update_report_meta=update_fn,
            )
        assert meta["manual_exclusions"] == ["a", "b", "c"]

    def test_initially_empty_list(self) -> None:
        """从空列表开始正常工作."""
        update_fn, meta = _make_mock_update_report_meta()
        meta["manual_exclusions"] = []
        result = set_case_exclusion(
            report_name="r1",
            exclusion_key="k1",
            excluded=True,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert result["manual_exclusions"] == ["k1"]

    def test_discard_absent_key_no_effect(self) -> None:
        """移除不存在的 key 不报错且无变化."""
        update_fn, meta = _make_mock_update_report_meta()
        meta["manual_exclusions"] = ["other"]
        result = set_case_exclusion(
            report_name="r1",
            exclusion_key="absent",
            excluded=False,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert result["manual_exclusions"] == ["other"]

    def test_logs_event(self, caplog_fixture: pytest.LogCaptureFixture) -> None:
        """验证排除了日志事件."""
        update_fn, meta = _make_mock_update_report_meta()
        set_case_exclusion(
            report_name="r1",
            exclusion_key="k1",
            excluded=True,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_exclusions,
            update_report_meta=update_fn,
        )
        assert "manual case exclusion changed" in caplog_fixture.text
