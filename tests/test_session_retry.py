"""请求重试机制测试。"""

from unittest.mock import patch
from postman_api_tester.session import create_shared_session


class TestRequestRetry:
    """请求重试功能测试。"""

    def test_retry_disabled_by_default(self):
        """默认禁用重试时，session 不应配置重试适配器。"""
        with patch("postman_api_tester.config.ENABLE_REQUEST_RETRY", False):
            session = create_shared_session()
            # 检查是否没有挂载重试适配器
            # requests.Session 默认使用 HTTPAdapter，我们检查是否是自定义的
            adapter = session.get_adapter("http://example.com")
            # 默认适配器的 max_retries.total 为 0（禁用重试）
            assert adapter.max_retries.total == 0

    def test_retry_enabled_configures_adapter(self):
        """启用重试时，session 应配置重试适配器。"""
        with patch("postman_api_tester.config.ENABLE_REQUEST_RETRY", True), patch(
            "postman_api_tester.config.REQUEST_RETRY_TOTAL", 3
        ), patch("postman_api_tester.config.REQUEST_RETRY_BACKOFF_FACTOR", 1.0), patch(
            "postman_api_tester.config.REQUEST_RETRY_STATUS_FORCELIST",
            (429, 500, 502, 503, 504),
        ):
            session = create_shared_session()
            adapter = session.get_adapter("http://example.com")
            # 应该配置了重试
            assert hasattr(adapter, "max_retries")
            assert adapter.max_retries.total == 3

    def test_retry_with_custom_status_codes(self):
        """自定义重试状态码应生效。"""
        custom_status = (500, 503)
        with patch("postman_api_tester.config.ENABLE_REQUEST_RETRY", True), patch(
            "postman_api_tester.config.REQUEST_RETRY_TOTAL", 2
        ), patch("postman_api_tester.config.REQUEST_RETRY_BACKOFF_FACTOR", 0.5), patch(
            "postman_api_tester.config.REQUEST_RETRY_STATUS_FORCELIST", custom_status
        ):
            session = create_shared_session()
            adapter = session.get_adapter("http://example.com")
            assert adapter.max_retries.status_forcelist == custom_status

    def test_retry_config_error_fallback(self):
        """配置读取失败时应降级为默认行为。"""
        # 模拟配置模块不存在
        with patch.dict("sys.modules", {"postman_api_tester.config": None}):
            session = create_shared_session()
            # 应该正常创建 session，不配置重试
            assert session is not None

    def test_retry_backoff_factor_validation(self):
        """退避因子应为非负数。"""
        # config.py 在导入时已验证并处理为 max(0.0, value)
        # 这里测试 session.py 能正确处理配置值
        with patch("postman_api_tester.config.ENABLE_REQUEST_RETRY", True), patch(
            "postman_api_tester.config.REQUEST_RETRY_TOTAL", 3
        ), patch("postman_api_tester.config.REQUEST_RETRY_BACKOFF_FACTOR", 0.0), patch(
            "postman_api_tester.config.REQUEST_RETRY_STATUS_FORCELIST", (500,)
        ):
            # 0.0 是合法值，应该能正常创建
            session = create_shared_session()
            adapter = session.get_adapter("http://example.com")
            assert adapter.max_retries.backoff_factor >= 0.0

    def test_retry_allowed_methods(self):
        """重试应覆盖常用 HTTP 方法。"""
        with patch("postman_api_tester.config.ENABLE_REQUEST_RETRY", True), patch(
            "postman_api_tester.config.REQUEST_RETRY_TOTAL", 1
        ), patch("postman_api_tester.config.REQUEST_RETRY_BACKOFF_FACTOR", 1.0), patch(
            "postman_api_tester.config.REQUEST_RETRY_STATUS_FORCELIST", (500,)
        ):
            session = create_shared_session()
            adapter = session.get_adapter("http://example.com")
            allowed = adapter.max_retries.allowed_methods
            # 应该包含常见方法
            assert "GET" in allowed
            assert "POST" in allowed
            assert "PUT" in allowed
            assert "DELETE" in allowed
