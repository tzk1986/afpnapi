from typing import Callable, Dict, List


def delete_report_artifacts(
    report_name: str,
    *,
    find_report: Callable[[str], Dict[str, object]],
    collect_report_artifacts: Callable[[Dict[str, object]], List[object]],
    invalidate_reports_cache: Callable[[], None],
) -> List[str]:
    report = find_report(report_name)
    artifacts = collect_report_artifacts(report)
    deleted_files: List[str] = []
    for artifact in artifacts:
        exists = getattr(artifact, "exists", None)
        is_file = getattr(artifact, "is_file", None)
        unlink = getattr(artifact, "unlink", None)
        if callable(exists) and callable(is_file) and callable(unlink) and artifact.exists() and artifact.is_file():
            artifact.unlink()
            deleted_files.append(getattr(artifact, "name", str(artifact)))

    invalidate_reports_cache()
    return deleted_files
