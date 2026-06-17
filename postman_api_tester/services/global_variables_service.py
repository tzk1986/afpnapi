"""全局变量持久化服务。

提供 CRUD 操作，读写 ``GLOBAL_VARIABLES_FILE`` 配置的 JSON 文件。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_COUNT = 1000


def _resolve_path(config_path: str) -> Path:
    """解析并验证变量文件路径。"""
    p = Path(config_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def read_variables(file_path: str, max_count: int = DEFAULT_MAX_COUNT) -> Dict[str, Any]:
    """读取全局变量文件，返回 {version, updated_at, variables, count}。"""
    p = _resolve_path(file_path)
    if not p.exists():
        return {"version": 1, "updated_at": "", "variables": {}, "count": 0}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        variables = raw.get("variables", {})
        if not isinstance(variables, dict):
            variables = {}
        return {
            "version": raw.get("version", 1),
            "updated_at": raw.get("updated_at", ""),
            "variables": variables,
            "count": len(variables),
        }
    except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        logger.warning("全局变量文件读取失败: %s (%s)", file_path, exc)
        return {"version": 1, "updated_at": "", "variables": {}, "count": 0}


def write_variables(
    file_path: str,
    variables: Dict[str, str],
    max_count: int = DEFAULT_MAX_COUNT,
) -> Dict[str, Any]:
    """写入全局变量文件，返回 {count, truncated}。"""
    p = _resolve_path(file_path)
    truncated = False
    if len(variables) > max_count:
        variables = dict(list(variables.items())[:max_count])
        truncated = True
    data = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "variables": variables,
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"count": len(variables), "truncated": truncated}
    except OSError as exc:
        logger.error("全局变量文件写入失败: %s (%s)", file_path, exc)
        raise


def set_variable(file_path: str, key: str, value: str, max_count: int = DEFAULT_MAX_COUNT) -> Dict[str, Any]:
    """设置单个变量（合并写入）。"""
    current = read_variables(file_path, max_count)
    current["variables"][key] = value
    return write_variables(file_path, current["variables"], max_count)


def delete_variable(file_path: str, key: str) -> bool:
    """删除单个变量。返回是否实际删除。"""
    current = read_variables(file_path)
    if key not in current["variables"]:
        return False
    del current["variables"][key]
    write_variables(file_path, current["variables"])
    return True


def clear_variables(file_path: str) -> None:
    """清空所有变量。"""
    write_variables(file_path, {})


def mask_value(value: str) -> str:
    """对变量值进行脱敏展示（保留首尾各 2 字符）。"""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
