"""core.types 模块单元测试。

覆盖 copy_summary() 纯函数。
"""

from typing import Any, Dict

import pytest

from postman_api_tester.core.types import SummaryData, copy_summary


def _make_summary(**overrides: Any) -> SummaryData:
	base: Dict[str, Any] = {
		"total": 10,
		"passed": 8,
		"failed": 1,
		"error": 1,
		"success_rate": "80.00%",
		"duration": "5.2s",
		"start_time": "2026-06-23T10:00:00",
		"end_time": "2026-06-23T10:00:05",
		"avg_response_ms": 200,
		"max_response_ms": 500,
		"p95_response_ms": 450,
	}
	base.update(overrides)
	return SummaryData(**base)  # type: ignore[typeddict-item]


class TestCopySummary:
	"""copy_summary() 摘要深拷贝测试。"""

	def test_returns_equal_copy(self) -> None:
		original = _make_summary()
		copied = copy_summary(original)
		assert copied == original

	def test_is_different_object(self) -> None:
		original = _make_summary()
		copied = copy_summary(original)
		assert copied is not original

	def test_all_fields_present(self) -> None:
		original = _make_summary()
		copied = copy_summary(original)
		expected_keys = {"total", "passed", "failed", "error", "success_rate",
						 "duration", "start_time", "end_time",
						 "avg_response_ms", "max_response_ms", "p95_response_ms"}
		assert set(copied.keys()) == expected_keys

	def test_mutation_does_not_affect_original(self) -> None:
		original = _make_summary()
		copied = copy_summary(original)
		copied["total"] = 999
		assert original["total"] == 10

	def test_zero_values(self) -> None:
		original = _make_summary(total=0, passed=0, failed=0, error=0,
								 success_rate="0.00%", avg_response_ms=0,
								 max_response_ms=0, p95_response_ms=0)
		copied = copy_summary(original)
		assert copied["total"] == 0
		assert copied["passed"] == 0

	def test_large_values(self) -> None:
		original = _make_summary(total=1000000, passed=999999, failed=1, error=0)
		copied = copy_summary(original)
		assert copied["total"] == 1000000
		assert copied["passed"] == 999999
