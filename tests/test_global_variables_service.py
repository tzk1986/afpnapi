"""全局变量服务单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from postman_api_tester.services.global_variables_service import (
    add_env,
    clear_scope,
    clear_variables,
    delete_variable,
    get_env_list,
    mask_value,
    read_all,
    read_scope,
    read_variables,
    merge_variables_for_env,
    remove_env,
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
        set_variable(path, "shared", "new_key", "new_val")

        data = read_variables(path)
        assert data["variables"]["new_key"] == "new_val"
        assert data["variables"]["existing"] == "val"

    def test_set_overwrites_existing(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"key": "old"})
        set_variable(path, "shared", "key", "new")

        data = read_variables(path)
        assert data["variables"]["key"] == "new"

    def test_set_on_empty_file(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "first", "value")
        data = read_variables(path)
        assert data["variables"] == {"first": "value"}


class TestDeleteVariable:

    def test_delete_existing(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"a": "1", "b": "2"})
        result = delete_variable(path, "shared", "a")
        assert result is True
        data = read_variables(path)
        assert "a" not in data["variables"]
        assert data["variables"]["b"] == "2"

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        write_variables(path, {"a": "1"})
        result = delete_variable(path, "shared", "missing")
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


class TestMultiEnvironment:

    def test_read_all_empty(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        data = read_all(path)
        assert data["shared"] == {}
        assert data["environments"] == {"默认环境": {}}
        assert "默认环境" in data.get("env_list", [])
        assert data["total_count"] == 0

    def test_set_shared_and_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "token", "abc")
        set_variable(path, "env", "db_host", "10.0.0.1", env_name="prod")
        data = read_all(path)
        assert data["shared"] == {"token": "abc"}
        assert data["environments"]["prod"] == {"db_host": "10.0.0.1"}
        assert data["total_count"] == 2

    def test_read_scope_shared(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "a", "1")
        set_variable(path, "env", "b", "2", env_name="test")
        result = read_scope(path, "shared")
        assert result["variables"] == {"a": "1"}
        assert result["count"] == 1

    def test_read_scope_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "a", "1")
        set_variable(path, "env", "b", "2", env_name="test")
        result = read_scope(path, "env", env_name="test")
        assert result["variables"] == {"b": "2"}

    def test_read_scope_env_nonexistent(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "a", "1")
        result = read_scope(path, "env", env_name="nonexistent")
        assert result["variables"] == {}
        assert result["count"] == 0

    def test_delete_variable_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "env", "x", "1", env_name="dev")
        set_variable(path, "env", "y", "2", env_name="dev")
        assert delete_variable(path, "env", "x", env_name="dev") is True
        result = read_scope(path, "env", env_name="dev")
        assert result["variables"] == {"y": "2"}

    def test_clear_scope_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "a", "1")
        set_variable(path, "env", "b", "2", env_name="prod")
        clear_scope(path, "env", env_name="prod")
        data = read_all(path)
        assert data["shared"] == {"a": "1"}
        assert data["environments"]["prod"] == {}

    def test_merge_variables_for_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "token", "shared_token")
        set_variable(path, "shared", "app", "myapp")
        set_variable(path, "env", "token", "prod_token", env_name="prod")
        set_variable(path, "env", "db", "proddb", env_name="prod")
        merged = merge_variables_for_env(path, "prod")
        assert merged["token"] == "prod_token"
        assert merged["app"] == "myapp"
        assert merged["db"] == "proddb"

    def test_merge_variables_no_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "shared", "a", "1")
        set_variable(path, "env", "b", "2", env_name="prod")
        merged = merge_variables_for_env(path, "")
        assert merged == {"a": "1"}

    def test_old_format_migration(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        old_data = {"version": 1, "updated_at": "2026-01-01T00:00:00", "variables": {"old_key": "old_val"}}
        Path(path).write_text(json.dumps(old_data, ensure_ascii=False), encoding="utf-8")
        data = read_all(path)
        assert data["shared"] == {"old_key": "old_val"}
        assert data["environments"] == {"默认环境": {}}

    def test_multiple_environments_isolated(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        set_variable(path, "env", "key1", "val_prod", env_name="prod")
        set_variable(path, "env", "key2", "val_dev", env_name="dev")
        prod = read_scope(path, "env", env_name="prod")
        dev = read_scope(path, "env", env_name="dev")
        assert prod["variables"] == {"key1": "val_prod"}
        assert dev["variables"] == {"key2": "val_dev"}


class TestEnvManagement:

    def test_get_env_list_default(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        env_list = get_env_list(path)
        assert env_list == ["默认环境"]

    def test_add_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        result = add_env(path, "生产环境")
        assert result["exists"] is False
        assert "生产环境" in result["env_list"]

    def test_add_duplicate_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        add_env(path, "测试环境")
        result = add_env(path, "测试环境")
        assert result["exists"] is True

    def test_remove_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        add_env(path, "临时环境")
        result = remove_env(path, "临时环境")
        assert "error" not in result
        assert "临时环境" not in result["env_list"]

    def test_remove_default_env_blocked(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        result = remove_env(path, "默认环境")
        assert "error" in result

    def test_remove_nonexistent_env(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        result = remove_env(path, "不存在")
        assert "error" in result

    def test_env_list_persists_with_variables(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        add_env(path, "开发环境")
        set_variable(path, "env", "db_host", "localhost", env_name="开发环境")
        env_list = get_env_list(path)
        assert "开发环境" in env_list
        scope = read_scope(path, "env", env_name="开发环境")
        assert scope["variables"] == {"db_host": "localhost"}

