"""VariableContext 持久化单元测试。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from postman_api_tester.core.variable_context import VariableContext


class TestSaveToFile:

    def test_save_creates_file(self, tmp_path: Path) -> None:
        ctx = VariableContext({"a": "1", "b": "2"})
        path = str(tmp_path / "vars.json")
        ctx.save_to_file(path)

        assert os.path.exists(path)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["variables"] == {"a": "1", "b": "2"}
        assert "updated_at" in data

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        ctx = VariableContext({"x": "1"})
        path = str(tmp_path / "deep" / "nested" / "vars.json")
        ctx.save_to_file(path)
        assert os.path.exists(path)

    def test_save_truncates_excess(self, tmp_path: Path) -> None:
        vars_dict = {f"v{i}": str(i) for i in range(100)}
        ctx = VariableContext(vars_dict)
        path = str(tmp_path / "vars.json")
        ctx.save_to_file(path, max_count=10)

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert len(data["variables"]) == 10

    def test_save_empty_context(self, tmp_path: Path) -> None:
        ctx = VariableContext()
        path = str(tmp_path / "vars.json")
        ctx.save_to_file(path)

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["variables"] == {}

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        ctx1 = VariableContext({"a": "1"})
        ctx1.save_to_file(path)

        ctx2 = VariableContext({"b": "2"})
        ctx2.save_to_file(path)

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["variables"] == {"b": "2"}


class TestLoadFromFile:

    def test_load_existing_file(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        data = {
            "version": 1,
            "updated_at": "2026-06-17T08:00:00",
            "variables": {"token": "abc", "user_id": "42"},
        }
        Path(path).write_text(json.dumps(data), encoding="utf-8")

        ctx = VariableContext.load_from_file(path)
        assert ctx.get("token") == "abc"
        assert ctx.get("user_id") == "42"

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        path = str(tmp_path / "nonexistent.json")
        ctx = VariableContext.load_from_file(path)
        assert ctx.variables == {}

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        path = str(tmp_path / "bad.json")
        Path(path).write_text("not valid json{{{", encoding="utf-8")
        ctx = VariableContext.load_from_file(path)
        assert ctx.variables == {}

    def test_load_with_initial_variables_priority(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        data = {"version": 1, "updated_at": "", "variables": {"a": "from_file", "b": "from_file"}}
        Path(path).write_text(json.dumps(data), encoding="utf-8")

        ctx = VariableContext.load_from_file(path, initial_variables={"a": "override", "c": "new"})
        assert ctx.get("a") == "override"
        assert ctx.get("b") == "from_file"
        assert ctx.get("c") == "new"

    def test_load_truncates_excess(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        file_vars = {f"v{i}": str(i) for i in range(50)}
        data = {"version": 1, "updated_at": "", "variables": file_vars}
        Path(path).write_text(json.dumps(data), encoding="utf-8")

        ctx = VariableContext.load_from_file(path, max_count=10)
        assert len(ctx.variables) == 10

    def test_load_invalid_structure(self, tmp_path: Path) -> None:
        path = str(tmp_path / "bad.json")
        data = {"version": 1, "variables": "not_a_dict"}
        Path(path).write_text(json.dumps(data), encoding="utf-8")
        ctx = VariableContext.load_from_file(path)
        assert ctx.variables == {}


class TestRoundTrip:

    def test_save_then_load(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")
        original = VariableContext({"token": "xyz", "count": "42"})
        original.save_to_file(path)

        loaded = VariableContext.load_from_file(path)
        assert loaded.get("token") == "xyz"
        assert loaded.get("count") == "42"

    def test_save_update_load(self, tmp_path: Path) -> None:
        path = str(tmp_path / "vars.json")

        ctx1 = VariableContext({"a": "1"})
        ctx1.save_to_file(path)

        ctx2 = VariableContext.load_from_file(path)
        ctx2.set("b", "2")
        ctx2.save_to_file(path)

        ctx3 = VariableContext.load_from_file(path)
        assert ctx3.get("a") == "1"
        assert ctx3.get("b") == "2"
