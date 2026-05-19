"""服务端元数据与管理路由处理函数。

职责：
- 健康检查、日志指标、环境列表
- 静态文件服务、报告删除、最新报告跳转
"""

import json
import logging
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import jsonify, redirect, render_template, request, send_from_directory, url_for
from flask.typing import ResponseReturnValue

from postman_api_tester.report_server_config import (
    DEFAULT_ENV_NAME,
    ENABLE_ADHOC_RUN,
    ENABLE_ASSERTIONS,
    ENABLE_JUNIT_EXPORT,
    ENABLE_MANUAL_CASES,
    ENABLE_REPORT_ANALYTICS,
    ENABLE_REPORT_ANALYTICS_CHARTS,
    ENABLE_REPORT_LIST_FILTER,
    ENABLE_RESPONSE_TIME,
    ENABLE_RETRY_FAILURES,
    ENABLE_SELECTIVE_RUN,
    ENVIRONMENTS,
    MANUAL_CASE_FOLDER_NAME,
    REPORT_ANALYTICS_ENABLE_SAMPLES,
    REPORT_ANALYTICS_TOP_N_DEFAULT,
    REPORT_ANALYTICS_TREND_LIMIT_DEFAULT,
    REPORT_EXPORT_ALLOW_REPORT_ONLY,
    REPORT_EXPORT_CHANNEL_MODE,
    REPORT_EXPORT_DEFAULT_SCOPE,
    REPORT_EXPORT_INCLUDE_AUTH_DEFAULT,
    REPORT_EXPORT_STREAM_THRESHOLD,
    REPORT_VIEW_PAGE_SIZE_DEFAULT,
    RUN_RESULTS_PER_PAGE_DEFAULT,
    RUN_RESULTS_PER_PAGE_MAX,
    RUN_RESULTS_PER_PAGE_MIN,
    RUN_STATUS_POLL_INTERVAL_MS,
    ADHOC_DEFAULT_COLLECTION_NAME,
    ADHOC_MAX_ITEMS,
    COLLECTION_PREVIEW_MAX_ITEMS,
)
from postman_api_tester.handlers.base_handler import BaseHandler
from postman_api_tester.report_repository import (
    collect_report_artifacts,
    find_report as _repo_find_report,
    invalidate_reports_cache as _repo_invalidate_reports_cache,
    list_reports as _repo_list_reports,
)
from postman_api_tester.services.report_results_service import (
    build_environments_payload,
    build_health_payload,
    build_report_delete_payload,
)
from postman_api_tester.utils.logging_utils import (
    get_log_alert_snapshot,
    get_log_metrics_snapshot,
)
from postman_api_tester.utils.server_utils import get_local_ip

logger = logging.getLogger(__name__)


MODULE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = MODULE_DIR.parent


def _resolve_reports_dir() -> Path:
    """解析报告目录。"""
    env_dir = (
        os.environ.get("POSTMAN_REPORTS_DIR")
        or os.environ.get("REPORTS_DIR")
        or ""
    ).strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    try:
        from postman_api_tester import config as cfg
        cfg_dir = getattr(cfg, "REPORT_OUTPUT_DIR", "").strip()
        if cfg_dir:
            return Path(cfg_dir).expanduser().resolve()
    except Exception:
        pass
    return (PROJECT_ROOT / "reports").resolve()


REPORTS_DIR = _resolve_reports_dir()
EXPORTS_DIR = (REPORTS_DIR.parent / "uploaded_collections" / "exports").resolve()


def health() -> ResponseReturnValue:
    """健康检查端点。"""
    return jsonify(
        build_health_payload(
            datetime.now().isoformat(),
            log_alert=get_log_alert_snapshot(),
        )
    )


def log_metrics() -> ResponseReturnValue:
    """日志聚合指标。"""
    return jsonify(get_log_metrics_snapshot())


def api_environments() -> ResponseReturnValue:
    """返回可用环境列表（不含 token 值）。"""
    env_list: List[Dict[str, Any]] = []
    for env_name, env_cfg in ENVIRONMENTS.items():
        if not isinstance(env_cfg, dict):
            continue
        env_list.append({
            "name": str(env_name),
            "base_url": str(env_cfg.get("base_url", "")),
            "has_token": bool(env_cfg.get("token", "").strip()),
        })
    return jsonify(build_environments_payload(env_list=env_list, default_env_name=DEFAULT_ENV_NAME))


def api_report_delete(report_name: str) -> ResponseReturnValue:
    """删除报告产物。"""
    from postman_api_tester.handlers.admin_handler import delete_report_artifacts as _admin_delete_report_artifacts
    try:
        deleted_files = _admin_delete_report_artifacts(
            report_name,
            find_report=_repo_find_report,
            collect_report_artifacts=collect_report_artifacts,
            invalidate_reports_cache=_repo_invalidate_reports_cache,
        )
    except FileNotFoundError:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"报告不存在: {report_name}"), 404)
    logger.info("删除报告产物成功: report=%s files=%s", report_name, deleted_files)
    return jsonify(build_report_delete_payload(report_name=report_name, deleted_files=deleted_files))


def latest_report() -> ResponseReturnValue:
    """跳转到最新报告。"""
    reports = _repo_list_reports()
    if not reports:
        return redirect(url_for("index"))
    return redirect(url_for("report_view", name=reports[0]["report_name"]))


def serve_report(filename: str) -> ResponseReturnValue:
    """服务报告文件。"""
    return send_from_directory(REPORTS_DIR, filename)


def serve_export(filename: str) -> ResponseReturnValue:
    """服务导出文件。"""
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)
