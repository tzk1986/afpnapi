"""Report utility helpers for summary computation."""

"""开发导读：
- 职责：根据执行结果聚合 summary 指标（总数、通过率、状态分布）。
- 入口：compute_summary()。
"""

from typing import Any, Dict, List


def compute_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
	total = len(results)
	passed = sum(1 for r in results if r.get("status") == "PASSED")
	failed = sum(1 for r in results if r.get("status") == "FAILED")
	error = sum(1 for r in results if r.get("status") == "ERROR")
	rate = f"{(passed / total * 100):.2f}%" if total > 0 else "0.00%"
	return {"total": total, "passed": passed, "failed": failed, "error": error, "success_rate": rate}


__all__ = ["compute_summary"]
