"""UI 认证档案路由单元测试。

覆盖 api_ui_auth_routes.py 中的所有端点：
- 档案列表
- 创建档案
- 获取档案详情
- 更新档案
- 删除档案
- 导出 storage_state
- 清理过期档案
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from flask import Flask

from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profile_delete,
    api_ui_auth_profile_export,
    api_ui_auth_profile_get,
    api_ui_auth_profile_update,
    api_ui_auth_profiles_cleanup,
    api_ui_auth_profiles_create,
    api_ui_auth_profiles_list,
    ui_auth_profiles_page,
)
from postman_api_tester.services.ui_auth_profile_store import UiAuthProfileStore


@pytest.fixture
def tmp_profiles_dir(tmp_path: Path) -> Path:
    """临时档案存储目录。"""
    return tmp_path / "auth_profiles"


@pytest.fixture
def auth_store(tmp_profiles_dir: Path) -> UiAuthProfileStore:
    """认证档案存储实例。"""
    return UiAuthProfileStore(profiles_dir=tmp_profiles_dir)


@pytest.fixture
def app(auth_store: UiAuthProfileStore) -> Generator[Flask, None, None]:
    """Flask 测试应用。"""
    app = Flask(__name__)
    app.config["TESTING"] = True

    # 替换全局 auth store
    import postman_api_tester.handlers.ui_auth_routes as routes_module
    original_store = routes_module._auth_profile_store
    routes_module._auth_profile_store = auth_store

    # 注册路由
    app.add_url_rule(
        "/ui-testing/auth-profiles",
        "ui_auth_profiles_page",
        ui_auth_profiles_page,
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles",
        "api_ui_auth_profiles_list",
        api_ui_auth_profiles_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles",
        "api_ui_auth_profiles_create",
        api_ui_auth_profiles_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles/<profile_id>",
        "api_ui_auth_profile_get",
        api_ui_auth_profile_get,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles/<profile_id>",
        "api_ui_auth_profile_update",
        api_ui_auth_profile_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles/<profile_id>",
        "api_ui_auth_profile_delete",
        api_ui_auth_profile_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles/<profile_id>/export",
        "api_ui_auth_profile_export",
        api_ui_auth_profile_export,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/ui-testing/auth-profiles/cleanup",
        "api_ui_auth_profiles_cleanup",
        api_ui_auth_profiles_cleanup,
        methods=["POST"],
    )

    yield app

    # 恢复原始 store
    routes_module._auth_profile_store = original_store


@pytest.fixture
def client(app: Flask):
    """Flask 测试客户端。"""
    return app.test_client()


class TestUiAuthProfilesPage:
    """认证档案管理页面测试。"""

    @pytest.mark.skip(reason="需要完整的 Flask 应用配置模板目录")
    def test_render_page(self, client) -> None:
        """页面渲染成功。"""
        resp = client.get("/ui-testing/auth-profiles")
        assert resp.status_code == 200


class TestApiUiAuthProfilesList:
    """档案列表 API 测试。"""

    def test_list_empty(self, client) -> None:
        """空列表返回成功。"""
        resp = client.get("/api/ui-testing/auth-profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["code"] == 200
        assert data["data"]["profiles"] == []

    def test_list_with_profiles(self, client, auth_store: UiAuthProfileStore) -> None:
        """有档案时返回列表。"""
        auth_store.save_profile({
            "name": "测试档案1",
            "base_url": "http://example.com",
            "cookies": [],
        })
        auth_store.save_profile({
            "name": "测试档案2",
            "base_url": "http://test.com",
            "cookies": [],
        })

        resp = client.get("/api/ui-testing/auth-profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["data"]["profiles"]) == 2


class TestApiUiAuthProfilesCreate:
    """创建档案 API 测试。"""

    def test_create_success(self, client) -> None:
        """创建成功返回 201。"""
        resp = client.post(
            "/api/ui-testing/auth-profiles",
            json={
                "name": "新档案",
                "base_url": "http://example.com",
                "cookies": [{"name": "session", "value": "abc123"}],
                "local_storage": {"token": "xyz"},
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["code"] == 201
        assert "id" in data["data"]

    def test_create_invalid_json(self, client) -> None:
        """无效 JSON 返回 400。"""
        resp = client.post(
            "/api/ui-testing/auth-profiles",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_create_missing_cookies(self, client) -> None:
        """缺少 cookies 字段返回 400。"""
        resp = client.post(
            "/api/ui-testing/auth-profiles",
            json={
                "name": "新档案",
                "base_url": "http://example.com",
            },
        )
        assert resp.status_code == 400

    def test_create_invalid_cookies_type(self, client) -> None:
        """cookies 类型错误返回 400。"""
        resp = client.post(
            "/api/ui-testing/auth-profiles",
            json={
                "name": "新档案",
                "cookies": "not a list",
            },
        )
        assert resp.status_code == 400


class TestApiUiAuthProfileGet:
    """获取档案详情 API 测试。"""

    def test_get_success(self, client, auth_store: UiAuthProfileStore) -> None:
        """获取成功返回档案详情。"""
        profile_id = auth_store.save_profile({
            "name": "测试档案",
            "base_url": "http://example.com",
            "cookies": [{"name": "session", "value": "abc"}],
        })

        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["name"] == "测试档案"
        assert data["data"]["base_url"] == "http://example.com"

    def test_get_nonexistent(self, client) -> None:
        """不存在的档案返回 404。"""
        resp = client.get("/api/ui-testing/auth-profiles/nonexistent")
        assert resp.status_code == 404


class TestApiUiAuthProfileUpdate:
    """更新档案 API 测试。"""

    def test_update_success(self, client, auth_store: UiAuthProfileStore) -> None:
        """更新成功返回 ok。"""
        profile_id = auth_store.save_profile({
            "name": "原档案",
            "base_url": "http://example.com",
            "cookies": [],
        })

        resp = client.put(
            f"/api/ui-testing/auth-profiles/{profile_id}",
            json={"name": "更新后的档案"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["ok"] is True

        # 验证更新成功
        updated = auth_store.get_profile(profile_id)
        assert updated["name"] == "更新后的档案"

    def test_update_nonexistent(self, client) -> None:
        """更新不存在的档案返回 404。"""
        resp = client.put(
            "/api/ui-testing/auth-profiles/nonexistent",
            json={"name": "新名称"},
        )
        assert resp.status_code == 404

    def test_update_invalid_json(self, client, auth_store: UiAuthProfileStore) -> None:
        """无效 JSON 返回 400。"""
        profile_id = auth_store.save_profile({
            "name": "测试",
            "cookies": [],
        })

        resp = client.put(
            f"/api/ui-testing/auth-profiles/{profile_id}",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_update_preserves_id(self, client, auth_store: UiAuthProfileStore) -> None:
        """更新时 id 字段不会被覆盖。"""
        profile_id = auth_store.save_profile({
            "name": "测试",
            "cookies": [],
        })

        # 尝试更新 id 字段
        resp = client.put(
            f"/api/ui-testing/auth-profiles/{profile_id}",
            json={"id": "malicious_id", "name": "新名称"},
        )
        assert resp.status_code == 200

        # 验证 id 未被改变
        updated = auth_store.get_profile(profile_id)
        assert updated["id"] == profile_id


class TestApiUiAuthProfileDelete:
    """删除档案 API 测试。"""

    def test_delete_success(self, client, auth_store: UiAuthProfileStore) -> None:
        """删除成功返回 ok。"""
        profile_id = auth_store.save_profile({
            "name": "待删除",
            "cookies": [],
        })

        resp = client.delete(f"/api/ui-testing/auth-profiles/{profile_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["ok"] is True

        # 验证已删除
        assert auth_store.get_profile(profile_id) is None

    def test_delete_nonexistent(self, client) -> None:
        """删除不存在的档案返回 404。"""
        resp = client.delete("/api/ui-testing/auth-profiles/nonexistent")
        assert resp.status_code == 404


class TestApiUiAuthProfileExport:
    """导出 storage_state API 测试。"""

    def test_export_success(self, client, auth_store: UiAuthProfileStore) -> None:
        """导出成功返回 storage_state。"""
        profile_id = auth_store.save_profile({
            "name": "导出测试",
            "base_url": "http://example.com",
            "cookies": [{"name": "session", "value": "abc123"}],
            "local_storage": {"token": "xyz"},
        })

        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}/export")
        assert resp.status_code == 200
        data = resp.get_json()
        state = data["data"]
        assert "cookies" in state
        assert "origins" in state

    def test_export_nonexistent(self, client) -> None:
        """导出不存在的档案返回 404。"""
        resp = client.get("/api/ui-testing/auth-profiles/nonexistent/export")
        assert resp.status_code == 404

    def test_export_expired(self, client, auth_store: UiAuthProfileStore) -> None:
        """导出过期档案返回 410。"""
        profile_id = auth_store.save_profile({
            "name": "过期档案",
            "base_url": "http://example.com",
            "cookies": [],
        })

        # 手动标记为过期
        profile = auth_store.get_profile(profile_id)
        profile["expires_at"] = "2020-01-01T00:00:00"
        auth_store.save_profile(profile)

        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}/export")
        assert resp.status_code == 410


class TestApiUiAuthProfilesCleanup:
    """清理过期档案 API 测试。"""

    def test_cleanup_success(self, client, auth_store: UiAuthProfileStore) -> None:
        """清理成功返回移除数量。"""
        # 创建一个过期档案
        profile_id = auth_store.save_profile({
            "name": "过期档案",
            "cookies": [],
        })
        profile = auth_store.get_profile(profile_id)
        profile["expires_at"] = "2020-01-01T00:00:00"
        auth_store.save_profile(profile)

        resp = client.post("/api/ui-testing/auth-profiles/cleanup")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["removed"] >= 1

    def test_cleanup_no_expired(self, client, auth_store: UiAuthProfileStore) -> None:
        """没有过期档案时返回 0。"""
        auth_store.save_profile({
            "name": "有效档案",
            "cookies": [],
        })

        resp = client.post("/api/ui-testing/auth-profiles/cleanup")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["removed"] == 0


class TestFullAuthProfileFlow:
    """完整认证档案流程集成测试。"""

    def test_crud_flow(self, client) -> None:
        """测试完整的 CRUD 流程。"""
        # 1. 创建
        resp = client.post(
            "/api/ui-testing/auth-profiles",
            json={
                "name": "流程测试档案",
                "base_url": "http://example.com",
                "cookies": [{"name": "session", "value": "abc123"}],
            },
        )
        assert resp.status_code == 201
        profile_id = resp.get_json()["data"]["id"]

        # 2. 获取
        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["name"] == "流程测试档案"

        # 3. 更新
        resp = client.put(
            f"/api/ui-testing/auth-profiles/{profile_id}",
            json={"name": "更新后的档案"},
        )
        assert resp.status_code == 200

        # 4. 验证更新
        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}")
        assert resp.get_json()["data"]["name"] == "更新后的档案"

        # 5. 导出
        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}/export")
        assert resp.status_code == 200

        # 6. 删除
        resp = client.delete(f"/api/ui-testing/auth-profiles/{profile_id}")
        assert resp.status_code == 200

        # 7. 验证删除
        resp = client.get(f"/api/ui-testing/auth-profiles/{profile_id}")
        assert resp.status_code == 404
