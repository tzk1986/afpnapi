"""JUnit XML 导出路由处理函数。"""

import logging
import re
from pathlib import Path

from flask import make_response
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error
from postman_api_tester.report_server_config import ENABLE_JUNIT_EXPORT
from postman_api_tester.report_repository import find_report as _repo_find_report
from postman_api_tester.services.report_junit_service import build_junit_xml as _svc_build_junit_xml

logger = logging.getLogger(__name__)


def api_export_junit(report_name: str) -> ResponseReturnValue:
    """JUnit XML 导出 API。错误码：COL_JUNIT_001-003"""
    if not ENABLE_JUNIT_EXPORT:
        return _json_error("当前环境未启用 JUnit XML 导出能力。", 403, "COL_JUNIT_001")

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在：{report_name}", 404, "COL_JUNIT_002")

    try:
        xml_content = _svc_build_junit_xml(report)
    except Exception as exc:
        logger.exception("JUnit XML 生成失败: %s", exc)
        return _json_error("JUnit XML 生成失败", 500, "COL_JUNIT_003")

    safe_stem = re.sub(r'[^\w一-鿿\-.]', '_', Path(report_name).stem)[:80]
    filename = f"{safe_stem}_junit.xml"
    resp = make_response(xml_content)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
