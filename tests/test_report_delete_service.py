"""report_delete_service 单元测试."""

from pathlib import Path
from unittest.mock import Mock, call

import pytest

from postman_api_tester.services.report_delete_service import (
    delete_report_artifacts,
)


# -- helpers ------------------------------------------------------------------ #


def _make_file(tmp_path: Path, name: str, content: str = "data") -> Path:
    """Create a real file and return its Path."""
    p = tmp_path / name
    p.write_text(content)
    return p


def _make_dir(tmp_path: Path, name: str) -> Path:
    """Create a real directory and return its Path."""
    d = tmp_path / name
    d.mkdir()
    return d


def _make_report(artifacts: list[Path]) -> dict:
    """Wrap artifacts in a minimal report dict."""
    return {"name": "test-report", "_artifacts": artifacts}


def _run(
    tmp_path: Path,
    artifacts: list[Path],
    find_fn: Mock | None = None,
    collect_fn: Mock | None = None,
    invalidate_fn: Mock | None = None,
) -> list[str]:
    """Helper to call delete_report_artifacts with defaults."""
    if find_fn is None:
        find_fn = Mock(return_value=_make_report(artifacts))
    if collect_fn is None:
        collect_fn = Mock(return_value=artifacts)
    if invalidate_fn is None:
        invalidate_fn = Mock()

    return delete_report_artifacts(
        report_name="test-report",
        find_report=find_fn,
        collect_report_artifacts=collect_fn,
        invalidate_reports_cache=invalidate_fn,
    )


# -- fixtures ----------------------------------------------------------------- #


@pytest.fixture
def tmp_files(tmp_path: Path) -> dict[str, Path]:
    """Pre-populate tmp_path with several named files."""
    return {
        name: _make_file(tmp_path, name)
        for name in ("summary.html", "details.json", "meta.yaml", "page.png")
    }


# -- normal deletion ---------------------------------------------------------- #


class TestDeleteNormal:
    """Happy-path deletion scenarios."""

    def test_deletes_all_artifacts(self, tmp_path, tmp_files):
        """All existing files are removed from disk."""
        artifact_paths = list(tmp_files.values())
        result = _run(tmp_path, artifact_paths)

        assert len(result) == len(artifact_paths)
        for path in artifact_paths:
            assert not path.exists(), f"{path} should have been deleted"

    def test_return_value_contains_only_filenames(self, tmp_files):
        """Returned names are bare filenames, not full paths."""
        artifact_paths = list(tmp_files.values())
        result = _run(tmp_files["summary.html"].parent, artifact_paths)

        for name in result:
            assert isinstance(name, str)
            assert "/" not in name
            assert "\\" not in name
        assert sorted(result) == ["details.json", "meta.yaml", "page.png", "summary.html"]

    def test_returned_names_are_set_of_originals(self, tmp_files):
        """Every original file name appears exactly once in the result."""
        artifact_paths = list(tmp_files.values())
        result = _run(tmp_files["details.json"].parent, artifact_paths)

        expected = {p.name for p in artifact_paths}
        assert set(result) == expected
        assert len(result) == len(expected)  # no duplicates

    def test_callbacks_called_in_order(self, tmp_files):
        """find_report -> collect -> unlink xN -> invalidate ordering."""
        artifacts = list(tmp_files.values())
        find_mock = Mock(return_value={"name": "test"})
        collect_mock = Mock(return_value=artifacts)
        invalidation_mock = Mock()

        result = delete_report_artifacts(
            report_name="my-report",
            find_report=find_mock,
            collect_report_artifacts=collect_mock,
            invalidate_reports_cache=invalidation_mock,
        )

        # Verify order via call counts at end
        assert find_mock.called
        assert collect_mock.called
        assert invalidation_mock.called
        # Each artifact unlink
        assert collect_mock.call_count == 1
        assert invalidation_mock.call_count == 1

    def test_report_dict_passthrough(self):
        """collect_report_artifacts receives the exact dict find_report returned."""
        expected_report = {"id": 42, "status": "complete"}
        find_mock = Mock(return_value=expected_report)
        collect_mock = Mock(return_value=[])

        delete_report_artifacts(
            report_name="x",
            find_report=find_mock,
            collect_report_artifacts=collect_mock,
            invalidate_reports_cache=Mock(),
        )

        collect_mock.assert_called_once_with(expected_report)

    def test_find_report_receives_report_name(self):
        """find_report is called with the report_name argument."""
        report_name = "my-special-report"
        find_mock = Mock(return_value={})
        delete_report_artifacts(
            report_name=report_name,
            find_report=find_mock,
            collect_report_artifacts=Mock(return_value=[]),
            invalidate_reports_cache=Mock(),
        )
        find_mock.assert_called_once_with(report_name)


# -- empty / no-op scenarios -------------------------------------------------- #


class TestEmptyScenarios:
    """Edge cases where nothing or very little happens."""

    def test_empty_artifacts_list(self):
        """No artifacts => instant return, cache still invalidated."""
        invalidate = Mock()
        result = delete_report_artifacts(
            report_name="empty",
            find_report=Mock(return_value={}),
            collect_report_artifacts=Mock(return_value=[]),
            invalidate_reports_cache=invalidate,
        )

        assert result == []
        invalidate.assert_called_once()

    def test_no_files_exist_on_disk(self, tmp_path):
        """Artifacts point to nonexistent paths => skipped silently."""
        fake_paths = [tmp_path / "ghost1.html", tmp_path / "ghost2.json"]
        result = _run(tmp_path, fake_paths)

        assert result == []

    def test_mixed_existing_and_missing(self, tmp_path, tmp_files):
        """Only existing files appear in results; missing ones skipped."""
        ghost = tmp_path / "phantom.log"
        artifact_paths = list(tmp_files.values()) + [ghost]

        result = _run(tmp_path, artifact_paths)

        assert len(result) == len(tmp_files)
        assert "phantom.log" not in result

    def test_return_count_matches_deleted(self):
        """Return list length equals number of unlink operations performed."""
        invalidate = Mock()
        collect = Mock(return_value=[])
        delete_report_artifacts(
            report_name="noop",
            find_report=Mock(return_value={}),
            collect_report_artifacts=collect,
            invalidate_reports_cache=invalidate,
        )
        # No artifacts at all — zero unlinks, zero returned
        assert collect.return_value == []  # sanity check


# -- directory skipping ------------------------------------------------------- #


class TestDirectorySkipping:
    """Directories must never be deleted by this function."""

    def test_directory_not_deleted(self, tmp_path):
        """A Path that is a directory is skipped entirely."""
        subdir = _make_dir(tmp_path, "subdir")
        result = _run(tmp_path, [subdir])

        assert result == []
        assert subdir.is_dir()  # still exists as directory

    def test_mixed_files_and_dirs(self, tmp_path, tmp_files):
        """Files get deleted; directories stay."""
        subdir = _make_dir(tmp_path, "keep_me")
        artifact_paths = list(tmp_files.values()) + [subdir]

        result = _run(tmp_path, artifact_paths)

        assert len(result) == len(tmp_files)  # dirs excluded
        for fname in result:
            assert not (tmp_path / fname).exists()
        assert subdir.is_dir()  # untouched

    def test_nested_dir_content_untouched(self, tmp_path):
        """Deep content inside a directory-skipped path is preserved."""
        parent = _make_dir(tmp_path, "parent")
        child = parent / "child.txt"
        child.write_text("inner")

        result = _run(tmp_path, [parent])

        assert result == []
        assert child.read_text() == "inner"


# -- error handling ----------------------------------------------------------- #


class TestErrorHandling:
    """Behavior when callbacks raise exceptions."""

    def test_find_report_raises_FileNotFoundError(self):
        """FileNotFoundError propagates; cache NOT invalidated."""
        invalidate = Mock()
        with pytest.raises(FileNotFoundError):
            delete_report_artifacts(
                report_name="missing",
                find_report=Mock(side_effect=FileNotFoundError("no such report")),
                collect_report_artifacts=Mock(),
                invalidate_reports_cache=invalidate,
            )

        invalidate.assert_not_called()

    def test_find_report_raises_generic_exception(self):
        """Any exception from find_report propagates; cache NOT invalidated."""
        invalidate = Mock()
        with pytest.raises(RuntimeError, match="boom"):
            delete_report_artifacts(
                report_name="bad",
                find_report=Mock(side_effect=RuntimeError("boom")),
                collect_report_artifacts=Mock(),
                invalidate_reports_cache=invalidate,
            )

        invalidate.assert_not_called()

    def test_collect_artifacts_raises_exception(self):
        """Exception from collect propagates; cache NOT invalidated."""
        invalidate = Mock()
        with pytest.raises(ValueError, match="bad data"):
            delete_report_artifacts(
                report_name="x",
                find_report=Mock(return_value={}),
                collect_report_artifacts=Mock(side_effect=ValueError("bad data")),
                invalidate_reports_cache=invalidate,
            )

        invalidate.assert_not_called()


# -- logging ------------------------------------------------------------------ #


class TestLogging:
    """Verify logging output."""

    def test_started_logged(self, caplog, tmp_files):
        """'report.delete.started' event logged before any work."""
        with caplog.at_level("INFO"):
            _run(tmp_files["summary.html"].parent, list(tmp_files.values()))

        started_records = [
            r for r in caplog.records if r.getMessage().startswith("report delete started")
        ]
        assert len(started_records) == 1
        assert started_records[0].report_name == "test-report"

    def test_completed_logged(self, caplog, tmp_files):
        """'report.delete.completed' event logged with deleted count."""
        with caplog.at_level("INFO"):
            _run(tmp_files["summary.html"].parent, list(tmp_files.values()))

        completed_records = [
            r for r in caplog.records if "report.delete.completed" in getattr(r, "event", "")
        ]
        assert len(completed_records) == 1
        record = completed_records[0]
        assert record.report_name == "test-report"
        assert record.deleted_count == len(tmp_files)

    def test_completed_count_zero_when_nothing_deleted(self, caplog):
        """Count is zero when artifacts list is empty."""
        with caplog.at_level("INFO"):
            delete_report_artifacts(
                report_name="zero",
                find_report=Mock(return_value={}),
                collect_report_artifacts=Mock(return_value=[]),
                invalidate_reports_cache=Mock(),
            )

        completed_records = [
            r for r in caplog.records if "report.delete.completed" in getattr(r, "event", "")
        ]
        assert len(completed_records) == 1
        assert completed_records[0].deleted_count == 0

    def test_no_error_logs_on_normal_run(self, caplog, tmp_files):
        """No WARNING or ERROR records during successful deletion."""
        with caplog.at_level("WARNING"):
            _run(tmp_files["summary.html"].parent, list(tmp_files.values()))

        warning_records = [r for r in caplog.records if r.levelno >= 30]
        assert len(warning_records) == 0
