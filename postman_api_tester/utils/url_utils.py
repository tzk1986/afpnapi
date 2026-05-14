"""URL utilities for request normalization and merge helpers."""

"""开发导读：
- 职责：URL 与 params 归一化、查询串合并与去重。
- 入口：normalize_url_and_params()、merge_url_with_params()。
- 使用方：执行层、代理请求与实际请求 URL 展示链路。
"""

from typing import Any, Dict, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


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


__all__ = ["normalize_url_and_params", "merge_url_with_params"]
