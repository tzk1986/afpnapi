"""v1.39.0 S1.3 项目脚手架 routes 层单测（N12）。

覆盖 v3 5.5 测试矩阵 routes 行与 S1.3 检查点：
开关关→403 PRJ_100（API 包装体/页面提示页，且零文件系统痕迹）、
非法 JSON→统一 400 包装（G-34）、成功包装 `data["code"]==200`+`data["data"]`、
CRUD 全链、CAS 409（PRJ_306/602，current 合并体）、删除防护 PRJ_305、
集合/追溯/模板端点、A9/A12/A13 占位 501。
execute 真实入队断言（env_name/report_name 透传）在 S3.1 补充。
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from flask import Flask

from postman_api_tester.handlers import project_routes as pr
from postman_api_tester.handlers.base_handler import register_error_handlers
from postman_api_tester.services.project_service import ProjectService
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
                "content_template": "# {{project_name}}",
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
                "content_template": json.dumps({"info": {"name": "示例集合"}, "item": [{"request": {}}]}),
                "render": False,
            },
        ],
    }
    tpl.update(overrides)
    return tpl


def _register_routes(app: Flask) -> None:
    """按 v3 5.2 路径表注册 18 条路由（与 S1.4 report_server 装配逐条对齐）。"""
    r = app.add_url_rule
    r("/projects", "projects_page", pr.projects_page)
    r("/projects/create", "projects_create_page", pr.projects_create_page)
    r("/projects/detail/<project_id>", "projects_detail_page", pr.projects_detail_page)
    r("/api/projects", "api_list_projects", pr.api_list_projects, methods=["GET"])
    r("/api/projects", "api_create_project", pr.api_create_project, methods=["POST"])
    r("/api/projects/<project_id>", "api_get_project", pr.api_get_project, methods=["GET"])
    r("/api/projects/<project_id>", "api_update_project", pr.api_update_project, methods=["PUT"])
    r("/api/projects/<project_id>", "api_delete_project", pr.api_delete_project, methods=["DELETE"])
    r(
        "/api/projects/<project_id>/collections",
        "api_list_project_collections",
        pr.api_list_project_collections,
        methods=["GET"],
    )
    r(
        "/api/projects/<project_id>/collections",
        "api_add_project_collection",
        pr.api_add_project_collection,
        methods=["POST"],
    )
    r(
        "/api/projects/<project_id>/collections/<col_id>",
        "api_remove_project_collection",
        pr.api_remove_project_collection,
        methods=["DELETE"],
    )
    r("/api/projects/<project_id>/execute", "api_execute_project", pr.api_execute_project, methods=["POST"])
    r("/api/projects/<project_id>/tracing", "api_get_project_tracing", pr.api_get_project_tracing, methods=["GET"])
    r("/api/projects/<project_id>/tracing", "api_put_project_tracing", pr.api_put_project_tracing, methods=["PUT"])
    r(
        "/api/projects/<project_id>/export/tracing.csv",
        "api_export_project_tracing_csv",
        pr.api_export_project_tracing_csv,
    )
    r("/api/projects/<project_id>/export", "api_export_project_zip", pr.api_export_project_zip)
    r("/api/project-templates", "api_list_project_templates", pr.api_list_project_templates, methods=["GET"])
    r("/api/project-templates", "api_create_project_template", pr.api_create_project_template, methods=["POST"])


class _Env:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
        monkeypatch.setattr(pr, "ENABLE_PROJECT_SCAFFOLD", enabled)
        self.projects_dir = tmp_path / "projects"
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        d = builtin / "api_basic"
        d.mkdir(parents=True)
        (d / "template.json").write_text(
            json.dumps(_basic_template(), ensure_ascii=False), encoding="utf-8"
        )
        self.svc = ProjectService(
            project_store=ProjectStore(projects_dir=self.projects_dir),
            template_store=ProjectTemplateStore(
                builtin_dir=builtin, user_dir=tmp_path / "user_templates"
            ),
        )
        monkeypatch.setattr(pr, "get_project_service", lambda: self.svc)
        app = Flask(__name__)
        app.testing = True
        register_error_handlers(app)
        _register_routes(app)
        self.client = app.test_client()


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool = True) -> _Env:
    return _Env(tmp_path, monkeypatch, enabled)


def _create_payload(name: str = "项目甲", **over: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": name,
        "template_id": "tpl_api_basic",
        "variables": {"system": "餐厅", "module": "订单", "owner": "张三"},
    }
    payload.update(over)
    return payload


# ---------- 开关关：403 + 零文件系统痕迹（G-25） ----------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/projects"),
        ("POST", "/api/projects"),
        ("GET", "/api/projects/proj_a1b2c3d4e5f6"),
        ("GET", "/api/project-templates"),
    ],
)
def test_api_disabled_returns_403_prj_100(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    e = _env(tmp_path, monkeypatch, enabled=False)
    resp = e.client.open(path, method=method, json={})
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["error_code"] == "PRJ_100"
    assert data["code"] == 403
    # 开关关：读路径与门控均不触碰磁盘
    assert not e.projects_dir.exists()


def test_page_disabled_returns_403_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _env(tmp_path, monkeypatch, enabled=False)
    for path in ("/projects", "/projects/create", "/projects/detail/proj_a1b2c3d4e5f6"):
        resp = e.client.get(path)
        assert resp.status_code == 403
        assert b"ENABLE_PROJECT_SCAFFOLD" in resp.data
    assert not e.projects_dir.exists()


# ---------- 包装契约（v2 冲突 1 / L-1） ----------


def test_success_wrapper_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = _env(tmp_path, monkeypatch)
    resp = e.client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == 200
    assert isinstance(data["data"], dict)
    assert data["data"]["items"] == []


def test_invalid_json_body_wrapped_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G-34：非法 JSON 不得外漏 Flask HTML 400，统一走业务包装。"""
    e = _env(tmp_path, monkeypatch)
    resp = e.client.post(
        "/api/projects", data="{not json", content_type="application/json"
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error_code"] == "PRJ_201"
    assert resp.is_json  # 非 Flask 默认 HTML 400（G-34）
    assert data["data"]["details"]


# ---------- CRUD 全链 ----------


def test_crud_full_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = _env(tmp_path, monkeypatch)
    c = e.client

    resp = c.post("/api/projects", json=_create_payload())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 200
    project = body["data"]
    pid = project["id"]
    assert project["name"] == "项目甲"

    resp = c.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["id"] == pid

    resp = c.put(
        f"/api/projects/{pid}",
        json={"name": "改名", "updated_at": project["metadata"]["updated_at"]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["name"] == "改名"

    resp = c.delete(f"/api/projects/{pid}")
    assert resp.status_code == 403
    assert resp.get_json()["error_code"] == "PRJ_305"

    resp = c.delete(f"/api/projects/{pid}", json={"confirm": True})
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"deleted": pid}

    assert c.get(f"/api/projects/{pid}").status_code == 404


def test_get_missing_404_and_invalid_id_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _env(tmp_path, monkeypatch)
    resp = e.client.get("/api/projects/proj_a1b2c3d4e5f6")
    assert resp.status_code == 404
    assert resp.get_json()["error_code"] == "PRJ_102"

    resp = e.client.get("/api/projects/proj_bad")
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_301"


def test_create_error_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = _env(tmp_path, monkeypatch)
    resp = e.client.post("/api/projects", json={"name": "ok"})
    assert resp.status_code == 404  # 缺 template_id → PRJ_203
    assert resp.get_json()["error_code"] == "PRJ_203"

    resp = e.client.post("/api/projects", json=_create_payload(variables={}))
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_202"

    e.client.post("/api/projects", json=_create_payload())
    resp = e.client.post("/api/projects", json=_create_payload())
    assert resp.status_code == 409
    assert resp.get_json()["error_code"] == "PRJ_204"


def test_list_filter_invalid_status_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _env(tmp_path, monkeypatch)
    resp = e.client.get("/api/projects?status=bogus")
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_101"


# ---------- CAS 冲突合并体（G-36） ----------


def test_update_cas_conflict_carries_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _env(tmp_path, monkeypatch)
    project = e.client.post("/api/projects", json=_create_payload()).get_json()["data"]
    pid = project["id"]
    resp = e.client.put(f"/api/projects/{pid}", json={"name": "x", "updated_at": "stale"})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error_code"] == "PRJ_306"
    assert body["data"]["current"]["name"] == "项目甲"


# ---------- 集合 A6~A8 ----------


def test_collections_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = _env(tmp_path, monkeypatch)
    project = e.client.post("/api/projects", json=_create_payload()).get_json()["data"]
    pid = project["id"]

    resp = e.client.get(f"/api/projects/{pid}/collections")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["items"]) == 1  # 模板生成 demo

    resp = e.client.post(
        f"/api/projects/{pid}/collections",
        json={"info": {"name": "手工"}, "item": [{"request": {}}]},
    )
    assert resp.status_code == 200
    col_id = resp.get_json()["data"]["id"]

    resp = e.client.post(f"/api/projects/{pid}/collections", json={"nope": 1})
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_401"

    resp = e.client.delete(f"/api/projects/{pid}/collections/{col_id}")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["items"]) == 1

    resp = e.client.delete(f"/api/projects/{pid}/collections/{col_id}")
    assert resp.status_code == 404
    assert resp.get_json()["error_code"] == "PRJ_404"


# ---------- 追溯 A10~A11 ----------


def test_tracing_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = _env(tmp_path, monkeypatch)
    project = e.client.post("/api/projects", json=_create_payload()).get_json()["data"]
    pid = project["id"]

    resp = e.client.get(f"/api/projects/{pid}/tracing")
    assert resp.status_code == 200
    got = resp.get_json()["data"]
    assert got["total"] == 1 and got["rate"] == 100.0

    resp = e.client.put(
        f"/api/projects/{pid}/tracing",
        json={
            "rows": [
                {"case_no": "C1", "title": "扫码", "convert_status": "automated"},
                {"case_no": "C2", "title": "退款", "convert_status": "pending"},
            ],
            "updated_at": got["updated_at"],
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["rate"] == 50.0

    resp = e.client.put(f"/api/projects/{pid}/tracing", json={"rows": [], "updated_at": got["updated_at"]})
    assert resp.status_code == 409
    assert resp.get_json()["error_code"] == "PRJ_602"

    # 非法 JSON → rows=None → PRJ_603（行格式非法）
    resp = e.client.put(
        f"/api/projects/{pid}/tracing",
        data="{bad",
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_603"


# ---------- 模板 A14~A15 ----------


def test_template_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = _env(tmp_path, monkeypatch)
    resp = e.client.get("/api/project-templates")
    assert resp.status_code == 200
    items = resp.get_json()["data"]["items"]
    assert [t["id"] for t in items] == ["tpl_api_basic"]
    assert items[0]["source"] == "builtin"

    resp = e.client.post(
        "/api/project-templates",
        json={"name": "我的模板", "files": [{"path": "docs/a.md", "content_template": "hi", "render": False}]},
    )
    assert resp.status_code == 200
    created = resp.get_json()["data"]
    assert created["id"].startswith("tpl_") and created["source"] == "user"

    resp = e.client.post(
        "/api/project-templates",
        json={"name": "坏路径", "files": [{"path": "../evil.md", "content_template": "x"}]},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "TPL_001"

    resp = e.client.post("/api/project-templates", json={"name": "api_basic", "files": []})
    assert resp.status_code == 409
    assert resp.get_json()["error_code"] == "TPL_002"


# ---------- A9/A12/A13 占位（真实实现分别在 S3.1/S4.2 接线） ----------


def test_not_wired_endpoints_return_501(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _env(tmp_path, monkeypatch)
    project = e.client.post("/api/projects", json=_create_payload()).get_json()["data"]
    pid = project["id"]
    for path in (
        f"/api/projects/{pid}/execute",
        f"/api/projects/{pid}/export/tracing.csv",
        f"/api/projects/{pid}/export",
    ):
        resp = e.client.post(path) if path.endswith("execute") else e.client.get(path)
        assert resp.status_code == 501
        assert resp.get_json()["error_code"] == "COM_001"


# ---------- ValueError 兜底映射（PRJ_301 via PROJECT_ERROR_MAP） ----------


def test_value_error_fallback_maps_prj_301(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _env(tmp_path, monkeypatch)
    def _boom(_pid: str) -> Dict[str, Any]:
        raise ValueError("非法项目 id")

    monkeypatch.setattr(e.svc, "list_collections", _boom)
    resp = e.client.get("/api/projects/proj_a1b2c3d4e5f6/collections")
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_301"
