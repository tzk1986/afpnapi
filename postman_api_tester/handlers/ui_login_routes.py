"""UI 登录配置 API 路由处理函数。

提供登录配置的 CRUD 和执行测试。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import make_response, render_template, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.ui_login_config_store import _login_config_store

logger = logging.getLogger(__name__)


def api_ui_login_configs_list() -> ResponseReturnValue:
    """列出所有登录配置（摘要）。"""
    configs = _login_config_store.list_configs()
    return BaseHandler.json_response({"configs": configs})


def api_ui_login_configs_create() -> ResponseReturnValue:
    """创建登录配置。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_LCFG_001")

    name = payload.get("name")
    if not name:
        return json_error("配置名称不能为空", 400, "UIT_LCFG_002")

    login_steps = payload.get("login_steps")
    if not isinstance(login_steps, list):
        return json_error("login_steps 必须为数组", 400, "UIT_LCFG_003")

    base_url = payload.get("base_url", "")
    if not base_url:
        return json_error("base_url 不能为空", 400, "UIT_LCFG_004")

    config_id = _login_config_store.save_config(payload)
    logger.info(
        "ui_login_config_created",
        extra={
            "event": "ui.login_config.created",
            "config_id": config_id,
            "config_name": name,
            "step_count": len(login_steps),
        },
    )
    return BaseHandler.json_response({"id": config_id}, 201, "Created")


def api_ui_login_config_get(config_id: str) -> ResponseReturnValue:
    """获取登录配置详情。"""
    config = _login_config_store.get_config(config_id)
    if not config:
        return json_error(f"登录配置不存在: {config_id}", 404, "UIT_LCFG_005")
    return BaseHandler.json_response(config)


def api_ui_login_config_update(config_id: str) -> ResponseReturnValue:
    """更新登录配置。"""
    existing = _login_config_store.get_config(config_id)
    if not existing:
        return json_error(f"登录配置不存在: {config_id}", 404, "UIT_LCFG_005")

    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_LCFG_001")

    # 合并更新
    merged: Dict[str, Any] = {**existing, **payload, "id": config_id}
    updated_id = _login_config_store.save_config(merged)
    logger.info(
        "ui_login_config_updated",
        extra={
            "event": "ui.login_config.updated",
            "config_id": updated_id,
        },
    )
    return BaseHandler.json_response({"ok": True})


def api_ui_login_config_delete(config_id: str) -> ResponseReturnValue:
    """删除登录配置。"""
    if not _login_config_store.delete_config(config_id):
        return json_error(f"登录配置不存在: {config_id}", 404, "UIT_LCFG_005")
    logger.info(
        "ui_login_config_deleted",
        extra={
            "event": "ui.login_config.deleted",
            "config_id": config_id,
        },
    )
    return BaseHandler.json_response({"ok": True})


def api_ui_login_config_test(config_id: str) -> ResponseReturnValue:
    """测试执行登录配置，验证步骤是否正确并返回 Cookie。"""
    config = _login_config_store.get_config(config_id)
    if not config:
        return json_error(f"登录配置不存在: {config_id}", 404, "UIT_LCFG_005")

    login_steps = config.get("login_steps", [])
    if not login_steps:
        return json_error("登录步骤为空", 400, "UIT_LCFG_006")

    base_url = config.get("base_url", "")
    if not base_url:
        return json_error("base_url 未配置", 400, "UIT_LCFG_007")

    try:
        from postman_api_tester.services.ui_headless_engine import (
            UiHeadlessEngine,
        )

        engine = UiHeadlessEngine(browser_type="chromium")
        result = engine.execute_login_config(
            login_steps=login_steps,
            base_url=base_url,
            timeout_ms=config.get("success_condition", {}).get("timeout_ms", 30000),
        )
    except Exception as e:
        logger.error("login_config_test_error: %s", e, exc_info=True)
        return BaseHandler.json_response(
            {
                "status": "error",
                "error": str(e),
                "cookies": [],
                "cookie_count": 0,
            }
        )

    cookie_count = len(result.get("cookies", []))
    if result.get("status") == "passed":
        logger.info(
            "ui_login_config_test_passed",
            extra={
                "event": "ui.login_config.test_passed",
                "config_id": config_id,
                "cookie_count": cookie_count,
                "duration_ms": result.get("duration_ms", 0),
            },
        )
    else:
        logger.warning(
            "ui_login_config_test_failed",
            extra={
                "event": "ui.login_config.test_failed",
                "config_id": config_id,
                "error": result.get("error", ""),
            },
        )

    return BaseHandler.json_response(result)


def ui_login_configs_page() -> ResponseReturnValue:
    """登录配置列表页面。"""
    resp = make_response(render_template("ui_testing_login_configs.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def ui_login_config_editor_page(config_id: str = "") -> ResponseReturnValue:
    """登录配置编辑器页面。"""
    resp = make_response(
        render_template("ui_testing_login_config_editor.html", config_id=config_id)
    )
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp
