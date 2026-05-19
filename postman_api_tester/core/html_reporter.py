"""HTML 报告生成器。

职责：
- 从 PostmanTestReport 生成 HTML/JSON 报告文件
- 控制台报告输出
"""

import json
import logging
import os
import socket
from typing import Any, Dict, List, Optional, Tuple

from postman_api_tester.core.types import SummaryData, DetailsData, IndexResultsData, ReportMetadata
from postman_api_tester.executor import TestResultRecord
from postman_api_tester.utils.security import sanitize_headers

logger = logging.getLogger(__name__)


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
        table_rows = ""
        for idx, result in enumerate(page_results):
            global_idx = start_idx + idx
            status_class = f"status-{result['status'].lower()}"
            status_lower = result['status'].lower()
            detail_id = f"detail-{global_idx}"

            table_rows += f"""
            <tr class="result-row result-{status_lower}" data-status="{status_lower}">
                <td><span class="expand-btn" onclick="toggleDetail('{detail_id}', {global_idx})">详情</span></td>
                <td>{result['name']}</td>
                <td>{result.get('folder', '-')}</td>
                <td>{result['method']}</td>
                <td><span class="url">{result['url']}</span></td>
                <td><span class="{status_class}">{result['status']}</span></td>
                <td>{result['status_code'] or '-'}</td>
                <td><span class="detail">{result['message']}</span></td>
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
        details_data = HtmlReporter._build_details_data(report, )
        
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
        """生成索引页面 HTML，支持客户端分页与每页条数切换。"""
        # 准备结果数据 JSON（包含详情信息）
        results_data = HtmlReporter._build_index_results_data(report, )
        results_json = json.dumps(results_data, ensure_ascii=False)
        selected_page_size = HtmlReporter._normalize_index_page_size(report, results_per_page)
        page_size_options_html = HtmlReporter._render_page_size_options(report, selected_page_size)
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Postman API 测试报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px; }}
        
        .header {{ background-color: #333; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .header h1 {{ margin-bottom: 5px; }}
        
        .summary {{ background-color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; }}
        .summary-item {{ padding: 10px; }}
        .summary-item label {{ font-weight: bold; display: block; margin-bottom: 5px; color: #666; }}
        .summary-item span {{ font-size: 24px; font-weight: bold; }}
        .summary-item.passed span {{ color: green; }}
        .summary-item.failed span {{ color: red; }}
        .summary-item.error span {{ color: orange; }}
        
        .controls {{ background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .control-row {{ display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
        .control-item {{ display: flex; align-items: center; gap: 10px; }}
        .control-item label {{ font-weight: bold; }}
        .control-item select {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }}
        .control-item select:hover {{ background-color: #f9f9f9; }}
        .control-item input[type="text"] {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; min-width: 200px; }}
        .search-item {{ display: flex; align-items: center; gap: 5px; }}
        .search-item input {{ flex: 1; min-width: 200px; }}
        .search-item button {{ padding: 8px 15px; background-color: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
        .search-item button:hover {{ background-color: #0052a3; }}
        .token-item {{ display: flex; align-items: center; gap: 5px; }}
        .token-item input {{ flex: 1; min-width: 250px; }}
        .token-item button {{ padding: 8px 15px; background-color: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
        .token-item button:hover {{ background-color: #218838; }}
        .filter-btn {{ padding: 8px 15px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background-color: #f9f9f9; font-size: 14px; }}
        .filter-btn:hover {{ background-color: #e9e9e9; }}
        .filter-btn.active {{ background-color: #333; color: white; border-color: #333; }}
        
        .results-section {{ background-color: white; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; }}
        
        table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
        th {{ background-color: #f0f0f0; padding: 10px 12px; text-align: left; font-weight: bold; border-bottom: 2px solid #ddd; overflow: hidden; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #ddd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }}
        td.td-wrap {{ white-space: normal; overflow: visible; max-width: none; }}
        tr:hover {{ background-color: #f9f9f9; }}
        .status-passed {{ color: green; font-weight: bold; }}
        .status-failed {{ color: red; font-weight: bold; }}
        .status-error {{ color: orange; font-weight: bold; }}
        .url {{ color: #0066cc; font-family: monospace; }}
        .expand-btn {{ cursor: pointer; color: #0066cc; font-weight: bold; padding: 2px 8px; }}
        .expand-btn:hover {{ background-color: #e9e9e9; border-radius: 3px; }}
        td.msg-td {{ cursor: pointer; }}
        td.msg-td:hover {{ background-color: #fff8e1; }}
        td.msg-td.msg-expanded {{ white-space: normal !important; overflow: visible !important; max-width: none !important; word-break: break-word; background-color: #fff8e1; }}
        td.msg-td.msg-failed-color {{ color: #c0392b; }}
        
        .detail-row {{ display: none; background-color: #f9f9f9; }}
        .detail-row.expanded {{ display: table-row; }}
        .detail-content {{ padding: 15px; font-family: monospace; font-size: 12px; background-color: #f5f5f5; border-radius: 4px; overflow-x: auto; }}
        .detail-header {{ font-weight: bold; color: #333; margin-top: 10px; margin-bottom: 5px; }}
        pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
        
        .pagination-section {{ background-color: white; padding: 15px; border-radius: 5px; margin-top: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
        .pagination-info {{ margin-bottom: 15px; color: #666; }}
        .page-buttons {{ display: flex; gap: 5px; justify-content: center; flex-wrap: wrap; }}
        .page-btn {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background-color: #f9f9f9; font-size: 13px; }}
        .page-btn:hover {{ background-color: #e9e9e9; }}
        .page-btn.active {{ background-color: #333; color: white; }}
        .page-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        
        .loading {{ text-align: center; padding: 20px; color: #666; }}
        .no-data {{ text-align: center; padding: 30px; color: #999; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Postman API 测试报告</h1>
        <p>自动化接口测试结果汇总 - 优化版</p>
    </div>
    
    <div class="summary">
        <div class="summary-grid">
            <div class="summary-item">
                <label>总计</label>
                <span>{summary['total']}</span>
            </div>
            <div class="summary-item passed">
                <label>√ 通过</label>
                <span>{summary['passed']}</span>
            </div>
            <div class="summary-item failed">
                <label>× 失败</label>
                <span>{summary['failed']}</span>
            </div>
            <div class="summary-item error">
                <label>! 错误</label>
                <span>{summary['error']}</span>
            </div>
            <div class="summary-item">
                <label>成功率</label>
                <span>{summary['success_rate']}</span>
            </div>
            <div class="summary-item">
                <label>耗时</label>
                <span>{summary['duration']}</span>
            </div>
        </div>
        <div style="margin-top: 15px; font-size: 12px; color: #666;">
            开始: {summary['start_time']} | 结束: {summary['end_time']}
        </div>
    </div>
    
    <div class="controls">
        <div class="control-row">
            <div class="search-item">
                <label for="search-input">搜索:</label>
                <input type="text" id="search-input" placeholder="输入API名称、路径、文件夹进行搜索..." onkeyup="performSearch()">
                <button onclick="clearSearch()">清空</button>
            </div>
        </div>
        <div class="control-row">
            <div class="token-item">
                <label for="token-input">Token:</label>
                <input type="text" id="token-input" placeholder="输入认证 token（可选，用于重新请求接口）">
                <button id="test-token-btn" onclick="testToken()">测试Token</button>
            </div>
        </div>
        <div class="control-row">
            <div class="control-item">
                <label for="page-size">每页显示:</label>
                <select id="page-size" onchange="changePageSize()">
                    {page_size_options_html}
                </select>
            </div>
            <div class="control-item">
                <label>状态筛选:</label>
                <button class="filter-btn active" onclick="filterResults('all', this)">全部</button>
                <button class="filter-btn" onclick="filterResults('PASSED', this)">√ 成功</button>
                <button class="filter-btn" onclick="filterResults('FAILED', this)">× 失败</button>
                <button class="filter-btn" onclick="filterResults('ERROR', this)">! 错误</button>
            </div>
        </div>
    </div>
    
    <div class="results-section">
        <div id="table-container">
            <div class="loading">加载数据中...</div>
        </div>
    </div>
    
    <div class="pagination-section">
        <div class="pagination-info" id="pagination-info">第 1 页 | 共 {total_pages} 页 | 共 {total_results} 条数据</div>
        <div class="page-buttons" id="pagination-buttons"></div>
    </div>
    
    <script>
        let allResults = {results_json};
        let filteredResults = allResults;
        let currentPage = 1;
        let pageSize = {selected_page_size};
        let currentFilter = 'all';
        let searchQuery = '';
        let detailCache = {{}};
        let currentToken = '';
        
        // 初始化
        function init() {{
            changePageSize();
            renderTable();
        }}
        
        // 执行搜索
        function performSearch() {{
            searchQuery = document.getElementById('search-input').value.toLowerCase().trim();
            currentPage = 1;
            applyFilters();
        }}
        
        // 清空搜索
        function clearSearch() {{
            document.getElementById('search-input').value = '';
            searchQuery = '';
            currentPage = 1;
            applyFilters();
        }}

        function applyStatusFilter(results) {{
            if (currentFilter === 'all') {{
                return results;
            }}
            return results.filter(r => r.status === currentFilter);
        }}

        function applySearchFilter(results) {{
            if (!searchQuery) {{
                return results;
            }}
            return results.filter(r => {{
                const searchFields = [
                    r.name,
                    r.url,
                    r.folder || '',
                    r.method
                ].map(f => (f || '').toLowerCase());
                return searchFields.some(field => field.includes(searchQuery));
            }});
        }}
        
        // 应用所有过滤条件
        function applyFilters() {{
            const statusFiltered = applyStatusFilter(allResults);
            filteredResults = applySearchFilter(statusFiltered);
            renderTable();
        }}
        
        // 改变每页显示数量
        function changePageSize() {{
            pageSize = parseInt(document.getElementById('page-size').value);
            currentPage = 1;
            renderTable();
        }}

        function setActiveFilterButton(activeButton) {{
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            if (activeButton) {{
                activeButton.classList.add('active');
            }}
        }}

        function getCurrentPageData() {{
            const totalPages = getTotalPages();
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            return {{
                totalPages,
                start,
                pageData: filteredResults.slice(start, end),
            }};
        }}

        function buildResultRows(pageData, startIndex) {{
            let html = '';
            pageData.forEach((result, idx) => {{
                const globalIdx = startIndex + idx;
                const statusClass = `status-${{result.status.toLowerCase()}}`;
                const detailId = `detail-${{globalIdx}}`;

                html += `
                    <tr data-result-idx="${{globalIdx}}">
                        <td><span class="expand-btn" onclick="toggleDetail('${{detailId}}', ${{globalIdx}}, this)">展开</span></td>
                        <td title="${{result.name}}">${{result.name}}</td>
                        <td title="${{result.folder || '-'}}">${{result.folder || '-'}}</td>
                        <td><strong>${{result.method}}</strong></td>
                        <td title="${{result.url}}"><span class="url">${{result.url}}</span></td>
                        <td><span class="${{statusClass}}">${{result.status}}</span></td>
                        <td>${{result.status_code || '-'}}</td>
                        <td class="msg-td ${{result.status === 'FAILED' || result.status === 'ERROR' ? 'msg-failed-color' : ''}}" title="\u70b9\u51fb\u5c55\u5f00/\u6536\u8d77\u5b8c\u6574\u5185\u5bb9" onclick="toggleMsgCell(this)">${{result.message || '-'}}</td>
                    </tr>
                    <tr class="detail-row" id="${{detailId}}">
                        <td class="td-wrap" colspan="8">
                            <div class="detail-content" id="detail-content-${{globalIdx}}">
                                <div class="loading">加载详情中...</div>
                            </div>
                        </td>
                    </tr>
                `;
            }});
            return html;
        }}

        function buildResultsTable(pageData, startIndex) {{
            return `
                <table>
                    <colgroup>
                        <col style="width: 60px;">
                        <col style="width: 12%;">
                        <col style="width: 10%;">
                        <col style="width: 60px;">
                        <col style="width: 22%;">
                        <col style="width: 70px;">
                        <col style="width: 60px;">
                        <col>
                    </colgroup>
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
                        ${{buildResultRows(pageData, startIndex)}}
                    </tbody>
                </table>
            `;
        }}
        
        // 筛选结果
        function filterResults(status, activeButton) {{
            currentFilter = status;
            currentPage = 1;
            setActiveFilterButton(activeButton || null);
            
            applyFilters();
        }}

        function getTotalPages() {{
            return Math.ceil(filteredResults.length / pageSize);
        }}
        
        // 渲染表格
        function renderTable() {{
            const pageState = getCurrentPageData();
            const totalPages = pageState.totalPages;
            const startIndex = pageState.start;
            const pageData = pageState.pageData;
            
            if (filteredResults.length === 0) {{
                document.getElementById('table-container').innerHTML = '<div class="no-data">没有符合条件的数据</div>';
                updatePagination(0, 0);
                return;
            }}
            
            document.getElementById('table-container').innerHTML = buildResultsTable(pageData, startIndex);
            updatePagination(totalPages, filteredResults.length);
        }}
        
        function buildPaginationButtons(totalPages) {{
            let buttons = '';

            // 上一页
            buttons += `<button class="page-btn" onclick="goPage(${{currentPage - 1}})" ${{currentPage === 1 ? 'disabled' : ''}}>上一页</button>`;

            // 椤电爜
            const maxPages = 10;
            let startPage = Math.max(1, currentPage - Math.floor(maxPages / 2));
            let endPage = Math.min(totalPages, startPage + maxPages - 1);
            startPage = Math.max(1, endPage - maxPages + 1);

            if (startPage > 1) buttons += '<button class="page-btn" onclick="goPage(1)">1</button>';
            if (startPage > 2) buttons += '<span style="padding: 8px 5px;">...</span>';

            for (let i = startPage; i <= endPage; i++) {{
                const active = i === currentPage ? 'active' : '';
                buttons += `<button class="page-btn ${{active}}" onclick="goPage(${{i}})">${{i}}</button>`;
            }}

            if (endPage < totalPages - 1) buttons += '<span style="padding: 8px 5px;">...</span>';
            if (endPage < totalPages) buttons += `<button class="page-btn" onclick="goPage(${{totalPages}})">${{totalPages}}</button>`;

            // 下一页
            buttons += `<button class="page-btn" onclick="goPage(${{currentPage + 1}})" ${{currentPage === totalPages ? 'disabled' : ''}}>下一页</button>`;
            return buttons;
        }}

        // 更新分页信息和按钮
        function updatePagination(totalPages, totalItems) {{
            document.getElementById('pagination-info').textContent = 
                `第 ${{currentPage}} 页 | 共 ${{totalPages}} 页 | 共 ${{totalItems}} 条数据`;

            document.getElementById('pagination-buttons').innerHTML = buildPaginationButtons(totalPages);
        }}
        
        // 跳转到指定页
        function goPage(page) {{
            const totalPages = getTotalPages();
            if (page >= 1 && page <= totalPages) {{
                currentPage = page;
                renderTable();
                window.scrollTo(0, 0);
            }}
        }}
        
        // 切换消息列展开/收起
        function toggleMsgCell(td) {{
            td.classList.toggle('msg-expanded');
            td.title = td.classList.contains('msg-expanded') ? '\u70b9\u51fb\u6536\u8d77' : '\u70b9\u51fb\u5c55\u5f00/\u6536\u8d77\u5b8c\u6574\u5185\u5bb9';
        }}
        
        // 切换详情显示
        function toggleDetail(detailId, resultIdx, triggerEl) {{
            const detailRow = document.getElementById(detailId);
            const btn = triggerEl;
            const isExpanded = detailRow.classList.contains('expanded');
            
            if (isExpanded) {{
                detailRow.classList.remove('expanded');
                btn.textContent = '展开';
            }} else {{
                detailRow.classList.add('expanded');
                btn.textContent = '收起';
                loadDetail(resultIdx);
            }}
        }}
        
        // 加载详情数据（从内存直接加载，无需 AJAX）
        function loadDetail(resultIdx) {{
            const detailContent = document.getElementById(`detail-content-${{resultIdx}}`);
            
            // 检查缓存
            if (detailCache[resultIdx]) {{
                detailContent.innerHTML = detailCache[resultIdx];
                return;
            }}
            
            // 从全局结果中查找目标项
            const result = allResults[resultIdx];
            if (!result) {{
                const html = '<div class="loading">详情数据未找到</div>';
                detailCache[resultIdx] = html;
                detailContent.innerHTML = html;
                return;
            }}
            
            try {{
                const requestInfo = result.request_info || {{}};
                const responseInfo = result.response_info || {{}};
                
                const requestHeaders = JSON.stringify(requestInfo.headers || {{}}, null, 2) || '无';
                const requestParams = JSON.stringify(requestInfo.params || {{}}, null, 2) || '无';
                const requestBody = typeof requestInfo.body === 'object' ? JSON.stringify(requestInfo.body, null, 2) : (requestInfo.body || '无');
                const responseBody = typeof responseInfo.body === 'object' ? JSON.stringify(responseInfo.body, null, 2) : (responseInfo.body || '无');
                const responseHeaders = JSON.stringify(responseInfo.headers || {{}}, null, 2) || '无';
                
                const html = `
                    <div style="margin-bottom: 15px; padding: 10px; background-color: #e8f5e8; border-radius: 4px; border-left: 4px solid #28a745;">
                        <strong>提示：</strong>如果看到 "session 已经过期" 错误，可输入 token 后点击“重新请求”重试该接口。
                        <button onclick="reRequestApi(` + resultIdx + `)" style="margin-left: 10px; padding: 5px 10px; background-color: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 12px;">重新请求</button>
                    </div>
                    
                    <div class="detail-header">请求信息</div>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">请求头：</div>
                    <pre>${{requestHeaders}}</pre>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">查询参数：</div>
                    <pre>${{requestParams}}</pre>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">请求体：</div>
                    <pre>${{requestBody}}</pre>
                    
                    <div class="detail-header" style="margin-top: 15px;">响应信息</div>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">响应头：</div>
                    <pre>${{responseHeaders}}</pre>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">响应体：</div>
                    <pre>${{responseBody}}</pre>
                `;
                
                detailCache[resultIdx] = html;
                detailContent.innerHTML = html;
            }} catch (error) {{
                const html = '<div class="loading">详情加载失败: ' + error.message + '</div>';
                detailCache[resultIdx] = html;
                detailContent.innerHTML = html;
            }}
        }}
        
        // 测试 Token 有效性
        async function testToken() {{
            const token = document.getElementById('token-input').value.trim();
            if (!token) {{
                alert('请先输入Token！');
                document.getElementById('token-input').focus();
                return;
            }}
            
            const testBtn = document.getElementById('test-token-btn');
            const originalText = testBtn.textContent;
            testBtn.textContent = '测试中...';
            testBtn.disabled = true;
            
            try {{
                // 发送测试请求
                const response = await fetch('/test-token', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{ token: token }})
                }});
                
                const result = await response.json();
                
                if (result.success) {{
                    alert('Token 有效');
                    testBtn.textContent = 'Token 有效';
                    testBtn.style.backgroundColor = '#28a745';
                }} else {{
                    alert('Token 无效: ' + (result.message || '未知错误'));
                    testBtn.textContent = '✗ Token无效';
                    testBtn.style.backgroundColor = '#dc3545';
                }}
                
            }} catch (error) {{
                alert('Token 测试失败: ' + error.message);
                testBtn.textContent = '测试失败';
                testBtn.style.backgroundColor = '#dc3545';
                console.error('Token test error:', error);
            }} finally {{
                testBtn.disabled = false;
                setTimeout(() => {{
                    testBtn.textContent = originalText;
                    testBtn.style.backgroundColor = '';
                }}, 3000);
            }}
        }}
        
        // 重新请求 API
        async function reRequestApi(resultIdx) {{
            const token = document.getElementById('token-input').value.trim();
            if (!token) {{
                alert('请先输入Token！');
                document.getElementById('token-input').focus();
                return;
            }}
            
            const result = allResults[resultIdx];
            if (!result) {{
                alert('测试结果未找到！');
                return;
            }}
            
            // 显示加载状态
            const detailContent = document.getElementById(`detail-content-${{resultIdx}}`);
            detailContent.innerHTML = '<div class="loading">正在重新请求...</div>';
            
            try {{
                // 准备请求数据
                const requestData = {{
                    url: result.url,
                    method: result.method,
                    headers: result.request_info?.headers || {{}},
                    params: result.request_info?.params || {{}},
                    body: result.request_info?.body || null,
                    token: token
                }};
                
                // 发送请求到后端重新测试
                const response = await fetch('/re-request-api', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify(requestData)
                }});
                
                if (!response.ok) {{
                    throw new Error(`HTTP ${{response.status}}: ${{response.statusText}}`);
                }}
                
                const newResult = await response.json();
                
                // 更新结果数据
                allResults[resultIdx] = newResult;
                
                // 清除缓存并重新加载详情
                delete detailCache[resultIdx];
                loadDetail(resultIdx);
                
                    // 更新表格中的状态
                const row = document.querySelector(`tr[data-result-idx="${{resultIdx}}"]`);
                if (row) {{
                    const statusCell = row.querySelector('td:nth-child(6) span');
                    const codeCell = row.querySelector('td:nth-child(7)');
                    const messageCell = row.querySelector('td:nth-child(8) span');
                    
                    if (statusCell) {{
                        statusCell.className = `status-${{newResult.status.toLowerCase()}}`;
                        statusCell.textContent = newResult.status;
                    }}
                    if (codeCell) {{
                        codeCell.textContent = newResult.status_code || '-';
                    }}
                    if (messageCell) {{
                        messageCell.textContent = newResult.message;
                    }}
                    
                    // 更新行样式
                    row.className = `result-row result-${{newResult.status.toLowerCase()}}`;
                    row.setAttribute('data-status', newResult.status.toLowerCase());
                }}
                
                alert('重新请求完成');
                
            }} catch (error) {{
                detailContent.innerHTML = `<div class="loading" style="color: red;">重新请求失败: ${{error.message}}</div>`;
                console.error('Re-request error:', error);
            }}
        }}
        
        // 页面加载完成后初始化
        window.addEventListener('DOMContentLoaded', init);
    </script>
</body>
</html>
"""
    

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

