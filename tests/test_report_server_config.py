"""report_server_config 模块单元测试。

覆盖配置读取工具函数的正常/边界/异常路径。
"""

import pytest
from unittest.mock import MagicMock, patch
from types import ModuleType


class TestCfgInt:
    """_cfg_int 函数测试。"""

    def test_returns_default_when_cfg_is_none(self):
        """当 _cfg 为 None 时返回默认值。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_int
            assert _cfg_int("NONEXISTENT", 42) == 42

    def test_returns_config_value(self):
        """返回配置模块中的值。"""
        mock_cfg = MagicMock()
        mock_cfg.MY_VALUE = 100
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_int
            assert _cfg_int("MY_VALUE", 42) == 100

    def test_returns_default_on_type_error(self):
        """当配置值无法转换为 int 时返回默认值。"""
        mock_cfg = MagicMock()
        mock_cfg.BAD_VALUE = "not_a_number"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_int
            assert _cfg_int("BAD_VALUE", 99) == 99

    def test_returns_default_on_value_error(self):
        """当配置值为 None 时返回默认值。"""
        mock_cfg = MagicMock()
        mock_cfg.NONE_VALUE = None
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_int
            assert _cfg_int("NONE_VALUE", 55) == 55

    def test_converts_string_to_int(self):
        """字符串数字应正确转换。"""
        mock_cfg = MagicMock()
        mock_cfg.STR_NUM = "123"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_int
            assert _cfg_int("STR_NUM", 0) == 123


class TestCfgBool:
    """_cfg_bool 函数测试。"""

    def test_returns_default_when_cfg_is_none(self):
        """当 _cfg 为 None 时返回默认值。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_bool
            assert _cfg_bool("NONEXISTENT", True) is True
            assert _cfg_bool("NONEXISTENT", False) is False

    def test_returns_config_value(self):
        """返回配置模块中的布尔值。"""
        mock_cfg = MagicMock()
        mock_cfg.FLAG = True
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_bool
            assert _cfg_bool("FLAG", False) is True

    def test_converts_string_true(self):
        """字符串 'true' 应转换为 True。"""
        mock_cfg = MagicMock()
        mock_cfg.STR_TRUE = "true"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_bool
            assert _cfg_bool("STR_TRUE", False) is True

    def test_converts_string_false(self):
        """字符串 'false' 应转换为 False。"""
        mock_cfg = MagicMock()
        mock_cfg.STR_FALSE = "false"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_bool
            assert _cfg_bool("STR_FALSE", True) is False


class TestCfgStr:
    """_cfg_str 函数测试。"""

    def test_returns_default_when_cfg_is_none(self):
        """当 _cfg 为 None 时返回默认值。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_str
            assert _cfg_str("NONEXISTENT", "default") == "default"

    def test_returns_config_value(self):
        """返回配置模块中的字符串值。"""
        mock_cfg = MagicMock()
        mock_cfg.MY_STR = "hello"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_str
            assert _cfg_str("MY_STR", "default") == "hello"

    def test_strips_whitespace(self):
        """应去除首尾空白。"""
        mock_cfg = MagicMock()
        mock_cfg.WS_STR = "  spaced  "
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_str
            assert _cfg_str("WS_STR", "") == "spaced"

    def test_returns_default_for_none_value(self):
        """当配置值为 None 时返回默认值。"""
        mock_cfg = MagicMock()
        mock_cfg.NONE_STR = None
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_str
            assert _cfg_str("NONE_STR", "fallback") == "fallback"


class TestCfgFloat:
    """_cfg_float 函数测试。"""

    def test_returns_default_when_cfg_is_none(self):
        """当 _cfg 为 None 时返回默认值。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_float
            assert _cfg_float("NONEXISTENT", 3.14) == 3.14

    def test_returns_config_value(self):
        """返回配置模块中的浮点值。"""
        mock_cfg = MagicMock()
        mock_cfg.RATE = 0.5
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_float
            assert _cfg_float("RATE", 1.0) == 0.5

    def test_converts_string_to_float(self):
        """字符串数字应正确转换。"""
        mock_cfg = MagicMock()
        mock_cfg.STR_FLOAT = "2.718"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_float
            assert _cfg_float("STR_FLOAT", 0.0) == 2.718

    def test_returns_default_on_invalid_string(self):
        """无效字符串返回默认值。"""
        mock_cfg = MagicMock()
        mock_cfg.BAD_FLOAT = "not_a_float"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_float
            assert _cfg_float("BAD_FLOAT", 9.99) == 9.99


class TestCfgDict:
    """_cfg_dict 函数测试。"""

    def test_returns_default_when_cfg_is_none(self):
        """当 _cfg 为 None 时返回默认字典。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_dict
            assert _cfg_dict("NONEXISTENT") == {}

    def test_returns_config_value(self):
        """返回配置模块中的字典值。"""
        mock_cfg = MagicMock()
        mock_cfg.MY_DICT = {"key": "value"}
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_dict
            assert _cfg_dict("MY_DICT") == {"key": "value"}

    def test_returns_default_for_non_dict(self):
        """当配置值不是字典时返回默认值。"""
        mock_cfg = MagicMock()
        mock_cfg.NOT_DICT = "string_value"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_dict
            assert _cfg_dict("NOT_DICT", {"default": True}) == {"default": True}

    def test_returns_empty_dict_when_no_default(self):
        """无默认参数时返回空字典。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_dict
            assert _cfg_dict("NONEXISTENT") == {}


class TestCfgTuple:
    """_cfg_tuple 函数测试。"""

    def test_returns_default_when_cfg_is_none(self):
        """当 _cfg 为 None 时返回默认元组。"""
        with patch("postman_api_tester.report_server_config._cfg", None):
            from postman_api_tester.report_server_config import _cfg_tuple
            assert _cfg_tuple("NONEXISTENT") == ()

    def test_converts_list_to_tuple(self):
        """列表应转换为元组。"""
        mock_cfg = MagicMock()
        mock_cfg.MY_LIST = ["a", "b", "c"]
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_tuple
            assert _cfg_tuple("MY_LIST") == ("a", "b", "c")

    def test_parses_comma_separated_string(self):
        """逗号分隔字符串应解析为元组。"""
        mock_cfg = MagicMock()
        mock_cfg.CSV = "x,y,z"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_tuple
            assert _cfg_tuple("CSV") == ("x", "y", "z")

    def test_strips_whitespace_from_csv(self):
        """CSV 解析应去除空白。"""
        mock_cfg = MagicMock()
        mock_cfg.CSV_WS = " a , b , c "
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_tuple
            assert _cfg_tuple("CSV_WS") == ("a", "b", "c")

    def test_skips_empty_items(self):
        """空项应被跳过。"""
        mock_cfg = MagicMock()
        mock_cfg.CSV_EMPTY = "a,,b,  ,c"
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_tuple
            assert _cfg_tuple("CSV_EMPTY") == ("a", "b", "c")

    def test_returns_default_for_non_iterable(self):
        """非可迭代值返回默认元组。"""
        mock_cfg = MagicMock()
        mock_cfg.NOT_ITER = 12345
        with patch("postman_api_tester.report_server_config._cfg", mock_cfg):
            from postman_api_tester.report_server_config import _cfg_tuple
            assert _cfg_tuple("NOT_ITER", ("default",)) == ("default",)


class TestNormalizeEnvironments:
    """_normalize_environments 函数测试。"""

    def test_empty_dict(self):
        """空字典返回空结果。"""
        from postman_api_tester.report_server_config import _normalize_environments
        assert _normalize_environments({}) == {}

    def test_none_input(self):
        """None 输入返回空字典。"""
        from postman_api_tester.report_server_config import _normalize_environments
        assert _normalize_environments(None) == {}

    def test_non_dict_input(self):
        """非字典输入返回空字典。"""
        from postman_api_tester.report_server_config import _normalize_environments
        assert _normalize_environments("string") == {}
        assert _normalize_environments([1, 2, 3]) == {}

    def test_valid_environment(self):
        """有效环境配置应正确规范化。"""
        from postman_api_tester.report_server_config import _normalize_environments
        raw = {
            "production": {
                "base_url": "https://api.example.com",
                "token": "abc123",
            }
        }
        result = _normalize_environments(raw)
        assert result == {
            "production": {
                "base_url": "https://api.example.com",
                "token": "abc123",
            }
        }

    def test_strips_whitespace(self):
        """应去除 base_url 和 token 的空白。"""
        from postman_api_tester.report_server_config import _normalize_environments
        raw = {
            "staging": {
                "base_url": "  https://staging.example.com  ",
                "token": "  xyz789  ",
            }
        }
        result = _normalize_environments(raw)
        assert result["staging"]["base_url"] == "https://staging.example.com"
        assert result["staging"]["token"] == "xyz789"

    def test_handles_missing_fields(self):
        """缺少字段时应使用空字符串。"""
        from postman_api_tester.report_server_config import _normalize_environments
        raw = {
            "dev": {
                "base_url": "http://localhost",
            }
        }
        result = _normalize_environments(raw)
        assert result["dev"]["base_url"] == "http://localhost"
        assert result["dev"]["token"] == ""

    def test_skips_non_dict_values(self):
        """非字典值的环境应被跳过。"""
        from postman_api_tester.report_server_config import _normalize_environments
        raw = {
            "valid": {"base_url": "http://valid", "token": "t1"},
            "invalid": "not_a_dict",
            "also_invalid": 123,
        }
        result = _normalize_environments(raw)
        assert len(result) == 1
        assert "valid" in result

    def test_multiple_environments(self):
        """多个环境应全部保留。"""
        from postman_api_tester.report_server_config import _normalize_environments
        raw = {
            "dev": {"base_url": "http://dev", "token": "d"},
            "staging": {"base_url": "http://staging", "token": "s"},
            "prod": {"base_url": "http://prod", "token": "p"},
        }
        result = _normalize_environments(raw)
        assert len(result) == 3
        assert set(result.keys()) == {"dev", "staging", "prod"}


class TestRuntimeConstants:
    """运行时配置常量测试。"""

    def test_results_per_page_defaults(self):
        """分页默认值应在合理范围内。"""
        from postman_api_tester.report_server_config import (
            RUN_RESULTS_PER_PAGE_DEFAULT,
            RUN_RESULTS_PER_PAGE_MIN,
            RUN_RESULTS_PER_PAGE_MAX,
        )
        assert RUN_RESULTS_PER_PAGE_MIN <= RUN_RESULTS_PER_PAGE_DEFAULT <= RUN_RESULTS_PER_PAGE_MAX
        assert RUN_RESULTS_PER_PAGE_MIN >= 1
        assert RUN_RESULTS_PER_PAGE_MAX <= 1000

    def test_report_view_page_size_defaults(self):
        """报告视图分页默认值应在合理范围内。"""
        from postman_api_tester.report_server_config import (
            REPORT_VIEW_PAGE_SIZE_DEFAULT,
            REPORT_VIEW_PAGE_SIZE_MIN,
            REPORT_VIEW_PAGE_SIZE_MAX,
        )
        assert REPORT_VIEW_PAGE_SIZE_MIN <= REPORT_VIEW_PAGE_SIZE_DEFAULT <= REPORT_VIEW_PAGE_SIZE_MAX

    def test_export_scope_is_valid(self):
        """导出范围应为有效值。"""
        from postman_api_tester.report_server_config import REPORT_EXPORT_DEFAULT_SCOPE
        assert REPORT_EXPORT_DEFAULT_SCOPE in {"full", "report_only"}

    def test_export_channel_mode_is_valid(self):
        """导出通道模式应为有效值。"""
        from postman_api_tester.report_server_config import REPORT_EXPORT_CHANNEL_MODE
        assert REPORT_EXPORT_CHANNEL_MODE in {"auto", "legacy", "stream"}

    def test_stream_threshold_is_positive(self):
        """流式导出阈值应为正数。"""
        from postman_api_tester.report_server_config import REPORT_EXPORT_STREAM_THRESHOLD
        assert REPORT_EXPORT_STREAM_THRESHOLD >= 1

    def test_proxy_allowed_hosts_is_tuple(self):
        """PROXY_ALLOWED_HOSTS 应为元组。"""
        from postman_api_tester.report_server_config import PROXY_ALLOWED_HOSTS
        assert isinstance(PROXY_ALLOWED_HOSTS, tuple)

    def test_log_alert_thresholds_are_non_negative(self):
        """日志告警阈值应为非负数。"""
        from postman_api_tester.report_server_config import (
            LOG_ALERT_ERROR_WINDOW_SECONDS,
            LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN,
        )
        assert LOG_ALERT_ERROR_WINDOW_SECONDS >= 60
        assert LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN >= 0.0

    def test_quality_score_penalties_are_non_negative(self):
        """质量评分扣减值应为非负数。"""
        from postman_api_tester.report_server_config import (
            QUALITY_SCORE_FAILED_PENALTY,
            QUALITY_SCORE_ERROR_PENALTY,
            QUALITY_SCORE_SLOW_PENALTY,
            QUALITY_SCORE_ASSERTION_MISSING_PENALTY,
        )
        assert QUALITY_SCORE_FAILED_PENALTY >= 0
        assert QUALITY_SCORE_ERROR_PENALTY >= 0
        assert QUALITY_SCORE_SLOW_PENALTY >= 0
        assert QUALITY_SCORE_ASSERTION_MISSING_PENALTY >= 0

    def test_report_scan_exclude_dirs_is_list(self):
        """报告扫描排除目录应为列表。"""
        from postman_api_tester.report_server_config import REPORT_SCAN_EXCLUDE_DIRS
        assert isinstance(REPORT_SCAN_EXCLUDE_DIRS, list)
        assert "old" in REPORT_SCAN_EXCLUDE_DIRS

    def test_success_codes_set_is_frozenset(self):
        """成功错误码集合应为 frozenset。"""
        from postman_api_tester.report_server_config import SUCCESS_ERR_CODES_SET
        assert isinstance(SUCCESS_ERR_CODES_SET, frozenset)

    def test_success_messages_set_is_frozenset(self):
        """成功消息集合应为 frozenset。"""
        from postman_api_tester.report_server_config import SUCCESS_MESSAGES_SET
        assert isinstance(SUCCESS_MESSAGES_SET, frozenset)
        assert "success" in SUCCESS_MESSAGES_SET
