"""全局变量 JSON 存储的底层 I/O 工具函数。

提供 _read_store / _write_store / merge_variables_for_env 等纯函数，
供 core/variable_context.py 和 services/global_variables_service.py 共用。

文件格式（version 2）::

    {
      "version": 2,
      "updated_at": "2026-06-17T10:30:00",
      "shared": {"key": "value"},
      "environments": {"生产环境": {"key": "value"}}
    }

旧格式（version 1）自动迁移：variables 整体移入 shared。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_path(config_path: str) -> Path:
    p = Path(config_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _empty_store() -> dict[str, Any]:
    return {
        "version": 2,
        "updated_at": "",
        "shared": {},
        "env_list": ["默认环境"],
        "environments": {"默认环境": {}},
    }


def _read_store(file_path: str) -> dict[str, Any]:
    """读取原始 JSON store，自动迁移旧格式。"""
    p = _resolve_path(file_path)
    if not p.exists():
        return _empty_store()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("全局变量文件读取失败: %s (%s)", file_path, exc)
        return _empty_store()

    version = raw.get("version", 1) if isinstance(raw, dict) else 1
    if version >= 2 and "shared" in raw:
        envs = raw.get("environments", {})
        if not isinstance(envs, dict):
            envs = {}
        env_list = raw.get("env_list")
        if not isinstance(env_list, list) or len(env_list) == 0:
            env_list = list(envs.keys()) if envs else ["默认环境"]
            if "默认环境" not in env_list:
                env_list.insert(0, "默认环境")
        store: dict[str, Any] = {
            "version": 2,
            "updated_at": raw.get("updated_at", ""),
            "shared": raw.get("shared", {})
            if isinstance(raw.get("shared"), dict)
            else {},
            "env_list": [str(e) for e in env_list],
            "environments": envs,
        }
    else:
        old_vars = raw.get("variables", {}) if isinstance(raw, dict) else {}
        if not isinstance(old_vars, dict):
            old_vars = {}
        store = {
            "version": 2,
            "updated_at": raw.get("updated_at", "") if isinstance(raw, dict) else "",
            "shared": old_vars,
            "env_list": ["默认环境"],
            "environments": {"默认环境": {}},
        }
        _write_store(file_path, store)
    return store


def _write_store(file_path: str, store: dict[str, Any]) -> None:
    """写入 JSON store。"""
    p = _resolve_path(file_path)
    store["version"] = 2
    store["updated_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("全局变量文件写入失败: %s (%s)", file_path, exc)
        raise


def merge_variables_for_env(file_path: str, env_name: str = "") -> dict[str, str]:
    """合并 shared + env 变量（env 优先），用于执行层加载。"""
    store = _read_store(file_path)
    merged: dict[str, str] = {}
    shared = store.get("shared", {})
    if isinstance(shared, dict):
        merged.update(shared)
    if env_name:
        env_vars = store.get("environments", {}).get(env_name, {})
        if isinstance(env_vars, dict):
            merged.update(env_vars)
    return merged
