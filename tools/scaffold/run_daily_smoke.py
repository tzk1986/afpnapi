# -*- coding: utf-8 -*-
"""每日冒烟 CLI 调度器（不依赖 report server，Web 端不可用时照样执行）。

背景（已核实源码）：
  1. CLI 入口 ``python -m postman_api_tester.postman_api_tester`` 执行完不返回
     失败退出码（恒为 0），调度判定必须像本脚本这样自行统计结果；
  2. "一键重试失败用例"是 web 路由能力，CLI 不可用，本脚本通过
     ``selected_item_paths``（仅执行已选接口）重跑本轮失败接口实现等价重试；
  3. run_postman_tests() 的 env_name / data_file / 全局变量持久化在 CLI 下同样
     生效（variables.json 自动加载与保存），跨集合传链没问题。

manifest 行格式（空行与 # 开头行为注释）：
    <collection路径> [env=<环境名>] [data=<csv或json路径>]
    路径支持绝对路径或相对项目根目录。

用法:
    python tools/scaffold/run_daily_smoke.py [manifest]
        [--output DIR] [--retries N] [--no-retry] [--env 默认环境名]

退出码: 0=全部通过, 1=存在最终失败, 2=参数/文件错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 支持环境变量覆盖，便于服务器部署
# 优先级: MANIFEST_FILE 环境变量 > 本地开发默认路径
DEFAULT_MANIFEST = os.environ.get(
    "SMOKE_MANIFEST_FILE",
    os.path.join("D:", os.sep, "-11", "11", "auto-assets", "collections", "smoke_manifest.txt")
)
DEFAULT_OUTPUT = os.path.join(ROOT, "reports", "daily_smoke")


def parse_manifest(path: str, default_env: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            collection = parts[0]
            if not os.path.isabs(collection):
                collection = os.path.join(ROOT, collection)
            env, data = default_env, ""
            for opt in parts[1:]:
                key, _, value = opt.partition("=")
                if key == "env":
                    env = value
                elif key == "data":
                    data = value
            entries.append({"collection": collection, "env": env, "data": data})
    return entries


def _failed(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in results if r.get("status") != "PASSED"]


def run_one(entry: Dict[str, str], output_dir: str, retries: int) -> Dict[str, Any]:
    from postman_api_tester.postman_api_tester import run_postman_tests

    collection = entry["collection"]
    name = os.path.splitext(os.path.basename(collection))[0]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    row: Dict[str, Any] = {
        "collection": name,
        "file": collection,
        "env": entry["env"],
        "total": 0,
        "failed_final": 0,
        "fixed_by_retry": 0,
        "report_files": [],
        "error": "",
    }

    if not os.path.isfile(collection):
        row["error"] = "文件不存在"
        row["failed_final"] = 1
        return row

    try:
        report = run_postman_tests(
            postman_file=collection,
            env_name=entry["env"],
            data_file=entry["data"],
            output_dir=output_dir,
            report_name=f"smoke_{name}_{stamp}",
        )
    except Exception as exc:  # 环境不通等整体异常也算失败，不中断后续集合
        row["error"] = f"执行异常: {exc}"
        row["failed_final"] = 1
        return row

    if report.generated_report_file:
        row["report_files"].append(report.generated_report_file)
    row["total"] = len(report.results)
    failed = _failed(report.results)

    attempt = 0
    while failed and attempt < retries:
        attempt += 1
        paths = sorted({tuple(r.get("item_path") or ()) for r in failed})
        try:
            retry_report = run_postman_tests(
                postman_file=collection,
                env_name=entry["env"],
                data_file=entry["data"],
                selected_item_paths=[list(p) for p in paths],
                output_dir=output_dir,
                report_name=f"smoke_{name}_{stamp}_retry{attempt}",
            )
        except Exception as exc:
            row["error"] = f"重试异常: {exc}"
            break
        if retry_report.generated_report_file:
            row["report_files"].append(retry_report.generated_report_file)
        still_failed = _failed(retry_report.results)
        row["fixed_by_retry"] += len(failed) - len(still_failed)
        failed = still_failed

    row["failed_final"] = len(failed)
    row["failed_details"] = [
        {
            "name": r.get("name"),
            "status": r.get("status"),
            "message": (r.get("message") or "")[:300],
            "item_path": r.get("item_path"),
        }
        for r in failed
    ]
    return row


def write_summary(rows: List[Dict[str, Any]], output_dir: str) -> Tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total = sum(r["total"] for r in rows)
    final_failed = sum(r["failed_final"] for r in rows)
    fixed = sum(r["fixed_by_retry"] for r in rows)
    passed = total - final_failed
    summary = {
        "time": stamp,
        "total": total,
        "passed": passed,
        "failed_final": final_failed,
        "fixed_by_retry": fixed,
        "pass_rate": f"{(passed / total * 100):.1f}%" if total else "N/A",
        "rows": rows,
    }
    json_path = os.path.join(output_dir, f"smoke_summary_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    lines = [
        f"# 每日冒烟报告 {stamp}",
        "",
        f"- 总数 {total} | 通过 {passed} | 重试后通过 {fixed} | 最终失败 {final_failed} | 通过率 {summary['pass_rate']}",
        "",
        "| Collection | 总数 | 最终失败 | 重试挽回 | 环境 | 备注 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        note = r["error"] or ("、".join(os.path.basename(p) for p in r["report_files"][:2]))
        lines.append(
            f"| {r['collection']} | {r['total']} | {r['failed_final']} | {r['fixed_by_retry']} | {r['env'] or '-'} | {note} |"
        )
    md_path = os.path.join(output_dir, f"smoke_summary_{stamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return json_path, md_path


def push_feishu(summary_json: str) -> None:
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        return
    import requests

    with open(summary_json, encoding="utf-8") as f:
        s = json.load(f)
    text = (
        f"[接口冒烟] {s['time']} 通过率 {s['pass_rate']}"
        f"（总 {s['total']} / 失败 {s['failed_final']} / 重试挽回 {s['fixed_by_retry']}）"
    )
    try:
        requests.post(webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=10)
    except Exception as exc:
        print(f"飞书推送失败（不影响退出码）: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="每日接口冒烟 CLI 调度器")
    ap.add_argument("manifest", nargs="?", default=DEFAULT_MANIFEST, help="冒烟清单文件")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="报告输出目录")
    ap.add_argument("--retries", type=int, default=1, help="失败重试轮数（默认1）")
    ap.add_argument("--no-retry", action="store_true", help="禁用失败重试")
    ap.add_argument("--env", default="", help="默认环境名（清单未标注 env= 时生效）")
    args = ap.parse_args()

    if not os.path.isfile(args.manifest):
        print(f"清单不存在: {args.manifest}", file=sys.stderr)
        return 2
    os.makedirs(args.output, exist_ok=True)
    retries = 0 if args.no_retry else max(0, args.retries)

    entries = parse_manifest(args.manifest, args.env)
    if not entries:
        print("清单为空", file=sys.stderr)
        return 2

    rows = []
    for entry in entries:
        print(f">>> 执行 {entry['collection']} (env={entry['env'] or '默认'})")
        rows.append(run_one(entry, args.output, retries))

    json_path, md_path = write_summary(rows, args.output)
    push_feishu(json_path)

    ok = sum(r["failed_final"] for r in rows) == 0
    print(f"\n汇总: {md_path}")
    print(f"结果: {'全部通过' if ok else '存在失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
