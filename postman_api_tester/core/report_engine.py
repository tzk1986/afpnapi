"""报告生成引擎。

职责：
- 从 TestResult 列表生成 Report 对象（纯内存操作）
- 计算统计信息（平均/max/p95）
- 不涉及磁盘 I/O（由上层处理）
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, TypedDict

logger = logging.getLogger(__name__)


class SummaryData(TypedDict):
    """报告汇总数据结构。"""

    total: int
    passed: int
    failed: int
    error: int
    skipped: int
    avg_response_ms: int
    max_response_ms: int
    p95_response_ms: int
    pass_rate: float


class ReportEngine:
    """报告生成引擎。"""

    @staticmethod
    def generate(
        results: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成报告对象（纯内存操作）。

        Args:
            results: 测试结果列表
            config: 报告配置（collection_name, base_url 等）

        Returns:
            完整的报告数据字典
        """
        summary = ReportEngine._calculate_summary(results)
        report: Dict[str, Any] = {
            "collection_name": config.get("collection_name", "Unknown"),
            "base_url": config.get("base_url", ""),
            "generated_at": datetime.now().isoformat(),
            "summary": summary,
            "results": results,
            "config": config,
        }
        logger.info(
            "report_generated",
            extra={
                "total": summary["total"],
                "passed": summary["passed"],
                "failed": summary["failed"],
            },
        )
        return report

    @staticmethod
    def _calculate_summary(results: List[Dict[str, Any]]) -> SummaryData:
        """计算汇总统计。"""
        total = len(results)
        passed = sum(1 for r in results if r.get("status") == "PASSED")
        failed = sum(1 for r in results if r.get("status") == "FAILED")
        error = sum(1 for r in results if r.get("status") == "ERROR")
        skipped = sum(1 for r in results if r.get("status") == "SKIPPED")

        response_times = [
            r.get("response_time_ms", 0)
            for r in results
            if isinstance(r.get("response_time_ms"), (int, float))
        ]

        avg_time = int(sum(response_times) / len(response_times)) if response_times else 0
        max_time = max(response_times) if response_times else 0
        p95_time = ReportEngine._calculate_p95(response_times)

        pass_rate = (passed / total * 100.0) if total > 0 else 0.0

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": error,
            "skipped": skipped,
            "avg_response_ms": avg_time,
            "max_response_ms": max_time,
            "p95_response_ms": p95_time,
            "pass_rate": round(pass_rate, 2),
        }

    @staticmethod
    def _calculate_p95(values: List[int]) -> int:
        """计算第 95 百分位值。"""
        if not values:
            return 0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * 0.95)
        idx = max(0, min(idx, len(sorted_values) - 1))
        return sorted_values[idx]

    @staticmethod
    def merge_with_manual_cases(
        report_data: Dict[str, Any],
        manual_cases: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """合并人工用例到报告数据。

        Args:
            report_data: 原始报告数据
            manual_cases: 人工用例列表

        Returns:
            合并后的报告数据
        """
        if not manual_cases:
            return report_data

        merged = dict(report_data)
        existing_results: List[Dict[str, Any]] = list(merged.get("results", []))
        existing_results.extend(manual_cases)
        merged["results"] = existing_results

        # 重新计算 summary
        merged["summary"] = ReportEngine._calculate_summary(existing_results)
        return merged
