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

    def test_generate_preserves_config(self) -> None:
        """配置应在报告中保留。"""
        config = {"collection_name": "test", "base_url": "http://api.com", "custom_field": "value"}
        report = ReportEngine.generate([], config)
        assert report["config"] == config

    def test_generate_with_error_status(self) -> None:
        """ERROR 和 SKIPPED 状态应单独计数。"""
        results = [
            {"status": "PASSED", "response_time_ms": 100},
            {"status": "ERROR", "response_time_ms": 0},
            {"status": "SKIPPED", "response_time_ms": 0},
        ]
        report = ReportEngine.generate(results, {})
        assert report["summary"]["error"] == 1
        assert report["summary"]["skipped"] == 1

    def test_generate_missing_response_time(self) -> None:
        """缺少 response_time_ms 不应中断计算。"""
        results = [
            {"status": "PASSED"},
            {"status": "PASSED", "response_time_ms": 100},
        ]
        report = ReportEngine.generate(results, {})
        assert report["summary"]["avg_response_ms"] == 100

    def test_pass_rate_rounding(self) -> None:
        """通过率应四舍五入到 2 位小数。"""
        results = [{"status": "PASSED"} for _ in range(2)] + [{"status": "FAILED"}]
        summary = ReportEngine._calculate_summary(results)
        assert summary["pass_rate"] == 66.67

    def test_calculate_p95_empty(self) -> None:
        """空列表应返回 0。"""
        assert ReportEngine._calculate_p95([]) == 0

    def test_calculate_p95_single_value(self) -> None:
        """单值列表应返回该值。"""
        assert ReportEngine._calculate_p95([100]) == 100

    def test_calculate_p95_unsorted(self) -> None:
        """未排序输入应正确处理。"""
        values = [50, 10, 90, 30, 70, 20, 80, 40, 60, 100]
        p95 = ReportEngine._calculate_p95(values)
        # 排序后 [10,20,30,40,50,60,70,80,90,100]，p95 索引 int(10*0.95)=9，值为 100
        assert p95 == 100

    def test_invalid_response_time_ignored(self) -> None:
        """无效的 response_time_ms 值应被忽略。"""
        results = [
            {"status": "PASSED", "response_time_ms": "invalid"},
            {"status": "PASSED", "response_time_ms": None},
            {"status": "PASSED", "response_time_ms": 100},
        ]
        summary = ReportEngine._calculate_summary(results)
        assert summary["avg_response_ms"] == 100

    def test_merge_with_manual_cases_empty(self) -> None:
        """空人工用例应返回原始报告。"""
        report = {"results": [{"status": "PASSED"}], "summary": {"total": 1}}
        merged = ReportEngine.merge_with_manual_cases(report, [])
        assert merged == report

    def test_merge_adds_manual_cases(self) -> None:
        """人工用例应追加到结果中。"""
        report = {"results": [{"status": "PASSED", "response_time_ms": 100}], "summary": {"total": 1}}
        manual = [{"status": "FAILED", "response_time_ms": 200}]
        merged = ReportEngine.merge_with_manual_cases(report, manual)
        assert len(merged["results"]) == 2
        assert merged["results"][1]["status"] == "FAILED"

    def test_merge_recalculates_summary(self) -> None:
        """合并后应重新计算汇总。"""
        report = {"results": [{"status": "PASSED", "response_time_ms": 100}], "summary": {"total": 1}}
        manual = [{"status": "FAILED", "response_time_ms": 200}]
        merged = ReportEngine.merge_with_manual_cases(report, manual)
        assert merged["summary"]["total"] == 2
        assert merged["summary"]["passed"] == 1
        assert merged["summary"]["failed"] == 1
        assert merged["summary"]["pass_rate"] == 50.0

    def test_merge_preserves_other_fields(self) -> None:
        """其他报告字段应保留。"""
        report = {
            "collection_name": "test",
            "base_url": "http://test.com",
            "results": [],
            "summary": {},
        }
        merged = ReportEngine.merge_with_manual_cases(report, [{"status": "PASSED", "response_time_ms": 100}])
        assert merged["collection_name"] == "test"
        assert merged["base_url"] == "http://test.com"
