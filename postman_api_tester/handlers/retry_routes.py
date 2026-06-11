"""重试失败用例与全量重试路由处理函数。"""

from functools import partial
from typing import SupportsInt

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error
from postman_api_tester.services.report_job_execution_service import (
    enqueue_retry_job as _job_enqueue_retry_job,
    prepare_retry_job_context as _job_prepare_retry_job_context,
    run_postman_job as _job_run_postman_job,
)
from postman_api_tester.report_job_store import set_run_job
from postman_api_tester.report_server_config import (
    ENABLE_RETRY_FAILURES,
    RUN_RESULTS_PER_PAGE_DEFAULT,
    RUN_RESULTS_PER_PAGE_MAX,
    RUN_RESULTS_PER_PAGE_MIN,
)
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_repository import (
    find_report as _repo_find_report,
    invalidate_reports_cache as _repo_invalidate_reports_cache,
)
from postman_api_tester.services.report_results_service import build_retry_queued_payload
from postman_api_tester.utils.server_utils import clamp_page_size as _clamp_page_size

REPORTS_DIR = ReportServerApp._resolve_reports_dir()

_RUN_POSTMAN_JOB_FN = partial(
    _job_run_postman_job,
    set_run_job=set_run_job,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)


def clamp_run_results_per_page(value: SupportsInt | str | bytes | bytearray | None) -> int:
    return _clamp_page_size(
        value,
        default=RUN_RESULTS_PER_PAGE_DEFAULT,
        min_size=RUN_RESULTS_PER_PAGE_MIN,
        max_size=RUN_RESULTS_PER_PAGE_MAX,
    )


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
