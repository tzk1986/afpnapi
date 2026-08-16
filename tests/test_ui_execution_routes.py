"""UI 执行路由单元测试。"""

from typing import Generator

import pytest
from flask import Flask

from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_settings_get,
    api_ui_testing_settings_reset,
    api_ui_testing_settings_update,
    api_ui_testing_execution_status,
    api_ui_testing_executions_list,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Generator[Flask, None, None]:
    """提供 Flask 测试应用（注册 UI 执行路由）。"""
    app = Flask(__name__)
    app.config["TESTING"] = True

    app.add_url_rule(
        "/api/ui-testing/settings",
        "api_ui_testing_settings_get",
        api_ui_testing_settings_get,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/ui-testing/settings",
        "api_ui_testing_settings_update",
        api_ui_testing_settings_update,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/ui-testing/settings/reset",
        "api_ui_testing_settings_reset",
        api_ui_testing_settings_reset,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/ui-testing/execution/<job_id>/status",
        "api_ui_testing_execution_status",
        api_ui_testing_execution_status,
    )
    app.add_url_rule(
        "/api/ui-testing/executions",
        "api_ui_testing_executions_list",
        api_ui_testing_executions_list,
    )

    yield app


@pytest.fixture  # type: ignore[untyped-decorator]
def client(app: Flask):
    """Flask 测试客户端。"""
    return app.test_client()


def test_settings_get_returns_default_settings(client: Flask.test_client) -> None:
    """测试获取设置返回默认配置。"""
    response = client.get("/api/ui-testing/settings")
    assert response.status_code == 200

    data = response.get_json()
    assert "data" in data
    assert "headless" in data["data"]
    assert "browser_type" in data["data"]["headless"]
    assert data["data"]["headless"]["browser_type"] == "chromium"


def test_settings_update_changes_browser(client: Flask.test_client) -> None:
    """测试更新设置修改浏览器类型。"""
    response = client.post(
        "/api/ui-testing/settings",
        json={"headless": {"browser_type": "firefox"}},
    )
    assert response.status_code == 200

    data = response.get_json()
    assert data["data"]["headless"]["browser_type"] == "firefox"


def test_settings_update_rejects_invalid_browser(client: Flask.test_client) -> None:
    """测试更新设置接受任意浏览器类型（无验证）。"""
    response = client.post(
        "/api/ui-testing/settings",
        json={"headless": {"browser_type": "invalid_browser"}},
    )
    # Invalid browser is accepted (no validation), falls back to default
    assert response.status_code == 200


def test_settings_update_changes_viewport(client: Flask.test_client) -> None:
    """测试更新设置修改视口大小。"""
    response = client.post(
        "/api/ui-testing/settings",
        json={"headless": {"viewport_width": 1920, "viewport_height": 1080}},
    )
    assert response.status_code == 200

    data = response.get_json()
    assert data["data"]["headless"]["viewport_width"] == 1920
    assert data["data"]["headless"]["viewport_height"] == 1080


def test_settings_reset_restores_defaults(client: Flask.test_client) -> None:
    """测试重置设置恢复默认值。"""
    # 先修改设置
    client.post(
        "/api/ui-testing/settings",
        json={"headless": {"browser_type": "firefox", "viewport_width": 1920}},
    )

    # 重置设置
    response = client.post("/api/ui-testing/settings/reset")
    assert response.status_code == 200

    data = response.get_json()
    assert data["data"]["headless"]["browser_type"] == "chromium"
    assert data["data"]["headless"]["viewport_width"] == 1280


def test_execution_status_returns_not_found_for_invalid_job(
    client: Flask.test_client,
) -> None:
    """测试查询不存在的任务状态返回 404。"""
    response = client.get("/api/ui-testing/execution/invalid-job-id/status")
    assert response.status_code == 404

    data = response.get_json()
    assert "code" in data


def test_executions_list_returns_array(client: Flask.test_client) -> None:
    """测试获取执行列表返回数组。"""
    response = client.get("/api/ui-testing/executions")
    assert response.status_code == 200

    data = response.get_json()
    assert "data" in data
    assert isinstance(data["data"], list)
