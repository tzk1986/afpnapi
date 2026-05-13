import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from postman_api_tester.handlers.collection_handler import extract_collection_preview_items
from postman_api_tester.utils.collection_utils import (
    append_manual_cases_to_collection,
    collect_report_item_paths,
    find_item_fallback,
    item_by_path,
    prune_collection_to_paths,
    remove_excluded_items,
)
from postman_api_tester.report_repository import load_report_details_map
from postman_api_tester.report_server_utils import (
    normalize_manual_case,
    normalize_manual_exclusions,
    sanitize_export_name,
    strip_auth_headers,
)
from postman_api_tester.utils.request_builder import (
    set_request_body,
    set_request_headers,
    set_request_url,
)


def export_collection_with_latest_params(
    report: Dict[str, Any],
    *,
    exports_dir: Path,
    collection_preview_max_items: int,
    enable_manual_cases: bool,
    manual_case_folder_name: str,
    report_export_allow_report_only: bool,
    include_auth: bool = False,
    export_scope: str = "full",
) -> Dict[str, Any]:
    source_file = str(report.get("source_file") or "").strip()
    if not source_file:
        raise ValueError("报告缺少 source_file，无法导出集合。")

    source_path = Path(source_file)
    if not source_path.exists():
        raise FileNotFoundError(f"婧愰泦鍚堟枃浠朵笉瀛樺湪: {source_file}")

    with source_path.open("r", encoding="utf-8") as file:
        collection_data = json.load(file)

    scope = str(export_scope or "full").strip().lower()
    if scope not in {"full", "report_only"}:
        scope = "full"
    if scope == "report_only" and not report_export_allow_report_only:
        scope = "full"

    source_preview_items = extract_collection_preview_items(collection_data, collection_preview_max_items)
    source_total_count = len(source_preview_items)

    details_map = load_report_details_map(report)
    updated_count = 0
    skipped_count = 0
    warnings: List[str] = []

    for index, result in enumerate(report.get("results", [])):
        detail = details_map.get(str(index)) or {}
        request_info_obj = detail.get("request_info") if isinstance(detail, dict) else {}
        request_info = request_info_obj if isinstance(request_info_obj, dict) else {}

        item = item_by_path(collection_data, result.get("item_path") or [])
        if item is None:
            item = find_item_fallback(collection_data, result)
            if item is None:
                skipped_count += 1
                warnings.append(f"索引 {index} 无法定位到集合节点: {result.get('name', '-')}")
                continue

        request_obj = item.setdefault("request", {})
        if not isinstance(request_obj, dict):
            skipped_count += 1
            warnings.append(f"索引 {index} 的 request 结构异常: {result.get('name', '-')}")
            continue

        method = str(result.get("method") or request_obj.get("method") or "GET").upper()
        url = str(result.get("url") or request_obj.get("url") or "").strip()
        headers = dict(request_info.get("headers") or {})
        if not include_auth:
            headers = strip_auth_headers(headers)
        params = dict(request_info.get("params") or {})
        body = request_info.get("body")
        body_mode = request_info.get("body_mode")
        body_data = request_info.get("body_data")

        request_obj["method"] = method
        set_request_url(request_obj, url, params)
        set_request_headers(request_obj, headers)
        set_request_body(request_obj, body, body_mode=body_mode, body_data=body_data)
        updated_count += 1

    final_collection = collection_data
    report_only_count = 0
    scope_effective_same_as_full = False
    if scope == "report_only":
        selected_paths = collect_report_item_paths(report)
        if not selected_paths:
            raise ValueError("导出范围为 report_only 时，报告中缺少可用 item_path。")
        final_collection = prune_collection_to_paths(collection_data, selected_paths)
        pruned_items = extract_collection_preview_items(final_collection, collection_preview_max_items)
        report_only_count = len(pruned_items)
        scope_effective_same_as_full = report_only_count == source_total_count
        if scope_effective_same_as_full:
            warnings.append("当前报告接口与源集合接口一致，report_only 与 full 导出内容相同。")

    manual_cases: List[Dict[str, Any]] = []
    if enable_manual_cases:
        for case in report.get("manual_cases", []):
            if isinstance(case, dict):
                default_folder = str(case.get("folder") or manual_case_folder_name)
                manual_cases.append(normalize_manual_case(case, default_folder))

    manual_exclusions = normalize_manual_exclusions(report.get("manual_exclusions") or [])
    folder_name = str(manual_case_folder_name).strip() or manual_case_folder_name
    appended_manual_count = append_manual_cases_to_collection(
        collection_data=final_collection,
        manual_cases=manual_cases,
        default_folder=folder_name,
        include_auth=include_auth,
    )
    removed_excluded_count = remove_excluded_items(final_collection, manual_exclusions)

    exports_dir.mkdir(parents=True, exist_ok=True)
    preferred_name = report.get("source_original_file") or source_path.name
    source_name = sanitize_export_name(preferred_name)
    stem = Path(source_name).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "latest" if scope == "full" else "report_only"
    export_name = f"{stem}_{suffix}_{timestamp}.json"
    export_path = exports_dir / export_name

    with export_path.open("w", encoding="utf-8") as file:
        json.dump(final_collection, file, indent=2, ensure_ascii=False)

    return {
        "file_name": export_name,
        "file_path": str(export_path),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "export_scope": scope,
        "report_only_count": report_only_count,
        "manual_cases_count": len(manual_cases),
        "manual_case_count": len(manual_cases),
        "appended_manual_count": appended_manual_count,
        "manual_case_exported_count": appended_manual_count,
        "excluded_count": len(manual_exclusions),
        "removed_excluded_count": removed_excluded_count,
        "source_total_count": source_total_count,
        "scope_effective_same_as_full": scope_effective_same_as_full,
        "composition": {
            "updated_requests": updated_count,
            "manual_cases_added": appended_manual_count,
            "excluded_removed": removed_excluded_count,
        },
        "warnings": warnings,
    }

