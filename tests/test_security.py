"""security 工具函数单元测试。"""

from postman_api_tester.utils.security import (
    DEFAULT_SENSITIVE_HEADERS,
    is_safe_url,
    sanitize_headers,
    strip_auth_headers,
    strip_sensitive_headers,
)


class TestSanitizeHeaders:
    """sanitize_headers 测试。"""

    def test_masks_sensitive_headers(self) -> None:
        """敏感头被替换为 ***。"""
        headers = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
        }
        result = sanitize_headers(headers)
        assert result["Authorization"] == "***"
        assert result["Content-Type"] == "application/json"

    def test_masks_cookie(self) -> None:
        """Cookie 头被替换。"""
        headers = {"Cookie": "session=abc123", "Accept": "text/html"}
        result = sanitize_headers(headers)
        assert result["Cookie"] == "***"
        assert result["Accept"] == "text/html"

    def test_case_insensitive(self) -> None:
        """大小写不敏感。"""
        headers = {"AUTHORIZATION": "Bearer token", "content-type": "text/plain"}
        result = sanitize_headers(headers)
        assert result["AUTHORIZATION"] == "***"
        assert result["content-type"] == "text/plain"

    def test_custom_mask(self) -> None:
        """自定义掩码。"""
        headers = {"Authorization": "Bearer token"}
        result = sanitize_headers(headers, mask="[REDACTED]")
        assert result["Authorization"] == "[REDACTED]"

    def test_empty_headers(self) -> None:
        """空字典返回空字典。"""
        assert sanitize_headers({}) == {}

    def test_none_headers(self) -> None:
        """None 返回空字典。"""
        assert sanitize_headers(None) == {}  # type: ignore[arg-type]

    def test_preserves_key_case(self) -> None:
        """保留原始 key 大小写。"""
        headers = {"Api-Key": "secret123"}
        result = sanitize_headers(headers)
        assert "Api-Key" in result
        assert result["Api-Key"] == "***"

    def test_all_default_sensitive_headers_masked(self) -> None:
        """所有默认敏感头都被掩码。"""
        headers = {h: "value" for h in DEFAULT_SENSITIVE_HEADERS}
        result = sanitize_headers(headers)
        for key in result:
            assert result[key] == "***", f"{key} should be masked"


class TestStripSensitiveHeaders:
    """strip_sensitive_headers 测试。"""

    def test_removes_sensitive_headers(self) -> None:
        """敏感头被移除。"""
        headers = {"Authorization": "Bearer token", "Content-Type": "application/json"}
        result = strip_sensitive_headers(headers)
        assert "Authorization" not in result
        assert result["Content-Type"] == "application/json"

    def test_removes_cookie(self) -> None:
        """Cookie 被移除。"""
        headers = {"Cookie": "session=abc", "Accept": "*/*"}
        result = strip_sensitive_headers(headers)
        assert "Cookie" not in result
        assert result["Accept"] == "*/*"

    def test_case_insensitive(self) -> None:
        """大小写不敏感。"""
        headers = {"authorization": "Bearer token", "X-TOKEN": "xyz"}
        result = strip_sensitive_headers(headers)
        assert "authorization" not in result
        assert "X-TOKEN" not in result

    def test_empty_headers(self) -> None:
        """空字典返回空字典。"""
        assert strip_sensitive_headers({}) == {}

    def test_none_headers(self) -> None:
        """None 返回空字典。"""
        assert strip_sensitive_headers(None) == {}  # type: ignore[arg-type]

    def test_no_sensitive_headers(self) -> None:
        """无敏感头时原样返回。"""
        headers = {"Content-Type": "application/json", "Accept": "text/html"}
        result = strip_sensitive_headers(headers)
        assert result == headers


class TestStripAuthHeaders:
    """strip_auth_headers 测试。"""

    def test_is_alias_for_strip_sensitive(self) -> None:
        """strip_auth_headers 是 strip_sensitive_headers 的别名。"""
        headers = {"Authorization": "Bearer token", "Content-Type": "application/json"}
        assert strip_auth_headers(headers) == strip_sensitive_headers(headers)

    def test_removes_auth(self) -> None:
        """移除认证头。"""
        headers = {"Authorization": "Bearer token"}
        result = strip_auth_headers(headers)
        assert "Authorization" not in result


class TestIsSafeUrl:
    """is_safe_url SSRF 防护测试。"""

    def test_public_urls_are_safe(self) -> None:
        """公网地址应允许。"""
        assert is_safe_url("https://example.com") is True
        assert is_safe_url("https://api.github.com") is True
        assert is_safe_url("http://www.google.com") is True
        assert is_safe_url("https://subdomain.example.org/path?query=1") is True

    def test_localhost_is_unsafe(self) -> None:
        """localhost 应禁止。"""
        assert is_safe_url("http://localhost") is False
        assert is_safe_url("http://localhost:5000") is False
        assert is_safe_url("https://localhost/api") is False

    def test_loopback_ip_is_unsafe(self) -> None:
        """127.0.0.1 应禁止。"""
        assert is_safe_url("http://127.0.0.1") is False
        assert is_safe_url("http://127.0.0.1:5000") is False
        assert is_safe_url("https://127.0.0.1/api") is False

    def test_private_ip_10_is_unsafe(self) -> None:
        """10.x.x.x 私有地址应禁止。"""
        assert is_safe_url("http://10.0.0.1") is False
        assert is_safe_url("http://10.50.11.120:9101") is False
        assert is_safe_url("https://10.255.255.255") is False

    def test_private_ip_172_is_unsafe(self) -> None:
        """172.16-31.x.x 私有地址应禁止。"""
        assert is_safe_url("http://172.16.0.1") is False
        assert is_safe_url("http://172.31.255.255") is False
        # 172.32.x.x 不在私有范围，应允许
        assert is_safe_url("http://172.32.0.1") is True

    def test_private_ip_192_is_unsafe(self) -> None:
        """192.168.x.x 私有地址应禁止。"""
        assert is_safe_url("http://192.168.1.1") is False
        assert is_safe_url("http://192.168.0.1:8080") is False
        assert is_safe_url("https://192.168.255.255") is False

    def test_zero_ip_is_unsafe(self) -> None:
        """0.0.0.0 应禁止。"""
        assert is_safe_url("http://0.0.0.0") is False
        assert is_safe_url("http://0.0.0.0:5000") is False

    def test_ipv6_loopback_is_unsafe(self) -> None:
        """IPv6 回环地址应禁止。"""
        assert is_safe_url("http://[::1]") is False
        assert is_safe_url("http://[::1]:5000") is False

    def test_invalid_url_is_unsafe(self) -> None:
        """无效 URL 应禁止。"""
        assert is_safe_url("") is False
        assert is_safe_url("not-a-url") is False
        assert (
            is_safe_url("ftp://example.com") is True
        )  # ftp 协议允许，但不在 http/https 范围

    def test_url_without_hostname_is_unsafe(self) -> None:
        """无主机名的 URL 应禁止。"""
        assert is_safe_url("http://") is False
        assert is_safe_url("https:///path") is False
