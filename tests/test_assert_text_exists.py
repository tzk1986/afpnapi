"""assert_text_exists 纯文本断言单元测试。

验证无头引擎的 _action_assert_text_exists 方法：
- 页面存在文本时断言通过
- 页面不存在文本时断言失败
- 空文本输入时直接失败
- 超时行为正确
"""

import unittest
from unittest.mock import MagicMock, patch


class FakeLocator:
    """模拟 Playwright Locator。"""

    def __init__(self, found: bool, raise_on_wait: bool = False):
        self._found = found
        self._raise_on_wait = raise_on_wait

    @property
    def first(self):
        return self

    def wait_for(self, state: str = "attached", timeout: int = 30000):
        if self._raise_on_wait:
            raise TimeoutError("Locator.wait_for: Timeout 30000ms exceeded")
        if not self._found:
            raise TimeoutError("Locator.wait_for: Timeout 30000ms exceeded")


class FakePage:
    """模拟 Playwright Page。"""

    def __init__(self, body_text: str = "", text_found: bool = True, raise_on_wait: bool = False):
        self._body_text = body_text
        self._text_found = text_found
        self._raise_on_wait = raise_on_wait

    def get_by_text(self, text: str, exact: bool = False):
        # 简单模拟：如果 body_text 包含 text 则视为找到
        if text in self._body_text:
            return FakeLocator(found=True)
        return FakeLocator(found=False, raise_on_wait=True)

    def inner_text(self, selector: str) -> str:
        return self._body_text


class TestAssertTextExists(unittest.TestCase):
    """测试 _action_assert_text_exists 方法。"""

    def _make_engine(self):
        """创建最小化的引擎实例（绕过 __init__ 的重量级依赖）。"""
        from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine
        engine = UiHeadlessEngine.__new__(UiHeadlessEngine)
        return engine

    def test_empty_text_returns_failed(self):
        """空文本输入应直接返回失败，不尝试查找。"""
        engine = self._make_engine()
        page = FakePage()
        result = engine._action_assert_text_exists(page, "", 5000)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["action"], "assert_text_exists")
        self.assertIn("未指定", result["error"])

    def test_text_found_returns_passed(self):
        """页面存在指定文本时应返回通过。"""
        engine = self._make_engine()
        page = FakePage(body_text="订单列表 - 供应商管理系统", text_found=True)
        result = engine._action_assert_text_exists(page, "供应商", 5000)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["value"], "供应商")
        self.assertEqual(result["error"], "")

    def test_text_not_found_returns_failed(self):
        """页面不存在指定文本时应返回失败，包含诊断信息。"""
        engine = self._make_engine()
        page = FakePage(body_text="订单列表 - 管理系统", text_found=False)
        result = engine._action_assert_text_exists(page, "供应商", 5000)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["value"], "供应商")
        self.assertIn("供应商", result["error"])
        self.assertIn("页面内容前 200 字", result["error"])

    def test_result_structure(self):
        """返回结果应包含标准字段。"""
        engine = self._make_engine()
        page = FakePage(body_text="测试文本", text_found=True)
        result = engine._action_assert_text_exists(page, "测试", 5000)
        self.assertIn("action", result)
        self.assertIn("selector", result)
        self.assertIn("value", result)
        self.assertIn("status", result)
        self.assertIn("error", result)
        self.assertEqual(result["selector"], {})


class TestAssertTextExistsChineseText(unittest.TestCase):
    """测试中文文本断言场景。"""

    def _make_engine(self):
        from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine
        engine = UiHeadlessEngine.__new__(UiHeadlessEngine)
        return engine

    def test_chinese_text_found(self):
        """中文文本应能正确匹配。"""
        engine = self._make_engine()
        page = FakePage(body_text="欢迎使用供应商管理平台，当前订单数: 128", text_found=True)
        result = engine._action_assert_text_exists(page, "供应商管理平台", 5000)
        self.assertEqual(result["status"], "passed")

    def test_chinese_text_with_special_chars(self):
        """包含特殊字符的中文文本应能正确匹配。"""
        engine = self._make_engine()
        page = FakePage(body_text="订单金额：¥1,234.56（含税）", text_found=True)
        result = engine._action_assert_text_exists(page, "¥1,234.56", 5000)
        self.assertEqual(result["status"], "passed")


if __name__ == "__main__":
    unittest.main()
