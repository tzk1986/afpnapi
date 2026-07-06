"""UI 测试执行路由处理函数。

提供执行任务创建、状态查询、报告获取、执行历史和回放页面渲染。
"""

import logging
import time
from typing import Any, Dict, Optional

from flask import make_response, render_template, request
from flask.typing import ResponseReturnValue

from postman_api_tester.config import (
    UI_EXECUTION_DEFAULT_DELAY_MS,
    UI_EXECUTION_DEFAULT_TIMEOUT_MS,
    UI_EXECUTION_MAX_CONCURRENT,
)
from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.ui_case_store import UiCaseStore
from postman_api_tester.services.ui_execution_store import UiExecutionStore
from postman_api_tester.services.ui_recorder_inject import get_replayer_js

logger = logging.getLogger(__name__)

_case_store = UiCaseStore()
_execution_store = UiExecutionStore()

# 当前活跃任务计数（简易并发控制）
_active_jobs: Dict[str, Dict[str, Any]] = {}


def api_ui_testing_execute(case_id: str) -> ResponseReturnValue:
    """创建执行任务，返回 job_id 和 replay_url。"""
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "browser_replay")
    options = payload.get("options", {})

    if len(_active_jobs) >= UI_EXECUTION_MAX_CONCURRENT:
        logger.warning(
            "ui_execution_concurrent_limit",
            extra={
                "event": "ui.execution.concurrent_limit",
                "current_count": len(_active_jobs),
                "max_concurrent": UI_EXECUTION_MAX_CONCURRENT,
            },
        )
        return json_error("并发任务数已达上限", 429, "UIT_EXEC_006")

    case_data = _case_store.get_case(case_id)
    if not case_data:
        return json_error(f"用例不存在: {case_id}", 404, "UIT_EXEC_001")

    case_name = case_data.get("name", "")
    job_id = _execution_store.create_job(case_id, mode, case_name)

    if not options.get("delay_between_steps"):
        options["delay_between_steps"] = UI_EXECUTION_DEFAULT_DELAY_MS
    if not options.get("timeout"):
        options["timeout"] = UI_EXECUTION_DEFAULT_TIMEOUT_MS

    _active_jobs[job_id] = {
        "case_id": case_id,
        "case_data": case_data,
        "mode": mode,
        "options": options,
        "created_at": time.time(),
    }

    replay_url = f"/ui-testing/replay/{job_id}"

    logger.info(
        "ui_execution_created",
        extra={
            "event": "ui.execution.created",
            "job_id": job_id,
            "case_id": case_id,
            "mode": mode,
        },
    )

    return BaseHandler.json_response(
        {
            "job_id": job_id,
            "case_id": case_id,
            "mode": mode,
            "status": "ready",
            "replay_url": replay_url,
        },
        201,
        "Created",
    )


def api_ui_testing_execution_status(job_id: str) -> ResponseReturnValue:
    """查询执行状态（实时进度）。"""
    result = _execution_store.get_result(job_id)
    if not result:
        return json_error(f"执行任务不存在: {job_id}", 404, "UIT_EXEC_002")
    return BaseHandler.json_response(result)


def api_ui_testing_execution_report(job_id: str) -> ResponseReturnValue:
    """获取完整执行报告。"""
    result = _execution_store.get_result(job_id)
    if not result:
        return json_error(f"执行任务不存在: {job_id}", 404, "UIT_EXEC_003")
    return BaseHandler.json_response(result)


def api_ui_testing_executions_list() -> ResponseReturnValue:
    """执行历史列表。"""
    case_id = request.args.get("case_id", "").strip() or None
    limit = min(int(request.args.get("limit", 20)), 100)
    results = _execution_store.list_results(case_id=case_id, limit=limit)
    return BaseHandler.json_response(results)


def api_ui_testing_execution_cancel(job_id: str) -> ResponseReturnValue:
    """取消执行。"""
    result = _execution_store.get_result(job_id)
    if not result:
        return json_error(f"执行任务不存在: {job_id}", 404, "UIT_EXEC_004")

    if result.get("status") in ("passed", "failed", "cancelled"):
        return json_error(f"任务已结束: {result['status']}", 400, "UIT_EXEC_005")

    summary = {
        "steps_total": len(result.get("steps", [])),
        "steps_passed": result.get("steps_passed", 0),
        "steps_failed": result.get("steps_failed", 0),
    }
    _execution_store.finalize_job(job_id, "cancelled", summary)
    _active_jobs.pop(job_id, None)

    logger.info(
        "ui_execution_cancelled",
        extra={"event": "ui.execution.cancelled", "job_id": job_id},
    )
    return BaseHandler.json_response({"ok": True, "status": "cancelled"})


def api_ui_testing_execution_step_report(job_id: str) -> ResponseReturnValue:
    """前端回放引擎上报步骤结果。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_EXEC_007")

    step_result = payload.get("step_result", {})
    if not step_result:
        return json_error("缺少 step_result", 400, "UIT_EXEC_008")

    _execution_store.update_step(job_id, step_result)
    return BaseHandler.json_response({"ok": True})


def api_ui_testing_execution_finalize(job_id: str) -> ResponseReturnValue:
    """前端回放引擎上报执行完成。"""
    payload = request.get_json(silent=True) or {}
    status = payload.get("status", "passed")
    summary = payload.get("summary", {})

    _execution_store.finalize_job(job_id, status, summary)
    _active_jobs.pop(job_id, None)
    return BaseHandler.json_response({"ok": True})


def api_ui_testing_execution_init(job_id: str) -> ResponseReturnValue:
    """返回回放引擎初始化数据（steps + options）。"""
    job_data = _active_jobs.get(job_id)
    if not job_data:
        result = _execution_store.get_result(job_id)
        if not result:
            return json_error(f"执行任务不存在: {job_id}", 404, "UIT_EXEC_002")
        case_data = _case_store.get_case(result.get("case_id", ""))
        if not case_data:
            return json_error("用例数据不存在", 404, "UIT_EXEC_001")
        return BaseHandler.json_response({
            "steps": case_data.get("steps", []),
            "options": {
                "delay_between_steps": UI_EXECUTION_DEFAULT_DELAY_MS,
                "timeout": UI_EXECUTION_DEFAULT_TIMEOUT_MS,
            },
            "case_name": case_data.get("name", ""),
            "base_url": case_data.get("base_url", ""),
        })

    case_data = job_data["case_data"]
    return BaseHandler.json_response({
        "steps": case_data.get("steps", []),
        "options": job_data["options"],
        "case_name": case_data.get("name", ""),
        "base_url": case_data.get("base_url", ""),
    })


def ui_testing_replay_page(job_id: str) -> ResponseReturnValue:
    """回放页面渲染。"""
    resp = make_response(render_template("ui_testing_replay.html", job_id=job_id))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def api_ui_testing_replay_engine_js() -> ResponseReturnValue:
    """返回回放引擎 JavaScript 代码。"""
    origin = request.host_url.rstrip("/")
    js_code = get_replayer_js(origin)
    resp = make_response(js_code)
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    resp.headers["Cache-Control"] = "no-cache"
    return resp
