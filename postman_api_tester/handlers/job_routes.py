"""任务执行路由处理函数（run-postman、ad-hoc、状态查询）。"""

import json
import logging
import uuid
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, SupportsInt, Tuple

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from postman_api_tester.handlers.base_handler import json_error as _json_error
from postman_api_tester.utils.collection_utils import (
    build_adhoc_collection as _svc_build_adhoc_collection,
    normalize_adhoc_case as _svc_normalize_adhoc_case,
)
from postman_api_tester.services.report_job_execution_service import (
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

logger = logging.getLogger(__name__)

REPORTS_DIR = ReportServerApp._resolve_reports_dir()
UPLOADS_DIR = (Path(__file__).resolve().parent.parent / "uploaded_collections").resolve()


def _parse_selected_item_paths(raw: Any) -> List[List[int]]:
    if raw is None:
        return []
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"selected_item_paths 不是有效 JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("selected_item_paths 必须是数组")
    normalized: List[List[int]] = []
    seen: set = set()
    for item in data:
        if not isinstance(item, list) or not item:
            continue
        if not all(isinstance(index, int) and index >= 0 for index in item):
            raise ValueError("selected_item_paths 的每条路径必须是非负整数数组")
        key = tuple(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(list(item))
    logger.info(
        "selected item paths parsed",
        extra={"event": "handler.collection.selected_paths.parsed", "path_count": len(normalized)},
    )
    return normalized

_RUN_POSTMAN_JOB_FN = partial(
    _job_run_postman_job,
    set_run_job=set_run_job,
    invalidate_reports_cache=_repo_invalidate_reports_cache,
)


def _parse_judgment_config_from_form(form: Any) -> Optional[Dict[str, Any]]:
    """从表单解析可配置结果判定参数，无任何配置时返回 None。填写即启用。"""
    config: Dict[str, Any] = {}

    raw_err_codes = form.get("judgment_success_err_codes")
    if raw_err_codes is not None and str(raw_err_codes).strip():
        config["success_err_codes"] = str(raw_err_codes).strip()

    raw_messages = form.get("judgment_success_messages")
    if raw_messages is not None and str(raw_messages).strip():
        config["success_messages"] = str(raw_messages).strip()

    return config if config else None


def _parse_judgment_config_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 JSON payload 解析可配置结果判定参数，无任何配置时返回 None。填写即启用。"""
    raw_cfg = payload.get("judgment_config")
    if isinstance(raw_cfg, dict) and raw_cfg:
        config: Dict[str, Any] = {}
        if "success_err_codes" in raw_cfg and str(raw_cfg["success_err_codes"]).strip():
            config["success_err_codes"] = str(raw_cfg["success_err_codes"]).strip()
        if "success_messages" in raw_cfg and str(raw_cfg["success_messages"]).strip():
            config["success_messages"] = str(raw_cfg["success_messages"]).strip()
        return config if config else None
    return None


def _resolve_output_dir(
    output_dir: str,
    report_name: Optional[str],
    *,
    reports_dir: Path,
) -> Tuple[str, Optional[str]]:
    """解析并校验输出目录路径，防止目录遍历。

    若 output_dir 误填为 .html 文件名，则自动移至 report_name。
    非空 output_dir 必须位于 reports_dir 子树内，否则回退至 reports_dir。
    """
    if output_dir.lower().endswith(".html"):
        if not report_name:
            report_name = output_dir
        output_dir = ""
    if output_dir:
        resolved = (reports_dir / output_dir).resolve()
        try:
            resolved.relative_to(reports_dir)
            return str(resolved), report_name
        except ValueError:
            pass
    return str(reports_dir), report_name


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
    """上传 Collection 并执行测试任务 API。错误码：JOB_RUN_001-007"""
    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return _json_error("请上传有效的 Postman JSON 文件", 400, "JOB_RUN_001")

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return _json_error("上传文件必须是 .json 格式", 400, "JOB_RUN_002")

    original_name = _sanitize_uploaded_name(original_name)

    base_url = str(request.form.get("base_url", "")).strip() or None
    if base_url is not None and not _svc_is_valid_http_url(base_url):
        return _json_error("base_url 仅允许合法的 http/https 地址", 400, "JOB_RUN_003")
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
    output_dir = str(request.form.get("output_dir", "")).strip()
    report_name = str(request.form.get("report_name", "")).strip() or None
    output_dir, report_name = _resolve_output_dir(output_dir, report_name, reports_dir=REPORTS_DIR)
    results_per_page = clamp_run_results_per_page(request.form.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    run_scope = str(request.form.get("run_scope", "all")).strip().lower() or "all"
    raw_selected_paths = request.form.get("selected_item_paths", "")
    selected_item_paths: List[List[int]] = []
    if ENABLE_SELECTIVE_RUN and run_scope == "selected":
        try:
            selected_item_paths = _parse_selected_item_paths(raw_selected_paths)
        except ValueError as exc:
            return _json_error(str(exc), 400, "JOB_RUN_004")
        if not selected_item_paths:
            return _json_error("选择了仅执行已选接口，但未提供有效 selected_item_paths", 400, "JOB_RUN_005")

    # 解析可配置结果判定（judgment_config）
    judgment_config = _parse_judgment_config_from_form(request.form)

    # 解析数据驱动文件（可选）
    data_file_path = ""
    data_file = request.files.get("data_file")
    if data_file and str(data_file.filename or "").strip():
        data_filename = str(data_file.filename or "").strip().lower()
        if not data_filename.endswith((".csv", ".json")):
            return _json_error("数据文件仅支持 .csv 或 .json 格式", 400, "JOB_RUN_006")
        data_suffix = Path(str(data_file.filename or ".csv")).suffix or ".csv"
        data_file_path = str(_build_saved_json_path(UPLOADS_DIR, uuid.uuid4().hex, f"_data{data_suffix}"))
        data_file.save(data_file_path)

    # 解析预置变量（可选，JSON 字符串）
    initial_variables: Optional[Dict[str, str]] = None
    raw_initial_vars = request.form.get("initial_variables", "")
    if isinstance(raw_initial_vars, str) and raw_initial_vars.strip():
        try:
            parsed_vars = json.loads(raw_initial_vars.strip())
            if isinstance(parsed_vars, dict):
                initial_variables = {str(k): str(v) for k, v in parsed_vars.items()}
        except (json.JSONDecodeError, ValueError):
            return _json_error("initial_variables 必须是有效的 JSON 对象", 400, "JOB_RUN_007")

    suffix = Path(original_name).suffix or ".json"
    job_id = uuid.uuid4().hex
    saved_file = _build_saved_json_path(UPLOADS_DIR, job_id, suffix)
    collection_file.save(str(saved_file))

    # 保存上传的文件（formdata/binary 模式）
    uploaded_files_paths: Dict[str, str] = {}
    upload_files = request.files.getlist("upload_files")
    if upload_files:
        upload_dir = UPLOADS_DIR / job_id / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        for upload_file in upload_files:
            if upload_file and str(upload_file.filename or "").strip():
                # 文件名格式: upload_key_original_filename
                raw_name = str(upload_file.filename or "").strip()
                parts = raw_name.split("_", 2)
                upload_key = parts[0] + "_" + parts[1] if len(parts) >= 3 else raw_name
                file_name = parts[2] if len(parts) >= 3 else raw_name
                file_path = upload_dir / file_name
                upload_file.save(str(file_path))
                uploaded_files_paths[upload_key] = str(file_path)

    job_params = _build_run_postman_job_params(
        job_id=job_id,
        original_name=original_name,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name,
        base_url=base_url,
        token=token,
        selected_item_paths=selected_item_paths if selected_item_paths else None,
        judgment_config=judgment_config,
        data_file=data_file_path,
        initial_variables=initial_variables,
        env_name=env_name,
        uploaded_files=uploaded_files_paths if uploaded_files_paths else None,
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
    """Ad-hoc 接口测试提交 API。错误码：JOB_ADHOC_001-005"""
    if not ENABLE_ADHOC_RUN:
        return _json_error("当前环境未启用直接新增接口测试能力。", 403, "JOB_ADHOC_001")

    payload = request.get_json(silent=True) or {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        return _json_error("cases 不能为空，且必须是数组。", 400, "JOB_ADHOC_002")
    if len(raw_cases) > ADHOC_MAX_ITEMS:
        return _json_error(f"单次最多支持 {ADHOC_MAX_ITEMS} 条接口。", 400, "JOB_ADHOC_003")

    base_url = str(payload.get("base_url", "")).strip() or None
    if base_url is not None and not _svc_is_valid_http_url(base_url):
        return _json_error("base_url 仅允许合法的 http/https 地址", 400, "JOB_ADHOC_004")

    token = str(payload.get("token", "")).strip() or None
    output_dir = str(payload.get("output_dir", "")).strip()
    report_name = str(payload.get("report_name", "")).strip() or None
    output_dir, report_name = _resolve_output_dir(output_dir, report_name, reports_dir=REPORTS_DIR)
    results_per_page = clamp_run_results_per_page(payload.get("results_per_page", RUN_RESULTS_PER_PAGE_DEFAULT))
    collection_name = str(payload.get("collection_name", "")).strip() or ADHOC_DEFAULT_COLLECTION_NAME

    try:
        normalized_cases = [_svc_normalize_adhoc_case(item, idx, base_url) for idx, item in enumerate(raw_cases)]
        collection_data = _svc_build_adhoc_collection(normalized_cases, collection_name, base_url)
    except ValueError as exc:
        return _json_error(str(exc), 400, "JOB_ADHOC_005")

    job_id = uuid.uuid4().hex
    saved_file = _build_saved_json_path(UPLOADS_DIR, job_id)
    with saved_file.open("w", encoding="utf-8") as f:
        json.dump(collection_data, f, indent=2, ensure_ascii=False)

    source_original_file = _sanitize_uploaded_name(f"{collection_name}.json")
    # 解析可配置结果判定（judgment_config）
    adhoc_judgment_config = _parse_judgment_config_from_payload(payload)
    job_params = _build_ad_hoc_job_params(
        job_id=job_id,
        source_original_file=source_original_file,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name,
        base_url=base_url,
        token=token,
        judgment_config=adhoc_judgment_config,
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
    """查询任务执行状态 API。错误码：JOB_STATUS_001"""
    job = get_run_job(job_id)
    if not job:
        return _json_error("任务不存在。", 404, "JOB_STATUS_001")
    return jsonify(job)
