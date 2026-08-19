"""_is_login_step 登录步骤检测单元测试。

验证登录按钮检测逻辑：
- 中文"登录"关键词匹配
- 英文"login"/"sign in"关键词匹配
- is_login_step 元数据优先
- 非登录步骤不误判
"""

import unittest

from postman_api_tester.services.ui_headless_engine import _is_login_step


class TestIsLoginStep(unittest.TestCase):
    """测试 _is_login_step 函数。"""

    def test_chinese_login_in_selector(self):
        """选择器包含中文'登录'应识别为登录步骤。"""
        step = {"selector": "button.login-btn", "element_info": {"text": "登录"}}
        self.assertTrue(_is_login_step(step))

    def test_chinese_login_in_text_only(self):
        """element_info.text 包含中文'登录'应识别为登录步骤。"""
        step = {"selector": "#submit-btn", "element_info": {"text": "用户登录"}}
        self.assertTrue(_is_login_step(step))

    def test_english_login_in_selector(self):
        """选择器包含英文'login'应识别为登录步骤。"""
        step = {"selector": "#loginButton", "element_info": {}}
        self.assertTrue(_is_login_step(step))

    def test_english_signin_in_text(self):
        """element_info.text 包含'sign in'应识别为登录步骤。"""
        step = {"selector": "button.primary", "element_info": {"text": "Sign In"}}
        self.assertTrue(_is_login_step(step))

    def test_english_log_in_with_space(self):
        """element_info.text 包含'log in'（两个单词）应识别为登录步骤。"""
        step = {"selector": "button", "element_info": {"text": "Log In"}}
        self.assertTrue(_is_login_step(step))

    def test_explicit_metadata_flag(self):
        """is_login_step 元数据标记为 True 应直接识别。"""
        step = {"selector": "#random-btn", "is_login_step": True, "element_info": {}}
        self.assertTrue(_is_login_step(step))

    def test_metadata_flag_overrides_no_keywords(self):
        """is_login_step 元数据优先于关键词检测。"""
        step = {"selector": "button", "is_login_step": True, "element_info": {"text": "提交"}}
        self.assertTrue(_is_login_step(step))

    def test_non_login_step_returns_false(self):
        """普通按钮点击不应识别为登录步骤。"""
        step = {"selector": "button.save", "element_info": {"text": "保存"}}
        self.assertFalse(_is_login_step(step))

    def test_empty_step_returns_false(self):
        """空步骤不应识别为登录步骤。"""
        step = {}
        self.assertFalse(_is_login_step(step))

    def test_selector_as_string(self):
        """选择器为字符串时应正确检测。"""
        step = {"selector": "button#login-submit", "element_info": {}}
        self.assertTrue(_is_login_step(step))

    def test_case_insensitive_matching(self):
        """关键词匹配应不区分大小写。"""
        step = {"selector": "button", "element_info": {"text": "LOGIN"}}
        self.assertTrue(_is_login_step(step))

    def test_partial_chinese_chars_not_matched(self):
        """仅包含单个中文字符（如'登'但不含'录'）不应匹配。"""
        # "登山" 含有 "登" 但不含 "录"
        step = {"selector": "button", "element_info": {"text": "登山"}}
        self.assertFalse(_is_login_step(step))


if __name__ == "__main__":
    unittest.main()
