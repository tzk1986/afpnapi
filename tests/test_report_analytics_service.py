"""Tests for services/report_analytics_service.py — 覆盖 15 个函数，正常路径与边界路径。"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from postman_api_tester.services.report_analytics_service import (
    _coverage,
    _error_category_summary,
    _error_suggestions,
    _folder_top,
    _frequent_errors,
    _method_distribution,
    _quality_score,
    _safe_manual_cases,
    _safe_results,
    _source_total,
    _status_distribution,
    _summary_total,
    _trend,
    build_report_analytics_compare_payload,
    build_report_analytics_payload,
)
from postman_api_tester.utils.analytics_utils import (
    ERROR_CATEGORY_ASSERTION,
    ERROR_CATEGORY_AUTH,
    ERROR_CATEGORY_BUSINESS,
    ERROR_CATEGORY_CONNECTION,
    ERROR_CATEGORY_DATABASE,
    ERROR_CATEGORY_UNKNOWN,
)


# ---------------------------------------------------------------------------
# _safe_results / _safe_manual_cases
# ---------------------------------------------------------------------------

class TestSafeResults(unittest.TestCase):

    def test_empty_report(self) -> None:
        assert _safe_results({}) == []

    def test_missing_results_key(self) -> None:
        assert _safe_results({"other": 1}) == []

    def test_results_not_list(self) -> None:
        assert _safe_results({"results": "bad"}) == []

    def test_filters_non_dict_items(self) -> None:
        result = _safe_results({"results": [{"status": "PASSED"}, "bad", 42, None]})
        assert result == [{"status": "PASSED"}]

    def test_valid_results(self) -> None:
        results = [{"status": "PASSED"}, {"status": "FAILED"}]
        assert _safe_results({"results": results}) == results


class TestSafeManualCases(unittest.TestCase):

    def test_empty_report(self) -> None:
        assert _safe_manual_cases({}) == []

    def test_manual_cases_not_list(self) -> None:
        assert _safe_manual_cases({"manual_cases": "bad"}) == []

    def test_filters_non_dict_items(self) -> None:
        result = _safe_manual_cases({"manual_cases": [{"name": "x"}, "bad", None]})
        assert result == [{"name": "x"}]

    def test_valid_manual_cases(self) -> None:
        cases = [{"name": "a"}, {"name": "b"}]
        assert _safe_manual_cases({"manual_cases": cases}) == cases


# ---------------------------------------------------------------------------
# _summary_total / _source_total
# ---------------------------------------------------------------------------

class TestSummaryTotal(unittest.TestCase):

    def test_no_summary_uses_default(self) -> None:
        assert _summary_total({}, 10) == 10

    def test_summary_not_dict_uses_default(self) -> None:
        assert _summary_total({"summary": "bad"}, 5) == 5

    def test_summary_total_used_when_larger(self) -> None:
        assert _summary_total({"summary": {"total": 20}}, 10) == 20

    def test_default_used_when_larger(self) -> None:
        assert _summary_total({"summary": {"total": 5}}, 10) == 10

    def test_summary_total_missing_key(self) -> None:
        assert _summary_total({"summary": {}}, 7) == 7


class TestSourceTotal(unittest.TestCase):

    def test_no_source_total_falls_back_to_summary(self) -> None:
        assert _source_total({"summary": {"total": 15}}, 10) == 15

    def test_source_total_used_when_positive(self) -> None:
        assert _source_total({"source_total_count": 30}, 10) == 30

    def test_source_total_negative_falls_back(self) -> None:
        assert _source_total({"source_total_count": -1, "summary": {"total": 12}}, 10) == 12

    def test_source_total_less_than_executed_returns_executed(self) -> None:
        assert _source_total({"source_total_count": 5}, 10) == 10


# ---------------------------------------------------------------------------
# _status_distribution
# ---------------------------------------------------------------------------

class TestStatusDistribution(unittest.TestCase):

    def test_empty_results(self) -> None:
        result = _status_distribution([])
        assert result == {"PASSED": 0, "FAILED": 0, "ERROR": 0, "OTHER": 0}

    def test_counts_by_status(self) -> None:
        results = [
            {"status": "PASSED"}, {"status": "PASSED"},
            {"status": "FAILED"}, {"status": "ERROR"},
        ]
        result = _status_distribution(results)
        assert result == {"PASSED": 2, "FAILED": 1, "ERROR": 1, "OTHER": 0}

    def test_unknown_status_goes_to_other(self) -> None:
        results = [{"status": "SKIPPED"}, {"status": "TIMEOUT"}]
        result = _status_distribution(results)
        assert result["OTHER"] == 2
        assert result["PASSED"] == 0

    def test_none_status_treated_as_unknown(self) -> None:
        results = [{"status": None}, {"status": ""}]
        result = _status_distribution(results)
        assert result["OTHER"] == 2

    def test_case_insensitive(self) -> None:
        results = [{"status": "passed"}, {"status": "Failed"}]
        result = _status_distribution(results)
        assert result["PASSED"] == 1
        assert result["FAILED"] == 1


# ---------------------------------------------------------------------------
# _method_distribution
# ---------------------------------------------------------------------------

class TestMethodDistribution(unittest.TestCase):

    def test_empty_results(self) -> None:
        result = _method_distribution([])
        assert result == {"GET": 0, "POST": 0, "PUT": 0, "PATCH": 0, "DELETE": 0, "OTHER": 0}

    def test_counts_by_method(self) -> None:
        results = [
            {"method": "GET"}, {"method": "POST"}, {"method": "PUT"},
            {"method": "PATCH"}, {"method": "DELETE"}, {"method": "GET"},
        ]
        result = _method_distribution(results)
        assert result["GET"] == 2
        assert result["POST"] == 1
        assert result["DELETE"] == 1

    def test_unknown_method_goes_to_other(self) -> None:
        results = [{"method": "OPTIONS"}, {"method": "HEAD"}]
        result = _method_distribution(results)
        assert result["OTHER"] == 2

    def test_none_method_goes_to_other(self) -> None:
        results = [{"method": None}, {"method": ""}]
        result = _method_distribution(results)
        assert result["OTHER"] == 2

    def test_case_insensitive(self) -> None:
        results = [{"method": "get"}, {"method": "Post"}]
        result = _method_distribution(results)
        assert result["GET"] == 1
        assert result["POST"] == 1


# ---------------------------------------------------------------------------
# _folder_top
# ---------------------------------------------------------------------------

class TestFolderTop(unittest.TestCase):

    def test_empty_results(self) -> None:
        assert _folder_top([], top_n=5) == []

    def test_counts_by_folder(self) -> None:
        results = [
            {"folder": "auth"}, {"folder": "auth"}, {"folder": "users"},
        ]
        result = _folder_top(results, top_n=5)
        folders = {row["folder"]: row["count"] for row in result}
        assert folders["auth"] == 2
        assert folders["users"] == 1

    def test_top_n_limits_results(self) -> None:
        results = [{"folder": f"folder_{i}"} for i in range(10)]
        result = _folder_top(results, top_n=3)
        assert len(result) == 3

    def test_none_folder_becomes_root(self) -> None:
        results = [{"folder": None}, {"folder": ""}]
        result = _folder_top(results, top_n=5)
        folders = [row["folder"] for row in result]
        assert "(root)" in folders

    def test_missing_folder_key_becomes_root(self) -> None:
        results = [{}]
        result = _folder_top(results, top_n=5)
        assert result[0]["folder"] == "(root)"


# ---------------------------------------------------------------------------
# _error_category_summary
# ---------------------------------------------------------------------------

class TestErrorCategorySummary(unittest.TestCase):

    def test_empty_items(self) -> None:
        result = _error_category_summary([])
        assert all(row["count"] == 0 for row in result)
        assert len(result) == 6

    def test_connection_error_categorized(self) -> None:
        items = [{"message": "Connection refused", "err_code": ""}]
        result = _error_category_summary(items)
        conn_row = next(r for r in result if r["category"] == ERROR_CATEGORY_CONNECTION)
        assert conn_row["count"] == 1
        assert conn_row["ratio"] > 0

    def test_auth_error_categorized(self) -> None:
        items = [{"message": "Unauthorized", "err_code": "401"}]
        result = _error_category_summary(items)
        auth_row = next(r for r in result if r["category"] == ERROR_CATEGORY_AUTH)
        assert auth_row["count"] == 1

    def test_multiple_items_same_category(self) -> None:
        items = [
            {"message": "Connection timeout", "err_code": ""},
            {"message": "Connection refused", "err_code": ""},
        ]
        result = _error_category_summary(items)
        conn_row = next(r for r in result if r["category"] == ERROR_CATEGORY_CONNECTION)
        assert conn_row["count"] == 2
        assert conn_row["ratio"] == 100.0


# ---------------------------------------------------------------------------
# _error_suggestions
# ---------------------------------------------------------------------------

class TestErrorSuggestions(unittest.TestCase):

    def test_empty_category_summary(self) -> None:
        assert _error_suggestions([]) == []

    def test_skips_zero_count_categories(self) -> None:
        summary = [{"category": ERROR_CATEGORY_CONNECTION, "count": 0, "ratio": 0.0}]
        assert _error_suggestions(summary) == []

    def test_returns_suggestion_for_nonzero_category(self) -> None:
        summary = [{"category": ERROR_CATEGORY_CONNECTION, "count": 3, "ratio": 0.5}]
        result = _error_suggestions(summary)
        assert len(result) == 1
        assert result[0]["category"] == ERROR_CATEGORY_CONNECTION
        assert "base_url" in result[0]["suggestion"]

    def test_unknown_category_falls_back_to_unknown_suggestion(self) -> None:
        summary = [{"category": "weird_category", "count": 1, "ratio": 0.1}]
        result = _error_suggestions(summary)
        assert len(result) == 1
        assert "可观测性" in result[0]["suggestion"] or "规则" in result[0]["suggestion"]


# ---------------------------------------------------------------------------
# _frequent_errors
# ---------------------------------------------------------------------------

class TestFrequentErrors(unittest.TestCase):

    def test_empty_items(self) -> None:
        assert _frequent_errors([], top_n=5, include_samples=False) == []

    def test_groups_by_normalized_message(self) -> None:
        items = [
            {"message": "Connection refused", "name": "api1", "method": "GET", "url": "/a", "status": "ERROR", "err_code": ""},
            {"message": "Connection refused", "name": "api2", "method": "POST", "url": "/b", "status": "ERROR", "err_code": ""},
        ]
        result = _frequent_errors(items, top_n=5, include_samples=False)
        assert len(result) == 1
        assert result[0]["count"] == 2
        assert "samples" not in result[0]

    def test_include_samples_adds_samples(self) -> None:
        items = [
            {"message": "Timeout", "name": "api1", "method": "GET", "url": "/a", "status": "ERROR", "err_code": ""},
        ]
        result = _frequent_errors(items, top_n=5, include_samples=True)
        assert "samples" in result[0]
        assert len(result[0]["samples"]) == 1
        assert result[0]["samples"][0]["name"] == "api1"

    def test_samples_capped_at_3(self) -> None:
        items = [
            {"message": "Timeout", "name": f"api{i}", "method": "GET", "url": f"/{i}", "status": "ERROR", "err_code": ""}
            for i in range(5)
        ]
        result = _frequent_errors(items, top_n=5, include_samples=True)
        assert len(result[0]["samples"]) == 3

    def test_top_n_limits_output(self) -> None:
        items = [
            {"message": f"Error {i}", "name": "x", "method": "GET", "url": "/x", "status": "ERROR", "err_code": ""}
            for i in range(10)
        ]
        result = _frequent_errors(items, top_n=3, include_samples=False)
        assert len(result) == 3

    def test_sorted_by_count_descending(self) -> None:
        items = [
            {"message": "rare", "name": "x", "method": "GET", "url": "/x", "status": "ERROR", "err_code": ""},
            {"message": "common", "name": "x", "method": "GET", "url": "/x", "status": "ERROR", "err_code": ""},
            {"message": "common", "name": "x", "method": "GET", "url": "/x", "status": "ERROR", "err_code": ""},
        ]
        result = _frequent_errors(items, top_n=5, include_samples=False)
        assert result[0]["message"] == "common"
        assert result[0]["count"] == 2


# ---------------------------------------------------------------------------
# _quality_score
# ---------------------------------------------------------------------------

class TestQualityScore(unittest.TestCase):

    def _make_results(self, passed: int = 0, failed: int = 0, error: int = 0,
                      response_times: list | None = None,
                      with_assertions: bool = False) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i in range(passed):
            item: Dict[str, Any] = {"status": "PASSED"}
            if response_times and i < len(response_times):
                item["response_time_ms"] = response_times[i]
            if with_assertions:
                item["assertion_results"] = [{"expr": "$.ok", "passed": True}]
            results.append(item)
        for _ in range(failed):
            results.append({"status": "FAILED"})
        for _ in range(error):
            results.append({"status": "ERROR"})
        return results

    def test_perfect_score_no_penalties(self) -> None:
        results = self._make_results(passed=10)
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=2,
            assertion_missing_penalty=0, assertions_enabled=False,
        )
        assert score["total_score"] == 100
        assert score["stability_score"] == 100
        assert score["performance_score"] == 100

    def test_failed_penalty_reduces_stability(self) -> None:
        results = self._make_results(passed=8, failed=2)
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=2,
            assertion_missing_penalty=0, assertions_enabled=False,
        )
        assert score["penalties"]["failed_count"] == 2
        assert score["stability_score"] == 90  # 100 - 2*5

    def test_error_penalty_reduces_stability(self) -> None:
        results = self._make_results(passed=8, error=2)
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=2,
            assertion_missing_penalty=0, assertions_enabled=False,
        )
        assert score["penalties"]["error_count"] == 2
        assert score["stability_score"] == 80  # 100 - 2*10

    def test_slow_requests_reduce_performance(self) -> None:
        results = self._make_results(passed=5, response_times=[100, 200, 600, 700, 800])
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=3,
            assertion_missing_penalty=0, assertions_enabled=False,
        )
        assert score["penalties"]["slow_count"] == 3
        assert score["performance_score"] == 91  # 100 - 3*3

    def test_assertion_missing_penalty_when_enabled(self) -> None:
        results = [
            {"status": "PASSED"},  # no assertion_results
            {"status": "PASSED", "assertion_results": [{"expr": "$.ok", "passed": True}]},
        ]
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=2,
            assertion_missing_penalty=4, assertions_enabled=True,
        )
        assert score["penalties"]["missing_assertion_count"] == 1
        assert score["assertion_score"] == 96  # 100 - 1*4

    def test_assertion_score_100_when_disabled(self) -> None:
        results = self._make_results(passed=5)
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=2,
            assertion_missing_penalty=4, assertions_enabled=False,
        )
        assert score["assertion_score"] == 100

    def test_total_score_clamped_at_zero(self) -> None:
        results = self._make_results(failed=50)
        score = _quality_score(
            results=results, p95=500,
            failed_penalty=5, error_penalty=10, slow_penalty=2,
            assertion_missing_penalty=0, assertions_enabled=False,
        )
        assert score["total_score"] == 0


# ---------------------------------------------------------------------------
# _coverage
# ---------------------------------------------------------------------------

class TestCoverage(unittest.TestCase):

    def test_basic_coverage(self) -> None:
        report = {"source_total_count": 10, "manual_cases": [{"name": "mc1"}]}
        results = [{"key": "a"}, {"key": "b"}]
        cov = _coverage(report, results, top_n=5)
        assert cov["executed_total"] == 2
        assert cov["manual_cases_total"] == 1
        assert cov["source_total"] == 10

    def test_uncovered_top_from_source_items(self) -> None:
        report = {
            "source_total_count": 5,
            "source_items": [
                {"key": "a", "name": "A", "folder": "f1", "method": "GET", "url": "/a"},
                {"key": "b", "name": "B", "folder": "f1", "method": "POST", "url": "/b"},
                {"key": "c", "name": "C", "folder": "f2", "method": "PUT", "url": "/c"},
            ],
        }
        results = [{"key": "a"}]
        cov = _coverage(report, results, top_n=5)
        uncovered_keys = [row["key"] for row in cov["uncovered_top"]]
        assert "b" in uncovered_keys
        assert "c" in uncovered_keys
        assert "a" not in uncovered_keys

    def test_no_source_items_means_empty_uncovered(self) -> None:
        report = {"source_total_count": 5}
        results = [{"key": "a"}]
        cov = _coverage(report, results, top_n=5)
        assert cov["uncovered_top"] == []


# ---------------------------------------------------------------------------
# _trend
# ---------------------------------------------------------------------------

class TestTrend(unittest.TestCase):

    def test_empty_reports(self) -> None:
        report = {"collection_name": "api", "source_file": "a.json"}
        result = _trend(report=report, reports=[], trend_limit=10)
        assert result["success_rate"] == []
        assert result["avg_response_ms"] == []
        assert result["failed_count"] == []

    def test_filters_by_collection_name(self) -> None:
        report = {"collection_name": "api_a", "source_file": ""}
        reports = [
            {"collection_name": "api_a", "report_name": "r1", "generated_at": "2026-06-15",
             "summary": {"success_rate": "90%", "avg_response_ms": 100, "failed": 2}},
            {"collection_name": "api_b", "report_name": "r2", "generated_at": "2026-06-15",
             "summary": {"success_rate": "80%", "avg_response_ms": 200, "failed": 5}},
        ]
        result = _trend(report=report, reports=reports, trend_limit=10)
        assert len(result["success_rate"]) == 1
        assert result["success_rate"][0]["report_name"] == "r1"

    def test_trend_limit_truncates(self) -> None:
        report = {"collection_name": "api", "source_file": ""}
        reports = [
            {"collection_name": "api", "report_name": f"r{i}", "generated_at": f"2026-06-{i:02d}",
             "summary": {"success_rate": "90%", "avg_response_ms": 100, "failed": 1}}
            for i in range(1, 11)
        ]
        result = _trend(report=report, reports=reports, trend_limit=3)
        assert len(result["success_rate"]) == 3

    def test_ordered_chronologically_ascending(self) -> None:
        report = {"collection_name": "api", "source_file": ""}
        reports = [
            {"collection_name": "api", "report_name": "r_new", "generated_at": "2026-06-16",
             "summary": {"success_rate": "95%", "avg_response_ms": 80, "failed": 1}},
            {"collection_name": "api", "report_name": "r_old", "generated_at": "2026-06-14",
             "summary": {"success_rate": "80%", "avg_response_ms": 120, "failed": 4}},
        ]
        result = _trend(report=report, reports=reports, trend_limit=10)
        names = [row["report_name"] for row in result["success_rate"]]
        assert names == ["r_old", "r_new"]


# ---------------------------------------------------------------------------
# build_report_analytics_payload (integration)
# ---------------------------------------------------------------------------

def _default_kwargs(**overrides: Any) -> Dict[str, Any]:
    defaults: Dict[str, Any] = dict(
        top_n=5,
        trend_limit=10,
        include_samples=False,
        histogram_buckets=[100, 200, 500, 1000],
        failed_penalty=5,
        error_penalty=10,
        slow_penalty=2,
        assertion_missing_penalty=0,
        assertions_enabled=False,
    )
    defaults.update(overrides)
    return defaults


class TestBuildReportAnalyticsPayload(unittest.TestCase):

    def _make_report(self, results: list | None = None, **extra: Any) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "report_name": "test_report",
            "collection_name": "api_test",
            "source_total_count": len(results) if results else 0,
            "results": results or [],
            "summary": {"total": len(results) if results else 0, "success_rate": "100%"},
        }
        report.update(extra)
        return report

    def test_empty_report_returns_valid_structure(self) -> None:
        report = self._make_report([])
        payload = build_report_analytics_payload(report=report, reports=[], **_default_kwargs())
        assert payload["report_name"] == "test_report"
        assert "distributions" in payload
        assert "performance" in payload
        assert "diagnostics" in payload
        assert "quality_score" in payload
        assert "coverage" in payload
        assert "trend" in payload

    def test_distributions_populated(self) -> None:
        results = [
            {"status": "PASSED", "method": "GET", "folder": "auth"},
            {"status": "FAILED", "method": "POST", "folder": "auth"},
        ]
        report = self._make_report(results)
        payload = build_report_analytics_payload(report=report, reports=[], **_default_kwargs())
        assert payload["distributions"]["status"]["PASSED"] == 1
        assert payload["distributions"]["status"]["FAILED"] == 1
        assert payload["distributions"]["method"]["GET"] == 1
        assert payload["distributions"]["method"]["POST"] == 1

    def test_quality_score_reflects_failures(self) -> None:
        results = [{"status": "PASSED"} for _ in range(8)] + [{"status": "FAILED"} for _ in range(2)]
        report = self._make_report(results)
        payload = build_report_analytics_payload(report=report, reports=[], **_default_kwargs())
        assert payload["quality_score"]["penalties"]["failed_count"] == 2
        assert payload["quality_score"]["stability_score"] < 100

    def test_error_items_feed_diagnostics(self) -> None:
        results = [
            {"status": "ERROR", "message": "Connection refused", "err_code": "", "name": "x", "method": "GET", "url": "/x"},
        ]
        report = self._make_report(results)
        payload = build_report_analytics_payload(report=report, reports=[], **_default_kwargs())
        assert len(payload["diagnostics"]["suggestions"]) > 0
        conn_suggestion = next(s for s in payload["diagnostics"]["suggestions"]
                               if s["category"] == ERROR_CATEGORY_CONNECTION)
        assert conn_suggestion is not None


# ---------------------------------------------------------------------------
# build_report_analytics_compare_payload (integration)
# ---------------------------------------------------------------------------

class TestBuildReportAnalyticsComparePayload(unittest.TestCase):

    def _make_report(self, name: str, passed: int, failed: int, success_rate: str,
                     avg_response_ms: int) -> Dict[str, Any]:
        results = [{"status": "PASSED"} for _ in range(passed)] + \
                  [{"status": "FAILED"} for _ in range(failed)]
        return {
            "report_name": name,
            "collection_name": "api_test",
            "source_total_count": passed + failed,
            "results": results,
            "summary": {
                "total": passed + failed,
                "success_rate": success_rate,
                "avg_response_ms": avg_response_ms,
                "failed": failed,
                "error": 0,
            },
        }

    def test_compare_returns_delta_structure(self) -> None:
        left = self._make_report("r1", passed=8, failed=2, success_rate="80%", avg_response_ms=100)
        right = self._make_report("r2", passed=9, failed=1, success_rate="90%", avg_response_ms=80)
        payload = build_report_analytics_compare_payload(
            left_report=left, right_report=right, reports=[], **_default_kwargs(),
        )
        assert "left_snapshot" in payload
        assert "right_snapshot" in payload
        assert "delta" in payload
        assert "score_delta" in payload

    def test_success_rate_delta_positive_when_improved(self) -> None:
        left = self._make_report("r1", passed=8, failed=2, success_rate="80%", avg_response_ms=100)
        right = self._make_report("r2", passed=10, failed=0, success_rate="100%", avg_response_ms=80)
        payload = build_report_analytics_compare_payload(
            left_report=left, right_report=right, reports=[], **_default_kwargs(),
        )
        assert payload["delta"]["success_rate_delta"] == 20.0

    def test_failed_delta_positive_when_more_failures(self) -> None:
        left = self._make_report("r1", passed=10, failed=0, success_rate="100%", avg_response_ms=80)
        right = self._make_report("r2", passed=7, failed=3, success_rate="70%", avg_response_ms=120)
        payload = build_report_analytics_compare_payload(
            left_report=left, right_report=right, reports=[], **_default_kwargs(),
        )
        assert payload["delta"]["failed_delta"] == 3

    def test_score_delta_reflects_quality_change(self) -> None:
        left = self._make_report("r1", passed=10, failed=0, success_rate="100%", avg_response_ms=80)
        right = self._make_report("r2", passed=5, failed=5, success_rate="50%", avg_response_ms=200)
        payload = build_report_analytics_compare_payload(
            left_report=left, right_report=right, reports=[], **_default_kwargs(),
        )
        assert payload["score_delta"] < 0  # quality degraded

    def test_avg_response_delta_ms(self) -> None:
        left = self._make_report("r1", passed=10, failed=0, success_rate="100%", avg_response_ms=100)
        right = self._make_report("r2", passed=10, failed=0, success_rate="100%", avg_response_ms=150)
        payload = build_report_analytics_compare_payload(
            left_report=left, right_report=right, reports=[], **_default_kwargs(),
        )
        assert payload["delta"]["avg_response_delta_ms"] == 50


if __name__ == "__main__":
    unittest.main()
