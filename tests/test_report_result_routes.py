"""report_result_routes 单元测试。"""

import json
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Flask:
    """创建 Flask 测试应用。"""
    app = Flask(__name__)
    app.testing = True
    return app


def _register_routes(app: Flask) -> None:
    """注册 report_result 路由到测试应用。"""
    from postman_api_tester.handlers.report_result_routes import (
        api_compare,
        api_report_analytics,
        api_report_analytics_compare,
        api_report_result_detail,
        api_report_results,
    )

    app.add_url_rule("/api/report-results/<report_name>", "results", api_report_results)
    app.add_url_rule("/api/report-analytics/<report_name>", "analytics", api_report_analytics)
    app.add_url_rule("/api/report-analytics-compare", "analytics_compare", api_report_analytics_compare)
    app.add_url_rule("/api/report-results/<report_name>/<int:result_index>", "detail", api_report_result_detail)
    app.add_url_rule("/api/compare", "compare", api_compare)


class TestApiReportResults:
    """report-results 端点测试。"""

    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", side_effect=FileNotFoundError())
    def test_report_not_found(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-results/nonexistent")
        assert resp.status_code == 404

    @patch(
        "postman_api_tester.handlers.report_result_routes._build_report_results_payload",
        return_value={"results": [], "total": 0, "page": 1},
    )
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", return_value={"report_name": "test"})
    def test_success(self, mock_find: MagicMock, mock_payload: MagicMock, app: Flask) -> None:
        """成功返回结果列表。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-results/test_report")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data

    @patch(
        "postman_api_tester.handlers.report_result_routes._build_report_results_payload",
        return_value={"results": [], "total": 0, "page": 2},
    )
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", return_value={"report_name": "test"})
    def test_with_pagination(self, mock_find: MagicMock, mock_payload: MagicMock, app: Flask) -> None:
        """分页参数正确传递。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-results/test_report?page=2&page_size=10")
        assert resp.status_code == 200


class TestApiReportAnalytics:
    """report-analytics 端点测试。"""

    @patch("postman_api_tester.handlers.report_result_routes.ENABLE_REPORT_ANALYTICS", False)
    def test_disabled_returns_403(self, app: Flask) -> None:
        """功能未启用返回 403。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-analytics/test_report")
        assert resp.status_code == 403

    @patch("postman_api_tester.handlers.report_result_routes.ENABLE_REPORT_ANALYTICS", True)
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", side_effect=FileNotFoundError())
    def test_report_not_found(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-analytics/nonexistent")
        assert resp.status_code == 404

    @patch("postman_api_tester.handlers.report_result_routes._repo_list_reports", return_value=[])
    @patch(
        "postman_api_tester.handlers.report_result_routes._build_analytics_payload",
        return_value={"top_n": [], "trend": []},
    )
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", return_value={"report_name": "test"})
    @patch("postman_api_tester.handlers.report_result_routes.ENABLE_REPORT_ANALYTICS", True)
    def test_success(
        self, mock_find: MagicMock, mock_payload: MagicMock, mock_list: MagicMock, app: Flask
    ) -> None:
        """成功返回分析数据。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-analytics/test_report")
        assert resp.status_code == 200


class TestApiReportAnalyticsCompare:
    """report-analytics-compare 端点测试。"""

    @patch("postman_api_tester.handlers.report_result_routes.ENABLE_REPORT_ANALYTICS", False)
    def test_disabled_returns_403(self, app: Flask) -> None:
        """功能未启用返回 403。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-analytics-compare?left=a&right=b")
        assert resp.status_code == 403

    @patch("postman_api_tester.handlers.report_result_routes.ENABLE_REPORT_ANALYTICS", True)
    def test_missing_params_returns_400(self, app: Flask) -> None:
        """缺少参数返回 400。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-analytics-compare")
        assert resp.status_code == 400

    @patch("postman_api_tester.handlers.report_result_routes.ENABLE_REPORT_ANALYTICS", True)
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", side_effect=FileNotFoundError())
    def test_report_not_found(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-analytics-compare?left=nonexistent&right=also_missing")
        assert resp.status_code == 404


class TestApiReportResultDetail:
    """report-result-detail 端点测试。"""

    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", side_effect=FileNotFoundError())
    def test_report_not_found(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-results/nonexistent/0")
        assert resp.status_code == 404

    @patch(
        "postman_api_tester.handlers.report_result_routes.build_result_detail_payload",
        return_value={"request_info": {}, "response_info": {}},
    )
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", return_value={"report_name": "test"})
    def test_success(self, mock_find: MagicMock, mock_detail: MagicMock, app: Flask) -> None:
        """成功返回结果详情。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-results/test_report/0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "request_info" in data or "response_info" in data

    @patch(
        "postman_api_tester.handlers.report_result_routes.build_result_detail_payload",
        side_effect=IndexError(),
    )
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", return_value={"report_name": "test"})
    def test_index_not_found(self, mock_find: MagicMock, mock_detail: MagicMock, app: Flask) -> None:
        """结果索引不存在返回 404。"""
        _register_routes(app)
        resp = app.test_client().get("/api/report-results/test_report/999")
        assert resp.status_code == 404


class TestApiCompare:
    """compare 端点测试。"""

    def test_missing_params_returns_400(self, app: Flask) -> None:
        """缺少参数返回 400。"""
        _register_routes(app)
        resp = app.test_client().get("/api/compare")
        assert resp.status_code == 400

    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", side_effect=FileNotFoundError())
    def test_report_not_found(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404。"""
        _register_routes(app)
        resp = app.test_client().get("/api/compare?left=nonexistent&right=also_missing")
        assert resp.status_code == 404

    @patch(
        "postman_api_tester.handlers.report_result_routes.build_compare_payload",
        return_value={"left": {}, "right": {}},
    )
    @patch("postman_api_tester.handlers.report_result_routes._repo_find_report", return_value={"report_name": "test"})
    def test_success(self, mock_find: MagicMock, mock_payload: MagicMock, app: Flask) -> None:
        """成功返回对比数据。"""
        _register_routes(app)
        resp = app.test_client().get("/api/compare?left=report_a&right=report_b")
        assert resp.status_code == 200
