"""UI 代理服务单元测试。"""

import pytest

from postman_api_tester.services.ui_proxy_service import UiProxyService


class TestToProxyUrl:
    """代理 URL 生成测试。"""

    def test_simple_url(self) -> None:
        result = UiProxyService.to_proxy_url("https://example.com/page")
        assert result.startswith("/ui-testing/proxy?url=")
        assert "example.com" in result

    def test_url_with_query_params(self) -> None:
        result = UiProxyService.to_proxy_url("https://example.com/search?q=test&page=1")
        assert "example.com" in result
        assert "search" in result

    def test_resource_proxy_url(self) -> None:
        result = UiProxyService.to_resource_proxy_url("https://example.com/style.css")
        assert result.startswith("/ui-testing/proxy-resource?url=")


class TestRewriteHtml:
    """HTML 改写测试。"""

    def test_rewrite_anchor_href(self) -> None:
        html = '<a href="/about">About</a>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy?url=" in result
        assert "example.com" in result

    def test_rewrite_img_src(self) -> None:
        html = '<img src="/images/logo.png">'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_rewrite_link_href(self) -> None:
        html = '<link rel="stylesheet" href="/css/style.css">'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_rewrite_form_action(self) -> None:
        html = '<form action="/submit" method="POST"><input type="text"></form>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy?url=" in result

    def test_rewrite_script_src(self) -> None:
        html = '<script src="/js/app.js"></script>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_preserve_data_urls(self) -> None:
        html = '<img src="data:image/png;base64,iVBOR">'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "data:image/png" in result

    def test_preserve_javascript_urls(self) -> None:
        html = '<a href="javascript:void(0)">Click</a>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "javascript:void(0)" in result

    def test_preserve_hash_urls(self) -> None:
        html = '<a href="#section1">Jump</a>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert 'href="#section1"' in result

    def test_inject_recorder_script(self) -> None:
        html = "<html><body><h1>Hello</h1></body></html>"
        result = UiProxyService.rewrite_html(html, "https://example.com")
        assert "<script>" in result
        assert "UIRecorder" in result or "SelectorEngine" in result

    def test_remove_base_tag(self) -> None:
        html = '<base href="/"><a href="/page">Link</a>'
        result = UiProxyService.rewrite_html(html, "https://example.com")
        assert "<base" not in result.lower()

    def test_remove_frame_busting(self) -> None:
        html = '<script>if(top!==self)top.location=self.location;</script><body></body>'
        result = UiProxyService.rewrite_html(html, "https://example.com")
        assert "frame-busting removed" in result

    def test_rewrite_inline_style_url(self) -> None:
        html = '<div style="background-image: url(/bg.png)">Content</div>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_rewrite_style_tag_url(self) -> None:
        html = '<style>.bg { background: url(/img/bg.jpg); }</style>'
        result = UiProxyService.rewrite_html(html, "https://example.com/page")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_resolve_relative_url(self) -> None:
        html = '<a href="subpage">Link</a>'
        result = UiProxyService.rewrite_html(html, "https://example.com/dir/page")
        assert "example.com" in result
        assert "subpage" in result

    def test_resolve_protocol_relative_url(self) -> None:
        html = '<script src="//cdn.example.com/lib.js"></script>'
        result = UiProxyService.rewrite_html(html, "https://example.com")
        assert "cdn.example.com" in result

    def test_rewrite_double_quoted_attrs(self) -> None:
        html = '<a href="/page">Link</a>'
        result = UiProxyService.rewrite_html(html, "https://example.com")
        assert "/ui-testing/proxy?url=" in result

    def test_empty_html(self) -> None:
        result = UiProxyService.rewrite_html("", "https://example.com")
        assert "<script>" in result

    def test_no_body_tag(self) -> None:
        html = "<div>Content</div>"
        result = UiProxyService.rewrite_html(html, "https://example.com")
        assert "<script>" in result


class TestRewriteCssUrls:
    """CSS url() 改写测试。"""

    def test_single_quoted_url(self) -> None:
        css = "background: url('/img/bg.png');"
        result = UiProxyService._rewrite_css_urls(css, "https://example.com", "https://example.com")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_double_quoted_url(self) -> None:
        css = 'background: url("/img/bg.png");'
        result = UiProxyService._rewrite_css_urls(css, "https://example.com", "https://example.com")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_unquoted_url(self) -> None:
        css = "background: url(/img/bg.png);"
        result = UiProxyService._rewrite_css_urls(css, "https://example.com", "https://example.com")
        assert "/ui-testing/proxy-resource?url=" in result

    def test_preserve_data_url(self) -> None:
        css = "background: url('data:image/png;base64,abc');"
        result = UiProxyService._rewrite_css_urls(css, "https://example.com", "https://example.com")
        assert "data:image/png" in result


class TestResolveUrl:
    """URL 解析测试。"""

    def test_absolute_url(self) -> None:
        result = UiProxyService._resolve_url("https://other.com/page", "https://example.com")
        assert result == "https://other.com/page"

    def test_relative_url(self) -> None:
        result = UiProxyService._resolve_url("/about", "https://example.com/page")
        assert result == "https://example.com/about"

    def test_protocol_relative(self) -> None:
        result = UiProxyService._resolve_url("//cdn.example.com/lib.js", "https://example.com")
        assert result == "https://cdn.example.com/lib.js"

    def test_javascript_url(self) -> None:
        result = UiProxyService._resolve_url("javascript:void(0)", "https://example.com")
        assert result is None

    def test_data_url(self) -> None:
        result = UiProxyService._resolve_url("data:image/png;base64,abc", "https://example.com")
        assert result is None

    def test_hash_url(self) -> None:
        result = UiProxyService._resolve_url("#section", "https://example.com")
        assert result is None

    def test_empty_url(self) -> None:
        result = UiProxyService._resolve_url("", "https://example.com")
        assert result is None

    def test_mailto_url(self) -> None:
        result = UiProxyService._resolve_url("mailto:test@example.com", "https://example.com")
        assert result is None
