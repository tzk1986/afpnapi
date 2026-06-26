"""Tests for postman_api_tester.services.report_job_execution_service."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch, call

import pytest

from postman_api_tester.services.report_job_execution_service import (
    _safe_run_job,
    _build_progress_message,
    _create_progress_callback,
    run_postman_job,
    enqueue_retry_job,
    prepare_retry_job_context,
    enqueue_job_with_worker,
)


class TestBuildProgressMessage:
    """Tests for _build_progress_message helper."""

    def test_zero_total_returns_basic_message(self):
        """Test that zero total returns basic message."""
        result = _build_progress_message(0, 0, 0, "")
        assert result == "任务正在执行中..."

    def test_negative_total_returns_basic_message(self):
        """Test that negative total returns basic message."""
        result = _build_progress_message(-1, 0, 0, "")
        assert result == "任务正在执行中..."

    def test_positive_total_without_name(self):
        """Test positive total without current name."""
        result = _build_progress_message(10, 5, 50, "")
        assert result == "任务正在执行中: 5/10 (50%)"

    def test_positive_total_with_name(self):
        """Test positive total with current name."""
        result = _build_progress_message(10, 5, 50, "API1")
        assert result == "任务正在执行中: 5/10 (50%)，当前接口: API1"

    def test_completed_equals_total(self):
        """Test when completed equals total."""
        result = _build_progress_message(10, 10, 100, "LastAPI")
        assert result == "任务正在执行中: 10/10 (100%)，当前接口: LastAPI"


class TestCreateProgressCallback:
    """Tests for _create_progress_callback helper."""

    def test_callback_updates_status(self):
        """Test that callback updates job status."""
        set_run_job = MagicMock()
        callback = _create_progress_callback("job-1", set_run_job)

        callback({
            "total": 10,
            "completed": 5,
            "percent": 50,
            "current_name": "API1",
            "current_method": "GET",
            "current_url": "http://test.com",
            "last_status": "passed",
        })

        set_run_job.assert_called_once()
        call_kwargs = set_run_job.call_args[1]
        assert call_kwargs["status"] == "running"
        assert call_kwargs["total"] == 10
        assert call_kwargs["completed"] == 5
        assert call_kwargs["percent"] == 50
        assert "API1" in call_kwargs["message"]

    def test_callback_handles_missing_fields(self):
        """Test callback handles missing progress fields gracefully."""
        set_run_job = MagicMock()
        callback = _create_progress_callback("job-2", set_run_job)

        callback({})  # All fields missing

        set_run_job.assert_called_once()
        call_kwargs = set_run_job.call_args[1]
        assert call_kwargs["status"] == "running"
        assert call_kwargs["total"] == 0
        assert call_kwargs["completed"] == 0


class TestSafeRunJob:
    """Tests for _safe_run_job wrapper."""

    def test_successful_execution(self):
        """Test successful function execution."""
        fn = MagicMock()
        set_run_job = MagicMock()

        _safe_run_job(fn, ("arg1", "arg2"), "job-1", set_run_job)

        fn.assert_called_once_with("arg1", "arg2")
        set_run_job.assert_not_called()

    def test_successful_execution_with_kwargs(self):
        """Test successful execution with keyword arguments."""
        fn = MagicMock()
        set_run_job = MagicMock()

        _safe_run_job(fn, ("arg1",), "job-1", set_run_job, kwargs={"key": "value"})

        fn.assert_called_once_with("arg1", key="value")

    def test_exception_handling_updates_status(self):
        """Test exception is caught and status updated to error."""
        fn = MagicMock(side_effect=ValueError("test error"))
        set_run_job = MagicMock()

        _safe_run_job(fn, (), "job-1", set_run_job)

        set_run_job.assert_called_once()
        call_kwargs = set_run_job.call_args[1]
        assert call_kwargs["status"] == "error"
        assert "test error" in call_kwargs["message"]

    def test_exception_in_set_run_job_is_suppressed(self):
        """Test that exception in set_run_job is suppressed."""
        fn = MagicMock(side_effect=ValueError("test error"))
        set_run_job = MagicMock(side_effect=RuntimeError("set_run_job failed"))

        # Should not raise
        _safe_run_job(fn, (), "job-1", set_run_job)


class TestRunPostmanJob:
    """Tests for run_postman_job."""

    @patch("postman_api_tester.postman_api_tester.run_postman_tests")
    def test_successful_execution(self, mock_run_tests):
        """Test successful job execution flow."""
        mock_report = MagicMock()
        mock_report.generated_report_file = "/path/to/report.html"
        mock_report.generated_meta_file = "/path/to/meta.json"
        mock_run_tests.return_value = mock_report

        set_run_job = MagicMock()
        invalidate_cache = MagicMock()

        run_postman_job(
            job_id="job-1",
            postman_file="/path/to/collection.json",
            base_url="http://test.com",
            output_dir="/output",
            token="token123",
            report_name="Test Report",
            source_original_file="original.json",
            results_per_page=50,
            selected_item_paths=[[0, 1]],
            set_run_job=set_run_job,
            invalidate_reports_cache=invalidate_cache,
        )

        # Verify status transitions
        assert set_run_job.call_count == 2
        # First call: running
        assert set_run_job.call_args_list[0][1]["status"] == "running"
        # Second call: success
        assert set_run_job.call_args_list[1][1]["status"] == "success"
        assert set_run_job.call_args_list[1][1]["report_name"] == "report.html"

        # Verify cache invalidation
        invalidate_cache.assert_called_once()

    @patch("postman_api_tester.postman_api_tester.run_postman_tests")
    def test_execution_failure(self, mock_run_tests):
        """Test job execution failure handling."""
        mock_run_tests.side_effect = RuntimeError("Execution failed")

        set_run_job = MagicMock()
        invalidate_cache = MagicMock()

        run_postman_job(
            job_id="job-1",
            postman_file="/path/to/collection.json",
            base_url=None,
            output_dir="/output",
            token=None,
            report_name=None,
            source_original_file=None,
            results_per_page=50,
            selected_item_paths=None,
            set_run_job=set_run_job,
            invalidate_reports_cache=invalidate_cache,
        )

        # Verify status transitions
        assert set_run_job.call_count == 2
        # First call: running
        assert set_run_job.call_args_list[0][1]["status"] == "running"
        # Second call: failed
        assert set_run_job.call_args_list[1][1]["status"] == "failed"
        assert "Execution failed" in set_run_job.call_args_list[1][1]["message"]

        # Verify cache not invalidated on failure
        invalidate_cache.assert_not_called()

    @patch("postman_api_tester.postman_api_tester.run_postman_tests")
    def test_progress_callback(self, mock_run_tests):
        """Test progress callback is invoked."""
        mock_report = MagicMock()
        mock_report.generated_report_file = "/path/report.html"
        mock_report.generated_meta_file = "/path/meta.json"

        def capture_callback(**kwargs):
            callback = kwargs.get("progress_callback")
            if callback:
                callback({"total": 10, "completed": 5, "percent": 50, "current_name": "API1"})
            return mock_report

        mock_run_tests.side_effect = capture_callback

        set_run_job = MagicMock()
        invalidate_cache = MagicMock()

        run_postman_job(
            job_id="job-1",
            postman_file="/path/collection.json",
            base_url=None,
            output_dir="/output",
            token=None,
            report_name=None,
            source_original_file=None,
            results_per_page=50,
            selected_item_paths=None,
            set_run_job=set_run_job,
            invalidate_reports_cache=invalidate_cache,
        )

        # Verify progress callback was called (3 calls: running, progress, success)
        assert set_run_job.call_count == 3
        # Second call should be progress update
        progress_call = set_run_job.call_args_list[1]
        assert progress_call[1]["status"] == "running"
        assert progress_call[1]["completed"] == 5
        assert progress_call[1]["total"] == 10
        assert "API1" in progress_call[1]["current_name"]


class TestEnqueueRetryJob:
    """Tests for enqueue_retry_job."""

    @patch("postman_api_tester.services.report_job_execution_service.build_retry_job_plan")
    @patch("postman_api_tester.services.report_job_execution_service.threading.Thread")
    def test_retry_job_queued(self, mock_thread_class, mock_build_plan):
        """Test retry job is queued and thread started."""
        mock_build_plan.return_value = {
            "job_id": "retry-job-1",
            "queue_record": {"status": "queued", "message": "Retry queued"},
            "worker_args": ["retry-job-1", "/path/file.json", None, "/output"],
        }

        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        set_run_job = MagicMock()
        run_job_fn = MagicMock()

        job_id = enqueue_retry_job(
            saved_file="/path/file.json",
            runtime={"key": "value"},
            selected_paths=[[0]],
            queued_message="Retry queued",
            set_run_job=set_run_job,
            run_postman_job_fn=run_job_fn,
        )

        assert job_id == "retry-job-1"
        mock_build_plan.assert_called_once()
        set_run_job.assert_called_once_with("retry-job-1", status="queued", message="Retry queued")
        mock_thread_class.assert_called_once()
        mock_thread.start.assert_called_once()


class TestPrepareRetryJobContext:
    """Tests for prepare_retry_job_context."""

    @patch("postman_api_tester.services.report_job_execution_service.build_retry_source_runtime_context")
    @patch("postman_api_tester.services.report_job_execution_service.collect_failed_item_paths")
    def test_failures_mode(self, mock_collect_failed, mock_build_context):
        """Test failures retry mode."""
        mock_collect_failed.return_value = [[0], [1]]
        mock_build_context.return_value = ({"file": "/path"}, None)

        paths, ctx, error = prepare_retry_job_context(
            payload={"key": "value"},
            report={"results": []},
            retry_mode="failures",
            output_dir="/output",
            default_results_per_page=50,
            clamp_run_results_per_page=lambda x: 50,
        )

        assert paths == [[0], [1]]
        assert ctx == {"file": "/path"}
        assert error is None
        mock_collect_failed.assert_called_once()

    @patch("postman_api_tester.services.report_job_execution_service.build_retry_source_runtime_context")
    @patch("postman_api_tester.services.report_job_execution_service.collect_all_item_paths")
    def test_all_mode(self, mock_collect_all, mock_build_context):
        """Test all retry mode."""
        mock_collect_all.return_value = [[0], [1], [2]]
        mock_build_context.return_value = ({"file": "/path"}, None)

        paths, ctx, error = prepare_retry_job_context(
            payload={},
            report={"results": []},
            retry_mode="all",
            output_dir="/output",
            default_results_per_page=50,
            clamp_run_results_per_page=lambda x: 50,
        )

        assert paths == [[0], [1], [2]]
        assert ctx == {"file": "/path"}
        assert error is None
        mock_collect_all.assert_called_once()

    def test_invalid_mode_returns_error(self):
        """Test invalid retry mode returns error."""
        paths, ctx, error = prepare_retry_job_context(
            payload={},
            report={"results": []},
            retry_mode="invalid",
            output_dir="/output",
            default_results_per_page=50,
            clamp_run_results_per_page=lambda x: 50,
        )

        assert paths == []
        assert ctx is None
        assert "未知重试模式" in error

    @patch("postman_api_tester.services.report_job_execution_service.build_retry_source_runtime_context")
    @patch("postman_api_tester.services.report_job_execution_service.collect_failed_item_paths")
    def test_context_build_failure(self, mock_collect_failed, mock_build_context):
        """Test context build failure is propagated."""
        mock_collect_failed.return_value = [[0]]
        mock_build_context.return_value = (None, "Source file not found")

        paths, ctx, error = prepare_retry_job_context(
            payload={},
            report={"results": []},
            retry_mode="failures",
            output_dir="/output",
            default_results_per_page=50,
            clamp_run_results_per_page=lambda x: 50,
        )

        assert paths == [[0]]
        assert ctx is None
        assert error == "Source file not found"


class TestEnqueueJobWithWorker:
    """Tests for enqueue_job_with_worker."""

    @patch("postman_api_tester.services.report_job_execution_service.threading.Thread")
    def test_basic_job_enqueue(self, mock_thread_class):
        """Test basic job enqueue flow."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        set_run_job = MagicMock()
        run_job_fn = MagicMock()

        job_params = {
            "base_url": "http://test.com",
            "token": "token123",
            "report_name": "Test Report",
            "file_name": "collection.json",
        }

        enqueue_job_with_worker(
            job_id="job-1",
            saved_file="/path/file.json",
            job_params=job_params.copy(),
            results_per_page=50,
            run_postman_job_fn=run_job_fn,
            set_run_job=set_run_job,
            default_output_dir="/default/output",
        )

        set_run_job.assert_called_once()
        mock_thread_class.assert_called_once()
        mock_thread.start.assert_called_once()

    @patch("postman_api_tester.services.report_job_execution_service.threading.Thread")
    def test_job_with_optional_params(self, mock_thread_class):
        """Test job enqueue with optional parameters."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        set_run_job = MagicMock()
        run_job_fn = MagicMock()

        job_params = {
            "judgment_config": {"codes": ["0"]},
            "data_file": "/path/data.csv",
            "initial_variables": {"var1": "value1"},
            "env_name": "dev",
        }

        enqueue_job_with_worker(
            job_id="job-2",
            saved_file="/path/file.json",
            job_params=job_params.copy(),
            results_per_page=50,
            run_postman_job_fn=run_job_fn,
            set_run_job=set_run_job,
            default_output_dir="/output",
            selected_item_paths=[[0, 1]],
        )

        # Verify thread was created with correct kwargs
        thread_call = mock_thread_class.call_args
        assert thread_call[1]["kwargs"] == {
            "kwargs": {
                "judgment_config": {"codes": ["0"]},
                "data_file": "/path/data.csv",
                "initial_variables": {"var1": "value1"},
                "env_name": "dev",
            }
        }

    @patch("postman_api_tester.services.report_job_execution_service.threading.Thread")
    def test_job_uses_default_output_dir(self, mock_thread_class):
        """Test job uses default output dir when not specified."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        set_run_job = MagicMock()
        run_job_fn = MagicMock()

        job_params = {}  # No output_dir specified

        enqueue_job_with_worker(
            job_id="job-3",
            saved_file="/path/file.json",
            job_params=job_params.copy(),
            results_per_page=50,
            run_postman_job_fn=run_job_fn,
            set_run_job=set_run_job,
            default_output_dir="/default/output",
        )

        # Verify thread args contain default output dir
        thread_call = mock_thread_class.call_args
        worker_args = thread_call[1]["args"][1]  # Second element of args tuple
        assert "/default/output" in worker_args
