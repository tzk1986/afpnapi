"""Analytics utility helpers for report aggregation."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


ERROR_CATEGORY_CONNECTION = "connection"
ERROR_CATEGORY_AUTH = "auth"
ERROR_CATEGORY_BUSINESS = "business"
ERROR_CATEGORY_ASSERTION = "assertion"
ERROR_CATEGORY_DATABASE = "database"
ERROR_CATEGORY_UNKNOWN = "unknown"


def clamp_int(value: object, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def parse_histogram_buckets(text: str) -> List[int]:
    numbers: List[int] = []
    for part in str(text or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value >= 0:
            numbers.append(value)
    if not numbers:
        return [0, 50, 100, 200, 500, 1000, 3000, 5000]
    return sorted(set(numbers))


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def parse_rate_text(value: object) -> float:
    text = str(value or "").strip().replace("%", "")
    return to_float(text, default=0.0)


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def normalize_error_message(message: object) -> str:
    normalized = normalize_text(message)
    if not normalized:
        return "(empty message)"
    normalized = re.sub(r"\b\d{2,}\b", "{n}", normalized)
    normalized = re.sub(r"\b[0-9a-f]{8,}\b", "{id}", normalized)
    normalized = re.sub(r"/\d+", "/{n}", normalized)
    return normalized


def extract_response_times(results: Sequence[Dict[str, Any]]) -> List[int]:
    times: List[int] = []
    for item in results:
        value = to_int(item.get("response_time_ms"), default=-1)
        if value >= 0:
            times.append(value)
    return times


def percentile(values: Sequence[int], q: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return int(values[0])
    sorted_values = sorted(values)
    rank = max(0.0, min(1.0, q)) * (len(sorted_values) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return int(sorted_values[low])
    weight = rank - low
    interpolated = sorted_values[low] + (sorted_values[high] - sorted_values[low]) * weight
    return int(round(interpolated))


def build_quantiles(values: Sequence[int]) -> Dict[str, int]:
    if not values:
        return {"avg": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0}
    avg = int(round(sum(values) / len(values)))
    return {
        "avg": avg,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
    }


def build_histogram(values: Sequence[int], buckets: Sequence[int]) -> List[Dict[str, object]]:
    limits = sorted(set(int(v) for v in buckets))
    if not limits:
        limits = [0, 50, 100, 200, 500, 1000, 3000, 5000]
    counts = [0 for _ in range(len(limits))]
    for value in values:
        idx = len(limits) - 1
        for i in range(1, len(limits)):
            if value < limits[i]:
                idx = i - 1
                break
        counts[idx] += 1

    rows: List[Dict[str, object]] = []
    for i, count in enumerate(counts):
        min_value = limits[i]
        if i < len(limits) - 1:
            max_value = limits[i + 1]
            label = f"[{min_value}, {max_value})"
            rows.append(
                {
                    "bucket": label,
                    "min_inclusive": min_value,
                    "max_exclusive": max_value,
                    "count": count,
                }
            )
        else:
            label = f"[{min_value}, +inf)"
            rows.append(
                {
                    "bucket": label,
                    "min_inclusive": min_value,
                    "max_exclusive": None,
                    "count": count,
                }
            )
    return rows


def classify_error_category(message: object, err_code: object) -> str:
    text = f"{normalize_text(err_code)} {normalize_text(message)}"
    if any(keyword in text for keyword in ("timeout", "timed out", "connection", "refused", "dns", "network", "ssl", "tls")):
        return ERROR_CATEGORY_CONNECTION
    if any(keyword in text for keyword in ("unauthorized", "forbidden", "token", "expired", "login", "鉴权", "认证", "权限")):
        return ERROR_CATEGORY_AUTH
    if any(keyword in text for keyword in ("assert", "jsonpath", "expected", "断言", "校验")):
        return ERROR_CATEGORY_ASSERTION
    if any(keyword in text for keyword in ("sql", "mysql", "postgres", "database", "db", "constraint", "数据库")):
        return ERROR_CATEGORY_DATABASE
    if any(keyword in text for keyword in ("business", "biz", "invalid", "参数", "业务", "不合法", "重复", "不存在")):
        return ERROR_CATEGORY_BUSINESS
    return ERROR_CATEGORY_UNKNOWN


def ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100.0, 2)


def safe_top_items(counter: Dict[str, int], top_n: int) -> List[Tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:top_n]


def distinct_list(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
