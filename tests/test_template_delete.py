"""A16 用户模板删除单测。

覆盖：删除成功（目录消失 + A14 列表不再含）、内置只读 409 TPL_002、
不存在 404 PRJ_203、非法 id 400 PRJ_301（store 路径守卫）、开关关 403 PRJ_100。
夹具复用 test_project_routes 的 _Env 模式（tmp 两源目录 + monkeypatch）。
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from flask import Flask

from postman_api_tester.handlers import project_routes as pr
from postman_api_tester.handlers.base_handler import register_error_handlers
from postman_api_tester.services.project_service import ProjectService
from postman_api_tester.services.project_store import ProjectStore, ProjectTemplateStore

from tests.test_project_routes import _basic_template


class _Env:
    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool = True
    ) -> None:
        monkeypatch.setattr(pr, "ENABLE_PROJECT_SCAFFOLD", enabled)
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        d = builtin / "api_basic"
        d.mkdir(parents=True)
        (d / "template.json").write_text(
            json.dumps(_basic_template(), ensure_ascii=False), encoding="utf-8"
        )
        self.user_dir = tmp_path / "user_templates"
        self.svc = ProjectService(
            project_store=ProjectStore(projects_dir=tmp_path / "projects"),
            template_store=ProjectTemplateStore(
                builtin_dir=builtin, user_dir=self.user_dir
            ),
        )
        monkeypatch.setattr(pr, "get_project_service", lambda: self.svc)
        app = Flask(__name__)
        app.testing = True
        register_error_handlers(app)
        app.add_url_rule(
            "/api/project-templates",
            "api_list_project_templates",
            pr.api_list_project_templates,
            methods=["GET"],
        )
        app.add_url_rule(
            "/api/project-templates",
            "api_create_project_template",
            pr.api_create_project_template,
            methods=["POST"],
        )
        app.add_url_rule(
            "/api/project-templates/<template_id>",
            "api_delete_project_template",
            pr.api_delete_project_template,
            methods=["DELETE"],
        )
        self.client = app.test_client()


def _create_user_template(client: Any, name: str = "自定义模板") -> str:
    payload: Dict[str, Any] = {
        "name": name,
        "version": "1.0.0",
        "variables": [
            {"key": "owner", "label": "负责人", "type": "string", "required": True}
        ],
        "files": [],
    }
    resp = client.post("/api/project-templates", json=payload)
    assert resp.status_code == 200
    return str(resp.get_json()["data"]["id"])


def test_delete_user_template_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _Env(tmp_path, monkeypatch)
    tid = _create_user_template(e.client)
    assert (e.user_dir / tid / "template.json").is_file()

    resp = e.client.delete(f"/api/project-templates/{tid}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"]["deleted"] is True
    assert data["data"]["id"] == tid
    assert not (e.user_dir / tid).exists()

    ids = [t["id"] for t in e.client.get("/api/project-templates").get_json()["data"]["items"]]
    assert tid not in ids and "tpl_api_basic" in ids


def test_delete_builtin_returns_409_tpl_002(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _Env(tmp_path, monkeypatch)
    resp = e.client.delete("/api/project-templates/tpl_api_basic")
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error_code"] == "TPL_002"
    # 内置目录未被触碰
    assert (e.svc.templates._builtin / "api_basic" / "template.json").is_file()


def test_delete_missing_returns_404_prj_203(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _Env(tmp_path, monkeypatch)
    resp = e.client.delete("/api/project-templates/tpl_not_exist")
    assert resp.status_code == 404
    assert resp.get_json()["error_code"] == "PRJ_203"


def test_delete_invalid_id_returns_400_prj_301(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _Env(tmp_path, monkeypatch)
    resp = e.client.delete("/api/project-templates/nope")
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "PRJ_301"


def test_delete_disabled_returns_403_prj_100(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _Env(tmp_path, monkeypatch, enabled=False)
    resp = e.client.delete("/api/project-templates/tpl_api_basic")
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["error_code"] == "PRJ_100"
    assert not e.user_dir.exists()
