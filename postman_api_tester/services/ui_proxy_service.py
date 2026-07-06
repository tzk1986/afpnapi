"""UI 测试反向代理服务。

获取外部 URL 的 HTML 内容，改写所有资源引用指向代理端点，
并注入录制器脚本，使目标页面可在 iframe 中安全展示和交互。
"""

import logging
import re
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

PROXY_PREFIX = "/ui-testing/proxy"
RESOURCE_PROXY_PREFIX = "/ui-testing/proxy-resource"

_SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav",
    ".pdf", ".zip", ".tar", ".gz",
}

_CONTENT_TYPE_MAP = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


class UiProxyService:
    """反向代理：获取外部 URL 并改写 HTML 以支持 iframe 嵌入。"""

    REQUEST_TIMEOUT = 15
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB

    @classmethod
    def fetch_and_rewrite(cls, url: str) -> Tuple[str, int, Dict[str, str]]:
        """获取外部 URL 并改写 HTML。

        Args:
            url: 目标 URL

        Returns:
            (body, status_code, response_headers)

        Raises:
            requests.RequestException: 网络请求失败
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"仅支持 http/https 协议: {url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        resp = requests.get(url, headers=headers, timeout=cls.REQUEST_TIMEOUT, allow_redirects=True)

        content_type = resp.headers.get("Content-Type", "")
        is_html = "text/html" in content_type or "application/xhtml" in content_type

        response_headers: Dict[str, str] = {}
        for key in ("Content-Type", "Cache-Control", "ETag"):
            if key in resp.headers:
                response_headers[key] = resp.headers[key]

        response_headers.pop("X-Frame-Options", None)
        response_headers.pop("Content-Security-Policy", None)

        if is_html:
            body = cls.rewrite_html(resp.text, resp.url)
            response_headers["Content-Type"] = "text/html; charset=utf-8"
        else:
            body = resp.text if isinstance(resp.text, str) else resp.content.decode("utf-8", errors="replace")

        return body, resp.status_code, response_headers

    @classmethod
    def fetch_resource(
        cls,
        url: str,
        method: str = "GET",
        req_headers: Optional[Dict[str, str]] = None,
        req_body: Optional[bytes] = None,
    ) -> Tuple[bytes, int, Dict[str, str]]:
        """获取子资源（CSS/JS/图片/API），不改写内容。

        Args:
            url: 目标 URL
            method: HTTP 方法（GET/POST/PUT/DELETE 等）
            req_headers: 原始请求头（转发 Content-Type 等）
            req_body: 原始请求体

        Returns:
            (body_bytes, status_code, headers)
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"仅支持 http/https 协议: {url}")

        headers: Dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        }
        if req_headers:
            for key in ("Content-Type", "Authorization", "X-Requested-With", "Accept", "Accept-Language"):
                if key in req_headers:
                    headers[key] = req_headers[key]

        resp = requests.request(
            method, url, headers=headers, data=req_body,
            timeout=cls.REQUEST_TIMEOUT, allow_redirects=True,
        )

        response_headers: Dict[str, str] = {}
        for key in ("Content-Type", "Cache-Control", "ETag"):
            if key in resp.headers:
                response_headers[key] = resp.headers[key]

        return resp.content, resp.status_code, response_headers

    @staticmethod
    def rewrite_html(html: str, base_url: str) -> str:
        """改写 HTML 中的所有 URL 引用。

        处理：
        - 添加/改写 <base href>
        - 改写 href, src, action, poster, data 属性
        - 改写内联 style 中的 url()
        - 改写 <style> 标签中的 url()
        - 注入录制器脚本
        """
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        result = html

        result = UiProxyService._inject_early_script(result, origin)
        result = UiProxyService._rewrite_base_tag(result, base_url)
        result = UiProxyService._rewrite_attr_urls(result, base_url, origin)
        result = UiProxyService._rewrite_inline_style_urls(result, base_url, origin)
        result = UiProxyService._rewrite_style_tag_urls(result, base_url, origin)
        result = UiProxyService._remove_frame_busting(result)
        result = UiProxyService._inject_recorder_script(result, origin)

        return result

    @staticmethod
    def to_proxy_url(url: str) -> str:
        """将原始 URL 转为代理 URL。"""
        return f"{PROXY_PREFIX}?url={quote(url, safe='')}"

    @staticmethod
    def to_resource_proxy_url(url: str) -> str:
        """将资源 URL 转为资源代理 URL。"""
        return f"{RESOURCE_PROXY_PREFIX}?url={quote(url, safe='')}"

    @staticmethod
    def _resolve_url(href: str, base_url: str) -> Optional[str]:
        """将相对 URL 解析为绝对 URL。"""
        if not href or href.startswith(("javascript:", "data:", "blob:", "#", "mailto:", "tel:")):
            return None
        if href.startswith("//"):
            parsed_base = urlparse(base_url)
            return f"{parsed_base.scheme}:{href}"
        return urljoin(base_url, href)

    @staticmethod
    def _rewrite_base_tag(html: str, base_url: str) -> str:
        """移除或替换 <base href> 标签。"""
        html = re.sub(r'<base\s+[^>]*>', '', html, flags=re.IGNORECASE)
        return html

    @staticmethod
    def _outside_scripts(html: str, transform: Callable[[str], str]) -> str:
        """对 <script> 标签外部的 HTML 内容应用变换，保持脚本内容不变。"""
        pattern = re.compile(r'(<script\b[^>]*>)(.*?)(</script>)', re.IGNORECASE | re.DOTALL)
        parts = pattern.split(html)
        result = []
        for i, part in enumerate(parts):
            if i % 4 == 0:
                result.append(transform(part))
            else:
                result.append(part)
        return "".join(result)

    @staticmethod
    def _rewrite_attr_urls(html: str, base_url: str, origin: str) -> str:
        """改写 HTML 属性中的 URL 引用。"""
        attr_patterns = [
            (r'(<(?:a|area)\s[^>]*?)href\s*=\s*"([^"]*)"', "href", True),
            (r"(<(?:a|area)\s[^>]*?)href\s*=\s*'([^']*)'", "href", True),
            (r'(<(?:img|script|video|audio|source|embed|iframe|track)\s[^>]*?)src\s*=\s*"([^"]*)"', "src", False),
            (r"(<(?:img|script|video|audio|source|embed|iframe|track)\s[^>]*?)src\s*=\s*'([^']*)'", "src", False),
            (r'(<link\s[^>]*?)href\s*=\s*"([^"]*)"', "href", False),
            (r"(<link\s[^>]*?)href\s*=\s*'([^']*)'", "href", False),
            (r'(<form\s[^>]*?)action\s*=\s*"([^"]*)"', "action", True),
            (r"(<form\s[^>]*?)action\s*=\s*'([^']*)'", "action", True),
            (r'(<(?:object|video)\s[^>]*?)data\s*=\s*"([^"]*)"', "data", False),
            (r'(<(?:video|img)\s[^>]*?)poster\s*=\s*"([^"]*)"', "poster", False),
        ]

        def _rewrite_outside(outside: str) -> str:
            for pattern, attr_name, is_page_url in attr_patterns:
                def _replace_attr(match: re.Match) -> str:
                    prefix = match.group(1)
                    url_value = match.group(2)
                    resolved = UiProxyService._resolve_url(url_value, base_url)
                    if resolved is None:
                        return match.group(0)
                    if is_page_url:
                        proxy_url = UiProxyService.to_proxy_url(resolved)
                    else:
                        proxy_url = UiProxyService.to_resource_proxy_url(resolved)
                    return f'{prefix}{attr_name}="{proxy_url}"'
                outside = re.sub(pattern, _replace_attr, outside, flags=re.IGNORECASE)
            return outside

        return UiProxyService._outside_scripts(html, _rewrite_outside)

    @staticmethod
    def _rewrite_inline_style_urls(html: str, base_url: str, origin: str) -> str:
        """改写内联 style 属性中的 url()。"""
        def _replace_style_attr(match: re.Match) -> str:
            prefix = match.group(1)
            style_content = match.group(2)
            rewritten = UiProxyService._rewrite_css_urls(style_content, base_url, origin)
            return f'{prefix}"{rewritten}"'

        def _rewrite_outside(outside: str) -> str:
            return re.sub(
                r'(style\s*=\s*)"((?:[^"\\]|\\.)*)"',
                _replace_style_attr,
                outside,
                flags=re.IGNORECASE,
            )

        return UiProxyService._outside_scripts(html, _rewrite_outside)

    @staticmethod
    def _rewrite_style_tag_urls(html: str, base_url: str, origin: str) -> str:
        """改写 <style> 标签中的 url()。"""
        def _replace_style_tag(match: re.Match) -> str:
            open_tag = match.group(1)
            css_content = match.group(2)
            close_tag = match.group(3)
            rewritten = UiProxyService._rewrite_css_urls(css_content, base_url, origin)
            return f"{open_tag}{rewritten}{close_tag}"

        def _rewrite_outside(outside: str) -> str:
            return re.sub(
                r'(<style[^>]*>)(.*?)(</style>)',
                _replace_style_tag,
                outside,
                flags=re.IGNORECASE | re.DOTALL,
            )

        return UiProxyService._outside_scripts(html, _rewrite_outside)

    @staticmethod
    def _rewrite_css_urls(css: str, base_url: str, origin: str) -> str:
        """改写 CSS 中的 url() 引用。"""
        def _replace_css_url(match: re.Match) -> str:
            url_value = match.group(1) or match.group(2)
            if url_value.startswith(("data:", "blob:", "#")):
                return match.group(0)
            resolved = UiProxyService._resolve_url(url_value, base_url)
            if resolved is None:
                return match.group(0)
            proxy_url = UiProxyService.to_resource_proxy_url(resolved)
            return f"url('{proxy_url}')"

        css = re.sub(
            r"""url\(\s*(?:'([^']*)'|"([^"]*)")\s*\)""",
            _replace_css_url,
            css,
        )
        css = re.sub(
            r"""url\(\s*([^'")\s]+)\s*\)""",
            _replace_css_url,
            css,
        )
        return css

    @staticmethod
    def _remove_frame_busting(html: str) -> str:
        """移除常见的 frame-busting 脚本。"""
        patterns = [
            r'if\s*\(\s*top\s*!==?\s*self\s*\)\s*top\.location\s*=\s*self\.location',
            r'if\s*\(\s*window\.top\s*!==?\s*window\s*\)\s*.*?;',
            r'if\s*\(\s*self\s*!=\s*top\s*\)\s*.*?;',
        ]
        for pattern in patterns:
            html = re.sub(pattern, '/* frame-busting removed */', html, flags=re.IGNORECASE)
        return html

    @staticmethod
    def _inject_early_script(html: str, origin: str) -> str:
        """在 <head> 后立即注入早期脚本，拦截动态脚本/资源创建。"""
        early_js = (
            '(function(){'
            'var _T="' + origin + '";'
            'var _F=location.protocol+"//"+location.host;'
            'if(!_T||_T===_F)return;'
            'var _dw=document.write.bind(document);'
            'document.write=function(h){'
            'if(typeof h==="string"){'
            'h=h.split(_F).join(_T);'
            '}'
            'return _dw(h);'
            '};'
            'var _ce=document.createElement.bind(document);'
            'document.createElement=function(t){'
            'var el=_ce(t);'
            'if(t&&t.toLowerCase()==="script"){'
            'var _s=Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype,"src");'
            'if(_s&&_s.set){'
            'var _ss=_s.set;'
            'Object.defineProperty(el,"src",{'
            'set:function(v){'
            'if(typeof v==="string"&&v.indexOf(_F)===0)v=_T+v.substring(_F.length);'
            '_ss.call(this,v);'
            '},'
            'get:function(){return _s.get.call(this);}'
            '});'
            '}'
            '}'
            'return el;'
            '};'
            '})();'
        )
        early_script = f"<script>{early_js}</script>"

        lower = html.lower()
        if "<head>" in lower:
            idx = lower.index("<head>") + len("<head>")
            html = html[:idx] + early_script + html[idx:]
        elif "<html>" in lower:
            idx = lower.index("<html>") + len("<html>")
            html = html[:idx] + early_script + html[idx:]
        else:
            html = early_script + html

        return html

    @staticmethod
    def _inject_recorder_script(html: str, origin: str = "") -> str:
        """在 </body> 前注入录制器脚本。"""
        from postman_api_tester.services.ui_recorder_inject import get_recorder_js

        script_tag = f"<script>\n{get_recorder_js(origin)}\n</script>"

        lower = html.lower()
        if "</body>" in lower:
            idx = lower.index("</body>")
            html = html[:idx] + script_tag + html[idx:]
        elif "</html>" in lower:
            idx = lower.index("</html>")
            html = html[:idx] + script_tag + html[idx:]
        else:
            html += script_tag

        return html
