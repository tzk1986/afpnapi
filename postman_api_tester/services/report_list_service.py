"""开发导读：
- 职责：生成首页报告列表摘要项，避免返回完整 results 造成重载。
- 入口：report_list_item()。
- 输出：列表页所需最小字段集（时间、来源、汇总、成功率等）。
"""

from typing import Any, Dict


def report_list_item(report: Dict[str, Any]) -> Dict[str, Any]:
    """生成首页报告列表所需的摘要项字典。"""
    summary = dict(report.get("summary") or {})
    return {
        "report_name": report.get("report_name", ""),
        "generated_at": report.get("generated_at", ""),
        "host_name": report.get("host_name", ""),
        "collection_name": report.get("collection_name", ""),
        "source_file": report.get("source_file", ""),
        "source_original_file": report.get("source_original_file", ""),
        "summary": {
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "error": summary.get("error", 0),
            "success_rate": summary.get("success_rate", "0%"),
        },
        "load_error": report.get("load_error", ""),
        "legacy": bool(report.get("legacy", False)),
    }


def is_total_report_name(report_name: str) -> bool:
    """判断报告名是否为总报告名（不含分页标记 _page_）。"""
    return "_page_" not in str(report_name or "").lower()
