"""UI 测试执行结果存储服务。

以 JSON 文件形式持久化执行结果，服务重启后可恢复。
目录结构：
  ui_testing_cases/
    exec_{job_id}/
      result.json      ← 完整报告
      screenshots/     ← 截图（Phase 2）
"""

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from postman_api_tester.config import (
    UI_EXECUTION_RESULTS_DIR,
    UI_EXECUTION_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path("ui_testing_cases")


class UiExecutionStore:
    """执行结果文件存储。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is not None:
            self._base_dir = base_dir
        elif UI_EXECUTION_RESULTS_DIR:
            self._base_dir = Path(UI_EXECUTION_RESULTS_DIR)
        else:
            self._base_dir = _DEFAULT_DIR
        self._lock = threading.Lock()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        return self._base_dir / f"exec_{job_id}"

    def _result_file(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "result.json"

    def create_job(self, case_id: str, mode: str, case_name: str) -> str:
        """创建执行任务记录，返回 job_id。"""
        job_id = f"{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        record: Dict[str, Any] = {
            "job_id": job_id,
            "case_id": case_id,
            "case_name": case_name,
            "mode": mode,
            "status": "ready",
            "started_at": now,
            "ended_at": None,
            "total_duration_ms": 0,
            "steps_total": 0,
            "steps_passed": 0,
            "steps_failed": 0,
            "steps": [],
        }

        job_dir = self._job_dir(job_id)
        with self._lock:
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "screenshots").mkdir(exist_ok=True)
            self._write_result(job_id, record)

        logger.info(
            "ui_execution_job_created",
            extra={
                "event": "ui.execution.created",
                "job_id": job_id,
                "case_id": case_id,
                "case_name": case_name,
                "mode": mode,
            },
        )
        return job_id

    def update_step(self, job_id: str, step_result: Dict[str, Any]) -> None:
        """追加单个步骤结果。"""
        with self._lock:
            record = self._read_result(job_id)
            if record is None:
                return
            record["steps"].append(step_result)
            status = step_result.get("status", "passed")
            if status == "passed":
                record["steps_passed"] = record.get("steps_passed", 0) + 1
            elif status in ("failed", "error"):
                record["steps_failed"] = record.get("steps_failed", 0) + 1
            record["status"] = "running"
            self._write_result(job_id, record)

        logger.debug(
            "ui_execution_step_complete",
            extra={
                "event": "ui.execution.step_complete",
                "job_id": job_id,
                "step_index": step_result.get("index"),
                "action": step_result.get("action"),
                "status": status,
                "duration_ms": step_result.get("duration_ms", 0),
            },
        )

    def finalize_job(self, job_id: str, status: str, summary: Dict[str, Any]) -> str:
        """完成执行，写入最终报告。返回目录路径。"""
        with self._lock:
            record = self._read_result(job_id)
            if record is None:
                return ""
            record["status"] = status
            record["ended_at"] = datetime.now().isoformat()
            record["total_duration_ms"] = summary.get("total_duration_ms", 0)
            record["steps_total"] = summary.get("steps_total", len(record.get("steps", [])))
            record["steps_passed"] = summary.get("steps_passed", record.get("steps_passed", 0))
            record["steps_failed"] = summary.get("steps_failed", record.get("steps_failed", 0))
            self._write_result(job_id, record)

        logger.info(
            "ui_execution_completed",
            extra={
                "event": "ui.execution.completed",
                "job_id": job_id,
                "status": status,
                "total_steps": record["steps_total"],
                "passed": record["steps_passed"],
                "failed": record["steps_failed"],
                "duration_ms": record["total_duration_ms"],
            },
        )
        return str(self._job_dir(job_id))

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """读取完整执行报告。"""
        with self._lock:
            return self._read_result(job_id)

    def list_results(
        self, case_id: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """列出执行历史（可选按 case_id 过滤）。"""
        results: List[Dict[str, Any]] = []
        with self._lock:
            dirs = sorted(
                self._base_dir.glob("exec_*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for job_dir in dirs:
                if len(results) >= limit:
                    break
                result_file = job_dir / "result.json"
                if not result_file.exists():
                    continue
                try:
                    data = json.loads(result_file.read_text(encoding="utf-8"))
                    if case_id and data.get("case_id") != case_id:
                        continue
                    results.append({
                        "job_id": data.get("job_id", ""),
                        "case_id": data.get("case_id", ""),
                        "case_name": data.get("case_name", ""),
                        "mode": data.get("mode", ""),
                        "status": data.get("status", ""),
                        "steps_total": data.get("steps_total", 0),
                        "steps_passed": data.get("steps_passed", 0),
                        "steps_failed": data.get("steps_failed", 0),
                        "total_duration_ms": data.get("total_duration_ms", 0),
                        "started_at": data.get("started_at", ""),
                        "ended_at": data.get("ended_at", ""),
                    })
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to read execution result %s: %s", job_dir.name, e)

        return results

    def _read_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """内部：读取 result.json（调用方需持有锁）。"""
        result_file = self._result_file(job_id)
        if not result_file.exists():
            return None
        try:
            return json.loads(result_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to read execution result %s: %s", job_id, e)
            return None

    def _write_result(self, job_id: str, record: Dict[str, Any]) -> None:
        """内部：写入 result.json（调用方需持有锁）。"""
        result_file = self._result_file(job_id)
        result_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
