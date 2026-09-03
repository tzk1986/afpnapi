"""Collection 可视化编辑器 Service 层。

职责：
- Collection JSON 解析为前端友好的扁平结构
- 前端编辑数据反向构建为标准 Postman Collection JSON
- 变量依赖关系分析（生产/消费/警告）
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from postman_api_tester.assertions import normalize_assertion_rules

logger = logging.getLogger(__name__)

_VARIABLE_REF_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_BASE_URL_VARS = frozenset({"baseUrl", "base_url"})

# v1.37.18: 与 parser._parse_x_extensions bool 分支同口径的字符串白名单
_TRUTHY_STRINGS = {"1", "true", "yes", "y", "on"}


def _normalize_optional_bool(value: Any) -> Optional[bool]:
    """缺失=None（继承）；bool 原值；其余按 parser 同口径字符串归一化为 bool。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY_STRINGS


def parse_collection_to_flat(collection_data: Dict[str, Any]) -> Dict[str, Any]:
    """解析 Collection JSON 为前端友好的扁平结构。

    Args:
        collection_data: 原始 Postman Collection JSON dict

    Returns:
        {
            "collection_info": {name, schema, _postman_id, variables},
            "groups": [{group_name, requests, subgroups}]
        }
    """
    info = collection_data.get("info", {})
    variables = collection_data.get("variable", [])

    return {
        "collection_info": {
            "name": info.get("name", "Imported Collection"),
            "schema": info.get("schema", ""),
            "_postman_id": info.get("_postman_id", uuid.uuid4().hex),
            "variables": variables,
        },
        # v1.37.18: 集合级共享断言（作用于全部接口）
        "x_shared_assertions": normalize_assertion_rules(
            collection_data.get("x_shared_assertions"), source="editor-parse"
        ),
        "groups": _walk_items(collection_data.get("item", []), depth=0),
    }


def _walk_items(items: List[Dict[str, Any]], depth: int) -> List[Dict[str, Any]]:
    """递归遍历 Collection item 树，分离 folder 和 request 节点。"""
    groups: List[Dict[str, Any]] = []
    requests: List[Dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        child_items = item.get("item")
        request_obj = item.get("request")

        if request_obj is not None and not isinstance(child_items, list):
            # 这是一个请求节点
            req_id = uuid.uuid4().hex[:8]
            requests.append(_parse_request_node(item, request_obj, req_id))
        elif isinstance(child_items, list):
            # 这是一个文件夹节点
            group_name = item.get("name", "")
            group: Dict[str, Any] = {
                "group_name": group_name,
                "requests": [],
                "subgroups": [],
            }

            # 递归处理子项
            for child in child_items:
                if not isinstance(child, dict):
                    continue
                child_request = child.get("request")
                child_items_nested = child.get("item")

                if child_request is not None and not isinstance(
                    child_items_nested, list
                ):
                    req_id = uuid.uuid4().hex[:8]
                    group["requests"].append(
                        _parse_request_node(child, child_request, req_id)
                    )
                elif isinstance(child_items_nested, list):
                    subgroup = {
                        "group_name": child.get("name", ""),
                        "requests": [],
                        "subgroups": [],
                    }
                    _walk_items_into_group(child_items_nested, subgroup, depth + 1)
                    group["subgroups"].append(subgroup)

            groups.append(group)

    # 将没有文件夹的请求也作为独立的 group 返回
    if requests:
        groups.append(
            {
                "group_name": "",
                "requests": requests,
                "subgroups": [],
            }
        )

    return groups


def _walk_items_into_group(
    items: List[Dict[str, Any]], group: Dict[str, Any], depth: int
) -> None:
    """递归将 item 填充到指定的 group 中。"""
    for item in items:
        if not isinstance(item, dict):
            continue

        child_items = item.get("item")
        request_obj = item.get("request")

        if request_obj is not None and not isinstance(child_items, list):
            req_id = uuid.uuid4().hex[:8]
            group["requests"].append(_parse_request_node(item, request_obj, req_id))
        elif isinstance(child_items, list):
            subgroup = {
                "group_name": item.get("name", ""),
                "requests": [],
                "subgroups": [],
            }
            _walk_items_into_group(child_items, subgroup, depth + 1)
            group["subgroups"].append(subgroup)


def _parse_request_node(
    item: Dict[str, Any], request_obj: Dict[str, Any], req_id: str
) -> Dict[str, Any]:
    """解析单个请求节点为扁平结构。"""
    # 提取 method
    if isinstance(request_obj, dict):
        method = request_obj.get("method", "GET")
        header = request_obj.get("header", [])
        url_obj = request_obj.get("url", {})
        body_obj = request_obj.get("body")
    else:
        method = "GET"
        header = []
        url_obj = {}
        body_obj = None

    # 提取 URL
    url_str = _get_url_str(url_obj)

    # 提取 params（从 URL 的 query 中）
    params = _extract_params_from_url(url_obj)

    # 提取 body
    body_mode, body_data = _extract_body_mode(body_obj)

    # 提取 x_extract
    x_extract = {}
    if isinstance(request_obj, dict):
        x_extract_raw = request_obj.get("x_extract", {})
        if isinstance(x_extract_raw, dict):
            x_extract = {
                str(k): str(v) for k, v in x_extract_raw.items() if isinstance(v, str)
            }

    # 提取 x_assertions（经归一化过滤非法项）
    x_assertions: List[Dict[str, Any]] = []
    x_judgment_rules: List[Dict[str, Any]] = []
    if isinstance(request_obj, dict):
        x_assertions = normalize_assertion_rules(
            request_obj.get("x_assertions"), source="editor-parse"
        )
        # v1.37.22: 自定义一级判定规则往返
        x_judgment_rules = normalize_assertion_rules(
            request_obj.get("x_judgment_rules"), source="editor-parse"
        )

    # v1.37.18: 判定字段往返（缺失=None，编辑器不丢手工配置）
    flat: Dict[str, Any] = {
        "id": req_id,
        "name": item.get("name", ""),
        "method": str(method).upper(),
        "url": url_str,
        "headers": header if isinstance(header, list) else [],
        "params": params,
        "body_mode": body_mode,
        "body_data": body_data,
        "x_extract": x_extract,
        "x_assertions": x_assertions,
        "x_judgment_rules": x_judgment_rules,
        "description": item.get("description", ""),
        "x_enable_err_code_judgment": None,
        "x_enable_message_judgment": None,
        "x_skip_shared_assertions": None,
        "x_success_err_codes": "",
        "x_success_messages": "",
    }
    if isinstance(request_obj, dict):
        for bool_key in (
            "x_enable_err_code_judgment",
            "x_enable_message_judgment",
            "x_skip_shared_assertions",
        ):
            if request_obj.get(bool_key) is not None:
                flat[bool_key] = _normalize_optional_bool(request_obj[bool_key])
        for str_key in ("x_success_err_codes", "x_success_messages"):
            raw_str = request_obj.get(str_key)
            if raw_str is not None and str(raw_str).strip():
                flat[str_key] = str(raw_str).strip()
    return flat


def _get_url_str(url_obj: Any) -> str:
    """从 Postman URL 对象中提取 URL 字符串。"""
    if isinstance(url_obj, str):
        return url_obj
    if isinstance(url_obj, dict):
        raw = url_obj.get("raw", "")
        if raw:
            return raw
        # 从 path 和 query 构建
        path = url_obj.get("path", [])
        if isinstance(path, list):
            url_str = "/".join(str(p) for p in path if p)
            query = url_obj.get("query", [])
            if isinstance(query, list) and query:
                query_str = "&".join(
                    f"{q.get('key', '')}={q.get('value', '')}"
                    for q in query
                    if isinstance(q, dict)
                )
                if query_str:
                    url_str += "?" + query_str
            return url_str
    return ""


def _extract_params_from_url(url_obj: Any) -> List[Dict[str, str]]:
    """从 URL 对象中提取 query 参数。"""
    if isinstance(url_obj, dict):
        query = url_obj.get("query", [])
        if isinstance(query, list):
            return [
                {"key": q.get("key", ""), "value": q.get("value", "")}
                for q in query
                if isinstance(q, dict)
            ]
    return []


def _extract_body_mode(body_obj: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
    """从 Postman body 对象中提取 body_mode 和 body_data。"""
    if body_obj is None:
        return "none", None

    if not isinstance(body_obj, dict):
        return "none", None

    mode = body_obj.get("mode", "none")

    if mode == "raw":
        raw = body_obj.get("raw", "")
        language = body_obj.get("options", {}).get("raw", {}).get("language", "text")
        return "raw", {"content": raw, "language": language}
    elif mode == "urlencoded":
        data = body_obj.get("urlencoded", [])
        return "urlencoded", {"data": data if isinstance(data, list) else []}
    elif mode == "formdata":
        data = body_obj.get("formdata", [])
        return "formdata", {"data": data if isinstance(data, list) else []}
    elif mode == "graphql":
        graphql_data = body_obj.get("graphql", {})
        return "graphql", {
            "query": graphql_data.get("query", "")
            if isinstance(graphql_data, dict)
            else "",
            "variables": graphql_data.get("variables", "")
            if isinstance(graphql_data, dict)
            else "",
        }
    elif mode == "file":
        return "binary", {"src": body_obj.get("file", {}).get("src", "")}

    return mode, None


def build_collection_json(flat_data: Dict[str, Any]) -> Dict[str, Any]:
    """将前端编辑后的扁平数据组装为标准 Postman Collection JSON。

    Args:
        flat_data: 前端传来的完整数据（含 collection_info + groups）

    Returns:
        标准的 Postman Collection v2.1 JSON dict
    """
    info = flat_data.get("collection_info", {})
    groups = flat_data.get("groups", [])

    collection: Dict[str, Any] = {
        "info": {
            "name": info.get("name", "Collection"),
            "schema": info.get(
                "schema",
                "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            ),
            "_postman_id": info.get("_postman_id", uuid.uuid4().hex),
        },
        "item": _assemble_items(groups),
        "variable": info.get("variables", []),
    }

    # v1.37.18: 根级共享断言写回（归一化防御前端脏值，空不写字段）
    shared = normalize_assertion_rules(
        flat_data.get("x_shared_assertions"), source="editor-build"
    )
    if shared:
        collection["x_shared_assertions"] = shared

    return collection


def _assemble_items(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """递归构建 Collection item 树。"""
    result: List[Dict[str, Any]] = []

    for group in groups:
        requests = group.get("requests", [])
        subgroups = group.get("subgroups", [])

        # 先添加子文件夹
        if subgroups:
            for sg in subgroups:
                sg_items = _assemble_items([sg])
                if sg_items:
                    result.append(sg_items[0])

        # 再添加请求
        for req in requests:
            item = {
                "name": req.get("name", ""),
                "request": _build_request_object(req),
            }
            desc = req.get("description", "")
            if desc:
                item["description"] = desc
            result.append(item)

    return result


def _build_request_object(request: Dict[str, Any]) -> Dict[str, Any]:
    """构建单个请求的 Postman request 对象。"""
    postman_req: Dict[str, Any] = {
        "method": request.get("method", "GET"),
        "header": request.get("headers", []),
        "url": _build_url_object(request.get("url", ""), request.get("params", [])),
    }

    # Body
    body_mode = request.get("body_mode", "none")
    body_data = request.get("body_data")

    if body_mode != "none" and body_data is not None:
        postman_req["body"] = _build_body_object(body_mode, body_data)

    # x_extract
    x_extract = request.get("x_extract", {})
    if x_extract and isinstance(x_extract, dict):
        postman_req["x_extract"] = x_extract

    # x_assertions（再次归一化，防御前端脏值）
    x_assertions = normalize_assertion_rules(
        request.get("x_assertions"), source="editor-build"
    )
    if x_assertions:
        postman_req["x_assertions"] = x_assertions

    # v1.37.22: 自定义一级判定规则写回（再次归一化，空不写）
    x_judgment_rules = normalize_assertion_rules(
        request.get("x_judgment_rules"), source="editor-build"
    )
    if x_judgment_rules:
        postman_req["x_judgment_rules"] = x_judgment_rules

    # v1.37.18: 判定字段写回（bool 三字段 is-not-None 才写且严格 isinstance 防御；
    # success 两字段非空 str 才写——编辑器不编辑、仅保留不丢失）
    for bool_key in (
        "x_enable_err_code_judgment",
        "x_enable_message_judgment",
        "x_skip_shared_assertions",
    ):
        value = request.get(bool_key)
        if value is None:
            continue
        if isinstance(value, bool):
            postman_req[bool_key] = value
        else:
            logger.warning("editor-build 丢弃非 bool 判定字段 %s: %r", bool_key, value)
    for str_key in ("x_success_err_codes", "x_success_messages"):
        raw_str = request.get(str_key)
        if isinstance(raw_str, str) and raw_str.strip():
            postman_req[str_key] = raw_str.strip()

    return postman_req


def _build_url_object(url_str: str, params: List[Dict[str, str]]) -> Dict[str, Any]:
    """构建 Postman URL 对象。"""
    url_obj: Dict[str, Any] = {"raw": url_str}

    if params:
        url_obj["query"] = [
            {"key": p.get("key", ""), "value": p.get("value", "")}
            for p in params
            if isinstance(p, dict)
        ]

    return url_obj


def _build_body_object(body_mode: str, body_data: Dict[str, Any]) -> Dict[str, Any]:
    """构建 Postman body 对象。"""
    body: Dict[str, Any] = {"mode": body_mode}

    if body_mode == "raw":
        body["raw"] = body_data.get("content", "")
        language = body_data.get("language", "text")
        body["options"] = {"raw": {"language": language}}
    elif body_mode == "urlencoded":
        body["urlencoded"] = body_data.get("data", [])
    elif body_mode == "formdata":
        body["formdata"] = body_data.get("data", [])
    elif body_mode == "graphql":
        body["graphql"] = {
            "query": body_data.get("query", ""),
            "variables": body_data.get("variables", ""),
        }
    elif body_mode == "binary":
        body["file"] = {"src": body_data.get("src", "")}

    return body


def analyze_dependency_map(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """分析变量生产/消费关系。

    Returns:
        {
            "produced": {var_name: {by_request: req_id, by_name: req_name}},
            "consumed": {var_name: {by_requests: [{request_id, location}]}},
            "warnings": [{var_name, issue, affected_by}]
        }
    """
    produced: Dict[str, Dict[str, str]] = {}
    consumed: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
    warnings: List[Dict[str, Any]] = []

    # Phase 1: 收集变量生产（x_extract）
    def walk_produce(gs: List[Dict[str, Any]]) -> None:
        for g in gs:
            for req in g.get("requests", []):
                x_extract = req.get("x_extract", {})
                if isinstance(x_extract, dict):
                    for var_name in x_extract:
                        produced[var_name] = {
                            "by_request": req["id"],
                            "by_name": req.get("name", ""),
                        }
            walk_produce(g.get("subgroups", []))

    walk_produce(groups)

    # Phase 2: 收集变量消费
    def collect_text_refs(request: Dict[str, Any]) -> List[str]:
        """从请求的所有文本字段中提取 {{变量}} 引用。"""
        texts: List[str] = [request.get("url", "")]

        for h in request.get("headers", []):
            if isinstance(h, dict):
                texts.append(h.get("key", ""))
                texts.append(h.get("value", ""))

        for p in request.get("params", []):
            if isinstance(p, dict):
                texts.append(p.get("key", ""))
                texts.append(p.get("value", ""))

        body_data = request.get("body_data")
        if isinstance(body_data, dict):
            if body_data.get("content"):
                texts.append(str(body_data["content"]))
            if body_data.get("raw"):
                texts.append(str(body_data["raw"]))

        refs: Set[str] = set()
        for text in texts:
            for var_ref in _VARIABLE_REF_PATTERN.findall(str(text)):
                if var_ref not in _BASE_URL_VARS:
                    refs.add(var_ref)
        return list(refs)

    def walk_consume(gs: List[Dict[str, Any]]) -> None:
        for g in gs:
            for req in g.get("requests", []):
                var_refs = collect_text_refs(req)
                for var_ref in var_refs:
                    if var_ref not in consumed:
                        consumed[var_ref] = {"by_requests": []}
                    consumed[var_ref]["by_requests"].append(
                        {
                            "request_id": req["id"],
                            "location": f"{req.get('method', '')} {req.get('name', '')}",
                        }
                    )
            walk_consume(g.get("subgroups", []))

    walk_consume(groups)

    # Phase 3: 生成警告
    for var_name, consume_info in consumed.items():
        if var_name not in produced:
            warnings.append(
                {
                    "var_name": var_name,
                    "issue": "not_produced",
                    "affected_by": consume_info["by_requests"],
                }
            )

    return {
        "produced": produced,
        "consumed": consumed,
        "warnings": warnings,
    }


def send_single_request(
    request_data: Dict[str, Any], variables: Dict[str, str]
) -> Dict[str, Any]:
    """对单个请求执行变量替换后发送，返回完整响应。

    Args:
        request_data: 单个请求的完整配置（url/method/headers/params/body_mode/body_data）
        variables: 预置变量字典，用于替换 {{var}} 占位符

    Returns:
        execute_http_request() 的原始返回 dict
    """
    from postman_api_tester.handlers.http_handler import execute_http_request
    from postman_api_tester.utils.variable_substitution import substitute_variables

    url = substitute_variables(request_data.get("url", ""), variables)

    headers: Dict[str, str] = {}
    for h in request_data.get("headers", []):
        if isinstance(h, dict) and not h.get("disabled"):
            k = substitute_variables(str(h.get("key", "")), variables)
            v = substitute_variables(str(h.get("value", "")), variables)
            if k:
                headers[k] = v

    params: Dict[str, str] = {}
    for p in request_data.get("params", []):
        if isinstance(p, dict) and not p.get("disabled"):
            k = substitute_variables(str(p.get("key", "")), variables)
            v = substitute_variables(str(p.get("value", "")), variables)
            if k:
                params[k] = v

    body_mode = request_data.get("body_mode", "none")
    body_data = request_data.get("body_data")
    if body_mode == "raw" and isinstance(body_data, dict):
        content = substitute_variables(str(body_data.get("content", "")), variables)
        language = str(body_data.get("language", "json"))
        body_data = {
            "raw_content": content,
            "raw_language": language,
            "raw_content_type": "application/json" if language == "json" else "",
        }

    return execute_http_request(
        url=url,
        method=request_data.get("method", "GET"),
        headers=headers,
        params=params,
        body_mode=body_mode,
        body_data=body_data,
        legacy_body=None,
        is_multipart=False,
        files_source=None,
    )


def validate_for_execution(flat_data: Dict[str, Any]) -> List[str]:
    """执行前验证，返回错误列表。"""
    errors: List[str] = []

    if not flat_data.get("groups"):
        errors.append("Collection 中没有接口")

    for group in flat_data.get("groups", []):
        for req in group.get("requests", []):
            if not req.get("name"):
                errors.append(f"接口 {req.get('id', 'unknown')} 缺少名称")
            if not req.get("url"):
                errors.append(f"接口 {req.get('name', 'unknown')} 缺少 URL")
            method = req.get("method", "")
            valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            if method and method not in valid_methods:
                errors.append(f"接口 {req.get('name', 'unknown')} 方法 {method} 无效")

    return errors


__all__ = [
    "parse_collection_to_flat",
    "build_collection_json",
    "analyze_dependency_map",
    "validate_for_execution",
    "send_single_request",
]
