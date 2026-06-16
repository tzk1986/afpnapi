"""collection_editor_routes 单元测试。"""

import io
import json
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.collection_editor_routes import (
    api_collection_dependency,
    api_collection_parse,
    api_collection_save,
    api_collection_send,
)


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


@pytest.fixture  # type: ignore[untyped-decorator]
def client(app: Flask) -> Generator:
    """创建测试客户端。"""
    with app.test_client() as client:
        yield client


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 请求上下文。"""
    app = Flask(__name__)
    with app.test_request_context():
        yield


def _register_routes(app: Flask) -> None:
    """注册 collection editor 路由到测试应用。"""
    app.add_url_rule("/api/collection-editor/parse", "parse", api_collection_parse, methods=["POST"])
    app.add_url_rule("/api/collection-editor/save", "save", api_collection_save, methods=["PUT"])
    app.add_url_rule("/api/collection-editor/dependency", "dependency", api_collection_dependency, methods=["POST"])
    app.add_url_rule("/api/collection-editor/send", "send", api_collection_send, methods=["POST"])


class TestApiCollectionParse:
    """parse 端点测试。"""

    def test_missing_field_returns_ce_parse_001(self, app: Flask) -> None:
        """缺少 collection_json 字段返回 400 + CE_PARSE_001。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/parse",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_PARSE_001"

    def test_non_dict_returns_ce_parse_002(self, app: Flask) -> None:
        """非 dict 类型返回 400 + CE_PARSE_002。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/parse",
            data=json.dumps({"collection_json": "not_a_dict"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_PARSE_002"

    def test_invalid_json_file_returns_ce_parse_003(self, app: Flask) -> None:
        """无效 JSON 文件返回 400 + CE_PARSE_003。"""
        _register_routes(app)
        data = {"file": (io.BytesIO(b"{bad json"), "test.json")}
        resp = app.test_client().post(
            "/api/collection-editor/parse",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        resp_data = resp.get_json()
        assert resp_data["error_code"] == "CE_PARSE_003"

    @patch(
        "postman_api_tester.services.collection_editor_service.parse_collection_to_flat",
        return_value={"groups": [], "allRequests": []},
    )
    def test_success_with_json_body(self, mock_parse: MagicMock, app: Flask) -> None:
        """有效 JSON body 解析成功。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/parse",
            data=json.dumps({"collection_json": SAMPLE_COLLECTION}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "groups" in data
        mock_parse.assert_called_once_with(SAMPLE_COLLECTION)

    @patch(
        "postman_api_tester.services.collection_editor_service.parse_collection_to_flat",
        return_value={"groups": [], "allRequests": []},
    )
    def test_success_with_file_upload(self, mock_parse: MagicMock, app: Flask) -> None:
        """文件上传解析成功。"""
        _register_routes(app)
        content = json.dumps(SAMPLE_COLLECTION).encode("utf-8")
        data = {"file": (io.BytesIO(content), "test.json")}
        resp = app.test_client().post(
            "/api/collection-editor/parse",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        mock_parse.assert_called_once()

    @patch(
        "postman_api_tester.services.collection_editor_service.parse_collection_to_flat",
        side_effect=RuntimeError("unexpected"),
    )
    def test_service_exception_returns_ce_parse_004(self, mock_parse: MagicMock, app: Flask) -> None:
        """服务层异常返回 500 + CE_PARSE_004。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/parse",
            data=json.dumps({"collection_json": SAMPLE_COLLECTION}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["error_code"] == "CE_PARSE_004"


class TestApiCollectionSave:
    """save 端点测试。"""

    def test_missing_body_returns_ce_save_001(self, app: Flask) -> None:
        """缺少请求体返回 400 + CE_SAVE_001。"""
        _register_routes(app)
        resp = app.test_client().put(
            "/api/collection-editor/save",
            data="",
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_SAVE_001"

    @patch(
        "postman_api_tester.services.collection_editor_service.validate_for_execution",
        return_value=["missing name"],
    )
    def test_validation_failure_returns_ce_save_002(self, mock_validate: MagicMock, app: Flask) -> None:
        """校验失败返回 400 + CE_SAVE_002。"""
        _register_routes(app)
        flat_data = {"groups": [], "allRequests": []}
        resp = app.test_client().put(
            "/api/collection-editor/save",
            data=json.dumps(flat_data),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_SAVE_002"
        assert "missing name" in data["data"]["details"]

    @patch(
        "postman_api_tester.services.collection_editor_service.validate_for_execution",
        return_value=[],
    )
    @patch(
        "postman_api_tester.services.collection_editor_service.build_collection_json",
        return_value={"info": {}, "item": []},
    )
    def test_success(self, mock_build: MagicMock, mock_validate: MagicMock, app: Flask) -> None:
        """有效数据保存成功。"""
        _register_routes(app)
        flat_data = {"groups": [], "allRequests": []}
        resp = app.test_client().put(
            "/api/collection-editor/save",
            data=json.dumps(flat_data),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "collection_json" in data

    @patch(
        "postman_api_tester.services.collection_editor_service.validate_for_execution",
        side_effect=RuntimeError("boom"),
    )
    def test_service_exception_returns_ce_save_003(self, mock_validate: MagicMock, app: Flask) -> None:
        """服务层异常返回 500 + CE_SAVE_003。"""
        _register_routes(app)
        resp = app.test_client().put(
            "/api/collection-editor/save",
            data=json.dumps({"groups": []}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["error_code"] == "CE_SAVE_003"


class TestApiCollectionDependency:
    """dependency 端点测试。"""

    def test_missing_groups_returns_ce_dep_001(self, app: Flask) -> None:
        """缺少 groups 字段返回 400 + CE_DEP_001。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/dependency",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_DEP_001"

    @patch(
        "postman_api_tester.services.collection_editor_service.analyze_dependency_map",
        return_value={"produced": {}, "consumed": {}, "warnings": []},
    )
    def test_success(self, mock_analyze: MagicMock, app: Flask) -> None:
        """有效数据依赖分析成功。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/dependency",
            data=json.dumps({"groups": []}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "produced" in data
        assert "consumed" in data
        assert "warnings" in data

    @patch(
        "postman_api_tester.services.collection_editor_service.analyze_dependency_map",
        side_effect=RuntimeError("analysis failed"),
    )
    def test_service_exception_returns_ce_dep_002(self, mock_analyze: MagicMock, app: Flask) -> None:
        """服务层异常返回 500 + CE_DEP_002。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/dependency",
            data=json.dumps({"groups": []}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["error_code"] == "CE_DEP_002"


class TestApiCollectionSend:
    """send 端点测试。"""

    def test_missing_request_returns_ce_send_001(self, app: Flask) -> None:
        """缺少 request 字段返回 400 + CE_SEND_001。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/send",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_SEND_001"

    def test_request_not_dict_returns_ce_send_002(self, app: Flask) -> None:
        """request 不是 dict 返回 400 + CE_SEND_002。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/send",
            data=json.dumps({"request": "not_a_dict"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_SEND_002"

    def test_variables_not_dict_returns_ce_send_003(self, app: Flask) -> None:
        """variables 不是 dict 返回 400 + CE_SEND_003。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/send",
            data=json.dumps({"request": {"method": "GET"}, "variables": "bad"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "CE_SEND_003"

    @patch(
        "postman_api_tester.services.collection_editor_service.send_single_request",
        return_value={
            "success": True,
            "status_code": 200,
            "elapsed_ms": 50,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": {"data": "ok"},
            "actual_request_url": "https://example.com/api",
        },
    )
    def test_success(self, mock_send: MagicMock, app: Flask) -> None:
        """请求成功返回完整响应。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/send",
            data=json.dumps({"request": {"method": "GET", "url": "https://example.com/api"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status_code"] == 200
        assert data["elapsed_ms"] == 50
        assert data["response_body"] == {"data": "ok"}

    @patch(
        "postman_api_tester.services.collection_editor_service.send_single_request",
        return_value={"success": False, "status_code": 404, "error_message": "Not Found"},
    )
    def test_target_api_error_returns_ce_send_004(self, mock_send: MagicMock, app: Flask) -> None:
        """目标接口返回错误返回 404 + CE_SEND_004。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/send",
            data=json.dumps({"request": {"method": "GET", "url": "https://example.com/api"}}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error_code"] == "CE_SEND_004"
        assert "404" in data["data"]["details"]

    @patch(
        "postman_api_tester.services.collection_editor_service.send_single_request",
        side_effect=RuntimeError("connection failed"),
    )
    def test_service_exception_returns_ce_send_005(self, mock_send: MagicMock, app: Flask) -> None:
        """服务层异常返回 500 + CE_SEND_005。"""
        _register_routes(app)
        resp = app.test_client().post(
            "/api/collection-editor/send",
            data=json.dumps({"request": {"method": "GET", "url": "https://example.com/api"}}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["error_code"] == "CE_SEND_005"
