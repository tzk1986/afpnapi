"""Tests for services/report_export_service.py helper functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from postman_api_tester.services.report_export_service import (
    _apply_scope_pruning,
    _validate_export_source,
)


class TestValidateExportSource:

    def test_missing_source_file_raises(self) -> None:
        with pytest.raises(ValueError, match="source_file"):
            _validate_export_source({})

    def test_empty_source_file_raises(self) -> None:
        with pytest.raises(ValueError, match="source_file"):
            _validate_export_source({"source_file": "  "})

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _validate_export_source({"source_file": str(tmp_path / "missing.json")})

    def test_existing_file_returns_path(self, tmp_path: Path) -> None:
        f = tmp_path / "collection.json"
        f.write_text("{}")
        result = _validate_export_source({"source_file": str(f)})
        assert result == f


class TestApplyScopePruning:

    def _make_report(self, results: list) -> Dict[str, Any]:
        return {"results": results}

    def test_full_scope_returns_collection_unchanged(self) -> None:
        collection = {"info": {}, "item": []}
        final, count, same, warnings = _apply_scope_pruning(
            collection, "full", self._make_report([]), 100, 0,
        )
        assert final is collection
        assert count == 0
        assert same is False
        assert warnings == []

    def test_report_only_without_paths_raises(self) -> None:
        collection = {"info": {}, "item": []}
        with pytest.raises(ValueError, match="item_path"):
            _apply_scope_pruning(collection, "report_only", self._make_report([]), 100, 0)

    def test_report_only_with_matching_count_sets_same_as_full(self) -> None:
        collection: Dict[str, Any] = {
            "info": {"name": "test"},
            "item": [
                {"name": "req1", "request": {"method": "GET", "url": {"raw": "http://a.com/1"}}},
            ],
        }
        report = {
            "results": [{"item_path": [0]}],
        }
        final, count, same, warnings = _apply_scope_pruning(
            collection, "report_only", report, 100, source_total_count=1,
        )
        assert count == 1
        assert same is True
        assert len(warnings) == 1
        assert "相同" in warnings[0]

    def test_report_only_with_different_count_not_same(self) -> None:
        collection: Dict[str, Any] = {
            "info": {"name": "test"},
            "item": [
                {"name": "req1", "request": {"method": "GET", "url": {"raw": "http://a.com/1"}}},
                {"name": "req2", "request": {"method": "GET", "url": {"raw": "http://a.com/2"}}},
            ],
        }
        report = {
            "results": [{"item_path": [0]}],
        }
        final, count, same, warnings = _apply_scope_pruning(
            collection, "report_only", report, 100, source_total_count=2,
        )
        assert count == 1
        assert same is False
        assert warnings == []
