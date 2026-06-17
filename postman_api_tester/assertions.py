"""断言引擎模块。

开发导读:
- 负责解析并执行 JSONPath 断言规则。
- 输出统一断言结果结构，供执行器汇总到报告层。
- 支持 13 种操作符: eq/ne/gt/lt/gte/lte/exists/not_exists/contains/regex/length_eq/type/schema。
"""
import logging as _logging
import re as _re
from typing import Any, Dict, List, Tuple

logger = _logging.getLogger(__name__)

try:
    from jsonpath_ng import parse as _jsonpath_parse
    _JSONPATH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSONPATH_AVAILABLE = False
    logger.warning("jsonpath_ng 未安装，断言功能不可用。请运行: pip install 'jsonpath-ng>=1.5.3'")

try:
    import jsonschema as _jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

SUPPORTED_OPS = {
    "eq", "ne", "gt", "lt", "gte", "lte",
    "exists", "not_exists", "contains",
    "regex", "length_eq", "type", "schema",
}


def evaluate_assertions(response_body: Any, assertions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """评估断言列表，返回每条断言的结果列表。

    每项结果包含: path, op, expected, actual, passed, message
    """
    results: List[Dict[str, Any]] = []
    if not _JSONPATH_AVAILABLE:
        return [{"path": "*", "op": "*", "expected": None, "actual": None,
                 "passed": False, "message": "jsonpath_ng 未安装，请运行: pip install 'jsonpath-ng>=1.5.3'"}]

    for rule in assertions:
        path = str(rule.get("path", ""))
        op = str(rule.get("op", "eq")).strip().lower()
        expected = rule.get("expected")
        actual: Any = None
        passed = False
        message = ""
        try:
            expr = _jsonpath_parse(path)
            matches = [m.value for m in expr.find(response_body)]
            if op == "not_exists":
                passed = len(matches) == 0
                actual = matches
                message = "" if passed else f"路径 {path} 存在值: {matches}"
            elif op == "exists":
                passed = len(matches) > 0
                actual = matches
                message = "" if passed else f"路径 {path} 不存在"
            else:
                actual = matches[0] if matches else None
                passed, message = _compare(actual, op, expected)
                if not passed and not message:
                    message = f"{path}: {actual!r} {op} {expected!r} 断言失败"
        except Exception as exc:
            passed = False
            message = f"断言异常: {exc}"
        results.append({
            "path": path,
            "op": op,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "message": message,
        })
    return results


def _compare(actual: Any, op: str, expected: Any) -> Tuple[bool, str]:
    try:
        if op == "eq":
            return (actual == expected, "")
        if op == "ne":
            return (actual != expected, "")
        if op == "gt":
            return (actual > expected, "")
        if op == "lt":
            return (actual < expected, "")
        if op == "gte":
            return (actual >= expected, "")
        if op == "lte":
            return (actual <= expected, "")
        if op == "contains":
            return (str(expected) in str(actual), "")
        if op == "regex":
            pattern = str(expected)
            matched = _re.search(pattern, str(actual))
            return (matched is not None, "" if matched else f"值 {actual!r} 不匹配正则 {pattern!r}")
        if op == "length_eq":
            expected_len = int(expected)
            actual_len = len(actual) if actual is not None else 0
            return (actual_len == expected_len, "" if actual_len == expected_len else f"实际长度 {actual_len} != 期望 {expected_len}")
        if op == "type":
            return _check_type(actual, str(expected))
        if op == "schema":
            if not _JSONSCHEMA_AVAILABLE:
                return (False, "jsonschema 未安装，请运行: pip install jsonschema")
            try:
                _jsonschema.validate(instance=actual, schema=expected)
                return (True, "")
            except _jsonschema.ValidationError as exc:
                return (False, f"Schema 验证失败: {exc.message}")
        return (False, f"不支持的操作符: {op}，支持: {', '.join(sorted(SUPPORTED_OPS))}")
    except Exception as exc:
        return (False, f"比较异常: {exc}")


_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_type(actual: Any, expected_type: str) -> Tuple[bool, str]:
    """检查 actual 是否匹配 expected_type。"""
    expected_lower = expected_type.lower().strip()
    if expected_lower == "null":
        passed = actual is None
        return (passed, "" if passed else f"期望 null，实际 {type(actual).__name__}")
    if expected_lower == "integer":
        passed = isinstance(actual, int) and not isinstance(actual, bool)
        return (passed, "" if passed else f"期望 integer，实际 {type(actual).__name__}")
    if expected_lower == "number":
        passed = isinstance(actual, (int, float)) and not isinstance(actual, bool)
        return (passed, "" if passed else f"期望 number，实际 {type(actual).__name__}")
    py_type = _TYPE_MAP.get(expected_lower)
    if py_type is None:
        return (False, f"未知类型: {expected_type}，支持: {', '.join(sorted(_TYPE_MAP.keys()))}, null")
    passed = isinstance(actual, py_type)
    if not passed:
        return (False, f"期望 {expected_type}，实际 {type(actual).__name__}")
    return (True, "")
