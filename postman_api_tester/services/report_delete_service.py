"""开发导读：
- 职责：删除单份报告及其关联产物（html/details/meta/page 子页）。
- 入口：delete_report_artifacts()。
- 安全边界：依赖上层传入的工件收集函数，确保删除范围可控。
"""

from pathlib import Path
import logging
from typing import Any, Callable, Dict, List


logger = logging.getLogger(__name__)


def delete_report_artifacts(
    report_name: str,
    *,
    find_report: Callable[[str], Dict[str, Any]],
    collect_report_artifacts: Callable[[Dict[str, Any]], List[Path]],
    invalidate_reports_cache: Callable[[], None],
) -> List[str]:
    logger.info(
        "report delete started",
        extra={
            "event": "report.delete.started",
            "report_name": report_name,
        },
    )
    report = find_report(report_name)
    artifacts = collect_report_artifacts(report)
    deleted_files: List[str] = []
    for artifact in artifacts:
        if artifact.exists() and artifact.is_file():
            artifact.unlink()
            deleted_files.append(artifact.name)

    invalidate_reports_cache()
    logger.info(
        "report delete completed",
        extra={
            "event": "report.delete.completed",
            "report_name": report_name,
            "deleted_count": len(deleted_files),
        },
    )
    return deleted_files
