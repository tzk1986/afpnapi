"""Admin handler thin wrappers over service layer."""

"""开发导读：
- 职责：管理类路由入口的薄封装层（当前为报告删除）。
- 入口：delete_report_artifacts()。
- 行为：仅记录结构化日志并转发到 service，实现依赖注入与边界收口。
- 关系：不承载业务规则，避免与 services 出现双份实现。
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

from postman_api_tester.services.report_delete_service import (
    delete_report_artifacts as _svc_delete_report_artifacts,
)


logger = logging.getLogger(__name__)


def delete_report_artifacts(
    report_name: str,
    *,
    find_report: Callable[[str], Dict[str, Any]],
    collect_report_artifacts: Callable[[Dict[str, Any]], List[Path]],
    invalidate_reports_cache: Callable[[], None],
) -> List[str]:
    # 删除行为由 service 层实现，这里仅保留路由侧日志与依赖注入。
    logger.info(
        "handler delete report",
        extra={
            "event": "handler.admin.report_delete.forward",
            "report_name": report_name,
        },
    )
    return _svc_delete_report_artifacts(
        report_name,
        find_report=find_report,
        collect_report_artifacts=collect_report_artifacts,
        invalidate_reports_cache=invalidate_reports_cache,
    )


__all__ = ["delete_report_artifacts"]
