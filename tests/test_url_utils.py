"""URL 处理工具单元测试."""

import pytest
from postman_api_tester.utils.url_utils import UrlHandler


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
