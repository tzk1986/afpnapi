"""UI 测试执行路由处理函数。

提供执行任务创建、状态查询、报告获取、执行历史和回放页面渲染。
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from flask import make_response, render_template, request, send_file
from flask.typing import ResponseReturnValue

from postman_api_tester.config import (
    UI_EXECUTION_DEFAULT_DELAY_MS,
    UI_EXECUTION_DEFAULT_TIMEOUT_MS,
    UI_EXECUTION_MAX_CONCURRENT,
    UI_HEADLESS_BROWSER,
)
from postman_api_tester.handlers.base_handler import BaseHandler, json_error
from postman_api_tester.services.ui_case_store import UiCaseStore
from postman_api_tester.services.ui_execution_manager import UiExecutionManager
from postman_api_tester.services.ui_execution_store import UiExecutionStore
from postman_api_tester.services.ui_headless_engine import is_playwright_available
from postman_api_tester.services.ui_recorder_inject import get_replayer_js
from postman_api_tester.services.ui_settings_store import UiSettingsStore

logger = logging.getLogger(__name__)

_case_store = UiCaseStore()
_execution_store = UiExecutionStore()
_execution_manager = UiExecutionManager(_execution_store)
_settings_store = UiSettingsStore()

# 当前活跃任务计数（浏览器回放模式，简易并发控制）
_active_jobs: Dict[str, Dict[str, Any]] = {}

# 僵尸任务超时时间（30 分钟）
_STALE_JOB_TIMEOUT_SECONDS = 30 * 60


def _cleanup_stale_jobs() -> None:
    """清理超时的僵尸任务。

    浏览器回放模式依赖前端调用 finalize 清理任务，
    如果用户关闭页面或回放崩溃，任务会永远留在内存中。
    此函数清理创建时间超过 30 分钟的任务。
    """
    now = time.time()
    stale_jobs = [
        job_id
        for job_id, info in _active_jobs.items()
        if now - info.get("created_at", 0) > _STALE_JOB_TIMEOUT_SECONDS
    ]
    for job_id in stale_jobs:
        _active_jobs.pop(job_id, None)
        logger.info(
            "ui_execution_stale_cleanup",
            extra={"event": "ui.execution.stale_cleanup", "job_id": job_id},
        )


def api_ui_testing_execute(case_id: str) -> ResponseReturnValue:
    """创建执行任务，返回 job_id。

    mode=browser_replay: 返回 replay_url（前端 iframe 回放）
    mode=headless: 启动后台线程执行，返回 status_url
    """
    payload = request.get_json(silent=True) or {}
    settings = _settings_store.get_settings()
    mode = payload.get("mode", settings.get("default_mode", "browser_replay"))
    options = payload.get("options", {})

    br_settings = settings.get("browser_replay", {})
    if not options.get("delay_between_steps"):
        options["delay_between_steps"] = br_settings.get(
            "delay_between_steps", UI_EXECUTION_DEFAULT_DELAY_MS
        )
    if not options.get("timeout"):
        options["timeout"] = br_settings.get(
            "timeout_ms", UI_EXECUTION_DEFAULT_TIMEOUT_MS
        )

    if mode == "headless":
        if not is_playwright_available():
            return json_error("Playwright 未安装，请运行: pip install playwright && playwright install chromium", 400, "UIT_EXEC_010")
        if not _execution_manager.can_start():
            return json_error("并发任务数已达上限", 429, "UIT_EXEC_006")

    # 清理僵尸任务
    _cleanup_stale_jobs()

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

    # 执行前清除代理 session cookie（仅当 clear_login 为 true 时）
    clear_login = options.get("clear_login", True)
    base_url = case_data.get("base_url", "")
    if base_url and clear_login:
        from postman_api_tester.services.ui_proxy_service import _proxy_session_store
        _proxy_session_store.clear_cookies_by_base_url(base_url)
        logger.info(
            "ui_execution_init_cookies_cleared",
            extra={
                "event": "ui.execution.init.cookies_cleared",
                "case_id": case_id,
                "base_url": base_url,
            },
        )

    case_name = case_data.get("name", "")
    steps = case_data.get("steps", [])
    job_id = _execution_store.create_job(case_id, mode, case_name, steps_total=len(steps))

    logger.info(
        "ui_execution_created",
        extra={
            "event": "ui.execution.created",
            "job_id": job_id,
            "case_id": case_id,
            "mode": mode,
        },
    )

    if mode == "headless":
        hl_settings = settings.get("headless", {})
        options["headless_browser"] = hl_settings.get("browser_type", UI_HEADLESS_BROWSER)
        options["viewport_width"] = hl_settings.get("viewport_width", 1280)
        options["viewport_height"] = hl_settings.get("viewport_height", 720)
        options["take_screenshots"] = hl_settings.get("take_screenshots", True)
        _execution_manager.start_headless(job_id, case_data, options, on_complete=_send_webhook)
        return BaseHandler.json_response(
            {
                "job_id": job_id,
                "case_id": case_id,
                "mode": mode,
                "status": "running",
                "status_url": f"/api/ui-testing/execution/{job_id}/status",
                "report_url": f"/ui-testing/execution/{job_id}/report",
            },
            201,
            "Created",
        )

    _active_jobs[job_id] = {
        "case_id": case_id,
        "case_data": case_data,
        "mode": mode,
        "options": options,
        "created_at": time.time(),
    }

    replay_url = f"/ui-testing/replay/{job_id}"

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

    mode = result.get("mode", "browser_replay")
    if mode == "headless":
        _execution_manager.cancel(job_id)
    else:
        _active_jobs.pop(job_id, None)

    summary = {
        "steps_total": len(result.get("steps", [])),
        "steps_passed": result.get("steps_passed", 0),
        "steps_failed": result.get("steps_failed", 0),
    }
    _execution_store.finalize_job(job_id, "cancelled", summary)

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

    result = _execution_store.get_result(job_id)
    if result:
        _send_webhook(result)

    return BaseHandler.json_response({"ok": True})


def api_ui_testing_execution_screenshot_post(job_id: str) -> ResponseReturnValue:
    """前端回放引擎上报失败步骤截图（HTML 快照）。"""
    payload = request.get_json(silent=True)
    if not payload:
        return BaseHandler.json_response({"ok": True})

    step_index = payload.get("step_index")
    html_content = payload.get("html", "")
    if step_index is None or not html_content:
        return BaseHandler.json_response({"ok": True})

    screenshot_dir = _execution_store.base_dir / f"exec_{job_id}" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / f"step_{step_index}_fail.html"

    try:
        screenshot_path.write_text(html_content, encoding="utf-8")
        logger.info(
            "ui_screenshot_saved",
            extra={"event": "ui.execution.screenshot_saved", "job_id": job_id, "step_index": step_index},
        )
    except Exception as e:
        logger.warning(f"Failed to save screenshot: {e}")

    return BaseHandler.json_response({"ok": True})


def _extract_network_requests(steps: list) -> list:
    """从 steps 中提取 api_call 步骤的网络请求数据，供回放引擎比对。"""
    network_requests = []
    for step in steps:
        if step.get("action") != "api_call":
            continue
        net_req = step.get("network_request")
        if not net_req:
            continue
        net_resp = step.get("network_response") or {}
        network_requests.append({
            "url": net_req.get("url", ""),
            "url_path": net_req.get("url_path", ""),
            "method": net_req.get("method", "GET"),
            "headers": net_req.get("headers", {}),
            "body": net_req.get("body", ""),
            "response_status": net_resp.get("status", 0),
            "response_body": net_resp.get("body", ""),
        })
    return network_requests


def api_ui_testing_execution_init(job_id: str) -> ResponseReturnValue:
    """返回回放引擎初始化数据（steps + options）。"""
    from postman_api_tester.services.ui_proxy_service import _proxy_session_store

    job_data = _active_jobs.get(job_id)
    if not job_data:
        result = _execution_store.get_result(job_id)
        if not result:
            return json_error(f"执行任务不存在: {job_id}", 404, "UIT_EXEC_002")
        case_data = _case_store.get_case(result.get("case_id", ""))
        if not case_data:
            return json_error("用例数据不存在", 404, "UIT_EXEC_001")
        steps = case_data.get("steps", [])
        base_url = case_data.get("base_url", "")
        if base_url:
            cleared = _proxy_session_store.clear_cookies_by_base_url(base_url)
            logger.info(
                "ui_execution_init_cookies_cleared",
                extra={
                    "event": "ui.execution.init.cookies_cleared",
                    "job_id": job_id,
                    "base_url": base_url,
                    "cleared": cleared,
                },
            )
        resp = make_response(BaseHandler.json_response({
            "steps": [s for s in steps if s.get("action") != "api_call"],
            "options": {
                "delay_between_steps": UI_EXECUTION_DEFAULT_DELAY_MS,
                "timeout": UI_EXECUTION_DEFAULT_TIMEOUT_MS,
            },
            "case_name": case_data.get("name", ""),
            "base_url": base_url,
            "network_requests": _extract_network_requests(steps),
        }))
        # 清除浏览器旧 session cookie，确保 iframe 加载时创建新 session
        resp.set_cookie("_proxy_session", "", expires=0, path="/")
        return resp

    case_data = job_data["case_data"]
    options = job_data.get("options", {})
    clear_login = options.get("clear_login", True)
    steps = case_data.get("steps", [])
    base_url = case_data.get("base_url", "")
    if base_url and clear_login:
        cleared = _proxy_session_store.clear_cookies_by_base_url(base_url)
        logger.info(
            "ui_execution_init_cookies_cleared",
            extra={
                "event": "ui.execution.init.cookies_cleared",
                "job_id": job_id,
                "base_url": base_url,
                "cleared": cleared,
            },
        )
    resp = make_response(BaseHandler.json_response({
        "steps": [s for s in steps if s.get("action") != "api_call"],
        "options": options,
        "case_name": case_data.get("name", ""),
        "base_url": base_url,
        "network_requests": _extract_network_requests(steps),
    }))
    if clear_login:
        resp.set_cookie("_proxy_session", "", expires=0, path="/")
    return resp


def ui_testing_replay_page(job_id: str) -> ResponseReturnValue:
    """回放页面渲染。"""
    resp = make_response(render_template("ui_testing_replay.html", job_id=job_id))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def ui_testing_report_page(job_id: str) -> ResponseReturnValue:
    """渲染 HTML 执行报告页面。"""
    result = _execution_store.get_result(job_id)
    if not result:
        return render_template(
            "ui_testing_report.html",
            job_id=job_id,
            case_name="执行任务不存在",
            case_id="",
            status="cancelled",
            status_label="不存在",
            mode_label="",
            started_at="",
            ended_at="",
            steps_total=0,
            steps_passed=0,
            steps_failed=0,
            duration_s="0",
            steps=[],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    status = result.get("status", "running")
    status_labels = {"passed": "通过", "failed": "失败", "running": "执行中", "cancelled": "已取消", "ready": "就绪"}
    mode_labels = {"browser_replay": "浏览器回放", "headless": "无头浏览器"}

    raw_steps = result.get("steps", [])
    steps = []
    for i, s in enumerate(raw_steps):
        selector = s.get("selector", "")
        if isinstance(selector, dict):
            selector_display = selector.get("primary", "") or selector.get("fallback_css", "") or selector.get("fallback_xpath", "")
        else:
            selector_display = str(selector) if selector else ""

        value = s.get("value", "")
        value_display = str(value)[:60] if value else ""

        step_status = s.get("status", "skipped")
        step_status_labels = {"passed": "通过", "failed": "失败", "skipped": "跳过", "error": "错误"}

        duration_ms = s.get("duration_ms", 0)
        steps.append({
            "status": step_status,
            "action": s.get("action", "unknown"),
            "selector_display": selector_display,
            "value_display": value_display,
            "status_label": step_status_labels.get(step_status, step_status),
            "duration_s": f"{duration_ms / 1000:.2f}",
            "error": s.get("error", ""),
        })

    total_duration_ms = result.get("total_duration_ms", 0)

    resp = make_response(render_template(
        "ui_testing_report.html",
        job_id=job_id,
        case_name=result.get("case_name", ""),
        case_id=result.get("case_id", ""),
        status=status,
        status_label=status_labels.get(status, status),
        mode_label=mode_labels.get(result.get("mode", ""), result.get("mode", "")),
        started_at=result.get("started_at", ""),
        ended_at=result.get("ended_at", "") or "",
        steps_total=result.get("steps_total", len(raw_steps)),
        steps_passed=result.get("steps_passed", 0),
        steps_failed=result.get("steps_failed", 0),
        duration_s=f"{total_duration_ms / 1000:.2f}",
        steps=steps,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ))
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


def api_ui_testing_replay_log() -> ResponseReturnValue:
    """接收回放引擎日志并写入后端日志系统。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_REPLAY_LOG_001")

    # 诊断：记录所有 replay-log 请求体
    event = payload.get("event", "")
    if event.startswith("early_"):
        logger.info(f"replay-log DIAGNOSTIC: {payload}", extra={"event": f"ui.replay.{event}", "detail": payload})

    job_id = payload.get("job_id", "")
    step_index = payload.get("step_index", -1)
    event = payload.get("event", "")
    message = payload.get("message", "")
    detail = payload.get("detail", {})

    log_level = logging.DEBUG
    if payload.get("level") == "error":
        log_level = logging.ERROR
    elif payload.get("level") == "warn":
        log_level = logging.WARNING

    logger.log(
        log_level,
        f"replay[{job_id}] step={step_index} {event}: {message}",
        extra={
            "event": f"ui.replay.{event}",
            "job_id": job_id,
            "step_index": step_index,
            "detail": detail,
        },
    )
    return BaseHandler.json_response({"ok": True})


# ---- Phase 3: 设置管理 ----


def api_ui_testing_settings_get() -> ResponseReturnValue:
    """获取当前 UI 测试设置。"""
    return BaseHandler.json_response(_settings_store.get_settings())


def api_ui_testing_settings_update() -> ResponseReturnValue:
    """更新 UI 测试设置。"""
    payload = request.get_json(silent=True)
    if not payload:
        return json_error("无效的 JSON 数据", 400, "UIT_SETTINGS_001")
    updated = _settings_store.update_settings(payload)
    logger.info(
        "ui_settings_updated",
        extra={
            "event": "ui.settings.updated",
            "changed_keys": list(payload.keys()),
        },
    )
    return BaseHandler.json_response(updated)


def api_ui_testing_settings_reset() -> ResponseReturnValue:
    """恢复默认设置。"""
    settings = _settings_store.reset_settings()
    logger.info("ui_settings_reset", extra={"event": "ui.settings.reset"})
    return BaseHandler.json_response(settings)


def api_ui_testing_cleanup() -> ResponseReturnValue:
    """清理过期执行记录。"""
    settings = _settings_store.get_settings()
    retention_days = settings.get("retention_days", 30)
    deleted = _execution_store.cleanup_expired(retention_days)
    return BaseHandler.json_response({"deleted": deleted, "retention_days": retention_days})


def ui_testing_settings_page() -> ResponseReturnValue:
    """设置页面渲染。"""
    resp = make_response(render_template("ui_testing_settings.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def api_ui_testing_playwright_status() -> ResponseReturnValue:
    """检查 Playwright 安装状态。"""
    return BaseHandler.json_response({
        "available": is_playwright_available(),
        "hint": "已安装" if is_playwright_available() else "未安装，请运行: pip install playwright && playwright install chromium",
    })


def api_ui_testing_reports_list() -> ResponseReturnValue:
    """UI 报告列表（支持 status 筛选 + 分页）。"""
    status_filter = request.args.get("status", "").strip() or None
    case_id_filter = request.args.get("case_id", "").strip() or None
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(int(request.args.get("page_size", 20)), 999)

    total = _execution_store.count_results(case_id=case_id_filter, status=status_filter)
    offset = (page - 1) * page_size
    results = _execution_store.list_results(
        case_id=case_id_filter,
        status=status_filter,
        limit=page_size,
        offset=offset,
    )

    return BaseHandler.json_response({
        "items": results,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    })


def api_ui_testing_report_delete(job_id: str) -> ResponseReturnValue:
    """删除单个 UI 测试报告。"""
    result = _execution_store.get_result(job_id)
    if not result:
        return json_error(f"报告不存在: {job_id}", 404, "UIT_REPORT_001")

    if _execution_store.delete_job(job_id):
        logger.info(
            "ui_report_deleted",
            extra={"event": "ui.report.deleted", "job_id": job_id},
        )
        return BaseHandler.json_response({"ok": True, "job_id": job_id})
    return json_error("删除失败", 500, "UIT_REPORT_002")


def ui_testing_reports_page() -> ResponseReturnValue:
    """渲染 UI 测试报告列表页面。"""
    resp = make_response(render_template("ui_testing_reports.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def api_ui_testing_execution_screenshot(job_id: str, step_index: int) -> ResponseReturnValue:
    """返回失败步骤截图。"""
    screenshot_path = _execution_store.base_dir / f"exec_{job_id}" / "screenshots" / f"step_{step_index}_fail.png"
    if not screenshot_path.is_file():
        return json_error("截图不存在", 404, "UIT_SCREENSHOT_001")
    return send_file(str(screenshot_path), mimetype="image/png")


def _send_webhook(result: Dict[str, Any]) -> None:
    """执行完成后发送 Webhook 通知。"""
    import requests as req

    settings = _settings_store.get_settings()
    webhook_url = settings.get("webhook_url", "").strip()
    if not webhook_url:
        return

    status = result.get("status", "")
    on_complete = settings.get("webhook_on_complete", True)
    on_failure = settings.get("webhook_on_failure", True)

    if status == "failed" and not on_failure:
        return
    if status != "failed" and not on_complete:
        return

    payload = {
        "event": "ui.execution.completed",
        "job_id": result.get("job_id", ""),
        "case_id": result.get("case_id", ""),
        "case_name": result.get("case_name", ""),
        "status": status,
        "mode": result.get("mode", ""),
        "duration_ms": result.get("total_duration_ms", 0),
        "steps_total": result.get("steps_total", 0),
        "steps_passed": result.get("steps_passed", 0),
        "steps_failed": result.get("steps_failed", 0),
        "report_url": f"/ui-testing/execution/{result.get('job_id', '')}/report",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        resp = req.post(webhook_url, json=payload, timeout=10)
        logger.info(
            "ui_settings_webhook_sent",
            extra={
                "event": "ui.settings.webhook_sent",
                "webhook_url": webhook_url,
                "status_code": resp.status_code,
            },
        )
    except Exception as e:
        logger.warning(
            "ui_settings_webhook_failed",
            extra={
                "event": "ui.settings.webhook_failed",
                "webhook_url": webhook_url,
                "error": str(e),
            },
        )
