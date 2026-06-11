"""Postman API 测试主模块。

用于读取 APIFox/Postman 导出的接口文件，执行测试并生成报告。

开发导读:
- 主流程包含: 集合解析、可选筛选、认证解析、执行、报告生成与落盘。
- 对外建议调用 run_postman_tests；其余函数主要用于流程拆分与可测试性。
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from postman_api_tester.core.html_reporter import HtmlReporter
from postman_api_tester.core.types import (
    SummaryData,
    ProgressCallback,
    copy_summary,
)
from postman_api_tester.executor import TestResultRecord

logger = logging.getLogger(__name__)


class PostmanTestReport:
    """Postman 测试报告生成器。"""

    def __init__(self) -> None:
        self.results: List[TestResultRecord] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.collection_name = ""
        self.source_file = ""
        self.source_original_file = ""
        self.base_url = ""
        self.generated_report_file = ""
        self.generated_details_file = ""
        self.generated_meta_file = ""
        self.execution_mode = "full"
        self.interrupted = False
        self.interrupt_reason = ""
        self.assertion_strict_mode = False
        self._summary_cache: Optional[SummaryData] = None

    def add_result(self, result: TestResultRecord) -> None:
        """添加单条测试结果。"""
        self.results.append(result)
        self._summary_cache = None

    def add_results(self, results: List[TestResultRecord]) -> None:
        """批量添加测试结果。"""
        self.results.extend(results)
        self._summary_cache = None

    def generate_summary(self) -> SummaryData:
        """生成测试摘要。"""
        if self._summary_cache is not None:
            return copy_summary(self._summary_cache)

        self.end_time = datetime.now()

        passed = 0
        failed = 0
        error = 0
        for result in self.results:
            status = result.get('status')
            if status == 'PASSED':
                passed += 1
            elif status == 'FAILED':
                failed += 1
            elif status == 'ERROR':
                error += 1

        total = len(self.results)

        duration = (self.end_time - self.start_time).total_seconds()

        # 响应时间统计
        times = [r.get('response_time_ms', 0) for r in self.results if r.get('response_time_ms', 0) > 0]
        avg_response_ms = round(sum(times) / len(times)) if times else 0
        max_response_ms = max(times) if times else 0
        times_sorted = sorted(times)
        p95_idx = max(0, int(len(times_sorted) * 0.95) - 1)
        p95_response_ms = times_sorted[p95_idx] if times_sorted else 0

        summary: SummaryData = {
            'total': total,
            'passed': passed,
            'failed': failed,
            'error': error,
            'success_rate': f"{(passed/total*100):.2f}%" if total > 0 else "0%",
            'duration': f"{duration:.2f}s",
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'avg_response_ms': avg_response_ms,
            'max_response_ms': max_response_ms,
            'p95_response_ms': p95_response_ms,
        }
        self._summary_cache = summary
        return copy_summary(summary)

    def generate_html_report(self, output_path: str, results_per_page: int = 30) -> None:
        """生成 HTML 报告。"""
        HtmlReporter.generate_html_report(self, output_path, results_per_page=results_per_page)

    def print_console_report(self) -> None:
        """在控制台输出测试报告。"""
        HtmlReporter.print_console_report(self)


# Import execution helpers
from postman_api_tester.core.execution_helpers import (  # noqa: E402
    _prepare_runtime_settings,
    _prepare_execution_apis,
    _prepare_checkpoint_and_progress,
    _prepare_execution_context,
    _execute_and_finalize_suite,
    _complete_report_output,
)


def run_postman_tests(
    postman_file: str,
    base_url: Optional[str] = None,
    output_dir: Optional[str] = None,
    token: Optional[str] = None,
    report_name: Optional[str] = None,
    source_original_file: Optional[str] = None,
    results_per_page: int = 30,
    selected_item_paths: Optional[List[List[int]]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    judgment_config: Optional[Dict[str, Any]] = None,
) -> PostmanTestReport:
    """
    运行 Postman 接口测试。

    :param postman_file: Postman JSON 文件路径。
    :param base_url: 基础 URL（可选，覆盖集合中的配置）。
    :param output_dir: 报告输出目录。
    :param token: 手动指定认证 token（可选）。
    :param report_name: 报告名称（可选，支持 .html）。
    :param source_original_file: 原始上传文件名（可选）。
    :param results_per_page: 报告分页大小。
    :param selected_item_paths: 仅执行指定 item_path 的接口（可选）。
    :param progress_callback: 进度回调（可选）。
    :param judgment_config: 任务级结果判定配置（可选）。
    :return: 测试报告对象。
    """

    (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    ) = _prepare_runtime_settings(token, base_url, output_dir)

    parser, apis, total_apis_count, selected_total_count = _prepare_execution_apis(
        postman_file=postman_file,
        selected_item_paths=selected_item_paths,
        base_url=base_url,
    )

    checkpoint_path, collection_fingerprint, executed_item_paths, apis = _prepare_checkpoint_and_progress(
        enable_checkpoint_recovery=enable_checkpoint_recovery,
        output_dir=output_dir,
        postman_file=postman_file,
        parser_base_url=parser.base_url,
        selected_item_paths=selected_item_paths,
        apis=apis,
        checkpoint_dir=checkpoint_dir,
        progress_callback=progress_callback,
        total_apis_count=total_apis_count,
    )

    resolved_token, report, request_timeout, shared_session = _prepare_execution_context(
        token=token,
        apis=apis,
        parser=parser,
        postman_file=postman_file,
        source_original_file=source_original_file,
        assertion_strict_mode=assertion_strict_mode,
    )

    completed_count, execution_error = _execute_and_finalize_suite(
        apis=apis,
        total_apis_count=total_apis_count,
        report=report,
        resolved_token=resolved_token,
        request_timeout=request_timeout,
        assertion_strict_mode=assertion_strict_mode,
        progress_callback=progress_callback,
        enable_checkpoint_recovery=enable_checkpoint_recovery,
        checkpoint_flush_every_n=checkpoint_flush_every_n,
        checkpoint_path=checkpoint_path,
        collection_fingerprint=collection_fingerprint,
        parser_base_url=parser.base_url,
        selected_total_count=selected_total_count,
        executed_item_paths=executed_item_paths,
        shared_session=shared_session,
        judgment_config=judgment_config,
    )

    _complete_report_output(
        report,
        progress_callback=progress_callback,
        execution_error=execution_error,
        completed_count=completed_count,
        current_total=len(apis),
        total_apis_count=total_apis_count,
        output_dir=output_dir,
        report_name=report_name,
        results_per_page=results_per_page,
    )

    return report


if __name__ == '__main__':
    """
    使用示例:
    1. 将 Postman 导出的 JSON 文件放在项目目录
    2. 在命令行执行: python -m postman_api_tester.postman_api_tester <postman_file_path> [base_url] [output_dir]
    """

    if len(sys.argv) > 1:
        postman_file = sys.argv[1]
        base_url = sys.argv[2] if len(sys.argv) > 2 else None
        output_dir = sys.argv[3] if len(sys.argv) > 3 else None
        token = None
        results_per_page = 30

        if len(sys.argv) > 4:
            arg4 = str(sys.argv[4]).strip()
            # 兼容第4个参数直接作为分页大小的用法
            if arg4.isdigit() and len(sys.argv) == 5:
                results_per_page = int(arg4)
            else:
                token = None if arg4.lower() in {'', 'none', 'null', '-'} else arg4

        if len(sys.argv) > 5:
            results_per_page = int(sys.argv[5])

        run_postman_tests(
            postman_file=postman_file,
            base_url=base_url,
            output_dir=output_dir,
            token=token,
            results_per_page=results_per_page,
        )
    else:
        print("使用方法:")
        print("  python postman_api_tester.py <postman_file_path> [base_url] [output_dir] [token] [results_per_page]")
        print("\n参数说明:")
        print("  postman_file_path: Postman导出的JSON文件路径（必需）")
        print("  base_url: 基础URL（可选，将覆盖Postman文件中的配置）")
        print("  output_dir: 报告输出目录（可选，默认：../reports）")
