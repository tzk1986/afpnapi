"""report_utils.compute_summary 单元测试。"""

from typing import Any, Dict, List

from postman_api_tester.utils.report_utils import compute_summary


class TestComputeSummary:
	"""compute_summary() 聚合指标测试。"""

	def test_empty_results(self) -> None:
		result = compute_summary([])
		assert result["total"] == 0
		assert result["passed"] == 0
		assert result["failed"] == 0
		assert result["error"] == 0
		assert result["success_rate"] == "0.00%"

	def test_all_passed(self) -> None:
		results: List[Dict[str, Any]] = [
			{"status": "PASSED"},
			{"status": "PASSED"},
			{"status": "PASSED"},
		]
		result = compute_summary(results)
		assert result["total"] == 3
		assert result["passed"] == 3
		assert result["failed"] == 0
		assert result["error"] == 0
		assert result["success_rate"] == "100.00%"

	def test_all_failed(self) -> None:
		results: List[Dict[str, Any]] = [
			{"status": "FAILED"},
			{"status": "FAILED"},
		]
		result = compute_summary(results)
		assert result["total"] == 2
		assert result["passed"] == 0
		assert result["failed"] == 2
		assert result["success_rate"] == "0.00%"

	def test_all_error(self) -> None:
		results: List[Dict[str, Any]] = [{"status": "ERROR"}]
		result = compute_summary(results)
		assert result["total"] == 1
		assert result["error"] == 1
		assert result["passed"] == 0
		assert result["success_rate"] == "0.00%"

	def test_mixed_statuses(self) -> None:
		results: List[Dict[str, Any]] = [
			{"status": "PASSED"},
			{"status": "PASSED"},
			{"status": "FAILED"},
			{"status": "ERROR"},
		]
		result = compute_summary(results)
		assert result["total"] == 4
		assert result["passed"] == 2
		assert result["failed"] == 1
		assert result["error"] == 1
		assert result["success_rate"] == "50.00%"

	def test_missing_status_treated_as_non_passed(self) -> None:
		results: List[Dict[str, Any]] = [
			{"status": "PASSED"},
			{"other_field": "value"},
		]
		result = compute_summary(results)
		assert result["total"] == 2
		assert result["passed"] == 1
		assert result["success_rate"] == "50.00%"

	def test_success_rate_precision(self) -> None:
		results: List[Dict[str, Any]] = [
			{"status": "PASSED"},
			{"status": "PASSED"},
			{"status": "FAILED"},
		]
		result = compute_summary(results)
		assert result["success_rate"] == "66.67%"
