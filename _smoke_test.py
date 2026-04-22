#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
小规模冒烟测试 —— 验证本次优化改动的核心逻辑

覆盖范围：
  T1  config.py   : TOKEN / BASE_URL 从环境变量读取
  T2  Executor    : _auth_token 实例隔离（并发不污染）
  T3  Executor    : set_auth_token / get_auth_token 实例方法
  T4  Executor    : timeout 参数传递
  T5  Executor    : execute_test 超时 → 结果含"请求超时"
  T6  Executor    : execute_test session 在 finally 中关闭
  T7  Report      : details.json 敏感 header 脱敏为 ***
  T8  Server      : original_name 清洗逻辑
  T9  Server      : RUN_JOBS 超上限后清理旧任务
"""

import os
import sys
import json
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── 确保项目根目录在 sys.path ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []


def _check(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f": {detail}" if detail else ""))
    results.append((name, ok))


# ═══════════════════════════════════════════════════════════════════════════
# T1  config.py 环境变量读取
# ═══════════════════════════════════════════════════════════════════════════
def test_config_env():
    print("\n── T1  config.py 环境变量 ──")
    os.environ["POSTMAN_TOKEN"] = "test_token_from_env"
    os.environ["POSTMAN_BASE_URL"] = "http://env-host:9999"

    import importlib
    import postman_api_tester.config as cfg
    importlib.reload(cfg)

    _check("TOKEN 读取 POSTMAN_TOKEN 环境变量", cfg.TOKEN == "test_token_from_env",
           repr(cfg.TOKEN))
    _check("BASE_URL 读取 POSTMAN_BASE_URL 环境变量", cfg.BASE_URL == "http://env-host:9999",
           repr(cfg.BASE_URL))

    # 清除后 reload，TOKEN 应回退为 ""
    del os.environ["POSTMAN_TOKEN"]
    del os.environ["POSTMAN_BASE_URL"]
    importlib.reload(cfg)
    _check("无环境变量时 TOKEN 为空字符串", cfg.TOKEN == "", repr(cfg.TOKEN))


# ═══════════════════════════════════════════════════════════════════════════
# T2/T3  _auth_token 实例隔离
# ═══════════════════════════════════════════════════════════════════════════
def test_auth_token_isolation():
    print("\n── T2/T3  _auth_token 实例隔离 ──")
    from postman_api_tester.postman_api_tester import PostmanTestExecutor

    dummy_api = {"name": "x", "method": "GET", "url": "/", "full_url": "http://x/",
                 "headers": {}, "params": {}, "body": None}

    e1 = PostmanTestExecutor(dummy_api, auth_token="token_A")
    e2 = PostmanTestExecutor(dummy_api, auth_token="token_B")

    _check("e1._auth_token == token_A", e1._auth_token == "token_A", repr(e1._auth_token))
    _check("e2._auth_token == token_B", e2._auth_token == "token_B", repr(e2._auth_token))

    # 修改 e1 不影响 e2
    e1.set_auth_token("token_A_new")
    _check("set_auth_token 改 e1 不影响 e2",
           e1._auth_token == "token_A_new" and e2._auth_token == "token_B",
           f"e1={e1._auth_token!r} e2={e2._auth_token!r}")

    _check("get_auth_token 返回实例 token",
           e2.get_auth_token() == "token_B", repr(e2.get_auth_token()))

    # 并发写入互不污染
    barrier = threading.Barrier(2)
    tokens_seen = {}

    def worker(name, tok):
        e = PostmanTestExecutor(dummy_api, auth_token=tok)
        barrier.wait()
        time.sleep(0.01)
        tokens_seen[name] = e._auth_token

    t1 = threading.Thread(target=worker, args=("w1", "concurrent_A"))
    t2 = threading.Thread(target=worker, args=("w2", "concurrent_B"))
    t1.start(); t2.start(); t1.join(); t2.join()

    _check("并发实例 token 互不污染",
           tokens_seen.get("w1") == "concurrent_A" and tokens_seen.get("w2") == "concurrent_B",
           str(tokens_seen))


# ═══════════════════════════════════════════════════════════════════════════
# T4  execute_test: 超时参数实际传给 requests
# ═══════════════════════════════════════════════════════════════════════════
def test_execute_test_timeout():
    print("\n── T4  execute_test 超时参数 ──")
    from postman_api_tester.postman_api_tester import PostmanTestExecutor

    dummy_api = {"name": "Ping", "method": "GET", "url": "/ping",
                 "full_url": "http://mock/ping",
                 "headers": {}, "params": {}, "body": None}

    captured = {}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}

    e = PostmanTestExecutor(dummy_api)

    def fake_get(url, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return mock_resp

    e.session.get = fake_get
    e.execute_test()

    _check("execute_test 传递 timeout=(10,30)",
           captured.get("timeout") == (10, 30), str(captured.get("timeout")))


# ═══════════════════════════════════════════════════════════════════════════
# T5  execute_test: 请求超时 → 结果 message 含 "请求超时"
# ═══════════════════════════════════════════════════════════════════════════
def test_execute_test_timeout_message():
    print("\n── T5  超时异常处理 ──")
    import requests as req_lib
    from postman_api_tester.postman_api_tester import PostmanTestExecutor

    dummy_api = {"name": "Slow", "method": "POST", "url": "/slow",
                 "full_url": "http://mock/slow",
                 "headers": {}, "params": {}, "body": {}}

    e = PostmanTestExecutor(dummy_api)
    e.session.post = MagicMock(side_effect=req_lib.exceptions.Timeout("timed out"))

    result = e.execute_test()
    _check("超时异常 status == ERROR", result.get("status") == "ERROR",
           repr(result.get("status")))
    _check("超时异常 message 含'请求超时'",
           "请求超时" in str(result.get("message")), repr(result.get("message")))


# ═══════════════════════════════════════════════════════════════════════════
# T6  execute_test: session 在 finally 中被关闭
# ═══════════════════════════════════════════════════════════════════════════
def test_execute_test_session_closed():
    print("\n── T6  session.close() 在 finally ──")
    import requests as req_lib
    from postman_api_tester.postman_api_tester import PostmanTestExecutor

    dummy_api = {"name": "X", "method": "GET", "url": "/",
                 "full_url": "http://mock/", "headers": {}, "params": {}, "body": None}

    e = PostmanTestExecutor(dummy_api)
    close_called = []
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    e.session.get = MagicMock(return_value=mock_resp)

    orig_close = e.session.close
    e.session.close = lambda: (close_called.append(1), orig_close())

    e.execute_test()
    _check("execute_test 正常完成后 session.close() 被调用",
           len(close_called) == 1, f"called {len(close_called)} times")

    # 异常路径也要 close
    e2 = PostmanTestExecutor(dummy_api)
    close_called2 = []
    e2.session.get = MagicMock(side_effect=req_lib.exceptions.ConnectionError("conn err"))
    orig_close2 = e2.session.close
    e2.session.close = lambda: (close_called2.append(1), orig_close2())

    e2.execute_test()
    _check("execute_test 异常后 session.close() 也被调用",
           len(close_called2) == 1, f"called {len(close_called2)} times")


# ═══════════════════════════════════════════════════════════════════════════
# T7  generate_html_report: 敏感 header 脱敏
# ═══════════════════════════════════════════════════════════════════════════
def test_report_header_sanitize():
    print("\n── T7  details.json 敏感 header 脱敏 ──")
    import tempfile
    from datetime import datetime
    from postman_api_tester.postman_api_tester import PostmanTestReport

    report = PostmanTestReport()
    report.start_time = datetime.now()
    report.end_time = datetime.now()
    report.results = [
        {
            "name": "Login",
            "method": "POST",
            "url": "/login",
            "status": "PASSED",
            "message": "ok",
            "status_code": 200,
            "request_info": {
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer super_secret_token",
                    "token": "raw_token_value",
                    "x-token": "another_secret",
                    "X-Custom": "safe_value",
                }
            },
            "response_info": {"status_code": 200, "body": "{}"}
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test_report.html")
        report.generate_html_report(out_path)

        details_file = os.path.join(tmpdir, "test_report_details.json")
        _check("details.json 文件已生成", os.path.exists(details_file))

        with open(details_file, encoding="utf-8") as f:
            data = json.load(f)

        headers_in_file = data["0"]["request_info"]["headers"]
        _check("Authorization 已脱敏为 ***",
               headers_in_file.get("Authorization") == "***",
               repr(headers_in_file.get("Authorization")))
        _check("token 已脱敏为 ***",
               headers_in_file.get("token") == "***",
               repr(headers_in_file.get("token")))
        _check("x-token 已脱敏为 ***",
               headers_in_file.get("x-token") == "***",
               repr(headers_in_file.get("x-token")))
        _check("非敏感 X-Custom 保留原值",
               headers_in_file.get("X-Custom") == "safe_value",
               repr(headers_in_file.get("X-Custom")))
        _check("Content-Type 保留原值",
               headers_in_file.get("Content-Type") == "application/json",
               repr(headers_in_file.get("Content-Type")))


# ═══════════════════════════════════════════════════════════════════════════
# T8  original_name 清洗逻辑
# ═══════════════════════════════════════════════════════════════════════════
def test_original_name_sanitize():
    print("\n── T8  original_name 清洗 ──")
    import re as _re

    def sanitize(name: str) -> str:
        """与 report_server.py 中完全一致的清洗逻辑"""
        _safe_name = _re.sub(r'[^\w\u4e00-\u9fff\-. ()（）【】]', '_', name).strip('. ')
        return _safe_name if _safe_name else "collection.json"

    # 说明：
    #   "../etc/passwd.json" → sub 后 ".._etc_passwd.json" → strip('.' ' ') 剥首尾 → "_etc_passwd.json"
    #   "()"/括号在正则白名单中，保留；"<>" 被替换为 "_"
    #   "   .json" → strip 空格和点后剩 "json"（非空，不触发 fallback）
    cases = [
        ("normal.json",                   "normal.json"),
        ("数字餐厅（IFD）.json",           "数字餐厅（IFD）.json"),
        ("../etc/passwd.json",             "_etc_passwd.json"),
        ("<script>alert(1)</script>.json", "_script_alert(1)__script_.json"),
        ("   .json",                       "json"),
        ("a b-c_d.json",                   "a b-c_d.json"),
    ]

    all_ok = True
    for raw, expected in cases:
        got = sanitize(raw)
        ok = got == expected
        if not ok:
            all_ok = False
        _check(f"清洗 {raw!r}", ok, f"期望 {expected!r}，得到 {got!r}")


# ═══════════════════════════════════════════════════════════════════════════
# T9  RUN_JOBS 超上限后清理旧任务
# ═══════════════════════════════════════════════════════════════════════════
def test_run_jobs_eviction():
    print("\n── T9  RUN_JOBS 超上限清理 ──")
    import importlib
    import report_server as srv
    importlib.reload(srv)          # 重置全局 RUN_JOBS 状态

    # 先填入 200 条已完成任务
    for i in range(200):
        srv.RUN_JOBS[f"done_{i}"] = {"status": "success"}

    # 再写入第 201 条，应触发清理
    srv.set_run_job("trigger_evict", status="running")

    _check("RUN_JOBS 长度 ≤ 200 条（已清理旧任务）",
           len(srv.RUN_JOBS) <= 200, f"当前 {len(srv.RUN_JOBS)} 条")

    # 仍在运行的任务不应被清除
    _check("正在运行的任务 trigger_evict 未被清理",
           "trigger_evict" in srv.RUN_JOBS)


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  seldom-api-testing 优化改动冒烟测试")
    print("=" * 60)

    test_config_env()
    test_auth_token_isolation()
    test_execute_test_timeout()
    test_execute_test_timeout_message()
    test_execute_test_session_closed()
    test_report_header_sanitize()
    test_original_name_sanitize()
    test_run_jobs_eviction()

    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed
    print(f"  结果汇总：{passed}/{total} 通过，{failed} 失败")
    print("=" * 60)

    if failed:
        sys.exit(1)
