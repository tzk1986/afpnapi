#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告服务端模块。

开发导读:
- 提供报告列表、详情、重试执行、导出与局域网访问入口。
- 负责路由装配与服务生命周期管理，业务逻辑下沉到 handlers/services。
"""

import json
import logging
import os
import re
import socket
import time
import uuid
from types import ModuleType
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Dict, Iterator, List, Optional, SupportsInt
from flask import Flask, Response, jsonify, make_response, redirect, render_template, request, send_from_directory, stream_with_context, url_for
from flask.typing import ResponseReturnValue
from postman_api_tester.utils.url_utils import (
    merge_url_with_params as _merge_url_with_params,
    normalize_url_and_params as _normalize_url_and_params,
)
from postman_api_tester.services.report_patch_service import patch_report_result as _patch_report_result
from postman_api_tester.services.report_export_service import (
    export_collection_with_latest_params as _svc_export_collection_with_latest_params,
)
from postman_api_tester.services.report_request_service import (
    extract_http_request_fields as _svc_extract_http_request_fields,
    inject_token_header as _svc_inject_token_header,
    is_valid_http_url as _svc_is_valid_http_url,
    parse_int_default as _svc_parse_int_default,
    parse_optional_int as _svc_parse_optional_int,
    resolve_request_payload_source as _svc_resolve_request_payload_source,
)
from postman_api_tester.services.report_job_submission_service import (
    build_ad_hoc_job_params as _build_ad_hoc_job_params,
    build_run_postman_job_params as _build_run_postman_job_params,
    build_saved_json_path as _build_saved_json_path,
    sanitize_uploaded_name as _sanitize_uploaded_name,
)
from postman_api_tester.report_job_store import configure_run_jobs, get_run_job, set_run_job
from postman_api_tester.report_meta_repository import configure_reports_dir
from postman_api_tester.services.report_judgement_service import set_report_result_judgement as _svc_set_report_result_judgement
from postman_api_tester.services.report_junit_service import build_junit_xml as _svc_build_junit_xml
from postman_api_tester.services.report_lock_service import get_report_write_lock
from postman_api_tester.services.report_meta_update_service import update_report_meta as _svc_update_report_meta
from postman_api_tester.report_repository import (
    collect_report_artifacts,
    configure_report_repository,
    find_report as _repo_find_report,
    invalidate_reports_cache as _repo_invalidate_reports_cache,
    list_reports as _repo_list_reports,
)
from postman_api_tester.services.report_results_service import (
    build_case_exclusion_payload as build_case_exclusion_payload,
    build_collection_preview_payload as build_collection_preview_payload,
    build_compare_payload as build_compare_payload,
    build_error_payload as build_error_payload,
    build_environments_payload as build_environments_payload,
    build_export_collection_payload as build_export_collection_payload,
    build_health_payload as build_health_payload,
    build_job_queued_payload as build_job_queued_payload,
    build_manual_case_delete_payload as build_manual_case_delete_payload,
    build_manual_case_upsert_payload as build_manual_case_upsert_payload,
    build_proxy_response_payload as build_proxy_response_payload,
    build_re_request_error_payload as build_re_request_error_payload,
    build_re_request_success_payload as build_re_request_success_payload,
    build_report_delete_payload as build_report_delete_payload,
    build_report_meta_payload as build_report_meta_payload,
    build_result_detail_payload as build_result_detail_payload,
    build_result_judgement_payload as build_result_judgement_payload,
    build_retry_queued_payload as build_retry_queued_payload,
    build_test_token_payload as build_test_token_payload,
)
from postman_api_tester.report_server_utils import (
    manual_case_exclusion_key as _manual_case_exclusion_key,
    normalize_exclusion_key as _normalize_exclusion_key,
    normalize_manual_case as _normalize_manual_case,
    normalize_manual_exclusions as _normalize_manual_exclusions,
    to_bool as _to_bool,
)
from postman_api_tester.handlers.collection_handler import (
    build_adhoc_collection as _svc_build_adhoc_collection,
    extract_collection_preview_items as _svc_extract_collection_preview_items,
    normalize_adhoc_case as _svc_normalize_adhoc_case,
    parse_selected_item_paths as _svc_parse_selected_item_paths,
)
from postman_api_tester.handlers.admin_handler import delete_report_artifacts as _admin_delete_report_artifacts
from postman_api_tester.handlers.http_handler import execute_http_request as _http_execute_http_request
from postman_api_tester.handlers.job_handler import (
    enqueue_job_with_worker as _job_enqueue_job_with_worker,
    enqueue_retry_job as _job_enqueue_retry_job,
    prepare_retry_job_context as _job_prepare_retry_job_context,
    run_postman_job as _job_run_postman_job,
)
from postman_api_tester.handlers.manual_case_handler import (
    add_manual_case as _manual_add_manual_case,
    delete_manual_case as _manual_delete_manual_case,
    list_manual_cases as _manual_list_manual_cases,
    set_case_exclusion as _manual_set_case_exclusion,
    update_manual_case as _manual_update_manual_case,
)
from postman_api_tester.handlers.report_handler import (
    build_report_results_payload as _report_build_report_results_payload,
    normalize_status_filter as _report_normalize_status_filter,
)
from postman_api_tester.utils.report_utils import (
    compute_summary as _utils_compute_summary,
)
from postman_api_tester.utils.response_parser import (
    extract_msg_errcode as _utils_extract_msg_errcode,
)
from postman_api_tester.utils.logging_utils import (
    configure_logging_from_config,
    get_log_alert_snapshot,
    get_log_metrics_snapshot,
    get_log_sample_rate,
    log_sampled,
)

configure_logging_from_config(service_name="report_server")
logger = logging.getLogger(__name__)
ACCESS_LOG_SAMPLE_RATE = get_log_sample_rate(default=0.1)

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent

_cfg: Optional[ModuleType]
try:
    from postman_api_tester import config as _cfg
except Exception:
    _cfg = None


def _cfg_int(name: str, default: int) -> int:
    if _cfg is None:
        return int(default)
    try:
        return int(getattr(_cfg, name, default))
    except (TypeError, ValueError):
        return int(default)


def _cfg_bool(name: str, default: bool) -> bool:
    if _cfg is None:
        return bool(default)
    value = getattr(_cfg, name, default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _cfg_str(name: str, default: str) -> str:
    if _cfg is None:
        return str(default)
    value = getattr(_cfg, name, default)
    return str(value).strip() if value is not None else str(default)


RUN_RESULTS_PER_PAGE_DEFAULT = _cfg_int("RUN_RESULTS_PER_PAGE_DEFAULT", 30)
RUN_RESULTS_PER_PAGE_MIN = _cfg_int("RUN_RESULTS_PER_PAGE_MIN", 1)
RUN_RESULTS_PER_PAGE_MAX = _cfg_int("RUN_RESULTS_PER_PAGE_MAX", 100)

REPORT_VIEW_PAGE_SIZE_DEFAULT = _cfg_int("REPORT_VIEW_PAGE_SIZE_DEFAULT", 20)
REPORT_VIEW_PAGE_SIZE_MIN = _cfg_int("REPORT_VIEW_PAGE_SIZE_MIN", 1)
REPORT_VIEW_PAGE_SIZE_MAX = _cfg_int("REPORT_VIEW_PAGE_SIZE_MAX", 100)

RUN_STATUS_POLL_INTERVAL_MS = _cfg_int("RUN_STATUS_POLL_INTERVAL_MS", 3000)
ENABLE_SELECTIVE_RUN = _cfg_bool("ENABLE_SELECTIVE_RUN", True)
COLLECTION_PREVIEW_MAX_ITEMS = _cfg_int("COLLECTION_PREVIEW_MAX_ITEMS", 3000)

REPORT_EXPORT_DEFAULT_SCOPE = _cfg_str("REPORT_EXPORT_DEFAULT_SCOPE", "full").lower() or "full"
if REPORT_EXPORT_DEFAULT_SCOPE not in {"full", "report_only"}:
    REPORT_EXPORT_DEFAULT_SCOPE = "full"
REPORT_EXPORT_ALLOW_REPORT_ONLY = _cfg_bool("REPORT_EXPORT_ALLOW_REPORT_ONLY", True)
REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = _cfg_bool("REPORT_EXPORT_INCLUDE_AUTH_DEFAULT", False)
REPORT_EXPORT_CHANNEL_MODE = _cfg_str("REPORT_EXPORT_CHANNEL_MODE", "auto").lower() or "auto"
if REPORT_EXPORT_CHANNEL_MODE not in {"auto", "legacy", "stream"}:
    REPORT_EXPORT_CHANNEL_MODE = "auto"
REPORT_EXPORT_STREAM_THRESHOLD = max(1, _cfg_int("REPORT_EXPORT_STREAM_THRESHOLD", 800))
ENABLE_MANUAL_CASES = _cfg_bool("ENABLE_MANUAL_CASES", True)
MANUAL_CASE_FOLDER_NAME = _cfg_str("MANUAL_CASE_FOLDER_NAME", "人工补录") or "人工补录"
ENABLE_ADHOC_RUN = _cfg_bool("ENABLE_ADHOC_RUN", True)
ADHOC_MAX_ITEMS = _cfg_int("ADHOC_MAX_ITEMS", 200)
ADHOC_DEFAULT_COLLECTION_NAME = _cfg_str("ADHOC_DEFAULT_COLLECTION_NAME", "报告中心临时测试") or "报告中心临时测试"
ENABLE_RESPONSE_TIME = _cfg_bool("ENABLE_RESPONSE_TIME", True)
ENABLE_RETRY_FAILURES = _cfg_bool("ENABLE_RETRY_FAILURES", True)
ENABLE_JUNIT_EXPORT = _cfg_bool("ENABLE_JUNIT_EXPORT", True)
ENABLE_REPORT_LIST_FILTER = _cfg_bool("ENABLE_REPORT_LIST_FILTER", True)
ENABLE_ASSERTIONS = _cfg_bool("ENABLE_ASSERTIONS", False)


def _cfg_dict(name: str, default: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    if default is None:
        default = {}
    if _cfg is None:
        return default
    value = getattr(_cfg, name, default)
    return value if isinstance(value, dict) else default


EnvironmentConfig = Dict[str, str]
JobParams = Dict[str, object]
SummaryPayload = Dict[str, object]


def _normalize_environments(raw_environments: object) -> Dict[str, EnvironmentConfig]:
    if not isinstance(raw_environments, dict):
        return {}

    normalized: Dict[str, EnvironmentConfig] = {}
    for env_name, env_value in raw_environments.items():
        if not isinstance(env_value, dict):
            continue
        normalized[str(env_name)] = {
            "base_url": str(env_value.get("base_url", "") or "").strip(),
            "token": str(env_value.get("token", "") or "").strip(),
        }
    return normalized


ENVIRONMENTS: Dict[str, EnvironmentConfig] = _normalize_environments(_cfg_dict("ENVIRONMENTS", {}))
DEFAULT_ENV_NAME: str = _cfg_str("DEFAULT_ENV_NAME", "")


def resolve_reports_dir() -> Path:
    env_dir = (os.environ.get("POSTMAN_REPORTS_DIR") or os.environ.get("REPORTS_DIR") or "").strip()
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


REPORTS_DIR = resolve_reports_dir()
UPLOADS_DIR = (PROJECT_ROOT / "uploaded_collections").resolve()
EXPORTS_DIR = (UPLOADS_DIR / "exports").resolve()
configure_reports_dir(REPORTS_DIR)
configure_report_repository(REPORTS_DIR, cache_ttl=30.0)


app = Flask(__name__, template_folder=str((PROJECT_ROOT / "templates").resolve()))



def get_local_ip() -> str:
    """Return LAN IP and fallback to loopback when detection fails."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()
    
def _json_error(message: str, status_code: int) -> ResponseReturnValue:
    return jsonify(build_error_payload(message)), status_code


def clamp_page(value: SupportsInt | str | bytes | bytearray | None) -> int:
    if value is None:
        page = 1
    else:
        try:
            page = int(value)
        except (TypeError, ValueError):
            page = 1
    return max(1, page)

def clamp_page_size(value: SupportsInt | str | bytes | bytearray | None) -> int:
    if value is None:
        page_size = REPORT_VIEW_PAGE_SIZE_DEFAULT
    else:
        try:
            page_size = int(value)
        except (TypeError, ValueError):
            page_size = REPORT_VIEW_PAGE_SIZE_DEFAULT
    return max(REPORT_VIEW_PAGE_SIZE_MIN, min(page_size, REPORT_VIEW_PAGE_SIZE_MAX))

def clamp_run_results_per_page(value: SupportsInt | str | bytes | bytearray | None) -> int:
    if value is None:
        page_size = RUN_RESULTS_PER_PAGE_DEFAULT
    else:
        try:
            page_size = int(value)
        except (TypeError, ValueError):
            page_size = RUN_RESULTS_PER_PAGE_DEFAULT
    return max(RUN_RESULTS_PER_PAGE_MIN, min(page_size, RUN_RESULTS_PER_PAGE_MAX))


def _enqueue_job(
    *,
    job_id: str,
    saved_file: str,
    job_params: JobParams,
    results_per_page: int,
    selected_item_paths: Optional[List[List[int]]],
) -> None:
    _job_enqueue_job_with_worker(
        job_id=job_id,
        saved_file=saved_file,
        job_params=job_params,
        results_per_page=results_per_page,
        run_postman_job_fn=_RUN_POSTMAN_JOB_FN,
        set_run_job=set_run_job,
        default_output_dir=str(REPORTS_DIR),
        selected_item_paths=selected_item_paths,
    )


_RUN_JOBS_MAX = _cfg_int("RUN_JOBS_MAX", 200)
configure_run_jobs(_RUN_JOBS_MAX)
_RUN_POSTMAN_JOB_FN = partial(
    _job_run_postman_job,
    set_run_job=set_run_job,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)

_UPDATE_REPORT_META_FN = partial(
    _svc_update_report_meta,
    reports_dir=REPORTS_DIR,
    get_report_write_lock=get_report_write_lock,
    find_report=_repo_find_report,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)


@app.before_request
def _capture_request_start() -> None:
    request.environ["_request_start_at"] = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    request.environ["_request_id"] = request_id


@app.after_request
def _log_access(response: Response) -> Response:
    started_at = request.environ.get("_request_start_at")
    duration_ms = 0
    if isinstance(started_at, (int, float)):
        duration_ms = round((time.perf_counter() - started_at) * 1000)

    request_id = str(request.environ.get("_request_id") or "")
    extra_payload = {
        "event": "http.access.logged",
        "request_id": request_id,
        "method": request.method,
        "path": request.path,
        "status_code": int(response.status_code),
        "duration_ms": duration_ms,
        "remote_addr": request.remote_addr or "",
    }
    if request.user_agent and request.user_agent.string:
        extra_payload["user_agent"] = request.user_agent.string

    level = logging.WARNING if response.status_code >= 500 else logging.INFO
    sample_rate = 1.0 if response.status_code >= 400 else ACCESS_LOG_SAMPLE_RATE
    log_sampled(
        logger,
        level,
        "http_request",
        sample_rate=sample_rate,
        extra=extra_payload,
    )
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return response


@app.route("/health")
def health() -> ResponseReturnValue:
    """健康检查端点，用于监控系统存活状态。"""
    return jsonify(
        build_health_payload(
            datetime.now().isoformat(),
            log_alert=get_log_alert_snapshot(),
        )
    )


@app.route("/api/log-metrics")
def log_metrics() -> ResponseReturnValue:
    """日志聚合指标（内存计数快照）。"""
    return jsonify(get_log_metrics_snapshot())


@app.route("/")
def index() -> ResponseReturnValue:
    reports = _repo_list_reports()
    port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
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


@app.route("/adhoc-run")
def adhoc_run_page() -> ResponseReturnValue:
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


@app.route("/report-view")
def report_view() -> ResponseReturnValue:
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
    except Exception:
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
    )
    response = make_response(html)
    # 避免浏览器缓存旧版页面，确保模板改动即时生效。
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/reports/<path:filename>")
def serve_report(filename: str) -> ResponseReturnValue:
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/exports/<path:filename>")
def serve_export(filename: str) -> ResponseReturnValue:
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)


@app.route("/api/reports")
def api_reports() -> ResponseReturnValue:
    return jsonify(_repo_list_reports())


@app.route("/api/collection-preview", methods=["POST"])
def api_collection_preview() -> ResponseReturnValue:
    if not ENABLE_SELECTIVE_RUN:
        return _json_error("当前环境未启用接口选择执行功能。", 403)

    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return _json_error("请上传有效的 Postman JSON 文件", 400)

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return _json_error("上传文件必须是 .json 格式", 400)

    try:
        collection_data = json.load(collection_file.stream)
    except Exception as exc:
        return _json_error(f"JSON 解析失败: {exc}", 400)

    preview_items = _svc_extract_collection_preview_items(collection_data, COLLECTION_PREVIEW_MAX_ITEMS)
    total = len(preview_items)
    truncated = False
    if total >= COLLECTION_PREVIEW_MAX_ITEMS:
        truncated = True

    return jsonify(
        build_collection_preview_payload(
            file_name=original_name,
            total=total,
            truncated=truncated,
            max_items=COLLECTION_PREVIEW_MAX_ITEMS,
            items=preview_items,
        )
    )


@app.route("/api/export-collection", methods=["POST"])
def api_export_collection() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    include_auth = _to_bool(payload.get("include_auth"), default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT)
    export_scope = str(payload.get("export_scope", REPORT_EXPORT_DEFAULT_SCOPE)).strip().lower() or REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope not in {"full", "report_only"}:
        export_scope = REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope == "report_only" and not REPORT_EXPORT_ALLOW_REPORT_ONLY:
        export_scope = "full"
    if not report_name:
        return _json_error("report_name 不能为空", 400)

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    try:
        exported = _svc_export_collection_with_latest_params(
            report,
            exports_dir=EXPORTS_DIR,
            collection_preview_max_items=COLLECTION_PREVIEW_MAX_ITEMS,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            manual_case_folder_name=MANUAL_CASE_FOLDER_NAME,
            report_export_allow_report_only=REPORT_EXPORT_ALLOW_REPORT_ONLY,
            include_auth=include_auth,
            export_scope=export_scope,
        )
    except Exception as exc:
        return _json_error(str(exc), 400)

    return jsonify(
        build_export_collection_payload(
            report_name=report_name,
            exported=exported,
            include_auth=include_auth,
        )
    )


@app.route("/api/export-collection-stream", methods=["POST"])
def api_export_collection_stream() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    include_auth = _to_bool(payload.get("include_auth"), default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT)
    export_scope = str(payload.get("export_scope", REPORT_EXPORT_DEFAULT_SCOPE)).strip().lower() or REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope not in {"full", "report_only"}:
        export_scope = REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope == "report_only" and not REPORT_EXPORT_ALLOW_REPORT_ONLY:
        export_scope = "full"
    if not report_name:
        return _json_error("report_name 不能为空", 400)

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    try:
        exported = _svc_export_collection_with_latest_params(
            report,
            exports_dir=EXPORTS_DIR,
            collection_preview_max_items=COLLECTION_PREVIEW_MAX_ITEMS,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            manual_case_folder_name=MANUAL_CASE_FOLDER_NAME,
            report_export_allow_report_only=REPORT_EXPORT_ALLOW_REPORT_ONLY,
            include_auth=include_auth,
            export_scope=export_scope,
        )
    except Exception as exc:
        return _json_error(str(exc), 400)

    export_path = Path(str(exported.get("file_path") or ""))
    if not export_path.exists():
        return _json_error("导出文件不存在，无法进行流式下载", 500)

    def generate_chunks() -> Iterator[bytes]:
        with export_path.open("rb") as file:
            while True:
                chunk = file.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    response = Response(stream_with_context(generate_chunks()), mimetype="application/json")
    response.headers["Content-Disposition"] = f"attachment; filename={exported['file_name']}"
    response.headers["X-Export-Scope"] = str(exported.get("export_scope") or "full")
    return response


@app.route("/api/report-meta/<path:report_name>")
def api_report_detail(report_name: str) -> ResponseReturnValue:
    try:
        return jsonify(build_report_meta_payload(_repo_find_report(report_name)))
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)


@app.route("/api/manual-cases/<path:report_name>")
def api_manual_cases(report_name: str) -> ResponseReturnValue:
    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    payload = _manual_list_manual_cases(
        report_name=report_name,
        report=report,
        default_folder=MANUAL_CASE_FOLDER_NAME,
        enabled=ENABLE_MANUAL_CASES,
    )
    return jsonify(payload)


@app.route("/api/manual-cases/add", methods=["POST"])
def api_manual_case_add() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    case_payload = dict(payload.get("case") or {})
    if not case_payload:
        return _json_error("case 不能为空", 400)
    try:
        result = _manual_add_manual_case(
            report_name=report_name,
            payload=case_payload,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            default_folder_name=MANUAL_CASE_FOLDER_NAME,
            normalize_manual_case=_normalize_manual_case,
            update_report_meta=_UPDATE_REPORT_META_FN,
            create_id=lambda: uuid.uuid4().hex,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_manual_case_upsert_payload(report_name=report_name, result=result))


@app.route("/api/manual-cases/update", methods=["PUT"])
def api_manual_case_update() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    case_payload = dict(payload.get("case") or {})
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    if not case_id:
        return _json_error("case_id 不能为空", 400)
    try:
        result = _manual_update_manual_case(
            report_name=report_name,
            case_id=case_id,
            payload=case_payload,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            default_folder_name=MANUAL_CASE_FOLDER_NAME,
            normalize_manual_case=_normalize_manual_case,
            update_report_meta=_UPDATE_REPORT_META_FN,
        )
    except FileNotFoundError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_manual_case_upsert_payload(report_name=report_name, result=result))


@app.route("/api/manual-cases/delete", methods=["DELETE"])
def api_manual_case_delete() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    if not case_id:
        return _json_error("case_id 不能为空", 400)
    try:
        result = _manual_delete_manual_case(
            report_name=report_name,
            case_id=case_id,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            manual_case_exclusion_key=_manual_case_exclusion_key,
            normalize_manual_exclusions=_normalize_manual_exclusions,
            update_report_meta=_UPDATE_REPORT_META_FN,
        )
    except FileNotFoundError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_manual_case_delete_payload(report_name=report_name, result=result))


@app.route("/api/report-case-exclusion", methods=["POST"])
def api_report_case_exclusion() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    exclusion_key = str(payload.get("exclusion_key") or "").strip()
    excluded = _to_bool(payload.get("excluded"), default=True)
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    if not exclusion_key:
        return _json_error("exclusion_key 不能为空", 400)
    try:
        result = _manual_set_case_exclusion(
            report_name=report_name,
            exclusion_key=exclusion_key,
            excluded=excluded,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_manual_exclusions,
            update_report_meta=_UPDATE_REPORT_META_FN,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_case_exclusion_payload(report_name=report_name, excluded=excluded, result=result))


@app.route("/api/report-result-judgement", methods=["POST"])
def api_report_result_judgement() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400)

    raw_result_index = payload.get("result_index")
    if raw_result_index is None:
        return _json_error("result_index 必须是整数", 400)
    try:
        result_index = int(str(raw_result_index))
    except (TypeError, ValueError):
        return _json_error("result_index 必须是整数", 400)

    action = str(payload.get("action") or "override").strip().lower()
    target_status = str(payload.get("target_status") or "").strip().upper() or None
    reason = str(payload.get("reason") or "").strip()

    try:
        result = _svc_set_report_result_judgement(
            report_name=report_name,
            result_index=result_index,
            action=action,
            target_status=target_status,
            reason=reason,
            reports_dir=REPORTS_DIR,
            get_report_write_lock=get_report_write_lock,
            find_report=_repo_find_report,
            compute_summary=_utils_compute_summary,
            invalidate_reports_cache=_repo_invalidate_reports_cache,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    except IndexError:
        return _json_error(f"结果索引不存在: {result_index}", 404)
    except Exception as exc:
        return _json_error(str(exc), 400)

    return jsonify(
        build_result_judgement_payload(
            report_name=report_name,
            result_index=result_index,
            action=action,
            result=result,
        )
    )


# ---------------------------------------------------------------
# 升级二：一键重试失败用例
# ---------------------------------------------------------------
@app.route("/api/retry-failures", methods=["POST"])
def api_retry_failures() -> ResponseReturnValue:
    if not ENABLE_RETRY_FAILURES:
        return _json_error("当前环境未启用重试失败接口能力。", 403)

    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    if not report_name:
        return _json_error("缺少 report_name", 400)

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    failed_paths, source_runtime_ctx, source_runtime_error = _job_prepare_retry_job_context(
        payload=payload,
        report=report,
        retry_mode="failures",
        output_dir=str(REPORTS_DIR),
        default_results_per_page=RUN_RESULTS_PER_PAGE_DEFAULT,
        clamp_run_results_per_page=clamp_run_results_per_page,
    )

    if not failed_paths:
        return _json_error("当前报告无失败或错误接口，无需重试。", 400)

    if source_runtime_error:
        return _json_error(source_runtime_error, 400)
    assert source_runtime_ctx is not None
    saved_file = str(source_runtime_ctx["saved_file"])
    runtime = source_runtime_ctx["runtime"]

    job_id = _job_enqueue_retry_job(
        saved_file=saved_file,
        runtime=runtime,
        selected_paths=failed_paths,
        queued_message="重试任务已入队，等待执行。",
        set_run_job=set_run_job,
        run_postman_job_fn=_RUN_POSTMAN_JOB_FN,
    )

    return jsonify(
        build_retry_queued_payload(
            job_id=job_id,
            retry_count=len(failed_paths),
            message=f"已创建重试任务，共 {len(failed_paths)} 个失败接口，请轮询状态接口获取进度。",
        )
    )


@app.route("/api/retry-all", methods=["POST"])
def api_retry_all() -> ResponseReturnValue:
    if not ENABLE_RETRY_FAILURES:
        return _json_error("当前环境未启用重试接口能力。", 403)

    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    if not report_name:
        return _json_error("缺少 report_name", 400)

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    all_paths, source_runtime_ctx, source_runtime_error = _job_prepare_retry_job_context(
        payload=payload,
        report=report,
        retry_mode="all",
        output_dir=str(REPORTS_DIR),
        default_results_per_page=RUN_RESULTS_PER_PAGE_DEFAULT,
        clamp_run_results_per_page=clamp_run_results_per_page,
    )

    if not all_paths:
        return _json_error("当前报告没有可重试的接口。", 400)

    if source_runtime_error:
        return _json_error(source_runtime_error, 400)
    assert source_runtime_ctx is not None
    saved_file = str(source_runtime_ctx["saved_file"])
    runtime = source_runtime_ctx["runtime"]

    job_id = _job_enqueue_retry_job(
        saved_file=saved_file,
        runtime=runtime,
        selected_paths=all_paths,
        queued_message="全量重试任务已入队，等待执行。",
        set_run_job=set_run_job,
        run_postman_job_fn=_RUN_POSTMAN_JOB_FN,
    )

    return jsonify(
        build_retry_queued_payload(
            job_id=job_id,
            retry_count=len(all_paths),
            message=f"已创建全量重试任务，共 {len(all_paths)} 个接口，请轮询状态接口获取进度。",
        )
    )


# ---------------------------------------------------------------
# 升级七：JUnit XML 报告导出
# ---------------------------------------------------------------
@app.route("/api/export-junit/<path:report_name>")
def api_export_junit(report_name: str) -> ResponseReturnValue:
    if not ENABLE_JUNIT_EXPORT:
        return _json_error("当前环境未启用 JUnit XML 导出能力。", 403)

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    try:
        xml_content = _svc_build_junit_xml(report)
    except Exception as exc:
        logger.exception("JUnit XML 生成失败: %s", exc)
        return _json_error("JUnit XML 生成失败", 500)

    safe_stem = re.sub(r'[^\w\u4e00-\u9fff\-.]', '_', Path(report_name).stem)[:80]
    filename = f"{safe_stem}_junit.xml"
    resp = make_response(xml_content)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ---------------------------------------------------------------
# 升级四：多环境配置查询
# ---------------------------------------------------------------
@app.route("/api/environments")
def api_environments() -> ResponseReturnValue:
    """返回可用环境列表（不含 token 值）。"""
    env_list = []
    for env_name, env_cfg in ENVIRONMENTS.items():
        if not isinstance(env_cfg, dict):
            continue
        env_list.append({
            "name": str(env_name),
            "base_url": str(env_cfg.get("base_url", "")),
            "has_token": bool(env_cfg.get("token", "").strip()),
        })
    return jsonify(build_environments_payload(env_list=env_list, default_env_name=DEFAULT_ENV_NAME))


@app.route("/api/report-delete/<path:report_name>", methods=["DELETE"])
def api_report_delete(report_name: str) -> ResponseReturnValue:
    try:
        deleted_files = _admin_delete_report_artifacts(
            report_name,
            find_report=_repo_find_report,
            collect_report_artifacts=collect_report_artifacts,
            invalidate_reports_cache=_repo_invalidate_reports_cache,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    logger.info("删除报告产物成功: report=%s files=%s", report_name, deleted_files)
    return jsonify(build_report_delete_payload(report_name=report_name, deleted_files=deleted_files))


@app.route("/api/report-results/<path:report_name>")
def api_report_results(report_name: str) -> ResponseReturnValue:
    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    page = clamp_page(request.args.get("page", 1))
    page_size = clamp_page_size(request.args.get("page_size", REPORT_VIEW_PAGE_SIZE_DEFAULT))
    keyword = request.args.get("query", "")
    message_keyword = request.args.get("message_query", "")
    err_code_keyword = request.args.get("err_code_query", "")
    status_filter = _report_normalize_status_filter(request.args.get("status", "all"))
    include_excluded = _to_bool(request.args.get("include_excluded"), default=True)
    payload = _report_build_report_results_payload(
        report=report,
        page=page,
        page_size=page_size,
        keyword=keyword,
        message_keyword=message_keyword,
        err_code_keyword=err_code_keyword,
        status_filter=status_filter,
        include_excluded=include_excluded,
    )
    return jsonify(payload)


@app.route("/api/report-result-detail/<path:report_name>/<int:result_index>")
def api_report_result_detail(report_name: str, result_index: int) -> ResponseReturnValue:
    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    try:
        return jsonify(build_result_detail_payload(report, result_index))
    except IndexError:
        return _json_error(f"结果索引不存在: {result_index}", 404)


@app.route("/api/compare")
def api_compare() -> ResponseReturnValue:
    left_name = request.args.get("left", "")
    right_name = request.args.get("right", "")
    if not left_name or not right_name:
        return _json_error("left 和 right 参数不能为空", 400)
    try:
        left = _repo_find_report(left_name)
        right = _repo_find_report(right_name)
    except FileNotFoundError as exc:
        return _json_error(f"报告不存在: {exc}", 404)
    return jsonify(build_compare_payload(left, right))


@app.route("/test-token", methods=["POST"])
def test_token() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", "")).strip()
    if not token:
        return jsonify(build_test_token_payload(success=False, message="token 不能为空")), 400
    return jsonify(build_test_token_payload(success=True, message="token 格式有效，可用于后续请求"))


@app.route("/re-request-api", methods=["POST"])
def re_request_api() -> ResponseReturnValue:
    is_multipart, payload, source = _svc_resolve_request_payload_source(
        content_type=request.content_type,
        json_payload=request.get_json(silent=True),
        request_meta_raw=request.form.get("request_meta"),
    )
    request_fields = _svc_extract_http_request_fields(source, payload)
    url = request_fields["url"]
    method = request_fields["method"]
    headers = request_fields["headers"]
    params = request_fields["params"]
    body_mode = request_fields["body_mode"]
    body_data = request_fields["body_data"]
    legacy_body = request_fields["legacy_body"]
    token = str(source.get("token", "")).strip()
    save_to_report = bool(source.get("save_to_report", False))
    rpt_name = str(source.get("report_name", "")).strip()
    rpt_index = _svc_parse_optional_int(source.get("result_index"))
    expected_status = _svc_parse_int_default(source.get("expected_status") or 200, 200)

    if not url:
        return _json_error("url 不能为空", 400)
    if not _svc_is_valid_http_url(url):
        return _json_error("url 仅允许合法的 http/https 地址", 400)

    # 处理 token：转换为 headers
    headers = _svc_inject_token_header(headers, token)

    # 使用统一的 HTTP 请求执行 helper
    exec_result = _http_execute_http_request(
        url=url,
        method=method,
        headers=headers,
        params=params,
        body_mode=body_mode,
        body_data=body_data,
        legacy_body=legacy_body,
        is_multipart=is_multipart,
        files_source=request.files,
    )

    if not exec_result["success"]:
        # 请求执行失败
        normalized_url, normalized_params = _normalize_url_and_params(url, params)
        return jsonify(
            build_re_request_error_payload(
                source=source,
                url=url,
                method=method,
                normalized_url=normalized_url,
                actual_request_url=_merge_url_with_params(normalized_url, normalized_params),
                message=exec_result["error_message"],
                headers_to_send={},
                normalized_params=normalized_params,
                stored_body=None,
                stored_body_mode="legacy",
                stored_body_data=None,
            )
        )

    # 请求执行成功，处理响应
    response_body = exec_result["response_body"]
    response_message, err_code = _utils_extract_msg_errcode(response_body)
    status_code_ok = exec_result["status_code"] == expected_status
    normalized_msg = str(response_message or "").strip().lower()
    message_ok = normalized_msg == "" or normalized_msg == "success"

    if status_code_ok and message_ok:
        result_status = "PASSED"
        result_message = response_message
    else:
        result_status = "FAILED"
        if not status_code_ok:
            result_message = f"状态码不匹配: 期望 {expected_status}, 实际 {exec_result['status_code']}; message: {response_message}"
        else:
            result_message = f"message 校验未通过(期望为空或 success), 实际为: {response_message}"

    new_request_info = {
        "headers": exec_result["headers_to_send"],
        "params": exec_result["normalized_params"],
        "body": exec_result["stored_body"],
        "body_mode": exec_result["stored_body_mode"],
        "body_data": exec_result["stored_body_data"],
    }
    new_response_info = {"headers": exec_result["response_headers"], "body": response_body}

    result_fields = {
        "method": method,
        "url": exec_result["normalized_url"],
        "actual_request_url": exec_result["actual_request_url"],
        "item_path": source.get("item_path", []),
        "expected_status": expected_status,
        "status": result_status,
        "status_code": exec_result["status_code"],
        "message": result_message,
        "err_code": err_code,
    }

    new_summary: SummaryPayload = {}
    if save_to_report and rpt_name and rpt_index is not None:
        new_summary = _patch_report_result(
            rpt_name,
            rpt_index,
            result_fields,
            new_request_info,
            new_response_info,
            reports_dir=REPORTS_DIR,
            get_report_write_lock=get_report_write_lock,
            find_report=_repo_find_report,
            compute_summary=_utils_compute_summary,
            invalidate_reports_cache=_repo_invalidate_reports_cache,
        )

    return jsonify(
        build_re_request_success_payload(
            source=source,
            method=method,
            normalized_url=exec_result["normalized_url"],
            actual_request_url=exec_result["actual_request_url"],
            result_fields=result_fields,
            new_request_info=new_request_info,
            new_response_info=new_response_info,
            new_summary=new_summary,
        )
    )


@app.route("/api/proxy-request", methods=["POST"])
def api_proxy_request() -> ResponseReturnValue:
    """代理执行 HTTP 请求，供人工用例「发送」功能调用。仅允许 http/https。"""
    is_multipart, payload, source = _svc_resolve_request_payload_source(
        content_type=request.content_type,
        json_payload=request.get_json(silent=True),
        request_meta_raw=request.form.get("request_meta"),
    )
    request_fields = _svc_extract_http_request_fields(source, payload)
    url = request_fields["url"]
    method = request_fields["method"]
    req_headers = request_fields["headers"]
    req_params = request_fields["params"]
    body_mode = request_fields["body_mode"]
    body_data = request_fields["body_data"]
    legacy_body = request_fields["legacy_body"]

    if not url:
        return _json_error("url 不能为空", 400)

    # 使用统一的 HTTP 请求执行 helper
    exec_result = _http_execute_http_request(
        url=url,
        method=method,
        headers=req_headers,
        params=req_params,
        body_mode=body_mode,
        body_data=body_data,
        legacy_body=legacy_body,
        is_multipart=is_multipart,
        files_source=request.files,
    )

    if not exec_result["success"]:
        # 请求执行失败
        return _json_error(exec_result["error_message"], exec_result.get("error_code", 502))

    # 请求执行成功，返回响应
    return jsonify(
        build_proxy_response_payload(
            status_code=exec_result["status_code"],
            elapsed_ms=exec_result["elapsed_ms"],
            response_headers=exec_result["response_headers"],
            response_body=exec_result["response_body"],
        )
    )


@app.route("/api/run-postman", methods=["POST"])
def api_run_postman() -> ResponseReturnValue:
    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return _json_error("请上传有效的 Postman JSON 文件", 400)

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return _json_error("上传文件必须是 .json 格式", 400)

    original_name = _sanitize_uploaded_name(original_name)

    base_url = str(request.form.get("base_url", "")).strip() or None
    # 严格校验 base_url，仅允许 http/https，阻断 SSRF 风险
    if base_url is not None and not _svc_is_valid_http_url(base_url):
        return _json_error("base_url 仅允许合法的 http/https 地址", 400)
    token = str(request.form.get("token", "")).strip() or None
    # 升级四：如果传入 env_name 且环境存在，用环境配置填充未指定的 base_url / token
    env_name = str(request.form.get("env_name", "")).strip()
    if env_name and env_name in ENVIRONMENTS:
        env_cfg = ENVIRONMENTS[env_name]
        if isinstance(env_cfg, dict):
            if not base_url and env_cfg.get("base_url", "").strip():
                env_base = env_cfg["base_url"].strip()
                if _svc_is_valid_http_url(env_base):
                    base_url = env_base
            if not token and env_cfg.get("token", "").strip():
                token = env_cfg["token"].strip()
    output_dir = str(request.form.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(request.form.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(request.form.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    run_scope = str(request.form.get("run_scope", "all")).strip().lower() or "all"
    raw_selected_paths = request.form.get("selected_item_paths", "")
    selected_item_paths: List[List[int]] = []
    if ENABLE_SELECTIVE_RUN and run_scope == "selected":
        try:
            selected_item_paths = _svc_parse_selected_item_paths(raw_selected_paths)
        except ValueError as exc:
            return _json_error(str(exc), 400)
        if not selected_item_paths:
            return _json_error("选择了仅执行已选接口，但未提供有效 selected_item_paths", 400)

    suffix = Path(original_name).suffix or ".json"
    job_id = uuid.uuid4().hex
    saved_file = _build_saved_json_path(UPLOADS_DIR, job_id, suffix)
    collection_file.save(str(saved_file))
    job_params: JobParams = _build_run_postman_job_params(
        job_id=job_id,
        original_name=original_name,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name,
        base_url=base_url,
        token=token,
        selected_item_paths=selected_item_paths if selected_item_paths else None,
    )
    
    _enqueue_job(
        job_id=job_id,
        saved_file=str(saved_file),
        job_params=job_params,
        results_per_page=results_per_page,
        selected_item_paths=selected_item_paths if selected_item_paths else None,
    )

    return jsonify(build_job_queued_payload(job_id=job_id, message="任务已创建，请轮询状态接口获取执行进度。"))


@app.route("/api/run-ad-hoc-tests", methods=["POST"])
def api_run_ad_hoc_tests() -> ResponseReturnValue:
    if not ENABLE_ADHOC_RUN:
        return _json_error("当前环境未启用直接新增接口测试能力。", 403)

    payload = request.get_json(silent=True) or {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        return _json_error("cases 不能为空，且必须是数组。", 400)
    if len(raw_cases) > ADHOC_MAX_ITEMS:
        return _json_error(f"单次最多支持 {ADHOC_MAX_ITEMS} 条接口。", 400)

    base_url = str(payload.get("base_url", "")).strip() or None
    if base_url is not None and not _svc_is_valid_http_url(base_url):
        return _json_error("base_url 仅允许合法的 http/https 地址", 400)

    token = str(payload.get("token", "")).strip() or None
    output_dir = str(payload.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(payload.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(payload.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    collection_name = str(payload.get("collection_name", "")).strip() or ADHOC_DEFAULT_COLLECTION_NAME

    try:
        normalized_cases = [_svc_normalize_adhoc_case(item, idx, base_url) for idx, item in enumerate(raw_cases)]
        collection_data = _svc_build_adhoc_collection(normalized_cases, collection_name, base_url)
    except ValueError as exc:
        return _json_error(str(exc), 400)

    job_id = uuid.uuid4().hex
    saved_file = _build_saved_json_path(UPLOADS_DIR, job_id)
    with saved_file.open("w", encoding="utf-8") as f:
        json.dump(collection_data, f, indent=2, ensure_ascii=False)

    source_original_file = _sanitize_uploaded_name(f"{collection_name}.json")
    job_params: JobParams = _build_ad_hoc_job_params(
        job_id=job_id,
        source_original_file=source_original_file,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name,
        base_url=base_url,
        token=token,
    )
    job_params["collection_name"] = collection_name
    
    _enqueue_job(
        job_id=job_id,
        saved_file=str(saved_file),
        job_params=job_params,
        results_per_page=results_per_page,
        selected_item_paths=None,
    )

    return jsonify(build_job_queued_payload(job_id=job_id, message="ad-hoc 任务已创建，请轮询状态接口获取执行进度。"))


@app.route("/api/run-postman-status/<path:job_id>")
def api_run_postman_status(job_id: str) -> ResponseReturnValue:
    job = get_run_job(job_id)
    if not job:
        return _json_error("任务不存在。", 404)
    return jsonify(job)


@app.route("/latest")
def latest_report() -> ResponseReturnValue:
    reports = _repo_list_reports()
    if not reports:
        return redirect(url_for("index"))
    return redirect(url_for("report_view", name=reports[0]["report_name"]))


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
    host = os.environ.get("REPORT_SERVER_HOST", "0.0.0.0")
    print(f"报告目录: {REPORTS_DIR}")
    logger.info("报告服务启动: http://127.0.0.1:%d", port)
    logger.info("局域网访问地址: http://%s:%d", get_local_ip(), port)
    try:
        from waitress import serve
        logger.info("使用 waitress WSGI 服务器（生产模式）")
        serve(app, host=host, port=port)
    except ImportError:
        logger.warning("waitress 未安装，降级使用 Flask 开发服务器（建议 pip install waitress）")
        app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()


