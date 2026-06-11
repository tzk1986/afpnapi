"""HTML 报告生成器。

职责：
- 从 PostmanTestReport 生成 HTML/JSON 报告文件
- 控制台报告输出
"""

import html as _html
import json
import logging
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader

from postman_api_tester.core.types import SummaryData, DetailsData, IndexResultsData, ReportMetadata
from postman_api_tester.executor import TestResultRecord
from postman_api_tester.utils.security import sanitize_headers

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)


class HtmlReporter:
    """HTML 报告生成器。"""

    @staticmethod
    def _build_details_data(report: Any) -> DetailsData:
        """构建详情数据并执行请求头脱敏。"""
        details_data: DetailsData = {}
        for idx, result in enumerate(report.results):
            req_info = result.get('request_info', {})
            raw_req_headers = req_info.get('headers', {}) or {}
            sanitized_headers = sanitize_headers(raw_req_headers, mask='***')
            details_data[str(idx)] = {
                'request_info': {**req_info, 'headers': sanitized_headers},
                'response_info': result.get('response_info', {}),
            }
        return details_data


    @staticmethod
    def _write_json_file(report: Any, file_path: str, payload: object) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)


    @staticmethod
    def _write_text_file(report: Any, file_path: str, content: str) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)


    @staticmethod
    def _write_report_pages(
        report: Any,
        *,
        base_name: str,
        total_pages: int,
        results_per_page: int,
        summary: SummaryData,
        details_file_name: str,
    ) -> None:
        for page in range(1, total_pages + 1):
            page_content = HtmlReporter._generate_page_html(report, page, results_per_page, summary, details_file_name)
            page_path = f"{base_name}_page_{page}.html"
            HtmlReporter._write_text_file(report, page_path, page_content)


    @staticmethod
    def _build_index_results_data(report: Any) -> IndexResultsData:
        """构建首页报告表格数据（包含详情字段）。"""
        results_data: IndexResultsData = []
        for result in report.results:
            results_data.append({
                'name': result.get('name', ''),
                'folder': result.get('folder', ''),
                'method': result.get('method', ''),
                'url': result.get('url', ''),
                'status': result.get('status', ''),
                'status_code': result.get('status_code', ''),
                'message': result.get('message', ''),
                'err_code': result.get('err_code', ''),
                'request_info': result.get('request_info', {}),
                'response_info': result.get('response_info', {}),
            })
        return results_data


    @staticmethod
    def _normalize_index_page_size(report: Any, results_per_page: int) -> int:
        """规范首页每页数量，确保与下拉选项一致。"""
        page_size_options = {20, 30, 50, 100, 200}
        return results_per_page if results_per_page in page_size_options else 20


    @staticmethod
    def _render_page_size_options(report: Any, selected_page_size: int) -> str:
        option_values = [20, 30, 50, 100, 200]
        options: List[str] = []
        for value in option_values:
            selected = ' selected' if value == selected_page_size else ''
            options.append(f'<option value="{value}"{selected}>{value}条</option>')
        return '\n                    '.join(options)


    @staticmethod
    def _get_page_window(report: Any, page: int, results_per_page: int) -> Tuple[int, int, List[TestResultRecord]]:
        """返回分页窗口和当前页结果。"""
        start_idx = (page - 1) * results_per_page
        end_idx = min(page * results_per_page, len(report.results))
        page_results = report.results[start_idx:end_idx]
        return start_idx, end_idx, page_results


    @staticmethod
    def _build_page_table_rows(report: Any, page_results: List[TestResultRecord], start_idx: int) -> str:
        """构建分页报告表格行。"""
        _esc = _html.escape
        table_rows = ""
        for idx, result in enumerate(page_results):
            global_idx = start_idx + idx
            status_class = f"status-{_esc(str(result['status']).lower())}"
            status_lower = _esc(str(result['status']).lower())
            detail_id = f"detail-{global_idx}"

            table_rows += f"""
            <tr class="result-row result-{status_lower}" data-status="{status_lower}">
                <td><span class="expand-btn" onclick="toggleDetail('{detail_id}', {global_idx})">详情</span></td>
                <td>{_esc(str(result['name']))}</td>
                <td>{_esc(str(result.get('folder', '-')))}</td>
                <td>{_esc(str(result['method']))}</td>
                <td><span class="url">{_esc(str(result['url']))}</span></td>
                <td><span class="{status_class}">{_esc(str(result['status']))}</span></td>
                <td>{_esc(str(result['status_code'] or '-'))}</td>
                <td><span class="detail">{_esc(str(result['message']))}</span></td>
            </tr>
            <tr class="detail-row" id="{detail_id}">
                <td colspan="8">
                    <div class="detail-content" id="detail-content-{global_idx}">
                        <div class="loading">加载中...</div>
                    </div>
                </td>
            </tr>
"""
        return table_rows


    @staticmethod
    def generate_html_report(report: Any, output_path: str, results_per_page: int = 30) -> None:
        """生成 HTML 报告。"""
        summary = report.generate_summary()
        output_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else '.'
        os.makedirs(output_dir, exist_ok=True)

        # 计算分页
        total_results = len(report.results)
        total_pages = (total_results + results_per_page - 1) // results_per_page
        details_data = HtmlReporter._build_details_data(report)

        # 保存详情 JSON 文件
        base_name = os.path.splitext(output_path)[0]
        details_file = f"{base_name}_details.json"
        HtmlReporter._write_json_file(report, details_file, details_data)

        meta_file = f"{base_name}_meta.json"
        HtmlReporter._write_json_file(report, meta_file, HtmlReporter._build_report_metadata(report, summary, output_path, details_file))

        # 生成索引页面
        index_content = HtmlReporter._generate_index_html(report, summary, total_pages, results_per_page, total_results)
        HtmlReporter._write_text_file(report, output_path, index_content)

        # 生成分页页面
        HtmlReporter._write_report_pages(report,
            base_name=base_name,
            total_pages=total_pages,
            results_per_page=results_per_page,
            summary=summary,
            details_file_name=os.path.basename(details_file),
        )

        report.generated_report_file = output_path
        report.generated_details_file = details_file
        report.generated_meta_file = meta_file


    @staticmethod
    def _build_report_metadata(report: Any, summary: SummaryData, output_path: str, details_file: str) -> ReportMetadata:
        """构建历史报告和差异比对所需的结构化元数据。"""
        return {
            'report_name': os.path.basename(output_path),
            'generated_at': summary['end_time'],
            'host_name': socket.gethostname(),
            'collection_name': report.collection_name,
            'source_file': report.source_file,
            'source_original_file': report.source_original_file,
            'base_url': report.base_url,
            'execution_mode': report.execution_mode,
            'interrupted': bool(report.interrupted),
            'interrupt_reason': report.interrupt_reason,
            'assertion_strict_mode': bool(report.assertion_strict_mode),
            'summary': summary,
            'details_file': os.path.basename(details_file),
            'results': [
                {
                    'key': ' | '.join([
                        result.get('folder', '') or '-',
                        result.get('name', '') or '-',
                        result.get('method', '') or '-',
                        result.get('url', '') or '-',
                    ]),
                    'name': result.get('name', ''),
                    'folder': result.get('folder', ''),
                    'method': result.get('method', ''),
                    'url': result.get('url', ''),
                    'actual_request_url': result.get('actual_request_url', ''),
                    'item_path': result.get('item_path', []),
                    'expected_status': result.get('expected_status', 200),
                    'status': result.get('status', ''),
                    'status_code': result.get('status_code'),
                    'message': result.get('message', ''),
                    'err_code': result.get('err_code', ''),
                    'response_time_ms': result.get('response_time_ms', 0),
                }
                for result in report.results
            ]
        }


    @staticmethod
    def _generate_index_html(report: Any, summary: SummaryData, total_pages: int, results_per_page: int, total_results: int) -> str:
        """生成索引页面 HTML，使用 Jinja2 模板渲染。"""
        results_data = HtmlReporter._build_index_results_data(report)
        results_json = json.dumps(results_data, ensure_ascii=False).replace("</", "<\\/")
        selected_page_size = HtmlReporter._normalize_index_page_size(report, results_per_page)
        page_size_options_html = HtmlReporter._render_page_size_options(report, selected_page_size)

        env = _get_jinja_env()
        template = env.get_template("report_index.html")
        return template.render(
            summary_total=summary['total'],
            summary_passed=summary['passed'],
            summary_failed=summary['failed'],
            summary_error=summary['error'],
            summary_success_rate=summary['success_rate'],
            summary_duration=summary['duration'],
            summary_start_time=summary['start_time'],
            summary_end_time=summary['end_time'],
            total_pages=total_pages,
            total_results=total_results,
            results_json=results_json,
            page_size=selected_page_size,
            page_size_options_html=page_size_options_html,
        )


    @staticmethod
    def _generate_page_html(report: Any, page: int, results_per_page: int, summary: SummaryData, details_filename: str) -> str:
        """生成分页页面 HTML。"""
        start_idx, end_idx, page_results = HtmlReporter._get_page_window(report, page, results_per_page)
        table_rows = HtmlReporter._build_page_table_rows(report, page_results, start_idx)

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Postman API Test Report - Page {page}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .header {{ background-color: #333; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .summary {{ background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-item {{ display: inline-block; margin-right: 30px; }}
        .summary-item label {{ font-weight: bold; margin-right: 10px; }}
        .filter-section {{ background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .filter-btn {{ padding: 8px 15px; margin-right: 10px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background-color: #f9f9f9; font-size: 14px; }}
        .filter-btn:hover {{ background-color: #e9e9e9; }}
        .filter-btn.active {{ background-color: #333; color: white; }}
        table {{ width: 100%; border-collapse: collapse; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th {{ background-color: #f0f0f0; padding: 12px; text-align: left; font-weight: bold; border-bottom: 2px solid #ddd; }}
        td {{ padding: 12px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background-color: #f9f9f9; }}
        tr.hidden {{ display: none; }}
        .status-passed {{ color: green; font-weight: bold; }}
        .status-failed {{ color: red; font-weight: bold; }}
        .status-error {{ color: orange; font-weight: bold; }}
        .url {{ color: #0066cc; font-family: monospace; }}
        .detail {{ font-size: 12px; color: #666; }}
        .expand-btn {{ cursor: pointer; color: #0066cc; font-weight: bold; padding: 2px 5px; }}
        .expand-btn:hover {{ background-color: #f0f0f0; }}
        .detail-row {{ display: none; background-color: #f9f9f9; }}
        .detail-row.expanded {{ display: table-row; }}
        .detail-content {{ padding: 15px; font-family: monospace; font-size: 12px; background-color: #f5f5f5; border-radius: 4px; margin-top: 10px; overflow-x: auto; }}
        .detail-header {{ font-weight: bold; color: #333; margin-top: 10px; margin-bottom: 5px; }}
        pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
        .loading {{ text-align: center; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Postman API Test Report - Page {page}</h1>
        <p>Page {page} details ({start_idx + 1}-{end_idx} / {len(report.results)})</p>
    </div>

    <div class="summary">
        <div class="summary-item">
            <label>总计:</label>
            <span>{summary['total']}</span>
        </div>
        <div class="summary-item">
            <label style="color: green;">通过:</label>
            <span style="color: green;">{summary['passed']}</span>
        </div>
        <div class="summary-item">
            <label style="color: red;">失败:</label>
            <span style="color: red;">{summary['failed']}</span>
        </div>
        <div class="summary-item">
            <label style="color: orange;">错误:</label>
            <span style="color: orange;">{summary['error']}</span>
        </div>
        <div class="summary-item">
            <label>成功率</label>
            <span>{summary['success_rate']}</span>
        </div>
        <div class="summary-item">
            <label>耗时:</label>
            <span>{summary['duration']}</span>
        </div>
    </div>

    <h2>详细结果</h2>
    <div class="filter-section">
        <button class="filter-btn active" onclick="filterResults('all')">全部</button>
        <button class="filter-btn" onclick="filterResults('PASSED')">√ 成功</button>
        <button class="filter-btn" onclick="filterResults('FAILED')">× 失败</button>
        <button class="filter-btn" onclick="filterResults('ERROR')">! 错误</button>
    </div>

    <table id="resultTable">
        <thead>
            <tr>
                <th>操作</th>
                <th>API名称</th>
                <th>文件夹</th>
                <th>方法</th>
                <th>URL</th>
                <th>状态</th>
                <th>状态码</th>
                <th>详情</th>
            </tr>
        </thead>
        <tbody>
{table_rows}
        </tbody>
    </table>

    <script>
        let detailsCache = {{}};

        function toggleDetail(detailId, resultIdx) {{
            const detailRow = document.getElementById(detailId);
            const btn = event.target;
            const isExpanded = detailRow.classList.contains('expanded');

            if (isExpanded) {{
                detailRow.classList.remove('expanded');
                btn.textContent = '展开详情';
            }} else {{
                detailRow.classList.add('expanded');
                btn.textContent = '收起详情';
                loadDetail(resultIdx);
            }}
        }}

        function loadDetail(resultIdx) {{
            const detailContent = document.getElementById(`detail-content-${{resultIdx}}`);

            if (detailsCache[resultIdx]) {{
                detailContent.innerHTML = detailsCache[resultIdx];
                return;
            }}

            // 加载详情数据
            fetch('{details_filename}')
                .then(response => response.json())
                .then(data => {{
                    const detail = data[resultIdx.toString()];
                    if (detail) {{
                        const requestInfo = detail.request_info || {{}};
                        const responseInfo = detail.response_info || {{}};

                        const requestHeaders = JSON.stringify(requestInfo.headers || {{}}, null, 2);
                        const requestParams = JSON.stringify(requestInfo.params || {{}}, null, 2);
                        const requestBody = typeof requestInfo.body === 'object' ? JSON.stringify(requestInfo.body, null, 2) : (requestInfo.body || '');
                        const responseBody = typeof responseInfo.body === 'object' ? JSON.stringify(responseInfo.body, null, 2) : (responseInfo.body || '');
                        const responseHeaders = JSON.stringify(responseInfo.headers || {{}}, null, 2);

                        const html = `
                            <div class="detail-header">请求信息</div>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">请求头：</div>
                            <pre>${{requestHeaders}}</pre>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">查询参数：</div>
                            <pre>${{requestParams}}</pre>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">请求体：</div>
                            <pre>${{requestBody}}</pre>

                            <div class="detail-header" style="margin-top: 15px;">响应信息</div>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">响应头：</div>
                            <pre>${{responseHeaders}}</pre>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">响应体：</div>
                            <pre>${{responseBody}}</pre>
                        `;

                        detailsCache[resultIdx] = html;
                        detailContent.innerHTML = html;
                    }} else {{
                        detailContent.innerHTML = '<div class="loading">详情数据未找到</div>';
                    }}
                }})
                .catch(error => {{
                    console.error('加载详情失败:', error);
                    detailContent.innerHTML = '<div class="loading">加载详情失败</div>';
                }});
        }}

        function filterResults(status) {{
            const rows = document.querySelectorAll('.result-row');
            rows.forEach(row => {{
                if (status === 'all') {{
                    row.classList.remove('hidden');
                }} else {{
                    if (row.dataset.status === status.toLowerCase()) {{
                        row.classList.remove('hidden');
                    }} else {{
                        row.classList.add('hidden');
                    }}
                }}
            }});

            // 更新按钮状态
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>
"""


    @staticmethod
    def print_console_report(report: Any) -> None:
        """在控制台输出测试报告。"""
        summary = report.generate_summary()

        print("\n" + "="*80)
        print("Postman API 测试报告".center(80))
        print("="*80)
        print(f"\n总计: {summary['total']} | 通过: {summary['passed']} | 失败: {summary['failed']} | 错误: {summary['error']}")
        print(f"成功率: {summary['success_rate']} | 耗时: {summary['duration']}")
        print(f"开始时间: {summary['start_time']} | 结束时间: {summary['end_time']}")

        print("\n" + "-"*80)
        print("详细结果:".ljust(80))
        print("-"*80)

        for result in report.results:
            status_symbol = "PASS" if result['status'] == 'PASSED' else "FAIL" if result['status'] == 'FAILED' else "ERR"
            print(f"[{status_symbol}] {result['name']:30} | {result['method']:6} | {result['status']:8} | {result['status_code'] or '-'}")
            print(f"    URL: {result['url']}")
            print(f"    {result['message']}")

        print("="*80 + "\n")
