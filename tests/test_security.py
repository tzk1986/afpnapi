"""security 工具函数单元测试。"""

from postman_api_tester.utils.security import (
    DEFAULT_SENSITIVE_HEADERS,
    sanitize_headers,
    strip_auth_headers,
    strip_sensitive_headers,
)


class TestSanitizeHeaders:
    """sanitize_headers 测试。"""

    def test_masks_sensitive_headers(self) -> None:
        """敏感头被替换为 ***。"""
        headers = {"Authorization": "Bearer token123", "Content-Type": "application/json"}
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
