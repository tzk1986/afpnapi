"""Handler for report analytics route orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from postman_api_tester.services.report_analytics_service import (
    build_report_analytics_compare_payload,
    build_report_analytics_payload,
)
from postman_api_tester.utils.analytics_utils import clamp_int, parse_histogram_buckets


def _to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def normalize_analytics_query_params(
    *,
    top_n_raw: object,
    trend_limit_raw: object,
    include_samples_raw: object,
    top_n_default: int,
    top_n_max: int,
    trend_limit_default: int,
    trend_limit_max: int,
    include_samples_default: bool,
) -> Dict[str, Any]:
    top_n = clamp_int(top_n_raw, minimum=1, maximum=top_n_max, default=top_n_default)
    trend_limit = clamp_int(trend_limit_raw, minimum=1, maximum=trend_limit_max, default=trend_limit_default)
    include_samples = _to_bool(include_samples_raw, default=include_samples_default)
    return {
        "top_n": top_n,
        "trend_limit": trend_limit,
        "include_samples": include_samples,
    }


def build_analytics_payload(
    *,
    report: Mapping[str, Any],
    reports: Sequence[Dict[str, Any]],
    top_n: int,
    trend_limit: int,
    include_samples: bool,
    histogram_buckets_text: str,
    failed_penalty: int,
    error_penalty: int,
    slow_penalty: int,
    assertion_missing_penalty: int,
    assertions_enabled: bool,
) -> Dict[str, Any]:
    histogram_buckets: List[int] = parse_histogram_buckets(histogram_buckets_text)
    return build_report_analytics_payload(
        report=report,
        reports=reports,
        top_n=top_n,
        trend_limit=trend_limit,
        include_samples=include_samples,
        histogram_buckets=histogram_buckets,
        failed_penalty=failed_penalty,
        error_penalty=error_penalty,
        slow_penalty=slow_penalty,
        assertion_missing_penalty=assertion_missing_penalty,
        assertions_enabled=assertions_enabled,
    )


def build_analytics_compare_payload(
    *,
    left_report: Mapping[str, Any],
    right_report: Mapping[str, Any],
    reports: Sequence[Dict[str, Any]],
    top_n: int,
    trend_limit: int,
    include_samples: bool,
    histogram_buckets_text: str,
    failed_penalty: int,
    error_penalty: int,
    slow_penalty: int,
    assertion_missing_penalty: int,
    assertions_enabled: bool,
) -> Dict[str, Any]:
    histogram_buckets: List[int] = parse_histogram_buckets(histogram_buckets_text)
    return build_report_analytics_compare_payload(
        left_report=left_report,
        right_report=right_report,
        reports=reports,
        top_n=top_n,
        trend_limit=trend_limit,
        include_samples=include_samples,
        histogram_buckets=histogram_buckets,
        failed_penalty=failed_penalty,
        error_penalty=error_penalty,
        slow_penalty=slow_penalty,
        assertion_missing_penalty=assertion_missing_penalty,
        assertions_enabled=assertions_enabled,
    )
