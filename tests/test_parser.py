"""parser 模块单元测试。

覆盖 PostmanApiParser 的 load_file、extract_base_url、extract_apis、
_parse_item、_parse_request、_normalize_api_name、_build_url_from_dict。
"""

import json
import os
import tempfile
from typing import Any, Dict, List

import pytest

from postman_api_tester.exceptions import ParseError
from postman_api_tester.parser import PostmanApiParser


def _write_collection(tmpdir: str, data: Dict[str, Any]) -> str:
	path = os.path.join(tmpdir, "test_collection.json")
	with open(path, "w", encoding="utf-8") as f:
		json.dump(data, f)
	return path


class TestLoadFile:
	"""load_file() 文件加载测试。"""

	def test_file_not_found(self) -> None:
		with pytest.raises(ParseError, match="文件不存在"):
			PostmanApiParser("/nonexistent/path.json")

	def test_invalid_json(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			path = os.path.join(tmpdir, "bad.json")
			with open(path, "w") as f:
				f.write("not json {{{")
			with pytest.raises(ParseError, match="JSON文件格式错误"):
				PostmanApiParser(path)

	def test_valid_json(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			path = _write_collection(tmpdir, {"info": {"name": "test"}})
			parser = PostmanApiParser(path)
			assert parser.data == {"info": {"name": "test"}}


class TestExtractBaseUrl:
	"""extract_base_url() 基础 URL 提取测试。"""

	def test_from_baseUrl_variable(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"variable": [{"key": "baseUrl", "value": "https://api.example.com"}],
				"item": [],
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_base_url() == "https://api.example.com"

	def test_from_base_url_variable(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"variable": [{"key": "base_url", "value": "https://alt.example.com"}],
				"item": [],
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_base_url() == "https://alt.example.com"

	def test_from_first_request_dict_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"item": [{
					"request": {
						"url": {"protocol": "https", "host": "api.example.com"},
						"method": "GET",
					}
				}]
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_base_url() == "https://api.example.com"

	def test_from_first_request_string_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"item": [{
					"request": {
						"url": "https://api.example.com/users",
						"method": "GET",
					}
				}]
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_base_url() == "https://api.example.com"

	def test_empty_items(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_base_url() == ""

	def test_non_http_protocol_ignored(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"item": [{
					"request": {
						"url": {"protocol": "ftp", "host": "files.example.com"},
						"method": "GET",
					}
				}]
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_base_url() == ""


class TestExtractApis:
	"""extract_apis() API 提取测试。"""

	def test_simple_request(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"variable": [{"key": "baseUrl", "value": "https://api.example.com"}],
				"item": [{
					"name": "Get Users",
					"request": {
						"method": "GET",
						"url": {"raw": "https://api.example.com/users", "path": ["users"]},
						"header": [],
					}
				}]
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			apis = parser.extract_apis()
			assert len(apis) == 1
			assert apis[0]["name"] == "Get Users"
			assert apis[0]["method"] == "GET"

	def test_nested_folders(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"item": [{
					"name": "Auth",
					"item": [{
						"name": "Login",
						"request": {
							"method": "POST",
							"url": {"raw": "https://api.example.com/login", "path": ["login"]},
							"header": [],
						}
					}]
				}]
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			apis = parser.extract_apis()
			assert len(apis) == 1
			assert apis[0]["folder"] == "Auth"
			assert apis[0]["name"] == "Login"

	def test_missing_method_skipped(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data = {
				"item": [{
					"name": "Test",
					"request": {
						"method": "",
						"url": {"path": ["test"]},
						"header": [],
					}
				}]
			}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			apis = parser.extract_apis()
			assert len(apis) == 0

	def test_empty_collection(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser.extract_apis() == []


class TestParseRequest:
	"""_parse_request() 请求解析测试。"""

	def _make_parser(self, tmpdir: str, base_url: str = "https://api.example.com") -> PostmanApiParser:
		data = {"variable": [{"key": "baseUrl", "value": base_url}], "item": []}
		path = _write_collection(tmpdir, data)
		return PostmanApiParser(path)

	def test_raw_json_body(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "Create User",
				"request": {
					"method": "POST",
					"url": "/users",
					"header": [],
					"body": {"mode": "raw", "raw": '{"name": "Alice"}'},
				}
			}
			result = parser._parse_request(item, "Users")
			assert result["body"] == {"name": "Alice"}

	def test_raw_non_json_body(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "Plain Text",
				"request": {
					"method": "POST",
					"url": "/text",
					"header": [],
					"body": {"mode": "raw", "raw": "hello world"},
				}
			}
			result = parser._parse_request(item)
			assert result["body"] == "hello world"

	def test_formdata_body(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "Upload",
				"request": {
					"method": "POST",
					"url": "/upload",
					"header": [],
					"body": {
						"mode": "formdata",
						"formdata": [
							{"key": "name", "value": "Alice"},
							{"key": "disabled_field", "value": "skip", "disabled": True},
						]
					},
				}
			}
			result = parser._parse_request(item)
			assert result["body"]["__body_mode"] == "formdata"
			assert len(result["body"]["formdata"]) == 1
			assert result["body"]["formdata"][0]["key"] == "name"
			assert result["body"]["formdata"][0]["value"] == "Alice"
			assert result["body"]["formdata"][0]["type"] == "text"

	def test_urlencoded_body(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "Form",
				"request": {
					"method": "POST",
					"url": "/form",
					"header": [],
					"body": {
						"mode": "urlencoded",
						"urlencoded": [
							{"key": "user", "value": "admin"},
							{"key": "pass", "value": "secret"},
						]
					},
				}
			}
			result = parser._parse_request(item)
			assert result["body"] == {"user": "admin", "pass": "secret"}

	def test_headers_parsed(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "With Headers",
				"request": {
					"method": "GET",
					"url": "/test",
					"header": [
						{"key": "Authorization", "value": "Bearer token"},
						{"key": "Disabled", "value": "skip", "disabled": True},
					],
				}
			}
			result = parser._parse_request(item)
			assert result["headers"] == {"Authorization": "Bearer token"}

	def test_query_params_from_dict_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "With Params",
				"request": {
					"method": "GET",
					"url": {
						"raw": "https://api.example.com/search?q=test&page=1",
						"path": ["search"],
						"query": [
							{"key": "q", "value": "test"},
							{"key": "page", "value": "1"},
							{"key": "disabled", "value": "skip", "disabled": True},
						],
					},
					"header": [],
				}
			}
			result = parser._parse_request(item)
			assert result["params"] == {"q": "test", "page": "1"}

	def test_x_fields_parsed(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "With Extensions",
				"request": {
					"method": "GET",
					"url": "/test",
					"header": [],
					"x_success_err_codes": "E001, E002",
					"x_success_messages": "操作成功",
					"x_enable_err_code_judgment": "true",
					"x_enable_message_judgment": False,
					"x_extract": {"token": "$.data.token"},
				}
			}
			result = parser._parse_request(item)
			assert result["x_success_err_codes"] == "E001, E002"
			assert result["x_success_messages"] == "操作成功"
			assert result["x_enable_err_code_judgment"] is True
			assert result["x_enable_message_judgment"] is False
			assert result["x_extract"] == {"token": "$.data.token"}

	def test_x_fields_absent_not_in_result(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			parser = self._make_parser(tmpdir)
			item = {
				"name": "No Extensions",
				"request": {"method": "GET", "url": "/test", "header": []},
			}
			result = parser._parse_request(item)
			assert "x_success_err_codes" not in result
			assert "x_extract" not in result


class TestNormalizeApiName:
	"""_normalize_api_name() 名称规范化测试。"""

	def test_normal_name(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser._normalize_api_name("Get Users", "GET", "/users") == "Get Users"

	def test_empty_name_from_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser._normalize_api_name("", "GET", "/users") == "GET /users"

	def test_question_mark_name_from_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser._normalize_api_name("?", "POST", "/api/data") == "POST /api/data"

	def test_empty_name_and_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			assert parser._normalize_api_name("", "GET", "") == "GET 接口"

	def test_baseUrl_prefix_stripped(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			result = parser._normalize_api_name("", "GET", "{{baseUrl}}/users")
			assert result == "GET /users"


class TestBuildUrlFromDict:
	"""_build_url_from_dict() URL 构建测试。"""

	def test_path_with_query(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			url_dict = {
				"path": ["api", "users"],
				"query": [{"key": "page", "value": "1"}],
			}
			assert parser._build_url_from_dict(url_dict) == "/api/users?page=1"

	def test_raw_url_fallback(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			url_dict: Dict[str, Any] = {"raw": "https://api.example.com/users", "path": []}
			assert parser._build_url_from_dict(url_dict) == "https://api.example.com/users"

	def test_raw_variable_url(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			data: Dict[str, Any] = {"item": []}
			path = _write_collection(tmpdir, data)
			parser = PostmanApiParser(path)
			url_dict: Dict[str, Any] = {"raw": "{{baseUrl}}/users", "path": []}
			result = parser._build_url_from_dict(url_dict)
			assert result == "/users"
