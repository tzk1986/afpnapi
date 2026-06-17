"""内置变量函数注册表。

支持在 ``{{func_name(arg1,arg2)}}`` 语法中调用内置函数，
每次变量替换时实时计算并返回字符串结果。

开发导读:
- 函数通过 ``@register`` 装饰器注册，注册后即可在模板中使用。
- 未知函数名或参数错误时返回空字符串，由调用方决定是否保留原文。
"""

from __future__ import annotations

import random
import time
import uuid
from datetime import datetime
from typing import Callable, Dict

VariableFunc = Callable[..., str]

_BUILT_IN_FUNCTIONS: Dict[str, VariableFunc] = {}


def register(name: str) -> Callable[[VariableFunc], VariableFunc]:
    """注册一个内置变量函数。

    用法::

        @register("my_func")
        def _my_func(arg: str = "") -> str:
            return arg.upper()
    """
    def decorator(fn: VariableFunc) -> VariableFunc:
        _BUILT_IN_FUNCTIONS[name] = fn
        return fn
    return decorator


def get_registered_names() -> list[str]:
    """返回已注册的函数名列表（用于自动补全等场景）。"""
    return list(_BUILT_IN_FUNCTIONS.keys())


def evaluate_function(name: str, args_str: str) -> str:
    """解析并执行内置函数，返回字符串结果。

    - 函数不存在时返回 ``None``，表示不是已知函数（调用方保留原文）。
    - 函数存在但执行失败时返回空字符串。
    """
    fn = _BUILT_IN_FUNCTIONS.get(name)
    if fn is None:
        return None  # type: ignore[return-value]
    args = [a.strip() for a in args_str.split(",") if a.strip()] if args_str.strip() else []
    try:
        return fn(*args)
    except (TypeError, ValueError):
        return ""


# ── 内置函数 ────────────────────────────────────────────────────────────────

@register("timestamp")
def _timestamp() -> str:
    """Unix 时间戳（秒）。"""
    return str(int(time.time()))


@register("timestamp_ms")
def _timestamp_ms() -> str:
    """Unix 时间戳（毫秒）。"""
    return str(int(time.time() * 1000))


@register("uuid")
def _uuid() -> str:
    """UUID v4 字符串。"""
    return str(uuid.uuid4())


@register("random_int")
def _random_int(low: str = "0", high: str = "100") -> str:
    """随机整数 [low, high]。"""
    return str(random.randint(int(low), int(high)))


@register("date")
def _date(fmt: str = "") -> str:
    """当前日期，默认格式 ``%Y-%m-%d``。"""
    return datetime.now().strftime(fmt or "%Y-%m-%d")


@register("datetime")
def _datetime(fmt: str = "") -> str:
    """当前日期时间，默认格式 ``%Y-%m-%d %H:%M:%S``。"""
    return datetime.now().strftime(fmt or "%Y-%m-%d %H:%M:%S")


# ── 函数元数据（用于 UI 展示）──────────────────────────────────────────

_FUNCTION_META: Dict[str, Dict[str, str]] = {
    "timestamp": {
        "syntax": "{{timestamp()}}",
        "params": "无",
        "description": "Unix 时间戳（秒，10 位）",
        "example": "1750147200",
    },
    "timestamp_ms": {
        "syntax": "{{timestamp_ms()}}",
        "params": "无",
        "description": "Unix 时间戳（毫秒，13 位）",
        "example": "1750147200123",
    },
    "uuid": {
        "syntax": "{{uuid()}}",
        "params": "无",
        "description": "UUID v4 随机字符串",
        "example": "a3b1c2d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    },
    "random_int": {
        "syntax": "{{random_int(low,high)}}",
        "params": "low=下限(默认0), high=上限(默认100)",
        "description": "指定范围内的随机整数",
        "example": "{{random_int(1,100)}} → 42",
    },
    "date": {
        "syntax": "{{date(fmt)}}",
        "params": "fmt=日期格式(默认%Y-%m-%d)",
        "description": "当前日期字符串",
        "example": "{{date(%Y%m%d)}} → 20260617",
    },
    "datetime": {
        "syntax": "{{datetime(fmt)}}",
        "params": "fmt=日期时间格式(默认%Y-%m-%d %H:%M:%S)",
        "description": "当前日期时间字符串",
        "example": "{{datetime(%H:%M)}} → 14:30",
    },
}


def get_function_metadata() -> list[dict[str, str]]:
    """返回所有已注册函数的元数据列表（按注册顺序），用于 UI 帮助面板。"""
    result: list[dict[str, str]] = []
    for name in _BUILT_IN_FUNCTIONS:
        meta = _FUNCTION_META.get(name, {})
        result.append({
            "name": name,
            "syntax": meta.get("syntax", "{{" + name + "()}}"),
            "params": meta.get("params", ""),
            "description": meta.get("description", ""),
            "example": meta.get("example", ""),
        })
    return result
