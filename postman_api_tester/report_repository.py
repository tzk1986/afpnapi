"""报告仓储聚合模块。

开发导读:
- 统一聚合元数据仓储与详情文件读取能力。
- 对外提供报告列表缓存、单报告查询与详情映射加载。
"""

import json
import time as _time
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

from postman_api_tester.report_meta_repository import (
    legacy_postman_html_files,
    load_legacy_postman_report,
    load_report_meta,
    report_meta_files,
)
from postman_api_tester.utils.file_utils import safe_report_artifact


_REPORTS_DIR: Path = Path("reports").resolve()
_REPORTS_CACHE_TTL = 30.0


ReportRecord = Dict[str, object]
ReportDetailsEntry = Dict[str, object]
ReportDetailsMap = Dict[str, ReportDetailsEntry]


class _ReportsCache(TypedDict):
    data: Optional[List[ReportRecord]]
    by_name: Optional[Dict[str, ReportRecord]]
    ts: float


_REPORTS_CACHE: _ReportsCache = {"data": None, "by_name": None, "ts": 0.0}


def configure_report_repository(reports_dir: Path, cache_ttl: float = 30.0) -> None:
    global _REPORTS_DIR, _REPORTS_CACHE_TTL
    _REPORTS_DIR = Path(reports_dir).resolve()
    try:
        _REPORTS_CACHE_TTL = float(cache_ttl)
    except (TypeError, ValueError):
        _REPORTS_CACHE_TTL = 30.0


def invalidate_reports_cache() -> None:
    """主动清理报告列表缓存。"""
    _REPORTS_CACHE["data"] = None
    _REPORTS_CACHE["by_name"] = None
    _REPORTS_CACHE["ts"] = 0.0


def load_report_details_map(report: ReportRecord) -> ReportDetailsMap:
    details_file = str(report.get("details_file") or "").strip()
    if not details_file:
        return {}
    details_path = _REPORTS_DIR / details_file
    if not details_path.exists():
        return {}
    try:
        with details_path.open("r", encoding="utf-8") as file:
            details = json.load(file)
        if not isinstance(details, dict):
            return {}
        return {
            str(key): value
            for key, value in details.items()
            if isinstance(value, dict)
        }
    except Exception:
        return {}


def _is_total_report_name(report_name: str) -> bool:
    return "_page_" not in str(report_name or "").lower()


def list_reports() -> List[ReportRecord]:
    _now = _time.monotonic()
    if _REPORTS_CACHE["data"] is not None and (_now - _REPORTS_CACHE["ts"]) < _REPORTS_CACHE_TTL:
        return list(_REPORTS_CACHE["data"])

    reports: List[ReportRecord] = []
    seen_report_names = set()

    for meta_path in report_meta_files():
        try:
            report = load_report_meta(meta_path, include_results=False)
            report["meta_file"] = meta_path.name
            reports.append(report)
            seen_report_names.add(report.get("report_name"))
        except Exception as exc:
            reports.append({
                "report_name": meta_path.name,
                "generated_at": "",
                "host_name": "",
                "collection_name": "",
                "source_file": "",
                "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "success_rate": "0%"},
                "load_error": str(exc),
                "results": [],
                "_summary_only": True,
            })

    for html_path in legacy_postman_html_files():
        if html_path.name in seen_report_names:
            continue
        try:
            reports.append(load_legacy_postman_report(html_path))
        except Exception:
            continue

    # Final guard: regardless of data source, do not expose paged child reports.
    reports = [item for item in reports if _is_total_report_name(str(item.get("report_name", "") or ""))]

    reports.sort(key=lambda item: str(item.get("generated_at", "") or ""), reverse=True)

    _REPORTS_CACHE["data"] = reports
    _REPORTS_CACHE["by_name"] = {str(item.get("report_name") or ""): item for item in reports}
    _REPORTS_CACHE["ts"] = _time.monotonic()
    return list(reports)


def find_report(report_name: str) -> ReportRecord:
    reports_by_name = _REPORTS_CACHE.get("by_name")
    if reports_by_name is None or _REPORTS_CACHE.get("data") is None:
        list_reports()
        reports_by_name = _REPORTS_CACHE.get("by_name")
    if reports_by_name and report_name in reports_by_name:
        report = reports_by_name[report_name]
        if bool(report.get("_summary_only")):
            meta_file = str(report.get("meta_file") or "").strip()
            if not meta_file:
                raise FileNotFoundError(report_name)
            meta_path = _REPORTS_DIR / meta_file
            full_report = load_report_meta(meta_path, include_results=True)
            full_report["meta_file"] = meta_file
            cache_by_name = _REPORTS_CACHE.get("by_name")
            if cache_by_name is None:
                cache_by_name = {}
                _REPORTS_CACHE["by_name"] = cache_by_name
            cache_by_name[report_name] = full_report
            cached_data = _REPORTS_CACHE.get("data") or []
            for index, item in enumerate(cached_data):
                if str(item.get("report_name") or "") == report_name:
                    cached_data[index] = full_report
                    break
            _REPORTS_CACHE["data"] = cached_data
            return full_report
        return report
    raise FileNotFoundError(report_name)


def collect_report_artifacts(report: ReportRecord) -> List[Path]:
    artifacts: List[Path] = []
    seen: set[str] = set()

    for file_name in (
        report.get("report_name", ""),
        report.get("details_file", ""),
        report.get("meta_file", ""),
    ):
        path = safe_report_artifact(_REPORTS_DIR, str(file_name or ""))
        if path is not None and path.name not in seen:
            artifacts.append(path)
            seen.add(path.name)

    report_name = str(report.get("report_name") or "").strip()
    report_stem = Path(report_name).stem
    if report_stem:
        for page_path in sorted(_REPORTS_DIR.glob(f"{report_stem}_page_*.html")):
            resolved = page_path.resolve()
            try:
                resolved.relative_to(_REPORTS_DIR)
            except ValueError:
                continue
            if resolved.name not in seen:
                artifacts.append(resolved)
                seen.add(resolved.name)

    return artifacts

