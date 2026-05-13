import json
import re
from pathlib import Path
from typing import Dict, List


_REPORTS_DIR: Path = Path("reports").resolve()


ReportRecord = Dict[str, object]
SummaryRecord = Dict[str, object]


def configure_reports_dir(reports_dir: Path) -> None:
    global _REPORTS_DIR
    _REPORTS_DIR = Path(reports_dir).resolve()


def is_total_report_file(path: Path) -> bool:
    name = path.name.lower()
    return "_page_" not in name


def report_meta_files() -> List[Path]:
    if not _REPORTS_DIR.exists():
        return []
    return [path for path in sorted(_REPORTS_DIR.glob("*_meta.json"), reverse=True) if is_total_report_file(path)]


def _extract_json_value(text: str) -> object:
    text = text.strip().rstrip(",")
    return json.loads(text)


def _load_report_meta_summary(meta_path: Path) -> ReportRecord:
    data: ReportRecord = {
        "report_name": meta_path.name.replace("_meta.json", ".html"),
        "generated_at": "",
        "host_name": "",
        "collection_name": "",
        "source_file": "",
        "source_original_file": "",
        "summary": {},
        "results": [],
        "_summary_only": True,
    }
    summary: SummaryRecord = {}
    in_summary = False
    summary_keys = {
        "total", "passed", "failed", "error", "success_rate", "duration", "start_time", "end_time",
        "avg_response_ms", "max_response_ms", "p95_response_ms",
    }

    with meta_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith('"results"'):
                break
            if not in_summary and line.startswith('"summary"') and line.endswith("{"):
                in_summary = True
                continue
            if in_summary and line.startswith("}"):
                in_summary = False
                continue

            match = re.match(r'^"(?P<key>[^"]+)"\s*:\s*(?P<value>.+)$', line)
            if not match:
                continue
            key = str(match.group("key") or "")
            value_text = str(match.group("value") or "")

            try:
                value = _extract_json_value(value_text)
            except Exception:
                continue

            if in_summary:
                if key in summary_keys:
                    summary[key] = value
                continue

            if key in {"report_name", "generated_at", "host_name", "collection_name", "source_file", "source_original_file", "details_file", "base_url", "execution_mode", "interrupted", "interrupt_reason", "assertion_strict_mode"}:
                data[key] = value

    if not summary:
        summary = {"total": 0, "passed": 0, "failed": 0, "error": 0, "success_rate": "0%"}
    data["summary"] = summary
    return data


def load_report_meta(meta_path: Path, include_results: bool = True) -> ReportRecord:
    if include_results:
        with meta_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if "summary" not in data:
            data["summary"] = {}
        data["_summary_only"] = False
        return data if isinstance(data, dict) else {}

    try:
        return _load_report_meta_summary(meta_path)
    except Exception:
        # 兜底：若轻量解析失败，退回标准解析并丢弃 results，保持接口可用。
        with meta_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if "summary" not in data:
            data["summary"] = {}
        data["results"] = []
        data["_summary_only"] = True
        return data if isinstance(data, dict) else {}


def legacy_postman_html_files() -> List[Path]:
    if not _REPORTS_DIR.exists():
        return []
    return [path for path in sorted(_REPORTS_DIR.glob("*.html"), reverse=True) if is_total_report_file(path)]


def load_legacy_postman_report(report_path: Path) -> ReportRecord:
    content = report_path.read_text(encoding="utf-8")
    results_match = re.search(r"let\s+allResults\s*=\s*(\[.*?\]);", content, re.S)
    total_match = re.search(r"<label>总计</label>\s*<span>(\d+)</span>", content)
    passed_match = re.search(r"<label>? 通过</label>\s*<span>(\d+)</span>", content)
    failed_match = re.search(r"<label>? 失败</label>\s*<span>(\d+)</span>", content)
    error_match = re.search(r"<label>! 错误</label>\s*<span>(\d+)</span>", content)
    rate_match = re.search(r"<label>成功率</label>\s*<span>([^<]+)</span>", content)
    duration_match = re.search(r"<label>耗时</label>\s*<span>([^<]+)</span>", content)
    time_match = re.search(r"开始:\s*([^|<]+)\s*\|\s*结束:\s*([^<]+)", content)

    raw_results = json.loads(results_match.group(1)) if results_match else []
    if not isinstance(raw_results, list):
        raw_results = []
    results = [
        {
            "key": " | ".join([
                item.get("folder", "") or "-",
                item.get("name", "") or "-",
                item.get("method", "") or "-",
                item.get("url", "") or "-",
            ]),
            "name": item.get("name", ""),
            "folder": item.get("folder", ""),
            "method": item.get("method", ""),
            "url": item.get("url", ""),
            "status": item.get("status", ""),
            "status_code": item.get("status_code"),
            "message": item.get("message", ""),
            "err_code": item.get("err_code", ""),
        }
        for item in raw_results
        if isinstance(item, dict)
    ]

    generated_at = time_match.group(2).strip() if time_match else ""
    return {
        "report_name": report_path.name,
        "generated_at": generated_at,
        "host_name": "legacy-html",
        "collection_name": "",
        "source_file": str(report_path),
        "summary": {
            "total": int(total_match.group(1)) if total_match else len(results),
            "passed": int(passed_match.group(1)) if passed_match else len([item for item in results if item.get("status") == "PASSED"]),
            "failed": int(failed_match.group(1)) if failed_match else len([item for item in results if item.get("status") == "FAILED"]),
            "error": int(error_match.group(1)) if error_match else len([item for item in results if item.get("status") == "ERROR"]),
            "success_rate": rate_match.group(1).strip() if rate_match else "0.00%",
            "duration": duration_match.group(1).strip() if duration_match else "",
            "start_time": time_match.group(1).strip() if time_match else "",
            "end_time": time_match.group(2).strip() if time_match else "",
        },
        "details_file": f"{report_path.stem}_details.json",
        "results": results,
        "meta_file": "",
        "legacy": True,
    }
