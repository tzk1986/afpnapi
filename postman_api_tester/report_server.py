#!/usr/bin/env python
"""报告服务端模块。

开发导读:
- 提供报告列表、详情、重试执行、导出与局域网访问入口。
- 负责路由装配与服务生命周期管理，业务逻辑下沉到 handlers/services。
"""

import logging

from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.collection_editor_routes import (
    api_collection_dependency as _route_api_collection_dependency,
)
from postman_api_tester.handlers.collection_editor_routes import (
    api_collection_parse as _route_api_collection_parse,
)
from postman_api_tester.handlers.collection_editor_routes import (
    api_collection_save as _route_api_collection_save,
)
from postman_api_tester.handlers.collection_editor_routes import (
    api_collection_send as _route_api_collection_send,
)
from postman_api_tester.handlers.collection_routes import (
    api_collection_preview as _route_api_collection_preview,
)
from postman_api_tester.handlers.collection_routes import (
    api_export_collection as _route_api_export_collection,
)
from postman_api_tester.handlers.collection_routes import (
    api_export_collection_stream as _route_api_export_collection_stream,
)
from postman_api_tester.handlers.export_routes import (
    api_export_junit as _route_api_export_junit,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_env_add as _route_api_env_add,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_env_list_get as _route_api_env_list_get,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_env_remove as _route_api_env_remove,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_global_variables_all as _route_api_global_variables_all,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_global_variables_clear as _route_api_global_variables_clear,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_global_variables_delete as _route_api_global_variables_delete,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_global_variables_get as _route_api_global_variables_get,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_global_variables_set as _route_api_global_variables_set,
)
from postman_api_tester.handlers.global_variables_routes import (
    api_variable_functions as _route_api_variable_functions,
)
from postman_api_tester.handlers.job_routes import (
    api_run_ad_hoc_tests as _route_api_run_ad_hoc_tests,
)
from postman_api_tester.handlers.job_routes import (
    api_run_postman as _route_api_run_postman,
)
from postman_api_tester.handlers.job_routes import (
    api_run_postman_status as _route_api_run_postman_status,
)
from postman_api_tester.handlers.page_routes import (
    adhoc_run_page as _route_adhoc_run_page,
)
from postman_api_tester.handlers.page_routes import (
    collection_editor_page as _route_collection_editor_page,
)
from postman_api_tester.handlers.page_routes import (
    index as _route_index,
)
from postman_api_tester.handlers.page_routes import (
    report_view as _route_report_view,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_manual_case_add as _route_api_manual_case_add,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_manual_case_delete as _route_api_manual_case_delete,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_manual_case_update as _route_api_manual_case_update,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_manual_cases as _route_api_manual_cases,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_report_case_exclusion as _route_api_report_case_exclusion,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_report_detail as _route_api_report_detail,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_report_result_judgement as _route_api_report_result_judgement,
)
from postman_api_tester.handlers.report_meta_routes import (
    api_reports as _route_api_reports,
)
from postman_api_tester.handlers.report_result_routes import (
    api_compare as _route_api_compare,
)
from postman_api_tester.handlers.report_result_routes import (
    api_report_analytics as _route_api_report_analytics,
)
from postman_api_tester.handlers.report_result_routes import (
    api_report_analytics_compare as _route_api_report_analytics_compare,
)
from postman_api_tester.handlers.report_result_routes import (
    api_report_result_detail as _route_api_report_result_detail,
)
from postman_api_tester.handlers.report_result_routes import (
    api_report_results as _route_api_report_results,
)
from postman_api_tester.handlers.retry_routes import (
    api_retry_all as _route_api_retry_all,
)
from postman_api_tester.handlers.retry_routes import (
    api_retry_failures as _route_api_retry_failures,
)
from postman_api_tester.handlers.server_routes import (
    api_environments as _route_api_environments,
)
from postman_api_tester.handlers.server_routes import (
    api_report_delete as _route_api_report_delete,
)
from postman_api_tester.handlers.server_routes import (
    health as _route_health,
)
from postman_api_tester.handlers.server_routes import (
    latest_report as _route_latest_report,
)
from postman_api_tester.handlers.server_routes import (
    log_metrics as _route_log_metrics,
)
from postman_api_tester.handlers.server_routes import (
    serve_export as _route_serve_export,
)
from postman_api_tester.handlers.server_routes import (
    serve_report as _route_serve_report,
)
from postman_api_tester.handlers.test_proxy_routes import (
    api_proxy_request as _route_api_proxy_request,
)
from postman_api_tester.handlers.test_proxy_routes import (
    re_request_api as _route_re_request_api,
)
from postman_api_tester.handlers.test_proxy_routes import (
    test_token as _route_test_token,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_cleanup as _route_api_ui_testing_cleanup,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execute as _route_api_ui_testing_execute,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_cancel as _route_api_ui_testing_execution_cancel,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_finalize as _route_api_ui_testing_execution_finalize,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_init as _route_api_ui_testing_execution_init,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_report as _route_api_ui_testing_execution_report,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_screenshot as _route_api_ui_testing_execution_screenshot,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_screenshot_post as _route_api_ui_testing_execution_screenshot_post,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_status as _route_api_ui_testing_execution_status,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execution_step_report as _route_api_ui_testing_execution_step_report,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_executions_list as _route_api_ui_testing_executions_list,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_playwright_status as _route_api_ui_testing_playwright_status,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_replay_engine_js as _route_api_ui_testing_replay_engine_js,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_replay_log as _route_api_ui_testing_replay_log,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_report_delete as _route_api_ui_testing_report_delete,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_reports_list as _route_api_ui_testing_reports_list,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_settings_get as _route_api_ui_testing_settings_get,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_settings_reset as _route_api_ui_testing_settings_reset,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_settings_update as _route_api_ui_testing_settings_update,
)
from postman_api_tester.handlers.ui_execution_routes import (
    ui_testing_replay_page as _route_ui_testing_replay_page,
)
from postman_api_tester.handlers.ui_execution_routes import (
    ui_testing_report_page as _route_ui_testing_report_page,
)
from postman_api_tester.handlers.ui_execution_routes import (
    ui_testing_reports_page as _route_ui_testing_reports_page,
)
from postman_api_tester.handlers.ui_execution_routes import (
    ui_testing_settings_page as _route_ui_testing_settings_page,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_clear_recording as _route_api_ui_recorder_clear_recording,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_event as _route_api_ui_recorder_event,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_session_delete as _route_api_ui_recorder_session_delete,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_session_detail as _route_api_ui_recorder_session_detail,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_session_export as _route_api_ui_recorder_session_export,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_sessions as _route_api_ui_recorder_sessions,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    ui_recorder_demo_page as _route_ui_recorder_demo_page,
)
from postman_api_tester.handlers.ui_recorder_routes import (
    ui_recorder_page as _route_ui_recorder_page,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_case_delete as _route_api_ui_testing_case_delete,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_case_get as _route_api_ui_testing_case_get,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_case_update as _route_api_ui_testing_case_update,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_cases_create as _route_api_ui_testing_cases_create,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_cases_list as _route_api_ui_testing_cases_list,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_recording_get as _route_api_ui_testing_recording_get,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_recording_save_as_case as _route_api_ui_testing_recording_save_as_case,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_recording_start as _route_api_ui_testing_recording_start,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_recording_step as _route_api_ui_testing_recording_step,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_recording_stop as _route_api_ui_testing_recording_stop,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_recording_local_storage as _route_api_ui_testing_recording_local_storage,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_proxy_sessions_debug as _route_ui_proxy_sessions_debug,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_editor_page as _route_ui_testing_editor_page,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_index_page as _route_ui_testing_index_page,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_proxy as _route_ui_testing_proxy,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_proxy_resource as _route_ui_testing_proxy_resource,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_recorder_page as _route_ui_testing_recorder_page,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_spa_resource_fallback as _route_ui_testing_spa_resource_fallback,
)
from postman_api_tester.handlers.ui_testing_routes import (
    ui_testing_static_fallback as _route_ui_testing_static_fallback,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profiles_list as _route_api_ui_auth_profiles_list,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profiles_create as _route_api_ui_auth_profiles_create,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profile_get as _route_api_ui_auth_profile_get,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profile_update as _route_api_ui_auth_profile_update,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profile_delete as _route_api_ui_auth_profile_delete,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profile_export as _route_api_ui_auth_profile_export,
)
from postman_api_tester.handlers.ui_auth_routes import (
    api_ui_auth_profiles_cleanup as _route_api_ui_auth_profiles_cleanup,
)
from postman_api_tester.handlers.ui_auth_routes import (
    ui_auth_profiles_page as _route_ui_auth_profiles_page,
)
from postman_api_tester.report_job_store import configure_run_jobs
from postman_api_tester.report_meta_repository import (
    configure_reports_dir,
    configure_scan_excludes,
)
from postman_api_tester.report_repository import configure_report_repository
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_server_config import _cfg_int
from postman_api_tester.utils.logging_utils import configure_logging_from_config

configure_logging_from_config(service_name="report_server")
logger = logging.getLogger(__name__)

REPORTS_DIR = ReportServerApp._resolve_reports_dir()

app = ReportServerApp.create_app()
configure_reports_dir(REPORTS_DIR)
from postman_api_tester.report_server_config import (  # noqa: E402
    REPORT_SCAN_EXCLUDE_DIRS,
)

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
def api_report_result_detail(
    report_name: str, result_index: int
) -> ResponseReturnValue:
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


@app.route("/api/global-variables", methods=["GET"])
def api_global_variables_get() -> ResponseReturnValue:
    """读取全局变量列表（值脱敏）。"""
    return _route_api_global_variables_get()


@app.route("/api/global-variables", methods=["POST"])
def api_global_variables_set() -> ResponseReturnValue:
    """设置单个全局变量。"""
    return _route_api_global_variables_set()


@app.route("/api/global-variables", methods=["DELETE"])
def api_global_variables_clear() -> ResponseReturnValue:
    """清空所有全局变量。"""
    return _route_api_global_variables_clear()


@app.route("/api/global-variables/<path:key>", methods=["DELETE"])
def api_global_variables_delete_key(key: str) -> ResponseReturnValue:
    """删除单个全局变量。"""
    return _route_api_global_variables_delete(key)


@app.route("/api/global-variables/all", methods=["GET"])
def api_global_variables_all() -> ResponseReturnValue:
    """读取全部多环境变量（shared + 所有 env）。"""
    return _route_api_global_variables_all()


@app.route("/api/variable-functions", methods=["GET"])
def api_variable_functions() -> ResponseReturnValue:
    """返回变量函数元数据列表。"""
    return _route_api_variable_functions()


@app.route("/api/environments/list", methods=["GET"])
def api_env_list() -> ResponseReturnValue:
    """返回用户可管理的环境列表。"""
    return _route_api_env_list_get()


@app.route("/api/environments", methods=["POST"])
def api_env_create() -> ResponseReturnValue:
    """添加新环境。"""
    return _route_api_env_add()


@app.route("/api/environments/<path:env_name>", methods=["DELETE"])
def api_env_delete(env_name: str) -> ResponseReturnValue:
    """删除环境。"""
    return _route_api_env_remove(env_name)


# ---------------------------------------------------------------
# UI 录制器
# ---------------------------------------------------------------
@app.route("/ui-recorder")
def ui_recorder_page() -> ResponseReturnValue:
    return _route_ui_recorder_page()


@app.route("/ui-recorder/demo")
def ui_recorder_demo_page() -> ResponseReturnValue:
    return _route_ui_recorder_demo_page()


@app.route("/api/ui-recorder/event", methods=["POST", "OPTIONS"])
def api_ui_recorder_event() -> ResponseReturnValue:
    return _route_api_ui_recorder_event()


@app.route("/api/ui-recorder/sessions")
def api_ui_recorder_sessions() -> ResponseReturnValue:
    return _route_api_ui_recorder_sessions()


@app.route("/api/ui-recorder/session/<path:session_id>")
def api_ui_recorder_session_detail(session_id: str) -> ResponseReturnValue:
    return _route_api_ui_recorder_session_detail(session_id)


@app.route("/api/ui-recorder/session/<path:session_id>", methods=["DELETE"])
def api_ui_recorder_session_delete(session_id: str) -> ResponseReturnValue:
    return _route_api_ui_recorder_session_delete(session_id)


@app.route("/api/ui-recorder/session/<path:session_id>/export")
def api_ui_recorder_session_export(session_id: str) -> ResponseReturnValue:
    return _route_api_ui_recorder_session_export(session_id)


@app.route("/api/ui-recorder/sessions/clear-recording", methods=["POST"])
def api_ui_recorder_clear_recording() -> ResponseReturnValue:
    return _route_api_ui_recorder_clear_recording()


# ---------------------------------------------------------------
# Web UI 自动化测试
# ---------------------------------------------------------------
@app.route("/ui-testing")
def ui_testing_index_page() -> ResponseReturnValue:
    return _route_ui_testing_index_page()


@app.route("/ui-testing/recorder")
def ui_testing_recorder_page() -> ResponseReturnValue:
    return _route_ui_testing_recorder_page()


@app.route("/ui-testing/editor/<path:case_id>")
def ui_testing_editor_page(case_id: str) -> ResponseReturnValue:
    return _route_ui_testing_editor_page(case_id)


@app.route("/ui-testing/proxy", methods=["GET", "POST"])
def ui_testing_proxy() -> ResponseReturnValue:
    return _route_ui_testing_proxy()


@app.route(
    "/ui-testing/proxy-resource",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
def ui_testing_proxy_resource() -> ResponseReturnValue:
    return _route_ui_testing_proxy_resource()


@app.route("/api/ui-testing/proxy-sessions", methods=["GET"])
def ui_proxy_sessions_debug() -> ResponseReturnValue:
    """调试端点：查看代理会话 cookie 状态。"""
    return _route_ui_proxy_sessions_debug()


@app.route("/api/ui-testing/subsystem-token", methods=["GET"])
def ui_subsystem_token() -> ResponseReturnValue:
    """获取当前代理会话的子系统 token（供回放引擎在 new_tab 跳转前查询）。"""
    from flask import request as _req

    session_id = _req.cookies.get("_proxy_session", "")
    if not session_id:
        return {"code": 0, "data": {"token": ""}}
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    token = _proxy_session_store.get_subsystem_token(session_id) or ""
    return {"code": 0, "data": {"token": token}}


@app.route("/static/<path:filename>")
def ui_testing_static_fallback(filename: str) -> ResponseReturnValue:
    return _route_ui_testing_static_fallback(filename)


@app.route(
    "/<path:resource_path>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
def ui_testing_spa_resource_fallback(resource_path: str) -> ResponseReturnValue:
    return _route_ui_testing_spa_resource_fallback(resource_path)


@app.route("/api/ui-testing/cases")
def api_ui_testing_cases_list() -> ResponseReturnValue:
    return _route_api_ui_testing_cases_list()


@app.route("/api/ui-testing/cases", methods=["POST"])
def api_ui_testing_cases_create() -> ResponseReturnValue:
    return _route_api_ui_testing_cases_create()


@app.route("/api/ui-testing/cases/<path:case_id>")
def api_ui_testing_case_get(case_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_case_get(case_id)


@app.route("/api/ui-testing/cases/<path:case_id>", methods=["PUT"])
def api_ui_testing_case_update(case_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_case_update(case_id)


@app.route("/api/ui-testing/cases/<path:case_id>", methods=["DELETE"])
def api_ui_testing_case_delete(case_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_case_delete(case_id)


@app.route("/api/ui-testing/recording/start", methods=["POST"])
def api_ui_testing_recording_start() -> ResponseReturnValue:
    return _route_api_ui_testing_recording_start()


@app.route("/api/ui-testing/recording/step", methods=["POST"])
def api_ui_testing_recording_step() -> ResponseReturnValue:
    return _route_api_ui_testing_recording_step()


@app.route("/api/ui-testing/recording/stop", methods=["POST"])
def api_ui_testing_recording_stop() -> ResponseReturnValue:
    return _route_api_ui_testing_recording_stop()


@app.route("/api/ui-testing/recording/local-storage", methods=["POST"])
def api_ui_testing_recording_local_storage() -> ResponseReturnValue:
    return _route_api_ui_testing_recording_local_storage()


@app.route("/api/ui-testing/recording/<path:session_id>")
def api_ui_testing_recording_get(session_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_recording_get(session_id)


@app.route("/api/ui-testing/recording/<path:session_id>/save", methods=["POST"])
def api_ui_testing_recording_save_as_case() -> ResponseReturnValue:
    return _route_api_ui_testing_recording_save_as_case()


# ── UI 测试执行 ──


@app.route("/api/ui-testing/execute/<path:case_id>", methods=["POST"])
def api_ui_testing_execute(case_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execute(case_id)


@app.route("/api/ui-testing/execution/<path:job_id>/status")
def api_ui_testing_execution_status(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_status(job_id)


@app.route("/api/ui-testing/execution/<path:job_id>/report")
def api_ui_testing_execution_report(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_report(job_id)


@app.route("/api/ui-testing/executions")
def api_ui_testing_executions_list() -> ResponseReturnValue:
    return _route_api_ui_testing_executions_list()


@app.route("/api/ui-testing/execution/<path:job_id>/cancel", methods=["POST"])
def api_ui_testing_execution_cancel(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_cancel(job_id)


@app.route("/api/ui-testing/execution/<path:job_id>/step", methods=["POST"])
def api_ui_testing_execution_step_report(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_step_report(job_id)


@app.route("/api/ui-testing/execution/<path:job_id>/finalize", methods=["POST"])
def api_ui_testing_execution_finalize(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_finalize(job_id)


@app.route("/api/ui-testing/execution/<path:job_id>/init")
def api_ui_testing_execution_init(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_init(job_id)


@app.route("/api/ui-testing/execution/<path:job_id>/screenshot/<int:step_index>")
def api_ui_testing_execution_screenshot(
    job_id: str, step_index: int
) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_screenshot(job_id, step_index)


@app.route("/api/ui-testing/execution/<path:job_id>/screenshot", methods=["POST"])
def api_ui_testing_execution_screenshot_save(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_execution_screenshot_post(job_id)


@app.route("/api/ui-testing/replay-engine-js")
def api_ui_testing_replay_engine_js() -> ResponseReturnValue:
    return _route_api_ui_testing_replay_engine_js()


@app.route("/api/ui-testing/replay-log", methods=["POST"])
def api_ui_testing_replay_log() -> ResponseReturnValue:
    return _route_api_ui_testing_replay_log()


@app.route("/ui-testing/replay/<path:job_id>")
def ui_testing_replay_page(job_id: str) -> ResponseReturnValue:
    return _route_ui_testing_replay_page(job_id)


@app.route("/ui-testing/execution/<path:job_id>/report")
def ui_testing_report_page(job_id: str) -> ResponseReturnValue:
    return _route_ui_testing_report_page(job_id)


@app.route("/api/ui-testing/settings", methods=["GET"])
def api_ui_testing_settings_get() -> ResponseReturnValue:
    return _route_api_ui_testing_settings_get()


@app.route("/api/ui-testing/settings", methods=["PUT"])
def api_ui_testing_settings_update() -> ResponseReturnValue:
    return _route_api_ui_testing_settings_update()


@app.route("/api/ui-testing/playwright-status", methods=["GET"])
def api_ui_testing_playwright_status() -> ResponseReturnValue:
    return _route_api_ui_testing_playwright_status()


@app.route("/api/ui-testing/settings/reset", methods=["POST"])
def api_ui_testing_settings_reset() -> ResponseReturnValue:
    return _route_api_ui_testing_settings_reset()


@app.route("/api/ui-testing/cleanup", methods=["POST"])
def api_ui_testing_cleanup() -> ResponseReturnValue:
    return _route_api_ui_testing_cleanup()


@app.route("/ui-testing/settings")
def ui_testing_settings_page() -> ResponseReturnValue:
    return _route_ui_testing_settings_page()


@app.route("/ui-testing/reports")
def ui_testing_reports_page() -> ResponseReturnValue:
    return _route_ui_testing_reports_page()


@app.route("/api/ui-testing/reports")
def api_ui_testing_reports_list() -> ResponseReturnValue:
    return _route_api_ui_testing_reports_list()


@app.route("/api/ui-testing/report/<path:job_id>", methods=["DELETE"])
def api_ui_testing_report_delete(job_id: str) -> ResponseReturnValue:
    return _route_api_ui_testing_report_delete(job_id)


# ── UI 认证档案 ──


@app.route("/api/ui-testing/auth-profiles", methods=["GET"])
def ui_auth_profiles_list() -> ResponseReturnValue:
    return _route_api_ui_auth_profiles_list()


@app.route("/api/ui-testing/auth-profiles", methods=["POST"])
def ui_auth_profiles_create() -> ResponseReturnValue:
    return _route_api_ui_auth_profiles_create()


@app.route("/api/ui-testing/auth-profiles/<path:profile_id>", methods=["GET"])
def ui_auth_profile_get(profile_id: str) -> ResponseReturnValue:
    return _route_api_ui_auth_profile_get(profile_id)


@app.route("/api/ui-testing/auth-profiles/<path:profile_id>", methods=["PUT"])
def ui_auth_profile_update(profile_id: str) -> ResponseReturnValue:
    return _route_api_ui_auth_profile_update(profile_id)


@app.route("/api/ui-testing/auth-profiles/<path:profile_id>", methods=["DELETE"])
def ui_auth_profile_delete(profile_id: str) -> ResponseReturnValue:
    return _route_api_ui_auth_profile_delete(profile_id)


@app.route(
    "/api/ui-testing/auth-profiles/<path:profile_id>/export", methods=["GET"]
)
def ui_auth_profile_export_route(profile_id: str) -> ResponseReturnValue:
    return _route_api_ui_auth_profile_export(profile_id)


@app.route("/api/ui-testing/auth-profiles/cleanup", methods=["POST"])
def ui_auth_profiles_cleanup() -> ResponseReturnValue:
    return _route_api_ui_auth_profiles_cleanup()


@app.route("/ui-testing/auth-profiles")
def ui_auth_profiles_page_route() -> ResponseReturnValue:
    return _route_ui_auth_profiles_page()


# ── 登录配置路由 ──────────────────────────────────────────────────
from postman_api_tester.handlers.ui_login_routes import (
    api_ui_login_config_delete as _route_api_ui_login_config_delete,
)
from postman_api_tester.handlers.ui_login_routes import (
    api_ui_login_config_get as _route_api_ui_login_config_get,
)
from postman_api_tester.handlers.ui_login_routes import (
    api_ui_login_config_test as _route_api_ui_login_config_test,
)
from postman_api_tester.handlers.ui_login_routes import (
    api_ui_login_config_update as _route_api_ui_login_config_update,
)
from postman_api_tester.handlers.ui_login_routes import (
    api_ui_login_configs_create as _route_api_ui_login_configs_create,
)
from postman_api_tester.handlers.ui_login_routes import (
    api_ui_login_configs_list as _route_api_ui_login_configs_list,
)
from postman_api_tester.handlers.ui_login_routes import (
    ui_login_config_editor_page as _route_ui_login_config_editor_page,
)
from postman_api_tester.handlers.ui_login_routes import (
    ui_login_configs_page as _route_ui_login_configs_page,
)


@app.route("/api/ui-testing/login-configs", methods=["GET"])
def ui_login_configs_list_route() -> ResponseReturnValue:
    return _route_api_ui_login_configs_list()


@app.route("/api/ui-testing/login-configs", methods=["POST"])
def ui_login_configs_create_route() -> ResponseReturnValue:
    return _route_api_ui_login_configs_create()


@app.route("/api/ui-testing/login-configs/<path:config_id>", methods=["GET"])
def ui_login_config_get_route(config_id: str) -> ResponseReturnValue:
    return _route_api_ui_login_config_get(config_id)


@app.route("/api/ui-testing/login-configs/<path:config_id>", methods=["PUT"])
def ui_login_config_update_route(config_id: str) -> ResponseReturnValue:
    return _route_api_ui_login_config_update(config_id)


@app.route("/api/ui-testing/login-configs/<path:config_id>", methods=["DELETE"])
def ui_login_config_delete_route(config_id: str) -> ResponseReturnValue:
    return _route_api_ui_login_config_delete(config_id)


@app.route(
    "/api/ui-testing/login-configs/<path:config_id>/test", methods=["POST"]
)
def ui_login_config_test_route(config_id: str) -> ResponseReturnValue:
    return _route_api_ui_login_config_test(config_id)


@app.route("/ui-testing/login-configs")
def ui_login_configs_page_route() -> ResponseReturnValue:
    return _route_ui_login_configs_page()


@app.route("/ui-testing/login-configs/editor")
@app.route("/ui-testing/login-configs/editor/<path:config_id>")
def ui_login_config_editor_page_route(config_id: str = "") -> ResponseReturnValue:
    return _route_ui_login_config_editor_page(config_id)


@app.route("/favicon.ico")
def favicon() -> ResponseReturnValue:
    from flask import make_response

    return make_response("", 204)


# 入口已迁移到 postman_api_tester.report_server_app.ReportServerApp.run_app()
# 命令行启动: python -c "from postman_api_tester.report_server_app import ReportServerApp; ReportServerApp.run_app(ReportServerApp.create_app())"

if __name__ == "__main__":
    from postman_api_tester.report_server_app import ReportServerApp

    ReportServerApp.run_app(app)
