"""Report handler real implementations for filtering/comparison/result payloads."""

"""开发导读：
- 职责：报告结果筛选、分页、历史对比等"展示侧聚合逻辑"。
- 入口：filter_report_results()、paginate_items()、compare_report_data()。
- 输出：前端可直接消费的轻量结果项与对比摘要。
- 关系：详情数据按需来自 report_repository；完整 payload 仍委托 services.report_results_service。
"""

from typing import Any, Dict, List, Optional

from postman_api_tester.report_repository import load_report_details_map
from postman_api_tester.report_server_utils import (
    normalize_manual_exclusions as _normalize_manual_exclusions,
    result_exclusion_key as _result_exclusion_key,
)


def normalize_status_filter(value: str) -> Optional[str]:
    """状态筛选值归一化：支持中英文与别名输入。"""
    normalized = str(value or "").strip().upper()
    if normalized in {"", "ALL", "RESULT", "全部", "结果"}:
        return None
    if normalized in {"PASSED", "SUCCESS", "成功"}:
        return "PASSED"
    if normalized in {"FAILED", "FAIL", "失败"}:
        return "FAILED"
    if normalized in {"ERROR", "错误"}:
        return "ERROR"
    return None


def filter_report_results(
    report: Dict[str, Any],
    keyword: str,
    status_filter: Optional[str],
    message_keyword: str,
    err_code_keyword: str,
    include_excluded: bool = True,
) -> List[Dict[str, Any]]:
    """组合状态/关键字/错误码/排除开关，返回筛选后的结果列表。"""
    lowered_keyword = str(keyword or "").strip().lower()
    lowered_message_keyword = str(message_keyword or "").strip().lower()
    lowered_err_code_keyword = str(err_code_keyword or "").strip().lower()
    exclusion_set = set(_normalize_manual_exclusions(report.get("manual_exclusions") or []))
    details_map = load_report_details_map(report)
    filtered_items: List[Dict[str, Any]] = []

    for index, item in enumerate(report.get("results", [])):
        manual_judgement = item.get("manual_judgement") if isinstance(item.get("manual_judgement"), dict) else {}
        judgement_source = "manual" if manual_judgement.get("active") else "auto"
        exclusion_key = _result_exclusion_key(item)
        excluded = exclusion_key in exclusion_set
        if excluded and not include_excluded:
            continue
        if status_filter and item.get("status") != status_filter:
            continue
        if lowered_keyword:
            search_text = " ".join(
                [
                    str(item.get("name", "")),
                    str(item.get("url", "")),
                    str(item.get("folder", "")),
                    str(item.get("key", "")),
                ]
            ).lower()
            if lowered_keyword not in search_text:
                continue
        if lowered_message_keyword:
            message_text = str(item.get("message", "")).lower()
            if lowered_message_keyword not in message_text:
                continue
        if lowered_err_code_keyword:
            err_code_text = str(item.get("err_code", "")).lower()
            if lowered_err_code_keyword not in err_code_text:
                continue
        filtered_items.append(
            {
                "index": index,
                "name": item.get("name", ""),
                "folder": item.get("folder", ""),
                "method": item.get("method", ""),
                "url": item.get("url", ""),
                "status": item.get("status", ""),
                "status_code": item.get("status_code"),
                "message": item.get("message", ""),
                "err_code": item.get("err_code", ""),
                "response_time_ms": item.get("response_time_ms", 0),
                "data_index": item.get("data_index", 0),
                "excluded": excluded,
                "exclusion_key": exclusion_key,
                "judgement_source": judgement_source,
                "detail_available": str(index) in details_map,
            }
        )
    return filtered_items


def paginate_items(items: List[Dict[str, Any]], page: int, page_size: int) -> Dict[str, Any]:
    """统一分页结构。"""
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": current_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _map_results(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["key"]: item for item in report.get("results", [])}


def _to_rate(value: str) -> float:
    try:
        return float(str(value).replace("%", ""))
    except ValueError:
        return 0.0


def compare_report_data(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """历史报告对比：以 key 为主键，输出新增/移除/状态变化与成功率差值。"""
    left_map = _map_results(left)
    right_map = _map_results(right)
    left_keys = set(left_map.keys())
    right_keys = set(right_map.keys())

    added_keys = sorted(right_keys - left_keys)
    removed_keys = sorted(left_keys - right_keys)
    common_keys = sorted(left_keys & right_keys)
    changed: List[Dict[str, Any]] = []

    for key in common_keys:
        before = left_map[key]
        after = right_map[key]
        if before.get("status") != after.get("status") or before.get("status_code") != after.get("status_code"):
            changed.append(
                {
                    "key": key,
                    "name": after.get("name") or before.get("name"),
                    "folder": after.get("folder") or before.get("folder"),
                    "method": after.get("method") or before.get("method"),
                    "url": after.get("url") or before.get("url"),
                    "before_status": before.get("status"),
                    "after_status": after.get("status"),
                    "before_status_code": before.get("status_code"),
                    "after_status_code": after.get("status_code"),
                }
            )

    left_rate = _to_rate(left.get("summary", {}).get("success_rate", "0%"))
    right_rate = _to_rate(right.get("summary", {}).get("success_rate", "0%"))
    delta = right_rate - left_rate

    return {
        "left": left,
        "right": right,
        "summary": {
            "added_count": len(added_keys),
            "removed_count": len(removed_keys),
            "changed_count": len(changed),
            "success_rate_delta": round(delta, 2),
            "success_rate_delta_text": f"{delta:+.2f}%",
        },
        "added": [right_map[key] for key in added_keys],
        "removed": [left_map[key] for key in removed_keys],
        "changed": changed,
    }


__all__ = [
    "normalize_status_filter",
    "filter_report_results",
    "paginate_items",
    "compare_report_data",
]

