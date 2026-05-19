"""File utility implementations for report artifacts."""

"""开发导读：
- 职责：导出文件名安全清洗，防止非法字符与路径穿透风险。
- 入口：sanitize_export_name()。
"""

import re
from pathlib import Path
from typing import Optional


def sanitize_export_name(name: str) -> str:
	normalized = str(name or "").replace("\\", "/").split("/")[-1]
	normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized).strip(' .')
	return normalized or "collection"


def safe_report_artifact(reports_dir: Path, name: str) -> Optional[Path]:
	normalized = str(name or "").strip().replace("\\", "/")
	if not normalized:
		return None
	normalized = normalized.lstrip("/")
	candidate = (reports_dir / normalized).resolve()
	try:
		candidate.relative_to(reports_dir)
	except ValueError:
		return None
	return candidate

__all__ = ["safe_report_artifact", "sanitize_export_name"]
