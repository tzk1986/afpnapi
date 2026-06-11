"""开发导读：
- 职责：提交前参数规范化（文件名清洗、任务初始状态、落盘路径）。
- 入口：sanitize_uploaded_name()、build_*_job_params()、build_saved_json_path()。
- 目标：统一入队参数结构，降低路由层重复拼装风险。
"""

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


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
    judgment_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    selected_count = len(selected_item_paths or [])
    logger.info(
        "build run job params",
        extra={
            "event": "job.submit.params_built",
            "job_id": job_id,
            "run_scope": ("selected" if selected_count else "all"),
            "selected_count": selected_count,
        },
    )
    result: Dict[str, Any] = {
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
    if judgment_config is not None:
        result["judgment_config"] = judgment_config
    return result


def build_ad_hoc_job_params(
    *,
    job_id: str,
    source_original_file: str,
    saved_file: str,
    output_dir: str,
    report_name: Optional[str],
    base_url: Optional[str],
    token: Optional[str],
    judgment_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    logger.info(
        "build adhoc job params",
        extra={
            "event": "job.submit.adhoc_params_built",
            "job_id": job_id,
            "source_file": source_original_file,
        },
    )
    result: Dict[str, Any] = {
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
    if judgment_config is not None:
        result["judgment_config"] = judgment_config
    return result


def build_saved_json_path(base_dir: Path, job_id: str, suffix: str = ".json") -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    saved_path = base_dir / f"{job_id}{suffix}"
    logger.info(
        "build saved json path",
        extra={
            "event": "job.submit.path_built",
            "job_id": job_id,
            "saved_path": str(saved_path),
        },
    )
    return saved_path
