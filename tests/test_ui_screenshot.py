"""UI 截图保存接口单元测试。"""

import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask

from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_screenshot_post,
    api_ui_testing_execution_screenshot,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Generator[Flask, None, None]:
    """提供 Flask 测试应用（注册截图路由）。"""
    app = Flask(__name__)
    app.config["TESTING"] = True

    app.add_url_rule(
        "/api/ui-testing/execution/<job_id>/screenshot",
        "api_ui_testing_execution_screenshot_post",
        api_ui_testing_execution_screenshot_post,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/ui-testing/execution/<job_id>/screenshot/<int:step_index>",
        "api_ui_testing_execution_screenshot",
        api_ui_testing_execution_screenshot,
        methods=["GET"],
    )

    yield app


@pytest.fixture  # type: ignore[untyped-decorator]
def client(app: Flask):
    """Flask 测试客户端。"""
    return app.test_client()


@pytest.fixture  # type: ignore[untyped-decorator]
def temp_screenshot_dir():
    """临时截图目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("postman_api_tester.handlers.ui_execution_routes._execution_store") as mock_store:
            mock_store.base_dir = Path(tmpdir)
            yield Path(tmpdir)


def test_screenshot_save_failed_step(temp_screenshot_dir, client):
    """测试失败步骤截图保存为 step_N_fail.html。"""
    job_id = "test_job_123"
    step_index = 5
    html_content = "<html><body>Failed step</body></html>"

    # 保存失败步骤截图（默认状态为 failed）
    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": step_index,
            "html": html_content,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["ok"] is True

    # 验证文件保存为 step_N_fail.html
    screenshot_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_fail.html"
    assert screenshot_path.exists()
    assert screenshot_path.read_text(encoding="utf-8") == html_content


def test_screenshot_save_passed_step(temp_screenshot_dir, client):
    """测试成功步骤截图保存为 step_N.html。"""
    job_id = "test_job_456"
    step_index = 3
    html_content = "<html><body>Passed step</body></html>"

    # 保存成功步骤截图
    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": step_index,
            "html": html_content,
            "status": "passed",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["ok"] is True

    # 验证文件保存为 step_N.html（不带 _fail 后缀）
    screenshot_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}.html"
    assert screenshot_path.exists()
    assert screenshot_path.read_text(encoding="utf-8") == html_content


def test_screenshot_save_explicit_failed_step(temp_screenshot_dir, client):
    """测试明确指定 failed 状态的步骤截图保存为 step_N_fail.html。"""
    job_id = "test_job_789"
    step_index = 7
    html_content = "<html><body>Failed step explicit</body></html>"

    # 明确指定 status 为 failed
    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": step_index,
            "html": html_content,
            "status": "failed",
        },
    )

    assert response.status_code == 200

    # 验证文件保存为 step_N_fail.html
    screenshot_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_fail.html"
    assert screenshot_path.exists()


def test_screenshot_empty_payload_returns_ok(temp_screenshot_dir, client):
    """测试空 payload 返回 ok。"""
    job_id = "test_job_empty"

    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["ok"] is True


def test_screenshot_missing_step_index_returns_ok(temp_screenshot_dir, client):
    """测试缺少 step_index 返回 ok（不保存文件）。"""
    job_id = "test_job_no_index"

    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "html": "<html>test</html>",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["ok"] is True

    # 验证没有保存文件
    screenshot_dir = temp_screenshot_dir / f"exec_{job_id}" / "screenshots"
    assert not screenshot_dir.exists() or len(list(screenshot_dir.glob("*.html"))) == 0


def test_screenshot_missing_html_returns_ok(temp_screenshot_dir, client):
    """测试缺少 html 内容返回 ok（不保存文件）。"""
    job_id = "test_job_no_html"

    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["ok"] is True

    # 验证没有保存文件
    screenshot_dir = temp_screenshot_dir / f"exec_{job_id}" / "screenshots"
    assert not screenshot_dir.exists() or len(list(screenshot_dir.glob("*.html"))) == 0


def test_screenshot_get_passed_step(temp_screenshot_dir, client):
    """测试获取成功步骤截图。"""
    job_id = "test_get_passed"
    step_index = 2
    html_content = "<html><body>Passed screenshot</body></html>"

    # 先保存截图
    client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": step_index,
            "html": html_content,
            "status": "passed",
        },
    )

    # 获取截图
    response = client.get(f"/api/ui-testing/execution/{job_id}/screenshot/{step_index}")
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert html_content in response.get_data(as_text=True)


def test_screenshot_get_failed_step(temp_screenshot_dir, client):
    """测试获取失败步骤截图。"""
    job_id = "test_get_failed"
    step_index = 4
    html_content = "<html><body>Failed screenshot</body></html>"

    # 先保存截图
    client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": step_index,
            "html": html_content,
            "status": "failed",
        },
    )

    # 获取截图
    response = client.get(f"/api/ui-testing/execution/{job_id}/screenshot/{step_index}")
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert html_content in response.get_data(as_text=True)


def test_screenshot_get_nonexistent_returns_404(temp_screenshot_dir, client):
    """测试获取不存在的截图返回 404。"""
    job_id = "test_get_nonexistent"
    step_index = 999

    response = client.get(f"/api/ui-testing/execution/{job_id}/screenshot/{step_index}")
    assert response.status_code == 404


def test_screenshot_backward_compatibility(temp_screenshot_dir, client):
    """测试向后兼容性：未传递 status 时默认为 failed。"""
    job_id = "test_backward_compat"
    step_index = 1
    html_content = "<html><body>Legacy screenshot</body></html>"

    # 不传递 status 参数
    response = client.post(
        f"/api/ui-testing/execution/{job_id}/screenshot",
        json={
            "step_index": step_index,
            "html": html_content,
        },
    )

    assert response.status_code == 200

    # 验证文件保存为 step_N_fail.html（默认行为）
    screenshot_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_fail.html"
    assert screenshot_path.exists()
    assert screenshot_path.read_text(encoding="utf-8") == html_content
