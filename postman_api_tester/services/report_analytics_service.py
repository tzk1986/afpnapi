"""Report analytics aggregation service."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence

from postman_api_tester.utils.analytics_utils import (
    ERROR_CATEGORY_ASSERTION,
    ERROR_CATEGORY_AUTH,
    ERROR_CATEGORY_BUSINESS,
    ERROR_CATEGORY_CONNECTION,
    ERROR_CATEGORY_DATABASE,
    ERROR_CATEGORY_UNKNOWN,
    build_histogram,
    build_quantiles,
    classify_error_category,
    distinct_list,
    extract_response_times,
    normalize_error_message,
    parse_rate_text,
    ratio,
    safe_top_items,
    to_int,
)


def _safe_results(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw = report.get("results")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _safe_manual_cases(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw = report.get("manual_cases")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _summary_total(report: Mapping[str, Any], default_total: int) -> int:
    summary = report.get("summary")
    if isinstance(summary, dict):
        return max(default_total, to_int(summary.get("total"), default=default_total))
    return default_total


def _source_total(report: Mapping[str, Any], executed_total: int) -> int:
    source_total = to_int(report.get("source_total_count"), default=-1)
    if source_total >= 0:
        return max(source_total, executed_total)
    return _summary_total(report, executed_total)


def _status_distribution(results: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for item in results:
        status = str(item.get("status") or "UNKNOWN").upper()
        counter[status] += 1
    return {
        "PASSED": counter.get("PASSED", 0),
        "FAILED": counter.get("FAILED", 0),
        "ERROR": counter.get("ERROR", 0),
        "OTHER": sum(value for key, value in counter.items() if key not in {"PASSED", "FAILED", "ERROR"}),
    }


def _method_distribution(results: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for item in results:
        method = str(item.get("method") or "").upper()
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            counter[method] += 1
        else:
            counter["OTHER"] += 1
    return {
        "GET": counter.get("GET", 0),
        "POST": counter.get("POST", 0),
        "PUT": counter.get("PUT", 0),
        "PATCH": counter.get("PATCH", 0),
        "DELETE": counter.get("DELETE", 0),
        "OTHER": counter.get("OTHER", 0),
    }


def _folder_top(results: Sequence[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    for item in results:
        folder = str(item.get("folder") or "(root)").strip() or "(root)"
        counter[folder] += 1
    return [{"folder": folder, "count": count} for folder, count in safe_top_items(dict(counter), top_n)]


def _error_category_summary(error_items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = len(error_items)
    categories = [
        ERROR_CATEGORY_CONNECTION,
        ERROR_CATEGORY_AUTH,
        ERROR_CATEGORY_BUSINESS,
        ERROR_CATEGORY_ASSERTION,
        ERROR_CATEGORY_DATABASE,
        ERROR_CATEGORY_UNKNOWN,
    ]
    counter: Counter[str] = Counter()
    for item in error_items:
        category = classify_error_category(item.get("message"), item.get("err_code"))
        counter[category] += 1
    return [
        {
            "category": category,
            "count": counter.get(category, 0),
            "ratio": ratio(counter.get(category, 0), total),
        }
        for category in categories
    ]


def _error_suggestions(category_summary: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    suggestion_map = {
        ERROR_CATEGORY_CONNECTION: "检查 base_url、网络连通性、DNS 与超时配置，必要时提升读超时。",
        ERROR_CATEGORY_AUTH: "检查 token 注入优先级与有效期，确认环境切换后认证头是否一致。",
        ERROR_CATEGORY_BUSINESS: "核对测试数据前置条件与幂等性，必要时对断言字段做环境差异兜底。",
        ERROR_CATEGORY_ASSERTION: "检查 JSONPath 断言表达式与严格模式配置，避免断言目标字段缺失。",
        ERROR_CATEGORY_DATABASE: "检查 SQL/数据库兼容反馈，确认连接配置与事务前置数据是否可用。",
        ERROR_CATEGORY_UNKNOWN: "补充错误码与 message 规范化规则，提升可观测性并细化分类。",
    }
    suggestions: List[Dict[str, str]] = []
    for row in category_summary:
        category = str(row.get("category") or "")
        count = to_int(row.get("count"), default=0)
        if count <= 0:
            continue
        suggestions.append({"category": category, "suggestion": suggestion_map.get(category, suggestion_map[ERROR_CATEGORY_UNKNOWN])})
    return suggestions


def _frequent_errors(error_items: Sequence[Dict[str, Any]], top_n: int, include_samples: bool) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in error_items:
        normalized = normalize_error_message(item.get("message"))
        row = grouped.setdefault(
            normalized,
            {
                "message": normalized,
                "count": 0,
                "categories": [],
                "samples": [],
            },
        )
        row["count"] = to_int(row.get("count"), default=0) + 1
        category = classify_error_category(item.get("message"), item.get("err_code"))
        categories = row.get("categories")
        if isinstance(categories, list):
            categories.append(category)
        if include_samples:
            samples = row.get("samples")
            if isinstance(samples, list) and len(samples) < 3:
                samples.append(
                    {
                        "name": item.get("name", ""),
                        "method": item.get("method", ""),
                        "url": item.get("url", ""),
                        "status": item.get("status", ""),
                        "err_code": item.get("err_code", ""),
                    }
                )

    rows = sorted(grouped.values(), key=lambda value: (-to_int(value.get("count"), default=0), str(value.get("message") or "")))
    output: List[Dict[str, Any]] = []
    for row in rows[:top_n]:
        categories_raw = row.get("categories")
        if isinstance(categories_raw, list):
            categories = distinct_list([str(item) for item in categories_raw if str(item)])
        else:
            categories = []
        payload: Dict[str, Any] = {
            "message": row.get("message", ""),
            "count": to_int(row.get("count"), default=0),
            "categories": categories,
        }
        if include_samples:
            payload["samples"] = row.get("samples", [])
        output.append(payload)
    return output


def _quality_score(
    *,
    results: Sequence[Dict[str, Any]],
    p95: int,
    failed_penalty: int,
    error_penalty: int,
    slow_penalty: int,
    assertion_missing_penalty: int,
    assertions_enabled: bool,
) -> Dict[str, Any]:
    failed_count = sum(1 for item in results if str(item.get("status") or "").upper() == "FAILED")
    error_count = sum(1 for item in results if str(item.get("status") or "").upper() == "ERROR")
    slow_count = sum(1 for item in results if to_int(item.get("response_time_ms"), default=-1) > p95 and p95 > 0)
    missing_assertion_count = 0
    if assertions_enabled:
        for item in results:
            assertion_results = item.get("assertion_results")
            if not isinstance(assertion_results, list) or len(assertion_results) == 0:
                missing_assertion_count += 1

    failed_points = failed_count * failed_penalty
    error_points = error_count * error_penalty
    slow_points = slow_count * slow_penalty
    assertion_points = missing_assertion_count * assertion_missing_penalty
    total_penalty = failed_points + error_points + slow_points + assertion_points

    stability_score = max(0, min(100, 100 - failed_points - error_points))
    performance_score = max(0, min(100, 100 - slow_points))
    assertion_score = 100 if not assertions_enabled else max(0, min(100, 100 - assertion_points))
    total_score = max(0, min(100, 100 - total_penalty))

    return {
        "total_score": total_score,
        "stability_score": stability_score,
        "performance_score": performance_score,
        "assertion_score": assertion_score,
        "penalties": {
            "failed_count": failed_count,
            "error_count": error_count,
            "slow_count": slow_count,
            "missing_assertion_count": missing_assertion_count,
            "failed_points": failed_points,
            "error_points": error_points,
            "slow_points": slow_points,
            "assertion_points": assertion_points,
            "total_penalty": total_penalty,
        },
    }


def _coverage(report: Mapping[str, Any], results: Sequence[Dict[str, Any]], top_n: int) -> Dict[str, Any]:
    executed_total = len(results)
    source_total = _source_total(report, executed_total)
    manual_cases_total = len(_safe_manual_cases(report))

    execution_coverage = ratio(executed_total, source_total)
    manual_coverage = ratio(manual_cases_total, source_total)

    uncovered_top: List[Dict[str, Any]] = []
    source_items = report.get("source_items")
    if isinstance(source_items, list):
        source_key_map: Dict[str, Dict[str, Any]] = {}
        for item in source_items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if key:
                source_key_map[key] = item
        executed_keys = {str(item.get("key") or "").strip() for item in results if str(item.get("key") or "").strip()}
        missing_keys = sorted([key for key in source_key_map.keys() if key not in executed_keys])
        for key in missing_keys[:top_n]:
            src = source_key_map[key]
            uncovered_top.append(
                {
                    "key": key,
                    "name": src.get("name", ""),
                    "folder": src.get("folder", ""),
                    "method": src.get("method", ""),
                    "url": src.get("url", ""),
                }
            )

    return {
        "source_total": source_total,
        "executed_total": executed_total,
        "manual_cases_total": manual_cases_total,
        "execution_coverage": execution_coverage,
        "manual_coverage": manual_coverage,
        "uncovered_top": uncovered_top,
    }


def _trend(
    *,
    report: Mapping[str, Any],
    reports: Sequence[Dict[str, Any]],
    trend_limit: int,
) -> Dict[str, List[Dict[str, Any]]]:
    collection_name = str(report.get("collection_name") or "").strip()
    source_file = str(report.get("source_original_file") or report.get("source_file") or "").strip()
    related: List[Dict[str, Any]] = []
    for item in reports:
        if not isinstance(item, dict):
            continue
        if collection_name and str(item.get("collection_name") or "").strip() != collection_name:
            continue
        if source_file:
            item_source = str(item.get("source_original_file") or item.get("source_file") or "").strip()
            if item_source and item_source != source_file:
                continue
        related.append(item)

    related = sorted(related, key=lambda row: str(row.get("generated_at") or ""), reverse=True)[:trend_limit]
    ordered = list(reversed(related))
    success_rate: List[Dict[str, Any]] = []
    avg_response_ms: List[Dict[str, Any]] = []
    failed_count: List[Dict[str, Any]] = []
    for item in ordered:
        raw_summary = item.get("summary")
        summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
        report_name = str(item.get("report_name") or "")
        generated_at = str(item.get("generated_at") or "")
        success_rate.append(
            {
                "report_name": report_name,
                "generated_at": generated_at,
                "value": parse_rate_text(summary.get("success_rate", "0%")),
            }
        )
        avg_response_ms.append(
            {
                "report_name": report_name,
                "generated_at": generated_at,
                "value": to_int(summary.get("avg_response_ms"), default=0),
            }
        )
        failed_count.append(
            {
                "report_name": report_name,
                "generated_at": generated_at,
                "value": to_int(summary.get("failed"), default=0),
            }
        )
    return {
        "success_rate": success_rate,
        "avg_response_ms": avg_response_ms,
        "failed_count": failed_count,
    }


def build_report_analytics_payload(
    *,
    report: Mapping[str, Any],
    reports: Sequence[Dict[str, Any]],
    top_n: int,
    trend_limit: int,
    include_samples: bool,
    histogram_buckets: Sequence[int],
    failed_penalty: int,
    error_penalty: int,
    slow_penalty: int,
    assertion_missing_penalty: int,
    assertions_enabled: bool,
) -> Dict[str, Any]:
    results = _safe_results(report)
    response_times = extract_response_times(results)
    quantiles = build_quantiles(response_times)

    distributions = {
        "status": _status_distribution(results),
        "method": _method_distribution(results),
        "folder_top": _folder_top(results, top_n=top_n),
    }
    performance = {
        "histogram": build_histogram(response_times, histogram_buckets),
        "quantiles": quantiles,
    }

    error_items = [
        item
        for item in results
        if str(item.get("status") or "").upper() in {"FAILED", "ERROR"}
    ]
    category_summary = _error_category_summary(error_items)
    diagnostics = {
        "category_summary": category_summary,
        "frequent_errors": _frequent_errors(error_items, top_n=top_n, include_samples=include_samples),
        "suggestions": _error_suggestions(category_summary),
    }

    quality_score = _quality_score(
        results=results,
        p95=to_int(quantiles.get("p95"), default=0),
        failed_penalty=failed_penalty,
        error_penalty=error_penalty,
        slow_penalty=slow_penalty,
        assertion_missing_penalty=assertion_missing_penalty,
        assertions_enabled=assertions_enabled,
    )
    coverage = _coverage(report, results, top_n=top_n)
    trend = _trend(report=report, reports=reports, trend_limit=trend_limit)

    summary_snapshot = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "report_name": str(report.get("report_name") or ""),
        "summary_snapshot": summary_snapshot,
        "distributions": distributions,
        "performance": performance,
        "diagnostics": diagnostics,
        "quality_score": quality_score,
        "coverage": coverage,
        "trend": trend,
    }


def build_report_analytics_compare_payload(
    *,
    left_report: Mapping[str, Any],
    right_report: Mapping[str, Any],
    reports: Sequence[Dict[str, Any]],
    top_n: int,
    trend_limit: int,
    include_samples: bool,
    histogram_buckets: Sequence[int],
    failed_penalty: int,
    error_penalty: int,
    slow_penalty: int,
    assertion_missing_penalty: int,
    assertions_enabled: bool,
) -> Dict[str, Any]:
    left_snapshot = build_report_analytics_payload(
        report=left_report,
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
    right_snapshot = build_report_analytics_payload(
        report=right_report,
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

    left_summary_raw = left_snapshot.get("summary_snapshot")
    right_summary_raw = right_snapshot.get("summary_snapshot")
    left_quality_raw = left_snapshot.get("quality_score")
    right_quality_raw = right_snapshot.get("quality_score")

    left_summary: Mapping[str, Any] = left_summary_raw if isinstance(left_summary_raw, dict) else {}
    right_summary: Mapping[str, Any] = right_summary_raw if isinstance(right_summary_raw, dict) else {}
    left_quality: Mapping[str, Any] = left_quality_raw if isinstance(left_quality_raw, dict) else {}
    right_quality: Mapping[str, Any] = right_quality_raw if isinstance(right_quality_raw, dict) else {}

    success_rate_delta = round(
        parse_rate_text(right_summary.get("success_rate", "0%")) - parse_rate_text(left_summary.get("success_rate", "0%")),
        2,
    )
    avg_response_delta_ms = to_int(right_summary.get("avg_response_ms"), default=0) - to_int(left_summary.get("avg_response_ms"), default=0)
    failed_delta = to_int(right_summary.get("failed"), default=0) - to_int(left_summary.get("failed"), default=0)
    error_delta = to_int(right_summary.get("error"), default=0) - to_int(left_summary.get("error"), default=0)
    score_delta = round(
        float(to_int(right_quality.get("total_score"), default=0) - to_int(left_quality.get("total_score"), default=0)),
        2,
    )

    return {
        "left_snapshot": left_snapshot,
        "right_snapshot": right_snapshot,
        "delta": {
            "success_rate_delta": success_rate_delta,
            "avg_response_delta_ms": avg_response_delta_ms,
            "failed_delta": failed_delta,
            "error_delta": error_delta,
        },
        "score_delta": score_delta,
    }
