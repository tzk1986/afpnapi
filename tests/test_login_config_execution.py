"""登录配置执行方法单元测试。

测试 UiHeadlessEngine.execute_login_config() 的核心逻辑。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch


class TestExecuteLoginConfig(unittest.TestCase):
    """测试 execute_login_config 方法。"""

    def _make_engine(self) -> Any:
        """创建引擎实例（跳过 Playwright 可用性检查）。"""
        with patch(
            "postman_api_tester.services.ui_headless_engine._HAS_PLAYWRIGHT", True
        ):
            from postman_api_tester.services.ui_headless_engine import (
                UiHeadlessEngine,
            )

            return UiHeadlessEngine(browser_type="chromium")

    def test_successful_login_captures_cookies(self) -> None:
        """登录成功时捕获 Cookie。"""
        engine = self._make_engine()

        mock_cookie = {
            "name": "session_id",
            "value": "abc123",
            "domain": ".example.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.cookies.return_value = [mock_cookie]
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        with patch(
            "postman_api_tester.services.ui_headless_engine.sync_playwright",
            return_value=MagicMock(start=MagicMock(return_value=mock_pw)),
        ):
            # Mock _execute_step to return success
            engine._execute_step = MagicMock(
                return_value={"status": "passed", "error": ""}
            )

            result = engine.execute_login_config(
                login_steps=[
                    {"action": "navigate", "value": "/login"},
                    {"action": "type", "selector": "#user", "value": "admin"},
                ],
                base_url="http://example.com",
            )

        self.assertEqual(result["status"], "passed")
        self.assertGreater(result["cookie_count"], 0)
        self.assertEqual(result["cookies"][0]["name"], "session_id")
        self.assertEqual(result["cookies"][0]["value"], "abc123")

    def test_failed_login_returns_no_cookies(self) -> None:
        """登录失败时不返回 Cookie。"""
        engine = self._make_engine()

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        with patch(
            "postman_api_tester.services.ui_headless_engine.sync_playwright",
            return_value=MagicMock(start=MagicMock(return_value=mock_pw)),
        ):
            engine._execute_step = MagicMock(
                return_value={"status": "failed", "error": "元素未找到"}
            )

            result = engine.execute_login_config(
                login_steps=[{"action": "click", "selector": "#login-btn"}],
                base_url="http://example.com",
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["cookie_count"], 0)
        self.assertEqual(result["cookies"], [])
        self.assertEqual(result["error"], "元素未找到")

    def test_execution_error_returns_error_status(self) -> None:
        """执行异常时返回 error 状态。"""
        engine = self._make_engine()

        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = RuntimeError("浏览器启动失败")

        with patch(
            "postman_api_tester.services.ui_headless_engine.sync_playwright",
            return_value=MagicMock(start=MagicMock(return_value=mock_pw)),
        ):
            result = engine.execute_login_config(
                login_steps=[{"action": "navigate", "value": "/login"}],
                base_url="http://example.com",
            )

        self.assertEqual(result["status"], "error")
        self.assertIn("浏览器启动失败", result["error"])
        self.assertEqual(result["cookie_count"], 0)

    def test_cookie_domain_filtering(self) -> None:
        """Cookie 按目标域名过滤。"""
        engine = self._make_engine()

        mock_cookies = [
            {
                "name": "session",
                "value": "abc",
                "domain": ".example.com",
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "other",
                "value": "xyz",
                "domain": ".other-domain.com",
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
        ]

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.cookies.return_value = mock_cookies
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        with patch(
            "postman_api_tester.services.ui_headless_engine.sync_playwright",
            return_value=MagicMock(start=MagicMock(return_value=mock_pw)),
        ):
            engine._execute_step = MagicMock(
                return_value={"status": "passed", "error": ""}
            )

            result = engine.execute_login_config(
                login_steps=[{"action": "navigate", "value": "/login"}],
                base_url="http://example.com",
            )

        self.assertEqual(result["status"], "passed")
        # 只保留 example.com 域的 Cookie
        self.assertEqual(result["cookie_count"], 1)
        self.assertEqual(result["cookies"][0]["name"], "session")


class TestRefreshAuthFromLoginConfig(unittest.TestCase):
    """测试 _refresh_auth_from_login_config 函数。"""

    def test_config_not_found_returns_original(self) -> None:
        """登录配置不存在时返回原始档案。"""
        from postman_api_tester.handlers.ui_execution_routes import (
            _refresh_auth_from_login_config,
        )

        profile = {"id": "auth_001", "cookies": [], "name": "test"}

        with patch(
            "postman_api_tester.services.ui_login_config_store._login_config_store"
        ) as mock_store:
            mock_store.get_config.return_value = None
            result = _refresh_auth_from_login_config(profile, "login_999", "auth_001")

        self.assertEqual(result, profile)

    def test_empty_config_returns_original(self) -> None:
        """登录配置为空时返回原始档案。"""
        from postman_api_tester.handlers.ui_execution_routes import (
            _refresh_auth_from_login_config,
        )

        profile = {"id": "auth_001", "cookies": [], "name": "test"}

        with patch(
            "postman_api_tester.services.ui_login_config_store._login_config_store"
        ) as mock_store:
            mock_store.get_config.return_value = {
                "id": "login_001",
                "login_steps": [],
                "base_url": "http://example.com",
            }
            result = _refresh_auth_from_login_config(profile, "login_001", "auth_001")

        self.assertEqual(result, profile)


if __name__ == "__main__":
    unittest.main()
