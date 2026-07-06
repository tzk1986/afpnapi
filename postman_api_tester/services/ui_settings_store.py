"""UI 测试设置存储服务。

设置持久化到 ui_testing_cases/settings.json，线程安全读写。
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from postman_api_tester.config import (
    UI_EXECUTION_DEFAULT_DELAY_MS,
    UI_EXECUTION_DEFAULT_TIMEOUT_MS,
    UI_EXECUTION_RETENTION_DAYS,
    UI_HEADLESS_BROWSER,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path("ui_testing_cases")
_SETTINGS_FILE = "settings.json"

_DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_mode": "browser_replay",
    "browser_replay": {
        "delay_between_steps": UI_EXECUTION_DEFAULT_DELAY_MS,
        "timeout_ms": UI_EXECUTION_DEFAULT_TIMEOUT_MS,
    },
    "headless": {
        "browser_type": UI_HEADLESS_BROWSER,
        "viewport_width": 1280,
        "viewport_height": 720,
        "take_screenshots": True,
        "ignore_https_errors": False,
    },
    "retention_days": UI_EXECUTION_RETENTION_DAYS,
    "webhook_url": "",
    "webhook_on_complete": True,
    "webhook_on_failure": True,
}


class UiSettingsStore:
    """UI 测试设置文件存储。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base_dir = base_dir or _DEFAULT_DIR
        self._lock = threading.Lock()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[Dict[str, Any]] = None

    def _settings_file(self) -> Path:
        return self._base_dir / _SETTINGS_FILE

    def get_settings(self) -> Dict[str, Any]:
        """获取当前设置（合并默认值）。"""
        with self._lock:
            if self._cache is not None:
                return self._cache
            return self._read_settings()

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新设置，返回合并后的完整设置。"""
        with self._lock:
            current = self._read_settings()
            self._deep_merge(current, updates)
            self._validate(current)
            self._write_settings(current)
            self._cache = current
            return current

    def reset_settings(self) -> Dict[str, Any]:
        """恢复默认设置。"""
        import copy
        with self._lock:
            default = copy.deepcopy(_DEFAULT_SETTINGS)
            self._write_settings(default)
            self._cache = default
            return default

    def _read_settings(self) -> Dict[str, Any]:
        """从文件读取设置，与默认值合并。"""
        import copy
        settings = copy.deepcopy(_DEFAULT_SETTINGS)
        path = self._settings_file()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._deep_merge(settings, data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("settings_read_error: %s", e)
        return settings

    def _write_settings(self, settings: Dict[str, Any]) -> None:
        """写入设置到文件。"""
        path = self._settings_file()
        try:
            path.write_text(
                json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.error("settings_write_error: %s", e)

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """深度合并 override 到 base（原地修改 base）。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                UiSettingsStore._deep_merge(base[key], value)
            else:
                base[key] = value

    @staticmethod
    def _validate(settings: Dict[str, Any]) -> None:
        """校验设置值合法性。"""
        br = settings.get("browser_replay", {})
        delay = br.get("delay_between_steps", 500)
        if not isinstance(delay, int) or delay < 100 or delay > 10000:
            br["delay_between_steps"] = 500
        timeout = br.get("timeout_ms", 30000)
        if not isinstance(timeout, int) or timeout < 1000 or timeout > 300000:
            br["timeout_ms"] = 30000
        settings["browser_replay"] = br

        hl = settings.get("headless", {})
        if hl.get("browser_type") not in ("chromium", "firefox", "webkit"):
            hl["browser_type"] = "chromium"
        vw = hl.get("viewport_width", 1280)
        vh = hl.get("viewport_height", 720)
        if not isinstance(vw, int) or vw < 320 or vw > 7680:
            hl["viewport_width"] = 1280
        if not isinstance(vh, int) or vh < 240 or vh > 4320:
            hl["viewport_height"] = 720
        settings["headless"] = hl

        rd = settings.get("retention_days", 30)
        if not isinstance(rd, int) or rd < 1 or rd > 365:
            settings["retention_days"] = 30

        mode = settings.get("default_mode", "browser_replay")
        if mode not in ("browser_replay", "headless"):
            settings["default_mode"] = "browser_replay"

        wurl = settings.get("webhook_url", "")
        if wurl and not isinstance(wurl, str):
            settings["webhook_url"] = ""
