"""报告元数据、手动用例与结果判定路由处理函数。"""

import logging
import uuid
from functools import partial
from typing import Any, Dict

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import (
    BaseHandler,
    get_report_or_error,
    json_error as _json_error,
)
from postman_api_tester.exceptions import ValidationError
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
    """报告列表 API。"""
    return jsonify(_repo_list_reports())


def api_report_detail(report_name: str) -> ResponseReturnValue:
    """报告元数据详情 API。错误码：RPT_META_001"""
    report = get_report_or_error(report_name, "RPT_META_001")
    if isinstance(report, tuple):
        return report
    return jsonify(build_report_meta_payload(report))


def api_manual_cases(report_name: str) -> ResponseReturnValue:
    """人工用例列表 API。错误码：RPT_META_002"""
    report = get_report_or_error(report_name, "RPT_META_002")
    if isinstance(report, tuple):
        return report

    payload = build_manual_cases_payload(
        report_name=report_name,
        report=report,
        default_folder=MANUAL_CASE_FOLDER_NAME,
        enabled=ENABLE_MANUAL_CASES,
    )
    return jsonify(payload)


def api_manual_case_add() -> ResponseReturnValue:
    """新增人工用例 API。错误码：RPT_MANUAL_001-004"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    if not report_name:
        return _json_error("report_name 不能为空", 400, "RPT_MANUAL_001")
    try:
        report_name = BaseHandler.validate_string_length(report_name, "report_name", 255, 1)
    except ValidationError as e:
        return _json_error(str(e), 400, "RPT_MANUAL_001")
    case_payload = dict(payload.get("case") or {})
    if not case_payload:
        return _json_error("case 不能为空", 400, "RPT_MANUAL_002")
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
        return _json_error(f"报告不存在：{report_name}", 404, "RPT_MANUAL_003")
    except ValueError as exc:
        return _json_error(str(exc), 400, "RPT_MANUAL_004")
    except Exception as exc:
        logger.exception("add_manual_case error")
        return _json_error(f"操作异常：{type(exc).__name__}", 500, "RPT_MANUAL_004")
    return jsonify(build_manual_case_upsert_payload(report_name=report_name, result=result))


def api_manual_case_update() -> ResponseReturnValue:
    """更新人工用例 API。错误码：RPT_MANUAL_005-008"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    case_payload = dict(payload.get("case") or {})
    try:
        report_name = BaseHandler.validate_non_empty_string(report_name, "report_name")
        case_id = BaseHandler.validate_non_empty_string(case_id, "case_id", 100)
    except ValidationError as e:
        error_code = "RPT_MANUAL_005" if "report_name" in str(e) else "RPT_MANUAL_006"
        return _json_error(str(e), 400, error_code)
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
        return _json_error(str(exc), 404, "RPT_MANUAL_007")
    except ValueError as exc:
        return _json_error(str(exc), 400, "RPT_MANUAL_008")
    except Exception as exc:
        logger.exception("update_manual_case error")
        return _json_error(f"操作异常：{type(exc).__name__}", 500, "RPT_MANUAL_008")
    return jsonify(build_manual_case_upsert_payload(report_name=report_name, result=result))


def api_manual_case_delete() -> ResponseReturnValue:
    """删除人工用例 API。错误码：RPT_MANUAL_009-012"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    case_id = str(payload.get("case_id") or "").strip()
    try:
        report_name = BaseHandler.validate_non_empty_string(report_name, "report_name")
        case_id = BaseHandler.validate_non_empty_string(case_id, "case_id", 100)
    except ValidationError as e:
        error_code = "RPT_MANUAL_009" if "report_name" in str(e) else "RPT_MANUAL_010"
        return _json_error(str(e), 400, error_code)
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
        return _json_error(str(exc), 404, "RPT_MANUAL_011")
    except ValueError as exc:
        return _json_error(str(exc), 400, "RPT_MANUAL_012")
    except Exception as exc:
        logger.exception("delete_manual_case error")
        return _json_error(f"操作异常：{type(exc).__name__}", 500, "RPT_MANUAL_012")
    return jsonify(build_manual_case_delete_payload(report_name=report_name, result=result))


def api_report_case_exclusion() -> ResponseReturnValue:
    """用例排除标记 API。错误码：RPT_EXCL_001-004"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name") or "").strip()
    exclusion_key = str(payload.get("exclusion_key") or "").strip()
    from postman_api_tester.report_server_utils import to_bool as _to_bool
    excluded = _to_bool(payload.get("excluded"), default=True)
    try:
        report_name = BaseHandler.validate_non_empty_string(report_name, "report_name")
        exclusion_key = BaseHandler.validate_non_empty_string(exclusion_key, "exclusion_key", 500)
    except ValidationError as e:
        error_code = "RPT_EXCL_001" if "report_name" in str(e) else "RPT_EXCL_002"
        return _json_error(str(e), 400, error_code)
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
        return _json_error(f"报告不存在：{report_name}", 404, "RPT_EXCL_003")
    except ValueError as exc:
        return _json_error(str(exc), 400, "RPT_EXCL_004")
    except Exception as exc:
        logger.exception("set_case_exclusion error")
        return _json_error(f"操作异常：{type(exc).__name__}", 500, "RPT_EXCL_004")
    return jsonify(build_case_exclusion_payload(report_name=report_name, excluded=excluded, result=result))


def api_report_result_judgement() -> ResponseReturnValue:
    """结果人工判定 API。错误码：RPT_JUDGE_001-005"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    try:
        report_name = BaseHandler.validate_non_empty_string(report_name, "report_name")
    except ValidationError as e:
        return _json_error(str(e), 400, "RPT_JUDGE_001")

    raw_result_index = payload.get("result_index")
    if raw_result_index is None:
        return _json_error("result_index 必须是整数", 400, "RPT_JUDGE_002")
    try:
        result_index = int(str(raw_result_index))
    except (TypeError, ValueError):
        return _json_error("result_index 必须是整数", 400, "RPT_JUDGE_002")

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
        return _json_error(f"报告不存在：{report_name}", 404, "RPT_JUDGE_003")
    except IndexError:
        return _json_error(f"结果索引不存在：{result_index}", 404, "RPT_JUDGE_004")
    except ValueError as exc:
        return _json_error(str(exc), 400, "RPT_JUDGE_005")
    except Exception as exc:
        logger.exception("set_result_judgement error")
        return _json_error(f"操作异常：{type(exc).__name__}", 500, "RPT_JUDGE_005")

    return jsonify(
        build_result_judgement_payload(
            report_name=report_name,
            result_index=result_index,
            action=action,
            result=result,
        )
    )
