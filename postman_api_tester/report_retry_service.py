from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid


def collect_failed_item_paths(report: Dict[str, Any]) -> List[List[int]]:
    paths: List[List[int]] = []
    for item in report.get("results", []):
        if item.get("status") in ("FAILED", "ERROR"):
            item_path = item.get("item_path")
            if isinstance(item_path, list) and item_path:
                paths.append(item_path)
    return paths


def collect_all_item_paths(report: Dict[str, Any]) -> List[List[int]]:
    paths: List[List[int]] = []
    for item in report.get("results", []):
        item_path = item.get("item_path")
        if isinstance(item_path, list) and item_path:
            paths.append(item_path)
    return paths


def resolve_existing_source_file(report: Dict[str, Any]) -> Optional[str]:
    saved_file = str(report.get("source_file", "")).strip()
    if not saved_file:
        return None
    return saved_file if Path(saved_file).exists() else None


def build_retry_queue_record(
    job_id: str,
    saved_file: str,
    output_dir: str,
    selected_count: int,
    queued_message: str,
) -> Dict[str, Any]:
    file_name = Path(saved_file).name
    return {
        "id": job_id,
        "status": "queued",
        "message": queued_message,
        "total": 0,
        "completed": 0,
        "percent": 0,
        "current_name": "",
        "file_name": file_name,
        "saved_file": saved_file,
        "output_dir": output_dir,
        "report_name": "",
        "run_scope": "selected",
        "selected_count": selected_count,
    }


def build_retry_worker_args(
    job_id: str,
    saved_file: str,
    base_url: Optional[str],
    output_dir: str,
    token: Optional[str],
    results_per_page: int,
    selected_paths: List[List[int]],
) -> Tuple[Any, ...]:
    file_name = Path(saved_file).name
    return (
        job_id,
        saved_file,
        base_url,
        output_dir,
        token,
        None,
        file_name,
        results_per_page,
        selected_paths,
    )


def parse_retry_runtime_params(
    payload: Dict[str, Any],
    report: Dict[str, Any],
    output_dir: str,
    default_results_per_page: int,
    clamp_run_results_per_page: Callable[[Any], int],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    base_url = str(payload.get("base_url", "") or report.get("base_url", "")).strip() or None
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None, "base_url 仅允许合法的 http/https 地址"

    token = str(payload.get("token", "")).strip() or None
    results_per_page = clamp_run_results_per_page(payload.get("results_per_page", default_results_per_page))
    return {
        "base_url": base_url,
        "token": token,
        "output_dir": output_dir,
        "results_per_page": results_per_page,
    }, None


def build_retry_source_runtime_context(
    payload: Dict[str, Any],
    report: Dict[str, Any],
    output_dir: str,
    default_results_per_page: int,
    clamp_run_results_per_page: Callable[[Any], int],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    saved_file = resolve_existing_source_file(report)
    if not saved_file:
        return None, "找不到原始集合文件，无法重试。请确认报告对应的集合文件仍然存在。"

    runtime, runtime_error = parse_retry_runtime_params(
        payload=payload,
        report=report,
        output_dir=output_dir,
        default_results_per_page=default_results_per_page,
        clamp_run_results_per_page=clamp_run_results_per_page,
    )
    if runtime_error:
        return None, runtime_error
    assert runtime is not None

    return {
        "saved_file": saved_file,
        "runtime": runtime,
    }, None


def build_retry_job_plan(
    saved_file: str,
    runtime: Dict[str, Any],
    selected_paths: List[List[int]],
    queued_message: str,
) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex
    queue_record = build_retry_queue_record(
        job_id=job_id,
        saved_file=saved_file,
        output_dir=str(runtime["output_dir"]),
        selected_count=len(selected_paths),
        queued_message=queued_message,
    )
    worker_args = build_retry_worker_args(
        job_id=job_id,
        saved_file=saved_file,
        base_url=runtime.get("base_url"),
        output_dir=str(runtime["output_dir"]),
        token=runtime.get("token"),
        results_per_page=int(runtime["results_per_page"]),
        selected_paths=selected_paths,
    )
    return {
        "job_id": job_id,
        "queue_record": queue_record,
        "worker_args": worker_args,
    }
