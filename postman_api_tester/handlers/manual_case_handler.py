"""Manual-case handler thin wrappers over service layer."""

from typing import Any, Callable, Dict, List

from postman_api_tester.utils.collection_utils import append_manual_cases_to_collection
from postman_api_tester.services.report_results_service import build_manual_cases_payload
from postman_api_tester.services.report_manual_case_service import (
    add_manual_case as _svc_add_manual_case,
    delete_manual_case as _svc_delete_manual_case,
    set_case_exclusion as _svc_set_case_exclusion,
    update_manual_case as _svc_update_manual_case,
)


def list_manual_cases(
    report_name: str,
    report: Dict[str, Any],
    default_folder: str,
    enabled: bool,
) -> Dict[str, Any]:
    return build_manual_cases_payload(
        report_name=report_name,
        report=report,
        default_folder=default_folder,
        enabled=enabled,
    )


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
    return _svc_add_manual_case(
        report_name,
        payload,
        enable_manual_cases=enable_manual_cases,
        default_folder_name=default_folder_name,
        normalize_manual_case=normalize_manual_case,
        update_report_meta=update_report_meta,
        create_id=create_id,
    )


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
    return _svc_update_manual_case(
        report_name,
        case_id,
        payload,
        enable_manual_cases=enable_manual_cases,
        default_folder_name=default_folder_name,
        normalize_manual_case=normalize_manual_case,
        update_report_meta=update_report_meta,
    )


def delete_manual_case(
    report_name: str,
    case_id: str,
    *,
    enable_manual_cases: bool,
    manual_case_exclusion_key: Callable[[Dict[str, Any]], str],
    normalize_manual_exclusions: Callable[[List[str]], List[str]],
    update_report_meta: Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    return _svc_delete_manual_case(
        report_name,
        case_id,
        enable_manual_cases=enable_manual_cases,
        manual_case_exclusion_key=manual_case_exclusion_key,
        normalize_manual_exclusions=normalize_manual_exclusions,
        update_report_meta=update_report_meta,
    )


def set_case_exclusion(
    report_name: str,
    exclusion_key: str,
    excluded: bool,
    *,
    normalize_exclusion_key: Callable[[str], str],
    normalize_manual_exclusions: Callable[[List[str]], List[str]],
    update_report_meta: Callable[[str, Callable[[Dict[str, Any]], Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    return _svc_set_case_exclusion(
        report_name,
        exclusion_key,
        excluded,
        normalize_exclusion_key=normalize_exclusion_key,
        normalize_manual_exclusions=normalize_manual_exclusions,
        update_report_meta=update_report_meta,
    )


__all__ = [
    "list_manual_cases",
    "add_manual_case",
    "update_manual_case",
    "delete_manual_case",
    "set_case_exclusion",
    "append_manual_cases_to_collection",
]

