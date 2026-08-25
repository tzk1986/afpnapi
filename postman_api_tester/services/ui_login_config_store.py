"""UI 登录配置存储服务。

以 JSON 文件形式持久化存储登录步骤配置，
供无头执行时自动运行登录步骤并保存 Cookie 到认证档案。
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CONFIGS_DIR = Path("ui_testing_cases/login_configs")


class UiLoginConfigStore:
    """登录配置 JSON 文件存储。"""

    def __init__(self, configs_dir: Optional[Path] = None) -> None:
        self._configs_dir = configs_dir or _DEFAULT_CONFIGS_DIR
        self._lock = threading.Lock()
        self._configs_dir.mkdir(parents=True, exist_ok=True)

    def save_config(self, config: Dict[str, Any]) -> str:
        """保存登录配置，返回 config_id。"""
        config_id = config.get("id") or f"login_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        existing = self._load_config_data(config_id)
        created_at = existing.get("created_at", now) if existing else now

        record: Dict[str, Any] = {
            "id": config_id,
            "name": config.get("name", "未命名配置"),
            "description": config.get("description", ""),
            "base_url": config.get("base_url", ""),
            "login_steps": config.get("login_steps", []),
            "success_condition": config.get("success_condition", {}),
            "created_at": created_at,
            "updated_at": now,
        }

        file_path = self._configs_dir / f"{config_id}.json"
        with self._lock:
            file_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        logger.info(
            "ui_login_config_saved",
            extra={
                "event": "ui.login_config.saved",
                "config_id": config_id,
                "step_count": len(record["login_steps"]),
            },
        )
        return config_id

    def get_config(self, config_id: str) -> Optional[Dict[str, Any]]:
        """获取登录配置完整数据。"""
        return self._load_config_data(config_id)

    def list_configs(self) -> List[Dict[str, Any]]:
        """列出所有登录配置（摘要）。"""
        result: List[Dict[str, Any]] = []
        with self._lock:
            for file_path in sorted(
                self._configs_dir.glob("login_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            ):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    result.append(
                        {
                            "id": data.get("id", ""),
                            "name": data.get("name", ""),
                            "description": data.get("description", ""),
                            "base_url": data.get("base_url", ""),
                            "step_count": len(data.get("login_steps", [])),
                            "success_condition": data.get("success_condition", {}),
                            "created_at": data.get("created_at", ""),
                            "updated_at": data.get("updated_at", ""),
                        }
                    )
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to read login config %s: %s", file_path, e)
        return result

    def delete_config(self, config_id: str) -> bool:
        """删除登录配置。"""
        file_path = self._configs_dir / f"{config_id}.json"
        with self._lock:
            if not file_path.exists():
                return False
            file_path.unlink()
        logger.info(
            "ui_login_config_deleted",
            extra={"event": "ui.login_config.deleted", "config_id": config_id},
        )
        return True

    def find_by_base_url(self, base_url: str) -> Optional[Dict[str, Any]]:
        """根据 base_url 查找匹配的登录配置（精确匹配）。"""
        with self._lock:
            for file_path in self._configs_dir.glob("login_*.json"):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    if data.get("base_url") == base_url:
                        return data
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def _load_config_data(self, config_id: str) -> Optional[Dict[str, Any]]:
        """从磁盘加载登录配置数据。"""
        file_path = self._configs_dir / f"{config_id}.json"
        with self._lock:
            if not file_path.exists():
                return None
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to read login config %s: %s", config_id, e)
                return None


# 全局单例
_login_config_store: UiLoginConfigStore = UiLoginConfigStore()
