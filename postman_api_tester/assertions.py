"""升级五：JSONPath 断言引擎"""
import logging as _logging
from typing import Any, Dict, List, Tuple

logger = _logging.getLogger(__name__)

try:
    from jsonpath_ng import parse as _jsonpath_parse
    _JSONPATH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSONPATH_AVAILABLE = False
    logger.warning("jsonpath_ng 未安装，断言功能不可用。请运行: pip install 'jsonpath-ng>=1.5.3'")

SUPPORTED_OPS = {"eq", "ne", "gt", "lt", "gte", "lte", "exists", "not_exists", "contains"}


def evaluate_assertions(response_body: Any, assertions: List[Dict]) -> List[Dict]:
    """评估断言列表，返回每条断言的结果列表。

    每项结果包含: path, op, expected, actual, passed, message
    """
    results: List[Dict] = []
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
        return (False, f"不支持的操作符: {op}，支持: {', '.join(sorted(SUPPORTED_OPS))}")
    except Exception as exc:
        return (False, f"比较异常: {exc}")
