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

from flask import jsonify, redirect, render_template, request, send_from_directory, send_file, url_for
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
    from postman_api_tester.report_server_config import REPORT_OUTPUT_DIR as _cfg_dir
    if _cfg_dir:
        return Path(_cfg_dir).expanduser().resolve()
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
    from postman_api_tester.services.report_delete_service import delete_report_artifacts as _svc_delete
    logger.info(
        "handler delete report",
        extra={"event": "handler.server.report_delete.forward", "report_name": report_name},
    )
    try:
        deleted_files = _svc_delete(
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
    """服务报告文件。支持子目录中的报告。"""
    filepath = REPORTS_DIR / filename
    if filepath.exists():
        return send_file(filepath)
    # 如果直接路径不存在，尝试查找报告并获取实际路径
    try:
        for report in _repo_list_reports():
            if report.get("report_name") == filename:
                meta_file = str(report.get("meta_file") or "").strip()
                if meta_file:
                    meta_path = REPORTS_DIR / meta_file
                    report_path = meta_path.with_name(meta_path.name.replace("_meta.json", ".html"))
                    if report_path.exists():
                        return send_file(report_path)
                # 无 meta 文件的 legacy 报告：尝试 source_file 或 details_file 推导
                source_file = str(report.get("source_file") or "").strip()
                if source_file:
                    source_path = Path(source_file)
                    if source_path.exists():
                        return send_file(source_path)
                details_file = str(report.get("details_file") or "").strip()
                if details_file:
                    details_path = REPORTS_DIR / details_file
                    report_path = details_path.with_name(details_path.name.replace("_details.json", ".html"))
                    if report_path.exists():
                        return send_file(report_path)
    except OSError:
        pass
    from postman_api_tester.exceptions import ValidationError
    return BaseHandler.error_response(ValidationError(f"报告文件不存在: {filename}"), 404)


def serve_export(filename: str) -> ResponseReturnValue:
    """服务导出文件。"""
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)
