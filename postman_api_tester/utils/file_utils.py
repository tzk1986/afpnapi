"""File utility implementations for report artifacts."""

"""开发导读：
- 职责：导出文件名安全清洗，防止非法字符与路径穿透风险；JSON 原子写入。
- 入口：sanitize_export_name()、atomic_write_json()。
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional


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

def atomic_write_json(path: Path, data: Any) -> None:
	"""原子写入 JSON 文件：先写临时文件再 os.replace，避免写入中断损坏原文件。"""
	tmp_fd, tmp_str = tempfile.mkstemp(
		dir=str(path.parent), suffix=".tmp", prefix=path.name + "."
	)
	try:
		with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
			json.dump(data, f, indent=2, ensure_ascii=False)
		os.replace(tmp_str, str(path))
	except BaseException:
		try:
			os.unlink(tmp_str)
		except OSError:
			pass
		raise


__all__ = ["atomic_write_json", "safe_report_artifact", "sanitize_export_name"]
