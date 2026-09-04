#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目脚手架真机冒烟（N13，v1.39.0 阶段 3）。

前提：服务已启动且 ENABLE_PROJECT_SCAFFOLD=true。
Usage:
    python test_data/smoke_project_scaffold.py
    SMOKE_BASE_URL=http://127.0.0.1:5341 python test_data/smoke_project_scaffold.py

链路：A15 建模板 → A2 建项目 → A1 列表 → A9 无集合 409 → A7 加集合 →
A9 执行 → 轮询终态 → A3 history 收敛（done/failed 非挂起）→ 报告可见 →
A12/A13 占位 501 → A5 删项目清理。
"""

import os
import time
import uuid
from typing import Any, Dict

import requests

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000").rstrip("/")


def _must_ok(resp: requests.Response, name: str) -> Dict[str, Any]:
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} failed: {resp.status_code} {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError:
        return {"_text": resp.text}
    if isinstance(data, dict):
        data = data.get("data") or data
    return data


def _error_code(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("error_code") or "")
    except ValueError:
        return ""


def _smoke_template() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "id": f"tpl_smoke_{uuid.uuid4().hex[:8]}",
        "name": "N13冒烟模板",
        "version": "1.0.0",
        "metadata_template": {"owner": "{{owner}}"},
        "variables": [
            {"key": "owner", "label": "负责人", "type": "string", "required": True}
        ],
        "files": [],
    }


def _smoke_collection() -> Dict[str, Any]:
    return {
        "info": {"name": "冒烟集合"},
        "item": [
            {
                "name": "健康检查",
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                'pm.test("状态码200", function () { pm.response.to.have.status(200); });'
                            ],
                        },
                    }
                ],
                "request": {"method": "GET", "url": f"{BASE}/health"},
            }
        ],
    }


def main() -> None:
    out: Dict[str, Any] = {}

    out["health"] = _must_ok(requests.get(f"{BASE}/health", timeout=20), "health").get(
        "status"
    )

    # A15 用户模板（id 由服务端派生重写，G-33：必须用返回值）
    created_tpl = _must_ok(
        requests.post(f"{BASE}/api/project-templates", json=_smoke_template(), timeout=20),
        "A15",
    )
    tpl_id = str(created_tpl["id"])
    out["template_id"] = tpl_id

    # A2 建项目
    proj_name = f"N13冒烟项目-{uuid.uuid4().hex[:8]}"
    project = _must_ok(
        requests.post(
            f"{BASE}/api/projects",
            json={
                "name": proj_name,
                "template_id": tpl_id,
                "variables": {"owner": "smoke"},
            },
            timeout=20,
        ),
        "A2",
    )
    pid = str(project["id"])
    out["project_id"] = pid

    # A1 列表可见（search 匹配名称/描述）
    listed = _must_ok(
        requests.get(f"{BASE}/api/projects", params={"search": proj_name}, timeout=20),
        "A1",
    )
    if not any(item.get("id") == pid for item in listed.get("items") or []):
        raise RuntimeError(f"A1 列表未找到项目 {pid}")

    # A9 无集合 → 409 PRJ_502
    resp = requests.post(f"{BASE}/api/projects/{pid}/execute", timeout=20)
    if resp.status_code != 409 or _error_code(resp) != "PRJ_502":
        raise RuntimeError(f"无集合执行应 409 PRJ_502，实得 {resp.status_code} {_error_code(resp)}")

    # A7 加集合
    col = _must_ok(
        requests.post(
            f"{BASE}/api/projects/{pid}/collections", json=_smoke_collection(), timeout=20
        ),
        "A7",
    )
    out["collection_id"] = col.get("id")
    if int(col.get("request_count") or 0) != 1:
        raise RuntimeError(f"A7 request_count 应为 1，实得 {col.get('request_count')}")

    # A9 真实入队
    exec_result = _must_ok(
        requests.post(f"{BASE}/api/projects/{pid}/execute", timeout=20), "A9"
    )
    job_id = str(exec_result["job_id"])
    report_name = str(exec_result["report_name"])
    out["job_id"] = job_id
    out["report_name"] = report_name
    if exec_result.get("status") != "queued" or not report_name.endswith(".html"):
        raise RuntimeError(f"A9 返回异常: {exec_result}")
    if job_id[:8] not in report_name:
        raise RuntimeError(f"report_name 未嵌 job_id[:8]: {report_name}")

    # 轮询终态（原始 job dict，无包装）
    final: Dict[str, Any] = {}
    for _ in range(60):
        st = requests.get(f"{BASE}/api/run-postman-status/{job_id}", timeout=20)
        if st.status_code == 404:
            break  # 内存淘汰，交给 A3 懒对账
        final = st.json() or {}
        if final.get("status") not in ("queued", "running"):
            break
        time.sleep(1)
    out["job_status"] = final.get("status")

    # A3 懒对账收敛：history 头条必须离开 queued/running
    detail = _must_ok(requests.get(f"{BASE}/api/projects/{pid}", timeout=20), "A3")
    history = (detail.get("statistics") or {}).get("execution_history") or []
    if not history:
        raise RuntimeError("A3 history 为空，入队即记录未生效")
    head = history[0]
    if head.get("job_id") != job_id or head.get("report_name") != report_name:
        raise RuntimeError(f"A3 头条不匹配: {head}")
    if head.get("status") in (None, "queued", "running"):
        raise RuntimeError(f"执行后仍挂起: {head}")
    out["history_head"] = {"status": head.get("status"), "passed": head.get("passed"), "failed": head.get("failed")}
    if final.get("status") == "success":
        if head.get("status") != "done" or int(head.get("passed") or 0) < 1:
            raise RuntimeError(f"成功执行应收敛 done 且 passed>=1，实得 {head}")

    # 报告中心可见
    reports = _must_ok(requests.get(f"{BASE}/api/reports", timeout=20), "api/reports")
    names = [r.get("report_name") for r in reports] if isinstance(reports, list) else []
    if report_name not in names:
        raise RuntimeError(f"报告中心未找到 {report_name}")
    view = requests.get(
        f"{BASE}/report-view", params={"report": report_name}, timeout=20
    )
    if view.status_code != 200:
        raise RuntimeError(f"报告页访问 {view.status_code}")

    # A12/A13 占位（S4.2 接线后本段改为真实导出断言）
    for path, method in (
        (f"/api/projects/{pid}/export/tracing.csv", "get"),
        (f"/api/projects/{pid}/export", "get"),
    ):
        resp = getattr(requests, method)(f"{BASE}{path}", timeout=20)
        if resp.status_code != 501 or _error_code(resp) != "COM_001":
            raise RuntimeError(f"导出占位应 501 COM_001: {path} → {resp.status_code}")

    # 清理：A5 删除项目（确认位）
    _must_ok(
        requests.delete(f"{BASE}/api/projects/{pid}", json={"confirm": True}, timeout=20),
        "A5",
    )

    print("SMOKE OK:", ", ".join(f"{k}={v}" for k, v in out.items()))


if __name__ == "__main__":
    main()
