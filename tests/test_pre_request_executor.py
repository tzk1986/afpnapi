"""pre_request_executor 沙箱表达式执行器单元测试。

覆盖正常表达式、危险关键字拦截、超时保护、语法错误、空输入等路径。
"""

from unittest.mock import patch

from postman_api_tester.utils.pre_request_executor import (
    _contains_dangerous_keyword,
    execute_pre_request,
)


class TestDangerousKeywordCheck:
    """危险关键字检查测试。"""

    def test_import_blocked(self):
        """import 关键字被拦截。"""
        assert _contains_dangerous_keyword("import os") is True

    def test_dunder_import_blocked(self):
        """__import__ 被拦截。"""
        assert _contains_dangerous_keyword("__import__('os')") is True

    def test_exec_blocked(self):
        """exec 被拦截。"""
        assert _contains_dangerous_keyword("exec('print(1)')") is True

    def test_eval_blocked(self):
        """eval 被拦截。"""
        assert _contains_dangerous_keyword("eval('1+1')") is True

    def test_open_blocked(self):
        """open 被拦截。"""
        assert _contains_dangerous_keyword("open('/etc/passwd')") is True

    def test_os_blocked(self):
        """os 被拦截。"""
        assert _contains_dangerous_keyword("os.system('ls')") is True

    def test_sys_blocked(self):
        """sys 被拦截。"""
        assert _contains_dangerous_keyword("sys.exit(0)") is True

    def test_subprocess_blocked(self):
        """subprocess 被拦截。"""
        assert _contains_dangerous_keyword("subprocess.run(['ls'])") is True

    def test_builtins_blocked(self):
        """__builtins__ 被拦截。"""
        assert _contains_dangerous_keyword("__builtins__['open']") is True

    def test_globals_blocked(self):
        """globals 被拦截。"""
        assert _contains_dangerous_keyword("globals()") is True

    def test_locals_blocked(self):
        """locals 被拦截。"""
        assert _contains_dangerous_keyword("locals()") is True

    def test_class_dunder_blocked(self):
        """__class__ 被拦截。"""
        assert _contains_dangerous_keyword("x.__class__") is True

    def test_safe_expression_allowed(self):
        """安全表达式不被拦截。"""
        assert _contains_dangerous_keyword("hashlib.md5(b'test').hexdigest()") is False
        assert _contains_dangerous_keyword("hmac.new(b'k', b'd', hashlib.sha256).hexdigest()") is False
        assert _contains_dangerous_keyword("base64.b64encode(b'test').decode()") is False
        assert _contains_dangerous_keyword("int(time.time())") is False
        assert _contains_dangerous_keyword("'hello'.upper()") is False

    def test_json_allowed(self):
        """json 模块允许使用。"""
        assert _contains_dangerous_keyword("json.dumps({'a': 1})") is False

    def test_re_allowed(self):
        """re 模块允许使用。"""
        assert _contains_dangerous_keyword("re.sub(r'\\d', '', 'abc123')") is False


class TestExecutePreRequestEmpty:
    """空输入测试。"""

    def test_empty_expressions(self):
        """空字典返回空结果。"""
        assert execute_pre_request({}, {}) == {}

    def test_empty_expression_value(self):
        """表达式为空字符串时返回空字符串。"""
        result = execute_pre_request({"var": ""}, {})
        assert result == {"var": ""}


class TestExecutePreRequestNormal:
    """正常表达式执行测试。"""

    def test_simple_arithmetic(self):
        """简单算术运算。"""
        result = execute_pre_request({"val": "1 + 2"}, {})
        assert result["val"] == "3"

    def test_string_operation(self):
        """字符串操作。"""
        result = execute_pre_request({"val": "'hello'.upper()"}, {})
        assert result["val"] == "HELLO"

    def test_hashlib_md5(self):
        """hashlib.md5 计算。"""
        result = execute_pre_request(
            {"val": "hashlib.md5(b'test').hexdigest()"},
            {},
        )
        assert result["val"] == "098f6bcd4621d373cade4e832627b4f6"

    def test_hmac_sha256(self):
        """hmac.new 计算。"""
        result = execute_pre_request(
            {"val": "hmac.new(b'secret', b'data', hashlib.sha256).hexdigest()"},
            {},
        )
        assert len(result["val"]) == 64

    def test_base64_encode(self):
        """base64 编码。"""
        result = execute_pre_request(
            {"val": "base64.b64encode(b'hello').decode()"},
            {},
        )
        assert result["val"] == "aGVsbG8="

    def test_time_module(self):
        """time 模块可用。"""
        result = execute_pre_request({"val": "int(time.time())"}, {})
        assert result["val"].isdigit()

    def test_json_module(self):
        """json 模块可用。"""
        result = execute_pre_request(
            {"val": "json.dumps({'key': 'value'})"},
            {},
        )
        assert "key" in result["val"]

    def test_re_module(self):
        """re 模块可用。"""
        result = execute_pre_request(
            {"val": "re.sub(r'\\d', '', 'abc123def')"},
            {},
        )
        assert result["val"] == "abcdef"

    def test_reference_existing_variables(self):
        """表达式可引用已有变量。"""
        result = execute_pre_request(
            {"val": "variables.get('name', 'unknown').upper()"},
            {"name": "alice"},
        )
        assert result["val"] == "ALICE"

    def test_reference_missing_variable(self):
        """引用不存在的变量返回默认值。"""
        result = execute_pre_request(
            {"val": "variables.get('missing', 'default')"},
            {},
        )
        assert result["val"] == "default"

    def test_multiple_expressions(self):
        """多个表达式同时执行。"""
        result = execute_pre_request(
            {"a": "1 + 1", "b": "2 + 2", "c": "3 + 3"},
            {},
        )
        assert result == {"a": "2", "b": "4", "c": "6"}

    def test_later_expression_references_earlier_result(self):
        """后续表达式可引用前面设置的结果。"""
        result = execute_pre_request(
            {"a": "10", "b": "int(result.get('a', '0')) + 5"},
            {},
        )
        assert result["a"] == "10"
        assert result["b"] == "15"


class TestExecutePreRequestDangerous:
    """危险表达式拦截测试。"""

    def test_import_blocked(self):
        """import os 被拦截，返回空字符串。"""
        result = execute_pre_request({"val": "import os"}, {})
        assert result["val"] == ""

    def test_os_system_blocked(self):
        """os.system 被拦截。"""
        result = execute_pre_request({"val": "os.system('echo hacked')"}, {})
        assert result["val"] == ""

    def test_open_blocked(self):
        """open 被拦截。"""
        result = execute_pre_request({"val": "open('/etc/passwd').read()"}, {})
        assert result["val"] == ""

    def test_exec_blocked(self):
        """exec 被拦截。"""
        result = execute_pre_request({"val": "exec('x=1')"}, {})
        assert result["val"] == ""

    def test_eval_blocked(self):
        """eval 被拦截。"""
        result = execute_pre_request({"val": "eval('1+1')"}, {})
        assert result["val"] == ""


class TestExecutePreRequestErrors:
    """错误处理测试。"""

    def test_syntax_error(self):
        """语法错误返回空字符串。"""
        result = execute_pre_request({"val": "1 +"}, {})
        assert result["val"] == ""

    def test_name_error(self):
        """未定义变量返回空字符串。"""
        result = execute_pre_request({"val": "undefined_var + 1"}, {})
        assert result["val"] == ""

    def test_type_error(self):
        """类型错误返回空字符串。"""
        result = execute_pre_request({"val": "'a' + 1"}, {})
        assert result["val"] == ""

    def test_division_by_zero(self):
        """除零错误返回空字符串。"""
        result = execute_pre_request({"val": "1 / 0"}, {})
        assert result["val"] == ""

    def test_none_result_becomes_empty_string(self):
        """None 结果转为空字符串。"""
        result = execute_pre_request({"val": "None"}, {})
        assert result["val"] == ""

    def test_mixed_success_and_failure(self):
        """混合成功和失败的表达式。"""
        result = execute_pre_request(
            {"ok": "1 + 1", "bad": "1 / 0", "blocked": "import os"},
            {},
        )
        assert result["ok"] == "2"
        assert result["bad"] == ""
        assert result["blocked"] == ""


class TestExecutePreRequestTimeout:
    """超时保护测试。"""

    def test_infinite_loop_timeout(self):
        """死循环应在超时后返回空字符串。"""
        result = execute_pre_request({"val": "([x for x in iter(int, 1)])"}, {})
        assert result["val"] == ""


class TestSandboxIsolation:
    """沙箱隔离测试。"""

    def test_no_access_to_file_operations(self):
        """无法访问文件操作。"""
        result = execute_pre_request({"val": "open('test.txt')"}, {})
        assert result["val"] == ""

    def test_no_access_to_environment(self):
        """无法访问环境变量。"""
        result = execute_pre_request({"val": "os.environ"}, {})
        assert result["val"] == ""

    def test_no_class_traversal(self):
        """无法通过 __class__ 逃逸。"""
        result = execute_pre_request({"val": "''.__class__.__bases__[0].__subclasses__()"}, {})
        assert result["val"] == ""

    def test_safe_builtins_only(self):
        """仅允许安全内置函数。"""
        result = execute_pre_request({"val": "len('hello')"}, {})
        assert result["val"] == "5"

    def test_list_operations(self):
        """列表操作允许。"""
        result = execute_pre_request({"val": "sum([1, 2, 3])"}, {})
        assert result["val"] == "6"

    def test_dict_operations(self):
        """字典操作允许。"""
        result = execute_pre_request({"val": "dict(a=1, b=2)"}, {})
        assert "'a'" in result["val"] or "a" in result["val"]
