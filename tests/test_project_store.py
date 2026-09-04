"""v1.39.0 S1.1 项目脚手架 store 层单测（N10）。

覆盖 v3 5.5 / v4 三.5 测试矩阵：原子写并发读完整、锁内 RMW 无丢失、
懒建目录（构造零副作用）、id 正则表驱动拒绝、未提交目录跳过、
路径穿越拒绝、删除四重防护、模板两源合并与 user 覆盖、source 标记。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict

import pytest

from postman_api_tester.services.project_store import (
    ProjectStore,
    ProjectTemplateStore,
)


def _mk_project(pid: str, **overrides: Any) -> Dict[str, Any]:
    project: Dict[str, Any] = {
        "schema_version": 1,
        "id": pid,
        "name": "示例项目",
        "status": "active",
        "metadata": {},
        "collections": [],
    }
    project.update(overrides)
    return project


# ---------- id 正则（G-18，表驱动 4 拒 + 接受） ----------


@pytest.mark.parametrize(
    "bad_id",
    [
        "../../etc",  # 穿越
        "..%2f..%2f",  # 编码穿越
        "proj_中文项目名",  # 中文
        "CON",  # Windows 保留名
        "NUL",
        "proj_A1B2C3D4E5F6",  # 大写不在 [a-z0-9]
        "proj_short",  # 过短
        "proj_" + "a" * 13,  # 超长
        "random1234567890",  # 无前缀
        "",
        "proj_a1b2c3d4e5f6/../x",
    ],
)
def test_invalid_project_id_rejected(bad_id: str) -> None:
    assert not ProjectStore.is_valid_project_id(bad_id)


def test_valid_project_id_accepted() -> None:
    assert ProjectStore.is_valid_project_id("proj_a1b2c3d4e5f6")
    assert ProjectStore.is_valid_project_id("proj_000000000000")


def test_generated_id_matches_whitelist_and_unique() -> None:
    store = ProjectStore(projects_dir=Path(".unused"))
    ids = {store.generate_project_id() for _ in range(200)}
    assert len(ids) == 200
    for pid in ids:
        assert ProjectStore.is_valid_project_id(pid)


@pytest.mark.parametrize(
    "bad_tid",
    ["tpl_x", "tpl_", "tpl_中文", "tpl_AbCd_01", "tpl_" + "a" * 33, "../tpl_ok", "tpl_ok/x"],
)
def test_invalid_template_id_rejected(bad_tid: str) -> None:
    assert not ProjectTemplateStore.is_valid_template_id(bad_tid)


def test_valid_template_id_accepted() -> None:
    assert ProjectTemplateStore.is_valid_template_id("tpl_api_basic")
    assert ProjectTemplateStore.is_valid_template_id("tpl_ab")


# ---------- 懒建目录（G-25） ----------


def test_store_construction_touches_no_filesystem(tmp_path: Path) -> None:
    missing = tmp_path / "not_created_yet"
    ProjectStore(projects_dir=missing)
    ProjectTemplateStore(builtin_dir=missing / "b", user_dir=missing / "u")
    assert not missing.exists()
    # 读接口同样不建目录
    store = ProjectStore(projects_dir=missing)
    assert store.list_projects() == []
    assert store.get_project("proj_a1b2c3d4e5f6") is None
    assert not missing.exists()


def test_save_project_lazy_creates_dir(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path / "projects")
    pid = store.generate_project_id()
    path = store.save_project(_mk_project(pid))
    assert path.is_file()
    assert path.name == "project.json"


# ---------- project.json CRUD / 未提交目录跳过（G-17） ----------


def test_get_save_roundtrip(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    pid = "proj_a1b2c3d4e5f6"
    store.save_project(_mk_project(pid, name="回读项目"))
    data = store.get_project(pid)
    assert data is not None and data["name"] == "回读项目"


def test_invalid_id_no_side_effect(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    assert store.get_project("../evil") is None
    assert store.delete_project("../evil") is False
    assert store.is_committed("../evil") is False


def test_uncommitted_dir_skipped_by_list(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    pid_ok = "proj_a1b2c3d4e5f6"
    store.save_project(_mk_project(pid_ok))
    # 手工拷入半成品目录（无 project.json）与损坏 json
    (tmp_path / "proj_deadbeef0000").mkdir()
    bad = tmp_path / "proj_ffffffffffff"
    bad.mkdir()
    (bad / "project.json").write_text("{broken", encoding="utf-8")
    listed = store.list_projects()
    assert [p["id"] for p in listed] == [pid_ok]
    # 垃圾目录未被删除（保守策略）
    assert (tmp_path / "proj_deadbeef0000").is_dir()


def test_delete_requires_committed(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    garbage = tmp_path / "proj_000000000000"
    garbage.mkdir()
    assert store.delete_project("proj_000000000000") is False
    assert garbage.is_dir()  # 未提交目录不许删
    store.save_project(_mk_project("proj_000000000000"))
    assert store.delete_project("proj_000000000000") is True
    assert not garbage.exists()


def test_prepare_rollback(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    pid = store.generate_project_id()
    proj_dir = store.prepare_new_project_dir(pid)
    store.write_project_json(pid, "tracing.json", {"rows": []})
    assert proj_dir.is_dir()
    with pytest.raises(FileExistsError):
        store.prepare_new_project_dir(pid)
    store.rollback_project_dir(pid)
    assert not proj_dir.exists()


# ---------- 相对路径守卫（G-32 使用期） ----------


@pytest.mark.parametrize(
    "bad_rel",
    ["", "..", "../outside.json", "/abs/x.json", "C:/x.json", "a/../../b.json"],
)
def test_resolve_project_path_rejects(tmp_path: Path, bad_rel: str) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    store.save_project(_mk_project("proj_a1b2c3d4e5f6"))
    with pytest.raises(ValueError):
        store.resolve_project_path("proj_a1b2c3d4e5f6", bad_rel)


def test_relative_files_roundtrip(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    pid = "proj_a1b2c3d4e5f6"
    store.write_project_json(pid, "collections/col_a1b2c3d4e5f6.json", {"info": {}})
    store.write_project_text(pid, "docs/README.md", "# hello {{project_name}}")
    assert store.read_project_json(pid, "collections/col_a1b2c3d4e5f6.json") == {
        "info": {}
    }
    assert (tmp_path / pid / "docs" / "README.md").read_text(
        encoding="utf-8"
    ) == "# hello {{project_name}}"
    assert store.delete_project_file(pid, "collections/col_a1b2c3d4e5f6.json") is True
    assert store.read_project_json(pid, "collections/col_a1b2c3d4e5f6.json") is None


# ---------- 并发：原子写读完整 + 锁内 RMW 无丢失 ----------


def test_concurrent_writers_reader_always_valid(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    pid = "proj_a1b2c3d4e5f6"
    store.save_project(_mk_project(pid, name="init"))
    errors: list = []
    stop = threading.Event()

    def writer(tag: int) -> None:
        try:
            for i in range(30):
                store.save_project(_mk_project(pid, name=f"w{tag}-{i}", seq=i))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    def reader() -> None:
        try:
            while not stop.is_set():
                data = store.get_project(pid)
                if data is not None and "name" not in data:  # pragma: no cover
                    errors.append(AssertionError("读到残缺对象"))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    threads.append(threading.Thread(target=reader))
    for t in threads:
        t.start()
    threads[0].join()
    stop.set()
    for t in threads:
        t.join()
    assert not errors
    final = store.get_project(pid)
    assert final is not None  # 文件始终是完整 JSON


def test_locked_read_modify_write_no_loss(tmp_path: Path) -> None:
    store = ProjectStore(projects_dir=tmp_path)
    pid = "proj_a1b2c3d4e5f6"
    store.save_project(_mk_project(pid, counters={}))

    def bump(tag: str) -> None:
        def mut(data: Dict[str, Any], tag: str = tag) -> Dict[str, Any]:
            data["counters"][tag] = data["counters"].get(tag, 0) + 1
            return data

        for _ in range(10):
            assert store.update_project(pid, mut) is not None

    threads = [threading.Thread(target=bump, args=(t,)) for t in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data = store.get_project(pid)
    assert data is not None
    assert data["counters"] == {"a": 10, "b": 10, "c": 10}


# ---------- 模板两源合并（v3 4.1 / G-33 存储面） ----------


def _mk_template(tid: str, **overrides: Any) -> Dict[str, Any]:
    tpl: Dict[str, Any] = {"id": tid, "name": tid, "version": "1.0.0", "files": []}
    tpl.update(overrides)
    return tpl


def _put_template(root: Path, dirname: str, payload: Dict[str, Any]) -> Path:
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    path = d / "template.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_template_builtin_only(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    _put_template(builtin, "api_basic", _mk_template("tpl_api_basic"))
    store = ProjectTemplateStore(builtin_dir=builtin, user_dir=tmp_path / "user")
    items = store.list_templates()
    assert [t["id"] for t in items] == ["tpl_api_basic"]
    assert items[0]["source"] == "builtin"
    assert store.get_template("tpl_api_basic")["source"] == "builtin"
    assert not (tmp_path / "user").exists()  # 读取不建 user 目录


def test_template_user_override_builtin(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    _put_template(builtin, "api_basic", _mk_template("tpl_api_basic", desc="内置"))
    store = ProjectTemplateStore(builtin_dir=builtin, user_dir=user)
    saved = store.save_user_template(_mk_template("tpl_api_basic", desc="用户版"))
    assert saved == user / "tpl_api_basic" / "template.json"  # 用户模板以 id 作目录名
    got = store.get_template("tpl_api_basic")
    assert got is not None
    assert got["source"] == "user" and got["desc"] == "用户版"
    items = store.list_templates()
    assert len(items) == 1 and items[0]["source"] == "user"
    assert store.builtin_template_exists("tpl_api_basic")
    assert store.user_template_path_exists("tpl_api_basic")


def test_template_corrupted_and_invalid_ids_skipped(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    _put_template(builtin, "good", _mk_template("tpl_good"))
    _put_template(builtin, "broken", {})  # 占位后覆写损坏内容
    (builtin / "broken" / "template.json").write_text("{nope", encoding="utf-8")
    _put_template(builtin, "evil", _mk_template("../evil"))  # 内容 id 非法
    _put_template(builtin, "upper", _mk_template("Tpl_Good"))  # 大写非法
    store = ProjectTemplateStore(builtin_dir=builtin, user_dir=tmp_path / "user")
    items = store.list_templates()
    assert [t["id"] for t in items] == ["tpl_good"]
    assert store.get_template("tpl_broken") is None
    assert store.get_template("../evil") is None
    assert store.builtin_template_exists("tpl_good") is True
    assert store.builtin_template_exists("Tpl_Good") is False
    with pytest.raises(ValueError):
        store.save_user_template(_mk_template("tpl_x"))  # 前缀后仅 1 字符 < {2,32}


def test_template_get_prefers_user_shortcut(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    _put_template(builtin, "a", _mk_template("tpl_aa"))
    _put_template(user, "b", _mk_template("tpl_bb"))
    store = ProjectTemplateStore(builtin_dir=builtin, user_dir=user)
    got = store.get_template("tpl_aa")
    assert got is not None and got["source"] == "builtin"
    assert store.get_template("tpl_missing") is None
    # 目录名 ≠ id（内置短名惯例）：id 以文件内容为权威
    assert got["id"] == "tpl_aa"
