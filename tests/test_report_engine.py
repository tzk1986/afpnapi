"""ReportEngine 单元测试."""

import pytest
from postman_api_tester.core.report_engine import ReportEngine


class TestReportEngine:
    """ReportEngine 测试套件."""

    def test_calculate_summary_all_passed(self) -> None:
        """测试全部通过时的汇总."""
        results = [
            {"status": "PASSED", "response_time_ms": 100},
            {"status": "PASSED", "response_time_ms": 200},
        ]
        summary = ReportEngine._calculate_summary(results)
        assert summary["total"] == 2
        assert summary["passed"] == 2
        assert summary["failed"] == 0
        assert summary["error"] == 0
        assert summary["avg_response_ms"] == 150

    def test_calculate_summary_with_failures(self) -> None:
        """测试包含失败时的汇总."""
        results = [
            {"status": "PASSED", "response_time_ms": 100},
            {"status": "FAILED", "response_time_ms": 50},
            {"status": "ERROR", "response_time_ms": 0},
        ]
        summary = ReportEngine._calculate_summary(results)
        assert summary["total"] == 3
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["error"] == 1

    def test_calculate_p95(self) -> None:
        """测试 p95 计算."""
        results = [
            {"status": "PASSED", "response_time_ms": i * 10}
            for i in range(1, 21)
        ]
        summary = ReportEngine._calculate_summary(results)
        # 20 个元素，p95 索引为 int(20 * 0.95) = 19，即第 20 个元素 = 200
        assert summary["p95_response_ms"] == 200

    def test_generate_report_data(self) -> None:
        """测试生成报告数据对象."""
        results = [
            {"status": "PASSED", "name": "Test1", "response_time_ms": 100},
        ]
        config = {
            "collection_name": "Test Collection",
            "base_url": "http://localhost",
        }
        report = ReportEngine.generate(results, config)

        assert report["collection_name"] == "Test Collection"
        assert report["summary"]["total"] == 1
        assert len(report["results"]) == 1
        assert "generated_at" in report

    def test_generate_empty_results(self) -> None:
        """测试空结果生成报告."""
        report = ReportEngine.generate([], {"collection_name": "Empty"})
        assert report["summary"]["total"] == 0
        assert report["summary"]["passed"] == 0
        assert report["summary"]["failed"] == 0
        assert report["summary"]["error"] == 0
