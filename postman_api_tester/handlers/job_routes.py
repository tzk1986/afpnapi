"""任务执行路由处理函数（run-postman、ad-hoc、状态查询）。"""

import json
import uuid
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, SupportsInt

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import BaseHandler
from postman_api_tester.handlers.collection_handler import (
    build_adhoc_collection as _svc_build_adhoc_collection,
    normalize_adhoc_case as _svc_normalize_adhoc_case,
    parse_selected_item_paths as _svc_parse_selected_item_paths,
)
from postman_api_tester.handlers.job_handler import (
    enqueue_job_with_worker as _job_enqueue_job_with_worker,
    run_postman_job as _job_run_postman_job,
)
from postman_api_tester.report_job_store import get_run_job, set_run_job
from postman_api_tester.report_server_config import (
    ADHOC_DEFAULT_COLLECTION_NAME,
    ADHOC_MAX_ITEMS,
    ENABLE_ADHOC_RUN,
    ENABLE_SELECTIVE_RUN,
    ENVIRONMENTS,
    RUN_RESULTS_PER_PAGE_DEFAULT,
    RUN_RESULTS_PER_PAGE_MAX,
    RUN_RESULTS_PER_PAGE_MIN,
)
from postman_api_tester.report_server_app import ReportServerApp
from postman_api_tester.report_repository import invalidate_reports_cache as _repo_invalidate_reports_cache
from postman_api_tester.services.report_job_submission_service import (
    build_ad_hoc_job_params as _build_ad_hoc_job_params,
    build_run_postman_job_params as _build_run_postman_job_params,
    build_saved_json_path as _build_saved_json_path,
    sanitize_uploaded_name as _sanitize_uploaded_name,
)
from postman_api_tester.services.report_request_service import (
    is_valid_http_url as _svc_is_valid_http_url,
)
from postman_api_tester.services.report_results_service import build_job_queued_payload
from postman_api_tester.utils.server_utils import clamp_page_size as _clamp_page_size

REPORTS_DIR = ReportServerApp._resolve_reports_dir()
UPLOADS_DIR = (Path(__file__).resolve().parent.parent / "uploaded_collections").resolve()

_RUN_POSTMAN_JOB_FN = partial(
    _job_run_postman_job,
    set_run_job=set_run_job,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)


def _json_error(message: str, status_code: int) -> ResponseReturnValue:
    from postman_api_tester.exceptions import ValidationError
    return BaseHandler.error_response(ValidationError(message), status_code)


def clamp_run_results_per_page(value: SupportsInt | str | bytes | bytearray | None) -> int:
    return _clamp_page_size(
        value,
        default=RUN_RESULTS_PER_PAGE_DEFAULT,
        min_size=RUN_RESULTS_PER_PAGE_MIN,
        max_size=RUN_RESULTS_PER_PAGE_MAX,
    )


def _enqueue_job(
    *,
    job_id: str,
    saved_file: str,
    job_params: Dict[str, Any],
    results_per_page: int,
    selected_item_paths: Optional[List[List[int]]],
) -> None:
    _job_enqueue_job_with_worker(
        job_id=job_id,
        saved_file=saved_file,
        job_params=job_params,
        results_per_page=results_per_page,
        run_postman_job_fn=_RUN_POSTMAN_JOB_FN,
        set_run_job=set_run_job,
        default_output_dir=str(REPORTS_DIR),
        selected_item_paths=selected_item_paths,
    )


def api_run_postman() -> ResponseReturnValue:
    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return _json_error("请上传有效的 Postman JSON 文件", 400)

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return _json_error("上传文件必须是 .json 格式", 400)

    original_name = _sanitize_uploaded_name(original_name)

    base_url = str(request.form.get("base_url", "")).strip() or None
    if base_url is not None and not _svc_is_valid_http_url(base_url):
        return _json_error("base_url 仅允许合法的 http/https 地址", 400)
    token = str(request.form.get("token", "")).strip() or None
    env_name = str(request.form.get("env_name", "")).strip()
    if env_name and env_name in ENVIRONMENTS:
        env_cfg = ENVIRONMENTS[env_name]
        if isinstance(env_cfg, dict):
            if not base_url and env_cfg.get("base_url", "").strip():
                env_base = env_cfg["base_url"].strip()
                if _svc_is_valid_http_url(env_base):
                    base_url = env_base
            if not token and env_cfg.get("token", "").strip():
                token = env_cfg["token"].strip()
    output_dir = str(request.form.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(request.form.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(request.form.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    run_scope = str(request.form.get("run_scope", "all")).strip().lower() or "all"
    raw_selected_paths = request.form.get("selected_item_paths", "")
    selected_item_paths: List[List[int]] = []
    if ENABLE_SELECTIVE_RUN and run_scope == "selected":
        try:
            selected_item_paths = _svc_parse_selected_item_paths(raw_selected_paths)
        except ValueError as exc:
            return _json_error(str(exc), 400)
        if not selected_item_paths:
            return _json_error("选择了仅执行已选接口，但未提供有效 selected_item_paths", 400)

    suffix = Path(original_name).suffix or ".json"
    job_id = uuid.uuid4().hex
    saved_file = _build_saved_json_path(UPLOADS_DIR, job_id, suffix)
    collection_file.save(str(saved_file))
    job_params = _build_run_postman_job_params(
        job_id=job_id,
        original_name=original_name,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name,
        base_url=base_url,
        token=token,
        selected_item_paths=selected_item_paths if selected_item_paths else None,
    )

    _enqueue_job(
        job_id=job_id,
        saved_file=str(saved_file),
        job_params=job_params,
        results_per_page=results_per_page,
        selected_item_paths=selected_item_paths if selected_item_paths else None,
    )

    return jsonify(build_job_queued_payload(job_id=job_id, message="任务已创建，请轮询状态接口获取执行进度。"))


def api_run_ad_hoc_tests() -> ResponseReturnValue:
    if not ENABLE_ADHOC_RUN:
        return _json_error("当前环境未启用直接新增接口测试能力。", 403)

    payload = request.get_json(silent=True) or {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        return _json_error("cases 不能为空，且必须是数组。", 400)
    if len(raw_cases) > ADHOC_MAX_ITEMS:
        return _json_error(f"单次最多支持 {ADHOC_MAX_ITEMS} 条接口。", 400)

    base_url = str(payload.get("base_url", "")).strip() or None
    if base_url is not None and not _svc_is_valid_http_url(base_url):
        return _json_error("base_url 仅允许合法的 http/https 地址", 400)

    token = str(payload.get("token", "")).strip() or None
    output_dir = str(payload.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(payload.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(payload.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    collection_name = str(payload.get("collection_name", "")).strip() or ADHOC_DEFAULT_COLLECTION_NAME

    try:
        normalized_cases = [_svc_normalize_adhoc_case(item, idx, base_url) for idx, item in enumerate(raw_cases)]
        collection_data = _svc_build_adhoc_collection(normalized_cases, collection_name, base_url)
    except ValueError as exc:
        return _json_error(str(exc), 400)

    job_id = uuid.uuid4().hex
    saved_file = _build_saved_json_path(UPLOADS_DIR, job_id)
    with saved_file.open("w", encoding="utf-8") as f:
        json.dump(collection_data, f, indent=2, ensure_ascii=False)

    source_original_file = _sanitize_uploaded_name(f"{collection_name}.json")
    job_params = _build_ad_hoc_job_params(
        job_id=job_id,
        source_original_file=source_original_file,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name,
        base_url=base_url,
        token=token,
    )
    job_params["collection_name"] = collection_name

    _enqueue_job(
        job_id=job_id,
        saved_file=str(saved_file),
        job_params=job_params,
        results_per_page=results_per_page,
        selected_item_paths=None,
    )

    return jsonify(build_job_queued_payload(job_id=job_id, message="ad-hoc 任务已创建，请轮询状态接口获取执行进度。"))


def api_run_postman_status(job_id: str) -> ResponseReturnValue:
    job = get_run_job(job_id)
    if not job:
        return _json_error("任务不存在。", 404)
    return jsonify(job)
