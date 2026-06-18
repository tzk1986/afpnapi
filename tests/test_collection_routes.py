"""collection_routes 单元测试。"""

import io
import json
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


SAMPLE_COLLECTION = {
    "info": {"name": "test", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "item": [
        {
            "name": "req1",
            "request": {
                "method": "GET",
                "url": {"raw": "https://example.com/api", "protocol": "https", "host": ["example", "com"], "path": ["api"]},
            },
        }
    ],
}


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Flask:
    """创建 Flask 测试应用。"""
    app = Flask(__name__)
    app.testing = True
    return app


def _register_routes(app: Flask) -> None:
    """注册 collection 路由到测试应用。"""
    from postman_api_tester.handlers.collection_routes import (
        api_collection_preview,
        api_export_collection,
        api_export_collection_stream,
    )

    app.add_url_rule("/api/collection-preview", "preview", api_collection_preview, methods=["POST"])
    app.add_url_rule("/api/export-collection", "export", api_export_collection, methods=["POST"])
    app.add_url_rule("/api/export-collection-stream", "export_stream", api_export_collection_stream, methods=["POST"])


class TestApiCollectionPreview:
    """collection-preview 端点测试。"""

    @patch("postman_api_tester.handlers.collection_routes.ENABLE_SELECTIVE_RUN", False)
    def test_disabled_returns_col_preview_001(self, app: Flask) -> None:
        """功能未启用返回 403 + COL_PREVIEW_001。"""
        _register_routes(app)
        resp = app.test_client().post("/api/collection-preview", content_type="multipart/form-data")
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error_code"] == "COL_PREVIEW_001"

    @patch("postman_api_tester.handlers.collection_routes.ENABLE_SELECTIVE_RUN", True)
    def test_no_file_returns_col_preview_002(self, app: Flask) -> None:
        """未上传文件返回 400 + COL_PREVIEW_002。"""
        _register_routes(app)
        resp = app.test_client().post("/api/collection-preview", content_type="multipart/form-data")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "COL_PREVIEW_002"

    @patch("postman_api_tester.handlers.collection_routes.ENABLE_SELECTIVE_RUN", True)
    def test_non_json_file_returns_col_preview_003(self, app: Flask) -> None:
        """非 .json 文件返回 400 + COL_PREVIEW_003。"""
        _register_routes(app)
        data = {"collection_file": (io.BytesIO(b"{}"), "test.txt")}
        resp = app.test_client().post(
            "/api/collection-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        resp_data = resp.get_json()
        assert resp_data["error_code"] == "COL_PREVIEW_003"

    @patch("postman_api_tester.handlers.collection_routes.ENABLE_SELECTIVE_RUN", True)
    def test_invalid_json_returns_col_preview_004(self, app: Flask) -> None:
        """无效 JSON 返回 400 + COL_PREVIEW_004。"""
        _register_routes(app)
        data = {"collection_file": (io.BytesIO(b"{bad json}"), "test.json")}
        resp = app.test_client().post(
            "/api/collection-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        resp_data = resp.get_json()
        assert resp_data["error_code"] == "COL_PREVIEW_004"

    @patch("postman_api_tester.handlers.collection_routes.ENABLE_SELECTIVE_RUN", True)
    @patch(
        "postman_api_tester.handlers.collection_routes._svc_extract_collection_preview_items",
        return_value=[{"name": "req1", "method": "GET"}],
    )
    def test_success(self, mock_extract: MagicMock, app: Flask) -> None:
        """有效文件预览成功。"""
        _register_routes(app)
        content = json.dumps(SAMPLE_COLLECTION).encode("utf-8")
        data = {"collection_file": (io.BytesIO(content), "test.json")}
        resp = app.test_client().post(
            "/api/collection-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        resp_data = resp.get_json()
        assert "items" in resp_data or "preview_items" in resp_data or "total" in resp_data


class TestApiExportCollection:
    """export-collection 端点测试。"""

    def test_empty_report_name_returns_col_export_001(self, app: Flask) -> None:
        """report_name 为空返回 400 + COL_EXPORT_001。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection",
            data=json.dumps({"report_name": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "COL_EXPORT_001"

    @patch("postman_api_tester.report_repository.find_report", side_effect=FileNotFoundError())
    def test_report_not_found_returns_col_export_002(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404 + COL_EXPORT_002。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection",
            data=json.dumps({"report_name": "nonexistent"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error_code"] == "COL_EXPORT_002"

    @patch("postman_api_tester.report_repository.find_report", return_value=MagicMock())
    @patch(
        "postman_api_tester.handlers.collection_routes._svc_export_collection_with_latest_params",
        side_effect=ValueError("export failed"),
    )
    def test_export_exception_returns_col_export_003(
        self, mock_export: MagicMock, mock_find: MagicMock, app: Flask
    ) -> None:
        """导出异常返回 400 + COL_EXPORT_003。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection",
            data=json.dumps({"report_name": "test_report"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "COL_EXPORT_003"

    @patch("postman_api_tester.report_repository.find_report", return_value=MagicMock())
    @patch(
        "postman_api_tester.handlers.collection_routes._svc_export_collection_with_latest_params",
        return_value={
            "file_path": "/tmp/test.json",
            "file_name": "test.json",
            "export_scope": "full",
            "updated_count": 1,
            "skipped_count": 0,
            "report_only_count": 0,
            "warnings": [],
        },
    )
    def test_success(self, mock_export: MagicMock, mock_find: MagicMock, app: Flask) -> None:
        """导出成功。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection",
            data=json.dumps({"report_name": "test_report"}),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestApiExportCollectionStream:
    """export-collection-stream 端点测试。"""

    def test_empty_report_name_returns_col_export_001(self, app: Flask) -> None:
        """report_name 为空返回 400 + COL_EXPORT_001。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection-stream",
            data=json.dumps({"report_name": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "COL_EXPORT_001"

    @patch("postman_api_tester.report_repository.find_report", side_effect=FileNotFoundError())
    def test_report_not_found_returns_col_export_002(self, mock_find: MagicMock, app: Flask) -> None:
        """报告不存在返回 404 + COL_EXPORT_002。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection-stream",
            data=json.dumps({"report_name": "nonexistent"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error_code"] == "COL_EXPORT_002"

    @patch("postman_api_tester.report_repository.find_report", return_value=MagicMock())
    @patch(
        "postman_api_tester.handlers.collection_routes._svc_export_collection_with_latest_params",
        side_effect=ValueError("export failed"),
    )
    def test_export_exception_returns_col_export_003(
        self, mock_export: MagicMock, mock_find: MagicMock, app: Flask
    ) -> None:
        """导出异常返回 400 + COL_EXPORT_003。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/export-collection-stream",
            data=json.dumps({"report_name": "test_report"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "COL_EXPORT_003"
