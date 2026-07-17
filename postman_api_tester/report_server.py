#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告服务端模块。

开发导读:
- 提供报告列表、详情、重试执行、导出与局域网访问入口。
- 负责路由装配与服务生命周期管理，业务逻辑下沉到 handlers/services。
"""

import logging
from postman_api_tester.services.ui_recorder_inject import get_replayer_js

from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.global_variables_routes import (
    api_env_add as _route_api_env_add,
    api_env_list_get as _route_api_env_list_get,
    api_env_remove as _route_api_env_remove,
    api_global_variables_all as _route_api_global_variables_all,
    api_global_variables_clear as _route_api_global_variables_clear,
    api_global_variables_delete as _route_api_global_variables_delete,
    api_global_variables_get as _route_api_global_variables_get,
    api_global_variables_set as _route_api_global_variables_set,
    api_variable_functions as _route_api_variable_functions,
)
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
from postman_api_tester.handlers.ui_recorder_routes import (
    api_ui_recorder_event as _route_api_ui_recorder_event,
    api_ui_recorder_sessions as _route_api_ui_recorder_sessions,
    api_ui_recorder_session_detail as _route_api_ui_recorder_session_detail,
    api_ui_recorder_session_delete as _route_api_ui_recorder_session_delete,
    api_ui_recorder_session_export as _route_api_ui_recorder_session_export,
    api_ui_recorder_clear_recording as _route_api_ui_recorder_clear_recording,
    ui_recorder_demo_page as _route_ui_recorder_demo_page,
    ui_recorder_page as _route_ui_recorder_page,
)
from postman_api_tester.handlers.ui_testing_routes import (
    api_ui_testing_case_delete as _route_api_ui_testing_case_delete,
    api_ui_testing_case_get as _route_api_ui_testing_case_get,
    api_ui_testing_case_update as _route_api_ui_testing_case_update,
    api_ui_testing_cases_create as _route_api_ui_testing_cases_create,
    api_ui_testing_cases_list as _route_api_ui_testing_cases_list,
    api_ui_testing_recording_get as _route_api_ui_testing_recording_get,
    api_ui_testing_recording_save_as_case as _route_api_ui_testing_recording_save_as_case,
    api_ui_testing_recording_start as _route_api_ui_testing_recording_start,
    api_ui_testing_recording_step as _route_api_ui_testing_recording_step,
    api_ui_testing_recording_stop as _route_api_ui_testing_recording_stop,
    ui_testing_editor_page as _route_ui_testing_editor_page,
    ui_testing_index_page as _route_ui_testing_index_page,
    ui_testing_proxy as _route_ui_testing_proxy,
    ui_testing_proxy_resource as _route_ui_testing_proxy_resource,
    ui_proxy_sessions_debug as _route_ui_proxy_sessions_debug,
    ui_testing_recorder_page as _route_ui_testing_recorder_page,
    ui_testing_static_fallback as _route_ui_testing_static_fallback,
)
from postman_api_tester.handlers.ui_execution_routes import (
    api_ui_testing_execute as _route_api_ui_testing_execute,
    api_ui_testing_execution_cancel as _route_api_ui_testing_execution_cancel,
    api_ui_testing_execution_finalize as _route_api_ui_testing_execution_finalize,
    api_ui_testing_execution_init as _route_api_ui_testing_execution_init,
    api_ui_testing_execution_report as _route_api_ui_testing_execution_report,
    api_ui_testing_execution_screenshot as _route_api_ui_testing_execution_screenshot,
    api_ui_testing_execution_screenshot_post as _route_api_ui_testing_execution_screenshot_post,
    api_ui_testing_execution_status as _route_api_ui_testing_execution_status,
    api_ui_testing_execution_step_report as _route_api_ui_testing_execution_step_report,
    api_ui_testing_executions_list as _route_api_ui_testing_executions_list,
    api_ui_testing_replay_engine_js as _route_api_ui_testing_replay_engine_js,
    api_ui_testing_replay_log as _route_api_ui_testing_replay_log,
    api_ui_testing_report_delete as _route_api_ui_testing_report_delete,
    api_ui_testing_reports_list as _route_api_ui_testing_reports_list,
    api_ui_testing_settings_get as _route_api_ui_testing_settings_get,
    api_ui_testing_settings_update as _route_api_ui_testing_settings_update,
    api_ui_testing_playwright_status as _route_api_ui_testing_playwright_status,
    api_ui_testing_settings_reset as _route_api_ui_testing_settings_reset,
    api_ui_testing_cleanup as _route_api_ui_testing_cleanup,
    ui_testing_replay_page as _route_ui_testing_replay_page,
    ui_testing_report_page as _route_ui_testing_report_page,
    ui_testing_reports_page as _route_ui_testing_reports_page,
    ui_testing_settings_page as _route_ui_testing_settings_page,
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


@app.route("/ui-testing/proxy-resource", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def ui_testing_proxy_resource() -> ResponseReturnValue:
    return _route_ui_testing_proxy_resource()


@app.route("/api/ui-testing/proxy-sessions", methods=["GET"])
def ui_proxy_sessions_debug() -> ResponseReturnValue:
    """调试端点：查看代理会话 cookie 状态。"""
    return _route_ui_proxy_sessions_debug()


@app.route("/static/<path:filename>")
def ui_testing_static_fallback(filename: str) -> ResponseReturnValue:
    return _route_ui_testing_static_fallback(filename)


@app.route("/<path:resource_path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def ui_testing_spa_resource_fallback(resource_path: str) -> ResponseReturnValue:
    """SPA 资源/API 兜底：拦截所有未被其他路由处理的请求，
    转发到目标服务器。覆盖早期脚本 fetch 拦截器未覆盖的情况。"""
    from flask import make_response, request
    from urllib.parse import unquote as _uq
    from urllib.parse import urlparse as _urlparse, parse_qs

    _ext = resource_path.rsplit(".", 1)[-1].lower() if "." in resource_path else ""
    _resource_exts = {
        "png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp",
        "woff", "woff2", "ttf", "eot", "otf",
        "css", "js",
    }
    # 跳过代理自身的路径（不转发），但允许目标服务器的 /api/ 路径走兜底转发
    _skip_prefixes = {"ui-testing/", "ui-recorder/", "favicon.ico"}
    for prefix in _skip_prefixes:
        if resource_path.startswith(prefix):
            from flask import abort
            abort(404)
    # 代理自身的 API 路径也跳过（不走兜底转发）
    _proxy_api_prefixes = {"api/ui-testing/", "api/ui-recorder/", "api/postman/", "api/report/"}
    for prefix in _proxy_api_prefixes:
        if resource_path.startswith(prefix):
            from flask import abort
            abort(404)

    # OPTIONS 预检请求直接返回
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        return resp

    # 检查是否为资源请求（有扩展名）或 API 请求（包含 /api/ 路径段）
    is_resource = _ext in _resource_exts
    is_api = "/api/" in resource_path or resource_path.startswith("api/")
    # 页面请求：没有扩展名且不是 API（如 /home, /login, /dashboard）
    is_page = not is_resource and not is_api

    # 从 URL 参数提取目标 URL（新方案：_proxy_url 参数）
    params = parse_qs(request.query_string.decode("utf-8", errors="replace"))
    target_url = params.get("_proxy_url", [""])[0] or params.get("url", [""])[0]

    # 从 Referer 提取目标 URL（旧方案兼容）
    referer = request.headers.get("Referer", "")
    if not target_url and referer:
        try:
            parsed_ref = _urlparse(referer)
            ref_params = parse_qs(parsed_ref.query)
            target_url = ref_params.get("_proxy_url", [""])[0] or ref_params.get("url", [""])[0]
        except Exception:
            pass

    # 记录兜底请求
    logger.warning(
        "spa_fallback_request",
        extra={
            "event": "ui.proxy.fallback_request",
            "method": request.method,
            "path": resource_path,
            "is_page": is_page,
            "referer": referer if referer else "(none)",
        },
    )

    # 从 Cookie session 中获取 base_url
    if not target_url:
        session_id = request.cookies.get("_proxy_session")
        if session_id:
            from postman_api_tester.services.ui_proxy_service import _proxy_session_store
            target_url = _proxy_session_store.get_base_url(session_id) or ""

    # 如果还是没有 target_url，使用最近一次会话的 base_url
    if not target_url:
        from postman_api_tester.services.ui_proxy_service import _proxy_session_store
        with _proxy_session_store._lock:
            all_sessions = list(_proxy_session_store._sessions.items())
        if all_sessions:
            latest_sid = max(all_sessions, key=lambda item: item[1].get("last_active", 0))[0]
            target_url = _proxy_session_store.get_base_url(latest_sid) or ""

    if not target_url:
        from flask import abort
        abort(404)

    target_url = _uq(target_url)
    parsed_target = _urlparse(target_url)
    # 对于页面请求，使用 resource_path 作为目标路径；对于资源/API，也使用 resource_path
    full_url = f"{parsed_target.scheme}://{parsed_target.netloc}/{resource_path}"

    # 从 target_url 中提取 base_url，确保代理会话的 base_url 正确设置
    base_url = f"{parsed_target.scheme}://{parsed_target.netloc}"
    replay_mode = params.get("replay", [""])[0] == "1"
    recording_mode = params.get("recording", [""])[0] == "1"

    # 录制模式：清除旧的代理会话 cookie，创建新会话（确保从干净状态开始录制）
    if recording_mode:
        from postman_api_tester.services.ui_proxy_service import _proxy_session_store
        old_sid = request.cookies.get("_proxy_session")
        if old_sid:
            _proxy_session_store.delete_session(old_sid)
            logger.info("spa_fallback_recording_clear_session", extra={
                "event": "ui.proxy.fallback.recording_clear",
                "old_session_id": old_sid[:8],
            })
        session_id = _proxy_session_store.create_session(base_url)
        logger.info("spa_fallback_recording_new_session", extra={
            "event": "ui.proxy.fallback.recording_new",
            "session_id": session_id[:8],
            "base_url": base_url,
        })
    else:
        # 调用 _get_proxy_session_id 获取 session_id，确保 base_url 被正确设置
        from postman_api_tester.handlers.ui_testing_routes import _get_proxy_session_id
        session_id = _get_proxy_session_id(base_url)

    try:
        from typing import Union
        from postman_api_tester.services.ui_proxy_service import UiProxyService
        body: Union[str, bytes]
        if is_page:
            # 回放模式：获取回放引擎 JS 代码并注入到每个页面
            replay_engine_js = ""
            if replay_mode:
                origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
                replay_engine_js = get_replayer_js(origin)

            # 页面请求：使用 fetch_and_rewrite 改写 HTML
            body, status_code, headers = UiProxyService.fetch_and_rewrite(
                full_url,
                session_id if session_id else None,
                method=request.method,
                req_headers=dict(request.headers),
                req_body=request.get_data() if request.method != "GET" else None,
                replay_mode=replay_mode,
                recording_mode=recording_mode,
                replay_engine_js=replay_engine_js,
            )
        else:
            # 资源/API 请求：使用 fetch_resource
            body, status_code, headers = UiProxyService.fetch_resource(
                full_url,
                method=request.method,
                req_headers=dict(request.headers),
                req_body=request.get_data() if request.method not in ("GET", "HEAD") else None,
                session_id=session_id if session_id else None,
            )
    except Exception:
        return make_response(b"", 404)

    # 内容类型校验（仅对资源请求）
    if is_resource:
        content_type = headers.get("Content-Type", "")
        _binary_exts = {"png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp", "woff", "woff2", "ttf", "eot", "otf"}
        if _ext in _binary_exts and content_type.startswith("text/"):
            return make_response(b"", 404)

    # 重写 Location 响应头（页面请求的重定向）
    # 跳过已包含 _proxy_url 的 Location（由 ui_proxy_service 改写）
    if is_page and "Location" in headers and "_proxy_url" not in headers["Location"]:
        loc = headers["Location"]
        from urllib.parse import quote as _quote2
        base_url = f"{parsed_target.scheme}://{parsed_target.netloc}"
        if loc.startswith(("http://", "https://")):
            # 绝对 URL：提取 pathname
            loc_parsed = _urlparse(loc)
            loc_path = loc_parsed.pathname + ('?' + loc_parsed.query if loc_parsed.query else '') + \
                ('#' + loc_parsed.fragment if loc_parsed.fragment else '')
            sep = '&' if '?' in loc_path else '?'
            headers["Location"] = loc_path + sep + '_proxy_url=' + _quote2(loc, safe='')
        elif loc.startswith("/"):
            # 相对路径：构造完整 URL
            full_loc = base_url + loc
            loc_path = loc
            sep = '&' if '?' in loc_path else '?'
            headers["Location"] = loc_path + sep + '_proxy_url=' + _quote2(full_loc, safe='')

    resp = make_response(body, status_code)
    for key, value in headers.items():
        if key == "_set_cookies":
            for cookie_str in value:
                resp.headers.add("Set-Cookie", cookie_str)
        else:
            resp.headers[key] = value
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    if session_id:
        resp.headers.add("Set-Cookie", f"_proxy_session={session_id}; HttpOnly; SameSite=Lax; Max-Age=3600; Path=/")
    return resp


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
def api_ui_testing_execution_screenshot(job_id: str, step_index: int) -> ResponseReturnValue:
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


@app.route("/favicon.ico")
def favicon() -> ResponseReturnValue:
    from flask import make_response
    return make_response("", 204)


# 入口已迁移到 postman_api_tester.report_server_app.ReportServerApp.run_app()
# 命令行启动: python -c "from postman_api_tester.report_server_app import ReportServerApp; ReportServerApp.run_app(ReportServerApp.create_app())"

if __name__ == "__main__":
    from postman_api_tester.report_server_app import ReportServerApp
    ReportServerApp.run_app(app)


