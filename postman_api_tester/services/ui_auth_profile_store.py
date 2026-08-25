"""UI 认证档案文件存储服务。

以 JSON 文件形式持久化存储浏览器认证状态（Cookie），
供无头执行时通过 Playwright storage_state 加载，跳过登录步骤。
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PROFILES_DIR = Path("ui_testing_cases/auth_profiles")


class UiAuthProfileStore:
    """认证档案 JSON 文件存储。"""

    def __init__(self, profiles_dir: Optional[Path] = None) -> None:
        self._profiles_dir = profiles_dir or _DEFAULT_PROFILES_DIR
        self._lock = threading.Lock()
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def save_profile(self, profile: Dict[str, Any]) -> str:
        """保存认证档案，返回 profile_id。"""
        profile_id = profile.get("id") or f"auth_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        existing = self._load_profile_data(profile_id)
        created_at = existing.get("created_at", now) if existing else now

        record: Dict[str, Any] = {
            "id": profile_id,
            "name": profile.get("name", "未命名档案"),
            "description": profile.get("description", ""),
            "base_url": profile.get("base_url", ""),
            "cookies": profile.get("cookies", []),
            "source": profile.get("source", "manual"),
            "proxy_session_id": profile.get("proxy_session_id", ""),
            "created_at": created_at,
            "updated_at": now,
            "expires_at": profile.get("expires_at"),
        }

        file_path = self._profiles_dir / f"{profile_id}.json"
        with self._lock:
            file_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        logger.info(
            "ui_auth_profile_saved",
            extra={
                "event": "ui.auth.profile.saved",
                "profile_id": profile_id,
                "cookie_count": len(record["cookies"]),
            },
        )
        return profile_id

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """获取认证档案完整数据。"""
        return self._load_profile_data(profile_id)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """列出所有认证档案（摘要，不含完整 cookies）。"""
        result: List[Dict[str, Any]] = []
        with self._lock:
            for file_path in sorted(
                self._profiles_dir.glob("auth_*.json"),
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
                            "cookie_count": len(data.get("cookies", [])),
                            "source": data.get("source", ""),
                            "created_at": data.get("created_at", ""),
                            "updated_at": data.get("updated_at", ""),
                            "expires_at": data.get("expires_at"),
                        }
                    )
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(
                        "Failed to read auth profile %s: %s", file_path, e
                    )
        return result

    def delete_profile(self, profile_id: str) -> bool:
        """删除认证档案。"""
        file_path = self._profiles_dir / f"{profile_id}.json"
        with self._lock:
            if not file_path.exists():
                return False
            file_path.unlink()
        logger.info(
            "ui_auth_profile_deleted",
            extra={"event": "ui.auth.profile.deleted", "profile_id": profile_id},
        )
        return True

    def find_by_base_url(self, base_url: str) -> Optional[Dict[str, Any]]:
        """根据 base_url 查找匹配的认证档案（精确匹配）。"""
        with self._lock:
            for file_path in self._profiles_dir.glob("auth_*.json"):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    if data.get("base_url") == base_url:
                        return data
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def is_expired(self, profile: Dict[str, Any]) -> bool:
        """检查认证档案是否已过期。"""
        expires_at = profile.get("expires_at")
        if not expires_at:
            return False
        try:
            expire_time = datetime.fromisoformat(expires_at)
            return datetime.now() > expire_time
        except (ValueError, TypeError):
            return False

    def export_storage_state(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """导出 Playwright storage_state 格式数据。"""
        profile = self.get_profile(profile_id)
        if not profile:
            return None
        if self.is_expired(profile):
            return None
        return {
            "cookies": profile.get("cookies", []),
            "origins": [],  # Phase 1 不含 localStorage
        }

    def cleanup_expired(self) -> int:
        """清理已过期的认证档案。返回清理数量。"""
        removed = 0
        with self._lock:
            for file_path in list(self._profiles_dir.glob("auth_*.json")):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    expires_at = data.get("expires_at")
                    if expires_at:
                        expire_time = datetime.fromisoformat(expires_at)
                        if datetime.now() > expire_time:
                            file_path.unlink()
                            removed += 1
                except (json.JSONDecodeError, OSError, ValueError):
                    continue
        if removed > 0:
            logger.info(
                "ui_auth_profiles_cleanup",
                extra={
                    "event": "ui.auth.profile.cleanup",
                    "removed_count": removed,
                },
            )
        return removed

    def _load_profile_data(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """从磁盘加载认证档案数据（调用方须处理锁）。"""
        file_path = self._profiles_dir / f"{profile_id}.json"
        with self._lock:
            if not file_path.exists():
                return None
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to read auth profile %s: %s", profile_id, e)
                return None


# 全局单例
_auth_profile_store: UiAuthProfileStore = UiAuthProfileStore()
