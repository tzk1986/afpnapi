#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report analytics compare smoke test."""

from __future__ import annotations

from typing import Any, Dict, List

from postman_api_tester.handlers.report_analytics_handler import build_analytics_compare_payload


def _report(report_name: str, success_rate: str, avg_ms: int, failed: int, error: int) -> Dict[str, Any]:
    return {
        "report_name": report_name,
        "collection_name": "demo",
        "generated_at": "2026-05-14 10:00:00",
        "summary": {
            "total": 10,
            "passed": 10 - failed - error,
            "failed": failed,
            "error": error,
            "success_rate": success_rate,
            "avg_response_ms": avg_ms,
            "max_response_ms": 900,
            "p95_response_ms": 700,
        },
        "manual_cases": [],
        "results": [
            {
                "key": f"{report_name}-1",
                "name": "query",
                "folder": "F1",
                "method": "GET",
                "url": "/query",
                "status": "PASSED",
                "response_time_ms": max(1, avg_ms - 20),
                "assertion_results": [{"ok": True}],
            },
            {
                "key": f"{report_name}-2",
                "name": "payment",
                "folder": "F2",
                "method": "POST",
                "url": "/payment",
                "status": "FAILED" if failed > 0 else "PASSED",
                "message": "timeout" if failed > 0 else "",
                "response_time_ms": avg_ms + 35,
                "assertion_results": [],
            },
        ],
    }


def _reports_fixture() -> List[Dict[str, Any]]:
    return [
        _report("left_demo.html", "70.00%", 210, 2, 1),
        _report("right_demo.html", "85.00%", 180, 1, 0),
    ]


def main() -> None:
    reports = _reports_fixture()
    left_report = reports[0]
    right_report = reports[1]

    payload = build_analytics_compare_payload(
        left_report=left_report,
        right_report=right_report,
        reports=reports,
        top_n=10,
        trend_limit=20,
        include_samples=False,
        histogram_buckets_text="0,50,100,200,500,1000,3000,5000",
        failed_penalty=10,
        error_penalty=15,
        slow_penalty=5,
        assertion_missing_penalty=2,
        assertions_enabled=True,
    )

    assert payload["left_snapshot"]["report_name"] == "left_demo.html", payload
    assert payload["right_snapshot"]["report_name"] == "right_demo.html", payload
    assert payload["delta"]["success_rate_delta"] == 15.0, payload["delta"]
    assert payload["delta"]["avg_response_delta_ms"] == -30, payload["delta"]
    assert payload["delta"]["failed_delta"] == -1, payload["delta"]
    assert payload["delta"]["error_delta"] == -1, payload["delta"]
    assert isinstance(payload["score_delta"], float), payload

    print("report-analytics-compare-ok")


if __name__ == "__main__":
    main()
