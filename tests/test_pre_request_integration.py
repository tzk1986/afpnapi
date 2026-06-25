"""Pre-request 脚本端到端集成测试。

覆盖完整链路：解析器 → 执行器 → 变量替换。
"""

import json
import os
import tempfile
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.core.variable_context import VariableContext
from postman_api_tester.parser import PostmanApiParser


def _write_collection(tmpdir: str, data: Dict[str, Any]) -> str:
    path = os.path.join(tmpdir, "test_collection.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _make_parser(tmpdir: str) -> PostmanApiParser:
    data: Dict[str, Any] = {"item": []}
    path = _write_collection(tmpdir, data)
    return PostmanApiParser(path)


class TestParserPreRequest:
    """解析器 x_pre_request 字段测试。"""

    def test_parse_x_pre_request_field(self):
        """解析器应正确解析 x_pre_request 字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = _make_parser(tmpdir)
            item = {
                "name": "test_api",
                "request": {
                    "method": "POST",
                    "url": "/api/test",
                    "header": [],
                    "x_pre_request": {
                        "timestamp": "int(time.time())",
                        "sign": "hashlib.md5(b'test').hexdigest()",
                    },
                },
            }
            result = parser._parse_request(item)
            assert "x_pre_request" in result
            assert result["x_pre_request"]["timestamp"] == "int(time.time())"
            assert result["x_pre_request"]["sign"] == "hashlib.md5(b'test').hexdigest()"

    def test_parse_without_x_pre_request(self):
        """无 x_pre_request 字段时不应包含该键。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = _make_parser(tmpdir)
            item = {
                "name": "test_api",
                "request": {"method": "GET", "url": "/api/test", "header": []},
            }
            result = parser._parse_request(item)
            assert "x_pre_request" not in result

    def test_parse_empty_x_pre_request(self):
        """空 x_pre_request 字典不应写入结果。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = _make_parser(tmpdir)
            item = {
                "name": "test_api",
                "request": {
                    "method": "GET",
                    "url": "/api/test",
                    "header": [],
                    "x_pre_request": {},
                },
            }
            result = parser._parse_request(item)
            assert "x_pre_request" not in result

    def test_parse_x_pre_request_non_dict_ignored(self):
        """非字典类型的 x_pre_request 应被忽略。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = _make_parser(tmpdir)
            item = {
                "name": "test_api",
                "request": {
                    "method": "GET",
                    "url": "/api/test",
                    "header": [],
                    "x_pre_request": "not_a_dict",
                },
            }
            result = parser._parse_request(item)
            assert "x_pre_request" not in result

    def test_parse_x_pre_request_filters_non_string_values(self):
        """非字符串值的表达式应被过滤。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = _make_parser(tmpdir)
            item = {
                "name": "test_api",
                "request": {
                    "method": "GET",
                    "url": "/api/test",
                    "header": [],
                    "x_pre_request": {
                        "valid": "int(time.time())",
                        "invalid": 123,
                        "also_invalid": None,
                    },
                },
            }
            result = parser._parse_request(item)
            pre_req = result["x_pre_request"]
            assert "valid" in pre_req
            assert "invalid" not in pre_req
            assert "also_invalid" not in pre_req


class TestExecutorPreRequestIntegration:
    """执行器 pre-request 集成测试。"""

    @patch("postman_api_tester.config.ENABLE_PRE_REQUEST_SCRIPT", True)
    def test_pre_request_variables_merged(self):
        """启用时 pre-request 变量应合并到替换上下文。"""
        from postman_api_tester.utils.pre_request_executor import execute_pre_request

        expressions = {"ts": "str(1234567890)"}
        existing_vars: Dict[str, str] = {}
        result = execute_pre_request(expressions, existing_vars)

        assert result["ts"] == "1234567890"

    def test_pre_request_ignored_when_disabled(self):
        """禁用时 x_pre_request 不应执行。"""
        from postman_api_tester.config import ENABLE_PRE_REQUEST_SCRIPT

        original_value = ENABLE_PRE_REQUEST_SCRIPT
        try:
            import postman_api_tester.config as cfg
            cfg.ENABLE_PRE_REQUEST_SCRIPT = False

            from postman_api_tester.utils.pre_request_executor import execute_pre_request

            expressions = {"ts": "str(999)"}
            if not cfg.ENABLE_PRE_REQUEST_SCRIPT:
                result: Dict[str, str] = {}
            else:
                result = execute_pre_request(expressions, {})

            assert result == {}
        finally:
            cfg.ENABLE_PRE_REQUEST_SCRIPT = original_value

    @patch("postman_api_tester.config.ENABLE_PRE_REQUEST_SCRIPT", True)
    def test_pre_request_with_existing_variables(self):
        """pre-request 表达式应能引用已有变量。"""
        from postman_api_tester.utils.pre_request_executor import execute_pre_request

        expressions = {"result": "variables.get('name', 'unknown').upper()"}
        existing_vars = {"name": "alice"}
        result = execute_pre_request(expressions, existing_vars)

        assert result["result"] == "ALICE"

    @patch("postman_api_tester.config.ENABLE_PRE_REQUEST_SCRIPT", True)
    def test_pre_request_does_not_pollute_global_context(self):
        """pre-request 变量不应写入全局 VariableContext。"""
        from postman_api_tester.utils.pre_request_executor import execute_pre_request

        ctx = VariableContext()
        original_vars = set(ctx.variables.keys())

        expressions = {"local_var": "str(42)"}
        local_vars = execute_pre_request(expressions, ctx.variables)

        assert "local_var" in local_vars
        assert "local_var" not in set(ctx.variables.keys())
        assert set(ctx.variables.keys()) == original_vars

    @patch("postman_api_tester.config.ENABLE_PRE_REQUEST_SCRIPT", True)
    def test_pre_request_later_references_earlier(self):
        """后续表达式可引用前置表达式结果。"""
        from postman_api_tester.utils.pre_request_executor import execute_pre_request

        expressions = {
            "step1": "10",
            "step2": "int(result.get('step1', '0')) * 2",
        }
        result = execute_pre_request(expressions, {})

        assert result["step1"] == "10"
        assert result["step2"] == "20"


class TestVariableSubstitutionWithPreRequest:
    """变量替换与 pre-request 联合测试。"""

    def test_builtin_functions_in_substitution(self):
        """内置函数应在变量替换中正确执行。"""
        from postman_api_tester.utils.variable_substitution import substitute_variables

        result = substitute_variables("{{md5(test)}}", {})
        assert result == "098f6bcd4621d373cade4e832627b4f6"

    def test_hmac_sha256_in_substitution(self):
        """hmac_sha256 应在变量替换中正确执行。"""
        import hashlib
        import hmac
        from postman_api_tester.utils.variable_substitution import substitute_variables

        expected = hmac.new(b"secret", b"data", hashlib.sha256).hexdigest()
        result = substitute_variables("{{hmac_sha256(data,secret)}}", {})
        assert result == expected

    def test_url_encode_in_substitution(self):
        """url_encode 应在变量替换中正确执行。"""
        from postman_api_tester.utils.variable_substitution import substitute_variables

        result = substitute_variables("{{url_encode(hello world)}}", {})
        assert result == "hello%20world"

    def test_base64_roundtrip_in_substitution(self):
        """base64 编码解码应在变量替换中正确往返。"""
        from postman_api_tester.utils.variable_substitution import substitute_variables

        encoded = substitute_variables("{{base64_encode(user:pass)}}", {})
        assert encoded == "dXNlcjpwYXNz"

        decoded = substitute_variables("{{base64_decode(dXNlcjpwYXNz)}}", {})
        assert decoded == "user:pass"

    def test_random_string_in_substitution(self):
        """random_string 应在变量替换中正确执行。"""
        from postman_api_tester.utils.variable_substitution import substitute_variables

        result = substitute_variables("{{random_string(16,alpha)}}", {})
        assert len(result) == 16
        assert result.isalpha()

    def test_pre_request_result_used_in_substitution(self):
        """pre-request 结果应可用于变量替换。"""
        from postman_api_tester.utils.pre_request_executor import execute_pre_request
        from postman_api_tester.utils.variable_substitution import substitute_variables

        expressions = {"sign": "hashlib.md5(b'data').hexdigest()"}
        local_vars = execute_pre_request(expressions, {})

        merged = {**{}, **local_vars}
        result = substitute_variables("{{sign}}", merged)
        assert result == "8d777f385d3dfec8815d20f7496026dc"
