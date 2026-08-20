"""assert_element_exists 语义化选择器断言单元测试。

验证无头引擎的 _parse_semantic_selector 和 _action_assert_element_exists 方法：
- 语义化选择器解析（role:text 格式）
- 纯文本选择器降级
- 元素存在时断言通过
- 元素不存在时断言失败
- 空选择器时直接失败
- 多匹配时返回 match_count
"""

import unittest
from unittest.mock import MagicMock, patch


class FakeLocator:
    """模拟 Playwright Locator。"""

    def __init__(self, found: bool, count: int = 1, raise_on_count: bool = False):
        self._found = found
        self._count = count if found else 0
        self._raise_on_count = raise_on_count

    @property
    def first(self):
        return self

    def count(self) -> int:
        if self._raise_on_count:
            raise RuntimeError("count failed")
        return self._count

    def wait_for(self, state: str = "visible", timeout: int = 30000):
        if not self._found:
            raise TimeoutError("Locator.wait_for: Timeout 30000ms exceeded")


class FakePage:
    """模拟 Playwright Page。"""

    def __init__(
        self,
        text_found: bool = True,
        match_count: int = 1,
        raise_on_count: bool = False,
        url: str = "http://example.com/page",
    ):
        self._text_found = text_found
        self._match_count = match_count
        self._raise_on_count = raise_on_count
        self.url = url

    def get_by_role(self, role: str, name: str = None, **kwargs):
        if self._text_found:
            return FakeLocator(found=True, count=self._match_count, raise_on_count=self._raise_on_count)
        return FakeLocator(found=False, count=0)

    def get_by_text(self, text: str, exact: bool = False):
        if self._text_found:
            return FakeLocator(found=True, count=self._match_count, raise_on_count=self._raise_on_count)
        return FakeLocator(found=False, count=0)


class TestParseSemanticSelector(unittest.TestCase):
    """测试 _parse_semantic_selector 方法。"""

    def _make_engine(self):
        """创建最小化的引擎实例（绕过 __init__ 的重量级依赖）。"""
        from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine
        engine = UiHeadlessEngine.__new__(UiHeadlessEngine)
        return engine

    def test_button_role(self):
        """button:查看订单 应解析为 role=button, text=查看订单。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("button:查看订单")
        self.assertEqual(role, "button")
        self.assertEqual(text, "查看订单")

    def test_link_role(self):
        """link:首页 应解析为 role=link, text=首页。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("link:首页")
        self.assertEqual(role, "link")
        self.assertEqual(text, "首页")

    def test_heading_role(self):
        """heading:系统设置 应解析为 role=heading, text=系统设置。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("heading:系统设置")
        self.assertEqual(role, "heading")
        self.assertEqual(text, "系统设置")

    def test_text_with_colon_not_role(self):
        """未知角色应降级为纯文本匹配。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("unknown:某些文字")
        self.assertEqual(role, "")
        self.assertEqual(text, "unknown:某些文字")

    def test_no_colon_pure_text(self):
        """无冒号应作为纯文本匹配。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("查看订单")
        self.assertEqual(role, "")
        self.assertEqual(text, "查看订单")

    def test_empty_string(self):
        """空字符串应返回空 role 和空 text。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("")
        self.assertEqual(role, "")
        self.assertEqual(text, "")

    def test_role_case_insensitive(self):
        """角色应不区分大小写。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("BUTTON:查看订单")
        self.assertEqual(role, "button")
        self.assertEqual(text, "查看订单")

    def test_text_containing_colon(self):
        """文本中包含冒号时应保留。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("label:时间: 10:30")
        self.assertEqual(role, "label")
        self.assertEqual(text, "时间: 10:30")

    def test_tab_role(self):
        """tab:订单管理 应解析为 role=tab, text=订单管理。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("tab:订单管理")
        self.assertEqual(role, "tab")
        self.assertEqual(text, "订单管理")

    def test_menuitem_role(self):
        """menuitem:退出登录 应解析为 role=menuitem, text=退出登录。"""
        engine = self._make_engine()
        role, text = engine._parse_semantic_selector("menuitem:退出登录")
        self.assertEqual(role, "menuitem")
        self.assertEqual(text, "退出登录")


class TestAssertElementExists(unittest.TestCase):
    """测试 _action_assert_element_exists 方法。"""

    def _make_engine(self):
        from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine
        engine = UiHeadlessEngine.__new__(UiHeadlessEngine)
        return engine

    def test_empty_selector_returns_failed(self):
        """空选择器应直接返回失败。"""
        engine = self._make_engine()
        page = FakePage()
        result = engine._action_assert_element_exists(page, "", 5000)
        self.assertEqual(result["status"], "failed")
        self.assertIn("未指定", result["error"])

    def test_element_found_returns_passed(self):
        """找到元素应返回通过。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "button:查看订单", 5000)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["action"], "assert_element_exists")

    def test_element_not_found_returns_failed(self):
        """未找到元素应返回失败。"""
        engine = self._make_engine()
        page = FakePage(text_found=False)
        result = engine._action_assert_element_exists(page, "button:不存在", 1000)
        self.assertEqual(result["status"], "failed")
        self.assertIn("未找到元素", result["error"])
        self.assertIn("当前 URL", result["error"])

    def test_result_structure_with_role(self):
        """带角色的选择器返回结果应包含 semantic selector。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "link:首页", 5000)
        self.assertIn("selector", result)
        self.assertEqual(result["selector"]["type"], "semantic")
        self.assertEqual(result["selector"]["role"], "link")
        self.assertEqual(result["selector"]["text"], "首页")

    def test_result_structure_without_role(self):
        """无角色的选择器返回结果应包含空 role。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "首页", 5000)
        self.assertEqual(result["selector"]["role"], "")
        self.assertEqual(result["selector"]["text"], "首页")

    def test_multiple_matches_returned(self):
        """多匹配应返回 match_count。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=3)
        result = engine._action_assert_element_exists(page, "button:提交", 5000)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["match_count"], 3)

    def test_pure_text_uses_get_by_text(self):
        """纯文本选择器应使用 get_by_text。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "欢迎使用", 5000)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["selector"]["role"], "")


class TestAssertElementExistsChineseText(unittest.TestCase):
    """测试中文文本断言场景。"""

    def _make_engine(self):
        from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine
        engine = UiHeadlessEngine.__new__(UiHeadlessEngine)
        return engine

    def test_chinese_button(self):
        """中文按钮文字应能匹配。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "button:提交订单", 5000)
        self.assertEqual(result["status"], "passed")

    def test_chinese_link(self):
        """中文链接文字应能匹配。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "link:个人中心", 5000)
        self.assertEqual(result["status"], "passed")

    def test_chinese_heading(self):
        """中文标题应能匹配。"""
        engine = self._make_engine()
        page = FakePage(text_found=True, match_count=1)
        result = engine._action_assert_element_exists(page, "heading:系统设置", 5000)
        self.assertEqual(result["status"], "passed")


if __name__ == "__main__":
    unittest.main()
