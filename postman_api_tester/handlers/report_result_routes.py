"""报告结果与分析路由处理函数。"""

from typing import Dict

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.report_server_config import (
    ENABLE_ASSERTIONS,
    ENABLE_REPORT_ANALYTICS,
    QUALITY_SCORE_ASSERTION_MISSING_PENALTY,
    QUALITY_SCORE_ERROR_PENALTY,
    QUALITY_SCORE_FAILED_PENALTY,
    QUALITY_SCORE_SLOW_PENALTY,
    REPORT_ANALYTICS_ENABLE_SAMPLES,
    REPORT_ANALYTICS_HISTOGRAM_BUCKETS,
    REPORT_ANALYTICS_TOP_N_DEFAULT,
    REPORT_ANALYTICS_TOP_N_MAX,
    REPORT_ANALYTICS_TREND_LIMIT_DEFAULT,
    REPORT_ANALYTICS_TREND_LIMIT_MAX,
    REPORT_VIEW_PAGE_SIZE_DEFAULT,
    REPORT_VIEW_PAGE_SIZE_MAX,
    REPORT_VIEW_PAGE_SIZE_MIN,
)
from postman_api_tester.handlers.base_handler import BaseHandler
from postman_api_tester.handlers.report_handler import (
    normalize_status_filter as _normalize_status_filter,
)
from postman_api_tester.services.report_analytics_service import (
    build_report_analytics_compare_payload as _build_analytics_compare_payload,
    build_report_analytics_payload as _build_analytics_payload,
)
from postman_api_tester.utils.analytics_utils import (
    normalize_analytics_query_params as _normalize_analytics_query_params,
    parse_histogram_buckets as _parse_histogram_buckets,
)
from postman_api_tester.report_repository import (
    find_report as _repo_find_report,
    list_reports as _repo_list_reports,
)
from postman_api_tester.report_server_utils import to_bool as _to_bool
from postman_api_tester.services.report_results_service import (
    build_compare_payload,
    build_report_results_payload as _build_report_results_payload,
    build_result_detail_payload,
)
from postman_api_tester.utils.server_utils import clamp_page as _clamp_page
from postman_api_tester.utils.server_utils import clamp_page_size as _clamp_page_size


def api_report_results(report_name: str) -> ResponseReturnValue:
    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"报告不存在: {report_name}"), 404)

    page = _clamp_page(request.args.get("page", 1))
    page_size = _clamp_page_size(
        request.args.get("page_size", REPORT_VIEW_PAGE_SIZE_DEFAULT),
        default=REPORT_VIEW_PAGE_SIZE_DEFAULT,
        min_size=REPORT_VIEW_PAGE_SIZE_MIN,
        max_size=REPORT_VIEW_PAGE_SIZE_MAX,
    )
    keyword = request.args.get("query", "")
    message_keyword = request.args.get("message_query", "")
    err_code_keyword = request.args.get("err_code_query", "")
    status_filter = _normalize_status_filter(request.args.get("status", "all"))
    include_excluded = _to_bool(request.args.get("include_excluded"), default=True)
    payload = _build_report_results_payload(
        report=report,
        page=page,
        page_size=page_size,
        keyword=keyword,
        message_keyword=message_keyword,
        err_code_keyword=err_code_keyword,
        status_filter=status_filter,
        include_excluded=include_excluded,
    )
    return jsonify(payload)


def api_report_analytics(report_name: str) -> ResponseReturnValue:
    if not ENABLE_REPORT_ANALYTICS:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError("当前环境未启用测试结果分析能力。"), 403)

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"报告不存在: {report_name}"), 404)

    params = _normalize_analytics_query_params(
        top_n_raw=request.args.get("top_n"),
        trend_limit_raw=request.args.get("trend_limit"),
        include_samples_raw=request.args.get("include_samples"),
        top_n_default=REPORT_ANALYTICS_TOP_N_DEFAULT,
        top_n_max=REPORT_ANALYTICS_TOP_N_MAX,
        trend_limit_default=REPORT_ANALYTICS_TREND_LIMIT_DEFAULT,
        trend_limit_max=REPORT_ANALYTICS_TREND_LIMIT_MAX,
        include_samples_default=REPORT_ANALYTICS_ENABLE_SAMPLES,
    )
    payload = _build_analytics_payload(
        report=report,
        reports=_repo_list_reports(),
        top_n=int(params["top_n"]),
        trend_limit=int(params["trend_limit"]),
        include_samples=bool(params["include_samples"]),
        histogram_buckets=_parse_histogram_buckets(REPORT_ANALYTICS_HISTOGRAM_BUCKETS),
        failed_penalty=QUALITY_SCORE_FAILED_PENALTY,
        error_penalty=QUALITY_SCORE_ERROR_PENALTY,
        slow_penalty=QUALITY_SCORE_SLOW_PENALTY,
        assertion_missing_penalty=QUALITY_SCORE_ASSERTION_MISSING_PENALTY,
        assertions_enabled=ENABLE_ASSERTIONS,
    )
    return jsonify(payload)


def api_report_analytics_compare() -> ResponseReturnValue:
    if not ENABLE_REPORT_ANALYTICS:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError("当前环境未启用测试结果分析能力。"), 403)

    left_name = str(request.args.get("left", "")).strip()
    right_name = str(request.args.get("right", "")).strip()
    if not left_name or not right_name:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError("left 和 right 参数不能为空"), 400)

    try:
        left_report = _repo_find_report(left_name)
        right_report = _repo_find_report(right_name)
    except FileNotFoundError as exc:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"报告不存在: {exc}"), 404)

    params = _normalize_analytics_query_params(
        top_n_raw=request.args.get("top_n"),
        trend_limit_raw=request.args.get("trend_limit"),
        include_samples_raw=request.args.get("include_samples"),
        top_n_default=REPORT_ANALYTICS_TOP_N_DEFAULT,
        top_n_max=REPORT_ANALYTICS_TOP_N_MAX,
        trend_limit_default=REPORT_ANALYTICS_TREND_LIMIT_DEFAULT,
        trend_limit_max=REPORT_ANALYTICS_TREND_LIMIT_MAX,
        include_samples_default=REPORT_ANALYTICS_ENABLE_SAMPLES,
    )
    payload = _build_analytics_compare_payload(
        left_report=left_report,
        right_report=right_report,
        reports=_repo_list_reports(),
        top_n=int(params["top_n"]),
        trend_limit=int(params["trend_limit"]),
        include_samples=bool(params["include_samples"]),
        histogram_buckets=_parse_histogram_buckets(REPORT_ANALYTICS_HISTOGRAM_BUCKETS),
        failed_penalty=QUALITY_SCORE_FAILED_PENALTY,
        error_penalty=QUALITY_SCORE_ERROR_PENALTY,
        slow_penalty=QUALITY_SCORE_SLOW_PENALTY,
        assertion_missing_penalty=QUALITY_SCORE_ASSERTION_MISSING_PENALTY,
        assertions_enabled=ENABLE_ASSERTIONS,
    )
    return jsonify(payload)


def api_report_result_detail(report_name: str, result_index: int) -> ResponseReturnValue:
    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"报告不存在: {report_name}"), 404)

    try:
        return jsonify(build_result_detail_payload(report, result_index))
    except IndexError:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"结果索引不存在: {result_index}"), 404)


def api_compare() -> ResponseReturnValue:
    left_name = request.args.get("left", "")
    right_name = request.args.get("right", "")
    if not left_name or not right_name:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError("left 和 right 参数不能为空"), 400)
    try:
        left = _repo_find_report(left_name)
        right = _repo_find_report(right_name)
    except FileNotFoundError as exc:
        from postman_api_tester.exceptions import ValidationError
        return BaseHandler.error_response(ValidationError(f"报告不存在: {exc}"), 404)
    return jsonify(build_compare_payload(left, right))
