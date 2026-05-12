#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sensitive headers smoke test.

验证点：
1. details 写入时敏感请求头必须被掩码为 ***
2. 导出请求头剔除逻辑应移除敏感头并保留普通头
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from postman_api_tester.postman_api_tester import PostmanTestReport
from postman_api_tester.report_server_utils import strip_auth_headers


def _build_report() -> PostmanTestReport:
    report = PostmanTestReport()
    report.results = [
        {
            "name": "sensitive-header-smoke",
            "method": "GET",
            "url": "http://example.local/api",
            "status": "PASSED",
            "status_code": 200,
            "message": "ok",
            "request_info": {
                "headers": {
                    "Authorization": "Bearer abc",
                    "Cookie": "SESSION=xyz",
                    "X-CSRF-Token": "csrf-value",
                    "X-Normal": "keep-me",
                },
                "params": {},
                "body": None,
            },
            "response_info": {"headers": {}, "body": {"ok": True}},
        }
    ]
    return report


def main() -> None:
    report = _build_report()

    details_data = report._build_details_data()
    req_headers = details_data["0"]["request_info"]["headers"]
    assert req_headers.get("Authorization") == "***", req_headers
    assert req_headers.get("Cookie") == "***", req_headers
    assert req_headers.get("X-CSRF-Token") == "***", req_headers
    assert req_headers.get("X-Normal") == "keep-me", req_headers

    stripped = strip_auth_headers(
        {
            "authorization": "a",
            "cookie": "b",
            "set-cookie": "c",
            "api-key": "d",
            "x-normal": "ok",
        }
    )
    assert "authorization" not in stripped, stripped
    assert "cookie" not in stripped, stripped
    assert "set-cookie" not in stripped, stripped
    assert "api-key" not in stripped, stripped
    assert stripped.get("x-normal") == "ok", stripped

    with TemporaryDirectory() as tmp:
        report.start_time = report.start_time
        out = str(Path(tmp) / "sensitive_smoke.html")
        report.generate_html_report(out, results_per_page=20)

    print("sensitive-headers-ok")


if __name__ == "__main__":
    main()
