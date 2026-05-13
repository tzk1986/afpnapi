"""Admin handler thin wrappers over service layer."""

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
