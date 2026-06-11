"""页面渲染路由处理函数。"""

import json
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import make_response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from postman_api_tester.report_server_config import (
    ADHOC_DEFAULT_COLLECTION_NAME,
    ADHOC_MAX_ITEMS,
    COLLECTION_PREVIEW_MAX_ITEMS,
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
)
from postman_api_tester.report_repository import (
    find_report as _repo_find_report,
    list_reports as _repo_list_reports,
)
from postman_api_tester.utils.server_utils import get_local_ip

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def index() -> ResponseReturnValue:
    """首页：报告列表与任务提交入口。"""
    reports = _repo_list_reports()
    from postman_api_tester.report_server_config import REPORT_SERVER_PORT as port
    return render_template(
        "index.html",
        host_name=socket.gethostname(),
        self_url=f"http://127.0.0.1:{port}",
        lan_url=f"http://{get_local_ip()}:{port}",
        reports_json=json.dumps(reports, ensure_ascii=False),
        run_results_per_page_default=RUN_RESULTS_PER_PAGE_DEFAULT,
        run_results_per_page_min=RUN_RESULTS_PER_PAGE_MIN,
        run_results_per_page_max=RUN_RESULTS_PER_PAGE_MAX,
        run_status_poll_interval_ms=RUN_STATUS_POLL_INTERVAL_MS,
        enable_selective_run=ENABLE_SELECTIVE_RUN,
        collection_preview_max_items=COLLECTION_PREVIEW_MAX_ITEMS,
        enable_adhoc_run=ENABLE_ADHOC_RUN,
        adhoc_max_items=ADHOC_MAX_ITEMS,
        adhoc_default_collection_name=ADHOC_DEFAULT_COLLECTION_NAME,
        enable_response_time=ENABLE_RESPONSE_TIME,
        enable_retry_failures=ENABLE_RETRY_FAILURES,
        enable_junit_export=ENABLE_JUNIT_EXPORT,
        enable_report_list_filter=ENABLE_REPORT_LIST_FILTER,
        environments_json=json.dumps(list(ENVIRONMENTS.keys()), ensure_ascii=False),
        default_env_name=DEFAULT_ENV_NAME,
    )


def adhoc_run_page() -> ResponseReturnValue:
    """Ad-hoc 测试提交页面。"""
    if not ENABLE_ADHOC_RUN:
        return redirect(url_for("index"))
    return render_template(
        "adhoc_run.html",
        run_results_per_page_default=RUN_RESULTS_PER_PAGE_DEFAULT,
        run_results_per_page_min=RUN_RESULTS_PER_PAGE_MIN,
        run_results_per_page_max=RUN_RESULTS_PER_PAGE_MAX,
        run_status_poll_interval_ms=RUN_STATUS_POLL_INTERVAL_MS,
        adhoc_max_items=ADHOC_MAX_ITEMS,
        adhoc_default_collection_name=ADHOC_DEFAULT_COLLECTION_NAME,
        enable_assertions=ENABLE_ASSERTIONS,
        environments_json=json.dumps(list(ENVIRONMENTS.keys()), ensure_ascii=False),
        default_env_name=DEFAULT_ENV_NAME,
    )


def report_view() -> ResponseReturnValue:
    """报告详情页。"""
    report_name = request.args.get("name", "")
    if not report_name:
        reports = _repo_list_reports()
        if reports:
            return redirect(url_for("report_view", name=reports[0]["report_name"]))
        return redirect(url_for("index"))

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return render_template("report_not_found.html", name=report_name), 404

    template_updated_at = "-"
    try:
        template_path = (PROJECT_ROOT / "templates" / "report_view.html").resolve()
        template_updated_at = datetime.fromtimestamp(template_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        template_updated_at = "-"

    html = render_template(
        "report_view.html",
        report_name=report.get("report_name", ""),
        report_name_json=json.dumps(report.get("report_name", ""), ensure_ascii=False),
        collection_name=report.get("collection_name", ""),
        source_file=report.get("source_file", ""),
        generated_at=report.get("generated_at", ""),
        summary=report.get("summary", {}),
        report_view_page_size_default=REPORT_VIEW_PAGE_SIZE_DEFAULT,
        report_export_default_scope=REPORT_EXPORT_DEFAULT_SCOPE,
        report_export_allow_report_only=REPORT_EXPORT_ALLOW_REPORT_ONLY,
        report_export_include_auth_default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT,
        report_export_channel_mode=REPORT_EXPORT_CHANNEL_MODE,
        report_export_stream_threshold=REPORT_EXPORT_STREAM_THRESHOLD,
        enable_manual_cases=ENABLE_MANUAL_CASES,
        manual_case_folder_name=MANUAL_CASE_FOLDER_NAME,
        template_updated_at=template_updated_at,
        enable_response_time=ENABLE_RESPONSE_TIME,
        enable_retry_failures=ENABLE_RETRY_FAILURES,
        enable_junit_export=ENABLE_JUNIT_EXPORT,
        enable_report_analytics=ENABLE_REPORT_ANALYTICS,
        enable_report_analytics_charts=ENABLE_REPORT_ANALYTICS_CHARTS,
        report_analytics_top_n_default=REPORT_ANALYTICS_TOP_N_DEFAULT,
        report_analytics_trend_limit_default=REPORT_ANALYTICS_TREND_LIMIT_DEFAULT,
        report_analytics_enable_samples=REPORT_ANALYTICS_ENABLE_SAMPLES,
    )
    response = make_response(html)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
