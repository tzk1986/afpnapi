"""Pre-request 沙箱表达式执行器。

在请求发出前执行用户定义的 Python 表达式，动态计算变量值。
采用沙箱隔离：限制内置函数、白名单模块、危险关键字检查、超时保护。

开发导读:
- 仅允许纯计算操作（哈希、编码、时间戳等），禁止文件/网络/系统调用。
- 表达式执行失败返回空字符串，不中断请求流程。
- 跨平台超时：Unix 使用 signal.SIGALRM，Windows 使用 ThreadPoolExecutor。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Dict

logger = logging.getLogger(__name__)

_SAFE_BUILTINS: Dict[str, object] = {
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
    "len": len,
    "range": range,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "isinstance": isinstance,
    "True": True,
    "False": False,
    "None": None,
}

_SAFE_MODULES: Dict[str, object] = {
    "hashlib": hashlib,
    "hmac": hmac,
    "base64": base64,
    "time": time,
    "json": json,
    "re": re,
}

_DANGEROUS_KEYWORDS = re.compile(
    r"\b(import|__import__|exec|eval|compile|open|os|sys|subprocess|"
    r"__builtins__|globals|locals|getattr|setattr|delattr|"
    r"__class__|__subclasses__|__bases__|__mro__|__init__|"
    r"breakpoint|exit|quit|input)\b"
)

_TIMEOUT_SECONDS = 1


def _contains_dangerous_keyword(expression: str) -> bool:
    """检查表达式是否包含危险关键字。"""
    return _DANGEROUS_KEYWORDS.search(expression) is not None


def _execute_expression(expression: str, sandbox_globals: Dict[str, object]) -> str:
    """在沙箱中执行单个表达式，返回字符串结果。"""
    try:
        value = eval(expression, sandbox_globals)  # noqa: S307
        return str(value) if value is not None else ""
    except SyntaxError as e:
        logger.warning("pre-request syntax error: %s", e)
        return ""
    except Exception as e:
        logger.warning("pre-request execution error: %s: %s", type(e).__name__, e)
        return ""


def _execute_with_thread_timeout(
    expression: str,
    sandbox_globals: Dict[str, object],
    timeout: float,
) -> str:
    """使用 ThreadPoolExecutor 实现跨平台超时。"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_execute_expression, expression, sandbox_globals)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            logger.warning("pre-request expression timeout (%.1fs)", timeout)
            return ""


def _execute_with_signal_timeout(
    expression: str,
    sandbox_globals: Dict[str, object],
    timeout: float,
) -> str:
    """使用 signal.SIGALRM 实现 Unix 超时（更高效）。"""
    import signal

    class _TimeoutError(Exception):
        pass

    def _handler(signum: int, frame: object) -> None:
        raise _TimeoutError("pre-request expression timeout")

    old_handler = signal.signal(signal.SIGALRM, _handler)  # type: ignore[attr-defined]
    signal.setitimer(signal.ITIMER_REAL, timeout)  # type: ignore[attr-defined]
    try:
        return _execute_expression(expression, sandbox_globals)
    except _TimeoutError:
        logger.warning("pre-request expression timeout (%.1fs)", timeout)
        return ""
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)  # type: ignore[attr-defined]
        signal.signal(signal.SIGALRM, old_handler)  # type: ignore[attr-defined]


def _execute_with_timeout(expression: str, sandbox_globals: Dict[str, object]) -> str:
    """跨平台超时执行：Unix 用 signal，Windows 用线程池。"""
    if sys.platform == "win32":
        return _execute_with_thread_timeout(expression, sandbox_globals, _TIMEOUT_SECONDS)
    return _execute_with_signal_timeout(expression, sandbox_globals, _TIMEOUT_SECONDS)


def execute_pre_request(
    expressions: Dict[str, str],
    existing_variables: Dict[str, str],
) -> Dict[str, str]:
    """执行 pre-request 表达式，返回结果变量字典。

    - expressions: {变量名: Python 表达式}
    - existing_variables: 当前已有的变量（可在表达式中引用）
    """
    if not expressions:
        return {}

    result: Dict[str, str] = {}
    sandbox_globals: Dict[str, object] = {"__builtins__": _SAFE_BUILTINS}
    sandbox_globals.update(_SAFE_MODULES)
    sandbox_globals.update({"variables": existing_variables, "result": result})

    for var_name, expression in expressions.items():
        if _contains_dangerous_keyword(expression):
            logger.warning("pre-request blocked dangerous expression in '%s'", var_name)
            result[var_name] = ""
            continue

        result[var_name] = _execute_with_timeout(expression, sandbox_globals)
        sandbox_globals["result"] = result
        sandbox_globals["variables"] = {**existing_variables, **result}

    return result
