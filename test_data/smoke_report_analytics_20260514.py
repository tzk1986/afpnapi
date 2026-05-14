#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report analytics smoke test."""

from __future__ import annotations

from typing import Any, Dict, List

from postman_api_tester.handlers.report_analytics_handler import (
    build_analytics_payload,
    normalize_analytics_query_params,
)


def _report_fixture() -> Dict[str, Any]:
    return {
        "report_name": "demo.html",
        "collection_name": "demo",
        "generated_at": "2026-05-14 10:00:00",
        "summary": {
            "total": 4,
            "passed": 1,
            "failed": 2,
            "error": 1,
            "success_rate": "25.00%",
            "avg_response_ms": 260,
            "max_response_ms": 900,
            "p95_response_ms": 800,
        },
        "manual_cases": [{"id": "m1"}, {"id": "m2"}],
        "results": [
            {
                "key": "A",
                "name": "ok",
                "folder": "F1",
                "method": "GET",
                "url": "/ok",
                "status": "PASSED",
                "response_time_ms": 40,
                "assertion_results": [{"ok": True}],
            },
            {
                "key": "B",
                "name": "fail-auth",
                "folder": "F1",
                "method": "POST",
                "url": "/auth",
                "status": "FAILED",
                "message": "token expired",
                "err_code": "401",
                "response_time_ms": 350,
                "assertion_results": [],
            },
            {
                "key": "C",
                "name": "fail-db",
                "folder": "F2",
                "method": "PUT",
                "url": "/db",
                "status": "FAILED",
                "message": "database timeout",
                "err_code": "DB1001",
                "response_time_ms": 920,
            },
            {
                "key": "D",
                "name": "err-network",
                "folder": "F2",
                "method": "PATCH",
                "url": "/net",
                "status": "ERROR",
                "message": "connection refused",
                "err_code": "ECONN",
                "response_time_ms": 610,
            },
        ],
    }


def _reports_fixture(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    old_summary = {
        "total": 4,
        "passed": 3,
        "failed": 1,
        "error": 0,
        "success_rate": "75.00%",
        "avg_response_ms": 180,
    }
    return [
        {
            "report_name": "demo_old.html",
            "collection_name": "demo",
            "generated_at": "2026-05-13 10:00:00",
            "summary": old_summary,
        },
        report,
    ]


def main() -> None:
    report = _report_fixture()
    reports = _reports_fixture(report)

    params = normalize_analytics_query_params(
        top_n_raw="999",
        trend_limit_raw="0",
        include_samples_raw="true",
        top_n_default=10,
        top_n_max=50,
        trend_limit_default=20,
        trend_limit_max=30,
        include_samples_default=False,
    )
    assert params["top_n"] == 50, params
    assert params["trend_limit"] == 1, params
    assert params["include_samples"] is True, params

    payload = build_analytics_payload(
        report=report,
        reports=reports,
        top_n=10,
        trend_limit=20,
        include_samples=True,
        histogram_buckets_text="0,50,100,200,500,1000,3000,5000",
        failed_penalty=10,
        error_penalty=15,
        slow_penalty=5,
        assertion_missing_penalty=2,
        assertions_enabled=True,
    )

    assert payload["report_name"] == "demo.html", payload["report_name"]
    assert payload["distributions"]["status"]["FAILED"] == 2, payload["distributions"]
    assert payload["diagnostics"]["category_summary"], payload["diagnostics"]
    assert payload["quality_score"]["total_score"] <= 100, payload["quality_score"]
    assert payload["coverage"]["source_total"] >= payload["coverage"]["executed_total"], payload["coverage"]
    assert len(payload["trend"]["success_rate"]) >= 1, payload["trend"]

    print("report-analytics-ok")


if __name__ == "__main__":
    main()
