"""开发导读：
- 职责：报告结果人工判定（标记成功/失败/恢复自动）及历史记录维护。
- 入口：set_report_result_judgement()。
- 关系：与 patch 重试回写链路协同，保证判定来源可追踪。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from postman_api_tester.utils.file_utils import atomic_write_json


def set_report_result_judgement(
    report_name: str,
    result_index: int,
    action: str,
    target_status: Optional[str] = None,
    reason: str = "",
    *,
    reports_dir: Path,
    get_report_write_lock: Callable[[str], Any],
    find_report: Callable[[str], Dict[str, Any]],
    compute_summary: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
    invalidate_reports_cache: Callable[[], None],
) -> Dict[str, Any]:
    """对指定结果条目执行人工判定（覆盖或恢复自动）并持久化元数据。"""
    action = str(action or "override").strip().lower()
    if action not in {"override", "restore"}:
        raise ValueError("action 仅支持 override 或 restore")

    if action == "override":
        normalized_status = str(target_status or "").strip().upper()
        if normalized_status not in {"PASSED", "FAILED"}:
            raise ValueError("target_status 仅支持 PASSED 或 FAILED")
    else:
        normalized_status = ""

    lock = get_report_write_lock(report_name)
    with lock:
        report = find_report(report_name)
        meta_file_name = str(report.get("meta_file") or "").strip()
        if not meta_file_name:
            raise ValueError("报告缺少 meta_file，无法更新元数据。")
        meta_path = reports_dir / meta_file_name
        if not meta_path.exists():
            raise FileNotFoundError(f"元数据文件不存在: {meta_file_name}")

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        results: List[Dict[str, Any]] = meta.get("results", [])
        if result_index < 0 or result_index >= len(results):
            raise IndexError(result_index)

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        old_result = dict(results[result_index])
        history = old_result.get("judgement_history")
        if not isinstance(history, list):
            history = []

        old_status = str(old_result.get("status") or "")
        old_message = str(old_result.get("message") or "")
        manual_judgement_value = old_result.get("manual_judgement")
        manual_judgement: Dict[str, Any] = manual_judgement_value if isinstance(manual_judgement_value, dict) else {}

        if action == "override":
            updated_result = {
                **old_result,
                "status": normalized_status,
                "manual_judgement": {
                    "active": True,
                    "source": "manual",
                    "action": "override",
                    "at": now_text,
                    "from_status": old_status,
                    "from_message": old_message,
                    "target_status": normalized_status,
                    "reason": reason,
                },
            }
            history.append({
                "action": "override",
                "at": now_text,
                "from_status": old_status,
                "to_status": normalized_status,
                "reason": reason,
            })
        else:
            if not manual_judgement.get("active"):
                raise ValueError("当前结果无可恢复的人工判定")
            restored_status = str(manual_judgement.get("from_status") or old_status).strip().upper() or old_status
            restored_message = str(manual_judgement.get("from_message") or old_message)
            updated_result = {
                **old_result,
                "status": restored_status,
                "message": restored_message,
                "manual_judgement": {
                    **manual_judgement,
                    "active": False,
                    "source": "auto",
                    "action": "restore",
                    "restored_at": now_text,
                },
            }
            history.append({
                "action": "restore",
                "at": now_text,
                "from_status": old_status,
                "to_status": restored_status,
                "reason": reason,
            })

        updated_result["judgement_history"] = history
        results[result_index] = updated_result
        meta["results"] = results

        old_summary = meta.get("summary", {})
        new_stats = compute_summary(results)
        meta["summary"] = {
            **old_summary,
            "total": new_stats["total"],
            "passed": new_stats["passed"],
            "failed": new_stats["failed"],
            "error": new_stats["error"],
            "success_rate": new_stats["success_rate"],
        }

        atomic_write_json(meta_path, meta)

        invalidate_reports_cache()
        return {"summary": meta["summary"], "result": updated_result}
