#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report server smoke verification for v1.1.4 fixes.

Usage:
    python test_data/smoke_report_server_20260427.py
"""

import json
from typing import Any, Dict

import requests


def _must_ok(resp: requests.Response, name: str) -> Dict[str, Any]:
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} failed: {resp.status_code} {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError:
        return {"_text": resp.text}


def main() -> None:
    base = "http://127.0.0.1:5000"
    out: Dict[str, Any] = {}

    out["health"] = _must_ok(requests.get(f"{base}/health", timeout=20), "health").get("status")
    out["index_status"] = requests.get(f"{base}/", timeout=20).status_code

    reports = _must_ok(requests.get(f"{base}/api/reports", timeout=20), "api/reports")
    if not isinstance(reports, list) or not reports:
        raise RuntimeError("No available reports in /api/reports")

    report_name = str(reports[0].get("report_name") or "").strip()
    if not report_name:
        raise RuntimeError("No report_name in first report item")
    out["report_name"] = report_name

    out["report_view_status"] = requests.get(
        f"{base}/report-view", params={"report": report_name}, timeout=20
    ).status_code

    out["results_true_total"] = _must_ok(
        requests.get(
            f"{base}/api/report-results/{report_name}",
            params={"include_excluded": "true", "page": 1, "page_size": 5},
            timeout=20,
        ),
        "report-results true",
    ).get("total")

    out["results_false_total"] = _must_ok(
        requests.get(
            f"{base}/api/report-results/{report_name}",
            params={"include_excluded": "false", "page": 1, "page_size": 5},
            timeout=20,
        ),
        "report-results false",
    ).get("total")

    # manual-cases CRUD
    _must_ok(requests.get(f"{base}/api/manual-cases/{report_name}", timeout=20), "manual-cases get")
    case_payload = {
        "name": "自动验证-临时用例",
        "folder": "人工补录",
        "method": "GET",
        "url": f"{base}/health",
        "status": "PASSED",
        "expected_status": 200,
        "status_code": 200,
        "request_info": {"headers": {}, "params": {}, "body": None},
        "response_info": {"headers": {}, "body": {"status": "ok"}},
    }
    add = _must_ok(
        requests.post(
            f"{base}/api/manual-cases/add",
            json={"report_name": report_name, "case": case_payload},
            timeout=20,
        ),
        "manual-cases add",
    )
    case_id = str((add.get("case") or {}).get("id") or "")
    if not case_id:
        raise RuntimeError("manual-cases add did not return case id")
    out["manual_case_id"] = case_id

    upd = _must_ok(
        requests.put(
            f"{base}/api/manual-cases/update",
            json={
                "report_name": report_name,
                "case_id": case_id,
                "case": {
                    "name": "自动验证-临时用例-更新",
                    "message": "smoke update",
                    "status": "FAILED",
                    "err_code": "SMOKE",
                },
            },
            timeout=20,
        ),
        "manual-cases update",
    )
    out["manual_update_status"] = (upd.get("case") or {}).get("status")

    dele = _must_ok(
        requests.delete(
            f"{base}/api/manual-cases/delete",
            json={"report_name": report_name, "case_id": case_id},
            timeout=20,
        ),
        "manual-cases delete",
    )
    out["manual_delete_count"] = len(dele.get("manual_cases") or [])

    # export-collection
    export_resp = _must_ok(
        requests.post(
            f"{base}/api/export-collection",
            json={"report_name": report_name, "include_auth": False, "export_scope": "full"},
            timeout=30,
        ),
        "export-collection",
    )
    out["export_file_name"] = export_resp.get("file_name")
    out["export_scope"] = export_resp.get("export_scope")

    # security checks
    out["re_request_invalid_scheme_status"] = requests.post(
        f"{base}/re-request-api", json={"url": "ftp://example.com/a", "method": "GET"}, timeout=20
    ).status_code
    out["proxy_invalid_scheme_status"] = requests.post(
        f"{base}/api/proxy-request", json={"url": "file:///etc/passwd", "method": "GET"}, timeout=20
    ).status_code

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
