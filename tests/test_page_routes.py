"""page_routes 单元测试。

覆盖页面渲染路由的正常/边界/异常路径。
"""

import json
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.page_routes import (
    adhoc_run_page,
    collection_editor_page,
    index,
    report_view,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Flask:
    """创建测试用 Flask 应用。"""
    test_app = Flask(__name__, template_folder="../../templates")
    test_app.config["TESTING"] = True

    @test_app.route("/", endpoint="index")
    def _index_stub():
        return "index"

    @test_app.route("/report-view", endpoint="report_view")
    def _report_view_stub():
        return "report_view"

    return test_app


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context(app: Flask) -> Generator[None, None, None]:
    """提供 Flask 应用上下文。"""
    with app.test_request_context():
        yield


@pytest.fixture  # type: ignore[untyped-decorator]
def app_with_request(app: Flask) -> Flask:
    """提供带请求上下文的 Flask 应用。"""
    return app


class TestIndex:
    """首页路由测试。"""

    def test_index_renders_template(self, app_context: None) -> None:
        """index 应渲染 index.html 模板。"""
        with patch("postman_api_tester.handlers.page_routes._repo_list_reports") as mock_list:
            mock_list.return_value = []
            with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                mock_render.return_value = "<html>index</html>"
                result = index()

                assert result == "<html>index</html>"
                mock_render.assert_called_once()
                call_kwargs = mock_render.call_args[1]
                assert call_kwargs["host_name"]
                assert "run_results_per_page_default" in call_kwargs
                assert "enable_selective_run" in call_kwargs

    def test_index_passes_reports_json(self, app_context: None) -> None:
        """index 应传递 reports_json。"""
        with patch("postman_api_tester.handlers.page_routes._repo_list_reports") as mock_list:
            mock_list.return_value = [{"report_name": "test"}]
            with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                mock_render.return_value = "<html></html>"
                index()

                call_kwargs = mock_render.call_args[1]
                reports_data = json.loads(call_kwargs["reports_json"])
                assert len(reports_data) == 1
                assert reports_data[0]["report_name"] == "test"

    def test_index_passes_environments_json(self, app_context: None) -> None:
        """index 应传递 environments_json。"""
        with patch("postman_api_tester.handlers.page_routes._repo_list_reports") as mock_list:
            mock_list.return_value = []
            with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                mock_render.return_value = ""
                with patch("postman_api_tester.handlers.page_routes.ENVIRONMENTS", {"dev": {}, "prod": {}}):
                    index()
                    call_kwargs = mock_render.call_args[1]
                    envs = json.loads(call_kwargs["environments_json"])
                    assert "dev" in envs
                    assert "prod" in envs


class TestAdhocRunPage:
    """Ad-hoc 测试页面路由测试。"""

    def test_adhoc_page_redirects_when_disabled(self, app_context: None) -> None:
        """ENABLE_ADHOC_RUN=false 时应重定向到首页。"""
        with patch("postman_api_tester.handlers.page_routes.ENABLE_ADHOC_RUN", False):
            result = adhoc_run_page()
            assert result.status_code == 302

    def test_adhoc_page_renders_when_enabled(self, app_context: None) -> None:
        """ENABLE_ADHOC_RUN=true 时应渲染模板。"""
        with patch("postman_api_tester.handlers.page_routes.ENABLE_ADHOC_RUN", True):
            with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                mock_render.return_value = "<html>adhoc</html>"
                result = adhoc_run_page()

                assert result == "<html>adhoc</html>"
                mock_render.assert_called_once()
                call_kwargs = mock_render.call_args[1]
                assert "adhoc_max_items" in call_kwargs
                assert "enable_assertions" in call_kwargs

    def test_adhoc_page_passes_config_values(self, app_context: None) -> None:
        """adhoc 页面应传递配置值。"""
        with patch("postman_api_tester.handlers.page_routes.ENABLE_ADHOC_RUN", True):
            with patch("postman_api_tester.handlers.page_routes.ADHOC_MAX_ITEMS", 50):
                with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                    mock_render.return_value = ""
                    adhoc_run_page()
                    call_kwargs = mock_render.call_args[1]
                    assert call_kwargs["adhoc_max_items"] == 50


class TestCollectionEditorPage:
    """Collection 编辑器页面路由测试。"""

    def test_renders_collection_editor_template(self, app_context: None) -> None:
        """应渲染 collection_editor.html。"""
        with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
            mock_render.return_value = "<html>editor</html>"
            result = collection_editor_page()

            assert result == "<html>editor</html>"
            mock_render.assert_called_once_with("collection_editor.html")


class TestReportView:
    """报告详情页路由测试。"""

    def test_redirects_to_first_report_when_no_name(self, app_context: None) -> None:
        """无 name 参数时应重定向到第一个报告。"""
        with patch("postman_api_tester.handlers.page_routes._repo_list_reports") as mock_list:
            mock_list.return_value = [{"report_name": "first_report"}]
            result = report_view()
            assert result.status_code == 302

    def test_redirects_to_index_when_no_reports(self, app_context: None) -> None:
        """无报告时重定向到首页。"""
        with patch("postman_api_tester.handlers.page_routes._repo_list_reports") as mock_list:
            mock_list.return_value = []
            with patch("postman_api_tester.handlers.page_routes.request") as mock_request:
                mock_request.args = {"name": ""}
                result = report_view()
                assert result.status_code == 302

    def test_returns_404_when_report_not_found(self, app_context: None) -> None:
        """报告不存在时返回 404。"""
        with patch("postman_api_tester.handlers.page_routes.request") as mock_request:
            mock_request.args = {"name": "nonexistent"}
            with patch("postman_api_tester.handlers.page_routes._repo_find_report") as mock_find:
                mock_find.side_effect = FileNotFoundError("not found")
                with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                    mock_render.return_value = "<html>not found</html>"
                    result = report_view()
                    assert result[1] == 404

    def test_renders_report_view_template(self, app_context: None) -> None:
        """应渲染 report_view.html。"""
        with patch("postman_api_tester.handlers.page_routes.request") as mock_request:
            mock_request.args = {"name": "my_report"}
            with patch("postman_api_tester.handlers.page_routes._repo_find_report") as mock_find:
                mock_find.return_value = {
                    "report_name": "my_report",
                    "collection_name": "Test Collection",
                    "source_file": "/path/to/file.json",
                    "generated_at": "2026-06-25 20:30:00",
                    "summary": {"total": 10, "passed": 8},
                }
                with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                    mock_render.return_value = "<html>report</html>"
                    with patch("postman_api_tester.handlers.page_routes.make_response") as mock_response:
                        mock_resp = MagicMock()
                        mock_resp.headers = {}
                        mock_response.return_value = mock_resp
                        result = report_view()

                        mock_render.assert_called_once()
                        call_kwargs = mock_render.call_args[1]
                        assert call_kwargs["report_name"] == "my_report"
                        assert call_kwargs["collection_name"] == "Test Collection"

    def test_report_view_sets_no_cache_headers(self, app_context: None) -> None:
        """报告详情页应设置 no-cache 头。"""
        with patch("postman_api_tester.handlers.page_routes.request") as mock_request:
            mock_request.args = {"name": "test_report"}
            with patch("postman_api_tester.handlers.page_routes._repo_find_report") as mock_find:
                mock_find.return_value = {
                    "report_name": "test_report",
                    "collection_name": "",
                    "source_file": "",
                    "generated_at": "",
                    "summary": {},
                }
                with patch("postman_api_tester.handlers.page_routes.render_template") as mock_render:
                    mock_render.return_value = "<html></html>"
                    with patch("postman_api_tester.handlers.page_routes.make_response") as mock_response:
                        mock_resp = MagicMock()
                        mock_resp.headers = {}
                        mock_response.return_value = mock_resp
                        report_view()

                        headers = mock_resp.headers
                        assert "no-store" in headers.get("Cache-Control", "")
                        assert headers.get("Pragma") == "no-cache"
                        assert headers.get("Expires") == "0"
