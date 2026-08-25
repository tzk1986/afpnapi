"""无头引擎 auth_state_path 校验测试。

覆盖 _validate_auth_state_file 的各种场景：
- 空路径返回 None
- 文件不存在返回 None
- JSON 格式错误返回 None
- 缺少 cookies 字段返回 None
- 合法文件返回 storage_state 字典
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from postman_api_tester.services.ui_headless_engine import _validate_auth_state_file


@pytest.fixture()
def tmp_auth_file(tmp_path: Path) -> Path:
    return tmp_path / "auth_state.json"


def _write_auth_file(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestValidateAuthStateFile:
    """auth_state_path 校验。"""

    def test_none_path_returns_none(self) -> None:
        assert _validate_auth_state_file(None, "job-1") is None

    def test_empty_path_returns_none(self) -> None:
        assert _validate_auth_state_file("", "job-1") is None

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        fake_path = str(tmp_path / "nonexistent.json")
        assert _validate_auth_state_file(fake_path, "job-1") is None

    def test_invalid_json_returns_none(self, tmp_auth_file: Path) -> None:
        tmp_auth_file.write_text("not valid json{{{", encoding="utf-8")
        assert _validate_auth_state_file(str(tmp_auth_file), "job-1") is None

    def test_missing_cookies_field_returns_none(self, tmp_auth_file: Path) -> None:
        _write_auth_file(tmp_auth_file, {"origins": []})
        assert _validate_auth_state_file(str(tmp_auth_file), "job-1") is None

    def test_not_dict_returns_none(self, tmp_auth_file: Path) -> None:
        tmp_auth_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert _validate_auth_state_file(str(tmp_auth_file), "job-1") is None

    def test_valid_file_returns_dict(self, tmp_auth_file: Path) -> None:
        data = {
            "cookies": [{"name": "session", "value": "abc123"}],
            "origins": [],
        }
        _write_auth_file(tmp_auth_file, data)
        result = _validate_auth_state_file(str(tmp_auth_file), "job-1")
        assert result is not None
        assert result["cookies"] == data["cookies"]
        assert result["origins"] == []

    def test_empty_cookies_array_is_valid(self, tmp_auth_file: Path) -> None:
        _write_auth_file(tmp_auth_file, {"cookies": [], "origins": []})
        result = _validate_auth_state_file(str(tmp_auth_file), "job-1")
        assert result is not None
        assert result["cookies"] == []
