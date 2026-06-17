"""全局变量 CRUD 路由处理函数。

提供：
- GET  /api/global-variables     — 读取变量列表（值脱敏）
- POST /api/global-variables     — 设置单个变量（{key, value}）
- DELETE /api/global-variables   — 清空所有变量
- DELETE /api/global-variables/<key> — 删除单个变量
"""

from __future__ import annotations

import logging

from flask import request
from flask.typing import ResponseReturnValue

from postman_api_tester.exceptions import ValidationError
from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.global_variables_service import (
    clear_variables,
    delete_variable,
    mask_value,
    read_variables,
    set_variable,
)

logger = logging.getLogger(__name__)


def _get_file_path() -> str:
    """从 report_server_config 读取文件路径。"""
    from postman_api_tester.report_server_config import GLOBAL_VARIABLES_FILE
    return GLOBAL_VARIABLES_FILE


def _get_max_count() -> int:
    from postman_api_tester.report_server_config import GLOBAL_VARIABLES_MAX_COUNT
    return GLOBAL_VARIABLES_MAX_COUNT


def api_global_variables_get() -> ResponseReturnValue:
    """GET /api/global-variables — 读取变量列表（值脱敏）。"""
    file_path = _get_file_path()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    data = read_variables(file_path, _get_max_count())
    masked = {k: mask_value(str(v)) for k, v in data["variables"].items()}
    return BaseHandler.json_response({
        "variables": masked,
        "count": data["count"],
        "updated_at": data["updated_at"],
        "file_path": file_path,
    })


def api_global_variables_set() -> ResponseReturnValue:
    """POST /api/global-variables — 设置单个变量。"""
    file_path = _get_file_path()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    body = request.get_json(silent=True) or {}
    key = str(body.get("key", "")).strip()
    value = str(body.get("value", "")).strip()

    if not key:
        return json_error("缺少 key 字段", 400, "GV_SET_001")
    if not value:
        return json_error("缺少 value 字段", 400, "GV_SET_002")

    result = set_variable(file_path, key, value, _get_max_count())
    logger.info("global variable set: %s", key)
    return BaseHandler.json_response({"count": result["count"], "truncated": result["truncated"]})


def api_global_variables_delete(key: str = "") -> ResponseReturnValue:
    """DELETE /api/global-variables/<key> — 删除单个变量。"""
    file_path = _get_file_path()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    if not key:
        return json_error("缺少 key 参数", 400, "GV_DEL_001")

    deleted = delete_variable(file_path, key)
    if not deleted:
        return json_error(f"变量 '{key}' 不存在", 404, "GV_DEL_002")

    logger.info("global variable deleted: %s", key)
    return BaseHandler.json_response({"deleted": True, "key": key})


def api_global_variables_clear() -> ResponseReturnValue:
    """DELETE /api/global-variables — 清空所有变量。"""
    file_path = _get_file_path()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    clear_variables(file_path)
    logger.info("global variables cleared")
    return BaseHandler.json_response({"cleared": True})
