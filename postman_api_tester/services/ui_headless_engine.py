"""UI 测试无头浏览器执行引擎。

使用 Playwright 在后台线程中执行 UI 测试步骤。
需要安装 playwright: pip install playwright && playwright install chromium
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 无头执行日志目录
_HEADLESS_LOG_DIR = Path("logs/headless")
_HEADLESS_LOG_RETENTION_DAYS = 10


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
        with open(log_file, "a", encoding="utf-8") as f:
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
    ) -> Dict[str, Any]:
        """执行所有步骤，返回摘要。

        Args:
            steps: 步骤列表
            base_url: 基础 URL（导航步骤的相对路径会拼接此值）
            options: 执行选项（timeout, delay_between_steps）
            job_id: 任务 ID（用于截图命名）
            cancel_flag: threading.Event，被 set 时中止执行
            on_step_complete: 回调 (step_index, step_result_dict) -> None
        """
        timeout_ms = options.get("timeout", 30000)
        delay_ms = options.get("delay_between_steps", 500)
        viewport_w = options.get("viewport_width", 1280)
        viewport_h = options.get("viewport_height", 720)

        pw = sync_playwright().start()
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        steps_passed = 0
        steps_failed = 0
        start_time = time.time()

        _cleanup_old_logs()

        current_step_index = [-1]  # 用 list 以便在闭包中修改

        def _on_request(request: Any) -> None:
            """拦截并记录无头执行中的网络请求。"""
            url = request.url
            # 只记录 API 请求，跳过静态资源
            if "/api/" not in url:
                return
            _log_request(job_id, current_step_index[0], {
                "event": "request",
                "method": request.method,
                "url": url,
                "headers": dict(request.headers),
            })

        def _on_response(response: Any) -> None:
            """记录响应状态。"""
            url = response.url
            if "/api/" not in url:
                return
            _log_request(job_id, current_step_index[0], {
                "event": "response",
                "method": response.request.method,
                "url": url,
                "status": response.status,
                "status_text": response.status_text,
            })

        try:
            launcher = getattr(pw, self._browser_type, pw.chromium)
            browser = launcher.launch(headless=True)
            context = browser.new_context(viewport={"width": viewport_w, "height": viewport_h})
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            # 监听网络请求
            page.on("request", _on_request)
            page.on("response", _on_response)

            # 自动导航到 base_url（回放模式下 iframe 已指向 base_url，无头模式需要显式跳转）
            if base_url:
                page.goto(base_url, wait_until="domcontentloaded")

            for i, step in enumerate(steps):
                if cancel_flag is not None and cancel_flag.is_set():
                    break

                step_start = time.time()
                step_result = self._execute_step(page, step, base_url, timeout_ms)
                step_duration_ms = int((time.time() - step_start) * 1000)

                step_result["index"] = i
                step_result["duration_ms"] = step_duration_ms

                if step_result["status"] == "passed":
                    steps_passed += 1
                else:
                    steps_failed += 1
                    self._take_screenshot(page, job_id, i)

                if on_step_complete is not None:
                    on_step_complete(i, step_result)

                if delay_ms > 0 and i < len(steps) - 1:
                    time.sleep(delay_ms / 1000.0)

        except Exception as e:
            logger.error("headless_engine_fatal_error: %s", e, exc_info=True)
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            pw.stop()

        total_duration_ms = int((time.time() - start_time) * 1000)
        status = "passed" if steps_failed == 0 else "failed"
        if cancel_flag is not None and cancel_flag.is_set():
            status = "cancelled"

        return {
            "status": status,
            "steps_total": len(steps),
            "steps_passed": steps_passed,
            "steps_failed": steps_failed,
            "total_duration_ms": total_duration_ms,
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

    def _resolve_selector(self, selector: Any) -> Tuple[str, str]:
        """解析选择器，返回 (strategy, value)。

        strategy: 'css' | 'xpath' | 'text' | 'role'
        """
        if isinstance(selector, dict):
            primary = selector.get("primary", "")
            fallback_css = selector.get("fallback_css", "")
            fallback_xpath = selector.get("fallback_xpath", "")
            if primary:
                if primary.startswith("/") or primary.startswith("("):
                    return ("xpath", primary)
                return ("css", primary)
            if fallback_css:
                return ("css", fallback_css)
            if fallback_xpath:
                return ("xpath", fallback_xpath)
            return ("css", "")

        s = str(selector) if selector else ""
        if not s:
            return ("css", "")
        if s.startswith("/") or s.startswith("("):
            return ("xpath", s)
        if s.startswith("text="):
            return ("text", s[5:])
        if s.startswith("role="):
            return ("role", s[5:])
        return ("css", s)

    def _find_element(self, page: "Page", selector: Any, timeout_ms: int) -> Any:
        """查找元素，支持选择器回退链。"""
        strategy, value = self._resolve_selector(selector)
        if not value:
            raise HeadlessExecutionError("选择器为空")

        if strategy == "xpath":
            locator = page.locator(f"xpath={value}")
        elif strategy == "text":
            locator = page.get_by_text(value)
        elif strategy == "role":
            locator = page.get_by_role(value)  # type: ignore[arg-type]
        else:
            locator = page.locator(value)

        locator.wait_for(state="visible", timeout=timeout_ms)
        return locator

    def _selector_to_dict(self, selector: Any) -> Any:
        """确保 selector 在结果中以 dict 形式返回。"""
        if isinstance(selector, dict):
            return selector
        return {"primary": str(selector) if selector else "", "fallback_css": "", "fallback_xpath": ""}

    # ---- Action implementations ----

    def _action_navigate(self, page: "Page", url: str, base_url: str) -> Dict[str, Any]:
        target = url
        if url and not url.startswith(("http://", "https://", "about:")):
            if base_url:
                target = base_url.rstrip("/") + "/" + url.lstrip("/")
        page.goto(target, wait_until="domcontentloaded")
        return {"action": "navigate", "selector": {}, "value": target, "status": "passed", "error": ""}

    def _action_click(self, page: "Page", selector: Any, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.click()
        return {"action": "click", "selector": self._selector_to_dict(selector), "value": "", "status": "passed", "error": ""}

    def _action_type(self, page: "Page", selector: Any, value: str, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        try:
            el.fill(value)
        except Exception as e:
            err = str(e)
            if "cannot be filled" in err:
                # radio/checkbox — 回退为点击
                el.click()
                return {"action": "type", "selector": self._selector_to_dict(selector), "value": value, "status": "passed", "error": ""}
            raise
        return {"action": "type", "selector": self._selector_to_dict(selector), "value": value, "status": "passed", "error": ""}

    def _action_clear(self, page: "Page", selector: Any, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.fill("")
        return {"action": "clear", "selector": self._selector_to_dict(selector), "value": "", "status": "passed", "error": ""}

    def _action_select(self, page: "Page", selector: Any, value: str, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.select_option(value)
        return {"action": "select", "selector": self._selector_to_dict(selector), "value": value, "status": "passed", "error": ""}

    def _action_hover(self, page: "Page", selector: Any, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        el.hover()
        return {"action": "hover", "selector": self._selector_to_dict(selector), "value": "", "status": "passed", "error": ""}

    def _action_check(self, page: "Page", selector: Any, action: str, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        if action == "check":
            el.check()
        elif action == "uncheck":
            el.uncheck()
        else:
            # select_radio → 点击 radio 按钮
            el.click()
        return {"action": action, "selector": self._selector_to_dict(selector), "value": "", "status": "passed", "error": ""}

    def _action_wait(self, page: "Page", value: str) -> Dict[str, Any]:
        try:
            ms = int(float(value))
        except (ValueError, TypeError):
            ms = 1000
        time.sleep(ms / 1000.0)
        return {"action": "wait", "selector": {}, "value": value, "status": "passed", "error": ""}

    def _action_assert_text(self, page: "Page", selector: Any, expected: str, timeout_ms: int) -> Dict[str, Any]:
        el = self._find_element(page, selector, timeout_ms)
        actual = (el.inner_text() or "").strip()
        if expected in actual:
            return {"action": "assert_text", "selector": self._selector_to_dict(selector), "value": expected, "status": "passed", "error": ""}
        return {
            "action": "assert_text",
            "selector": self._selector_to_dict(selector),
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望包含 '{expected}', 实际 '{actual[:80]}'",
        }

    def _action_assert_visible(self, page: "Page", selector: Any, timeout_ms: int) -> Dict[str, Any]:
        self._find_element(page, selector, timeout_ms)
        return {"action": "assert_visible", "selector": self._selector_to_dict(selector), "value": "", "status": "passed", "error": ""}

    def _action_assert_url(self, page: "Page", expected: str) -> Dict[str, Any]:
        actual = page.url
        if expected in actual:
            return {"action": "assert_url", "selector": {}, "value": expected, "status": "passed", "error": ""}
        return {
            "action": "assert_url",
            "selector": {},
            "value": expected,
            "status": "failed",
            "error": f"断言失败: 期望 URL 包含 '{expected}', 实际 '{actual}'",
        }

    def _action_scroll(self, page: "Page", value: str) -> Dict[str, Any]:
        try:
            px = int(float(value)) if value else 300
        except (ValueError, TypeError):
            px = 300
        page.evaluate(f"window.scrollBy(0, {px})")
        return {"action": "scroll", "selector": {}, "value": value, "status": "passed", "error": ""}

    def _action_screenshot(self, page: "Page") -> Dict[str, Any]:
        return {"action": "screenshot", "selector": {}, "value": "", "status": "passed", "error": ""}

    def _take_screenshot(self, page: "Page", job_id: str, step_index: int) -> None:
        """失败时截图保存。"""
        if not self._screenshots_dir:
            return
        try:
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = self._screenshots_dir / f"step_{step_index}_fail.png"
            page.screenshot(path=str(path))
        except Exception as e:
            logger.warning("screenshot_failed: %s", e)
