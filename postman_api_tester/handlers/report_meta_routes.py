"""报告元数据、手动用例与结果判定路由处理函数。"""

import logging
import uuid
from functools import partial
from typing import Any, Dict

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error
from postman_api_tester.services.report_manual_case_service import (
    add_manual_case as _svc_add_manual_case,
    delete_manual_case as _svc_delete_manual_case,
    set_case_exclusion as _svc_set_case_exclusion,
    update_manual_case as _svc_update_manual_case,
)
from postman_api_tester.report_server_config import (
    ENABLE_MANUAL_CASES,
    MANUAL_CASE_FOLDER_NAME,
)
from postman_api_tester.report_server_utils import (
    manual_case_exclusion_key as _manual_case_exclusion_key,
    normalize_exclusion_key as _normalize_exclusion_key,
    normalize_manual_case as _normalize_manual_case,
    normalize_manual_exclusions as _normalize_manual_exclusions,
)
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_repository import (
    find_report as _repo_find_report,
    invalidate_reports_cache as _repo_invalidate_reports_cache,
    list_reports as _repo_list_reports,
)
from postman_api_tester.services.report_judgement_service import (
    set_report_result_judgement as _svc_set_report_result_judgement,
)
from postman_api_tester.services.report_lock_service import get_report_write_lock
from postman_api_tester.services.report_meta_update_service import (
    update_report_meta as _svc_update_report_meta,
)
from postman_api_tester.services.report_results_service import (
    build_case_exclusion_payload,
    build_manual_case_delete_payload,
    build_manual_case_upsert_payload,
    build_manual_cases_payload,
    build_report_meta_payload,
    build_result_judgement_payload,
)
from postman_api_tester.utils.report_utils import compute_summary as _utils_compute_summary

logger = logging.getLogger(__name__)

REPORTS_DIR = ReportServerApp._resolve_reports_dir()

_UPDATE_REPORT_META_FN = partial(
    _svc_update_report_meta,
    reports_dir=REPORTS_DIR,
    get_report_write_lock=get_report_write_lock,
    find_report=_repo_find_report,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)


def api_reports() -> ResponseReturnValue:
    return jsonify(_repo_list_reports())


def api_report_detail(report_name: str) -> ResponseReturnValue:
    try:
        return jsonify(build_report_meta_payload(_repo_find_report(report_name)))
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)


def api_manual_cases(report_name: str) -> ResponseReturnValue:
    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)

    payload = build_manual_cases_payload(
        report_name=report_name,
        report=report,
        default_folder=MANUAL_CASE_FOLDER_NAME,
        enabled=ENABLE_MANUAL_CASES,
    )
    return jsonify(payload)


def api_manual_case_add() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    case_payload = dict(payload.get("case") or {})
    if not case_payload:
        return _json_error("case 不能为空", 400)
    try:
        result = _svc_add_manual_case(
            report_name=report_name,
            payload=case_payload,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            default_folder_name=MANUAL_CASE_FOLDER_NAME,
            normalize_manual_case=_normalize_manual_case,
            update_report_meta=_UPDATE_REPORT_META_FN,
            create_id=lambda: uuid.uuid4().hex,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_manual_case_upsert_payload(report_name=report_name, result=result))


def api_manual_case_update() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    case_payload = dict(payload.get("case") or {})
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    if not case_id:
        return _json_error("case_id 不能为空", 400)
    try:
        result = _svc_update_manual_case(
            report_name=report_name,
            case_id=case_id,
            payload=case_payload,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            default_folder_name=MANUAL_CASE_FOLDER_NAME,
            normalize_manual_case=_normalize_manual_case,
            update_report_meta=_UPDATE_REPORT_META_FN,
        )
    except FileNotFoundError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_manual_case_upsert_payload(report_name=report_name, result=result))


def api_manual_case_delete() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    if not case_id:
        return _json_error("case_id 不能为空", 400)
    try:
        result = _svc_delete_manual_case(
            report_name=report_name,
            case_id=case_id,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            manual_case_exclusion_key=_manual_case_exclusion_key,
            normalize_manual_exclusions=_normalize_manual_exclusions,
            update_report_meta=_UPDATE_REPORT_META_FN,
        )
    except FileNotFoundError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_manual_case_delete_payload(report_name=report_name, result=result))


def api_report_case_exclusion() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    exclusion_key = str(payload.get("exclusion_key") or "").strip()
    from postman_api_tester.report_server_utils import to_bool as _to_bool
    excluded = _to_bool(payload.get("excluded"), default=True)
    if not report_name:
        return _json_error("report_name 不能为空", 400)
    if not exclusion_key:
        return _json_error("exclusion_key 不能为空", 400)
    try:
        result = _svc_set_case_exclusion(
            report_name=report_name,
            exclusion_key=exclusion_key,
            excluded=excluded,
            normalize_exclusion_key=_normalize_exclusion_key,
            normalize_manual_exclusions=_normalize_manual_exclusions,
            update_report_meta=_UPDATE_REPORT_META_FN,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    except Exception as exc:
        return _json_error(str(exc), 400)
    return jsonify(build_case_exclusion_payload(report_name=report_name, excluded=excluded, result=result))


def api_report_result_judgement() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400)

    raw_result_index = payload.get("result_index")
    if raw_result_index is None:
        return _json_error("result_index 必须是整数", 400)
    try:
        result_index = int(str(raw_result_index))
    except (TypeError, ValueError):
        return _json_error("result_index 必须是整数", 400)

    action = str(payload.get("action") or "override").strip().lower()
    target_status = str(payload.get("target_status") or "").strip().upper() or None
    reason = str(payload.get("reason") or "").strip()

    try:
        result = _svc_set_report_result_judgement(
            report_name=report_name,
            result_index=result_index,
            action=action,
            target_status=target_status,
            reason=reason,
            reports_dir=REPORTS_DIR,
            get_report_write_lock=get_report_write_lock,
            find_report=_repo_find_report,
            compute_summary=_utils_compute_summary,
            invalidate_reports_cache=_repo_invalidate_reports_cache,
        )
    except FileNotFoundError:
        return _json_error(f"报告不存在: {report_name}", 404)
    except IndexError:
        return _json_error(f"结果索引不存在: {result_index}", 404)
    except Exception as exc:
        return _json_error(str(exc), 400)

    return jsonify(
        build_result_judgement_payload(
            report_name=report_name,
            result_index=result_index,
            action=action,
            result=result,
        )
    )
