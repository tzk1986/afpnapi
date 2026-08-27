"""UI 认证档案 API 路由处理函数。

提供认证档案的 CRUD 和 Playwright storage_state 导出。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import make_response, render_template, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.ui_auth_profile_store import _auth_profile_store

logger = logging.getLogger(__name__)


def ui_auth_profiles_page() -> ResponseReturnValue:
    """认证档案管理页面。"""
    resp = make_response(render_template("ui_testing_auth_profiles.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def api_ui_auth_profiles_list() -> ResponseReturnValue:
    """列出所有认证档案（摘要）。"""
    profiles = _auth_profile_store.list_profiles()
    return BaseHandler.json_response({"profiles": profiles})


def api_ui_auth_profiles_create() -> ResponseReturnValue:
    """创建认证档案。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_AUTH_001")

    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        return json_error("cookies 必须为数组", 400, "UIT_AUTH_002")

    profile_id = _auth_profile_store.save_profile(payload)
    logger.info(
        "ui_auth_profile_created",
        extra={
            "event": "ui.auth.profile.created",
            "profile_id": profile_id,
            "profile_name": payload.get("name", ""),
            "cookie_count": len(cookies),
        },
    )
    return BaseHandler.json_response({"id": profile_id}, 201, "Created")


def api_ui_auth_profile_get(profile_id: str) -> ResponseReturnValue:
    """获取认证档案详情。"""
    profile = _auth_profile_store.get_profile(profile_id)
    if not profile:
        return json_error(f"认证档案不存在: {profile_id}", 404, "UIT_AUTH_003")
    return BaseHandler.json_response(profile)


def api_ui_auth_profile_update(profile_id: str) -> ResponseReturnValue:
    """更新认证档案。"""
    existing = _auth_profile_store.get_profile(profile_id)
    if not existing:
        return json_error(f"认证档案不存在: {profile_id}", 404, "UIT_AUTH_003")

    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_AUTH_001")

    # 合并更新
    merged = {**existing, **payload, "id": profile_id}
    updated_id = _auth_profile_store.save_profile(merged)
    logger.info(
        "ui_auth_profile_updated",
        extra={
            "event": "ui.auth.profile.updated",
            "profile_id": updated_id,
        },
    )
    return BaseHandler.json_response({"ok": True})


def api_ui_auth_profile_delete(profile_id: str) -> ResponseReturnValue:
    """删除认证档案。"""
    if not _auth_profile_store.delete_profile(profile_id):
        return json_error(f"认证档案不存在: {profile_id}", 404, "UIT_AUTH_003")
    logger.info(
        "ui_auth_profile_deleted",
        extra={
            "event": "ui.auth.profile.deleted",
            "profile_id": profile_id,
        },
    )
    return BaseHandler.json_response({"ok": True})


def api_ui_auth_profile_export(profile_id: str) -> ResponseReturnValue:
    """导出为 Playwright storage_state JSON。"""
    state = _auth_profile_store.export_storage_state(profile_id)
    if state is None:
        profile = _auth_profile_store.get_profile(profile_id)
        if not profile:
            return json_error(f"认证档案不存在: {profile_id}", 404, "UIT_AUTH_003")
        if _auth_profile_store.is_expired(profile):
            return json_error("认证档案已过期", 410, "UIT_AUTH_004")
    return BaseHandler.json_response(state)


def api_ui_auth_profiles_cleanup() -> ResponseReturnValue:
    """清理已过期的认证档案。"""
    removed = _auth_profile_store.cleanup_expired()
    return BaseHandler.json_response({"removed": removed})
