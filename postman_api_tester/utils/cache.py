"""Cache utility implementations."""

from typing import Any, MutableMapping, Optional


def reset_reports_cache(cache: MutableMapping[str, Any]) -> None:
	cache["data"] = None
	cache["by_name"] = None
	cache["ts"] = 0.0


def invalidate_reports_cache(cache: Optional[MutableMapping[str, Any]] = None) -> None:
	if cache is None:
		return
	reset_reports_cache(cache)

__all__ = ["invalidate_reports_cache"]
