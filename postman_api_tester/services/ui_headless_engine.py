"""UI 测试无头浏览器执行引擎。

使用 Playwright 在后台线程中执行 UI 测试步骤。
需要安装 playwright: pip install playwright && playwright install chromium
"""

import contextlib
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

logger = logging.getLogger(__name__)

# 无头执行日志目录
_HEADLESS_LOG_DIR = Path("logs/headless")
_HEADLESS_LOG_RETENTION_DAYS = 10

# 超时常量（毫秒）
DEFAULT_TIMEOUT_MS = 30000
NAVIGATION_TIMEOUT_MS = 15000
PAGE_LOAD_TIMEOUT_MS = 10000
QUICK_LOAD_TIMEOUT_MS = 5000
DOM_CONTENT_TIMEOUT_MS = 3000


def _cleanup_old_logs() -> None:
    """清理超过保留天数的无头执行日志。"""
    if not _HEADLESS_LOG_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=_HEADLESS_LOG_RETENTION_DAYS)
    cleaned = 0
    for f in _HEADLESS_LOG_DIR.glob("exec_*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                cleaned += 1
        except OSError:
            pass
    if cleaned > 0:
        logger.info("headless_log_cleanup: removed %d old log files", cleaned)


def _log_request(job_id: str, step_index: int, request_data: Dict[str, Any]) -> None:
    """将无头执行中的网络请求追加到日志文件。"""
    _HEADLESS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _HEADLESS_LOG_DIR / f"exec_{job_id}.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "step_index": step_index,
        **request_data,
    }
    try:
        with Path(log_file).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        sync_playwright,
    )

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


def is_playwright_available() -> bool:
    """检查 Playwright 是否已安装。"""
    return _HAS_PLAYWRIGHT


class HeadlessExecutionError(Exception):
    """无头执行异常。"""


class UiHeadlessEngine:
    """Playwright 无头执行引擎。"""

    def __init__(
        self,
        browser_type: str = "chromium",
        screenshots_dir: Optional[Path] = None,
    ) -> None:
        if not _HAS_PLAYWRIGHT:
            raise HeadlessExecutionError(
                "Playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )
        self._browser_type = browser_type
        self._screenshots_dir = screenshots_dir

    def execute(
        self,
        steps: List[Dict[str, Any]],
        base_url: str,
        options: Dict[str, Any],
        job_id: str,
        cancel_flag: Optional[Any] = None,
        on_step_complete: Optional[Any] = None,
        on_browser_ready: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """执行所有步骤，返回摘要。

        Args:
            steps: 步骤列表
            base_url: 基础 URL（导航步骤的相对路径会拼接此值）
            options: 执行选项（timeout, delay_between_steps）
            job_id: 任务 ID（用于截图命名）
            cancel_flag: threading.Event，被 set 时中止执行
            on_step_complete: 回调 (step_index, step_result_dict) -> None
            on_browser_ready: 浏览器启动完成回调 () -> None
        """
        timeout_ms = options.get("timeout", DEFAULT_TIMEOUT_MS)
        delay_ms = options.get("delay_between_steps", 200)
        viewport_w = options.get("viewport_width", 1280)
        viewport_h = options.get("viewport_height", 720)

        pw = sync_playwright().start()
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        steps_passed = 0
        steps_failed = 0
        _step_results: List[Dict[str, Any]] = []

        _cleanup_old_logs()

        current_step_index = [-1]  # 用 list 以便在闭包中修改

        def _on_request(request: Any) -> None:
            """拦截并记录无头执行中的网络请求。"""
            url = request.url
            # 只记录 API 请求，跳过静态资源
            if "/api/" not in url:
                return
            _log_request(
                job_id,
                current_step_index[0],
                {
                    "event": "request",
                    "method": request.method,
                    "url": url,
                    "headers": dict(request.headers),
                },
            )

        def _on_response(response: Any) -> None:
            """记录响应状态。"""
            url = response.url
            if "/api/" not in url:
                return
            _log_request(
                job_id,
                current_step_index[0],
                {
                    "event": "response",
                    "method": response.request.method,
                    "url": url,
                    "status": response.status,
                    "status_text": response.status_text,
                },
            )

        try:
            launcher = getattr(pw, self._browser_type, pw.chromium)
            browser = launcher.launch(headless=True)
            context = browser.new_context(
                viewport={"width": viewport_w, "height": viewport_h}
            )
            page = context.new_page()
            assert page is not None
            page.set_default_timeout(timeout_ms)

            # 监听网络请求
            page.on("request", _on_request)
            page.on("response", _on_response)

            # 自动导航到 base_url（回放模式下 iframe 已指向 base_url，无头模式需要显式跳转）
            if base_url:
                page.goto(base_url, wait_until="load")

            # 浏览器启动完成，开始计时
            start_time = time.time()
            if on_browser_ready is not None:
                on_browser_ready()

            # 监听新页面/弹窗（用于 new_tab 处理）
            popup_page: Any = None
            captured_new_tab_url: str = ""

            def _on_popup(p: Any) -> None:
                nonlocal popup_page
                # 忽略无效 URL 的 popup（如 null、about:blank）
                if p.url and p.url != "about:blank" and "/null" not in p.url:
                    popup_page = p
                    logger.info(
                        "headless_popup_detected",
                        extra={"event": "headless.popup", "url": p.url},
                    )

            context.on("page", _on_popup)

            _pending_new_tab_url = ""
            _pending_new_tab_index = -1
            _redirect_detected = ""
            _navigate_listener_active = False
            _terminated = False

            def _on_navigate(frame: Any) -> None:
                """framenavigated 监听：实时检测 SPA 重定向到登录/错误页。"""
                nonlocal _redirect_detected
                if _redirect_detected:
                    return
                if frame != cast(Any, page).main_frame:
                    return
                new_url = frame.url
                target = _pending_new_tab_url
                if not target or not new_url:
                    return
                from urllib.parse import urlparse as _up

                cur = _up(new_url)
                tgt = _up(target)
                # 跨域检测
                if cur.hostname and tgt.hostname and cur.hostname != tgt.hostname:
                    _redirect_detected = f"页面被重定向到其他域名: 当前={new_url[:120]}, 期望={target[:120]}"
                    return
                # 重定向模式检测（仅同域内）
                cur_path = cur.path.lower()
                tgt_path = tgt.path.lower()
                for pattern in ["/login", "/error", "/404", "/502", "/403", "/500"]:
                    if pattern in cur_path and pattern not in tgt_path:
                        _redirect_detected = f"页面被重定向到 {pattern}（会话可能已过期）: {new_url[:120]}"
                        return

            for i, step in enumerate(steps):
                if cancel_flag is not None and cancel_flag.is_set():
                    break

                step_start = time.time()
                action = step.get("action", "").lower()
                url_before_step = page.url

                # new_tab：导航到新页面（与浏览器回放引擎行为一致）
                if action == "new_tab":
                    # 清理上一个 new_tab 的 framenavigated 监听（如果有）
                    if _navigate_listener_active:
                        page.remove_listener("framenavigated", _on_navigate)
                        _navigate_listener_active = False
                    _pending_new_tab_url = ""
                    _redirect_detected = ""
                    navigation_error = ""
                    # 诊断信息收集
                    _diag: Dict[str, Any] = {
                        "stage": "new_tab_start",
                        "current_url": page.url[:200],
                    }
                    try:
                        diag_cookies = page.context.cookies()
                        _diag["cookie_count"] = len(diag_cookies)
                        _diag["cookie_names"] = [c["name"] for c in diag_cookies]
                        _diag["session_cookies"] = [
                            {
                                "name": c["name"],
                                "domain": c["domain"],
                                "path": c.get("path", ""),
                            }
                            for c in diag_cookies
                            if any(
                                kw in c["name"].lower()
                                for kw in [
                                    "session",
                                    "token",
                                    "auth",
                                    "sso",
                                    "jsessionid",
                                ]
                            )
                        ]
                    except Exception as e:
                        _diag["cookie_error"] = str(e)
                    # 检查 localStorage 和 sessionStorage 中的 token
                    try:
                        storage_info = page.evaluate("""() => {
                            var keys = [];
                            try { for (var i = 0; i < localStorage.length; i++) keys.push('L:' + localStorage.key(i)); } catch(e) {}
                            try { for (var i = 0; i < sessionStorage.length; i++) keys.push('S:' + sessionStorage.key(i)); } catch(e) {}
                            var espUser = '';
                            try { espUser = localStorage.getItem('esp-web:user') || ''; } catch(e) {}
                            return {
                                localStorage_keys: keys.filter(function(k) { return k.indexOf('L:') === 0; }),
                                sessionStorage_keys: keys.filter(function(k) { return k.indexOf('S:') === 0; }),
                                token_in_localStorage: localStorage.getItem('token') || localStorage.getItem('access_token') || localStorage.getItem('auth_token') || '',
                                token_in_sessionStorage: sessionStorage.getItem('token') || sessionStorage.getItem('access_token') || sessionStorage.getItem('auth_token') || '',
                                esp_web_user: espUser.substring(0, 500),
                            };
                        }""")
                        _diag["storage"] = storage_info
                    except Exception as e:
                        _diag["storage_error"] = str(e)
                    # 优先级：弹窗页面 > 步骤数据解析
                    if popup_page is not None:
                        try:
                            popup_page.wait_for_load_state("load", timeout=PAGE_LOAD_TIMEOUT_MS)
                            popup_page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
                            actual_url = popup_page.url
                            # 验证弹窗 URL 是否到达预期页面
                            resolved_url = self._resolve_new_tab_url(
                                step, steps, i, base_url
                            )
                            if resolved_url and not self._urls_match(
                                actual_url, resolved_url
                            ):
                                navigation_error = f"弹窗页面 URL 不匹配: 当前={actual_url[:120]}, 目标={resolved_url[:120]}"
                            else:
                                page.close()
                                page = popup_page
                                popup_page = None
                        except Exception as e:
                            logger.warning("headless_popup_error: %s", e)
                            actual_url = ""
                            navigation_error = f"弹窗页面加载失败: {e}"
                    elif captured_new_tab_url:
                        actual_url = captured_new_tab_url
                        captured_new_tab_url = ""
                        _diag["branch"] = "captured_url"
                        _diag["captured_url"] = actual_url[:200]
                        try:
                            _diag["goto_start"] = page.url[:200]
                            page.goto(actual_url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS)
                            _diag["after_load"] = page.url[:200]
                            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
                            _diag["after_idle1"] = page.url[:200]
                            if not self._urls_match(page.url, actual_url):
                                navigation_error = f"页面跳转未到达目标 URL: 当前={page.url[:120]}, 目标={actual_url[:120]}"
                            else:
                                time.sleep(0.5)
                                try:
                                    page.wait_for_load_state(
                                        "networkidle", timeout=QUICK_LOAD_TIMEOUT_MS
                                    )
                                except Exception:
                                    pass
                                _diag["after_idle2"] = page.url[:200]
                                if not self._urls_match(page.url, actual_url):
                                    navigation_error = (
                                        f"页面认证后重定向（会话可能已过期）: "
                                        f"当前={page.url[:120]}, 目标={actual_url[:120]}"
                                    )
                        except Exception as e:
                            navigation_error = f"页面导航失败: {e}"
                    else:
                        actual_url = self._resolve_new_tab_url(step, steps, i, base_url)
                        _diag["branch"] = "resolved_url"
                        _diag["resolved_url"] = actual_url[:200] if actual_url else ""
                        if actual_url:
                            try:
                                # 读取 9101 页面的 SSO token
                                esp_web_user = page.evaluate(
                                    "localStorage.getItem('esp-web:user') || ''"
                                )
                                _diag["esp_web_user_found"] = bool(esp_web_user)

                                # 用 window.open 触发弹窗，模拟成功路径的 popup 机制
                                _diag["popup_trigger"] = "window_open"
                                page.evaluate(f"window.open('{actual_url}', '_blank')")
                                time.sleep(0.5)
                                # 等待 _on_popup 捕获弹窗
                                for _ in range(20):
                                    if popup_page is not None:
                                        break
                                    time.sleep(0.2)
                                if popup_page is not None:
                                    try:
                                        popup_page.wait_for_load_state(
                                            "load", timeout=PAGE_LOAD_TIMEOUT_MS
                                        )
                                        popup_page.wait_for_load_state(
                                            "networkidle", timeout=PAGE_LOAD_TIMEOUT_MS
                                        )
                                        actual_url = popup_page.url
                                        _diag["popup_captured"] = True
                                        _diag["popup_url"] = actual_url[:200]
                                        page.close()
                                        page = popup_page
                                        popup_page = None
                                        # 注入 SSO token 到 9301 页面
                                        if esp_web_user:
                                            page.evaluate(
                                                f"localStorage.setItem('esp-web:user', {json.dumps(esp_web_user)})"
                                            )
                                            page.reload(wait_until="load")
                                            page.wait_for_load_state(
                                                "networkidle", timeout=PAGE_LOAD_TIMEOUT_MS
                                            )
                                            _diag["token_injected"] = True
                                    except Exception as e:
                                        logger.warning("headless_popup_error: %s", e)
                                        navigation_error = f"弹窗页面加载失败: {e}"
                                else:
                                    # 降级：window.open 未触发弹窗，page.goto + token 注入
                                    _diag["popup_captured"] = False
                                    _diag["goto_start"] = page.url[:200]
                                    page.goto(
                                        actual_url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS
                                    )
                                    _diag["after_load"] = page.url[:200]
                                    # 注入 SSO token 到 9301 的 localStorage
                                    if esp_web_user:
                                        page.evaluate(
                                            f"localStorage.setItem('esp-web:user', {json.dumps(esp_web_user)})"
                                        )
                                        _diag["token_injected"] = True
                                        page.reload(wait_until="load")
                                        _diag["after_token_inject"] = page.url[:200]
                                    page.wait_for_load_state(
                                        "networkidle", timeout=PAGE_LOAD_TIMEOUT_MS
                                    )
                                    _diag["after_idle1"] = page.url[:200]
                                    if not self._urls_match(page.url, actual_url):
                                        navigation_error = (
                                            f"页面跳转未到达目标 URL: "
                                            f"当前={page.url[:120]}, 目标={actual_url[:120]}"
                                        )
                                    else:
                                        time.sleep(0.5)
                                        try:
                                            page.wait_for_load_state(
                                                "networkidle", timeout=QUICK_LOAD_TIMEOUT_MS
                                            )
                                        except Exception:
                                            pass
                                        _diag["after_idle2"] = page.url[:200]
                                        if not self._urls_match(page.url, actual_url):
                                            navigation_error = (
                                                f"页面认证后重定向（会话可能已过期）: "
                                                f"当前={page.url[:120]}, 目标={actual_url[:120]}"
                                            )
                            except Exception as e:
                                navigation_error = f"页面导航失败: {e}"
                        else:
                            navigation_error = "无法解析 new_tab 导航 URL"

                    new_tab_passed = bool(actual_url) and not navigation_error
                    _diag["navigation_error"] = navigation_error
                    step_result = {
                        "action": "new_tab",
                        "selector": {},
                        "value": actual_url,
                        "status": "passed" if new_tab_passed else "failed",
                        "error": navigation_error if navigation_error else "",
                        "_diag": _diag,
                    }
                    # new_tab 通过后，记录目标 URL 供下一步校验，并注册 framenavigated 实时监听
                    if new_tab_passed and actual_url:
                        _pending_new_tab_url = actual_url
                        _pending_new_tab_index = i
                        _redirect_detected = ""
                        if not _navigate_listener_active:
                            page.on("framenavigated", _on_navigate)
                            _navigate_listener_active = True
                        # 注入 SPA history API 拦截脚本，检测 pushState/replaceState 重定向
                        try:
                            page.evaluate("""() => {
                                if (window.__headless_spa_hooked) return;
                                window.__headless_spa_hooked = true;
                                window.__headless_redirect_url = null;
                                const _check = () => {
                                    const p = window.location.pathname.toLowerCase();
                                    const patterns = ['/login', '/error', '/404', '/502', '/403', '/500'];
                                    for (let i = 0; i < patterns.length; i++) {
                                        if (p.includes(patterns[i])) {
                                            window.__headless_redirect_url = window.location.href;
                                            return;
                                        }
                                    }
                                };
                                _check();
                                const _origPush = history.pushState;
                                history.pushState = function() {
                                    _origPush.apply(this, arguments);
                                    setTimeout(_check, 50);
                                };
                                const _origReplace = history.replaceState;
                                history.replaceState = function() {
                                    _origReplace.apply(this, arguments);
                                    setTimeout(_check, 50);
                                };
                                window.addEventListener('popstate', () => setTimeout(_check, 50));
                            }""")
                        except Exception:
                            pass
                elif action == "switch_tab":
                    # switch_tab：切换到另一个标签页（方案A：复用当前 page，导航到新 URL）
                    switch_url = (
                        step.get("page_url", "")
                        or step.get("tab_url", "")
                        or step.get("value", "")
                    )
                    logger.info(
                        "headless_switch_tab",
                        extra={
                            "event": "headless.switch_tab",
                            "url": switch_url[:200] if switch_url else "",
                            "tab_id": step.get("tab_id", ""),
                            "page_title": step.get("page_title", ""),
                        },
                    )
                    navigation_error = ""
                    actual_url = ""
                    if switch_url:
                        try:
                            page.goto(switch_url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS)
                            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
                            actual_url = page.url
                            if not self._urls_match(page.url, switch_url):
                                navigation_error = (
                                    f"switch_tab 页面未到达目标 URL: "
                                    f"当前={page.url[:120]}, 目标={switch_url[:120]}"
                                )
                            else:
                                time.sleep(0.5)
                                try:
                                    page.wait_for_load_state(
                                        "networkidle", timeout=QUICK_LOAD_TIMEOUT_MS
                                    )
                                except Exception:
                                    pass
                        except Exception as e:
                            navigation_error = f"switch_tab 页面导航失败: {e}"
                    else:
                        navigation_error = "switch_tab 无可用 URL"

                    switch_passed = bool(actual_url) and not navigation_error
                    step_result = {
                        "action": "switch_tab",
                        "selector": {},
                        "value": actual_url or switch_url,
                        "status": "passed" if switch_passed else "failed",
                        "error": navigation_error if navigation_error else "",
                    }
                else:
                    # new_tab 下一步 pre-check（framenavigated + SPA history hook + 当前 URL 对比）
                    if _pending_new_tab_url:
                        # 1. 检查 SPA history hook 是否捕获到重定向
                        spa_redirect = ""
                        try:
                            spa_redirect = page.evaluate(
                                "() => window.__headless_redirect_url || ''"
                            )
                        except Exception:
                            pass
                        # 2. 检查 URL 是否已变更（步骤尚未执行，任何 URL 变更都是重定向）
                        url_mismatch = ""
                        if not self._urls_match(page.url, _pending_new_tab_url):
                            url_mismatch = f"页面 URL 已变更: 当前={page.url[:120]}, 期望={_pending_new_tab_url[:120]}"
                        # 3. 组合检测结果
                        redirect_error = (
                            url_mismatch
                            or (
                                f"SPA 检测到页面重定向: {spa_redirect[:120]}"
                                if spa_redirect
                                else ""
                            )
                            or _redirect_detected
                            or self._check_page_redirect(page, _pending_new_tab_url)
                        )
                        if redirect_error:
                            # 清理 framenavigated 监听
                            if _navigate_listener_active:
                                page.remove_listener("framenavigated", _on_navigate)
                                _navigate_listener_active = False
                            _pending_new_tab_url = ""
                            _terminated = True
                            # 回写 new_tab 步骤为失败
                            if (
                                _pending_new_tab_index >= 0
                                and _pending_new_tab_index < len(_step_results)
                            ):
                                _step_results[_pending_new_tab_index]["status"] = (
                                    "failed"
                                )
                                _step_results[_pending_new_tab_index]["error"] = (
                                    redirect_error
                                )
                                steps_passed -= 1
                                steps_failed += 1
                            # 当前步骤标记为失败并终止
                            step_result = {
                                "action": action,
                                "selector": self._selector_to_dict(
                                    step.get("selector", "")
                                ),
                                "value": step.get("value", ""),
                                "status": "failed",
                                "error": f"new_tab 页面验证失败: {redirect_error}",
                            }
                            step_result["index"] = i
                            step_result["duration_ms"] = 0
                            steps_failed += 1
                            _step_results.append(step_result)
                            break

                    # 如果下一步是 new_tab，当前 click 前注入 window.open 拦截
                    next_is_new_tab = (
                        i + 1 < len(steps)
                        and steps[i + 1].get("action", "").lower() == "new_tab"
                    )
                    if action == "click" and next_is_new_tab:
                        url_before = page.url
                        popup_page = None
                        _pre_newtab_diag: Dict[str, Any] = {
                            "url_before_click": url_before[:200],
                        }
                        # 执行 click（不等待 popup，让 new_tab 步骤用 fallback URL 导航）
                        step_result = self._execute_step(
                            page, step, base_url, timeout_ms
                        )
                        # 短暂等待 popup 触发（_on_popup 异步回调）
                        time.sleep(0.5)
                        # 检测页面 URL 是否已跳转到新系统
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=DOM_CONTENT_TIMEOUT_MS)
                        except Exception:
                            pass
                        url_after = page.url
                        different_origin = self._is_different_origin(
                            url_before, url_after
                        )
                        _pre_newtab_diag["url_after_click"] = url_after[:200]
                        _pre_newtab_diag["different_origin"] = different_origin
                        _pre_newtab_diag["captured"] = (
                            url_after != url_before and different_origin
                        )
                        step_result["_pre_newtab_diag"] = _pre_newtab_diag
                        if url_after != url_before and different_origin:
                            captured_new_tab_url = url_after
                            logger.info(
                                "headless_navigation_captured",
                                extra={
                                    "event": "headless.navigation.captured",
                                    "url_before": url_before[:80],
                                    "url_after": url_after[:120],
                                },
                            )
                    else:
                        # new_tab 后第一步：使用 URL 监控执行，实时检测重定向
                        if _pending_new_tab_url:
                            step_result = self._execute_step_monitored(
                                page, step, base_url, timeout_ms, _pending_new_tab_url
                            )
                        else:
                            step_result = self._execute_step(
                                page, step, base_url, timeout_ms
                            )
                step_duration_ms = int((time.time() - step_start) * 1000)

                step_result["index"] = i
                step_result["duration_ms"] = step_duration_ms

                if step_result["status"] == "passed":
                    steps_passed += 1
                else:
                    steps_failed += 1
                    self._take_screenshot(page, job_id, i)

                # 步骤勾选了截图，无论通过/失败都截图
                if step.get("screenshot"):
                    self._take_screenshot(page, job_id, i, suffix="")
                    step_result["screenshot"] = True

                if on_step_complete is not None:
                    on_step_complete(i, step_result)

                _step_results.append(step_result)

                # new_tab 下一步 post-check：步骤执行后再次确认页面未被重定向
                # （SPA 可能在步骤执行期间重定向到登录/错误页）
                # 注意：仅对非 new_tab 步骤执行，否则 new_tab 自身刚加载完页面会误通过
                if _pending_new_tab_url and action != "new_tab":
                    # 检查 SPA history hook 是否捕获到重定向
                    spa_redirect = ""
                    try:
                        spa_redirect = page.evaluate(
                            "() => window.__headless_redirect_url || ''"
                        )
                    except Exception:
                        pass
                    post_error = (
                        (
                            f"SPA 检测到页面重定向: {spa_redirect[:120]}"
                            if spa_redirect
                            else ""
                        )
                        or _redirect_detected
                        or self._check_page_redirect(page, _pending_new_tab_url)
                    )
                    # 如果步骤失败且 URL 已变更，可能是重定向到首页等非标准错误页
                    if not post_error and step_result.get("status") != "passed":
                        if not self._urls_match(page.url, _pending_new_tab_url):
                            post_error = (
                                f"页面 URL 已变更（步骤失败）: 当前={page.url[:120]}, "
                                f"期望={_pending_new_tab_url[:120]}"
                            )
                    if _navigate_listener_active:
                        page.remove_listener("framenavigated", _on_navigate)
                        _navigate_listener_active = False
                    _pending_new_tab_url = ""
                    if post_error:
                        _terminated = True
                        # 回写 new_tab 步骤为失败
                        if _pending_new_tab_index >= 0 and _pending_new_tab_index < len(
                            _step_results
                        ):
                            if (
                                _step_results[_pending_new_tab_index]["status"]
                                == "passed"
                            ):
                                _step_results[_pending_new_tab_index]["status"] = (
                                    "failed"
                                )
                                _step_results[_pending_new_tab_index]["error"] = (
                                    post_error
                                )
                                steps_passed -= 1
                                steps_failed += 1
                        # 如果当前步骤通过了，也标记为失败
                        if step_result["status"] == "passed":
                            step_result["status"] = "failed"
                            step_result["error"] = f"new_tab 页面验证失败: {post_error}"
                            steps_passed -= 1
                            steps_failed += 1
                        break

                # new_tab 导航失败则终止测试（后续步骤依赖新页面）
                if action == "new_tab" and step_result["status"] == "failed":
                    break

                # 登录后等待页面跳转完成，确保 home 页面 JS 初始化完毕
                # （否则下一步 click 可能不触发 popup，导致 new_tab 丢失 SSO 上下文）
                if action == "click" and step_result["status"] == "passed":
                    sel = step.get("selector", "")
                    sel_str = (
                        sel.get("primary", "") if isinstance(sel, dict) else str(sel)
                    )
                    if "登" in sel_str and "录" in sel_str:
                        try:
                            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
                        except Exception:
                            pass
                        time.sleep(0.5)

                # 同页面操作跳过步骤间延迟，只有页面导航后才等待
                if delay_ms > 0 and i < len(steps) - 1 and page.url != url_before_step:
                    time.sleep(delay_ms / 1000.0)

        except Exception as e:
            logger.error("headless_engine_fatal_error: %s", e, exc_info=True)
        finally:
            if context is not None:
                with contextlib.suppress(Exception):
                    context.close()
            if browser is not None:
                with contextlib.suppress(Exception):
                    browser.close()
            pw.stop()

        total_duration_ms = int((time.time() - start_time) * 1000)
        status = "passed" if steps_failed == 0 else "failed"
        if _terminated:
            status = "terminated"
            # 标记剩余未执行步骤
            for remaining_i in range(len(_step_results), len(steps)):
                _step_results.append(
                    {
                        "index": remaining_i,
                        "action": steps[remaining_i].get("action", ""),
                        "selector": self._selector_to_dict(
                            steps[remaining_i].get("selector", "")
                        ),
                        "value": steps[remaining_i].get("value", ""),
                        "status": "not_executed",
                        "error": "new_tab 页面重定向，执行终止",
                        "duration_ms": 0,
                    }
                )
        if cancel_flag is not None and cancel_flag.is_set():
            status = "cancelled"

        return {
            "status": status,
            "steps_total": len(steps),
            "steps_passed": steps_passed,
            "steps_failed": steps_failed,
            "total_duration_ms": total_duration_ms,
            "_step_results": _step_results,
        }

    def _execute_step(
        self, page: "Page", step: Dict[str, Any], base_url: str, timeout_ms: int
    ) -> Dict[str, Any]:
        """执行单个步骤，返回 step_result dict。"""
        action = step.get("action", "").lower()
        selector = step.get("selector", "")
        value = step.get("value", "")

        try:
            if action == "navigate":
                return self._action_navigate(page, value, base_url)
            elif action == "click":
                return self._action_click(page, selector, timeout_ms)
            elif action in ("type", "input"):
                return self._action_type(page, selector, value, timeout_ms)
            elif action == "clear":
                return self._action_clear(page, selector, timeout_ms)
            elif action == "select":
                return self._action_select(page, selector, value, timeout_ms)
            elif action == "hover":
                return self._action_hover(page, selector, timeout_ms)
            elif action == "wait":
                return self._action_wait(page, value)
            elif action == "assert_text":
                return self._action_assert_text(page, selector, value, timeout_ms)
            elif action == "assert_visible":
                return self._action_assert_visible(page, selector, timeout_ms)
            elif action == "assert_url":
                return self._action_assert_url(page, value)
            elif action == "assert_title":
                return self._action_assert_title(page, value)
            elif action == "assert_count":
                return self._action_assert_count(page, selector, value, timeout_ms)
            elif action == "assert_value":
                return self._action_assert_value(page, selector, value, timeout_ms)
            elif action == "assert_enabled":
                return self._action_assert_enabled(page, selector, timeout_ms)
            elif action == "assert_disabled":
                return self._action_assert_disabled(page, selector, timeout_ms)
            elif action == "assert_not_visible":
                return self._action_assert_not_visible(page, selector, timeout_ms)
            elif action == "scroll":
                return self._action_scroll(page, value)
            elif action in ("select_radio", "check", "uncheck"):
                return self._action_check(page, selector, action, timeout_ms)
            elif action == "screenshot":
                return self._action_screenshot(page)
            else:
                return {
                    "action": action,
                    "selector": self._selector_to_dict(selector),
                    "value": value,
                    "status": "failed",
                    "error": f"未知操作: {action}",
                }
        except Exception as e:
            return {
                "action": action,
                "selector": self._selector_to_dict(selector),
                "value": value,
                "status": "failed",
                "error": str(e)[:200],
            }

    def _execute_step_monitored(
        self,
        page: "Page",
        step: Dict[str, Any],
        base_url: str,
        timeout_ms: int,
        expected_url: str,
    ) -> Dict[str, Any]:
        """执行步骤并轮询监控 URL 变化。

        用于 new_tab 后的第一个步骤：每 2 秒重试一次，每次重试前检查 URL
        是否已变更。如果 URL 变更，立即返回失败（不等待完整超时）。
        """
        action = step.get("action", "").lower()
        selector = step.get("selector", "")
        value = step.get("value", "")
        deadline = time.time() + timeout_ms / 1000.0
        poll_ms = 2000

        while time.time() < deadline:
            # 检查 URL 是否已变更
            current_url = page.url
            if not self._urls_match(current_url, expected_url):
                return {
                    "action": action,
                    "selector": self._selector_to_dict(selector),
                    "value": value,
                    "status": "failed",
                    "error": (
                        f"页面 URL 已变更: 当前={current_url[:120]}, "
                        f"期望={expected_url[:120]}"
                    ),
                }

            # 检查 SPA history hook
            try:
                spa = page.evaluate("() => window.__headless_redirect_url || ''")
                if spa:
                    return {
                        "action": action,
                        "selector": self._selector_to_dict(selector),
                        "value": value,
                        "status": "failed",
                        "error": f"SPA 检测到页面重定向: {spa[:120]}",
                    }
            except Exception:
                pass

            # 尝试执行步骤（短超时）
            remaining = int((deadline - time.time()) * 1000)
            attempt_timeout = min(poll_ms, max(remaining, 500))
            result = self._execute_step(page, step, base_url, attempt_timeout)
            if result["status"] == "passed":
                return result

        return {
            "action": action,
            "selector": self._selector_to_dict(selector),
            "value": value,
            "status": "failed",
            "error": f"Locator.wait_for: Timeout {timeout_ms}ms exceeded.",
        }

    def _classify_strategy(self, selector: str) -> Tuple[str, str]:
        """解析单个选择器字符串，返回 (strategy, value)。"""
        s = selector.strip()
        if not s:
            return ("css", "")
        if s.startswith(("/", "(")):
            return ("xpath", s)
        if s.startswith("text="):
            return ("text", s[5:])
        if s.startswith("role="):
            return ("role", s[5:])
        return ("css", s)

    def _resolve_selector_chain(self, selector: Any) -> List[Tuple[str, str]]:
        """解析选择器回退链，返回 [(strategy, value), ...] 按优先级排列。

        优先级：primary → fallback_css → fallback_xpath（去重，与浏览器引擎一致）
        """
        if not isinstance(selector, dict):
            s = str(selector) if selector else ""
            return [self._classify_strategy(s)] if s else []

        candidates: List[Tuple[str, str]] = []
        seen: set = set()
        for key in ("primary", "fallback_css", "fallback_xpath"):
            s = (selector.get(key, "") or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            candidates.append(self._classify_strategy(s))

        return candidates

    def _build_locator(self, page: "Page", strategy: str, value: str) -> Any:
        """根据 strategy 构建 Playwright locator。

        对 XPath 使用 .first 避免多元素匹配时 strict mode 报错，
        与浏览器回放引擎 querySelector / FIRST_ORDERED_NODE_TYPE 行为一致。
        """
        if strategy == "xpath":
            return page.locator(f"xpath={value}").first
        elif strategy == "text":
            return page.get_by_text(value)
        elif strategy == "role":
            # Playwright 的 ARIA role 类型在不同版本中定义可能不同
            return page.get_by_role(cast("Any", value))  # type: ignore[arg-type,unused-ignore]
        else:
            return page.locator(value).first

    def _resolve_selector(self, selector: Any) -> Tuple[str, str]:
        """解析选择器（兼容旧接口），返回 (strategy, value)。"""
        chain = self._resolve_selector_chain(selector)
        if chain:
            return chain[0]
        return ("css", "")

    @staticmethod
    def _urls_match(current_url: str, target_url: str) -> bool:
        """检查当前 URL 是否匹配目标 URL（比较 hostname + port + path）。"""
        if not current_url or not target_url:
            return False
        if current_url == target_url:
            return True
        from urllib.parse import urlparse  # noqa: E402

        cur = urlparse(current_url)
        tgt = urlparse(target_url)
        return (
            cur.hostname == tgt.hostname
            and cur.port == tgt.port
            and cur.path.rstrip("/") == tgt.path.rstrip("/")
        )

    @staticmethod
    def _check_page_redirect(page: "Page", target_url: str) -> str:
        """检查页面是否被重定向到登录/错误页面。

        仅检测重定向模式（login/error/404等）和跨域跳转。
        同站内合法路径变更（如点击菜单跳转）不视为重定向。
        返回空字符串表示正常，否则返回错误描述。
        """
        current_url = page.url
        from urllib.parse import urlparse  # noqa: E402

        cur = urlparse(current_url)
        tgt = urlparse(target_url)

        # 跨域重定向检测
        if cur.hostname and tgt.hostname and cur.hostname != tgt.hostname:
            return f"页面被重定向到其他域名: 当前={current_url[:120]}, 期望={target_url[:120]}"

        # 检查是否被重定向到已知错误/登录页面（仅在同域内检测）
        cur_path = cur.path.lower()
        tgt_path = tgt.path.lower()

        redirect_patterns = ["/login", "/error", "/404", "/502", "/403", "/500"]
        for pattern in redirect_patterns:
            if pattern in cur_path and pattern not in tgt_path:
                return (
                    f"页面被重定向到 {pattern}（会话可能已过期）: {current_url[:120]}"
                )

        return ""

    def _resolve_new_tab_url(
        self,
        step: Dict[str, Any],
        steps: List[Dict[str, Any]],
        index: int,
        base_url: str,
    ) -> str:
        """解析 new_tab 导航 URL，与浏览器回放引擎优先级一致。

        优先级：step.value → step.tab_url → 下一步 tab_url/page_url
        """
        # 1. 当前步骤的 value 或 tab_url
        url = step.get("value", "") or step.get("tab_url", "")
        if url:
            return url

        # 2. 下一步的 tab_url 或 page_url
        if index + 1 < len(steps):
            next_step = steps[index + 1]
            url = next_step.get("tab_url", "") or next_step.get("page_url", "")
            if url:
                return url

        return ""

    @staticmethod
    def _is_different_origin(url_a: str, url_b: str) -> bool:
        """判断两个 URL 是否属于不同源（host:port 不同）。"""
        try:
            from urllib.parse import urlparse

            pa = urlparse(url_a)
            pb = urlparse(url_b)
            return pa.netloc != pb.netloc
        except Exception:
            return url_a != url_b

    def _find_element(self, page: "Page", selector: Any, timeout_ms: int) -> Any:
        """查找元素，支持选择器回退链（primary → fallback_css → fallback_xpath）。

        与浏览器回放引擎 SelectorEngine.find 保持一致的回退策略：
        每个候选选择器分配较短超时，最后一个用完整超时。
        """
        candidates = self._resolve_selector_chain(selector)
        if not candidates:
            raise HeadlessExecutionError("选择器为空")

        per_timeout = 1000

        last_error: Optional[Exception] = None
        for i, (strategy, value) in enumerate(candidates):
            is_last = i == len(candidates) - 1
            wait_ms = timeout_ms if is_last else per_timeout

            try:
                locator = self._build_locator(page, strategy, value)
                if locator.is_visible():
                    return locator
                locator.wait_for(state="visible", timeout=wait_ms)
                return locator
            except Exception as e:
                last_error = e
                if is_last:
                    raise

        raise last_error or HeadlessExecutionError("元素未找到")

    def _selector_to_dict(self, selector: Any) -> Any:
        """确保 selector 在结果中以 dict 形式返回。"""
        if isinstance(selector, dict):
            return selector
        return {
            "primary": str(selector) if selector else "",
            "fallback_css": "",
            "fallback_xpath": "",
        }

    # ---- Action implementations ----

    def _action_navigate(self, page: "Page", url: str, base_url: str) -> Dict[str, Any]:
        target = url
        if url and not url.startswith(("http://", "https://", "about:")) and base_url:
            target = base_url.rstrip("/") + "/" + url.lstrip("/")
        page.goto(target, wait_until="domcontentloaded")
        return {
            "action": "navigate",
            "selector": {},
            "value": target,
            "status": "passed",
            "error": "",
        }

    def _action_click(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.click()
        return {
            "action": "click",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_type(
        self, page: "Page", selector: Any, value: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        try:
            el.fill(value)
        except Exception as e:
            err = str(e)
            if "cannot be filled" in err:
                el.click()
                return {
                    "action": "type",
                    "selector": self._selector_to_dict(selector),
                    "value": value,
                    "status": "passed",
                    "error": "",
                }
            raise
        return {
            "action": "type",
            "selector": self._selector_to_dict(selector),
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_clear(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.fill("")
        return {
            "action": "clear",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_select(
        self, page: "Page", selector: Any, value: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.select_option(value)
        return {
            "action": "select",
            "selector": self._selector_to_dict(selector),
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_hover(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.hover()
        return {
            "action": "hover",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_check(
        self, page: "Page", selector: Any, action: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        if action == "check":
            el.check()
        elif action == "uncheck":
            el.uncheck()
        else:
            el.click()
        return {
            "action": action,
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_wait(self, page: "Page", value: str) -> Dict[str, Any]:
        try:
            ms = int(float(value))
        except (ValueError, TypeError):
            ms = 1000
        time.sleep(ms / 1000.0)
        return {
            "action": "wait",
            "selector": {},
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_assert_text(
        self, page: "Page", selector: Any, expected: str, timeout_ms: int
    ) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        actual = (el.inner_text() or "").strip()
        if expected in actual:
            return {
                "action": "assert_text",
                "selector": self._selector_to_dict(selector),
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_text",
            "selector": self._selector_to_dict(selector),
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望包含 '{expected}', 实际 '{actual[:80]}'",
        }

    def _action_assert_visible(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        self._find_element(page, selector, timeout_ms)
        return {
            "action": "assert_visible",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _action_assert_url(self, page: "Page", expected: str) -> Dict[str, Any]:
        actual = page.url
        if expected in actual:
            return {
                "action": "assert_url",
                "selector": {},
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_url",
            "selector": {},
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望 URL 包含 '{expected}', 实际 '{actual}'",
        }

    def _action_assert_title(self, page: "Page", expected: str) -> Dict[str, Any]:
        actual = page.title()
        if expected in actual:
            return {
                "action": "assert_title",
                "selector": {},
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_title",
            "selector": {},
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望标题包含 '{expected}', 实际 '{actual}'",
        }

    def _action_assert_count(
        self, page: "Page", selector: Any, expected: str, timeout_ms: int
    ) -> Dict[str, Any]:
        """断言匹配选择器的元素数量等于期望值。"""
        try:
            expected_count = int(expected) if expected else 0
        except (ValueError, TypeError):
            return {
                "action": "assert_count",
                "selector": self._selector_to_dict(selector),
                "value": expected,
                "status": "failed",
                "error": f"期望数量必须是整数，实际 '{expected}'",
            }

        candidates = self._resolve_selector_chain(selector)
        if not candidates:
            return {
                "action": "assert_count",
                "selector": self._selector_to_dict(selector),
                "value": expected,
                "status": "failed",
                "error": "选择器为空",
            }

        # 使用第一个选择器候选
        strategy, value = candidates[0]

        # 对于 count，需要使用不带 .first 的 locator 来统计所有匹配元素
        if strategy == "xpath":
            locator = page.locator(f"xpath={value}")
        elif strategy == "text":
            locator = page.get_by_text(value)
        elif strategy == "role":
            locator = page.get_by_role(cast("Any", value))  # type: ignore[arg-type,unused-ignore]
        else:
            locator = page.locator(value)

        try:
            locator.first.wait_for(state="attached", timeout=timeout_ms)
        except Exception:
            pass

        actual_count = locator.count()

        if actual_count == expected_count:
            return {
                "action": "assert_count",
                "selector": self._selector_to_dict(selector),
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_count",
            "selector": self._selector_to_dict(selector),
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望 {expected_count} 个元素, 实际 {actual_count} 个",
        }

    def _action_assert_value(
        self, page: "Page", selector: Any, expected: str, timeout_ms: int
    ) -> Dict[str, Any]:
        """断言输入框的值等于期望值。"""
        el = self._find_element(page, selector, timeout_ms)
        actual = el.input_value() if el.input_value else ""

        if actual == expected:
            return {
                "action": "assert_value",
                "selector": self._selector_to_dict(selector),
                "value": expected,
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_value",
            "selector": self._selector_to_dict(selector),
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望值 '{expected}', 实际 '{actual[:80]}'",
        }

    def _action_assert_enabled(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        """断言元素处于启用状态（可交互）。"""
        el = self._find_element(page, selector, timeout_ms)
        is_enabled = el.is_enabled()

        if is_enabled:
            return {
                "action": "assert_enabled",
                "selector": self._selector_to_dict(selector),
                "value": "",
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_enabled",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "failed",
            "error": "断言失败: 元素处于禁用状态",
        }

    def _action_assert_disabled(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        """断言元素处于禁用状态。"""
        el = self._find_element(page, selector, timeout_ms)
        is_enabled = el.is_enabled()

        if not is_enabled:
            return {
                "action": "assert_disabled",
                "selector": self._selector_to_dict(selector),
                "value": "",
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_disabled",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "failed",
            "error": "断言失败: 元素处于启用状态",
        }

    def _action_assert_not_visible(
        self, page: "Page", selector: Any, timeout_ms: int
    ) -> Dict[str, Any]:
        """断言元素不可见或不存在。"""
        candidates = self._resolve_selector_chain(selector)
        if not candidates:
            return {
                "action": "assert_not_visible",
                "selector": self._selector_to_dict(selector),
                "value": "",
                "status": "passed",
                "error": "",
            }

        # 使用第一个选择器候选
        strategy, value = candidates[0]

        # 构建 locator（不带 .first，因为我们要检查是否存在）
        if strategy == "xpath":
            locator = page.locator(f"xpath={value}").first
        elif strategy == "text":
            locator = page.get_by_text(value)
        elif strategy == "role":
            locator = page.get_by_role(cast("Any", value))  # type: ignore[arg-type,unused-ignore]
        else:
            locator = page.locator(value).first

        # 等待元素隐藏或不存在
        try:
            locator.wait_for(state="hidden", timeout=min(timeout_ms, 2000))
            return {
                "action": "assert_not_visible",
                "selector": self._selector_to_dict(selector),
                "value": "",
                "status": "passed",
                "error": "",
            }
        except Exception:
            pass

        # 检查元素是否可见
        if locator.count() == 0 or not locator.is_visible():
            return {
                "action": "assert_not_visible",
                "selector": self._selector_to_dict(selector),
                "value": "",
                "status": "passed",
                "error": "",
            }
        return {
            "action": "assert_not_visible",
            "selector": self._selector_to_dict(selector),
            "value": "",
            "status": "failed",
            "error": "断言失败: 元素可见",
        }

    def _action_scroll(self, page: "Page", value: str) -> Dict[str, Any]:
        try:
            px = int(float(value)) if value else 300
        except (ValueError, TypeError):
            px = 300
        page.evaluate(f"window.scrollBy(0, {px})")
        return {
            "action": "scroll",
            "selector": {},
            "value": value,
            "status": "passed",
            "error": "",
        }

    def _action_screenshot(self, page: "Page") -> Dict[str, Any]:
        return {
            "action": "screenshot",
            "selector": {},
            "value": "",
            "status": "passed",
            "error": "",
        }

    def _take_screenshot(
        self, page: "Page", job_id: str, step_index: int, suffix: str = "_fail"
    ) -> None:
        """截图保存。suffix 为空时保存为 step_{i}.png，否则 step_{i}{suffix}.png。"""
        if not self._screenshots_dir:
            return
        try:
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = self._screenshots_dir / f"step_{step_index}{suffix}.png"
            page.screenshot(path=str(path))
        except Exception as e:
            logger.warning("screenshot_failed: %s", e)
