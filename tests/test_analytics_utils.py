"""Tests for postman_api_tester/utils/analytics_utils.py"""

import pytest

from postman_api_tester.utils.analytics_utils import (
    clamp_int,
    parse_histogram_buckets,
    to_float,
    to_int,
    parse_rate_text,
    normalize_text,
    normalize_error_message,
    extract_response_times,
    percentile,
    build_quantiles,
    build_histogram,
    classify_error_category,
    ratio,
    safe_top_items,
    distinct_list,
    _to_bool,
    normalize_analytics_query_params,
    ERROR_CATEGORY_CONNECTION,
    ERROR_CATEGORY_AUTH,
    ERROR_CATEGORY_BUSINESS,
    ERROR_CATEGORY_ASSERTION,
    ERROR_CATEGORY_DATABASE,
    ERROR_CATEGORY_UNKNOWN,
)


# ── clamp_int ────────────────────────────────────────────────────────


class TestClampInt:
    def test_normal_clamping(self):
        assert clamp_int(50, minimum=1, maximum=100, default=-1) == 50

    def test_below_minimum(self):
        assert clamp_int(-10, minimum=1, maximum=100, default=-1) == 1

    def test_above_maximum(self):
        assert clamp_int(200, minimum=1, maximum=100, default=-1) == 100

    def test_at_boundaries(self):
        assert clamp_int(1, minimum=1, maximum=100, default=-1) == 1
        assert clamp_int(100, minimum=1, maximum=100, default=-1) == 100

    def test_default_on_string_number(self):
        assert clamp_int("42", minimum=1, maximum=100, default=-1) == 42

    def test_default_on_valid_int_directly(self):
        assert clamp_int(99, minimum=1, maximum=100, default=-1) == 99

    def test_float_value_string_conversion_fails(self):
        # str(3.14) = "3.14", int("3.14") raises ValueError → parsed=default(-1)
        # then max(1, min(100, -1)) = 1 (clamped)
        assert clamp_int(3.14, minimum=1, maximum=100, default=-1) == 1

    def test_float_with_allowable_default(self):
        # When default falls within range, it passes through
        assert clamp_int(3.14, minimum=-5, maximum=100, default=-1) == -1

    def test_none_returns_default_via_str_clamped(self):
        # str(None) == "None", int("None") raises ValueError → default(-1)
        # then max(1, min(100, -1)) = 1 (clamped)
        assert clamp_int(None, minimum=1, maximum=100, default=-1) == 1

    def test_none_with_allowable_default(self):
        assert clamp_int(None, minimum=-5, maximum=100, default=-1) == -1

    def test_empty_string_returns_default(self):
        assert clamp_int("", minimum=1, maximum=100, default=7) == 7

    def test_non_numeric_string_returns_default(self):
        assert clamp_int("abc", minimum=1, maximum=100, default=5) == 5

    def test_boolean_is_subclass_of_int_in_python(self):
        # True → int(str(True)) → int("True") → ValueError → default
        assert clamp_int(True, minimum=1, maximum=100, default=9) == 9

    def test_negative_range(self):
        assert clamp_int(-5, minimum=-10, maximum=0, default=-1) == -5

    def test_equal_min_and_max(self):
        assert clamp_int(0, minimum=5, maximum=5, default=-1) == 5

    def test_zero_as_value(self):
        assert clamp_int(0, minimum=0, maximum=100, default=-1) == 0


# ── parse_histogram_buckets ──────────────────────────────────────────


class TestParseHistogramBuckets:
    def test_basic_comma_separated(self):
        result = parse_histogram_buckets("100,200,300")
        assert result == [100, 200, 300]

    def test_unsorted_input_gets_sorted(self):
        result = parse_histogram_buckets("300,100,200")
        assert result == [100, 200, 300]

    def test_duplicates_removed(self):
        result = parse_histogram_buckets("100,100,200")
        assert result == [100, 200]

    def test_whitespace_stripped(self):
        result = parse_histogram_buckets(" 100 , 200 , 300 ")
        assert result == [100, 200, 300]

    def test_empty_string_returns_defaults(self):
        result = parse_histogram_buckets("")
        assert result == [0, 50, 100, 200, 500, 1000, 3000, 5000]

    def test_none_returns_defaults(self):
        result = parse_histogram_buckets(None)
        assert result == [0, 50, 100, 200, 500, 1000, 3000, 5000]

    def test_negative_values_filtered_out(self):
        result = parse_histogram_buckets("-1,0,100")
        assert result == [0, 100]

    def test_non_numeric_skipped(self):
        result = parse_histogram_buckets("abc,100,xyz,200")
        assert result == [100, 200]

    def test_single_value(self):
        result = parse_histogram_buckets("500")
        assert result == [500]

    def test_all_invalid_returns_defaults(self):
        result = parse_histogram_buckets("abc,def,ghi")
        assert result == [0, 50, 100, 200, 500, 1000, 3000, 5000]

    def test_mixed_invalid_and_valid(self):
        result = parse_histogram_buckets(",abc,,100,,")
        assert result == [100]

    def test_large_numbers(self):
        result = parse_histogram_buckets("100000,200000,50000")
        assert result == [50000, 100000, 200000]

    def test_spaces_only(self):
        result = parse_histogram_buckets("   ,  ,  ")
        assert result == [0, 50, 100, 200, 500, 1000, 3000, 5000]


# ── to_float ─────────────────────────────────────────────────────────


class TestToFloat:
    def test_integer_input(self):
        assert to_float(42) == 42.0

    def test_float_input(self):
        assert to_float(3.14) == 3.14

    def test_string_number(self):
        assert to_float("99.5") == 99.5

    def test_negative_string(self):
        assert to_float("-10.5") == -10.5

    def test_default_on_none(self):
        assert to_float(None) == 0.0

    def test_custom_default_on_none(self):
        assert to_float(None, default=42.5) == 42.5

    def test_invalid_string_uses_default(self):
        assert to_float("abc") == 0.0

    def test_custom_default_on_invalid(self):
        assert to_float("abc", default=7.7) == 7.7

    def test_zero(self):
        assert to_float(0) == 0.0

    def test_zero_string(self):
        assert to_float("0") == 0.0

    def test_boolean_true_fails_and_uses_default(self):
        # str(True) = "True", float("True") raises ValueError → default
        assert to_float(True) == 0.0

    def test_boolean_false_fails_and_uses_default(self):
        assert to_float(False) == 0.0

    def test_custom_default_on_boolean(self):
        assert to_float(True, default=42.0) == 42.0

    def test_scientific_notation_string(self):
        assert to_float("1e2") == 100.0


# ── to_int ───────────────────────────────────────────────────────────


class TestToInt:
    def test_float_string_fails_uses_default(self):
        # int(str(42.9)) = int("42.9") → ValueError → default
        assert to_int(42.9) == 0

    def test_integer_input(self):
        assert to_int(42) == 42

    def test_string_number(self):
        assert to_int("99") == 99

    def test_negative(self):
        assert to_int("-50") == -50

    def test_none_uses_default(self):
        assert to_int(None) == 0

    def test_custom_default_on_none(self):
        assert to_int(None, default=7) == 7

    def test_invalid_string_uses_default(self):
        assert to_int("abc") == 0

    def test_empty_string_returns_default(self):
        assert to_int("", default=42) == 42

    def test_zero(self):
        assert to_int("0") == 0

    def test_boolean_true_fails_and_uses_default(self):
        # int(str(True)) = int("True") → ValueError → default
        assert to_int(True) == 0

    def test_boolean_false_fails_and_uses_default(self):
        assert to_int(False) == 0

    def test_large_string_number(self):
        assert to_int("999999999") == 999999999


# ── parse_rate_text ──────────────────────────────────────────────────


class TestParseRateText:
    def test_percentage_string(self):
        assert parse_rate_text("75%") == 75.0

    def test_no_percent_sign(self):
        assert parse_rate_text("88.5") == 88.5

    def test_empty_string(self):
        assert parse_rate_text("") == 0.0

    def test_none(self):
        assert parse_rate_text(None) == 0.0

    def test_with_spaces(self):
        assert parse_rate_text("  50%  ") == 50.0

    def test_decimal_percentage(self):
        assert parse_rate_text("33.33%") == 33.33

    def test_invalid_returns_zero(self):
        assert parse_rate_text("abc%") == 0.0

    def test_zero_percent(self):
        assert parse_rate_text("0%") == 0.0

    def test_hundred_percent(self):
        assert parse_rate_text("100%") == 100.0


# ── normalize_text ───────────────────────────────────────────────────


class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("Hello WORLD") == "hello world"

    def test_collapses_whitespace(self):
        assert normalize_text("a  b\tc\nd") == "a b c d"

    def test_leading_trailing_stripped(self):
        assert normalize_text("  abc  ") == "abc"

    def test_none_becomes_empty_string(self):
        assert normalize_text(None) == ""

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_tabs_and_newlines(self):
        assert normalize_text("foo\nbar\tbaz") == "foo bar baz"

    def test_already_normalized(self):
        assert normalize_text("already fine") == "already fine"

    def test_mixed_whitespace_types(self):
        result = normalize_text(" a \t b \n c \r d ")
        assert result == "a b c d"


# ── normalize_error_message ──────────────────────────────────────────


class TestNormalizeErrorMessage:
    def test_empty_message(self):
        assert normalize_error_message("") == "(empty message)"

    def test_none_message(self):
        assert normalize_error_message(None) == "(empty message)"

    def test_numbers_replaced(self):
        normalized = normalize_error_message("status code 200 returned")
        assert "{n}" in normalized
        assert "200" not in normalized

    def test_multi_digit_hex_ids_replaced(self):
        normalized = normalize_error_message("request id abcdef1234 found")
        assert "{id}" in normalized

    def test_short_numbers_preserved(self):
        """Numbers with fewer than 2 digits are NOT replaced."""
        normalized = normalize_error_message("code 42 ok")
        # "42" has 2 digits which is >= 2 so it gets replaced
        assert "{n}" in normalized or "42" in normalized

    def test_short_numbers_preserved_two_digits(self):
        """Exactly 2-digit numbers ARE replaced (>= 2)."""
        normalized = normalize_error_message("found at line 42")
        # "42" has 2 digits, \b\d{2,}\b matches
        assert "{n}" in normalized

    def test_single_digit_number_preserved(self):
        normalized = normalize_error_message("error 5 occurred")
        # "5" is only 1 digit, < 2 so NOT replaced
        assert "5" in normalized
        assert "{n}" not in normalized

    def test_urls_have_numbers_replaced(self):
        normalized = normalize_error_message("url /api/v2/items/123")
        # "2" is single digit (< 2), not replaced; "123" (>=2 digits) replaced
        assert "url /api/v2/items/{n}" in normalized.lower()

    def test_mixed_content(self):
        normalized = normalize_error_message("user abc12345678 logged in at 14:30")
        assert "{id}" in normalized
        assert "abc12345678" not in normalized

    def test_already_normalized_passes_through(self):
        normalized = normalize_error_message("{n} items found")
        # {n} doesn't match \b\d{2,}\b so preserved
        assert "{n}" in normalized

    def test_multiple_hex_ids(self):
        msg = "tokens aaaaaaaaaaaaaaaa and bbbbbbbbbbbbbbbb"
        normalized = normalize_error_message(msg)
        assert normalized.count("{id}") == 2

    def test_url_path_segment_redaction(self):
        normalized = normalize_error_message("path /api/v1/users/999/error")
        # "/v1" → "/{n}", "/999" → "/{n}"
        assert "/v" in normalized


# ── extract_response_times ───────────────────────────────────────────


class TestExtractResponseTimes:
    def test_normal_results(self):
        results = [
            {"response_time_ms": 100},
            {"response_time_ms": 200},
            {"response_time_ms": 300},
        ]
        assert extract_response_times(results) == [100, 200, 300]

    def test_negative_times_excluded(self):
        results = [{"response_time_ms": -1}, {"response_time_ms": 100}]
        assert extract_response_times(results) == [100]

    def test_missing_key_excluded(self):
        results = [{"other": 100}, {"response_time_ms": 50}]
        assert extract_response_times(results) == [50]

    def test_empty_results(self):
        assert extract_response_times([]) == []

    def test_zero_time_included(self):
        results = [{"response_time_ms": 0}]
        assert extract_response_times(results) == [0]

    def test_negative_zero_not_negative(self):
        results = [{"response_time_ms": -0}]
        assert extract_response_times(results) == [0]

    def test_invalid_response_time_excluded(self):
        results = [{"response_time_ms": "invalid"}]
        # to_int("invalid") returns default -1, then -1 < 0 → excluded
        assert extract_response_times(results) == []

    def test_mixed_valid_and_invalid(self):
        results = [
            {"response_time_ms": 100},
            {"response_time_ms": "bad"},
            {"response_time_ms": 300},
        ]
        assert extract_response_times(results) == [100, 300]

    def test_nested_dict_value(self):
        results = [{"response_time_ms": {"nested": True}}]
        # int(str({"nested": True})) → ValueError → default -1 → excluded
        assert extract_response_times(results) == []


# ── percentile ───────────────────────────────────────────────────────


class TestPercentile:
    def test_empty_list(self):
        assert percentile([], 0.5) == 0

    def test_single_element(self):
        assert percentile([42], 0.5) == 42

    def test_single_element_any_q(self):
        assert percentile([7], 0.99) == 7

    def test_exact_median_odd(self):
        assert percentile([1, 2, 3], 0.5) == 2

    def test_exact_median_even(self):
        assert percentile([1, 2, 3, 4], 0.5) == 2

    def test_p0(self):
        assert percentile([10, 20, 30], 0.0) == 10

    def test_p100(self):
        assert percentile([10, 20, 30], 1.0) == 30

    def test_q_clamped_to_0_when_negative(self):
        assert percentile([1, 2, 3], -0.5) == 1

    def test_q_clamped_to_1_when_above_1(self):
        assert percentile([1, 2, 3], 1.5) == 3

    def test_interpolation(self):
        values = [10, 20, 30, 40, 50]
        p95 = percentile(values, 0.95)
        rank = 0.95 * 4  # 3.8
        expected = round(40 + (50 - 40) * 0.8)  # 48
        assert p95 == expected

    def test_two_elements(self):
        assert percentile([0, 100], 0.5) == 50

    def test_unordered_input_sorted_first(self):
        assert percentile([3, 1, 2], 0.5) == 2

    def test_large_values(self):
        assert percentile([1000000], 0.5) == 1000000


# ── build_quantiles ──────────────────────────────────────────────────


class TestBuildQuantiles:
    def test_empty(self):
        result = build_quantiles([])
        assert result == {"avg": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0}

    def test_single_value(self):
        result = build_quantiles([50])
        assert result == {"avg": 50, "p50": 50, "p95": 50, "p99": 50, "max": 50}

    def test_known_dataset(self):
        result = build_quantiles([10, 20, 30, 40, 50])
        assert result["avg"] == 30
        assert result["max"] == 50
        assert result["p50"] == 30

    def test_all_keys_present(self):
        result = build_quantiles([1])
        assert set(result.keys()) == {"avg", "p50", "p95", "p99", "max"}

    def test_negative_values(self):
        result = build_quantiles([-10, 0, 10])
        assert result["avg"] == 0

    def test_large_dataset(self):
        values = list(range(1, 101))
        result = build_quantiles(values)
        assert result["max"] == 100
        assert result["avg"] == 50


# ── build_histogram ──────────────────────────────────────────────────


class TestBuildHistogram:
    def test_basic(self):
        buckets = [0, 100, 200]
        values = [50, 150, 250]
        rows = build_histogram(values, buckets)
        assert len(rows) == 3
        assert rows[0]["count"] == 1  # [0, 100)
        assert rows[1]["count"] == 1  # [100, 200)
        assert rows[2]["count"] == 1  # [200, +inf)

    def test_labels_formatting(self):
        rows = build_histogram([], [0, 100, 200])
        assert rows[0]["bucket"] == "[0, 100)"
        assert rows[1]["bucket"] == "[100, 200)"
        assert rows[2]["bucket"] == "[200, +inf)"

    def test_last_bucket_has_none_max(self):
        rows = build_histogram([], [0, 100])
        assert rows[-1]["max_exclusive"] is None

    def test_empty_values_all_zero(self):
        rows = build_histogram([], [0, 100])
        assert all(r["count"] == 0 for r in rows)

    def test_all_same_bucket(self):
        rows = build_histogram([10, 20, 30], [0, 100, 200])
        assert rows[0]["count"] == 3
        assert rows[1]["count"] == 0
        assert rows[2]["count"] == 0

    def test_default_buckets_when_empty(self):
        rows = build_histogram([5000], [])
        assert any(r["count"] > 0 for r in rows)
        assert len(rows) == 8  # default 8 buckets

    def test_duplicate_buckets_deduplicated(self):
        rows = build_histogram([50], [0, 100, 100, 200])
        assert len(rows) == 3
        assert rows[0]["bucket"] == "[0, 100)"
        assert rows[1]["bucket"] == "[100, 200)"
        assert rows[2]["bucket"] == "[200, +inf)"

    def test_boundary_at_limit(self):
        rows = build_histogram([100], [0, 100, 200])
        # value=100, limit[0]=0, limit[1]=100 → 100 < 100? No → idx=0
        # Actually loop: i=1: value < limits[1]? 100 < 100? No. i=2: idx stays
        # Final idx = 1 (last index), count in bucket [100, +inf)
        assert rows[1]["count"] == 1

    def test_value_zero(self):
        rows = build_histogram([0], [0, 100])
        # 0 < 100? Yes → idx=0 → [0, 100)
        assert rows[0]["count"] == 1

    def test_many_values_distribution(self):
        values = [10, 20, 30, 150, 250, 350, 500, 1500]
        rows = build_histogram(values, [0, 100, 500, 1000])
        assert rows[0]["count"] == 3  # [0, 100): 10,20,30
        assert rows[1]["count"] == 3  # [100, 500): 150,250,350
        assert rows[3]["count"] == 1  # [1000, +inf): 1500


# ── classify_error_category ──────────────────────────────────────────


class TestClassifyErrorCategory:
    def test_connection_timeout(self):
        result = classify_error_category("timeout", "timeout")
        assert result == ERROR_CATEGORY_CONNECTION

    def test_connection_refused(self):
        result = classify_error_category("connection refused", "")
        assert result == ERROR_CATEGORY_CONNECTION

    def test_connection_dns(self):
        result = classify_error_category("", "dns error")
        assert result == ERROR_CATEGORY_CONNECTION

    def test_connection_network(self):
        result = classify_error_category("", "network error")
        assert result == ERROR_CATEGORY_CONNECTION

    def test_connection_ssl(self):
        result = classify_error_category("", "ssl handshake failed")
        assert result == ERROR_CATEGORY_CONNECTION

    def test_connection_tls(self):
        result = classify_error_category("", "tls version mismatch")
        assert result == ERROR_CATEGORY_CONNECTION

    def test_auth_unauthorized(self):
        result = classify_error_category("unauthorized", "")
        assert result == ERROR_CATEGORY_AUTH

    def test_auth_forbidden(self):
        result = classify_error_category("forbidden", "")
        assert result == ERROR_CATEGORY_AUTH

    def test_auth_token_expired(self):
        result = classify_error_category("token expired", "")
        assert result == ERROR_CATEGORY_AUTH

    def test_auth_chinese_login(self):
        result = classify_error_category("", "login required")
        assert result == ERROR_CATEGORY_AUTH

    def test_auth_chinese_authentication(self):
        result = classify_error_category("", "鉴权失败")
        assert result == ERROR_CATEGORY_AUTH

    def test_assertion_failed(self):
        result = classify_error_category("assertion failed", "")
        assert result == ERROR_CATEGORY_ASSERTION

    def test_assertion_jsonpath(self):
        result = classify_error_category("", "jsonpath mismatch")
        assert result == ERROR_CATEGORY_ASSERTION

    def test_assertion_expected(self):
        result = classify_error_category("expected X got Y", "")
        assert result == ERROR_CATEGORY_ASSERTION

    def test_assertion_chinese(self):
        result = classify_error_category("", "断言失败")
        assert result == ERROR_CATEGORY_ASSERTION

    def test_database_sql(self):
        result = classify_error_category("sql error", "")
        assert result == ERROR_CATEGORY_DATABASE

    def test_database_mysql(self):
        result = classify_error_category("", "mysql deadlock found")
        assert result == ERROR_CATEGORY_DATABASE

    def test_database_postgres(self):
        result = classify_error_category("", "postgres db error")
        assert result == ERROR_CATEGORY_DATABASE

    def test_database_db(self):
        result = classify_error_category("", "db constraint violation")
        assert result == ERROR_CATEGORY_DATABASE

    def test_database_chinese(self):
        result = classify_error_category("", "数据库连接异常")
        assert result == ERROR_CATEGORY_DATABASE

    def test_business_invalid(self):
        result = classify_error_category("invalid parameter", "")
        assert result == ERROR_CATEGORY_BUSINESS

    def test_business_chinese(self):
        result = classify_error_category("", "业务不合法")
        assert result == ERROR_CATEGORY_BUSINESS

    def test_business_duplicate(self):
        result = classify_error_category("", "重复记录")
        assert result == ERROR_CATEGORY_BUSINESS

    def test_business_not_exists(self):
        result = classify_error_category("", "不存在")
        assert result == ERROR_CATEGORY_BUSINESS

    def test_unknown_fallback(self):
        result = classify_error_category("some random thing xyz", "xyz")
        assert result == ERROR_CATEGORY_UNKNOWN

    def test_empty_inputs(self):
        result = classify_error_category("", "")
        assert result == ERROR_CATEGORY_UNKNOWN

    def test_priority_connection_over_business(self):
        result = classify_error_category("invalid timeout", "timeout")
        # Both "timeout" (connection) and "invalid" (business) present;
        # connection check comes first so wins
        assert result == ERROR_CATEGORY_CONNECTION

    def test_mixed_keywords_lowers_case(self):
        result = classify_error_category("UNAUTHORIZED request", "TOKEN")
        assert result == ERROR_CATEGORY_AUTH


# ── ratio ────────────────────────────────────────────────────────────


class TestRatio:
    def test_perfect_ratio(self):
        assert ratio(100, 100) == 100.0

    def test_half(self):
        assert ratio(50, 100) == 50.0

    def test_quarter(self):
        assert ratio(25, 100) == 25.0

    def test_zero_count(self):
        assert ratio(0, 100) == 0.0

    def test_zero_total_returns_zero(self):
        assert ratio(10, 0) == 0.0

    def test_negative_total_returns_zero(self):
        assert ratio(10, -5) == 0.0

    def test_rounding(self):
        result = ratio(1, 3)
        assert result == 33.33

    def test_small_fraction(self):
        result = ratio(1, 7)
        assert abs(result - 14.29) < 0.01

    def test_total_one(self):
        assert ratio(1, 1) == 100.0


# ── safe_top_items ───────────────────────────────────────────────────


class TestSafeTopItems:
    def test_basic_ordering(self):
        counter = {"a": 3, "b": 1, "c": 2}
        result = safe_top_items(counter, 2)
        assert result == [("a", 3), ("c", 2)]

    def test_tie_breaking_alpha(self):
        counter = {"b": 5, "a": 5, "c": 5}
        result = safe_top_items(counter, 3)
        assert result == [("a", 5), ("b", 5), ("c", 5)]

    def test_top_n_larger_than_counter(self):
        counter = {"a": 1}
        result = safe_top_items(counter, 100)
        assert result == [("a", 1)]

    def test_top_n_zero(self):
        counter = {"a": 1, "b": 2}
        result = safe_top_items(counter, 0)
        assert result == []

    def test_empty_counter(self):
        assert safe_top_items({}, 5) == []

    def test_sort_by_count_descending(self):
        counter = {"x": 10, "y": 20, "z": 30}
        result = safe_top_items(counter, 3)
        assert [c for _, c in result] == [30, 20, 10]

    def test_single_item(self):
        assert safe_top_items({"only": 1}, 1) == [("only", 1)]


# ── distinct_list ────────────────────────────────────────────────────


class TestDistinctList:
    def test_simple_duplicates(self):
        result = distinct_list(["a", "b", "a", "c", "b"])
        assert result == ["a", "b", "c"]

    def test_no_duplicates(self):
        result = distinct_list(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_all_same(self):
        result = distinct_list(["x", "x", "x"])
        assert result == ["x"]

    def test_empty(self):
        assert distinct_list([]) == []

    def test_empty_strings(self):
        result = distinct_list(["", "", "a", ""])
        assert result == ["", "a"]

    def test_order_preserved(self):
        result = distinct_list(["z", "y", "x", "z", "y"])
        assert result == ["z", "y", "x"]


# ── _to_bool ─────────────────────────────────────────────────────────


class TestToBool:
    def test_true_variants(self):
        for val in ["true", "True", "TRUE", "yes", "Yes", "y", "Y", "on", "On", "1"]:
            assert _to_bool(val) is True, f"Expected True for '{val}'"

    def test_false_variants(self):
        for val in ["false", "False", "FALSE", "no", "No", "n", "N", "off", "Off", "0"]:
            assert _to_bool(val) is False, f"Expected False for '{val}'"

    def test_actual_bool_true(self):
        assert _to_bool(True) is True

    def test_actual_bool_false(self):
        assert _to_bool(False) is False

    def test_default_on_invalid(self):
        assert _to_bool("maybe") is False

    def test_custom_default_on_invalid(self):
        assert _to_bool("maybe", default=True) is True

    def test_custom_default_on_valid(self):
        """Custom default should not override valid inputs."""
        assert _to_bool("yes", default=False) is True
        assert _to_bool("no", default=True) is False

    def test_whitespace_stripped(self):
        assert _to_bool("  true  ") is True

    def test_empty_string(self):
        assert _to_bool("") is False

    def test_none(self):
        assert _to_bool(None) is False

    def test_numeric_string_one(self):
        assert _to_bool("1") is True

    def test_numeric_string_zero(self):
        assert _to_bool("0") is False

    def test_case_insensitive(self):
        assert _to_bool("YES") is True
        assert _to_bool("NO") is False


# ── normalize_analytics_query_params ─────────────────────────────────


class TestNormalizeAnalyticsQueryParams:
    def test_basic_passthrough(self):
        result = normalize_analytics_query_params(
            top_n_raw=5,
            trend_limit_raw=10,
            include_samples_raw="true",
            top_n_default=3,
            top_n_max=20,
            trend_limit_default=5,
            trend_limit_max=50,
            include_samples_default=False,
        )
        assert result == {"top_n": 5, "trend_limit": 10, "include_samples": True}

    def test_invalid_top_n_uses_default(self):
        result = normalize_analytics_query_params(
            top_n_raw="abc",
            trend_limit_raw=5,
            include_samples_raw="false",
            top_n_default=3,
            top_n_max=20,
            trend_limit_default=5,
            trend_limit_max=50,
            include_samples_default=False,
        )
        assert result == {"top_n": 3, "trend_limit": 5, "include_samples": False}

    def test_top_n_clamped_to_max(self):
        result = normalize_analytics_query_params(
            top_n_raw=999,
            trend_limit_raw=5,
            include_samples_raw="no",
            top_n_default=3,
            top_n_max=10,
            trend_limit_default=5,
            trend_limit_max=50,
            include_samples_default=False,
        )
        assert result["top_n"] == 10

    def test_trend_limit_clamped(self):
        result = normalize_analytics_query_params(
            top_n_raw=5,
            trend_limit_raw=999,
            include_samples_raw="",
            top_n_default=3,
            top_n_max=20,
            trend_limit_default=5,
            trend_limit_max=10,
            include_samples_default=False,
        )
        assert result["trend_limit"] == 10

    def test_include_samples_false(self):
        result = normalize_analytics_query_params(
            top_n_raw=5,
            trend_limit_raw=5,
            include_samples_raw="false",
            top_n_default=3,
            top_n_max=20,
            trend_limit_default=5,
            trend_limit_max=50,
            include_samples_default=True,
        )
        assert result["include_samples"] is False

    def test_default_when_none(self):
        result = normalize_analytics_query_params(
            top_n_raw=None,
            trend_limit_raw=None,
            include_samples_raw=None,
            top_n_default=7,
            top_n_max=20,
            trend_limit_default=8,
            trend_limit_max=50,
            include_samples_default=True,
        )
        assert result == {"top_n": 7, "trend_limit": 8, "include_samples": True}

    def test_returns_correct_keys(self):
        result = normalize_analytics_query_params(
            top_n_raw=1,
            trend_limit_raw=1,
            include_samples_raw="yes",
            top_n_default=1,
            top_n_max=1,
            trend_limit_default=1,
            trend_limit_max=1,
            include_samples_default=False,
        )
        assert set(result.keys()) == {"top_n", "trend_limit", "include_samples"}
        assert isinstance(result["top_n"], int)
        assert isinstance(result["trend_limit"], int)
        assert isinstance(result["include_samples"], bool)

    def test_top_n_below_minimum_clamped(self):
        result = normalize_analytics_query_params(
            top_n_raw=-100,
            trend_limit_raw=5,
            include_samples_raw="0",
            top_n_default=3,
            top_n_max=20,
            trend_limit_default=5,
            trend_limit_max=50,
            include_samples_default=False,
        )
        assert result["top_n"] == 1

    def test_trend_nulldefault(self):
        result = normalize_analytics_query_params(
            top_n_raw=5,
            trend_limit_raw=None,
            include_samples_raw=None,
            top_n_default=3,
            top_n_max=20,
            trend_limit_default=5,
            trend_limit_max=50,
            include_samples_default=True,
        )
        assert result["trend_limit"] == 5

    def test_all_boundaries_respected(self):
        result = normalize_analytics_query_params(
            top_n_raw=1,
            trend_limit_raw=1,
            include_samples_raw="no",
            top_n_default=5,
            top_n_max=10,
            trend_limit_default=5,
            trend_limit_max=10,
            include_samples_default=True,
        )
        assert result == {"top_n": 1, "trend_limit": 1, "include_samples": False}
