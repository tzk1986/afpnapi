"""全局变量持久化服务（多环境版）。

提供 CRUD 操作，读写 ``GLOBAL_VARIABLES_FILE`` 配置的 JSON 文件。
支持多环境作用域：shared（全局共享）+ environments（按环境分组）。

文件格式（version 2）::

    {
      "version": 2,
      "updated_at": "2026-06-17T10:30:00",
      "shared": {"key": "value"},
      "environments": {"生产环境": {"key": "value"}}
    }

旧格式（version 1）自动迁移：``variables`` 整体移入 ``shared``。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_MAX_COUNT = 1000


def _resolve_path(config_path: str) -> Path:
    """解析并验证变量文件路径。"""
    p = Path(config_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _empty_store() -> Dict[str, Any]:
    return {"version": 2, "updated_at": "", "shared": {}, "env_list": ["默认环境"], "environments": {"默认环境": {}}}


def _read_store(file_path: str) -> Dict[str, Any]:
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
        store: Dict[str, Any] = {
            "version": 2,
            "updated_at": raw.get("updated_at", ""),
            "shared": raw.get("shared", {}) if isinstance(raw.get("shared"), dict) else {},
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


def _write_store(file_path: str, store: Dict[str, Any]) -> None:
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


def _count_store(store: Dict[str, Any]) -> int:
    total = len(store.get("shared", {}))
    for env_vars in store.get("environments", {}).values():
        if isinstance(env_vars, dict):
            total += len(env_vars)
    return total


# ── 新版多环境 API ──────────────────────────────────────────────────────

def read_all(file_path: str, max_count: int = DEFAULT_MAX_COUNT) -> Dict[str, Any]:
    """读取完整多环境结构，返回 {version, updated_at, shared, env_list, environments, total_count}。"""
    store = _read_store(file_path)
    return {
        "version": store["version"],
        "updated_at": store["updated_at"],
        "shared": dict(store.get("shared", {})),
        "env_list": list(store.get("env_list", [])),
        "environments": {k: dict(v) for k, v in store.get("environments", {}).items() if isinstance(v, dict)},
        "total_count": _count_store(store),
    }


def read_scope(file_path: str, scope: str, env_name: str = "", max_count: int = DEFAULT_MAX_COUNT) -> Dict[str, Any]:
    """读取指定作用域的变量。scope='shared' 或 scope='env'。"""
    store = _read_store(file_path)
    if scope == "env":
        variables = store.get("environments", {}).get(env_name, {})
        if not isinstance(variables, dict):
            variables = {}
    else:
        variables = store.get("shared", {})
        if not isinstance(variables, dict):
            variables = {}
    return {"variables": dict(variables), "count": len(variables)}


def set_variable(
    file_path: str, scope: str, key: str, value: str,
    env_name: str = "", max_count: int = DEFAULT_MAX_COUNT,
) -> Dict[str, Any]:
    """在指定作用域设置单个变量。"""
    store = _read_store(file_path)
    if scope == "env":
        envs = store.setdefault("environments", {})
        if not isinstance(envs.get(env_name), dict):
            envs[env_name] = {}
        envs[env_name][key] = value
        total = len(envs[env_name])
    else:
        shared = store.setdefault("shared", {})
        shared[key] = value
        total = len(shared)
    truncated = False
    if total > max_count:
        if scope == "env":
            items = list(store["environments"][env_name].items())[:max_count]
            store["environments"][env_name] = dict(items)
        else:
            items = list(store["shared"].items())[:max_count]
            store["shared"] = dict(items)
        truncated = True
    _write_store(file_path, store)
    return {"count": min(total, max_count), "truncated": truncated}


def delete_variable(file_path: str, scope: str, key: str, env_name: str = "") -> bool:
    """删除指定作用域的变量。返回是否实际删除。"""
    store = _read_store(file_path)
    if scope == "env":
        env_vars = store.get("environments", {}).get(env_name, {})
        if not isinstance(env_vars, dict) or key not in env_vars:
            return False
        del env_vars[key]
    else:
        shared = store.get("shared", {})
        if not isinstance(shared, dict) or key not in shared:
            return False
        del shared[key]
    _write_store(file_path, store)
    return True


def clear_scope(file_path: str, scope: str, env_name: str = "") -> None:
    """清空指定作用域的变量。"""
    store = _read_store(file_path)
    if scope == "env":
        store.get("environments", {})[env_name] = {}
    else:
        store["shared"] = {}
    _write_store(file_path, store)


# ── 环境列表管理 ──────────────────────────────────────────────────────

def get_env_list(file_path: str) -> List[str]:
    """返回环境名称列表（按顺序）。"""
    store = _read_store(file_path)
    return list(store.get("env_list", []))


def add_env(file_path: str, env_name: str) -> Dict[str, Any]:
    """添加新环境。若已存在则返回 exists=True。"""
    store = _read_store(file_path)
    env_list = store.get("env_list", [])
    if env_name in env_list:
        return {"exists": True, "env_list": env_list}
    env_list.append(env_name)
    store["env_list"] = env_list
    envs = store.get("environments", {})
    if env_name not in envs:
        envs[env_name] = {}
    store["environments"] = envs
    _write_store(file_path, store)
    return {"exists": False, "env_list": env_list}


def remove_env(file_path: str, env_name: str) -> Dict[str, Any]:
    """删除环境（仅从列表和变量中移除，不可删除'默认环境'）。"""
    if env_name == "默认环境":
        return {"error": "默认环境不可删除"}
    store = _read_store(file_path)
    env_list = store.get("env_list", [])
    if env_name not in env_list:
        return {"error": f"环境 '{env_name}' 不存在"}
    env_list.remove(env_name)
    store["env_list"] = env_list
    envs = store.get("environments", {})
    envs.pop(env_name, None)
    store["environments"] = envs
    _write_store(file_path, store)
    return {"env_list": env_list}


# ── 兼容层（v1 单文件 API）──────────────────────────────────────────────

def read_variables(file_path: str, max_count: int = DEFAULT_MAX_COUNT) -> Dict[str, Any]:
    """兼容旧接口：读取 shared 变量。"""
    result = read_scope(file_path, "shared", max_count=max_count)
    store = _read_store(file_path)
    return {
        "version": store["version"],
        "updated_at": store["updated_at"],
        "variables": result["variables"],
        "count": result["count"],
    }


def write_variables(
    file_path: str, variables: Dict[str, str],
    max_count: int = DEFAULT_MAX_COUNT,
) -> Dict[str, Any]:
    """兼容旧接口：整体替换 shared 变量。"""
    store = _read_store(file_path)
    truncated = False
    if len(variables) > max_count:
        variables = dict(list(variables.items())[:max_count])
        truncated = True
    store["shared"] = dict(variables)
    _write_store(file_path, store)
    return {"count": len(variables), "truncated": truncated}


def delete_variable_compat(file_path: str, key: str) -> bool:
    """兼容旧接口：删除 shared 变量。"""
    return delete_variable(file_path, "shared", key)


def clear_variables(file_path: str) -> None:
    """兼容旧接口：清空 shared 变量。"""
    clear_scope(file_path, "shared")


def mask_value(value: str) -> str:
    """对变量值进行脱敏展示（保留首尾各 2 字符）。"""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def merge_variables_for_env(file_path: str, env_name: str = "") -> Dict[str, str]:
    """合并 shared + env 变量（env 优先），用于执行层加载。"""
    store = _read_store(file_path)
    merged: Dict[str, str] = {}
    shared = store.get("shared", {})
    if isinstance(shared, dict):
        merged.update(shared)
    if env_name:
        env_vars = store.get("environments", {}).get(env_name, {})
        if isinstance(env_vars, dict):
            merged.update(env_vars)
    return merged
