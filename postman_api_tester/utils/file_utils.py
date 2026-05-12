"""File utility implementations for report artifacts."""

import re
from pathlib import Path
from typing import Optional


def sanitize_export_name(name: str) -> str:
	normalized = str(name or "").replace("\\", "/").split("/")[-1]
	normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized).strip(' .')
	return normalized or "collection"


def safe_report_artifact(reports_dir: Path, name: str) -> Optional[Path]:
	normalized = Path(str(name or "").strip()).name
	if not normalized:
		return None
	candidate = (reports_dir / normalized).resolve()
	try:
		candidate.relative_to(reports_dir)
	except ValueError:
		return None
	return candidate

__all__ = ["safe_report_artifact", "sanitize_export_name"]
