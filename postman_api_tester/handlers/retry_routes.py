"""重试失败用例与全量重试路由处理函数。"""

from functools import partial
from typing import Any, Dict, Optional, Tuple

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import (
    get_report_or_error,
    json_error as _json_error,
)
from postman_api_tester.services.report_job_execution_service import (
    enqueue_retry_job as _job_enqueue_retry_job,
    prepare_retry_job_context as _job_prepare_retry_job_context,
    run_postman_job as _job_run_postman_job,
)
from postman_api_tester.report_job_store import set_run_job
from postman_api_tester.report_server_config import (
    ENABLE_RETRY_FAILURES,
    RUN_RESULTS_PER_PAGE_DEFAULT,
)
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_repository import (
    invalidate_reports_cache as _repo_invalidate_reports_cache,
)
from postman_api_tester.services.report_results_service import build_retry_queued_payload
from postman_api_tester.handlers.job_routes import clamp_run_results_per_page

REPORTS_DIR = ReportServerApp._resolve_reports_dir()

_RUN_POSTMAN_JOB_FN = partial(
    _job_run_postman_job,
    set_run_job=set_run_job,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)

_RETRY_ERROR_CODES: Dict[str, Dict[str, Tuple[str, int, str]]] = {
    "failures": {
        "disabled": ("当前环境未启用重试失败接口能力。", 403, "RPT_RETRY_001"),
        "missing_name": ("缺少 report_name", 400, "RPT_RETRY_002"),
        "no_paths": ("当前报告无失败或错误接口，无需重试。", 400, "RPT_RETRY_004"),
    },
    "all": {
        "disabled": ("当前环境未启用重试接口能力。", 403, "RPT_RETRY_006"),
        "missing_name": ("缺少 report_name", 400, "RPT_RETRY_007"),
        "no_paths": ("当前报告没有可重试的接口。", 400, "RPT_RETRY_009"),
    },
}

_RETRY_REPORT_ERROR_CODE = {"failures": "RPT_RETRY_003", "all": "RPT_RETRY_008"}
_RETRY_RUNTIME_ERROR_CODE = {"failures": "RPT_RETRY_005", "all": "RPT_RETRY_010"}
_RETRY_QUEUED_MESSAGE = {"failures": "重试任务已入队，等待执行。", "all": "全量重试任务已入队，等待执行。"}


def _dispatch_retry(retry_mode: str) -> ResponseReturnValue:
    """重试任务分发：统一 failures / all 两种模式的预检 + 入队流程。"""
    codes = _RETRY_ERROR_CODES[retry_mode]

    if not ENABLE_RETRY_FAILURES:
        msg, status, code = codes["disabled"]
        return _json_error(msg, status, code)

    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    if not report_name:
        msg, status, code = codes["missing_name"]
        return _json_error(msg, status, code)

    report = get_report_or_error(report_name, _RETRY_REPORT_ERROR_CODE[retry_mode])
    if isinstance(report, tuple):
        return report

    paths, source_runtime_ctx, source_runtime_error = _job_prepare_retry_job_context(
        payload=payload,
        report=report,
        retry_mode=retry_mode,
        output_dir=str(REPORTS_DIR),
        default_results_per_page=RUN_RESULTS_PER_PAGE_DEFAULT,
        clamp_run_results_per_page=clamp_run_results_per_page,
    )

    if not paths:
        msg, status, code = codes["no_paths"]
        return _json_error(msg, status, code)

    if source_runtime_error:
        return _json_error(source_runtime_error, 400, _RETRY_RUNTIME_ERROR_CODE[retry_mode])
    assert source_runtime_ctx is not None
    saved_file = str(source_runtime_ctx["saved_file"])
    runtime = source_runtime_ctx["runtime"]

    job_id = _job_enqueue_retry_job(
        saved_file=saved_file,
        runtime=runtime,
        selected_paths=paths,
        queued_message=_RETRY_QUEUED_MESSAGE[retry_mode],
        set_run_job=set_run_job,
        run_postman_job_fn=_RUN_POSTMAN_JOB_FN,
    )

    count = len(paths)
    label = "失败接口" if retry_mode == "failures" else "接口"
    return jsonify(
        build_retry_queued_payload(
            job_id=job_id,
            retry_count=count,
            message=f"已创建{'全量' if retry_mode == 'all' else ''}重试任务，共 {count} 个{label}，请轮询状态接口获取进度。",
        )
    )


def api_retry_failures() -> ResponseReturnValue:
    """重试失败接口 API。错误码：RPT_RETRY_001-005"""
    return _dispatch_retry("failures")


def api_retry_all() -> ResponseReturnValue:
    """全量重试 API。错误码：RPT_RETRY_006-010"""
    return _dispatch_retry("all")
