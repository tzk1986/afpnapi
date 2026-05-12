"""Job handler real implementations for queueing and worker orchestration."""

import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from postman_api_tester.services.report_retry_service import (
    build_retry_job_plan,
    build_retry_source_runtime_context,
    collect_all_item_paths,
    collect_failed_item_paths,
)


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
) -> None:
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
        )
        set_run_job(
            job_id,
            status="success",
            message="Execution completed, refreshing report index.",
            report_name=os.path.basename(str(report.generated_report_file or "")),
            report_meta_name=os.path.basename(str(report.generated_meta_file or "")),
        )
        invalidate_reports_cache()
    except Exception as exc:
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
    job_plan = build_retry_job_plan(
        saved_file=saved_file,
        runtime=runtime,
        selected_paths=selected_paths,
        queued_message=queued_message,
    )
    set_run_job(job_plan["job_id"], **job_plan["queue_record"])

    worker = threading.Thread(
        target=run_postman_job_fn,
        args=job_plan["worker_args"],
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
    if retry_mode == "failures":
        selected_paths = collect_failed_item_paths(report)
    elif retry_mode == "all":
        selected_paths = collect_all_item_paths(report)
    else:
        return [], None, f"未知重试模式: {retry_mode}"

    source_runtime_ctx, source_runtime_error = build_retry_source_runtime_context(
        payload=payload,
        report=report,
        output_dir=output_dir,
        default_results_per_page=default_results_per_page,
        clamp_run_results_per_page=clamp_run_results_per_page,
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
    base_url = job_params.pop("base_url", None)
    token = job_params.pop("token", None)
    output_dir = job_params.pop("output_dir", default_output_dir)
    report_name = job_params.pop("report_name", "")
    original_name = job_params.pop("file_name", "collection.json")

    set_run_job(job_id, **job_params)

    worker = threading.Thread(
        target=run_postman_job_fn,
        args=(
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
        daemon=True,
    )
    worker.start()


__all__ = [
    "run_postman_job",
    "enqueue_retry_job",
    "prepare_retry_job_context",
    "enqueue_job_with_worker",
]

