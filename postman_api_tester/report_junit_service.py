import io
import xml.etree.ElementTree as ET
from typing import Any, Dict


def _parse_duration_to_seconds(duration_str: str) -> float:
    text = str(duration_str or "").strip().rstrip("s").strip()
    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0


def build_junit_xml(report: Dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    results = report.get("results") or []
    report_name = report.get("report_name", "postman_tests")
    total = int(summary.get("total", 0))
    failures = int(summary.get("failed", 0))
    errors = int(summary.get("error", 0))
    duration_sec = _parse_duration_to_seconds(summary.get("duration", "0s"))

    suite = ET.Element("testsuite")
    suite.set("name", report_name)
    suite.set("tests", str(total))
    suite.set("failures", str(failures))
    suite.set("errors", str(errors))
    suite.set("time", f"{duration_sec:.3f}")
    suite.set("timestamp", str(summary.get("start_time", "")))

    for item in results:
        folder = item.get("folder", "") or ""
        name = item.get("name", "") or "unknown"
        classname = f"{folder}.{name}".strip(".") if folder else name
        tc = ET.SubElement(suite, "testcase")
        tc.set("name", name)
        tc.set("classname", classname)
        tc.set("time", str(round(item.get("response_time_ms", 0) / 1000, 3)))

        status = item.get("status", "")
        if status == "FAILED":
            failure = ET.SubElement(tc, "failure")
            failure.set("message", str(item.get("message", "")))
            failure.text = str(item.get("message", ""))
        elif status == "ERROR":
            error_el = ET.SubElement(tc, "error")
            error_el.set("message", str(item.get("message", "")))
            error_el.text = str(item.get("message", ""))

    try:
        ET.indent(suite, space="  ")
    except AttributeError:
        pass

    buf = io.StringIO()
    ET.ElementTree(suite).write(buf, encoding="unicode", xml_declaration=True)
    return buf.getvalue()
