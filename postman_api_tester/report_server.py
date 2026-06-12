#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告服务端模块。

开发导读:
- 提供报告列表、详情、重试执行、导出与局域网访问入口。
- 负责路由装配与服务生命周期管理，业务逻辑下沉到 handlers/services。
"""

import logging

from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.collection_editor_routes import (
    api_collection_dependency as _route_api_collection_dependency,
    api_collection_parse as _route_api_collection_parse,
    api_collection_save as _route_api_collection_save,
    api_collection_send as _route_api_collection_send,
)
from postman_api_tester.handlers.collection_routes import (
    api_collection_preview as _route_api_collection_preview,
    api_export_collection as _route_api_export_collection,
    api_export_collection_stream as _route_api_export_collection_stream,
)
from postman_api_tester.handlers.export_routes import (
    api_export_junit as _route_api_export_junit,
)
from postman_api_tester.handlers.job_routes import (
    api_run_ad_hoc_tests as _route_api_run_ad_hoc_tests,
    api_run_postman as _route_api_run_postman,
    api_run_postman_status as _route_api_run_postman_status,
)
from postman_api_tester.handlers.page_routes import (
    adhoc_run_page as _route_adhoc_run_page,
    collection_editor_page as _route_collection_editor_page,
    index as _route_index,
    report_view as _route_report_view,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_manual_case_add as _route_api_manual_case_add,
    api_manual_case_delete as _route_api_manual_case_delete,
    api_manual_case_update as _route_api_manual_case_update,
    api_manual_cases as _route_api_manual_cases,
    api_report_case_exclusion as _route_api_report_case_exclusion,
    api_report_detail as _route_api_report_detail,
    api_report_result_judgement as _route_api_report_result_judgement,
    api_reports as _route_api_reports,
)
from postman_api_tester.handlers.report_result_routes import (
    api_compare as _route_api_compare,
    api_report_analytics as _route_api_report_analytics,
    api_report_analytics_compare as _route_api_report_analytics_compare,
    api_report_result_detail as _route_api_report_result_detail,
    api_report_results as _route_api_report_results,
)
from postman_api_tester.handlers.retry_routes import (
    api_retry_all as _route_api_retry_all,
    api_retry_failures as _route_api_retry_failures,
)
from postman_api_tester.handlers.server_routes import (
    api_environments as _route_api_environments,
    api_report_delete as _route_api_report_delete,
    health as _route_health,
    latest_report as _route_latest_report,
    log_metrics as _route_log_metrics,
    serve_export as _route_serve_export,
    serve_report as _route_serve_report,
)
from postman_api_tester.handlers.test_proxy_routes import (
    api_proxy_request as _route_api_proxy_request,
    re_request_api as _route_re_request_api,
    test_token as _route_test_token,
)
from postman_api_tester.report_job_store import configure_run_jobs
from postman_api_tester.report_meta_repository import configure_reports_dir, configure_scan_excludes
from postman_api_tester.report_repository import configure_report_repository
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_server_config import _cfg_int
from postman_api_tester.utils.logging_utils import configure_logging_from_config

configure_logging_from_config(service_name="report_server")
logger = logging.getLogger(__name__)

REPORTS_DIR = ReportServerApp._resolve_reports_dir()

app = ReportServerApp.create_app()
configure_reports_dir(REPORTS_DIR)
from postman_api_tester.report_server_config import REPORT_SCAN_EXCLUDE_DIRS
configure_scan_excludes(REPORT_SCAN_EXCLUDE_DIRS)
configure_report_repository(REPORTS_DIR, cache_ttl=30.0)
configure_run_jobs(_cfg_int("RUN_JOBS_MAX", 200))


@app.route("/health")
def health() -> ResponseReturnValue:
    """健康检查端点，用于监控系统存活状态。"""
    return _route_health()


@app.route("/api/log-metrics")
def log_metrics() -> ResponseReturnValue:
    """日志聚合指标（内存计数快照）。"""
    return _route_log_metrics()


@app.route("/")
def index() -> ResponseReturnValue:
    return _route_index()


@app.route("/adhoc-run")
def adhoc_run_page() -> ResponseReturnValue:
    return _route_adhoc_run_page()


@app.route("/collection-editor")
def collection_editor_page() -> ResponseReturnValue:
    return _route_collection_editor_page()


@app.route("/report-view")
def report_view() -> ResponseReturnValue:
    return _route_report_view()


@app.route("/reports/<path:filename>")
def serve_report(filename: str) -> ResponseReturnValue:
    return _route_serve_report(filename)


@app.route("/exports/<path:filename>")
def serve_export(filename: str) -> ResponseReturnValue:
    return _route_serve_export(filename)


@app.route("/api/reports")
def api_reports() -> ResponseReturnValue:
    return _route_api_reports()


@app.route("/api/collection-preview", methods=["POST"])
def api_collection_preview() -> ResponseReturnValue:
    return _route_api_collection_preview()


@app.route("/api/export-collection", methods=["POST"])
def api_export_collection() -> ResponseReturnValue:
    return _route_api_export_collection()


@app.route("/api/export-collection-stream", methods=["POST"])
def api_export_collection_stream() -> ResponseReturnValue:
    return _route_api_export_collection_stream()


@app.route("/api/collection-editor/parse", methods=["POST"])
def api_collection_parse() -> ResponseReturnValue:
    return _route_api_collection_parse()


@app.route("/api/collection-editor/save", methods=["PUT"])
def api_collection_save() -> ResponseReturnValue:
    return _route_api_collection_save()


@app.route("/api/collection-editor/dependency", methods=["POST"])
def api_collection_dependency() -> ResponseReturnValue:
    return _route_api_collection_dependency()


@app.route("/api/collection-editor/send", methods=["POST"])
def api_collection_send() -> ResponseReturnValue:
    return _route_api_collection_send()


@app.route("/api/report-meta/<path:report_name>")
def api_report_detail(report_name: str) -> ResponseReturnValue:
    return _route_api_report_detail(report_name)


@app.route("/api/manual-cases/<path:report_name>")
def api_manual_cases(report_name: str) -> ResponseReturnValue:
    return _route_api_manual_cases(report_name)


@app.route("/api/manual-cases/add", methods=["POST"])
def api_manual_case_add() -> ResponseReturnValue:
    return _route_api_manual_case_add()


@app.route("/api/manual-cases/update", methods=["PUT"])
def api_manual_case_update() -> ResponseReturnValue:
    return _route_api_manual_case_update()


@app.route("/api/manual-cases/delete", methods=["DELETE"])
def api_manual_case_delete() -> ResponseReturnValue:
    return _route_api_manual_case_delete()


@app.route("/api/report-case-exclusion", methods=["POST"])
def api_report_case_exclusion() -> ResponseReturnValue:
    return _route_api_report_case_exclusion()


@app.route("/api/report-result-judgement", methods=["POST"])
def api_report_result_judgement() -> ResponseReturnValue:
    return _route_api_report_result_judgement()


# ---------------------------------------------------------------
# 升级二：一键重试失败用例
# ---------------------------------------------------------------
@app.route("/api/retry-failures", methods=["POST"])
def api_retry_failures() -> ResponseReturnValue:
    return _route_api_retry_failures()


@app.route("/api/retry-all", methods=["POST"])
def api_retry_all() -> ResponseReturnValue:
    return _route_api_retry_all()


# ---------------------------------------------------------------
# 升级七：JUnit XML 报告导出
# ---------------------------------------------------------------
@app.route("/api/export-junit/<path:report_name>")
def api_export_junit(report_name: str) -> ResponseReturnValue:
    return _route_api_export_junit(report_name)


# ---------------------------------------------------------------
# 升级四：多环境配置查询
# ---------------------------------------------------------------
@app.route("/api/environments")
def api_environments() -> ResponseReturnValue:
    """返回可用环境列表（不含 token 值）。"""
    return _route_api_environments()


@app.route("/api/report-delete/<path:report_name>", methods=["DELETE"])
def api_report_delete(report_name: str) -> ResponseReturnValue:
    return _route_api_report_delete(report_name)


@app.route("/api/report-results/<path:report_name>")
def api_report_results(report_name: str) -> ResponseReturnValue:
    return _route_api_report_results(report_name)


@app.route("/api/report-analytics/<path:report_name>")
def api_report_analytics(report_name: str) -> ResponseReturnValue:
    return _route_api_report_analytics(report_name)


@app.route("/api/report-analytics-compare")
def api_report_analytics_compare() -> ResponseReturnValue:
    return _route_api_report_analytics_compare()


@app.route("/api/report-result-detail/<path:report_name>/<int:result_index>")
def api_report_result_detail(report_name: str, result_index: int) -> ResponseReturnValue:
    return _route_api_report_result_detail(report_name, result_index)


@app.route("/api/compare")
def api_compare() -> ResponseReturnValue:
    return _route_api_compare()


@app.route("/test-token", methods=["POST"])
def test_token() -> ResponseReturnValue:
    return _route_test_token()


@app.route("/re-request-api", methods=["POST"])
def re_request_api() -> ResponseReturnValue:
    return _route_re_request_api()


@app.route("/api/proxy-request", methods=["POST"])
def api_proxy_request() -> ResponseReturnValue:
    return _route_api_proxy_request()


@app.route("/api/run-postman", methods=["POST"])
def api_run_postman() -> ResponseReturnValue:
    return _route_api_run_postman()


@app.route("/api/run-ad-hoc-tests", methods=["POST"])
def api_run_ad_hoc_tests() -> ResponseReturnValue:
    return _route_api_run_ad_hoc_tests()


@app.route("/api/run-postman-status/<path:job_id>")
def api_run_postman_status(job_id: str) -> ResponseReturnValue:
    return _route_api_run_postman_status(job_id)


@app.route("/latest")
def latest_report() -> ResponseReturnValue:
    return _route_latest_report()


@app.route("/favicon.ico")
def favicon() -> ResponseReturnValue:
    from flask import make_response
    return make_response("", 204)


# 入口已迁移到 postman_api_tester.report_server_app.ReportServerApp.run_app()
# 命令行启动: python -c "from postman_api_tester.report_server_app import ReportServerApp; ReportServerApp.run_app(ReportServerApp.create_app())"


