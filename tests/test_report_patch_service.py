"""report_patch_service 单元测试."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from postman_api_tester.services.report_patch_service import patch_report_result


def _write_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class MockLock:
    def __enter__(self):
        return None
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


BASE_RESULT = {
    "name": "Test API", "folder": "", "method": "GET",
    "url": "https://example.com/api", "status": "PASSED",
    "message": "ok", "expected_status": 200,
    "item_path": [], "manual_judgement": {}, "judgement_history": [],
}


def make_deps(
    meta_file: str = "_meta.json",
    details_file: str | None = "_details.json",
    compute_func=None,
) -> tuple[MagicMock, dict]:
    deps = MagicMock()
    deps.get_report_write_lock.return_value = MockLock()
    deps.find_report.return_value = {"meta_file": meta_file, "details_file": details_file or ""}
    if compute_func is None:
        compute_func = lambda rs: {"total": len(rs), "passed": sum(1 for r in rs if r["status"] == "PASSED"),
                                   "failed": sum(1 for r in rs if r["status"] == "FAILED"),
                                   "error": sum(1 for r in rs if r["status"] == "ERROR"),
                                   "success_rate": round(sum(1 for r in rs if r["status"] == "PASSED") / max(len(rs), 1), 2)}
    deps.compute_summary.side_effect = compute_func
    deps.invalidate_reports_cache.reset_mock()
    return deps, compute_func


# --- normal patch flow -------------------------------------------------------

class TestNormalPatch:
    def test_patch_updates_meta_summary(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        result = patch_report_result(
            report_name="my_report", result_index=0,
            new_result_fields={"status": "FAILED", "message": "Connection reset"},
            new_request_info={"body": "{}"},
            new_response_info={"status_code": 500, "headers": {}},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )

        assert isinstance(result, dict)
        assert result["total"] == 1
        assert result["passed"] == 0
        assert result["failed"] == 1

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["status"] == "FAILED"
        assert saved["results"][0]["retried"] is True
        assert isinstance(saved["results"][0]["retry_history"], list)

    def test_patch_merges_new_fields_over_old(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "name": "Create Item", "folder": "Items"}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED", "message": "Validation error", "url": "https://api.example.com/items/updated"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        row = saved["results"][0]
        assert row["status"] == "FAILED"
        assert row["message"] == "Validation error"
        assert row["url"] == "https://api.example.com/items/updated"
        assert row["name"] == "Create Item"
        assert row["folder"] == "Items"
        assert row["expected_status"] == 200
        assert row["retried"] is True

    def test_patch_generates_key_field(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [dict(BASE_RESULT, name="Test", folder="F1")]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert "key" in saved["results"][0]
        assert "F1" in saved["results"][0]["key"]

    def test_patch_handles_empty_values(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "name": "", "folder": "", "method": "", "url": ""}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert "key" in saved["results"][0]

    def test_calls_find_report_and_lock(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        deps.invalidate_reports_cache.reset_mock()
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})

        patch_report_result(
            report_name="my_report", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )

        deps.find_report.assert_called_once_with("my_report")
        deps.get_report_write_lock.assert_called_once_with("my_report")
        deps.invalidate_reports_cache.assert_called_once()


# --- details file ------------------------------------------------------------

class TestDetailsFile:
    def test_creates_details_when_missing(self, tmp_path: Path) -> None:
        deps, cf = make_deps(details_file="_details.json")
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        details_path = tmp_path / "_details.json"
        assert not details_path.exists()

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={"body": '{"user": "test"}'},
            new_response_info={"status_code": 500, "body": "Error"},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        assert details_path.exists()
        with details_path.open("r") as f:
            details = json.load(f)
        assert "0" in details
        assert details["0"]["request_info"] == {"body": '{"user": "test"}'}
        assert details["0"]["response_info"] == {"status_code": 500, "body": "Error"}

    def test_appends_to_existing_details(self, tmp_path: Path) -> None:
        deps, cf = make_deps(details_file="_details.json")
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        details_path = tmp_path / "_details.json"
        _write_json(details_path, {"0": {"request_info": {"old": "data"}}})

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={"new": "data"},
            new_response_info={"new_resp": True},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with details_path.open("r") as f:
            details = json.load(f)
        assert details["0"]["request_info"] == {"new": "data"}
        assert details["0"]["response_info"] == {"new_resp": True}

    def test_handles_corrupt_details_file(self, tmp_path: Path) -> None:
        deps, cf = make_deps(details_file="_details.json")
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        details_path = tmp_path / "_details.json"
        details_path.write_text("NOT VALID JSON {{{")

        # Should not raise
        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={"clean": True},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with details_path.open("r") as f:
            details = json.load(f)
        assert "0" in details

    def test_skips_details_when_no_details_file(self, tmp_path: Path) -> None:
        deps, cf = make_deps(details_file="")
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={"data": 1},
            new_response_info={"code": 500},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        details_candidates = list(tmp_path.glob("*_details*"))
        assert len(details_candidates) == 0


# --- retry_history -----------------------------------------------------------

class TestRetryHistory:
    def test_retry_history_accumulates(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        orig = {**BASE_RESULT, "custom_key": "preserved_in_history", "status": "PASSED", "message": "first pass"}
        results = [orig.copy()]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        history = saved["results"][0]["retry_history"]
        assert len(history) == 1
        assert history[0]["status"] == "PASSED"
        assert history[0]["custom_key"] == "preserved_in_history"

    def test_manual_judgement_reset_on_patch(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{
            **BASE_RESULT, "name": "B", "status": "PASSED",
            "manual_judgement": {"active": True, "source": "manual", "action": "override", "target_status": "PASSED"},
        }]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        mj = saved["results"][0]["manual_judgement"]
        assert mj["active"] is False
        assert mj["source"] == "auto"

    def test_judgement_history_preserved_across_patch(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{
            **BASE_RESULT, "name": "C",
            "manual_judgement": {},
            "judgement_history": [{"action": "override", "at": "2026-06-10 10:00:00",
                                   "from_status": "FAILED", "to_status": "PASSED"}],
        }]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert len(saved["results"][0]["judgement_history"]) == 1


# --- early returns -----------------------------------------------------------

class TestEarlyReturns:
    def test_find_report_raises_file_not_found(self) -> None:
        deps, cf = make_deps()
        deps.find_report.side_effect = FileNotFoundError("Report not found")

        result = patch_report_result(
            report_name="missing", result_index=0,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=Path("/tmp"),
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_meta_file_empty_string_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps(meta_file="")
        result = patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_meta_file_whitespace_only_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps(meta_file="   ")
        result = patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_meta_file_absent_from_report_dict_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        deps.find_report.return_value = {}
        result = patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_meta_path_does_not_exist_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps(meta_file="gone.json")
        result = patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_result_index_out_of_range_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})

        result = patch_report_result(
            report_name="r", result_index=99,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_negative_result_index_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})

        result = patch_report_result(
            report_name="r", result_index=-1,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}

    def test_empty_results_list_returns_empty(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        _write_json(tmp_path / "_meta.json", {"results": [], "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "success_rate": 0.0}})

        result = patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={}, new_request_info={}, new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=MagicMock(),
            invalidate_reports_cache=MagicMock(),
        )
        assert result == {}


# --- field merging edge cases ------------------------------------------------

class TestFieldMerging:
    def test_preserves_original_expected_status(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "expected_status": 201}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["expected_status"] == 201

    def test_new_expected_status_overrides(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [dict(BASE_RESULT)]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED", "expected_status": 204},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["expected_status"] == 204

    def test_item_path_overrides(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "item_path": ["Root", "Sub"]}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED", "item_path": ["NewPath"]},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["item_path"] == ["NewPath"]

    def test_method_falls_back_to_old(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "method": "PATCH"}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["method"] == "PATCH"


# --- non-dict manual_judgement -----------------------------------------------

class TestNonDictManualJudgement:
    def test_manual_judgement_is_none(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "name": "I", "manual_judgement": None}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert isinstance(saved["results"][0]["manual_judgement"], dict)
        assert saved["results"][0]["manual_judgement"]["active"] is False

    def test_manual_judgement_is_string(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "name": "J", "manual_judgement": "invalid"}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["manual_judgement"]["active"] is False

    def test_manual_judgement_is_list(self, tmp_path: Path) -> None:
        deps, cf = make_deps()
        results = [{**BASE_RESULT, "name": "K", "manual_judgement": ["bad"]}]
        _write_json(tmp_path / "_meta.json", {"results": results, "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}})
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        patch_report_result(
            report_name="r", result_index=0,
            new_result_fields={"status": "FAILED"},
            new_request_info={},
            new_response_info={},
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["manual_judgement"]["active"] is False
