"""JSONPath 轻量提取工具。

仅支持简化路径语法（字段访问 + 数组索引），禁止 eval/exec/过滤器/通配符。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_HEADER_PREFIX = "$header."
_FIELD_PATTERN = re.compile(r"^\$(?:\.([A-Za-z_][A-Za-z0-9_]*))*(?:\[(-?\d+)\])?(?:\.([A-Za-z_][A-Za-z0-9_]*)(?:\[(-?\d+)\])?)*$")


def _parse_path(expression: str) -> Optional[List[tuple[str, Optional[int]]]]:
    """将简化 JSONPath 表达式解析为 (field_name, optional_index) 段列表。

    返回 None 表示表达式非法（含通配符/过滤器/递归下降等）。
    """
    if not expression or not expression.startswith("$."):
        return None
    if ".." in expression or "*" in expression or "?" in expression or "[" in expression.split("$.", 1)[0]:
        return None

    body = expression[2:]
    if not body:
        return None

    segments: list[tuple[str, Optional[int]]] = []
    remaining = body

    while remaining:
        if remaining.startswith("."):
            remaining = remaining[1:]
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", remaining)
        if not match:
            return None
        field = match.group(1)
        remaining = remaining[match.end():]

        index: Optional[int] = None
        if remaining.startswith("["):
            idx_match = re.match(r"\[(-?\d+)\]", remaining)
            if not idx_match:
                return None
            index = int(idx_match.group(1))
            remaining = remaining[idx_match.end():]

        segments.append((field, index))

    return segments if segments else None


def _navigate_segments(data: Any, segments: List[tuple[str, Optional[int]]]) -> Any:
    """沿段列表逐层导航，任一层失败返回 _MISSING。"""
    current = data
    for field, index in segments:
        if isinstance(current, dict):
            if field not in current:
                return _MISSING
            current = current[field]
        else:
            return _MISSING
        if index is not None:
            if not isinstance(current, list):
                return _MISSING
            try:
                current = current[index]
            except IndexError:
                return _MISSING
    return current


class _Missing:
    """哨兵值，标识提取路径不存在。"""

    pass


_MISSING = _Missing()


def extract_by_jsonpath(data: Any, expression: str) -> Optional[str]:
    """从 JSON 数据中按简化 JSONPath 表达式提取值，返回字符串形式。

    支持：
    - ``$.field`` 简单字段
    - ``$.data.token`` 嵌套字段
    - ``$.items[0].id`` 数组索引（含负索引）

    不支持：通配符 ``$.*``、递归下降 ``$..``、过滤器 ``$?[...]``。

    提取失败（路径不存在/表达式非法）返回 ``None``。
    提取到的值为 None 时返回 ``"None"``（字符串化）。
    """
    segments = _parse_path(expression)
    if segments is None:
        return None
    result = _navigate_segments(data, segments)
    if isinstance(result, _Missing):
        return None
    if result is None:
        return "None"
    if isinstance(result, bool):
        return "true" if result else "false"
    if isinstance(result, (dict, list)):
        import json
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def extract_from_header(headers: Dict[str, str], header_name: str) -> Optional[str]:
    """从响应头字典中提取指定名称的值（大小写不敏感）。"""
    lower_name = header_name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value
    return None


def extract_from_response(
    response_data: Any,
    response_headers: Dict[str, str],
    extract_config: Dict[str, str],
) -> Dict[str, str]:
    """根据 x_extract 配置批量提取变量。

    - 以 ``$header.`` 开头的表达式从响应头提取
    - 其余表达式从响应体 JSON 提取
    - 提取失败的字段不包含在结果字典中
    """
    result: Dict[str, str] = {}
    for var_name, expression in extract_config.items():
        if not isinstance(expression, str):
            continue
        value: Optional[str] = None
        if expression.startswith(_HEADER_PREFIX):
            header_name = expression[len(_HEADER_PREFIX):]
            if header_name:
                value = extract_from_header(response_headers, header_name)
        else:
            value = extract_by_jsonpath(response_data, expression)
        if value is not None:
            result[var_name] = value
    return result
