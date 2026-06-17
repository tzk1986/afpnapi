"""变量替换引擎。

支持 {{variable}} 和 {{func(arg1,arg2)}} 两种格式的占位符替换，
为数据驱动和请求串联两个功能共享使用。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from postman_api_tester.parser import ApiConfig
from postman_api_tester.utils.variable_functions import evaluate_function

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_FUNC_PATTERN = re.compile(r"\{\{(\w+)\(([^)]*)\)\}\}")
_SENTINEL = object()
_BASE_URL_VARIABLES = frozenset({"baseUrl", "base_url"})


def _is_functions_enabled() -> bool:
    """延迟读取配置，避免循环导入。"""
    try:
        from postman_api_tester import config as _cfg
        return bool(getattr(_cfg, "ENABLE_VARIABLE_FUNCTIONS", True))
    except (ImportError, AttributeError):
        return True


def substitute_variables(text: str, variables: Dict[str, str]) -> str:
    """替换文本中的 ``{{variable}}`` 和 ``{{func(args)}}`` 为对应值。

    处理顺序：先替换函数调用（``{{timestamp()}}``），再替换普通变量（``{{token}}``）。
    - 未匹配的变量保持原样（不报错）
    - 未知函数保持原样（不报错）
    - ``ENABLE_VARIABLE_FUNCTIONS=false`` 时函数表达式原样保留
    - 不递归替换（替换后的值中若含 ``{{...}}`` 不再处理）
    - ``{{baseUrl}}`` / ``{{base_url}}`` 不在此处理（由 base_url 逻辑专属处理）
    """
    if not text:
        return text

    # 第一轮：函数调用替换（仅当 ENABLE_VARIABLE_FUNCTIONS=true 时执行）
    if _is_functions_enabled():
        def _func_replacer(match: re.Match[str]) -> str:
            func_name = match.group(1)
            args_str = match.group(2)
            result = evaluate_function(func_name, args_str)
            if result is not None:
                return result
            return match.group(0)  # 未知函数，原样保留

        text = _FUNC_PATTERN.sub(_func_replacer, text)

    if not variables:
        return text

    # 第二轮：普通变量替换（原有逻辑）
    def _var_replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name in _BASE_URL_VARIABLES:
            return match.group(0)
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)

    return _VARIABLE_PATTERN.sub(_var_replacer, text)


def _substitute_body(body: Any, variables: Dict[str, str]) -> Any:
    """递归替换 body 中的字符串值。"""
    if isinstance(body, str):
        return substitute_variables(body, variables)
    if isinstance(body, dict):
        return {k: _substitute_body(v, variables) for k, v in body.items()}
    if isinstance(body, list):
        return [_substitute_body(item, variables) for item in body]
    return body


def _substitute_params(params: Dict[str, object], variables: Dict[str, str]) -> Dict[str, object]:
    """替换请求参数中的键名和字符串值。"""
    if not variables and not _is_functions_enabled():
        return dict(params)
    result: Dict[str, object] = {}
    for key, value in params.items():
        new_key = substitute_variables(key, variables)
        if isinstance(value, str):
            result[new_key] = substitute_variables(value, variables)
        else:
            result[new_key] = value
    return result


def _copy_api_config(
    api: ApiConfig,
    *,
    url: Any = _SENTINEL,
    full_url: Any = _SENTINEL,
    headers: Any = _SENTINEL,
    params: Any = _SENTINEL,
    body: Any = _SENTINEL,
) -> ApiConfig:
    """构造 ApiConfig 副本，仅覆盖显式传入的字段。"""
    result: ApiConfig = {}
    for field in ("name", "folder", "method", "description", "expected_status",
                  "x_assertions", "x_expected_status", "x_success_err_codes",
                  "x_success_messages", "x_enable_err_code_judgment",
                  "x_enable_message_judgment"):
        if field in api:
            result[field] = api[field]
    if "url" in api:
        result["url"] = api["url"] if url is _SENTINEL else url
    if "full_url" in api:
        result["full_url"] = api["full_url"] if full_url is _SENTINEL else full_url
    if "headers" in api:
        result["headers"] = api["headers"] if headers is _SENTINEL else headers
    if "body" in api:
        result["body"] = api["body"] if body is _SENTINEL else body
    if "params" in api:
        result["params"] = api["params"] if params is _SENTINEL else params
    if "item_path" in api:
        result["item_path"] = api["item_path"]
    return result


def substitute_in_api_config(api: ApiConfig, variables: Dict[str, str]) -> ApiConfig:
    """对 ApiConfig 中的 URL/headers/body/params 执行变量替换。

    返回新的 ApiConfig 副本，不修改原始对象。
    """
    if not variables:
        return _copy_api_config(api)

    raw_url = api.get("url")
    new_url: Any = substitute_variables(str(raw_url), variables) if raw_url is not None else _SENTINEL
    raw_full_url = api.get("full_url")
    new_full_url: Any = substitute_variables(str(raw_full_url), variables) if raw_full_url is not None else _SENTINEL

    raw_headers = api.get("headers")
    new_headers: Any = _SENTINEL
    if isinstance(raw_headers, dict) and raw_headers:
        new_headers = {
            substitute_variables(str(k), variables): substitute_variables(str(v), variables)
            for k, v in raw_headers.items()
        }

    raw_params = api.get("params")
    new_params: Any = _SENTINEL
    if isinstance(raw_params, dict) and raw_params:
        new_params = _substitute_params(raw_params, variables)

    body = api.get("body")
    new_body: Any = _substitute_body(body, variables) if body is not None else _SENTINEL

    return _copy_api_config(
        api,
        **{k: v for k, v in [
            ("url", new_url),
            ("full_url", new_full_url),
            ("headers", new_headers),
            ("params", new_params),
            ("body", new_body),
        ] if v is not _SENTINEL},
    )


def extract_referenced_variables(text: str) -> set[str]:
    """提取文本中所有 ``{{variable}}`` 引用的变量名集合。"""
    if not text:
        return set()
    return set(_VARIABLE_PATTERN.findall(text))


def api_references_variables(api: ApiConfig, variable_names: set[str]) -> bool:
    """检测 api 的 URL/headers/body/params 是否引用了指定变量名集合中的变量。

    排除 ``baseUrl`` / ``base_url``。
    """
    if not variable_names:
        return False

    check_targets: list[str] = []
    if "url" in api:
        check_targets.append(str(api["url"]))
    if "full_url" in api:
        check_targets.append(str(api["full_url"]))

    raw_headers = api.get("headers")
    if isinstance(raw_headers, dict):
        for k, v in raw_headers.items():
            check_targets.append(str(k))
            check_targets.append(str(v))

    raw_params = api.get("params")
    if isinstance(raw_params, dict):
        for pk, pv in raw_params.items():
            check_targets.append(str(pk))
            if isinstance(pv, str):
                check_targets.append(pv)

    body = api.get("body")
    if isinstance(body, str):
        check_targets.append(body)
    elif isinstance(body, dict):
        _collect_strings(body, check_targets)
    elif isinstance(body, list):
        for item in body:
            if isinstance(item, str):
                check_targets.append(item)

    for target in check_targets:
        refs = extract_referenced_variables(target) - _BASE_URL_VARIABLES
        if refs & variable_names:
            return True
    return False


def _collect_strings(obj: Any, accumulator: list[str]) -> None:
    """递归收集对象中的所有字符串值。"""
    if isinstance(obj, str):
        accumulator.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, accumulator)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, accumulator)
