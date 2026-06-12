"""集合预览与导出路由处理函数。"""

import json
from pathlib import Path
from typing import Iterator

from flask import Response, jsonify, request, stream_with_context
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error
from postman_api_tester.utils.collection_utils import (
    extract_collection_preview_items as _svc_extract_collection_preview_items,
)
from postman_api_tester.report_server_config import (
    COLLECTION_PREVIEW_MAX_ITEMS,
    ENABLE_MANUAL_CASES,
    ENABLE_SELECTIVE_RUN,
    MANUAL_CASE_FOLDER_NAME,
    REPORT_EXPORT_ALLOW_REPORT_ONLY,
    REPORT_EXPORT_DEFAULT_SCOPE,
    REPORT_EXPORT_INCLUDE_AUTH_DEFAULT,
    REPORT_EXPORT_STREAM_THRESHOLD,
)
from postman_api_tester.report_server_utils import to_bool as _to_bool
from postman_api_tester.report_repository import find_report as _repo_find_report
from postman_api_tester.services.report_export_service import (
    export_collection_with_latest_params as _svc_export_collection_with_latest_params,
)
from postman_api_tester.services.report_results_service import (
    build_collection_preview_payload,
    build_export_collection_payload,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = (PROJECT_ROOT / "uploaded_collections").resolve()
EXPORTS_DIR = (UPLOADS_DIR / "exports").resolve()


def api_collection_preview() -> ResponseReturnValue:
    """Collection 接口预览 API。错误码：COL_PREVIEW_001-004"""
    if not ENABLE_SELECTIVE_RUN:
        return _json_error("当前环境未启用接口选择执行功能。", 403, "COL_PREVIEW_001")

    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return _json_error("请上传有效的 Postman JSON 文件", 400, "COL_PREVIEW_002")

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return _json_error("上传文件必须是 .json 格式", 400, "COL_PREVIEW_003")

    try:
        collection_data = json.load(collection_file.stream)
    except Exception as exc:
        return _json_error(f"JSON 解析失败：{exc}", 400, "COL_PREVIEW_004")

    preview_items = _svc_extract_collection_preview_items(collection_data, COLLECTION_PREVIEW_MAX_ITEMS)
    total = len(preview_items)
    truncated = False
    if total >= COLLECTION_PREVIEW_MAX_ITEMS:
        truncated = True

    return jsonify(
        build_collection_preview_payload(
            file_name=original_name,
            total=total,
            truncated=truncated,
            max_items=COLLECTION_PREVIEW_MAX_ITEMS,
            items=preview_items,
        )
    )


def api_export_collection() -> ResponseReturnValue:
    """Collection 导出 API。错误码：COL_EXPORT_001-003"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    include_auth = _to_bool(payload.get("include_auth"), default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT)
    export_scope = str(payload.get("export_scope", REPORT_EXPORT_DEFAULT_SCOPE)).strip().lower() or REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope not in {"full", "report_only"}:
        export_scope = REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope == "report_only" and not REPORT_EXPORT_ALLOW_REPORT_ONLY:
        export_scope = "full"
    if not report_name:
        return _json_error("report_name 不能为空", 400, "COL_EXPORT_001")

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在：{report_name}", 404, "COL_EXPORT_002")

    try:
        exported = _svc_export_collection_with_latest_params(
            report,
            exports_dir=EXPORTS_DIR,
            collection_preview_max_items=COLLECTION_PREVIEW_MAX_ITEMS,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            manual_case_folder_name=MANUAL_CASE_FOLDER_NAME,
            report_export_allow_report_only=REPORT_EXPORT_ALLOW_REPORT_ONLY,
            include_auth=include_auth,
            export_scope=export_scope,
        )
    except Exception as exc:
        return _json_error(str(exc), 400, "COL_EXPORT_003")

    return jsonify(
        build_export_collection_payload(
            report_name=report_name,
            exported=exported,
            include_auth=include_auth,
        )
    )


def api_export_collection_stream() -> ResponseReturnValue:
    """Collection 流式导出 API。错误码：COL_EXPORT_001-004"""
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    include_auth = _to_bool(payload.get("include_auth"), default=REPORT_EXPORT_INCLUDE_AUTH_DEFAULT)
    export_scope = str(payload.get("export_scope", REPORT_EXPORT_DEFAULT_SCOPE)).strip().lower() or REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope not in {"full", "report_only"}:
        export_scope = REPORT_EXPORT_DEFAULT_SCOPE
    if export_scope == "report_only" and not REPORT_EXPORT_ALLOW_REPORT_ONLY:
        export_scope = "full"
    if not report_name:
        return _json_error("report_name 不能为空", 400, "COL_EXPORT_001")

    try:
        report = _repo_find_report(report_name)
    except FileNotFoundError:
        return _json_error(f"报告不存在：{report_name}", 404, "COL_EXPORT_002")

    try:
        exported = _svc_export_collection_with_latest_params(
            report,
            exports_dir=EXPORTS_DIR,
            collection_preview_max_items=COLLECTION_PREVIEW_MAX_ITEMS,
            enable_manual_cases=ENABLE_MANUAL_CASES,
            manual_case_folder_name=MANUAL_CASE_FOLDER_NAME,
            report_export_allow_report_only=REPORT_EXPORT_ALLOW_REPORT_ONLY,
            include_auth=include_auth,
            export_scope=export_scope,
        )
    except Exception as exc:
        return _json_error(str(exc), 400, "COL_EXPORT_003")

    export_path = Path(str(exported.get("file_path") or ""))
    if not export_path.exists():
        return _json_error("导出文件不存在，无法进行流式下载", 500, "COL_EXPORT_004")

    def generate_chunks() -> Iterator[bytes]:
        with export_path.open("rb") as file:
            while True:
                chunk = file.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    response = Response(stream_with_context(generate_chunks()), mimetype="application/json")
    response.headers["Content-Disposition"] = f"attachment; filename={exported['file_name']}"
    response.headers["X-Export-Scope"] = str(exported.get("export_scope") or "full")
    return response
