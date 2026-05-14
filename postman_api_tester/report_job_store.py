"""运行任务状态存储模块。

开发导读:
- 维护内存态任务字典与并发锁，供报告服务查询任务进度。
- 提供任务写入、读取、上限控制与过期淘汰能力。
"""

import threading
from typing import Any, Dict, Optional


RUN_JOBS: Dict[str, Dict[str, Any]] = {}
RUN_JOBS_LOCK = threading.Lock()
_RUN_JOBS_MAX = 200


def configure_run_jobs(max_jobs: int) -> None:
    global _RUN_JOBS_MAX
    try:
        parsed = int(max_jobs)
    except (TypeError, ValueError):
        parsed = 200
    _RUN_JOBS_MAX = max(10, parsed)


def _evict_old_jobs_locked() -> None:
    """已在 RUN_JOBS_LOCK 持有下调用：超出上限时清理最早完成的任务。"""
    if len(RUN_JOBS) <= _RUN_JOBS_MAX:
        return
    terminal_statuses = {"success", "failed"}
    finished = [
        jid for jid, job in RUN_JOBS.items()
        if job.get("status") in terminal_statuses
    ]
    # 按写入顺序保留最新一半已完成任务
    to_evict = finished[: max(0, len(finished) - _RUN_JOBS_MAX // 2)]
    for jid in to_evict:
        del RUN_JOBS[jid]


def set_run_job(job_id: str, **updates: Any) -> None:
    with RUN_JOBS_LOCK:
        RUN_JOBS[job_id] = {**RUN_JOBS.get(job_id, {}), **updates}
        _evict_old_jobs_locked()


def get_run_job(job_id: str) -> Optional[Dict[str, Any]]:
    with RUN_JOBS_LOCK:
        job = RUN_JOBS.get(job_id)
        return dict(job) if job else None
