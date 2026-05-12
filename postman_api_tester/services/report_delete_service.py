from pathlib import Path
from typing import Any, Callable, Dict, List


def delete_report_artifacts(
    report_name: str,
    *,
    find_report: Callable[[str], Dict[str, Any]],
    collect_report_artifacts: Callable[[Dict[str, Any]], List[Path]],
    invalidate_reports_cache: Callable[[], None],
) -> List[str]:
    report = find_report(report_name)
    artifacts = collect_report_artifacts(report)
    deleted_files: List[str] = []
    for artifact in artifacts:
        if artifact.exists() and artifact.is_file():
            artifact.unlink()
            deleted_files.append(artifact.name)

    invalidate_reports_cache()
    return deleted_files
