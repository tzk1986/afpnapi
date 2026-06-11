"""开发导读：
- 职责：安全更新报告 meta 文件（读-改-写），并处理并发写锁。
- 入口：update_report_meta()。
- 目标：让上层以 updater 回调方式专注业务字段变更。
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict


def update_report_meta(
    report_name: str,
    updater: Callable[[Dict[str, Any]], Dict[str, Any]],
    *,
    reports_dir: Path,
    get_report_write_lock: Callable[[str], Any],
    find_report: Callable[[str], Dict[str, Any]],
    invalidate_reports_cache: Callable[[], None],
) -> Dict[str, Any]:
    """以原子方式读-改-写报告 meta 文件，调用 updater 回调执行变更。"""
    lock = get_report_write_lock(report_name)
    with lock:
        report = find_report(report_name)
        meta_file_name = str(report.get("meta_file") or "").strip()
        if not meta_file_name:
            raise ValueError("报告缺少 meta_file，无法更新元数据。")
        meta_path = reports_dir / meta_file_name
        if not meta_path.exists():
            raise FileNotFoundError(f"元数据文件不存在: {meta_file_name}")

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        if not isinstance(meta.get("manual_cases"), list):
            meta["manual_cases"] = []
        if not isinstance(meta.get("manual_exclusions"), list):
            meta["manual_exclusions"] = []

        updated_meta = updater(meta)
        if not isinstance(updated_meta, dict):
            raise ValueError("meta 更新回调必须返回 dict")

        tmp_meta = meta_path.with_suffix(".tmp")
        with tmp_meta.open("w", encoding="utf-8") as f:
            json.dump(updated_meta, f, indent=2, ensure_ascii=False)
        os.replace(str(tmp_meta), str(meta_path))

        invalidate_reports_cache()
        return updated_meta
