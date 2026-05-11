from datetime import datetime
from typing import Any, Callable, Dict, List


def add_manual_case(
    report_name: str,
    payload: Dict[str, Any],
    *,
    enable_manual_cases: bool,
    default_folder_name: str,
    normalize_manual_case: Callable[[Dict[str, Any], str], Dict[str, Any]],
    update_report_meta: Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]],
    create_id: Callable[[], str],
) -> Dict[str, Any]:
    if not enable_manual_cases:
        raise ValueError("当前环境未启用人工用例能力。")

    case = normalize_manual_case(payload, str(payload.get("folder") or default_folder_name))
    if not case.get("id"):
        case["id"] = create_id()
    if not case.get("created_at"):
        case["created_at"] = datetime.now().isoformat()
    if not case.get("name"):
        raise ValueError("name 不能为空")
    if not case.get("url"):
        raise ValueError("url 不能为空")

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        manual_cases = [c for c in meta.get("manual_cases", []) if isinstance(c, dict)]
        manual_cases.append(case)
        meta["manual_cases"] = manual_cases
        return meta

    updated_meta = update_report_meta(report_name, updater)
    return {"case": case, "manual_cases": updated_meta.get("manual_cases", [])}


def update_manual_case(
    report_name: str,
    case_id: str,
    payload: Dict[str, Any],
    *,
    enable_manual_cases: bool,
    default_folder_name: str,
    normalize_manual_case: Callable[[Dict[str, Any], str], Dict[str, Any]],
    update_report_meta: Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    if not enable_manual_cases:
        raise ValueError("当前环境未启用人工用例能力。")
    case_id = str(case_id or "").strip()
    if not case_id:
        raise ValueError("case_id 不能为空")

    holder: Dict[str, Any] = {}

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        manual_cases = [c for c in meta.get("manual_cases", []) if isinstance(c, dict)]
        found = False
        updated: List[Dict[str, Any]] = []
        for raw in manual_cases:
            if str(raw.get("id") or "") != case_id:
                updated.append(raw)
                continue
            merged = dict(raw)
            merged.update(payload)
            normalized = normalize_manual_case(merged, str(merged.get("folder") or default_folder_name))
            normalized["id"] = case_id
            updated.append(normalized)
            holder["case"] = normalized
            found = True
        if not found:
            raise FileNotFoundError(f"未找到指定人工用例: {case_id}")
        meta["manual_cases"] = updated
        return meta

    updated_meta = update_report_meta(report_name, updater)
    return {"case": holder.get("case"), "manual_cases": updated_meta.get("manual_cases", [])}


def delete_manual_case(
    report_name: str,
    case_id: str,
    *,
    enable_manual_cases: bool,
    manual_case_exclusion_key: Callable[[Dict[str, Any]], str],
    normalize_manual_exclusions: Callable[[List[str]], List[str]],
    update_report_meta: Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    if not enable_manual_cases:
        raise ValueError("当前环境未启用人工用例能力。")
    case_id = str(case_id or "").strip()
    if not case_id:
        raise ValueError("case_id 不能为空")

    removed_key = ""

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal removed_key
        manual_cases = [c for c in meta.get("manual_cases", []) if isinstance(c, dict)]
        kept: List[Dict[str, Any]] = []
        found = False
        for item in manual_cases:
            if str(item.get("id") or "") == case_id:
                removed_key = manual_case_exclusion_key(item)
                found = True
                continue
            kept.append(item)
        if not found:
            raise FileNotFoundError(f"未找到指定人工用例: {case_id}")
        meta["manual_cases"] = kept
        exclusions = [x for x in normalize_manual_exclusions(meta.get("manual_exclusions") or []) if x != removed_key]
        meta["manual_exclusions"] = exclusions
        return meta

    updated_meta = update_report_meta(report_name, updater)
    return {"manual_cases": updated_meta.get("manual_cases", [])}


def set_case_exclusion(
    report_name: str,
    exclusion_key: str,
    excluded: bool,
    *,
    normalize_exclusion_key: Callable[[str], str],
    normalize_manual_exclusions: Callable[[List[str]], List[str]],
    update_report_meta: Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    exclusion_key = normalize_exclusion_key(exclusion_key)
    if not exclusion_key:
        raise ValueError("exclusion_key 不能为空")

    def updater(meta: Dict[str, Any]) -> Dict[str, Any]:
        exclusions = normalize_manual_exclusions(meta.get("manual_exclusions") or [])
        exclusion_set = set(exclusions)
        if excluded:
            exclusion_set.add(exclusion_key)
        else:
            exclusion_set.discard(exclusion_key)
        meta["manual_exclusions"] = sorted(exclusion_set)
        return meta

    updated_meta = update_report_meta(report_name, updater)
    return {"manual_exclusions": updated_meta.get("manual_exclusions", [])}
