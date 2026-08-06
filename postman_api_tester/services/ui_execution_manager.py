"""UI 测试执行管理器。

在后台子进程中调度无头浏览器执行任务，与 UiExecutionStore 协作持久化结果。
使用 subprocess 隔离 Playwright greenlet 线程问题。
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Dict, Optional

from postman_api_tester.config import (
    UI_EXECUTION_MAX_CONCURRENT,
)
from postman_api_tester.services.ui_execution_store import UiExecutionStore
from postman_api_tester.services.ui_headless_engine import (
    is_playwright_available,
)

logger = logging.getLogger(__name__)

_active_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _worker_input_json(
    job_id: str,
    case_data: Dict[str, Any],
    options: Dict[str, Any],
    screenshots_dir: Optional[str],
) -> str:
    """构建传递给子进程的 JSON 输入，写入临时文件并返回文件路径。"""
    input_data = {
        "job_id": job_id,
        "case_data": case_data,
        "options": options,
        "screenshots_dir": screenshots_dir,
    }
    # 写入临时文件（避免 stdin 管道编码问题）
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"headless_worker_{job_id}_",
        delete=False,
        encoding="utf-8",
    ) as f:
        json.dump(input_data, f, ensure_ascii=False, default=str)
        return f.name


def _resolve_worker_script() -> str:
    """返回 worker 脚本的绝对路径。"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "ui_headless_worker.py",
    )


class UiExecutionManager:
    """后台子进程执行管理器。"""

    def __init__(self, store: UiExecutionStore) -> None:
        self._store = store

    @staticmethod
    def _parse_line(line_str: str) -> Dict[str, Any] | None:
        """解析一行 JSON 输出，失败返回 None。"""
        try:
            return json.loads(line_str)
        except json.JSONDecodeError:
            return None

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
        """启动无头浏览器后台执行（通过子进程隔离 Playwright）。"""
        if not is_playwright_available():
            self._store.update_step(
                job_id,
                {
                    "index": 0,
                    "action": "system",
                    "selector": {},
                    "value": "",
                    "status": "failed",
                    "error": "Playwright 未安装，无法使用无头浏览器模式",
                    "duration_ms": 0,
                },
            )
            self._store.finalize_job(
                job_id,
                "failed",
                {
                    "steps_total": 0,
                    "steps_passed": 0,
                    "steps_failed": 1,
                    "total_duration_ms": 0,
                },
            )
            return

        job_dir = self._store.base_dir / f"exec_{job_id}" / "screenshots"
        screenshots_dir = (
            str(job_dir) if options.get("take_screenshots", True) else None
        )

        input_file = _worker_input_json(job_id, case_data, options, screenshots_dir)

        cancel_event = threading.Event()
        process: Optional[subprocess.Popen[Any]] = None

        with _lock:
            _active_jobs[job_id] = {
                "cancel_event": cancel_event,
                "process": None,
            }

        # 标记为浏览器启动中
        self._store.update_status(job_id, "starting")

        def run() -> None:
            nonlocal process
            try:
                worker_script = _resolve_worker_script()
                python_exe = sys.executable

                process = subprocess.Popen(
                    [python_exe, worker_script, input_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                with _lock:
                    if job_id in _active_jobs:
                        _active_jobs[job_id]["process"] = process

                # 逐行读取 stdout：实时处理步骤结果和最终摘要
                final_result_data: Dict[str, Any] | None = None
                if process.stdout is not None:
                    first_line = process.stdout.readline()
                    if first_line:
                        line_str = first_line.decode("utf-8", errors="replace").strip()
                        if line_str == "BROWSER_READY":
                            self._store.update_status(job_id, "running")
                        else:
                            # 不是 BROWSER_READY，尝试作为 JSON 处理
                            parsed = self._parse_line(line_str)
                            if parsed is not None:
                                if "summary" in parsed or "success" in parsed:
                                    final_result_data = parsed
                                elif "step" in parsed:
                                    self._store.update_step(job_id, parsed["step"])

                    # 逐行读取后续输出（步骤结果 + 最终摘要）
                    for line in process.stdout:
                        line_str = line.decode("utf-8", errors="replace").strip()
                        if not line_str:
                            continue
                        parsed = self._parse_line(line_str)
                        if parsed is None:
                            continue
                        if "summary" in parsed or "success" in parsed:
                            final_result_data = parsed
                        elif "step" in parsed:
                            self._store.update_step(job_id, parsed["step"])

                # 等待进程结束并收集 stderr
                process.wait(timeout=300)
                stderr_data = ""
                if process.stderr is not None:
                    stderr_bytes = process.stderr.read()
                    stderr_data = (
                        stderr_bytes.decode("utf-8", errors="replace")
                        if stderr_bytes
                        else ""
                    )

                if process.returncode != 0:
                    error_msg = stderr_data[:500] if stderr_data else "子进程异常退出"
                    logger.error(
                        "headless_worker_failed: returncode=%s stderr=%s",
                        process.returncode,
                        error_msg,
                    )
                    self._store.finalize_job(
                        job_id,
                        "failed",
                        {
                            "steps_total": 0,
                            "steps_passed": 0,
                            "steps_failed": 0,
                            "total_duration_ms": 0,
                        },
                    )
                    if on_complete is not None:
                        result = self._store.get_result(job_id)
                        if result:
                            on_complete(result)
                    return

                if final_result_data is None:
                    logger.error("headless_worker_no_output: no valid JSON output from worker")
                    self._store.finalize_job(
                        job_id,
                        "failed",
                        {
                            "steps_total": 0,
                            "steps_passed": 0,
                            "steps_failed": 0,
                            "total_duration_ms": 0,
                        },
                    )
                    if on_complete is not None:
                        result = self._store.get_result(job_id)
                        if result:
                            on_complete(result)
                    return

                if not final_result_data.get("success"):
                    error_msg = final_result_data.get("error", "未知错误")
                    logger.error("headless_worker_error: %s", error_msg)
                    self._store.finalize_job(
                        job_id,
                        "failed",
                        {
                            "steps_total": 0,
                            "steps_passed": 0,
                            "steps_failed": 0,
                            "total_duration_ms": 0,
                        },
                    )
                    if on_complete is not None:
                        result = self._store.get_result(job_id)
                        if result:
                            on_complete(result)
                    return

                summary = final_result_data.get("summary", {})
                step_results = final_result_data.get("step_results", [])

                # 回填步骤结果到 store（实时更新可能已覆盖，此处兜底）
                for sr in step_results:
                    self._store.update_step(job_id, sr)

                self._store.finalize_job(
                    job_id, summary.get("status", "failed"), summary
                )
                if on_complete is not None:
                    result = self._store.get_result(job_id)
                    if result:
                        on_complete(result)

            except subprocess.TimeoutExpired:
                logger.error("headless_worker_timeout: job_id=%s", job_id)
                if process is not None:
                    process.kill()
                    process.wait()
                self._store.finalize_job(
                    job_id,
                    "failed",
                    {
                        "steps_total": 0,
                        "steps_passed": 0,
                        "steps_failed": 0,
                        "total_duration_ms": 0,
                    },
                )
                if on_complete is not None:
                    result = self._store.get_result(job_id)
                    if result:
                        on_complete(result)
            except Exception as e:
                logger.error(
                    "headless_execution_unexpected_error: %s", e, exc_info=True
                )
                if process is not None:
                    try:
                        process.kill()
                    except Exception:
                        pass
                self._store.finalize_job(
                    job_id,
                    "failed",
                    {
                        "steps_total": 0,
                        "steps_passed": 0,
                        "steps_failed": 0,
                        "total_duration_ms": 0,
                    },
                )
                if on_complete is not None:
                    result = self._store.get_result(job_id)
                    if result:
                        on_complete(result)
            finally:
                with _lock:
                    _active_jobs.pop(job_id, None)
                # 清理临时输入文件
                try:
                    os.unlink(input_file)
                except OSError:
                    pass

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
            process = job.get("process")
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass
        return True

    def is_active(self, job_id: str) -> bool:
        """任务是否仍在执行。"""
        with _lock:
            return job_id in _active_jobs
