"""全局变量路由单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask

from postman_api_tester.handlers.global_variables_routes import (
    api_global_variables_clear,
    api_global_variables_delete,
    api_global_variables_get,
    api_global_variables_set,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.add_url_rule("/api/global-variables", "gv_get", api_global_variables_get, methods=["GET"])
    app.add_url_rule("/api/global-variables", "gv_set", api_global_variables_set, methods=["POST"])
    app.add_url_rule("/api/global-variables", "gv_clear", api_global_variables_clear, methods=["DELETE"])
    app.add_url_rule(
        "/api/global-variables/<path:key>", "gv_delete", api_global_variables_delete, methods=["DELETE"]
    )
    return app


@pytest.fixture  # type: ignore[untyped-decorator]
def vars_file(tmp_path: Path) -> str:
    return str(tmp_path / "test_vars.json")


def _seed_vars(path: str, variables: dict) -> None:
    data = {"version": 1, "updated_at": "2026-06-17T08:00:00", "variables": variables}
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestApiGlobalVariablesGet:

    def test_disabled_returns_403(self, app: Flask) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=""):
            client = app.test_client()
            resp = client.get("/api/global-variables")
            assert resp.status_code == 403

    def test_empty_file(self, app: Flask, vars_file: str) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.get("/api/global-variables")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["data"]["count"] == 0

    def test_returns_masked_values(self, app: Flask, vars_file: str) -> None:
        _seed_vars(vars_file, {"token": "abcdef1234567890"})
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.get("/api/global-variables")
            data = resp.get_json()
            masked = data["data"]["variables"]["token"]
            assert masked.startswith("ab")
            assert masked.endswith("90")
            assert "abcdef1234567890" not in masked


class TestApiGlobalVariablesSet:

    def test_disabled_returns_403(self, app: Flask) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=""):
            client = app.test_client()
            resp = client.post("/api/global-variables", json={"key": "a", "value": "b"})
            assert resp.status_code == 403

    def test_missing_key_returns_400(self, app: Flask, vars_file: str) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.post("/api/global-variables", json={"value": "b"})
            assert resp.status_code == 400

    def test_missing_value_returns_400(self, app: Flask, vars_file: str) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.post("/api/global-variables", json={"key": "a"})
            assert resp.status_code == 400

    def test_set_success(self, app: Flask, vars_file: str) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.post("/api/global-variables", json={"key": "mykey", "value": "myval"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["data"]["count"] == 1


class TestApiGlobalVariablesDeleteKey:

    def test_disabled_returns_403(self, app: Flask) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=""):
            client = app.test_client()
            resp = client.delete("/api/global-variables/some_key")
            assert resp.status_code == 403

    def test_delete_nonexistent_returns_404(self, app: Flask, vars_file: str) -> None:
        _seed_vars(vars_file, {"a": "1"})
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.delete("/api/global-variables/nonexistent")
            assert resp.status_code == 404

    def test_delete_success(self, app: Flask, vars_file: str) -> None:
        _seed_vars(vars_file, {"a": "1", "b": "2"})
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.delete("/api/global-variables/a")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["data"]["deleted"] is True


class TestApiGlobalVariablesClear:

    def test_disabled_returns_403(self, app: Flask) -> None:
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=""):
            client = app.test_client()
            resp = client.delete("/api/global-variables")
            assert resp.status_code == 403

    def test_clear_success(self, app: Flask, vars_file: str) -> None:
        _seed_vars(vars_file, {"a": "1", "b": "2"})
        with patch("postman_api_tester.handlers.global_variables_routes._get_file_path", return_value=vars_file):
            client = app.test_client()
            resp = client.delete("/api/global-variables")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["data"]["cleared"] is True
