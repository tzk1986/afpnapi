"""Postman API 测试主模块。

用于读取 APIFox/Postman 导出的接口文件，执行测试并生成报告。
"""

import json
import logging
import os
import socket
import sys
import hashlib
from typing import Dict, List, Any, Optional, Callable, Tuple
from datetime import datetime
import re
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from postman_api_tester.runtime_utils import (
    checkpoint_file_path as _checkpoint_file_path,
    compute_collection_fingerprint as _compute_collection_fingerprint,
    item_path_text as _item_path_text,
    load_checkpoint as _load_checkpoint,
    save_checkpoint_atomic as _save_checkpoint_atomic,
)
from postman_api_tester.exceptions import ValidationError
from postman_api_tester.auth import get_auth_token
from postman_api_tester.parser import PostmanApiParser
from postman_api_tester.executor import PostmanTestExecutor
from postman_api_tester.utils.security import sanitize_headers
from postman_api_tester.session import SessionLike, RequestTimeout, create_shared_session, close_session, normalize_timeout, resolve_request_timeout

logger = logging.getLogger(__name__)

class PostmanTestReport:
    """Postman 测试报告生成器。"""
    
    def __init__(self):
        self.results = []
        self.start_time = datetime.now()
        self.end_time = None
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
        self._summary_cache: Optional[Dict[str, Any]] = None
    
    def add_result(self, result: Dict):
        """添加单条测试结果。"""
        self.results.append(result)
        self._summary_cache = None
    
    def add_results(self, results: List[Dict]):
        """批量添加测试结果。"""
        self.results.extend(results)
        self._summary_cache = None
    
    def generate_summary(self) -> Dict:
        """生成测试摘要。"""
        if self._summary_cache is not None:
            return dict(self._summary_cache)

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

        summary = {
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
        return dict(summary)

    def _build_details_data(self) -> Dict[str, Dict[str, Any]]:
        """构建详情数据并执行请求头脱敏。"""
        details_data: Dict[str, Dict[str, Any]] = {}
        for idx, result in enumerate(self.results):
            req_info = result.get('request_info', {})
            raw_req_headers = req_info.get('headers', {}) or {}
            sanitized_headers = sanitize_headers(raw_req_headers, mask='***')
            details_data[str(idx)] = {
                'request_info': {**req_info, 'headers': sanitized_headers},
                'response_info': result.get('response_info', {}),
            }
        return details_data

    def _write_json_file(self, file_path: str, payload: Any) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _write_text_file(self, file_path: str, content: str) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def _write_report_pages(
        self,
        *,
        base_name: str,
        total_pages: int,
        results_per_page: int,
        summary: Dict,
        details_file_name: str,
    ) -> None:
        for page in range(1, total_pages + 1):
            page_content = self._generate_page_html(page, results_per_page, summary, details_file_name)
            page_path = f"{base_name}_page_{page}.html"
            self._write_text_file(page_path, page_content)

    def _build_index_results_data(self) -> List[Dict[str, Any]]:
        """构建首页报告表格数据（包含详情字段）。"""
        results_data: List[Dict[str, Any]] = []
        for result in self.results:
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

    def _normalize_index_page_size(self, results_per_page: int) -> int:
        """规范首页每页数量，确保与下拉选项一致。"""
        page_size_options = {20, 30, 50, 100, 200}
        return results_per_page if results_per_page in page_size_options else 20

    def _render_page_size_options(self, selected_page_size: int) -> str:
        option_values = [20, 30, 50, 100, 200]
        options: List[str] = []
        for value in option_values:
            selected = ' selected' if value == selected_page_size else ''
            options.append(f'<option value="{value}"{selected}>{value}鏉?/option>')
        return '\n                    '.join(options)

    def _get_page_window(self, page: int, results_per_page: int) -> Tuple[int, int, List[Dict[str, Any]]]:
        """返回分页窗口和当前页结果。"""
        start_idx = (page - 1) * results_per_page
        end_idx = min(page * results_per_page, len(self.results))
        page_results = self.results[start_idx:end_idx]
        return start_idx, end_idx, page_results

    def _build_page_table_rows(self, page_results: List[Dict[str, Any]], start_idx: int) -> str:
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
    
    def generate_html_report(self, output_path: str, results_per_page: int = 30):
        """生成 HTML 报告。"""
        summary = self.generate_summary()
        output_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else '.'
        os.makedirs(output_dir, exist_ok=True)
        
        # 璁＄畻鍒嗛〉
        total_results = len(self.results)
        total_pages = (total_results + results_per_page - 1) // results_per_page
        details_data = self._build_details_data()
        
        # 保存详情 JSON 文件
        base_name = os.path.splitext(output_path)[0]
        details_file = f"{base_name}_details.json"
        self._write_json_file(details_file, details_data)

        meta_file = f"{base_name}_meta.json"
        self._write_json_file(meta_file, self._build_report_metadata(summary, output_path, details_file))
        
        # 生成索引页面
        index_content = self._generate_index_html(summary, total_pages, results_per_page, total_results)
        self._write_text_file(output_path, index_content)
        
        # 生成分页页面
        self._write_report_pages(
            base_name=base_name,
            total_pages=total_pages,
            results_per_page=results_per_page,
            summary=summary,
            details_file_name=os.path.basename(details_file),
        )

        self.generated_report_file = output_path
        self.generated_details_file = details_file
        self.generated_meta_file = meta_file

    def _build_report_metadata(self, summary: Dict, output_path: str, details_file: str) -> Dict[str, Any]:
        """鏋勫缓鍘嗗彶鎶ュ憡鍜屽樊寮傛瘮瀵规墍闇€鐨勭粨鏋勫寲鍏冩暟鎹€"""
        return {
            'report_name': os.path.basename(output_path),
            'generated_at': summary['end_time'],
            'host_name': socket.gethostname(),
            'collection_name': self.collection_name,
            'source_file': self.source_file,
            'source_original_file': self.source_original_file,
            'base_url': self.base_url,
            'execution_mode': self.execution_mode,
            'interrupted': bool(self.interrupted),
            'interrupt_reason': self.interrupt_reason,
            'assertion_strict_mode': bool(self.assertion_strict_mode),
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
                for result in self.results
            ]
        }
    
    def _generate_index_html(self, summary: Dict, total_pages: int, results_per_page: int, total_results: int) -> str:
        """生成索引页面 HTML，支持客户端分页与每页条数切换。"""
        # 准备结果数据 JSON（包含详情信息）
        results_data = self._build_index_results_data()
        results_json = json.dumps(results_data, ensure_ascii=False)
        selected_page_size = self._normalize_index_page_size(results_per_page)
        page_size_options_html = self._render_page_size_options(selected_page_size)
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Postman API 娴嬭瘯鎶ュ憡</title>
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
        <h1>Postman API 娴嬭瘯鎶ュ憡</h1>
        <p>鑷姩鍖栨帴鍙ｆ祴璇曠粨鏋滄眹鎬?- 浼樺寲鐗?/p>
    </div>
    
    <div class="summary">
        <div class="summary-grid">
            <div class="summary-item">
                <label>鎬昏</label>
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
                <label>鑰楁椂</label>
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
                <input type="text" id="search-input" placeholder="杈撳叆API鍚嶇О銆佽矾寰勩€佹枃浠跺す杩涜鎼滅储..." onkeyup="performSearch()">
                <button onclick="clearSearch()">娓呯┖</button>
            </div>
        </div>
        <div class="control-row">
            <div class="token-item">
                <label for="token-input">Token:</label>
                <input type="text" id="token-input" placeholder="输入认证 token（可选，用于重新请求接口）">
                <button id="test-token-btn" onclick="testToken()">娴嬭瘯Token</button>
            </div>
        </div>
        <div class="control-row">
            <div class="control-item">
                <label for="page-size">姣忛〉鏄剧ず:</label>
                <select id="page-size" onchange="changePageSize()">
                    {page_size_options_html}
                </select>
            </div>
            <div class="control-item">
                <label>鐘舵€佺瓫閫?</label>
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
        <div class="pagination-info" id="pagination-info">绗?1 椤?| 鍏?{total_pages} 椤?| 鍏?{total_results} 鏉℃暟鎹?/div>
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
        
        // 鍒濆鍖?
        function init() {{
            changePageSize();
            renderTable();
        }}
        
        // 鎵ц鎼滅储
        function performSearch() {{
            searchQuery = document.getElementById('search-input').value.toLowerCase().trim();
            currentPage = 1;
            applyFilters();
        }}
        
        // 娓呯┖鎼滅储
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
        
        // 搴旂敤鎵€鏈夎繃婊ゆ潯浠?
        function applyFilters() {{
            const statusFiltered = applyStatusFilter(allResults);
            filteredResults = applySearchFilter(statusFiltered);
            renderTable();
        }}
        
        // 鏀瑰彉姣忛〉鏄剧ず鏁伴噺
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
                        <td><span class="expand-btn" onclick="toggleDetail('${{detailId}}', ${{globalIdx}}, this)">鈻?灞曞紑</span></td>
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
                            <th>API鍚嶇О</th>
                            <th>鏂囦欢澶?/th>
                            <th>鏂规硶</th>
                            <th>URL</th>
                            <th>鐘舵€?/th>
                            <th>鐘舵€佺爜</th>
                            <th>详情</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${{buildResultRows(pageData, startIndex)}}
                    </tbody>
                </table>
            `;
        }}
        
        // 绛涢€夌粨鏋?
        function filterResults(status, activeButton) {{
            currentFilter = status;
            currentPage = 1;
            setActiveFilterButton(activeButton || null);
            
            applyFilters();
        }}

        function getTotalPages() {{
            return Math.ceil(filteredResults.length / pageSize);
        }}
        
        // 娓叉煋琛ㄦ牸
        function renderTable() {{
            const pageState = getCurrentPageData();
            const totalPages = pageState.totalPages;
            const startIndex = pageState.start;
            const pageData = pageState.pageData;
            
            if (filteredResults.length === 0) {{
                document.getElementById('table-container').innerHTML = '<div class="no-data">娌℃湁绗﹀悎鏉′欢鐨勬暟鎹?/div>';
                updatePagination(0, 0);
                return;
            }}
            
            document.getElementById('table-container').innerHTML = buildResultsTable(pageData, startIndex);
            updatePagination(totalPages, filteredResults.length);
        }}
        
        function buildPaginationButtons(totalPages) {{
            let buttons = '';

            // 涓婁竴椤?
            buttons += `<button class="page-btn" onclick="goPage(${{currentPage - 1}})" ${{currentPage === 1 ? 'disabled' : ''}}>芦 涓婁竴椤?/button>`;

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

            // 涓嬩竴椤?
            buttons += `<button class="page-btn" onclick="goPage(${{currentPage + 1}})" ${{currentPage === totalPages ? 'disabled' : ''}}>涓嬩竴椤?禄</button>`;
            return buttons;
        }}

        // 鏇存柊鍒嗛〉淇℃伅鍜屾寜閽?
        function updatePagination(totalPages, totalItems) {{
            document.getElementById('pagination-info').textContent = 
                `绗?${{currentPage}} 椤?| 鍏?${{totalPages}} 椤?| 鍏?${{totalItems}} 鏉℃暟鎹甡;

            document.getElementById('pagination-buttons').innerHTML = buildPaginationButtons(totalPages);
        }}
        
        // 杞埌鎸囧畾椤?
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
                btn.textContent = '鈻?灞曞紑';
            }} else {{
                detailRow.classList.add('expanded');
                btn.textContent = '鈻?鏀惰捣';
                loadDetail(resultIdx);
            }}
        }}
        
        // 加载详情数据（从内存直接加载，无需 AJAX）
        function loadDetail(resultIdx) {{
            const detailContent = document.getElementById(`detail-content-${{resultIdx}}`);
            
            // 妫€鏌ョ紦瀛?
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
                
                const requestHeaders = JSON.stringify(requestInfo.headers || {{}}, null, 2) || '鏃?;
                const requestParams = JSON.stringify(requestInfo.params || {{}}, null, 2) || '鏃?;
                const requestBody = typeof requestInfo.body === 'object' ? JSON.stringify(requestInfo.body, null, 2) : (requestInfo.body || '鏃?);
                const responseBody = typeof responseInfo.body === 'object' ? JSON.stringify(responseInfo.body, null, 2) : (responseInfo.body || '鏃?);
                const responseHeaders = JSON.stringify(responseInfo.headers || {{}}, null, 2) || '鏃?;
                
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
        
        // 娴嬭瘯Token鏈夋晥鎬?
        async function testToken() {{
            const token = document.getElementById('token-input').value.trim();
            if (!token) {{
                alert('璇峰厛杈撳叆Token锛?);
                document.getElementById('token-input').focus();
                return;
            }}
            
            const testBtn = document.getElementById('test-token-btn');
            const originalText = testBtn.textContent;
            testBtn.textContent = '娴嬭瘯涓?..';
            testBtn.disabled = true;
            
            try {{
                // 鍙戦€佹祴璇曡姹?
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
                    testBtn.textContent = '鉂?Token鏃犳晥';
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
                alert('璇峰厛杈撳叆Token锛?);
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
                
                // 鍙戦€佽姹傚埌鍚庣閲嶆柊娴嬭瘯
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
                
                // 娓呴櫎缂撳瓨锛岄噸鏂板姞杞借鎯?
                delete detailCache[resultIdx];
                loadDetail(resultIdx);
                
                // 鏇存柊琛ㄦ牸涓殑鐘舵€?
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
                    
                    // 鏇存柊琛屾牱寮?
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
    
    def _generate_page_html(self, page: int, results_per_page: int, summary: Dict, details_filename: str) -> str:
        """生成分页页面 HTML。"""
        start_idx, end_idx, page_results = self._get_page_window(page, results_per_page)
        table_rows = self._build_page_table_rows(page_results, start_idx)
        
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
        <p>Page {page} details ({start_idx + 1}-{end_idx} / {len(self.results)})</p>
    </div>
    
    <div class="summary">
        <div class="summary-item">
            <label>鎬昏:</label>
            <span>{summary['total']}</span>
        </div>
        <div class="summary-item">
            <label style="color: green;">閫氳繃:</label>
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
            <label>鑰楁椂:</label>
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
                <th>API鍚嶇О</th>
                <th>鏂囦欢澶?/th>
                <th>鏂规硶</th>
                <th>URL</th>
                <th>鐘舵€?/th>
                <th>鐘舵€佺爜</th>
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
            
            // 鏇存柊鎸夐挳鐘舵€?
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>
"""
    
    def print_console_report(self):
        """鍦ㄦ帶鍒跺彴杈撳嚭娴嬭瘯鎶ュ憡"""
        summary = self.generate_summary()
        
        print("\n" + "="*80)
        print("Postman API 娴嬭瘯鎶ュ憡".center(80))
        print("="*80)
        print(f"\n总计: {summary['total']} | 通过: {summary['passed']} | 失败: {summary['failed']} | 错误: {summary['error']}")
        print(f"成功率: {summary['success_rate']} | 耗时: {summary['duration']}")
        print(f"开始时间: {summary['start_time']} | 结束时间: {summary['end_time']}")
        
        print("\n" + "-"*80)
        print("详细结果:".ljust(80))
        print("-"*80)
        
        for result in self.results:
            status_symbol = "PASS" if result['status'] == 'PASSED' else "FAIL" if result['status'] == 'FAILED' else "ERR"
            print(f"[{status_symbol}] {result['name']:30} | {result['method']:6} | {result['status']:8} | {result['status_code'] or '-'}")
            print(f"    URL: {result['url']}")
            print(f"    {result['message']}")
        
        print("="*80 + "\n")


def _resolve_runtime_config(
    token: Optional[str],
    base_url: Optional[str],
    output_dir: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], bool, int, str, bool]:
    enable_checkpoint_recovery = False
    checkpoint_flush_every_n = 1
    checkpoint_dir = ""
    assertion_strict_mode = False

    try:
        from postman_api_tester import config as _cfg
        if token is None and getattr(_cfg, 'TOKEN', ''):
            token = _cfg.TOKEN.strip() or None
        if base_url is None and getattr(_cfg, 'BASE_URL', ''):
            base_url = _cfg.BASE_URL.strip() or None
        if output_dir is None and getattr(_cfg, 'REPORT_OUTPUT_DIR', ''):
            output_dir = _cfg.REPORT_OUTPUT_DIR.strip() or None
        enable_checkpoint_recovery = bool(getattr(_cfg, 'ENABLE_CHECKPOINT_RECOVERY', False))
        checkpoint_flush_every_n = max(1, int(getattr(_cfg, 'CHECKPOINT_FLUSH_EVERY_N', 1)))
        checkpoint_dir = str(getattr(_cfg, 'CHECKPOINT_DIR', '') or '').strip()
        assertion_strict_mode = bool(getattr(_cfg, 'ENABLE_ASSERTION_STRICT_MODE', False))
    except Exception:
        pass

    return (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    )


def _resolve_output_dir(output_dir: Optional[str]) -> str:
    if output_dir is not None:
        return output_dir
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')


def _validate_base_url(base_url: Optional[str]) -> None:
    if base_url is None:
        return
    from urllib.parse import urlparse as _urlparse
    _parsed = _urlparse(base_url)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        raise ValidationError(f"base_url 鏍煎紡鏃犳晥锛堜粎鏀寔 http/https锛? {base_url!r}")


def _filter_selected_apis(
    apis: List[Dict[str, Any]],
    selected_item_paths: Optional[List[List[int]]],
) -> Tuple[List[Dict[str, Any]], Optional[set]]:
    selected_path_set: Optional[set] = None
    if selected_item_paths:
        normalized_paths = []
        for path in selected_item_paths:
            if not isinstance(path, list):
                continue
            if all(isinstance(index, int) and index >= 0 for index in path):
                normalized_paths.append(tuple(path))
        selected_path_set = set(normalized_paths)
        if not selected_path_set:
            raise ValidationError("selected_item_paths 格式无效，未解析到可执行接口路径。")

        apis = [
            api for api in apis
            if tuple(api.get('item_path') or []) in selected_path_set
        ]
        if not apis:
            raise ValidationError("未匹配到可执行接口，请确认所选接口是否仍存在于当前集合。")
    return apis, selected_path_set


def _prepare_checkpoint_recovery(
    *,
    enable_checkpoint_recovery: bool,
    output_dir: str,
    postman_file: str,
    parser_base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    apis: List[Dict[str, Any]],
    checkpoint_dir: str,
) -> Tuple[str, str, set, List[Dict[str, Any]]]:
    checkpoint_path = ""
    collection_fingerprint = ""
    executed_item_paths: set = set()

    if not enable_checkpoint_recovery:
        return checkpoint_path, collection_fingerprint, executed_item_paths, apis

    try:
        collection_fingerprint = _compute_collection_fingerprint(postman_file, parser_base_url, selected_item_paths)
        checkpoint_path = _checkpoint_file_path(output_dir, postman_file, collection_fingerprint, checkpoint_dir=checkpoint_dir)
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint:
            fingerprint_match = str(checkpoint.get("collection_fingerprint") or "") == collection_fingerprint
            base_url_match = str(checkpoint.get("base_url") or "") == str(parser_base_url or "")
            if fingerprint_match and base_url_match:
                executed_item_paths = set(checkpoint.get("executed_item_paths") or [])
                if executed_item_paths:
                    original_count = len(apis)
                    apis = [
                        api for api in apis
                        if _item_path_text(api.get("item_path")) not in executed_item_paths
                    ]
                    logger.info("断点恢复生效，跳过已执行接口 %d 个，待执行 %d 个", original_count - len(apis), len(apis))
            else:
                logger.warning("检测到 checkpoint 与当前集合不匹配，已忽略恢复数据。")
    except Exception as exc:
        logger.warning("初始化 checkpoint 失败，已降级为普通执行: %s", exc)

    return checkpoint_path, collection_fingerprint, executed_item_paths, apis


def _parse_collection_apis(postman_file: str) -> Tuple[PostmanApiParser, List[Dict[str, Any]], int]:
    logger.info("开始加载 Postman 文件: %s", postman_file)
    parser = PostmanApiParser(postman_file)
    apis = parser.extract_apis()
    total_apis_count = len(apis)
    return parser, apis, total_apis_count


def _log_execution_scope(
    *,
    current_count: int,
    total_apis_count: int,
    parser_base_url: str,
    selected_path_set: Optional[set],
) -> None:
    logger.info("成功加载 %d 个 API 接口，基础 URL: %s", current_count, parser_base_url)
    if selected_path_set is not None:
        logger.info("鏈鎵ц鑼冨洿锛氬凡閫夋帴鍙?%d / 鍏ㄩ噺 %d", current_count, total_apis_count)


def _resolve_checkpoint_execution_apis(
    *,
    enable_checkpoint_recovery: bool,
    output_dir: str,
    postman_file: str,
    parser_base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    apis: List[Dict[str, Any]],
    checkpoint_dir: str,
) -> Tuple[str, str, set, List[Dict[str, Any]]]:
    apis_before_recovery = list(apis)
    checkpoint_path, collection_fingerprint, executed_item_paths, apis = _prepare_checkpoint_recovery(
        enable_checkpoint_recovery=enable_checkpoint_recovery,
        output_dir=output_dir,
        postman_file=postman_file,
        parser_base_url=parser_base_url,
        selected_item_paths=selected_item_paths,
        apis=apis,
        checkpoint_dir=checkpoint_dir,
    )
    if enable_checkpoint_recovery and not apis:
        # 防止生成空报告：若 checkpoint 覆盖全部接口，则回退为全量执行。
        logger.info("checkpoint 覆盖全部接口，本次回退为全量执行以保持报告可读性。")
        apis = apis_before_recovery
        executed_item_paths = set()
    return checkpoint_path, collection_fingerprint, executed_item_paths, apis


def _apply_base_url_override(
    parser: PostmanApiParser,
    apis: List[Dict[str, Any]],
    base_url: Optional[str],
) -> None:
    if not base_url:
        return
    parser.base_url = base_url
    for api in apis:
        api['full_url'] = urljoin(base_url, api['url']) if not api['url'].startswith('http') else api['url']


def _emit_progress(progress_callback: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(payload)
    except Exception:
        pass


def _emit_start_progress(
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    *,
    current_total: int,
    total_apis_count: int,
) -> None:
    _emit_progress(progress_callback, {
        'stage': 'running',
        'total': current_total,
        'total_all': total_apis_count,
        'completed': 0,
        'percent': 0,
        'current_name': '',
        'current_method': '',
        'current_url': '',
        'message': '开始执行测试',
    })


def _resolve_auth_token(
    token: Optional[str],
    apis: List[Dict[str, Any]],
    base_url: str,
    *,
    auth_session: SessionLike,
    request_timeout: RequestTimeout,
) -> Optional[str]:
    if token:
        logger.info("浣跨敤鎵嬪姩鎸囧畾鐨則oken: %s...", token[:20])
        return token

    auth_token = get_auth_token(apis, base_url, session=auth_session, request_timeout=request_timeout)

    if auth_token:
        logger.info("宸茶幏鍙栬璇乼oken: %s...", auth_token[:20])
    return auth_token


def _build_runtime_context(
    token: Optional[str],
    apis: List[Dict[str, Any]],
    base_url: str,
) -> Tuple[Optional[str], RequestTimeout, SessionLike]:
    """Build runtime context with unified timeout and shared session lifecycle."""
    shared_session = create_shared_session()
    request_timeout = normalize_timeout(resolve_request_timeout(default=(10, 30)), default=(10, 30))
    resolved_token = _resolve_auth_token(
        token,
        apis,
        base_url,
        auth_session=shared_session,
        request_timeout=request_timeout,
    )
    return resolved_token, request_timeout, shared_session


def _resolve_report_file_path(output_dir: str, report_name: Optional[str]) -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_report_name = f'postman_report_{timestamp}.html'
    selected_report_name = str(report_name or '').strip()
    if selected_report_name:
        normalized_name = selected_report_name.replace('\\', '/').split('/')[-1]
        normalized_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized_name).strip(' .')
        if normalized_name and not normalized_name.lower().endswith('.html'):
            normalized_name = f'{normalized_name}.html'
        report_file_name = normalized_name or default_report_name
    else:
        report_file_name = default_report_name

    report_file = os.path.join(output_dir, report_file_name)
    if os.path.exists(report_file):
        name_no_ext, ext = os.path.splitext(report_file_name)
        report_file = os.path.join(output_dir, f'{name_no_ext}_{timestamp}{ext or ".html"}')
    return report_file


def _flush_checkpoint_state(
    *,
    enable_checkpoint_recovery: bool,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set,
    completed: bool,
    last_error: str = "",
) -> None:
    if not (enable_checkpoint_recovery and checkpoint_path):
        return
    payload = {
        "collection_fingerprint": collection_fingerprint,
        "base_url": str(parser_base_url or ""),
        "selected_total_count": selected_total_count,
        "executed_item_paths": sorted(executed_item_paths),
        "completed": bool(completed),
        "last_error": str(last_error or ""),
        "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    _save_checkpoint_atomic(checkpoint_path, payload)


def _finalize_checkpoint_state(
    *,
    enable_checkpoint_recovery: bool,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set,
    execution_error: Optional[Exception],
) -> None:
    if not enable_checkpoint_recovery:
        return
    try:
        _flush_checkpoint_state(
            enable_checkpoint_recovery=enable_checkpoint_recovery,
            checkpoint_path=checkpoint_path,
            collection_fingerprint=collection_fingerprint,
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            completed=(execution_error is None),
            last_error=str(execution_error or ""),
        )
    except Exception as exc:
        logger.warning("写入 checkpoint 失败: %s", exc)


def _execute_api_suite(
    *,
    apis: List[Dict[str, Any]],
    total_apis_count: int,
    report: PostmanTestReport,
    resolved_token: Optional[str],
    request_timeout: RequestTimeout,
    assertion_strict_mode: bool,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    enable_checkpoint_recovery: bool,
    checkpoint_flush_every_n: int,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set,
    shared_session: SessionLike,
) -> Tuple[int, Optional[Exception]]:
    execution_error: Optional[Exception] = None
    completed_count = 0

    try:
        for idx, api in enumerate(apis, 1):
            logger.debug("[%d/%d] 娴嬭瘯: %s (%s %s)", idx, len(apis), api['name'], api['method'], api['url'])

            executor = PostmanTestExecutor(
                api,
                auth_token=resolved_token,
                session=shared_session,
                request_timeout=request_timeout,
                assertion_strict_mode=assertion_strict_mode,
            )
            executor.start()
            result = executor.execute_test()
            report.add_result(result)
            completed_count = idx

            item_path_key = _item_path_text(api.get("item_path"))
            if item_path_key:
                executed_item_paths.add(item_path_key)
            if enable_checkpoint_recovery and (idx % checkpoint_flush_every_n == 0):
                _flush_checkpoint_state(
                    enable_checkpoint_recovery=enable_checkpoint_recovery,
                    checkpoint_path=checkpoint_path,
                    collection_fingerprint=collection_fingerprint,
                    parser_base_url=parser_base_url,
                    selected_total_count=selected_total_count,
                    executed_item_paths=executed_item_paths,
                    completed=False,
                )

            _log = logger.info if result['status'] == 'PASSED' else logger.warning
            _log("[%d/%d] %s %s 鈫?%s", idx, len(apis), api['method'], api['name'], result['status'])

            _emit_progress(progress_callback, {
                'stage': 'running',
                'total': len(apis),
                'total_all': total_apis_count,
                'completed': idx,
                'percent': int(idx * 100 / len(apis)) if len(apis) > 0 else 100,
                'current_name': str(api.get('name', '')),
                'current_method': str(api.get('method', '')),
                'current_url': str(api.get('url', '')),
                'last_status': str(result.get('status', '')),
            })
    except Exception as exc:
        execution_error = exc
        logger.exception("鎵ц杩囩▼涓彂鐢熶腑鏂紓甯革紝灏嗚緭鍑洪儴鍒嗘垚鍔熸姤鍛? %s", exc)

    return completed_count, execution_error


def _execute_and_finalize_suite(
    *,
    apis: List[Dict[str, Any]],
    total_apis_count: int,
    report: PostmanTestReport,
    resolved_token: Optional[str],
    request_timeout: RequestTimeout,
    assertion_strict_mode: bool,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    enable_checkpoint_recovery: bool,
    checkpoint_flush_every_n: int,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set,
    shared_session: SessionLike,
) -> Tuple[int, Optional[Exception]]:
    completed_count = 0
    execution_error: Optional[Exception] = None
    try:
        completed_count, execution_error = _execute_api_suite(
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
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            shared_session=shared_session,
        )
    finally:
        close_session(shared_session)
        _finalize_checkpoint_state(
            enable_checkpoint_recovery=enable_checkpoint_recovery,
            checkpoint_path=checkpoint_path,
            collection_fingerprint=collection_fingerprint,
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            execution_error=execution_error,
        )
    return completed_count, execution_error


def _prepare_execution_context(
    *,
    token: Optional[str],
    apis: List[Dict[str, Any]],
    parser: PostmanApiParser,
    postman_file: str,
    source_original_file: Optional[str],
    assertion_strict_mode: bool,
) -> Tuple[Optional[str], PostmanTestReport, RequestTimeout, SessionLike]:
    # 棰勮幏鍙栬璇?token锛屼娇鐢ㄧ粺涓€ runtime context锛坰hared_session + timeout锛?
    resolved_token, request_timeout, shared_session = _build_runtime_context(token, apis, parser.base_url)

    # 鍒涘缓鎶ュ憡瀵硅薄
    report = _build_report_context(
        parser=parser,
        postman_file=postman_file,
        source_original_file=source_original_file,
        assertion_strict_mode=assertion_strict_mode,
    )

    # 鎵ц娴嬭瘯 鈥斺€?鎵€鏈?API 鍏变韩鍚屼竴 Session锛岄伩鍏嶆瘡娆″缓绔嬫柊 TCP 杩炴帴
    logger.info("开始执行测试，共 %d 个接口", len(apis))
    return resolved_token, report, request_timeout, shared_session


def _prepare_execution_apis(
    *,
    postman_file: str,
    selected_item_paths: Optional[List[List[int]]],
    base_url: Optional[str],
) -> Tuple[PostmanApiParser, List[Dict[str, Any]], int, int]:
    parser, apis, total_apis_count = _parse_collection_apis(postman_file)

    apis, selected_path_set = _filter_selected_apis(apis, selected_item_paths)
    _apply_base_url_override(parser, apis, base_url)

    selected_total_count = len(apis)
    _log_execution_scope(
        current_count=selected_total_count,
        total_apis_count=total_apis_count,
        parser_base_url=parser.base_url,
        selected_path_set=selected_path_set,
    )
    return parser, apis, total_apis_count, selected_total_count


def _prepare_runtime_settings(
    token: Optional[str],
    base_url: Optional[str],
    output_dir: Optional[str],
) -> Tuple[
    Optional[str],
    Optional[str],
    str,
    bool,
    int,
    str,
    bool,
]:
    (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    ) = _resolve_runtime_config(token, base_url, output_dir)

    output_dir = _resolve_output_dir(output_dir)
    _validate_base_url(base_url)

    return (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    )


def _prepare_checkpoint_and_progress(
    *,
    enable_checkpoint_recovery: bool,
    output_dir: str,
    postman_file: str,
    parser_base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    apis: List[Dict[str, Any]],
    checkpoint_dir: str,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    total_apis_count: int,
) -> Tuple[str, str, set, List[Dict[str, Any]]]:
    checkpoint_path, collection_fingerprint, executed_item_paths, apis = _resolve_checkpoint_execution_apis(
        enable_checkpoint_recovery=enable_checkpoint_recovery,
        output_dir=output_dir,
        postman_file=postman_file,
        parser_base_url=parser_base_url,
        selected_item_paths=selected_item_paths,
        apis=apis,
        checkpoint_dir=checkpoint_dir,
    )

    _emit_start_progress(
        progress_callback,
        current_total=len(apis),
        total_apis_count=total_apis_count,
    )
    return checkpoint_path, collection_fingerprint, executed_item_paths, apis


def _build_report_context(
    parser: PostmanApiParser,
    postman_file: str,
    source_original_file: Optional[str],
    assertion_strict_mode: bool,
) -> PostmanTestReport:
    report = PostmanTestReport()
    report.collection_name = parser.data.get('info', {}).get('name', '') if isinstance(parser.data, dict) else ''
    report.source_file = os.path.abspath(postman_file)
    report.source_original_file = str(source_original_file or '').strip()
    report.base_url = parser.base_url
    report.assertion_strict_mode = assertion_strict_mode
    return report


def _set_report_execution_outcome(report: PostmanTestReport, execution_error: Optional[Exception]) -> None:
    report.execution_mode = 'partial' if execution_error is not None else 'full'
    report.interrupted = execution_error is not None
    report.interrupt_reason = str(execution_error or '')


def _emit_finish_progress(
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    *,
    execution_error: Optional[Exception],
    completed_count: int,
    current_total: int,
    total_apis_count: int,
) -> None:
    _emit_progress(progress_callback, {
        'stage': 'finished' if execution_error is None else 'partial',
        'total': current_total,
        'total_all': total_apis_count,
        'completed': completed_count,
        'percent': int(completed_count * 100 / current_total) if current_total > 0 else 100,
        'message': '执行完成' if execution_error is None else f'执行中断，已生成部分报告: {execution_error}',
    })


def _generate_and_log_report(
    report: PostmanTestReport,
    *,
    output_dir: str,
    report_name: Optional[str],
    results_per_page: int,
    execution_error: Optional[Exception],
) -> str:
    print("\n生成测试报告...")
    report.generate_summary()

    report_file = _resolve_report_file_path(output_dir, report_name)
    report.generate_html_report(report_file, results_per_page=results_per_page)
    logger.info("HTML鎶ュ憡宸蹭繚瀛? %s", report_file)
    logger.info("鎶ュ憡鍏冩暟鎹凡淇濆瓨: %s", report.generated_meta_file)
    if execution_error is not None:
        logger.warning("鏈鎶ュ憡涓洪儴鍒嗘垚鍔熸姤鍛婏紝鍘熷洜: %s", execution_error)
    return report_file


def _complete_report_output(
    report: PostmanTestReport,
    *,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    execution_error: Optional[Exception],
    completed_count: int,
    current_total: int,
    total_apis_count: int,
    output_dir: str,
    report_name: Optional[str],
    results_per_page: int,
) -> None:
    _set_report_execution_outcome(report, execution_error)
    _emit_finish_progress(
        progress_callback,
        execution_error=execution_error,
        completed_count=completed_count,
        current_total=current_total,
        total_apis_count=total_apis_count,
    )
    _generate_and_log_report(
        report,
        output_dir=output_dir,
        report_name=report_name,
        results_per_page=results_per_page,
        execution_error=execution_error,
    )
    report.print_console_report()


def run_postman_tests(
    postman_file: str,
    base_url: str = None,
    output_dir: str = None,
    token: str = None,
    report_name: str = None,
    source_original_file: str = None,
    results_per_page: int = 30,
    selected_item_paths: Optional[List[List[int]]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
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
    浣跨敤绀轰緥:
    1. 灏哖ostman瀵煎嚭鐨凧SON鏂囦欢鏀惧湪椤圭洰鐩綍
    2. 鍦ㄥ懡浠よ鎵ц: python -m postman_api_tester.postman_api_tester <postman_file_path> [base_url] [output_dir]
    """
    
    if len(sys.argv) > 1:
        postman_file = sys.argv[1]
        base_url = sys.argv[2] if len(sys.argv) > 2 else None
        output_dir = sys.argv[3] if len(sys.argv) > 3 else None
        token = None
        results_per_page = 30

        if len(sys.argv) > 4:
            arg4 = str(sys.argv[4]).strip()
            # 鍏煎鐩存帴鎶婄4涓弬鏁板綋鍒嗛〉澶у皬鐨勭敤娉?
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
        print("浣跨敤鏂规硶:")
        print("  python postman_api_tester.py <postman_file_path> [base_url] [output_dir] [token] [results_per_page]")
        print("\n鍙傛暟璇存槑:")
        print("  postman_file_path: Postman导出的JSON文件路径（必需）")
        print("  base_url: 基础URL（可选，将覆盖Postman文件中的配置）")
        print("  output_dir: 报告输出目录（可选，默认：../reports）")
        print("  token: 手动指定认证token（可选，指定后跳过自动登录，直接用于测试）")

