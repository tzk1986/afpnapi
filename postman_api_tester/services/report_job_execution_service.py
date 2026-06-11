"""开发导读：
- 职责：执行任务线程编排与重试任务上下文构建。
- 入口：run_postman_job()、enqueue_job_with_worker()、prepare_retry_job_context()。
- 关系：调用主执行器并负责运行态日志/状态字段拼装。
"""

import os
import threading
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from postman_api_tester.services.report_retry_service import (
    build_retry_job_plan,
    build_retry_source_runtime_context,
    collect_all_item_paths,
    collect_failed_item_paths,
)
from postman_api_tester.utils.logging_utils import get_log_sample_rate, log_sampled


logger = logging.getLogger(__name__)
PROGRESS_LOG_SAMPLE_RATE = get_log_sample_rate(default=0.1)


def _safe_run_job(
    fn: Callable[..., None],
    args: tuple,
    job_id: str,
    set_run_job: Callable[..., None],
    kwargs: Optional[Dict[str, Any]] = None,
) -> None:
    """包装线程目标函数，捕获未处理异常并更新任务状态为 ERROR。"""
    try:
        fn(*args, **(kwargs or {}))
    except Exception as exc:
        logger.exception("job thread unhandled exception", extra={"job_id": job_id})
        try:
            set_run_job(job_id, status="error", message=f"任务异常退出: {exc}")
        except Exception:
            pass


def run_postman_job(
    job_id: str,
    postman_file: str,
    base_url: Optional[str],
    output_dir: str,
    token: Optional[str],
    report_name: Optional[str],
    source_original_file: Optional[str],
    results_per_page: int,
    selected_item_paths: Optional[List[List[int]]],
    *,
    set_run_job: Callable[..., None],
    invalidate_reports_cache: Callable[[], None],
    judgment_config: Optional[Dict[str, Any]] = None,
) -> None:
    """执行 Postman 测试任务，包含进度追踪与异常处理。"""
    logger.info(
        "job started",
        extra={
            "event": "job.run.started",
            "job_id": job_id,
            "postman_file": postman_file,
            "report_name": str(report_name or ""),
            "selected_count": len(selected_item_paths or []),
        },
    )
    set_run_job(job_id, status="running", message="任务正在执行中...")
    try:
        from postman_api_tester.postman_api_tester import run_postman_tests

        def on_progress(progress: Dict[str, Any]) -> None:
            total = int(progress.get("total") or 0)
            completed = int(progress.get("completed") or 0)
            percent = int(progress.get("percent") or 0)
            current_name = str(progress.get("current_name") or "")
            current_method = str(progress.get("current_method") or "")
            current_url = str(progress.get("current_url") or "")

            message = "任务正在执行中..."
            if total > 0:
                message = f"任务正在执行中: {completed}/{total} ({percent}%)"
                if current_name:
                    message = f"{message}，当前接口: {current_name}"

            set_run_job(
                job_id,
                status="running",
                message=message,
                total=total,
                completed=completed,
                percent=percent,
                current_name=current_name,
                current_method=current_method,
                current_url=current_url,
                last_status=str(progress.get("last_status") or ""),
            )
            log_sampled(
                logger,
                logging.INFO,
                "job progress",
                sample_rate=PROGRESS_LOG_SAMPLE_RATE,
                extra={
                    "event": "job.run.progress",
                    "job_id": job_id,
                    "completed": completed,
                    "total": total,
                    "percent": percent,
                    "current_name": current_name,
                    "last_status": str(progress.get("last_status") or ""),
                },
            )

        report = run_postman_tests(
            postman_file=postman_file,
            base_url=base_url,
            output_dir=output_dir,
            token=token,
            report_name=report_name,
            source_original_file=source_original_file,
            results_per_page=results_per_page,
            selected_item_paths=selected_item_paths,
            progress_callback=on_progress,
            judgment_config=judgment_config,
        )
        set_run_job(
            job_id,
            status="success",
            message="执行完成，正在刷新报告索引。",
            report_name=os.path.basename(str(report.generated_report_file or "")),
            report_meta_name=os.path.basename(str(report.generated_meta_file or "")),
        )
        logger.info(
            "job completed",
            extra={
                "event": "job.run.completed",
                "job_id": job_id,
                "report_name": os.path.basename(str(report.generated_report_file or "")),
                "meta_name": os.path.basename(str(report.generated_meta_file or "")),
            },
        )
        invalidate_reports_cache()
    except Exception as exc:
        logger.exception(
            "job failed",
            extra={
                "event": "job.run.failed",
                "job_id": job_id,
            },
        )
        set_run_job(job_id, status="failed", message=str(exc))


def enqueue_retry_job(
    saved_file: str,
    runtime: Dict[str, Any],
    selected_paths: List[List[int]],
    queued_message: str,
    *,
    set_run_job: Callable[..., None],
    run_postman_job_fn: Callable[..., None],
) -> str:
    """构建重试任务计划并启动执行线程，返回 job_id。"""
    job_plan = build_retry_job_plan(
        saved_file=saved_file,
        runtime=runtime,
        selected_paths=selected_paths,
        queued_message=queued_message,
    )
    set_run_job(job_plan["job_id"], **job_plan["queue_record"])
    logger.info(
        "retry job queued",
        extra={
            "event": "job.retry.queued",
            "job_id": str(job_plan["job_id"]),
            "selected_count": len(selected_paths),
            "source_file": saved_file,
        },
    )

    worker = threading.Thread(
        target=_safe_run_job,
        args=(run_postman_job_fn, tuple(job_plan["worker_args"]), str(job_plan["job_id"]), set_run_job),
        daemon=True,
    )
    worker.start()
    return str(job_plan["job_id"])


def prepare_retry_job_context(
    *,
    payload: Dict[str, Any],
    report: Dict[str, Any],
    retry_mode: str,
    output_dir: str,
    default_results_per_page: int,
    clamp_run_results_per_page: Callable[[Any], int],
) -> Tuple[List[List[int]], Optional[Dict[str, Any]], Optional[str]]:
    """根据重试模式收集路径并校验源集合可用性，返回参数元组。"""
    if retry_mode == "failures":
        selected_paths = collect_failed_item_paths(report)
    elif retry_mode == "all":
        selected_paths = collect_all_item_paths(report)
    else:
        logger.warning(
            "retry mode invalid",
            extra={
                "event": "job.retry.invalid_mode",
                "retry_mode": retry_mode,
            },
        )
        return [], None, f"未知重试模式: {retry_mode}"

    source_runtime_ctx, source_runtime_error = build_retry_source_runtime_context(
        payload=payload,
        report=report,
        output_dir=output_dir,
        default_results_per_page=default_results_per_page,
        clamp_run_results_per_page=clamp_run_results_per_page,
    )
    if source_runtime_error:
        logger.warning(
            "retry context failed",
            extra={
                "event": "job.retry.context_failed",
                "retry_mode": retry_mode,
                "error": source_runtime_error,
            },
        )
    else:
        logger.info(
            "retry context ready",
            extra={
                "event": "job.retry.context_ready",
                "retry_mode": retry_mode,
                "selected_count": len(selected_paths),
            },
        )
    return selected_paths, source_runtime_ctx, source_runtime_error


def enqueue_job_with_worker(
    job_id: str,
    saved_file: str,
    job_params: Dict[str, Any],
    results_per_page: int,
    *,
    run_postman_job_fn: Callable[..., None],
    set_run_job: Callable[..., None],
    default_output_dir: str,
    selected_item_paths: Optional[List[List[int]]] = None,
) -> None:
    """入队普通任务并启动后台工作线程执行 Postman 测试。"""
    base_url = job_params.pop("base_url", None)
    token = job_params.pop("token", None)
    output_dir = job_params.pop("output_dir", default_output_dir)
    report_name = job_params.pop("report_name", "")
    original_name = job_params.pop("file_name", "collection.json")
    judgment_config = job_params.pop("judgment_config", None)

    set_run_job(job_id, **job_params)
    logger.info(
        "job queued",
        extra={
            "event": "job.enqueue.queued",
            "job_id": job_id,
            "saved_file": saved_file,
            "report_name": str(report_name or ""),
            "selected_count": len(selected_item_paths or []),
        },
    )

    job_kwargs: Dict[str, Any] = {}
    if judgment_config is not None:
        job_kwargs["judgment_config"] = judgment_config

    worker = threading.Thread(
        target=_safe_run_job,
        args=(
            run_postman_job_fn,
            (
                job_id,
                saved_file,
                base_url,
                output_dir,
                token,
                report_name,
                original_name,
                results_per_page,
                selected_item_paths or [],
            ),
            job_id,
            set_run_job,
        ),
        kwargs={"kwargs": job_kwargs} if job_kwargs else {},
        daemon=True,
    )
    worker.start()

