"""v1.39.0 S1.2 项目脚手架 service 层单测（N11）。

覆盖 v3 5.5 / v4 三.5：模板两源合并、占位符 _unresolved、manifest 双期校验、
创建异常回滚、schema 校验（enum 越界/必填）、G-30 对账三分支（含重启模拟）、
CAS 409（PRJ_306/PRJ_602）、history cap、secret 脱敏、集合增删与上限、
dangling 派生、A15 声明期校验。
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from postman_api_tester.services import project_service as ps
from postman_api_tester.services.project_service import (
    ProjectError,
    ProjectService,
)
from postman_api_tester.services.project_store import (
    ProjectStore,
    ProjectTemplateStore,
)


def _basic_template(**overrides: Any) -> Dict[str, Any]:
    tpl: Dict[str, Any] = {
        "schema_version": 1,
        "id": "tpl_api_basic",
        "name": "基础接口模板",
        "version": "1.0.0",
        "metadata_template": {
            "system": "{{system}}",
            "module": "{{module}}",
            "owner": "{{owner}}",
        },
        "variables": [
            {
                "key": "system",
                "label": "系统",
                "type": "enum",
                "required": True,
                "options": ["餐厅", "ESP"],
            },
            {"key": "module", "label": "模块", "type": "string", "required": True},
            {"key": "owner", "label": "负责人", "type": "string", "required": True},
        ],
        "files": [
            {
                "path": "docs/README.md",
                "content_template": "# {{project_name}}\nsys={{system}}\nextra={{jira_key}}",
                "render": True,
            },
            {
                "path": "tracing.json",
                "content_template": json.dumps(
                    {
                        "schema_version": 1,
                        "rows": [
                            {
                                "case_no": "C1",
                                "title": "扫码",
                                "convert_status": "automated",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                "render": False,
            },
            {
                "path": "collections/demo.json",
                "content_template": json.dumps(
                    {
                        "info": {"name": "示例集合"},
                        "item": [
                            {"request": {}},
                            {"item": [{"request": {}}]},
                        ],
                    }
                ),
                "render": False,
            },
        ],
    }
    tpl.update(overrides)
    return tpl


def _put_template(root: Path, dirname: str, payload: Dict[str, Any]) -> None:
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / "template.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


class _Env:
    def __init__(self, tmp_path: Path) -> None:
        self.projects_dir = tmp_path / "projects"
        self.builtin = tmp_path / "builtin"
        self.user = tmp_path / "user"
        self.builtin.mkdir()
        _put_template(self.builtin, "api_basic", _basic_template())
        self.store = ProjectStore(projects_dir=self.projects_dir)
        self.svc = ProjectService(
            project_store=self.store,
            template_store=ProjectTemplateStore(
                builtin_dir=self.builtin, user_dir=self.user
            ),
        )


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Env:
    e = _Env(tmp_path)
    monkeypatch.setattr(ps, "ENVIRONMENTS", {"test": {"base_url": "http://x"}})
    return e


def _create(e: _Env, name: str = "项目甲", **over: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": name,
        "template_id": "tpl_api_basic",
        "variables": {"system": "餐厅", "module": "订单", "owner": "张三"},
    }
    payload.update(over)
    return e.svc.create_project(payload)


# ---------- 创建全链 ----------


def test_create_full_chain(env: _Env) -> None:
    project = _create(env)
    pid = str(project["id"])
    assert ProjectStore.is_valid_project_id(pid)
    assert project["status"] == "active"
    assert project["metadata"]["system"] == "餐厅"
    assert project["metadata"]["_unresolved"] == ["jira_key"]
    readme = (env.projects_dir / pid / "docs" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "# 项目甲" in readme and "extra=" in readme
    # 示例集合索引：文件名=服务端 col_id，request_count 递归计数
    assert len(project["collections"]) == 1
    col = project["collections"][0]
    assert col["file"] == f"collections/{col['id']}.json"
    assert col["name"] == "示例集合" and col["request_count"] == 2
    # tracing 单源派生
    tracing = env.svc.get_tracing(pid)
    assert tracing["total"] == 1 and tracing["automated"] == 1
    assert tracing["rate"] == 100.0
    assert project["template_info"]["id"] == "tpl_api_basic"
    assert project["config"]["auth_profile"] == ""
    assert (env.projects_dir / pid / "project.json").is_file()


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"name": "", "template_id": "tpl_api_basic"}, "PRJ_201"),
        ({"name": "ok"}, "PRJ_203"),
        ({"name": "ok", "template_id": "tpl_none"}, "PRJ_203"),
        (
            {"name": "ok", "template_id": "tpl_api_basic", "variables": {}},
            "PRJ_202",
        ),
        (
            {
                "name": "ok",
                "template_id": "tpl_api_basic",
                "variables": {
                    "system": "不存在的枚举",
                    "module": "m",
                    "owner": "o",
                },
            },
            "PRJ_202",
        ),
    ],
)
def test_create_validation_codes(
    env: _Env, payload: Dict[str, Any], code: str
) -> None:
    with pytest.raises(ProjectError) as exc:
        env.svc.create_project(payload)
    assert exc.value.code == code


def test_create_duplicate_name(env: _Env) -> None:
    _create(env, name="重名")
    with pytest.raises(ProjectError) as exc:
        _create(env, name="重名")
    assert exc.value.code == "PRJ_204" and exc.value.http_status == 409


def test_create_exception_rolls_back(env: _Env) -> None:
    _put_template(
        env.builtin,
        "broken",
        _basic_template(
            id="tpl_broken",
            files=[{"path": "a.json", "content_template": "not-json", "render": False}],
        ),
    )
    with pytest.raises(ProjectError) as exc:
        env.svc.create_project(
            {
                "name": "半程失败",
                "template_id": "tpl_broken",
                "variables": {"system": "餐厅", "module": "m", "owner": "o"},
            }
        )
    assert exc.value.code == "PRJ_205"
    # 目录已整体回滚，list 无脏项目
    assert env.store.list_projects() == []
    assert not any(
        p.name.startswith("proj_") for p in env.projects_dir.iterdir()
    )


def test_create_env_validation(env: _Env) -> None:
    with pytest.raises(ProjectError) as exc:
        _create(env, name="环境", config={"environment": "prod999"})
    assert exc.value.code == "PRJ_501"
    project = _create(env, name="环境", config={"environment": "test"})
    assert project["config"]["environment"] == "test"


def test_secret_answers_masked(env: _Env) -> None:
    tpl = _basic_template(
        id="tpl_secret",
        variables=[
            {"key": "token", "label": "令牌", "type": "secret", "required": True}
        ],
    )
    _put_template(env.builtin, "secret", tpl)
    project = env.svc.create_project(
        {
            "name": "脱敏",
            "template_id": "tpl_secret",
            "variables": {"token": "s3cr3t"},
        }
    )
    assert project["template_info"]["answers"]["token"] == "***"


# ---------- 列表 / 检索 / 过滤 ----------


def test_list_filter_and_paging(env: _Env) -> None:
    p1 = _create(env, name="阿尔法")
    p2 = _create(env, name="贝塔")
    env.svc.update_project(
        p2["id"],
        {
            "status": "completed",
            "updated_at": p2["metadata"]["updated_at"],
        },
    )
    page = env.svc.list_projects()
    assert page["total"] == 2
    assert {i["name"] for i in page["items"]} == {"阿尔法", "贝塔"}
    done = env.svc.list_projects(status="completed")
    assert done["total"] == 1 and done["items"][0]["id"] == p2["id"]
    hit = env.svc.list_projects(search="尔法")
    assert [i["id"] for i in hit["items"]] == [p1["id"]]
    small = env.svc.list_projects(page=2, page_size=1)
    assert small["total"] == 2 and len(small["items"]) == 1
    with pytest.raises(ProjectError) as exc:
        env.svc.list_projects(status="bogus")
    assert exc.value.code == "PRJ_101"


# ---------- 更新 CAS（G-36） ----------


def test_update_cas(env: _Env) -> None:
    project = _create(env)
    pid = str(project["id"])
    stamp = project["metadata"]["updated_at"]

    with pytest.raises(ProjectError) as exc:
        env.svc.update_project(pid, {"name": "改名", "updated_at": "stale"})
    assert exc.value.code == "PRJ_306" and exc.value.http_status == 409
    assert exc.value.data["name"] == "项目甲"

    updated = env.svc.update_project(pid, {"name": "改名", "updated_at": stamp})
    assert updated["name"] == "改名"
    assert updated["metadata"]["updated_at"] != stamp

    with pytest.raises(ProjectError) as exc:
        env.svc.update_project(pid, {"name": "再改"})
    assert exc.value.code == "PRJ_303"

    with pytest.raises(ProjectError) as exc:
        env.svc.update_project(
            pid, {"status": "cancelled", "updated_at": updated["metadata"]["updated_at"]}
        )
    assert exc.value.code == "PRJ_304"


# ---------- 删除防护 ----------


def test_delete_guard(env: _Env) -> None:
    project = _create(env)
    pid = str(project["id"])
    with pytest.raises(ProjectError) as exc:
        env.svc.delete_project(pid)
    assert exc.value.code == "PRJ_305" and exc.value.http_status == 403
    assert env.svc.delete_project(pid, confirmed=True) == {"deleted": pid}
    assert not (env.projects_dir / pid).exists()
    with pytest.raises(ProjectError) as exc:
        env.svc.delete_project(pid, confirmed=True)
    assert exc.value.code == "PRJ_102"
    with pytest.raises(ProjectError) as exc:
        env.svc.get_project("../evil")
    assert exc.value.code == "PRJ_301"


# ---------- 集合 A6~A8 ----------


def test_collections_add_remove_limit(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _create(env)
    pid = str(project["id"])
    with pytest.raises(ProjectError) as exc:
        env.svc.add_collection(pid, {"nope": 1})
    assert exc.value.code == "PRJ_401"

    entry = env.svc.add_collection(
        pid, {"info": {"name": "手工"}, "item": [{"request": {}}]}
    )
    assert entry["request_count"] == 1
    assert len(env.svc.list_collections(pid)["items"]) == 2

    monkeypatch.setattr(ps, "PROJECT_MAX_COLLECTIONS", 2)
    with pytest.raises(ProjectError) as exc:
        env.svc.add_collection(pid, {"info": {"name": "x"}, "item": []})
    assert exc.value.code == "PRJ_403" and exc.value.http_status == 409

    removed = env.svc.remove_collection(pid, entry["id"])
    assert [c["id"] for c in removed["items"]] == [project["collections"][0]["id"]]
    with pytest.raises(ProjectError) as exc:
        env.svc.remove_collection(pid, "col_missing0000")
    assert exc.value.code == "PRJ_404"


def test_tracing_dangling_after_collection_removal(env: _Env) -> None:
    project = _create(env)
    pid = str(project["id"])
    col_id = project["collections"][0]["id"]
    stamp = project["tracing"]["updated_at"]
    env.svc.put_tracing(
        pid,
        [
            {
                "case_no": "C1",
                "title": "扫码",
                "convert_status": "automated",
                "collection_id": col_id,
            }
        ],
        stamp,
    )
    assert env.svc.get_tracing(pid)["rows"][0]["dangling"] is False
    env.svc.remove_collection(pid, col_id)
    assert env.svc.get_tracing(pid)["rows"][0]["dangling"] is True


# ---------- 追溯 A10/A11 ----------


def test_tracing_put_cas_and_validation(env: _Env) -> None:
    project = _create(env)
    pid = str(project["id"])
    stamp = project["tracing"]["updated_at"]

    result = env.svc.put_tracing(
        pid,
        [
            {"case_no": "C1", "title": "t1", "convert_status": "automated"},
            {"case_no": "C2", "title": "t2", "convert_status": "pending"},
        ],
        stamp,
    )
    assert result["total"] == 2 and result["automated"] == 1
    assert result["rate"] == 50.0

    with pytest.raises(ProjectError) as exc:
        env.svc.put_tracing(pid, [], stamp)  # 旧 updated_at 已失效
    assert exc.value.code == "PRJ_602" and exc.value.http_status == 409

    fresh = env.svc.get_tracing(pid)
    with pytest.raises(ProjectError) as exc:
        env.svc.put_tracing(pid, [{"case_no": "C3"}], fresh["updated_at"])
    assert exc.value.code == "PRJ_603"
    with pytest.raises(ProjectError) as exc:
        env.svc.put_tracing(pid, "not-a-list", fresh["updated_at"])
    assert exc.value.code == "PRJ_603"


# ---------- G-30 状态机：入队即记录 + 懒对账 ----------


def test_record_enqueued_history_cap(env: _Env) -> None:
    project = _create(env)
    pid = str(project["id"])
    monkeyps = env.svc
    for i in range(25):
        monkeyps.record_execution_enqueued(pid, f"job_{i}", f"rep_{i}")
    reloaded = env.store.get_project(pid)
    assert reloaded is not None
    history = reloaded["statistics"]["execution_history"]
    assert len(history) == 20
    assert history[0]["job_id"] == "job_24"
    assert history[0]["status"] == "queued"
    assert reloaded["statistics"]["last_execution"]["job_id"] == "job_24"


def _seed_history(env: _Env, entries: list) -> str:
    project = _create(env)
    pid = str(project["id"])
    loaded = env.store.get_project(pid)
    assert loaded is not None
    loaded["statistics"]["execution_history"] = entries
    env.store.save_project(loaded)
    return pid


def test_reconcile_running_from_memory(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _seed_history(
        env, [{"job_id": "j1", "report_name": "r1", "time": "t", "status": "queued", "passed": None, "failed": None}]
    )
    monkeypatch.setattr(ps, "get_run_job", lambda jid: {"status": "running"})
    monkeypatch.setattr(ps, "find_report", lambda name: pytest.fail("不应读报告"))
    detail = env.svc.get_project(pid)
    assert detail["statistics"]["execution_history"][0]["status"] == "running"


def test_reconcile_done_after_restart(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _seed_history(
        env, [{"job_id": "j1", "report_name": "r1", "time": "t", "status": "running", "passed": None, "failed": None}]
    )
    monkeypatch.setattr(ps, "get_run_job", lambda jid: None)  # 模拟重启内存 miss

    def fake_find(name: str) -> Dict[str, Any]:
        assert name == "r1"
        return {"passed": 3, "failed": 1}

    monkeypatch.setattr(ps, "find_report", fake_find)
    detail = env.svc.get_project(pid)
    entry = detail["statistics"]["execution_history"][0]
    assert entry["status"] == "done"
    assert (entry["passed"], entry["failed"]) == (3, 1)
    # 对账结果已回写落盘
    raw = env.store.get_project(pid)
    assert raw is not None
    assert raw["statistics"]["execution_history"][0]["status"] == "done"


def test_reconcile_unknown_terminal(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _seed_history(
        env, [{"job_id": "j1", "report_name": "r1", "time": "t", "status": "queued", "passed": None, "failed": None}]
    )

    def raise_fnf(name: str) -> Dict[str, Any]:
        raise FileNotFoundError(name)

    monkeypatch.setattr(ps, "get_run_job", lambda jid: None)
    monkeypatch.setattr(ps, "find_report", raise_fnf)
    entry = env.svc.get_project(pid)["statistics"]["execution_history"][0]
    assert entry["status"] == "unknown"
    # unknown 终态：再次对账不再触碰
    monkeypatch.setattr(ps, "get_run_job", lambda jid: {"status": "success"})
    again = env.svc.get_project(pid)["statistics"]["execution_history"][0]
    assert again["status"] == "unknown"


def test_reconcile_memory_terminal_with_counts(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _seed_history(
        env, [{"job_id": "j1", "report_name": "r1", "time": "t", "status": "running", "passed": None, "failed": None}]
    )
    monkeypatch.setattr(ps, "get_run_job", lambda jid: {"status": "success"})
    monkeypatch.setattr(ps, "find_report", lambda name: {"passed": 5, "failed": 0})
    entry = env.svc.get_project(pid)["statistics"]["execution_history"][0]
    assert entry["status"] == "done"
    assert (entry["passed"], entry["failed"]) == (5, 0)


# ---------- A14/A15 模板面 ----------


def test_template_merged_user_overrides_builtin(env: _Env) -> None:
    with_override = _basic_template(desc_note="用户版")
    env.svc.templates.save_user_template(with_override)
    tpl = env.svc.load_template_merged("tpl_api_basic")
    assert tpl["source"] == "user" and tpl["desc_note"] == "用户版"
    items = env.svc.list_templates()["items"]
    assert [t["id"] for t in items] == ["tpl_api_basic"]
    assert items[0]["source"] == "user"
    project = _create(env, name="用覆盖模板建")
    assert project["template_info"]["source"] == "user"


def test_template_declaration_validation(env: _Env) -> None:
    with pytest.raises(ProjectError) as exc:
        env.svc.create_template(
            {
                "name": "Evil Path",
                "files": [{"path": "../escape.md", "content_template": "x"}],
            }
        )
    assert exc.value.code == "TPL_001"

    with pytest.raises(ProjectError) as exc:
        env.svc.create_template(
            {
                "name": "dup vars",
                "variables": [
                    {"key": "a", "type": "string"},
                    {"key": "a", "type": "string"},
                ],
            }
        )
    assert exc.value.code == "TPL_001"

    created = env.svc.create_template(
        {"name": "My Cool Tool!", "id": "evil-client-id"},
    )
    assert created["id"] != "evil-client-id"
    assert ProjectTemplateStore.is_valid_template_id(created["id"])
    assert created["source"] == "user"
    assert (env.user / created["id"] / "template.json").is_file()


def test_template_builtin_readonly_conflict(env: _Env) -> None:
    # slug 命中内置 id → TPL_002
    with pytest.raises(ProjectError) as exc:
        env.svc.create_template({"name": "api_basic"})
    assert exc.value.code == "TPL_002" and exc.value.http_status == 409


def test_template_size_limit(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ps, "PROJECT_TEMPLATE_MAX_BYTES", 50)
    with pytest.raises(ProjectError) as exc:
        env.svc.create_template({"name": "大模板", "description": "x" * 200})
    assert exc.value.code == "TPL_001"


def test_use_phase_declaration_check(env: _Env) -> None:
    # 使用期：手工塞入声明非法的内置模板（files.path 越界）→ PRJ_203
    _put_template(
        env.builtin,
        "evil",
        _basic_template(id="tpl_evil", files=[{"path": "/abs.md", "content_template": "x"}]),
    )
    with pytest.raises(ProjectError) as exc:
        env.svc.load_template_merged("tpl_evil")
    assert exc.value.code == "PRJ_203"
