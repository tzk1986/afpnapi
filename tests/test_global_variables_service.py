"""全局变量服务单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from postman_api_tester.services.global_variables_service import (
    clear_variables,
    delete_variable,
    mask_value,
    read_variables,
    set_variable,
    write_variables,
)


class TestReadWriteVariables:

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        path = str(tmp_path / "nonexistent.json")
        data = read_variables(path)
        assert data["variables"] == {}
        assert data["count"] == 0

    def test_write_then_read(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"a": "1", "b": "2"})
        data = read_variables(path)
        assert data["variables"] == {"a": "1", "b": "2"}
        assert data["count"] == 2

    def test_write_truncates_excess(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        vars_dict = {f"v{i}": str(i) for i in range(100)}
        result = write_variables(path, vars_dict, max_count=5)
        assert result["truncated"] is True
        data = read_variables(path)
        assert data["count"] == 5

    def test_write_no_truncation(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        result = write_variables(path, {"a": "1"}, max_count=100)
        assert result["truncated"] is False
        assert result["count"] == 1


class TestSetVariable:

    def test_set_new_variable(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"existing": "val"})
        set_variable(path, "new_key", "new_val")

        data = read_variables(path)
        assert data["variables"]["new_key"] == "new_val"
        assert data["variables"]["existing"] == "val"

    def test_set_overwrites_existing(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"key": "old"})
        set_variable(path, "key", "new")

        data = read_variables(path)
        assert data["variables"]["key"] == "new"

    def test_set_on_empty_file(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "first", "value")
        data = read_variables(path)
        assert data["variables"] == {"first": "value"}


class TestDeleteVariable:

    def test_delete_existing(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"a": "1", "b": "2"})
        result = delete_variable(path, "a")
        assert result is True
        data = read_variables(path)
        assert "a" not in data["variables"]
        assert data["variables"]["b"] == "2"

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"a": "1"})
        result = delete_variable(path, "missing")
        assert result is False


class TestClearVariables:

    def test_clear(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"a": "1", "b": "2"})
        clear_variables(path)
        data = read_variables(path)
        assert data["variables"] == {}


class TestMaskValue:

    def test_short_value(self) -> None:
        assert mask_value("abc") == "***"

    def test_medium_value(self) -> None:
        result = mask_value("abcdefgh")
        assert result.startswith("ab")
        assert result.endswith("gh")
        assert "***" in result

    def test_empty_value(self) -> None:
        assert mask_value("") == "***"

    def test_four_chars(self) -> None:
        assert mask_value("abcd") == "***"

    def test_five_chars(self) -> None:
        result = mask_value("abcde")
        assert result == "ab*de"
