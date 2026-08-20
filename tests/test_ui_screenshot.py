"""UI 截图保存接口单元测试。"""

import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch, MagicMock

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


def _mock_convert_html_to_png_success(html_path: Path, png_path: Path, base_url: str = "") -> None:
    """Mock PNG 转换成功：创建一个假的 PNG 文件。"""
    # PNG 文件头
    png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    png_path.write_bytes(png_data)


def _mock_convert_html_to_png_failure(html_path: Path, png_path: Path, base_url: str = "") -> None:
    """Mock PNG 转换失败：抛出异常。"""
    raise RuntimeError("Playwright not available")


def _mock_convert_url_to_png_success(url: str, png_path: Path) -> None:
    """Mock URL 截图成功：创建一个假的 PNG 文件。"""
    # PNG 文件头
    png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    png_path.write_bytes(png_data)


def _mock_convert_url_to_png_failure(url: str, png_path: Path) -> None:
    """Mock URL 截图失败：抛出异常。"""
    raise RuntimeError("Playwright not available")


def test_screenshot_save_as_png_passed(temp_screenshot_dir, client):
    """测试成功步骤截图保存为 PNG。"""
    job_id = "test_job_png_passed"
    step_index = 3
    html_content = "<html><body>Passed step</body></html>"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_success
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图失败，回退到 HTML

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

    # 验证 PNG 文件保存为 step_N.png
    png_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}.png"
    assert png_path.exists()

    # 验证临时 HTML 文件已删除
    temp_html = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_temp.html"
    assert not temp_html.exists()


def test_screenshot_save_as_png_failed(temp_screenshot_dir, client):
    """测试失败步骤截图保存为 PNG。"""
    job_id = "test_job_png_failed"
    step_index = 5
    html_content = "<html><body>Failed step</body></html>"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_success
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图失败，回退到 HTML

        response = client.post(
            f"/api/ui-testing/execution/{job_id}/screenshot",
            json={
                "step_index": step_index,
                "html": html_content,
                "status": "failed",
            },
        )

    assert response.status_code == 200

    # 验证 PNG 文件保存为 step_N_fail.png
    png_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_fail.png"
    assert png_path.exists()


def test_screenshot_fallback_to_html_on_failure(temp_screenshot_dir, client):
    """测试 PNG 转换失败时回退到保存 HTML。"""
    job_id = "test_job_fallback"
    step_index = 7
    html_content = "<html><body>Fallback screenshot</body></html>"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_failure
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图也失败

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

    # 验证 HTML 文件保存为 step_N.html
    html_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}.html"
    assert html_path.exists()
    assert html_path.read_text(encoding="utf-8") == html_content

    # 验证没有 PNG 文件
    png_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}.png"
    assert not png_path.exists()


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
    assert not screenshot_dir.exists()


def test_screenshot_missing_html_returns_ok(temp_screenshot_dir, client):
    """测试缺少 html 内容和 page_url 返回 ok（不保存文件）。"""
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

    # 验证没有保存截图文件（既没有 PNG 也没有 HTML）
    screenshot_dir = temp_screenshot_dir / f"exec_{job_id}" / "screenshots"
    if screenshot_dir.exists():
        # 目录可能被创建但没有文件
        files = list(screenshot_dir.iterdir())
        assert len(files) == 0, f"Expected no files, but found: {files}"


def test_screenshot_get_png_passed(temp_screenshot_dir, client):
    """测试获取成功步骤的 PNG 截图。"""
    job_id = "test_get_png_passed"
    step_index = 2
    html_content = "<html><body>Passed screenshot</body></html>"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_success
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图失败，回退到 HTML

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
    assert response.content_type == "image/png"


def test_screenshot_get_png_failed(temp_screenshot_dir, client):
    """测试获取失败步骤的 PNG 截图。"""
    job_id = "test_get_png_failed"
    step_index = 4
    html_content = "<html><body>Failed screenshot</body></html>"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_success
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图失败，回退到 HTML

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
    assert response.content_type == "image/png"


def test_screenshot_get_html_fallback(temp_screenshot_dir, client):
    """测试获取 HTML fallback 截图（PNG 转换失败时）。"""
    job_id = "test_get_html_fallback"
    step_index = 6
    html_content = "<html><body>HTML fallback screenshot</body></html>"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_failure
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图也失败

        # 先保存截图（会回退到 HTML）
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

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_html_to_png") as mock_convert, \
         patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_convert.side_effect = _mock_convert_html_to_png_success
        mock_url_convert.side_effect = _mock_convert_url_to_png_failure  # URL 截图失败，回退到 HTML

        # 不传递 status 参数
        response = client.post(
            f"/api/ui-testing/execution/{job_id}/screenshot",
            json={
                "step_index": step_index,
                "html": html_content,
            },
        )

    assert response.status_code == 200

    # 验证 PNG 文件保存为 step_N_fail.png（默认行为）
    png_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_fail.png"
    assert png_path.exists()


def test_screenshot_url_priority(temp_screenshot_dir, client):
    """测试 URL 截图优先级：当 page_url 可用时优先使用 URL 截图。"""
    job_id = "test_url_priority"
    step_index = 2
    html_content = "<html><body>URL priority screenshot</body></html>"
    page_url = "http://example.com/page"

    with patch("postman_api_tester.handlers.ui_execution_routes._convert_url_to_png") as mock_url_convert:
        mock_url_convert.side_effect = _mock_convert_url_to_png_success

        response = client.post(
            f"/api/ui-testing/execution/{job_id}/screenshot",
            json={
                "step_index": step_index,
                "html": html_content,
                "page_url": page_url,
                "status": "passed",
            },
        )

    assert response.status_code == 200

    # 验证 PNG 文件保存
    png_path = temp_screenshot_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}.png"
    assert png_path.exists()

    # 验证使用了 URL 截图方式
    mock_url_convert.assert_called_once_with(page_url, png_path)
