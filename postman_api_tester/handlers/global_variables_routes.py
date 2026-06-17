"""全局变量多环境 CRUD 路由处理函数。

提供：
- GET    /api/global-variables           — 按 scope 读取变量列表（值脱敏）
- GET    /api/global-variables/all       — 读取全部（shared + 所有 env）
- POST   /api/global-variables           — 设置变量（{scope, key, value, env_name?}）
- DELETE /api/global-variables           — 清空指定 scope 的变量
- DELETE /api/global-variables/<key>     — 删除指定 scope 的单个变量
- GET    /api/variable-functions          — 返回变量函数元数据列表
"""

from __future__ import annotations

import logging

from flask import request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.global_variables_service import (
    add_env,
    clear_scope,
    delete_variable,
    get_env_list,
    mask_value,
    read_all,
    read_scope,
    remove_env,
    set_variable,
)

logger = logging.getLogger(__name__)


def _get_file_path() -> str:
    from postman_api_tester.report_server_config import GLOBAL_VARIABLES_FILE
    return GLOBAL_VARIABLES_FILE


def _get_max_count() -> int:
    from postman_api_tester.report_server_config import GLOBAL_VARIABLES_MAX_COUNT
    return GLOBAL_VARIABLES_MAX_COUNT


def _check_enabled() -> str:
    file_path = _get_file_path()
    if not file_path:
        return ""
    return file_path


def api_global_variables_get() -> ResponseReturnValue:
    """GET /api/global-variables?scope=shared&env_name=X&masked=true — 读取变量列表（默认脱敏）。"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    scope = request.args.get("scope", "shared").strip()
    env_name = request.args.get("env_name", "").strip()
    do_mask = request.args.get("masked", "true").strip().lower() in {"1", "true", "yes"}

    data = read_scope(file_path, scope, env_name, _get_max_count())
    if do_mask:
        variables = {k: mask_value(str(v)) for k, v in data["variables"].items()}
        variables_list = [{"key": k, "value": mask_value(str(v))} for k, v in data["variables"].items()]
    else:
        variables = {k: str(v) for k, v in data["variables"].items()}
        variables_list = [{"key": k, "value": str(v)} for k, v in data["variables"].items()]
    return BaseHandler.json_response({
        "variables": variables,
        "variables_list": variables_list,
        "count": data["count"],
        "scope": scope,
        "env_name": env_name if scope == "env" else None,
        "masked": do_mask,
    })


def api_global_variables_all() -> ResponseReturnValue:
    """GET /api/global-variables/all?masked=true — 读取全部（shared + 所有 env），默认脱敏。"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    do_mask = request.args.get("masked", "true").strip().lower() in {"1", "true", "yes"}
    data = read_all(file_path, _get_max_count())

    def _process_vars(vars_dict: dict) -> dict:
        if do_mask:
            return {k: mask_value(str(v)) for k, v in vars_dict.items()}
        return {k: str(v) for k, v in vars_dict.items()}

    def _to_list(vars_dict: dict) -> list:
        if do_mask:
            return [{"key": k, "value": mask_value(str(v))} for k, v in vars_dict.items()]
        return [{"key": k, "value": str(v)} for k, v in vars_dict.items()]

    return BaseHandler.json_response({
        "shared": _process_vars(data.get("shared", {})),
        "shared_list": _to_list(data.get("shared", {})),
        "env_list": data.get("env_list", []),
        "environments": {k: _process_vars(v) for k, v in data.get("environments", {}).items() if isinstance(v, dict)},
        "environments_list": {k: _to_list(v) for k, v in data.get("environments", {}).items() if isinstance(v, dict)},
        "updated_at": data["updated_at"],
        "total_count": data["total_count"],
        "masked": do_mask,
    })


def api_global_variables_set() -> ResponseReturnValue:
    """POST /api/global-variables — 设置变量。body: {scope, key, value, env_name?}"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    body = request.get_json(silent=True) or {}
    scope = str(body.get("scope", "shared")).strip()
    key = str(body.get("key", "")).strip()
    value = str(body.get("value", "")).strip()
    env_name = str(body.get("env_name", "")).strip()

    if not key:
        return json_error("缺少 key 字段", 400, "GV_SET_001")
    if not value:
        return json_error("缺少 value 字段", 400, "GV_SET_002")
    if scope == "env" and not env_name:
        return json_error("环境变量需要指定 env_name", 400, "GV_SET_003")

    result = set_variable(file_path, scope, key, value, env_name, _get_max_count())
    logger.info("global variable set: scope=%s key=%s env=%s", scope, key, env_name)
    return BaseHandler.json_response({"count": result["count"], "truncated": result["truncated"]})


def api_global_variables_delete(key: str = "") -> ResponseReturnValue:
    """DELETE /api/global-variables/<key>?scope=shared&env_name=X — 删除单个变量。"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    if not key:
        return json_error("缺少 key 参数", 400, "GV_DEL_001")

    scope = request.args.get("scope", "shared").strip()
    env_name = request.args.get("env_name", "").strip()

    deleted = delete_variable(file_path, scope, key, env_name)
    if not deleted:
        return json_error(f"变量 '{key}' 不存在", 404, "GV_DEL_002")

    logger.info("global variable deleted: scope=%s key=%s env=%s", scope, key, env_name)
    return BaseHandler.json_response({"deleted": True, "key": key})


def api_global_variables_clear() -> ResponseReturnValue:
    """DELETE /api/global-variables?scope=shared&env_name=X — 清空指定作用域。"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    scope = request.args.get("scope", "shared").strip()
    env_name = request.args.get("env_name", "").strip()

    if scope == "env" and not env_name:
        return json_error("清空环境变量需要指定 env_name", 400, "GV_CLR_001")

    clear_scope(file_path, scope, env_name)
    logger.info("global variables cleared: scope=%s env=%s", scope, env_name)
    return BaseHandler.json_response({"cleared": True, "scope": scope})


def api_variable_functions() -> ResponseReturnValue:
    """GET /api/variable-functions — 返回变量函数元数据列表。"""
    from postman_api_tester.utils.variable_functions import get_function_metadata
    functions = get_function_metadata()
    return BaseHandler.json_response({"functions": functions, "count": len(functions)})


def api_env_list_get() -> ResponseReturnValue:
    """GET /api/environments/list — 返回用户可管理的环境列表。"""
    file_path = _check_enabled()
    if not file_path:
        return BaseHandler.json_response({"env_list": ["默认环境"]})
    env_list = get_env_list(file_path)
    return BaseHandler.json_response({"env_list": env_list})


def api_env_add() -> ResponseReturnValue:
    """POST /api/environments — 添加新环境。body: {name}"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return json_error("缺少 name 字段", 400, "ENV_ADD_001")

    result = add_env(file_path, name)
    if result.get("exists"):
        return json_error(f"环境 '{name}' 已存在", 409, "ENV_ADD_002")

    logger.info("environment added: %s", name)
    return BaseHandler.json_response({"env_list": result["env_list"]})


def api_env_remove(env_name: str) -> ResponseReturnValue:
    """DELETE /api/environments/<env_name> — 删除环境。"""
    file_path = _check_enabled()
    if not file_path:
        return json_error("全局变量持久化未启用（GLOBAL_VARIABLES_FILE 为空）", 403, "GV_DISABLED_001")

    result = remove_env(file_path, env_name)
    if "error" in result:
        return json_error(result["error"], 400, "ENV_DEL_001")

    logger.info("environment removed: %s", env_name)
    return BaseHandler.json_response({"env_list": result["env_list"]})
