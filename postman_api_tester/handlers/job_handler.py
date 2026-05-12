"""Job handler thin wrappers over service layer."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from postman_api_tester.services.report_job_execution_service import (
    enqueue_job_with_worker as _svc_enqueue_job_with_worker,
    enqueue_retry_job as _svc_enqueue_retry_job,
    prepare_retry_job_context as _svc_prepare_retry_job_context,
    run_postman_job as _svc_run_postman_job,
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
    return _svc_run_postman_job(
        job_id,
        postman_file,
        base_url,
        output_dir,
        token,
        report_name,
        source_original_file,
        results_per_page,
        selected_item_paths,
        set_run_job=set_run_job,
        invalidate_reports_cache=invalidate_reports_cache,
    )


def enqueue_retry_job(
    saved_file: str,
    runtime: Dict[str, Any],
    selected_paths: List[List[int]],
    queued_message: str,
    *,
    set_run_job: Callable[..., None],
    run_postman_job_fn: Callable[..., None],
) -> str:
    return _svc_enqueue_retry_job(
        saved_file,
        runtime,
        selected_paths,
        queued_message,
        set_run_job=set_run_job,
        run_postman_job_fn=run_postman_job_fn,
    )


def prepare_retry_job_context(
    *,
    payload: Dict[str, Any],
    report: Dict[str, Any],
    retry_mode: str,
    output_dir: str,
    default_results_per_page: int,
    clamp_run_results_per_page: Callable[[Any], int],
) -> Tuple[List[List[int]], Optional[Dict[str, Any]], Optional[str]]:
    return _svc_prepare_retry_job_context(
        payload=payload,
        report=report,
        retry_mode=retry_mode,
        output_dir=output_dir,
        default_results_per_page=default_results_per_page,
        clamp_run_results_per_page=clamp_run_results_per_page,
    )


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
    return _svc_enqueue_job_with_worker(
        job_id,
        saved_file,
        job_params,
        results_per_page,
        run_postman_job_fn=run_postman_job_fn,
        set_run_job=set_run_job,
        default_output_dir=default_output_dir,
        selected_item_paths=selected_item_paths,
    )


__all__ = [
    "run_postman_job",
    "enqueue_retry_job",
    "prepare_retry_job_context",
    "enqueue_job_with_worker",
]

