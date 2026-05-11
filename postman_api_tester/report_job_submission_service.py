import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def sanitize_uploaded_name(original_name: str) -> str:
    safe_name = re.sub(r'[^\w\u4e00-\u9fff\-. ()（）【】]', '_', str(original_name or "")).strip('. ')
    return safe_name if safe_name else "collection.json"


def build_run_postman_job_params(
    *,
    job_id: str,
    original_name: str,
    saved_file: str,
    output_dir: str,
    report_name: Optional[str],
    base_url: Optional[str],
    token: Optional[str],
    selected_item_paths: Optional[List[List[int]]],
) -> Dict[str, Any]:
    selected_count = len(selected_item_paths or [])
    return {
        "id": job_id,
        "status": "queued",
        "message": "任务已入队，等待执行。",
        "total": 0,
        "completed": 0,
        "percent": 0,
        "current_name": "",
        "file_name": original_name,
        "saved_file": saved_file,
        "output_dir": output_dir,
        "report_name": report_name or "",
        "run_scope": ("selected" if selected_count else "all"),
        "selected_count": selected_count,
        "base_url": base_url,
        "token": token,
    }


def build_ad_hoc_job_params(
    *,
    job_id: str,
    source_original_file: str,
    saved_file: str,
    output_dir: str,
    report_name: Optional[str],
    base_url: Optional[str],
    token: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": job_id,
        "status": "queued",
        "message": "任务已入队，等待执行。",
        "total": 0,
        "completed": 0,
        "percent": 0,
        "current_name": "",
        "file_name": source_original_file,
        "saved_file": saved_file,
        "output_dir": output_dir,
        "report_name": report_name or "",
        "run_scope": "all",
        "selected_count": 0,
        "collection_name": "",
        "adhoc": True,
        "base_url": base_url,
        "token": token,
    }


def build_saved_json_path(base_dir: Path, job_id: str, suffix: str = ".json") -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{job_id}{suffix}"
