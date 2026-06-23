"""report_job_store 模块单元测试。

覆盖 configure_run_jobs、set_run_job、get_run_job。
"""

from typing import Any, Dict, Optional

import pytest

from postman_api_tester import report_job_store
from postman_api_tester.report_job_store import (
	RUN_JOBS,
	RUN_JOBS_LOCK,
	configure_run_jobs,
	get_run_job,
	set_run_job,
)


@pytest.fixture(autouse=True)
def _clean_jobs() -> None:
	with RUN_JOBS_LOCK:
		RUN_JOBS.clear()
	yield
	with RUN_JOBS_LOCK:
		RUN_JOBS.clear()


class TestSetAndGetRunJob:
	"""set_run_job / get_run_job 基本读写测试。"""

	def test_set_then_get(self) -> None:
		set_run_job("job-1", status="running", progress=50)
		job = get_run_job("job-1")
		assert job is not None
		assert job["status"] == "running"
		assert job["progress"] == 50

	def test_get_nonexistent_returns_none(self) -> None:
		assert get_run_job("nonexistent") is None

	def test_update_existing_job(self) -> None:
		set_run_job("job-1", status="running")
		set_run_job("job-1", status="success", result="ok")
		job = get_run_job("job-1")
		assert job is not None
		assert job["status"] == "success"
		assert job["result"] == "ok"

	def test_get_returns_copy(self) -> None:
		set_run_job("job-1", status="running")
		job1 = get_run_job("job-1")
		job2 = get_run_job("job-1")
		assert job1 is not job2
		assert job1 == job2

	def test_multiple_jobs(self) -> None:
		set_run_job("a", status="running")
		set_run_job("b", status="success")
		set_run_job("c", status="failed")
		assert get_run_job("a")["status"] == "running"
		assert get_run_job("b")["status"] == "success"
		assert get_run_job("c")["status"] == "failed"


class TestConfigureRunJobs:
	"""configure_run_jobs() 配置测试。"""

	def test_valid_config(self) -> None:
		configure_run_jobs(500)
		assert report_job_store._RUN_JOBS_MAX == 500

	def test_minimum_is_10(self) -> None:
		configure_run_jobs(1)
		assert report_job_store._RUN_JOBS_MAX == 10

	def test_invalid_string_defaults_to_200(self) -> None:
		configure_run_jobs("not_a_number")
		assert report_job_store._RUN_JOBS_MAX == 200

	def test_none_defaults_to_200(self) -> None:
		configure_run_jobs(None)  # type: ignore[arg-type]
		assert report_job_store._RUN_JOBS_MAX == 200


class TestJobEviction:
	"""任务淘汰逻辑测试。"""

	def test_eviction_when_exceeds_limit(self) -> None:
		configure_run_jobs(10)
		for i in range(15):
			set_run_job(f"job-{i}", status="success")
		assert len(RUN_JOBS) <= 10

	def test_no_eviction_under_limit(self) -> None:
		configure_run_jobs(100)
		for i in range(5):
			set_run_job(f"job-{i}", status="running")
		assert len(RUN_JOBS) == 5
