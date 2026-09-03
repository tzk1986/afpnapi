# -*- coding: utf-8 -*-
"""UI 测试 CLI 调度器（不依赖 report server，可无人值守执行）。

背景：
  1. UI 测试通常通过 Web 界面触发执行，缺少 CLI 入口
  2. 本脚本支持通过命令行批量执行 UI 测试用例
  3. 支持指定用例 ID、全部执行、按标签过滤
  4. 执行结果生成汇总报告，支持飞书推送

用法:
    # 执行所有 UI 测试用例
    python tools/scaffold/run_ui_tests.py

    # 执行指定用例
    python tools/scaffold/run_ui_tests.py --case-ids rec_1786497336501_tplbks,rec_1786497570120_1zeuov

    # 按标签过滤执行
    python tools/scaffold/run_ui_tests.py --tag 冒烟

    # 指定浏览器类型
    python tools/scaffold/run_ui_tests.py --browser firefox

    # 带截图执行
    python tools/scaffold/run_ui_tests.py --screenshots

退出码: 0=全部通过, 1=存在失败, 2=参数/环境错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_OUTPUT = os.path.join(ROOT, "reports", "ui_tests")


def check_playwright() -> bool:
    """检查 Playwright 是否可用。"""
    try:
        from postman_api_tester.services.ui_headless_engine import is_playwright_available
        return is_playwright_available()
    except ImportError:
        return False


def list_cases(tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """列出 UI 测试用例，可按标签过滤。"""
    from postman_api_tester.services.ui_case_store import UiCaseStore

    store = UiCaseStore()
    cases = store.list_cases()

    if tags:
        tag_set = set(tags)
        cases = [c for c in cases if tag_set.intersection(set(c.get("tags", [])))]

    return cases


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """获取单个用例的完整数据。"""
    from postman_api_tester.services.ui_case_store import UiCaseStore

    store = UiCaseStore()
    return store.get_case(case_id)


def run_one_case(
    case_data: Dict[str, Any],
    browser_type: str,
    take_screenshots: bool,
    output_dir: str,
) -> Dict[str, Any]:
    """执行单个 UI 测试用例。"""
    from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine

    case_id = case_data.get("id", "unknown")
    case_name = case_data.get("name", "未命名")
    steps = case_data.get("steps", [])
    base_url = case_data.get("base_url", "")

    result: Dict[str, Any] = {
        "case_id": case_id,
        "case_name": case_name,
        "status": "pending",
        "steps_total": len(steps),
        "steps_passed": 0,
        "steps_failed": 0,
        "duration_ms": 0,
        "error": "",
        "screenshots_dir": None,
    }

    if not steps:
        result["status"] = "skipped"
        result["error"] = "无测试步骤"
        return result

    # 准备截图目录
    screenshots_dir = None
    if take_screenshots:
        screenshots_dir = os.path.join(output_dir, "screenshots", f"case_{case_id}")
        os.makedirs(screenshots_dir, exist_ok=True)
        result["screenshots_dir"] = screenshots_dir

    try:
        engine = UiHeadlessEngine(
            browser_type=browser_type,
            screenshots_dir=Path(screenshots_dir) if screenshots_dir else None,
        )

        start_time = time.time()
        summary = engine.execute(
            steps=steps,
            base_url=base_url,
            options={"take_screenshots": take_screenshots},
            job_id=f"cli_{case_id}_{int(time.time())}",
        )
        duration_ms = int((time.time() - start_time) * 1000)

        result["duration_ms"] = duration_ms
        result["steps_passed"] = summary.get("steps_passed", 0)
        result["steps_failed"] = summary.get("steps_failed", 0)
        result["status"] = "passed" if result["steps_failed"] == 0 else "failed"

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)[:500]

    return result


def write_summary(
    results: List[Dict[str, Any]],
    output_dir: str,
    browser_type: str,
) -> Tuple[str, str]:
    """生成执行汇总报告。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    total_cases = len(results)
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    error = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    total_steps = sum(r["steps_total"] for r in results)
    total_passed = sum(r["steps_passed"] for r in results)
    total_failed = sum(r["steps_failed"] for r in results)
    total_duration = sum(r["duration_ms"] for r in results)

    summary = {
        "timestamp": stamp,
        "browser": browser_type,
        "total_cases": total_cases,
        "passed_cases": passed,
        "failed_cases": failed,
        "error_cases": error,
        "skipped_cases": skipped,
        "total_steps": total_steps,
        "passed_steps": total_passed,
        "failed_steps": total_failed,
        "total_duration_ms": total_duration,
        "pass_rate": f"{(passed / total_cases * 100):.1f}%" if total_cases else "N/A",
        "results": results,
    }

    json_path = os.path.join(output_dir, f"ui_test_summary_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    lines = [
        f"# UI 测试报告 {stamp}",
        "",
        f"- 浏览器: {browser_type}",
        f"- 用例总数: {total_cases} | 通过: {passed} | 失败: {failed} | 错误: {error} | 跳过: {skipped}",
        f"- 步骤总数: {total_steps} | 通过: {total_passed} | 失败: {total_failed}",
        f"- 总耗时: {total_duration / 1000:.1f}s",
        f"- 通过率: {summary['pass_rate']}",
        "",
        "| 用例ID | 用例名称 | 状态 | 步骤(通过/总数) | 耗时 | 备注 |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        status_emoji = {"passed": "✅", "failed": "❌", "error": "⚠️", "skipped": "⏭️"}.get(r["status"], "?")
        note = r["error"][:50] if r["error"] else ""
        lines.append(
            f"| {r['case_id'][:12]} | {r['case_name'][:20]} | {status_emoji} {r['status']} | "
            f"{r['steps_passed']}/{r['steps_total']} | {r['duration_ms']}ms | {note} |"
        )

    md_path = os.path.join(output_dir, f"ui_test_summary_{stamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return json_path, md_path


def push_feishu(summary_json: str) -> None:
    """推送执行结果到飞书。"""
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        return

    import requests

    with open(summary_json, encoding="utf-8") as f:
        s = json.load(f)

    text = (
        f"[UI测试] {s['timestamp']} 通过率 {s['pass_rate']} "
        f"(用例 {s['passed_cases']}/{s['total_cases']} | "
        f"步骤 {s['passed_steps']}/{s['total_steps']})"
    )

    try:
        requests.post(webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=10)
    except Exception as exc:
        print(f"飞书推送失败（不影响退出码）: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="UI 测试 CLI 调度器")
    ap.add_argument("--case-ids", default="", help="指定用例ID（逗号分隔），为空则执行全部")
    ap.add_argument("--tag", action="append", dest="tags", help="按标签过滤（可多次指定）")
    ap.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"], help="浏览器类型")
    ap.add_argument("--screenshots", action="store_true", help="启用截图")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="报告输出目录")
    ap.add_argument("--list", action="store_true", help="仅列可用用例，不执行")
    args = ap.parse_args()

    # 检查 Playwright
    if not check_playwright():
        print("错误: Playwright 未安装或不可用", file=sys.stderr)
        print("请执行: pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    # 列出模式
    if args.list:
        cases = list_cases(tags=args.tags)
        print(f"UI 测试用例列表（共 {len(cases)} 个）：")
        for c in cases:
            tags_str = ", ".join(c.get("tags", [])) or "无标签"
            print(f"  {c['id']}: {c['name']} ({c['step_count']}步) [{tags_str}]")
        return 0

    # 获取待执行用例
    if args.case_ids:
        case_ids = [cid.strip() for cid in args.case_ids.split(",") if cid.strip()]
        cases_to_run = []
        for cid in case_ids:
            case_data = get_case(cid)
            if case_data:
                cases_to_run.append(case_data)
            else:
                print(f"警告: 用例不存在 {cid}", file=sys.stderr)
    else:
        cases_list = list_cases(tags=args.tags)
        cases_to_run = []
        for c in cases_list:
            case_data = get_case(c["id"])
            if case_data:
                cases_to_run.append(case_data)

    if not cases_to_run:
        print("没有可执行的用例", file=sys.stderr)
        return 2

    os.makedirs(args.output, exist_ok=True)

    # 执行用例
    results = []
    for case_data in cases_to_run:
        case_name = case_data.get("name", "未命名")
        print(f">>> 执行: {case_name} ({case_data.get('id', '')})")
        result = run_one_case(
            case_data=case_data,
            browser_type=args.browser,
            take_screenshots=args.screenshots,
            output_dir=args.output,
        )
        results.append(result)
        status_str = {"passed": "通过", "failed": "失败", "error": "错误", "skipped": "跳过"}.get(result["status"], result["status"])
        print(f"    结果: {status_str} ({result['steps_passed']}/{result['steps_total']}步, {result['duration_ms']}ms)")

    # 生成汇总
    json_path, md_path = write_summary(results, args.output, args.browser)
    push_feishu(json_path)

    # 输出总结
    passed = sum(1 for r in results if r["status"] == "passed")
    print(f"\n汇总: {md_path}")
    print(f"结果: {passed}/{len(results)} 用例通过")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
