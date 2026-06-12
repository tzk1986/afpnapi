"""Collection 可视化编辑器 Handler 层。

职责：
- 接收 HTTP 请求，调用 service 层处理
- 返回 JSON 响应
"""

import json
import logging

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error

logger = logging.getLogger(__name__)


def api_collection_parse() -> ResponseReturnValue:
    """POST /api/collection-editor/parse

    上传并解析 Collection JSON 文件。
    """
    try:
        file = request.files.get("file")
        if file:
            content = file.read().decode("utf-8")
            collection_data = json.loads(content)
        else:
            body = request.get_json(force=True, silent=True)
            if not body or "collection_json" not in body:
                return _json_error("缺少 collection_json 字段", 400)
            collection_data = body["collection_json"]

        if not isinstance(collection_data, dict):
            return _json_error("Collection JSON 格式无效", 400)

        from postman_api_tester.services.collection_editor_service import (
            parse_collection_to_flat as _svc_parse_collection_to_flat,
        )

        result = _svc_parse_collection_to_flat(collection_data)
        return jsonify(result)

    except json.JSONDecodeError as e:
        return _json_error(f"JSON 解析失败：{e}", 400)
    except Exception as e:
        logger.exception("parse_collection error")
        return _json_error(f"解析失败：{e}", 500)


def api_collection_save() -> ResponseReturnValue:
    """PUT /api/collection-editor/save

    保存编辑后的数据，返回标准 Collection JSON。
    """
    try:
        flat_data = request.get_json(force=True, silent=True)
        if not flat_data:
            return _json_error("缺少请求体", 400)

        from postman_api_tester.services.collection_editor_service import (
            build_collection_json as _svc_build_collection_json,
            validate_for_execution as _svc_validate_for_execution,
        )

        errors = _svc_validate_for_execution(flat_data)
        if errors:
            return _json_error("; ".join(errors), 400)

        collection_json = _svc_build_collection_json(flat_data)
        return jsonify({"collection_json": collection_json})

    except Exception as e:
        logger.exception("save_collection error")
        return _json_error(f"保存失败：{e}", 500)


def api_collection_dependency() -> ResponseReturnValue:
    """POST /api/collection-editor/dependency

    获取变量依赖关系图。
    """
    try:
        flat_data = request.get_json(force=True, silent=True)
        if not flat_data or "groups" not in flat_data:
            return _json_error("缺少 groups 字段", 400)

        from postman_api_tester.services.collection_editor_service import (
            analyze_dependency_map as _svc_analyze_dependency_map,
        )

        result = _svc_analyze_dependency_map(flat_data["groups"])
        return jsonify(result)

    except Exception as e:
        logger.exception("dependency_analysis error")
        return _json_error(f"分析失败：{e}", 500)


def api_collection_send() -> ResponseReturnValue:
    """POST /api/collection-editor/send

    发送单个请求，返回完整响应（status_code/elapsed_ms/headers/body）。
    """
    try:
        body = request.get_json(force=True, silent=True)
        if not body or "request" not in body:
            return _json_error("缺少 request 字段", 400)

        request_data = body["request"]
        if not isinstance(request_data, dict):
            return _json_error("request 必须是对象", 400)

        variables = body.get("variables", {})
        if not isinstance(variables, dict):
            return _json_error("variables 必须是对象", 400)

        from postman_api_tester.services.collection_editor_service import (
            send_single_request as _svc_send_single_request,
        )

        result = _svc_send_single_request(request_data, variables)

        if not result.get("success"):
            return _json_error(
                result.get("error_message", "请求失败"),
                result.get("error_code", 502),
            )

        return jsonify({
            "status_code": result["status_code"],
            "elapsed_ms": result["elapsed_ms"],
            "response_headers": result["response_headers"],
            "response_body": result["response_body"],
            "actual_request_url": result.get("actual_request_url", ""),
        })

    except Exception as e:
        logger.exception("send_request error")
        return _json_error(f"发送失败：{e}", 500)
