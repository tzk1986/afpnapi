"""ReportRetryService 单元测试."""

import pytest
from pathlib import Path
from typing import Any, Dict, List

from postman_api_tester.services.report_retry_service import (
    build_retry_job_plan,
    build_retry_queue_record,
    build_retry_source_runtime_context,
    build_retry_worker_args,
    collect_all_item_paths,
    collect_failed_item_paths,
    parse_retry_runtime_params,
    resolve_existing_source_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(
    results: List[Dict[str, Any]] | None = None,
    source_file: str | None = None,
    base_url: str | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a minimal report dict for testing."""
    report: Dict[str, Any] = {"results": results or []}
    if source_file is not None:
        report["source_file"] = source_file
    if base_url is not None:
        report["base_url"] = base_url
    report.update(extra)
    return report


# ===========================================================================
# collect_failed_item_paths
# ===========================================================================

class TestCollectFailedItemPaths:
    """Tests for collect_failed_item_paths()."""

    def test_empty_results(self) -> None:
        assert collect_failed_item_paths({"results": []}) == []

    def test_no_results_key(self) -> None:
        assert collect_failed_item_paths({}) == []

    def test_all_passed(self) -> None:
        report = _make_report(results=[
            {"status": "PASSED", "item_path": [0]},
            {"status": "PASSED", "item_path": [1]},
        ])
        assert collect_failed_item_paths(report) == []

    def test_single_failed(self) -> None:
        report = _make_report(results=[
            {"status": "FAILED", "item_path": [2]},
        ])
        assert collect_failed_item_paths(report) == [[2]]

    def test_single_error(self) -> None:
        report = _make_report(results=[
            {"status": "ERROR", "item_path": [3]},
        ])
        assert collect_failed_item_paths(report) == [[3]]

    def test_mixed_statuses(self) -> None:
        report = _make_report(results=[
            {"status": "PASSED", "item_path": [0]},
            {"status": "FAILED", "item_path": [1]},
            {"status": "ERROR", "item_path": [2]},
            {"status": "PASSED", "item_path": [3]},
        ])
        result = collect_failed_item_paths(report)
        assert result == [[1], [2]]

    def test_invalid_item_path_none(self) -> None:
        report = _make_report(results=[
            {"status": "FAILED", "item_path": None},
        ])
        assert collect_failed_item_paths(report) == []

    def test_invalid_item_path_empty_list(self) -> None:
        report = _make_report(results=[
            {"status": "FAILED", "item_path": []},
        ])
        assert collect_failed_item_paths(report) == []

    def test_invalid_item_path_string(self) -> None:
        report = _make_report(results=[
            {"status": "FAILED", "item_path": "not-a-list"},
        ])
        assert collect_failed_item_paths(report) == []

    def test_multiple_failed_items(self) -> None:
        report = _make_report(results=[
            {"status": "FAILED", "item_path": [0]},
            {"status": "PASSED", "item_path": [1]},
            {"status": "FAILED", "item_path": [2]},
            {"status": "ERROR", "item_path": [3]},
        ])
        assert collect_failed_item_paths(report) == [[0], [2], [3]]

    def test_nested_item_paths(self) -> None:
        report = _make_report(results=[
            {"status": "FAILED", "item_path": [1, 2, 3]},
            {"status": "ERROR", "item_path": [4, 5]},
        ])
        assert collect_failed_item_paths(report) == [[1, 2, 3], [4, 5]]


# ===========================================================================
# collect_all_item_paths
# ===========================================================================

class TestCollectAllItemPaths:
    """Tests for collect_all_item_paths()."""

    def test_empty_results(self) -> None:
        assert collect_all_item_paths({"results": []}) == []

    def test_no_results_key(self) -> None:
        assert collect_all_item_paths({}) == []

    def test_all_passed(self) -> None:
        report = _make_report(results=[
            {"status": "PASSED", "item_path": [0]},
            {"status": "PASSED", "item_path": [1]},
        ])
        assert collect_all_item_paths(report) == [[0], [1]]

    def test_mixed_statuses(self) -> None:
        report = _make_report(results=[
            {"status": "PASSED", "item_path": [0]},
            {"status": "FAILED", "item_path": [1]},
            {"status": "ERROR", "item_path": [2]},
        ])
        assert collect_all_item_paths(report) == [[0], [1], [2]]

    def test_skip_invalid_paths(self) -> None:
        report = _make_report(results=[
            {"status": "PASSED", "item_path": [0]},
            {"status": "FAILED", "item_path": None},
            {"status": "ERROR", "item_path": []},
            {"status": "PASSED", "item_path": "bad"},
            {"status": "FAILED", "item_path": [3]},
        ])
        assert collect_all_item_paths(report) == [[0], [3]]

    def test_nested_paths_included(self) -> None:
        report = _make_report(results=[
            {"status": "PASSED", "item_path": [1, 2, 3]},
        ])
        assert collect_all_item_paths(report) == [[1, 2, 3]]


# ===========================================================================
# resolve_existing_source_file
# ===========================================================================

class TestResolveExistingSourceFile:
    """Tests for resolve_existing_source_file()."""

    def test_missing_source_file_key(self, tmp_path: Path) -> None:
        report = {}
        assert resolve_existing_source_file(report) is None

    def test_source_file_is_none(self, tmp_path: Path) -> None:
        report = {"source_file": None}
        assert resolve_existing_source_file(report) is None

    def test_source_file_is_empty_string(self, tmp_path: Path) -> None:
        report = {"source_file": ""}
        assert resolve_existing_source_file(report) is None

    def test_source_file_is_whitespace_only(self, tmp_path: Path) -> None:
        report = {"source_file": "   \t  "}
        assert resolve_existing_source_file(report) is None

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        report = {"source_file": str(tmp_path / "nonexistent.json")}
        assert resolve_existing_source_file(report) is None

    def test_existing_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_collection.json"
        test_file.write_text("{}")
        report = {"source_file": str(test_file)}
        assert resolve_existing_source_file(report) == str(test_file)

    def test_source_file_strips_whitespace(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_collection.json"
        test_file.write_text("{}")
        report = {"source_file": f"  {test_file}  "}
        # strip() on the outer whitespace makes the path valid again
        result = resolve_existing_source_file(report)
        assert result == str(test_file)

    def test_nested_directory_file(self, tmp_path: Path) -> None:
        sub_dir = tmp_path / "sub" / "dir"
        sub_dir.mkdir(parents=True)
        test_file = sub_dir / "collection.json"
        test_file.write_text("{}")
        report = {"source_file": str(test_file)}
        assert resolve_existing_source_file(report) == str(test_file)


# ===========================================================================
# build_retry_queue_record
# ===========================================================================

class TestBuildRetryQueueRecord:
    """Tests for build_retry_queue_record()."""

    def test_basic_structure(self) -> None:
        record = build_retry_queue_record(
            job_id="abc-123",
            saved_file="/path/to/collection.json",
            output_dir="/output",
            selected_count=5,
            queued_message="Retrying 5 failed items",
        )
        assert record["id"] == "abc-123"
        assert record["status"] == "queued"
        assert record["message"] == "Retrying 5 failed items"
        assert record["total"] == 0
        assert record["completed"] == 0
        assert record["percent"] == 0
        assert record["current_name"] == ""
        assert record["file_name"] == "collection.json"
        assert record["saved_file"] == "/path/to/collection.json"
        assert record["output_dir"] == "/output"
        assert record["report_name"] == ""
        assert record["run_scope"] == "selected"
        assert record["selected_count"] == 5

    def test_file_name_extracts_basename(self) -> None:
        record = build_retry_queue_record(
            job_id="j1", saved_file="C:\\Windows\\Path\\to\\file.json",
            output_dir="/o", selected_count=0, queued_message="",
        )
        # Path.name on Windows with backslashes returns the basename
        assert record["file_name"] in ("file.json", "to\\file.json")

    def test_all_required_fields_present(self) -> None:
        record = build_retry_queue_record(
            job_id="x", saved_file="/f", output_dir="/o",
            selected_count=1, queued_message="m",
        )
        expected_keys = {
            "id", "status", "message", "total", "completed",
            "percent", "current_name", "file_name", "saved_file",
            "output_dir", "report_name", "run_scope", "selected_count",
        }
        assert set(record.keys()) == expected_keys


# ===========================================================================
# build_retry_worker_args
# ===========================================================================

class TestBuildRetryWorkerArgs:
    """Tests for build_retry_worker_args()."""

    def test_returns_tuple(self) -> None:
        args = build_retry_worker_args(
            job_id="j1", saved_file="/c.json", base_url="http://x.com",
            output_dir="/o", token="tok", results_per_page=10,
            selected_paths=[[0], [1]],
        )
        assert isinstance(args, tuple)
        assert len(args) == 9

    def test_correct_values(self) -> None:
        args = build_retry_worker_args(
            job_id="j1", saved_file="/c.json", base_url="http://x.com",
            output_dir="/o", token="tok", results_per_page=10,
            selected_paths=[[0, 1]],
        )
        assert args == (
            "j1",
            "/c.json",
            "http://x.com",
            "/o",
            "tok",
            None,
            "c.json",
            10,
            [[0, 1]],
        )

    def test_none_base_url_preserved(self) -> None:
        args = build_retry_worker_args(
            job_id="j1", saved_file="/c.json", base_url=None,
            output_dir="/o", token=None, results_per_page=5,
            selected_paths=[],
        )
        assert args[2] is None
        assert args[4] is None

    def test_file_name_extracted(self) -> None:
        args = build_retry_worker_args(
            job_id="j1", saved_file="/deep/path/my_collection.json",
            base_url=None, output_dir="/o", token=None,
            results_per_page=1, selected_paths=[],
        )
        assert args[6] == "my_collection.json"


# ===========================================================================
# parse_retry_runtime_params
# ===========================================================================

class TestParseRetryRuntimeParams:
    """Tests for parse_retry_runtime_params()."""

    @pytest.fixture
    def clamp_fn(self):
        """Simple clamp lambda that clamps to 1-1000 range."""
        return lambda v: max(1, min(int(v), 1000))

    def test_valid_url_from_payload(self, clamp_fn) -> None:
        payload = {"base_url": "https://api.example.com"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["base_url"] == "https://api.example.com"

    def test_fallback_to_report_base_url(self, clamp_fn) -> None:
        payload = {}
        report = {"base_url": "http://report-url.com"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report=report, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["base_url"] == "http://report-url.com"

    def test_payload_url_overrides_report_url(self, clamp_fn) -> None:
        payload = {"base_url": "https://payload.com"}
        report = {"base_url": "http://report.com"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report=report, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["base_url"] == "https://payload.com"

    def test_invalid_ftp_url(self, clamp_fn) -> None:
        payload = {"base_url": "ftp://files.example.com"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert runtime is None
        assert err == "base_url 仅允许合法的 http/https 地址"

    def test_no_scheme_url_rejected(self, clamp_fn) -> None:
        payload = {"base_url": "example.com/api"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert runtime is None
        assert err == "base_url 仅允许合法的 http/https 地址"

    def test_http_without_netloc_rejected(self, clamp_fn) -> None:
        # e.g. just a scheme + path but no host
        payload = {"base_url": "http:///some-path"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert runtime is None
        assert err == "base_url 仅允许合法的 http/https 地址"

    def test_empty_base_url_becomes_none(self, clamp_fn) -> None:
        payload = {"base_url": ""}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["base_url"] is None

    def test_whitespace_token_trimmed(self, clamp_fn) -> None:
        payload = {"token": "  my-token  "}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["token"] == "my-token"

    def test_whitespace_only_token_becomes_none(self, clamp_fn) -> None:
        payload = {"token": "   "}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["token"] is None

    def test_results_per_page_clamped(self, clamp_fn) -> None:
        runtime, err = parse_retry_runtime_params(
            payload={"results_per_page": 5000}, report={},
            output_dir="/out", default_results_per_page=50,
            clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["results_per_page"] == 1000

    def test_results_per_page_defaults_when_missing(self, clamp_fn) -> None:
        runtime, err = parse_retry_runtime_params(
            payload={}, report={}, output_dir="/out",
            default_results_per_page=75,
            clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["results_per_page"] == 75

    def test_output_dir_passed_through(self, clamp_fn) -> None:
        runtime, err = parse_retry_runtime_params(
            payload={}, report={}, output_dir="/custom/output/dir",
            default_results_per_page=10, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["output_dir"] == "/custom/output/dir"

    def test_https_allowed(self, clamp_fn) -> None:
        payload = {"base_url": "https://secure.api.com/v1"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["base_url"] == "https://secure.api.com/v1"

    def test_http_allowed(self, clamp_fn) -> None:
        payload = {"base_url": "http://localhost:8080/api"}
        runtime, err = parse_retry_runtime_params(
            payload=payload, report={}, output_dir="/out",
            default_results_per_page=50, clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert runtime["base_url"] == "http://localhost:8080/api"


# ===========================================================================
# build_retry_source_runtime_context
# ===========================================================================

class TestBuildRetrySourceRuntimeContext:
    """Tests for build_retry_source_runtime_context()."""

    @pytest.fixture
    def clamp_fn(self):
        return lambda v: max(1, min(int(v), 1000))

    def test_missing_source_file_returns_error(self, clamp_fn) -> None:
        report = {"results": [], "source_file": None}
        ctx, err = build_retry_source_runtime_context(
            payload={}, report=report, output_dir="/out",
            default_results_per_page=50,
            clamp_run_results_per_page=clamp_fn,
        )
        assert ctx is None
        assert "找不到原始集合文件" in err

    def test_nonexistent_source_file_returns_error(self, tmp_path: Path, clamp_fn) -> None:
        report = {"results": [], "source_file": str(tmp_path / "no_such.json")}
        ctx, err = build_retry_source_runtime_context(
            payload={}, report=report, output_dir="/out",
            default_results_per_page=50,
            clamp_run_results_per_page=clamp_fn,
        )
        assert ctx is None
        assert "找不到原始集合文件" in err

    def test_invalid_url_propagates_error(self, tmp_path: Path, clamp_fn) -> None:
        test_file = tmp_path / "valid.json"
        test_file.write_text("{}")
        report = {"results": [], "source_file": str(test_file)}
        payload = {"base_url": "ftp://bad-url"}
        ctx, err = build_retry_source_runtime_context(
            payload=payload, report=report, output_dir="/out",
            default_results_per_page=50,
            clamp_run_results_per_page=clamp_fn,
        )
        assert ctx is None
        assert err == "base_url 仅允许合法的 http/https 地址"

    def test_success_returns_context(self, tmp_path: Path, clamp_fn) -> None:
        test_file = tmp_path / "collection.json"
        test_file.write_text("{}")
        report = {
            "results": [],
            "source_file": str(test_file),
            "base_url": "http://api.test.com",
        }
        payload = {"token": "test-token", "results_per_page": 25}
        ctx, err = build_retry_source_runtime_context(
            payload=payload, report=report, output_dir="/out",
            default_results_per_page=50,
            clamp_run_results_per_page=clamp_fn,
        )
        assert err is None
        assert ctx is not None
        assert ctx["saved_file"] == str(test_file)
        assert "runtime" in ctx
        assert ctx["runtime"]["base_url"] == "http://api.test.com"
        assert ctx["runtime"]["token"] == "test-token"
        assert ctx["runtime"]["results_per_page"] == 25

    def test_empty_source_file_tripped_to_none(self, tmp_path: Path, clamp_fn) -> None:
        report = {"results": [], "source_file": ""}
        ctx, err = build_retry_source_runtime_context(
            payload={}, report=report, output_dir="/out",
            default_results_per_page=50,
            clamp_run_results_per_page=clamp_fn,
        )
        assert ctx is None
        assert "找不到原始集合文件" in err


# ===========================================================================
# build_retry_job_plan
# ===========================================================================

class TestBuildRetryJobPlan:
    """Tests for build_retry_job_plan()."""

    def test_returns_expected_structure(self) -> None:
        plan = build_retry_job_plan(
            saved_file="/path/collection.json",
            runtime={"output_dir": "/out", "results_per_page": 50},
            selected_paths=[[0], [1]],
            queued_message="retrying 2 items",
        )
        assert "job_id" in plan
        assert "queue_record" in plan
        assert "worker_args" in plan

    def test_job_id_is_uuid_hex(self) -> None:
        plan1 = build_retry_job_plan(
            saved_file="/f", runtime={"output_dir": "/o", "results_per_page": 50},
            selected_paths=[], queued_message="",
        )
        plan2 = build_retry_job_plan(
            saved_file="/f", runtime={"output_dir": "/o", "results_per_page": 50},
            selected_paths=[], queued_message="",
        )
        # UUID hex is 32 lowercase hex characters
        assert len(plan1["job_id"]) == 32
        assert len(plan2["job_id"]) == 32
        assert plan1["job_id"] != plan2["job_id"]

    def test_queue_record_matches_job_id(self) -> None:
        plan = build_retry_job_plan(
            saved_file="/path/collection.json",
            runtime={"output_dir": "/out", "results_per_page": 50},
            selected_paths=[[0]],
            queued_message="1 item retry",
        )
        assert plan["queue_record"]["id"] == plan["job_id"]
        assert plan["queue_record"]["selected_count"] == 1
        assert plan["queue_record"]["file_name"] == "collection.json"
        assert plan["queue_record"]["output_dir"] == "/out"

    def test_worker_args_matches_job_id(self) -> None:
        plan = build_retry_job_plan(
            saved_file="/path/collection.json",
            runtime={"output_dir": "/out", "base_url": "http://x.com",
                     "token": "tok", "results_per_page": 10},
            selected_paths=[[0], [1]],
            queued_message="2 items",
        )
        assert plan["worker_args"][0] == plan["job_id"]
        assert plan["worker_args"][8] == [[0], [1]]
        assert len(plan["worker_args"]) == 9

    def test_selected_count_matches_length(self) -> None:
        paths = [[i] for i in range(7)]
        plan = build_retry_job_plan(
            saved_file="/f", runtime={"output_dir": "/o", "results_per_page": 50},
            selected_paths=paths, queued_message="",
        )
        assert plan["queue_record"]["selected_count"] == len(paths)

    def test_runtime_output_dir_converted_to_str(self) -> None:
        plan = build_retry_job_plan(
            saved_file="/f",
            runtime={"output_dir": Path("/tmp/test_out"), "results_per_page": 50},
            selected_paths=[], queued_message="",
        )
        assert isinstance(plan["queue_record"]["output_dir"], str)
        assert isinstance(plan["worker_args"][3], str)

    def test_runtime_int_results_per_page(self) -> None:
        plan = build_retry_job_plan(
            saved_file="/f",
            runtime={"output_dir": "/o", "results_per_page": 42},
            selected_paths=[], queued_message="",
        )
        assert plan["worker_args"][7] == 42

    def test_queue_record_status_is_queued(self) -> None:
        plan = build_retry_job_plan(
            saved_file="/f", runtime={"output_dir": "/o", "results_per_page": 50},
            selected_paths=[], queued_message="msg",
        )
        assert plan["queue_record"]["status"] == "queued"
        assert plan["queue_record"]["message"] == "msg"
