"""Collection Editor Service 单元测试."""

from typing import Any, Dict
from unittest.mock import patch

from postman_api_tester.services.collection_editor_service import (
    analyze_dependency_map,
    build_collection_json,
    parse_collection_to_flat,
    send_single_request,
    validate_for_execution,
)


def _fake_exec_result(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "success": True,
        "status_code": 200,
        "response_body": {"ok": True},
        "response_headers": {"Content-Type": "application/json"},
        "elapsed_ms": 50,
        "normalized_url": "http://test/api",
        "normalized_params": {},
        "actual_request_url": "http://test/api",
        "headers_to_send": {},
        "stored_body": None,
        "stored_body_mode": "none",
        "stored_body_data": None,
    }
    base.update(overrides)
    return base


class TestParseCollectionToFlat:
    """parse_collection_to_flat 测试."""

    def test_empty_collection(self) -> None:
        result = parse_collection_to_flat({"info": {"name": "Test"}, "item": []})
        assert result["collection_info"]["name"] == "Test"
        assert result["groups"] == []

    def test_top_level_requests(self) -> None:
        collection = {
            "info": {"name": "Test"},
            "item": [
                {
                    "name": "Get Users",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {"raw": "http://api/users"},
                    },
                }
            ],
        }
        result = parse_collection_to_flat(collection)
        groups = result["groups"]
        assert len(groups) == 1
        assert groups[0]["group_name"] == ""
        assert len(groups[0]["requests"]) == 1
        assert groups[0]["requests"][0]["name"] == "Get Users"
        assert groups[0]["requests"][0]["method"] == "GET"


class TestBuildCollectionJson:
    """build_collection_json 测试."""

    def test_round_trip(self) -> None:
        original = {
            "info": {"name": "Test", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
            "item": [
                {
                    "name": "Ping",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {"raw": "http://ping/api"},
                    },
                }
            ],
        }
        flat = parse_collection_to_flat(original)
        rebuilt = build_collection_json(flat)
        assert rebuilt["info"]["name"] == "Test"
        assert len(rebuilt["item"]) == 1
        assert rebuilt["item"][0]["name"] == "Ping"


class TestAnalyzeDependencyMap:
    """analyze_dependency_map 测试."""

    def test_no_variables(self) -> None:
        groups = [{"group_name": "g", "requests": [{"id": "r1", "name": "req", "url": "http://api", "headers": [], "params": [], "body_data": None}], "subgroups": []}]
        result = analyze_dependency_map(groups)
        assert result["produced"] == {}
        assert result["consumed"] == {}
        assert result["warnings"] == []

    def test_produced_and_consumed(self) -> None:
        groups = [{
            "group_name": "",
            "requests": [
                {"id": "r1", "name": "login", "url": "http://api/login", "headers": [], "params": [], "body_data": None, "x_extract": {"token": "$.data.token"}},
                {"id": "r2", "name": "get_user", "url": "http://api/user", "headers": [{"key": "Authorization", "value": "Bearer {{token}}"}], "params": [], "body_data": None, "x_extract": {}},
            ],
            "subgroups": [],
        }]
        result = analyze_dependency_map(groups)
        assert "token" in result["produced"]
        assert result["produced"]["token"]["by_request"] == "r1"
        assert "token" in result["consumed"]
        assert result["warnings"] == []

    def test_warning_for_unproduced_variable(self) -> None:
        groups = [{
            "group_name": "",
            "requests": [
                {"id": "r1", "name": "req", "url": "http://api/{{undefined_var}}", "headers": [], "params": [], "body_data": None, "x_extract": {}},
            ],
            "subgroups": [],
        }]
        result = analyze_dependency_map(groups)
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["var_name"] == "undefined_var"


class TestValidateForExecution:
    """validate_for_execution 测试."""

    def test_empty_groups(self) -> None:
        errors = validate_for_execution({"groups": []})
        assert any("没有接口" in e for e in errors)

    def test_missing_name(self) -> None:
        flat = {"groups": [{"group_name": "", "requests": [{"id": "r1", "name": "", "url": "http://api", "method": "GET"}], "subgroups": []}]}
        errors = validate_for_execution(flat)
        assert any("缺少名称" in e for e in errors)

    def test_valid_request(self) -> None:
        flat = {"groups": [{"group_name": "", "requests": [{"id": "r1", "name": "OK", "url": "http://api", "method": "GET"}], "subgroups": []}]}
        errors = validate_for_execution(flat)
        assert errors == []


class TestSendSingleRequest:
    """send_single_request 测试."""

    @patch("postman_api_tester.handlers.http_handler.execute_http_request")
    def test_basic_get(self, mock_exec: Any) -> None:
        mock_exec.return_value = _fake_exec_result()
        result = send_single_request(
            {"url": "http://test/api", "method": "GET", "headers": [], "params": [], "body_mode": "none"},
            {},
        )
        assert result["success"] is True
        mock_exec.assert_called_once()
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs["url"] == "http://test/api"
        assert call_kwargs["method"] == "GET"

    @patch("postman_api_tester.handlers.http_handler.execute_http_request")
    def test_variable_substitution_in_url(self, mock_exec: Any) -> None:
        mock_exec.return_value = _fake_exec_result()
        result = send_single_request(
            {"url": "{{host}}/api", "method": "GET", "headers": [], "params": [], "body_mode": "none"},
            {"host": "http://resolved"},
        )
        assert result["success"] is True
        assert mock_exec.call_args.kwargs["url"] == "http://resolved/api"

    @patch("postman_api_tester.handlers.http_handler.execute_http_request")
    def test_variable_substitution_in_headers(self, mock_exec: Any) -> None:
        mock_exec.return_value = _fake_exec_result()
        result = send_single_request(
            {
                "url": "http://test/api",
                "method": "GET",
                "headers": [{"key": "Authorization", "value": "Bearer {{token}}"}],
                "params": [],
                "body_mode": "none",
            },
            {"token": "abc123"},
        )
        assert result["success"] is True
        headers = mock_exec.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer abc123"

    @patch("postman_api_tester.handlers.http_handler.execute_http_request")
    def test_variable_substitution_in_raw_body(self, mock_exec: Any) -> None:
        mock_exec.return_value = _fake_exec_result()
        result = send_single_request(
            {
                "url": "http://test/api",
                "method": "POST",
                "headers": [],
                "params": [],
                "body_mode": "raw",
                "body_data": {"content": '{"user": "{{name}}"}', "language": "json"},
            },
            {"name": "alice"},
        )
        assert result["success"] is True
        body_data = mock_exec.call_args.kwargs["body_data"]
        assert '"alice"' in body_data["raw_content"]
        assert body_data["raw_language"] == "json"
        assert body_data["raw_content_type"] == "application/json"

    @patch("postman_api_tester.handlers.http_handler.execute_http_request")
    def test_variable_substitution_in_params(self, mock_exec: Any) -> None:
        mock_exec.return_value = _fake_exec_result()
        result = send_single_request(
            {
                "url": "http://test/api",
                "method": "GET",
                "headers": [],
                "params": [{"key": "q", "value": "{{query}}"}],
                "body_mode": "none",
            },
            {"query": "hello"},
        )
        assert result["success"] is True
        params = mock_exec.call_args.kwargs["params"]
        assert params["q"] == "hello"

    @patch("postman_api_tester.handlers.http_handler.execute_http_request")
    def test_unmatched_variable_preserved(self, mock_exec: Any) -> None:
        mock_exec.return_value = _fake_exec_result()
        send_single_request(
            {"url": "http://test/{{unknown}}", "method": "GET", "headers": [], "params": [], "body_mode": "none"},
            {},
        )
        assert mock_exec.call_args.kwargs["url"] == "http://test/{{unknown}}"
