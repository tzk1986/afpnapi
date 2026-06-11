"""report_meta_update_service 单元测试."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from postman_api_tester.services.report_meta_update_service import update_report_meta


# ---- fixtures / helpers ----


def _make_stub_reports_dir(tmp_path: Path) -> Path:
    """创建子目录以模拟真实路径格式（如 reports/rpt001/meta.json）."""
    subdir = tmp_path / "reports" / "subdir"
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir


def _build_services(
    subdir: Path, meta_filename: str = "meta.json", extra_meta: dict | None = None
):
    """构建默认 stub 服务函数并写入初始 meta 文件."""
    init_meta = {"title": "initial", "manual_cases": [], **dict(extra_meta or {})}
    meta_file = subdir / meta_filename
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(init_meta, ensure_ascii=False), encoding="utf-8")

    def find_report(_name: str) -> Dict[str, Any]:
        return {"meta_file": meta_filename}

    def get_lock(report_name: str):
        import threading
        return threading.Lock()

    def invalidate_cache() -> None:
        invalidate_cache.called = True  # type: ignore[attr-defined]

    invalidate_cache.called = False  # type: ignore[attr-defined]

    return find_report, get_lock, invalidate_cache


# ---- happy path ----


def test_update_adds_field(tmp_path: Path) -> None:
    """验证 updater 可以添加新字段并持久化到磁盘."""
    subdir = _make_stub_reports_dir(tmp_path)
    find_report, get_lock, invalidate_cache = _build_services(subdir)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["new_key"] = "added"
        return meta

    result = update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    assert result["new_key"] == "added"
    assert result["title"] == "initial"

    persisted = json.loads((subdir / "meta.json").read_text(encoding="utf-8"))
    assert persisted["new_key"] == "added"
    assert invalidate_cache.called  # type: ignore[attr-defined]


def test_update_modifies_existing_field(tmp_path: Path) -> None:
    """验证 updater 可以修改已有字段."""
    subdir = _make_stub_reports_dir(tmp_path)
    find_report, get_lock, invalidate_cache = _build_services(subdir)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["title"] = "updated title"
        return meta

    result = update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    assert result["title"] == "updated title"
    persisted = json.loads((subdir / "meta.json").read_text(encoding="utf-8"))
    assert persisted["title"] == "updated title"


def test_update_manual_cases_list_preserved(tmp_path: Path) -> None:
    """验证手动用例列表在更新中保持不变."""
    subdir = _make_stub_reports_dir(tmp_path)
    init_meta = {"manual_cases": [{"id": 1}], "manual_exclusions": [{"id": 2}]}
    find_report, get_lock, invalidate_cache = _build_services(subdir, extra_meta=init_meta)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["extra"] = True
        return meta

    result = update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    assert result["manual_cases"] == [{"id": 1}]
    assert result["manual_exclusions"] == [{"id": 2}]


# ---- default lists ----


def test_default_manual_cases_when_missing(tmp_path: Path) -> None:
    """当 meta 中没有 manual_cases 时自动初始化为空列表."""
    subdir = _make_stub_reports_dir(tmp_path)
    init_meta = {"title": "no list"}
    find_report, get_lock, invalidate_cache = _build_services(subdir, extra_meta=init_meta)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["manual_cases"].append({"id": 99})
        return meta

    result = update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    assert result["manual_cases"] == [{"id": 99}]


def test_default_manual_exclusions_when_not_list(tmp_path: Path) -> None:
    """当 manual_exclusions 不是列表时（如被意外设为字符串），重置为空列表."""
    subdir = _make_stub_reports_dir(tmp_path)
    init_meta = {"manual_exclusions": "not-a-list"}
    find_report, get_lock, invalidate_cache = _build_services(subdir, extra_meta=init_meta)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["manual_exclusions"].append({"x": 1})
        return meta

    result = update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    assert result["manual_exclusions"] == [{"x": 1}]


# ---- error paths ----


def test_missing_meta_file_raises(tmp_path: Path) -> None:
    """报告记录中缺少 meta_file 时抛出 ValueError."""
    subdir = _make_stub_reports_dir(tmp_path)

    def find_report(_name: str) -> Dict[str, Any]:
        return {}  # 没有 meta_file key

    def get_lock(report_name: str):
        import threading
        return threading.Lock()

    def invalidate_cache() -> None:
        pass

    with pytest.raises(ValueError, match="报告缺少 meta_file"):
        update_report_meta(
            report_name="rpt1",
            updater=lambda m: m,
            reports_dir=subdir,
            get_report_write_lock=get_lock,
            find_report=find_report,
            invalidate_reports_cache=invalidate_cache,
        )


def test_empty_meta_file_string_raises(tmp_path: Path) -> None:
    """meta_file 为空字符串时同样触发 ValueError."""
    subdir = _make_stub_reports_dir(tmp_path)

    def find_report(_name: str) -> Dict[str, Any]:
        return {"meta_file": ""}

    def get_lock(report_name: str):
        import threading
        return threading.Lock()

    def invalidate_cache() -> None:
        pass

    with pytest.raises(ValueError, match="报告缺少 meta_file"):
        update_report_meta(
            report_name="rpt1",
            updater=lambda m: m,
            reports_dir=subdir,
            get_report_write_lock=get_lock,
            find_report=find_report,
            invalidate_reports_cache=invalidate_cache,
        )


def test_meta_file_whitespace_only_raises(tmp_path: Path) -> None:
    """meta_file 仅含空白字符时（经 strip 后为空）触发 ValueError."""
    subdir = _make_stub_reports_dir(tmp_path)

    def find_report(_name: str) -> Dict[str, Any]:
        return {"meta_file": "   "}

    def get_lock(report_name: str):
        import threading
        return threading.Lock()

    def invalidate_cache() -> None:
        pass

    with pytest.raises(ValueError, match="报告缺少 meta_file"):
        update_report_meta(
            report_name="rpt1",
            updater=lambda m: m,
            reports_dir=subdir,
            get_report_write_lock=get_lock,
            find_report=find_report,
            invalidate_reports_cache=invalidate_cache,
        )


def test_nonexistent_meta_file_raises(tmp_path: Path) -> None:
    """元数据文件不在磁盘上时抛出 FileNotFoundError."""
    subdir = _make_stub_reports_dir(tmp_path)

    def find_report(_name: str) -> Dict[str, Any]:
        return {"meta_file": "does-not-exist.json"}

    def get_lock(report_name: str):
        import threading
        return threading.Lock()

    def invalidate_cache() -> None:
        pass

    with pytest.raises(FileNotFoundError, match="元数据文件不存在"):
        update_report_meta(
            report_name="rpt1",
            updater=lambda m: m,
            reports_dir=subdir,
            get_report_write_lock=get_lock,
            find_report=find_report,
            invalidate_reports_cache=invalidate_cache,
        )


def test_updater_non_dict_returns_raises(tmp_path: Path) -> None:
    """updater 回调返回非 dict 时抛出 ValueError."""
    subdir = _make_stub_reports_dir(tmp_path)
    find_report, get_lock, invalidate_cache = _build_services(subdir)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        return "not a dict"  # type: ignore[return-value]

    with pytest.raises(ValueError, match="meta 更新回调必须返回 dict"):
        update_report_meta(
            report_name="rpt1",
            updater=updater,
            reports_dir=subdir,
            get_report_write_lock=get_lock,
            find_report=find_report,
            invalidate_reports_cache=invalidate_cache,
        )


# ---- atomicity / temp file ----


def test_tmp_file_not_persisted_on_success(tmp_path: Path) -> None:
    """成功更新后 .tmp 文件不应残留."""
    subdir = _make_stub_reports_dir(tmp_path)
    find_report, get_lock, invalidate_cache = _build_services(subdir)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["done"] = True
        return meta

    update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    tmp_files = list(subdir.glob("*.tmp"))
    assert not tmp_files, f"检测到残留临时文件: {tmp_files}"


def test_invalid_json_raises(tmp_path: Path) -> None:
    """元数据文件包含无效 JSON 时抛出 json.JSONDecodeError."""
    subdir = _make_stub_reports_dir(tmp_path)
    meta_file = subdir / "meta.json"
    meta_file.write_text("{broken json!!!}", encoding="utf-8")

    def find_report(_name: str) -> Dict[str, Any]:
        return {"meta_file": "meta.json"}

    def get_lock(report_name: str):
        import threading
        return threading.Lock()

    def invalidate_cache() -> None:
        pass

    with pytest.raises(json.JSONDecodeError):
        update_report_meta(
            report_name="rpt1",
            updater=lambda m: m,
            reports_dir=subdir,
            get_report_write_lock=get_lock,
            find_report=find_report,
            invalidate_reports_cache=invalidate_cache,
        )


def test_nested_meta_preserved(tmp_path: Path) -> None:
    """深层嵌套的 meta 结构在更新后保持不变."""
    subdir = _make_stub_reports_dir(tmp_path)
    nested = {"deep": {"level": {"items": [1, 2, 3]}}}
    init_meta = {"title": "nested", "config": nested}
    find_report, get_lock, invalidate_cache = _build_services(subdir, extra_meta=init_meta)

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["added"] = True
        return meta

    update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    persisted = json.loads((subdir / "meta.json").read_text(encoding="utf-8"))
    assert persisted["config"]["deep"]["level"]["items"] == [1, 2, 3]
    assert persisted["added"] is True


def test_custom_subdirectory_file(tmp_path: Path) -> None:
    """meta_file 指定子目录路径时能正确定位文件."""
    subdir = _make_stub_reports_dir(tmp_path)
    find_report, get_lock, invalidate_cache = _build_services(
        subdir, meta_filename="data/report-meta.json", extra_meta={"key": "val"}
    )

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        meta["key"] = "updated-val"
        return meta

    update_report_meta(
        report_name="rpt1",
        updater=updater,
        reports_dir=subdir,
        get_report_write_lock=get_lock,
        find_report=find_report,
        invalidate_reports_cache=invalidate_cache,
    )

    actual = subdir / "data" / "report-meta.json"
    assert actual.exists()
    persisted = json.loads(actual.read_text(encoding="utf-8"))
    assert persisted["key"] == "updated-val"
