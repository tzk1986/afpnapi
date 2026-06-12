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
    错误码：CE_PARSE_001/002/003/004
    """
    try:
        file = request.files.get("file")
        if file:
            content = file.read().decode("utf-8")
            collection_data = json.loads(content)
        else:
            body = request.get_json(force=True, silent=True)
            if not body or "collection_json" not in body:
                return _json_error("请求体缺少 collection_json 字段", 400, "CE_PARSE_001")
            collection_data = body["collection_json"]

        if not isinstance(collection_data, dict):
            return _json_error("Collection JSON 格式无效，请确认是 Postman Collection v2.1", 400, "CE_PARSE_002")

        from postman_api_tester.services.collection_editor_service import (
            parse_collection_to_flat as _svc_parse_collection_to_flat,
        )

        result = _svc_parse_collection_to_flat(collection_data)
        return jsonify(result)

    except json.JSONDecodeError as e:
        return _json_error(f"JSON 语法错误：{e}", 400, "CE_PARSE_003")
    except Exception as e:
        logger.exception("parse_collection error")
        return _json_error(f"解析异常：{type(e).__name__}，请检查 Collection 结构", 500, "CE_PARSE_004")


def api_collection_save() -> ResponseReturnValue:
    """PUT /api/collection-editor/save

    保存编辑后的数据，返回标准 Collection JSON。
    错误码：CE_SAVE_001/002/003
    """
    try:
        flat_data = request.get_json(force=True, silent=True)
        if not flat_data:
            return _json_error("保存时缺少请求体数据", 400, "CE_SAVE_001")

        from postman_api_tester.services.collection_editor_service import (
            build_collection_json as _svc_build_collection_json,
            validate_for_execution as _svc_validate_for_execution,
        )

        errors = _svc_validate_for_execution(flat_data)
        if errors:
            return _json_error(f"数据校验失败：{'; '.join(errors)}", 400, "CE_SAVE_002")

        collection_json = _svc_build_collection_json(flat_data)
        return jsonify({"collection_json": collection_json})

    except Exception as e:
        logger.exception("save_collection error")
        return _json_error(f"保存异常：{type(e).__name__}", 500, "CE_SAVE_003")


def api_collection_dependency() -> ResponseReturnValue:
    """POST /api/collection-editor/dependency

    获取变量依赖关系图。
    错误码：CE_DEP_001/002
    """
    try:
        flat_data = request.get_json(force=True, silent=True)
        if not flat_data or "groups" not in flat_data:
            return _json_error("依赖分析缺少 groups 字段", 400, "CE_DEP_001")

        from postman_api_tester.services.collection_editor_service import (
            analyze_dependency_map as _svc_analyze_dependency_map,
        )

        result = _svc_analyze_dependency_map(flat_data["groups"])
        return jsonify(result)

    except Exception as e:
        logger.exception("dependency_analysis error")
        return _json_error(f"依赖分析异常：{type(e).__name__}", 500, "CE_DEP_002")


def api_collection_send() -> ResponseReturnValue:
    """POST /api/collection-editor/send

    发送单个请求，返回完整响应（status_code/elapsed_ms/headers/body）。
    错误码：CE_SEND_001/002/003/004/005
    """
    try:
        body = request.get_json(force=True, silent=True)
        if not body or "request" not in body:
            return _json_error("发送请求缺少 request 字段", 400, "CE_SEND_001")

        request_data = body["request"]
        if not isinstance(request_data, dict):
            return _json_error("request 必须是 JSON 对象", 400, "CE_SEND_002")

        variables = body.get("variables", {})
        if not isinstance(variables, dict):
            return _json_error("variables 必须是 JSON 对象", 400, "CE_SEND_003")

        from postman_api_tester.services.collection_editor_service import (
            send_single_request as _svc_send_single_request,
        )

        result = _svc_send_single_request(request_data, variables)

        if not result.get("success"):
            status = result.get("status_code", 502)
            err_msg = result.get("error_message", "请求失败")
            return _json_error(f"目标接口返回 {status}：{err_msg}", status, "CE_SEND_004")

        return jsonify({
            "status_code": result["status_code"],
            "elapsed_ms": result["elapsed_ms"],
            "response_headers": result["response_headers"],
            "response_body": result["response_body"],
            "actual_request_url": result.get("actual_request_url", ""),
        })

    except Exception as e:
        logger.exception("send_request error")
        return _json_error(f"发送异常：{type(e).__name__}，请检查 URL 和变量配置", 500, "CE_SEND_005")
