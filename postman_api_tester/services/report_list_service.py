from typing import Any, Dict


def report_list_item(report: Dict[str, Any]) -> Dict[str, Any]:
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
    return "_page_" not in str(report_name or "").lower()
