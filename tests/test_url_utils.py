"""URL 处理工具单元测试."""

import pytest
from postman_api_tester.utils.url_utils import (
    UrlHandler,
    normalize_url_and_params,
    merge_url_with_params,
)


class TestUrlHandler:
    """URL 处理测试."""

    def test_merge_base_and_relative_simple(self) -> None:
        """测试简单 URL 合并."""
        result = UrlHandler.merge_base_and_relative(
            "http://localhost:8080",
            "/api/users",
            None
        )
        assert result == "http://localhost:8080/api/users"

    def test_merge_base_and_relative_with_params(self) -> None:
        """测试带查询参数的 URL 合并."""
        result = UrlHandler.merge_base_and_relative(
            "http://localhost:8080",
            "/api/users",
            {"id": "123", "name": "test"}
        )
        assert "http://localhost:8080/api/users?" in result
        assert "id=123" in result
        assert "name=test" in result

    def test_merge_base_and_relative_trailing_slash(self) -> None:
        """测试处理末尾斜杠."""
        result = UrlHandler.merge_base_and_relative(
            "http://localhost:8080/",
            "api/users",
            None
        )
        assert result == "http://localhost:8080/api/users"

    def test_normalize_url(self) -> None:
        """测试 URL 规范化."""
        # 移除多余空格
        result = UrlHandler.normalize_url("  http://localhost:8080/api  ")
        assert result == "http://localhost:8080/api"

        # 移除末尾斜杠
        result = UrlHandler.normalize_url("http://localhost:8080/")
        assert result == "http://localhost:8080"

    def test_normalize_url_empty(self) -> None:
        """测试空 URL 规范化."""
        assert UrlHandler.normalize_url("") == ""
        assert UrlHandler.normalize_url("   ") == ""


class TestNormalizeUrlAndParams:
    """normalize_url_and_params 函数测试."""

    def test_simple_url_no_params(self) -> None:
        """测试简单 URL 无参数."""
        url, params = normalize_url_and_params("http://example.com/api", None)
        assert url == "http://example.com/api"
        assert params == {}

    def test_url_with_query_string(self) -> None:
        """测试 URL 带查询字符串."""
        url, params = normalize_url_and_params("http://example.com/api?key=value", None)
        assert url == "http://example.com/api"
        assert params == {"key": "value"}

    def test_url_with_dict_params(self) -> None:
        """测试 URL 带字典参数."""
        url, params = normalize_url_and_params("http://example.com/api", {"id": "123"})
        assert url == "http://example.com/api"
        assert params == {"id": "123"}

    def test_url_with_list_params(self) -> None:
        """测试 URL 带列表参数."""
        url, params = normalize_url_and_params(
            "http://example.com/api",
            [{"key": "id", "value": "123"}, {"key": "name", "value": "test"}]
        )
        assert params == {"id": "123", "name": "test"}

    def test_url_with_query_and_params(self) -> None:
        """测试 URL 同时带查询字符串和参数."""
        url, params = normalize_url_and_params(
            "http://example.com/api?key1=value1",
            {"key2": "value2"}
        )
        assert params == {"key1": "value1", "key2": "value2"}

    def test_empty_url(self) -> None:
        """测试空 URL."""
        url, params = normalize_url_and_params("", None)
        assert url == "/"
        assert params == {}

    def test_url_with_fragment(self) -> None:
        """测试 URL 带 fragment."""
        url, params = normalize_url_and_params("http://example.com/api#section", None)
        assert "#section" in url


class TestMergeUrlWithParams:
    """merge_url_with_params 函数测试."""

    def test_merge_simple(self) -> None:
        """测试简单合并."""
        result = merge_url_with_params("http://example.com/api", {"key": "value"})
        assert "key=value" in result

    def test_merge_multiple_params(self) -> None:
        """测试多个参数合并."""
        result = merge_url_with_params(
            "http://example.com/api",
            {"id": "123", "name": "test"}
        )
        assert "id=123" in result
        assert "name=test" in result

    def test_merge_with_existing_query(self) -> None:
        """测试与现有查询字符串合并."""
        result = merge_url_with_params(
            "http://example.com/api?existing=yes",
            {"new": "param"}
        )
        assert "existing=yes" in result
        assert "new=param" in result

    def test_merge_empty_params(self) -> None:
        """测试空参数."""
        result = merge_url_with_params("http://example.com/api", {})
        assert result == "http://example.com/api"

    def test_merge_none_value(self) -> None:
        """测试 None 值转换为空字符串."""
        result = merge_url_with_params("http://example.com/api", {"key": None})
        assert "key=" in result
