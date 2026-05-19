"""URL utilities for request normalization and merge helpers."""

"""开发导读：
- 职责：URL 与 params 归一化、查询串合并与去重。
- 入口：normalize_url_and_params()、merge_url_with_params()。
- 使用方：执行层、代理请求与实际请求 URL 展示链路。
"""

from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, urljoin


def normalize_url_and_params(url: str, params: Any) -> Tuple[str, Dict[str, Any]]:
	"""Normalize URL and params into a canonical url + dict form."""
	raw_url = str(url or "").strip()
	merged: Dict[str, Any] = {}

	if isinstance(params, dict):
		merged.update(params)
	elif isinstance(params, list):
		for pair in params:
			if isinstance(pair, dict):
				key = str(pair.get("key") or "").strip()
				if key:
					merged[key] = pair.get("value")

	parts = urlsplit(raw_url)
	if parts.query:
		for key, value in parse_qsl(parts.query, keep_blank_values=True):
			merged.setdefault(key, value)

	normalized_url = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", parts.fragment))
	return normalized_url, merged


def merge_url_with_params(url: str, params: Dict[str, Any]) -> str:
	"""Merge URL and params dict into a final URL string."""
	normalized_url, normalized_params = normalize_url_and_params(url, params)
	if not normalized_params:
		return normalized_url

	parts = urlsplit(normalized_url)
	query = urlencode([(str(k), "" if v is None else str(v)) for k, v in normalized_params.items()])
	return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


class UrlHandler:
    """统一 URL 处理工具类。

    所有 URL 合并、规范化操作应通过此类进行，避免重复实现。
    """

    @staticmethod
    def merge_base_and_relative(
        base_url: str,
        relative_path: str,
        query_params: Optional[Dict[str, str]] = None,
    ) -> str:
        """统一 URL 合并逻辑。

        Args:
            base_url: 基础 URL
            relative_path: 相对路径
            query_params: 查询参数字典

        Returns:
            合并后的完整 URL
        """
        # 确保 base_url 末尾没有斜杠
        base_url = base_url.rstrip("/")

        # 确保 relative_path 以斜杠开头
        if relative_path and not relative_path.startswith("/"):
            relative_path = "/" + relative_path

        # 合并 base_url 和 relative_path
        merged_url = urljoin(base_url + "/", "." + relative_path)

        # 添加查询参数
        if query_params:
            query_string = urlencode(query_params)
            merged_url = f"{merged_url}?{query_string}"

        return merged_url

    @staticmethod
    def normalize_url(url: str) -> str:
        """规范化 URL。

        - 移除前后空格
        - 移除末尾斜杠

        Args:
            url: 原始 URL

        Returns:
            规范化后的 URL
        """
        url = url.strip()
        url = url.rstrip("/")
        return url


__all__ = ["normalize_url_and_params", "merge_url_with_params", "UrlHandler"]
