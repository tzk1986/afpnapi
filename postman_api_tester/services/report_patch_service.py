"""开发导读：
- 职责：对单条报告结果执行补丁式回写（结果字段、请求信息、响应信息）。
- 入口：patch_report_result()。
- 场景：编辑重试后将最新执行结果合并回 details/meta。
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, cast

from postman_api_tester.utils.file_utils import atomic_write_json


def _build_retry_history_and_judgement(
    old_result: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """构建重试历史和重置手工判定。

    注意：会通过 pop() 修改传入的 old_result（移除 retry_history 字段），
    调用方需确保传入的是副本而非原始引用。
    """
    old_history: List[Dict[str, Any]] = old_result.pop("retry_history", [])
    retry_history = old_history + [old_result]
    old_judgement_value = old_result.get("manual_judgement")
    old_judgement: Dict[str, Any] = old_judgement_value if isinstance(old_judgement_value, dict) else {}
    manual_judgement = {
        **old_judgement,
        "active": False,
        "source": "auto",
    }
    return retry_history, manual_judgement


def _build_merged_result(
    old_result: Dict[str, Any],
    new_result_fields: Dict[str, Any],
    retry_history: List[Dict[str, Any]],
    manual_judgement: Dict[str, Any],
) -> Dict[str, Any]:
    """构建合并后的结果对象。"""
    merged = {
        "name": old_result.get("name", ""),
        "folder": old_result.get("folder", ""),
        "method": new_result_fields.get("method", old_result.get("method", "")),
        "url": new_result_fields.get("url", old_result.get("url", "")),
        "item_path": new_result_fields.get("item_path", old_result.get("item_path", [])),
        "expected_status": new_result_fields.get("expected_status", old_result.get("expected_status", 200)),
        **new_result_fields,
        "retry_history": retry_history,
        "retried": True,
        "manual_judgement": manual_judgement,
        "judgement_history": old_result.get("judgement_history", []),
    }
    merged["key"] = " | ".join([
        merged.get("folder", "") or "-",
        merged.get("name", "") or "-",
        merged.get("method", "") or "-",
        merged.get("url", "") or "-",
    ])
    return merged


def _update_details_file(
    details_file_name: str,
    result_index: int,
    new_request_info: Dict[str, Any],
    new_response_info: Dict[str, Any],
    reports_dir: Path,
) -> None:
    """更新详情文件中的请求和响应信息。"""
    if not details_file_name:
        return
    details_path = reports_dir / details_file_name
    details: Dict[str, Any] = {}
    if details_path.exists():
        try:
            with details_path.open("r", encoding="utf-8") as f:
                details = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    details[str(result_index)] = {
        "request_info": new_request_info,
        "response_info": new_response_info,
    }
    atomic_write_json(details_path, details)


def patch_report_result(
    report_name: str,
    result_index: int,
    new_result_fields: Dict[str, Any],
    new_request_info: Dict[str, Any],
    new_response_info: Dict[str, Any],
    *,
    reports_dir: Path,
    get_report_write_lock: Callable[[str], Any],
    find_report: Callable[[str], Dict[str, Any]],
    compute_summary: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
    invalidate_reports_cache: Callable[[], None],
) -> Dict[str, Any]:
    """同步更新 _meta.json 与 _details.json。"""
    lock = get_report_write_lock(report_name)
    with lock:
        try:
            report = find_report(report_name)
        except FileNotFoundError:
            return {}

        meta_file_name = str(report.get("meta_file") or "").strip()
        if not meta_file_name:
            return {}

        meta_path = reports_dir / meta_file_name
        if not meta_path.exists():
            return {}

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        results: List[Dict[str, Any]] = meta.get("results", [])
        if result_index < 0 or result_index >= len(results):
            return {}

        old_result = dict(results[result_index])
        retry_history, manual_judgement = _build_retry_history_and_judgement(old_result)
        merged = _build_merged_result(old_result, new_result_fields, retry_history, manual_judgement)
        results[result_index] = merged
        meta["results"] = results

        new_stats = compute_summary(results)
        old_summary = meta.get("summary", {})
        meta["summary"] = {
            **old_summary,
            "total": new_stats["total"],
            "passed": new_stats["passed"],
            "failed": new_stats["failed"],
            "error": new_stats["error"],
            "success_rate": new_stats["success_rate"],
        }

        atomic_write_json(meta_path, meta)

        details_file_name = str(report.get("details_file") or "").strip()
        _update_details_file(details_file_name, result_index, new_request_info, new_response_info, reports_dir)

        invalidate_reports_cache()
        return cast(Dict[str, Any], meta["summary"])
