"""UI 测试执行管理器。

在后台线程中调度无头浏览器执行任务，与 UiExecutionStore 协作持久化结果。
"""

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from postman_api_tester.config import (
    UI_EXECUTION_MAX_CONCURRENT,
    UI_HEADLESS_BROWSER,
)
from postman_api_tester.services.ui_execution_store import UiExecutionStore
from postman_api_tester.services.ui_headless_engine import (
    HeadlessExecutionError,
    UiHeadlessEngine,
    is_playwright_available,
)

logger = logging.getLogger(__name__)

_active_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


class UiExecutionManager:
    """后台线程执行管理器。"""

    def __init__(self, store: UiExecutionStore) -> None:
        self._store = store

    def can_start(self) -> bool:
        """是否还能启动新任务。"""
        with _lock:
            return len(_active_jobs) < UI_EXECUTION_MAX_CONCURRENT

    def start_headless(
        self,
        job_id: str,
        case_data: Dict[str, Any],
        options: Dict[str, Any],
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """启动无头浏览器后台执行。"""
        if not is_playwright_available():
            self._store.update_step(job_id, {
                "index": 0,
                "action": "system",
                "selector": {},
                "value": "",
                "status": "failed",
                "error": "Playwright 未安装，无法使用无头浏览器模式",
                "duration_ms": 0,
            })
            self._store.finalize_job(job_id, "failed", {
                "steps_total": 0,
                "steps_passed": 0,
                "steps_failed": 1,
                "total_duration_ms": 0,
            })
            return

        cancel_event = threading.Event()
        with _lock:
            _active_jobs[job_id] = {
                "cancel_event": cancel_event,
                "thread": None,
            }

        job_dir = Path("ui_testing_cases") / f"exec_{job_id}" / "screenshots"

        def on_step_complete(step_index: int, step_result: Dict[str, Any]) -> None:
            self._store.update_step(job_id, step_result)

        def run() -> None:
            try:
                browser_type = options.get("headless_browser", UI_HEADLESS_BROWSER)
                screenshots_dir = job_dir if options.get("take_screenshots", True) else None
                engine = UiHeadlessEngine(
                    browser_type=browser_type,
                    screenshots_dir=screenshots_dir,
                )
                steps = case_data.get("steps", [])
                base_url = case_data.get("base_url", "")

                summary = engine.execute(
                    steps=steps,
                    base_url=base_url,
                    options=options,
                    job_id=job_id,
                    cancel_flag=cancel_event,
                    on_step_complete=on_step_complete,
                )
                self._store.finalize_job(job_id, summary["status"], summary)
                if on_complete is not None:
                    result = self._store.get_result(job_id)
                    if result:
                        on_complete(result)
            except HeadlessExecutionError as e:
                logger.error("headless_execution_error: %s", e)
                self._store.finalize_job(job_id, "failed", {
                    "steps_total": 0,
                    "steps_passed": 0,
                    "steps_failed": 0,
                    "total_duration_ms": 0,
                })
                if on_complete is not None:
                    result = self._store.get_result(job_id)
                    if result:
                        on_complete(result)
            except Exception as e:
                logger.error("headless_execution_unexpected_error: %s", e, exc_info=True)
                self._store.finalize_job(job_id, "failed", {
                    "steps_total": 0,
                    "steps_passed": 0,
                    "steps_failed": 0,
                    "total_duration_ms": 0,
                })
                if on_complete is not None:
                    result = self._store.get_result(job_id)
                    if result:
                        on_complete(result)
            finally:
                with _lock:
                    _active_jobs.pop(job_id, None)

        t = threading.Thread(target=run, name=f"ui-exec-{job_id}", daemon=True)
        with _lock:
            if job_id in _active_jobs:
                _active_jobs[job_id]["thread"] = t
        t.start()

    def cancel(self, job_id: str) -> bool:
        """取消执行。返回是否成功发出取消信号。"""
        with _lock:
            job = _active_jobs.get(job_id)
            if not job:
                return False
            job["cancel_event"].set()
        return True

    def is_active(self, job_id: str) -> bool:
        """任务是否仍在执行。"""
        with _lock:
            return job_id in _active_jobs
