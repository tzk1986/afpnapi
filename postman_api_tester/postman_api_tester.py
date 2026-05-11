"""
Postman API 文件测试模块
用于读取从APIFox/Postman导出的接口文件，动态生成并执行测试用例

版本: 1.0.2
更新日志:
- 1.0.2 (2026-04-20): 增强报告管理能力，支持历史报告索引、结构化对比与局域网访问
    * 生成报告时同步输出 meta.json，便于历史追踪和差异比对
    * 为报告服务端提供标准化数据源，避免只能解析 HTML
    * 修复分页详情页对详情 JSON 的固定文件名引用
- 1.0.1 (2026-04-16): 文档与代码整理版本
    * 去除冗余文档与测试脚本，保留中文主文档
    * 保持token注入兼容逻辑，修复大小写重复键风险
    * 统一对外版本号，便于发布与追踪
- 1.2.0 (2026-04-16): 新增自动token预获取功能，支持测试前自动登录获取认证token
  * 自动识别登录接口（包含login关键词的POST请求）
  * 执行登录获取token并自动添加到后续需要认证的请求中
  * 支持常见的token字段名：token, access_token, accessToken, auth_token, authorization
  * 避免重复执行登录测试，提高测试效率
- 1.1.0 (2026-04-16): 优化HTML报告性能，支持分页和懒加载详情，解决大量API导致浏览器卡顿的问题
  * 实现分页显示，每页默认30个结果，显著减少初始加载时间
  * 详情数据存储在单独JSON文件中，通过AJAX懒加载，避免内联大量数据
  * 索引页面仅包含分页导航，文件大小从几MB降至几KB
  * 支持1649+个API的流畅浏览和详情查看
  * 保持向后兼容性，可通过results_per_page参数调整分页大小
- 1.0.0: 初始版本
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
from postman_api_tester.session import create_shared_session, close_session, resolve_request_timeout

logger = logging.getLogger(__name__)

class PostmanTestReport:
    """Postman测试报告生成器"""
    
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
        """添加测试结果"""
        self.results.append(result)
        self._summary_cache = None
    
    def add_results(self, results: List[Dict]):
        """批量添加测试结果"""
        self.results.extend(results)
        self._summary_cache = None
    
    def generate_summary(self) -> Dict:
        """生成测试摘要"""
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

        # 响应时间统计（升级三）
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
    
    def generate_html_report(self, output_path: str, results_per_page: int = 30):
        """生成HTML报告"""
        summary = self.generate_summary()
        output_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else '.'
        os.makedirs(output_dir, exist_ok=True)
        
        # 计算分页
        total_results = len(self.results)
        total_pages = (total_results + results_per_page - 1) // results_per_page
        
        # 准备详情数据，过滤请求头中的敏感凭据字段
        _SENSITIVE_HEADERS = frozenset({
            'authorization', 'token', 'x-token', 'x-access-token', 'access-token',
        })
        details_data = {}
        for idx, result in enumerate(self.results):
            req_info = result.get('request_info', {})
            raw_req_headers = req_info.get('headers', {}) or {}
            sanitized_headers = {
                k: ('***' if k.lower() in _SENSITIVE_HEADERS else v)
                for k, v in raw_req_headers.items()
            }
            details_data[str(idx)] = {
                'request_info': {**req_info, 'headers': sanitized_headers},
                'response_info': result.get('response_info', {})
            }
        
        # 保存详情JSON文件
        base_name = os.path.splitext(output_path)[0]
        details_file = f"{base_name}_details.json"
        with open(details_file, 'w', encoding='utf-8') as f:
            json.dump(details_data, f, indent=2, ensure_ascii=False)

        meta_file = f"{base_name}_meta.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(self._build_report_metadata(summary, output_path, details_file), f, indent=2, ensure_ascii=False)
        
        # 生成索引页面
        index_content = self._generate_index_html(summary, total_pages, results_per_page, total_results)
        index_path = output_path
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        
        # 生成分页页面
        for page in range(1, total_pages + 1):
            page_content = self._generate_page_html(page, results_per_page, summary, os.path.basename(details_file))
            page_path = f"{base_name}_page_{page}.html"
            with open(page_path, 'w', encoding='utf-8') as f:
                f.write(page_content)

        self.generated_report_file = output_path
        self.generated_details_file = details_file
        self.generated_meta_file = meta_file

    def _build_report_metadata(self, summary: Dict, output_path: str, details_file: str) -> Dict[str, Any]:
        """构建历史报告和差异比对所需的结构化元数据。"""
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
        """生成索引页面HTML - 支持客户端分页和每页显示条数自定义"""
        # 准备结果数据JSON（包含详情信息）
        results_data = []
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
                'response_info': result.get('response_info', {})
            })
        
        results_json = json.dumps(results_data, ensure_ascii=False)
        
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
                <label>✓ 通过</label>
                <span>{summary['passed']}</span>
            </div>
            <div class="summary-item failed">
                <label>✗ 失败</label>
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
                <label for="search-input">🔍 搜索:</label>
                <input type="text" id="search-input" placeholder="输入API名称、路径、文件夹进行搜索..." onkeyup="performSearch()">
                <button onclick="clearSearch()">清空</button>
            </div>
        </div>
        <div class="control-row">
            <div class="token-item">
                <label for="token-input">🔑 Token:</label>
                <input type="text" id="token-input" placeholder="输入认证token (可选，用于重新请求接口)">
                <button id="test-token-btn" onclick="testToken()">测试Token</button>
            </div>
        </div>
        <div class="control-row">
            <div class="control-item">
                <label for="page-size">每页显示:</label>
                <select id="page-size" onchange="changePageSize()">
                    <option value="20" selected>20条</option>
                    <option value="30">30条</option>
                    <option value="50">50条</option>
                    <option value="100">100条</option>
                    <option value="200">200条</option>
                </select>
            </div>
            <div class="control-item">
                <label>状态筛选:</label>
                <button class="filter-btn active" onclick="filterResults('all')">全部</button>
                <button class="filter-btn" onclick="filterResults('PASSED')">✓ 成功</button>
                <button class="filter-btn" onclick="filterResults('FAILED')">✗ 失败</button>
                <button class="filter-btn" onclick="filterResults('ERROR')">! 错误</button>
            </div>
        </div>
    </div>
    
    <div class="results-section">
        <div id="table-container">
            <div class="loading">加载数据中...</div>
        </div>
    </div>
    
    <div class="pagination-section">
        <div class="pagination-info" id="pagination-info">第 1 页 | 共 0 页 | 共 0 条数据</div>
        <div class="page-buttons" id="pagination-buttons"></div>
    </div>
    
    <script>
        let allResults = {results_json};
        let filteredResults = allResults;
        let searchResults = allResults;
        let currentPage = 1;
        let pageSize = 20;
        let currentFilter = 'all';
        let searchQuery = '';
        let detailCache = {{}};
        let currentToken = '';
        
        // 初始化
        function init() {{
            changePageSize();
            renderTable();
        }}
        
        // 测试Token
        function testToken() {{
            currentToken = document.getElementById('token-input').value.trim();
            if (!currentToken) {{
                alert('请输入Token');
                return;
            }}
            
            // 测试token是否有效（发送一个简单的请求）
            alert('Token已设置: ' + currentToken.substring(0, 10) + '...\\n\\n现在可以点击"重新请求"按钮来使用此Token测试接口。');
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
        
        // 应用所有过滤条件
        function applyFilters() {{
            let results = allResults;
            
            // 应用状态筛选
            if (currentFilter !== 'all') {{
                results = results.filter(r => r.status === currentFilter);
            }}
            
            // 应用搜索
            if (searchQuery) {{
                results = results.filter(r => {{
                    const searchFields = [
                        r.name,
                        r.url,
                        r.folder || '',
                        r.method
                    ].map(f => (f || '').toLowerCase());
                    return searchFields.some(field => field.includes(searchQuery));
                }});
            }}
            
            filteredResults = results;
            renderTable();
        }}
        
        // 改变每页显示数量
        function changePageSize() {{
            pageSize = parseInt(document.getElementById('page-size').value);
            currentPage = 1;
            renderTable();
        }}
        
        // 筛选结果
        function filterResults(status) {{
            currentFilter = status;
            currentPage = 1;
            
            // 更新按钮状态
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            applyFilters();
        }}
        
        // 渲染表格
        function renderTable() {{
            const totalPages = Math.ceil(filteredResults.length / pageSize);
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            const pageData = filteredResults.slice(start, end);
            
            if (filteredResults.length === 0) {{
                document.getElementById('table-container').innerHTML = '<div class="no-data">没有符合条件的数据</div>';
                updatePagination(0, 0);
                return;
            }}
            
            let html = `
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
            `;
            
            pageData.forEach((result, idx) => {{
                const globalIdx = allResults.indexOf(result);
                const statusClass = `status-${{result.status.toLowerCase()}}`;
                const detailId = `detail-${{globalIdx}}`;
                
                html += `
                    <tr data-result-idx="${{globalIdx}}">
                        <td><span class="expand-btn" onclick="toggleDetail('${{detailId}}', ${{globalIdx}})">▶ 展开</span></td>
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
            
            html += `
                    </tbody>
                </table>
            `;
            
            document.getElementById('table-container').innerHTML = html;
            updatePagination(totalPages, filteredResults.length);
        }}
        
        // 更新分页信息和按钮
        function updatePagination(totalPages, totalItems) {{
            document.getElementById('pagination-info').textContent = 
                `第 ${{currentPage}} 页 | 共 ${{totalPages}} 页 | 共 ${{totalItems}} 条数据`;
            
            let buttons = '';
            
            // 上一页
            buttons += `<button class="page-btn" onclick="goPage(${{currentPage - 1}})" ${{currentPage === 1 ? 'disabled' : ''}}>« 上一页</button>`;
            
            // 页码
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
            buttons += `<button class="page-btn" onclick="goPage(${{currentPage + 1}})" ${{currentPage === totalPages ? 'disabled' : ''}}>下一页 »</button>`;
            
            document.getElementById('pagination-buttons').innerHTML = buttons;
        }}
        
        // 转到指定页
        function goPage(page) {{
            const totalPages = Math.ceil(filteredResults.length / pageSize);
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
        function toggleDetail(detailId, resultIdx) {{
            const detailRow = document.getElementById(detailId);
            const btn = event.target;
            const isExpanded = detailRow.classList.contains('expanded');
            
            if (isExpanded) {{
                detailRow.classList.remove('expanded');
                btn.textContent = '▶ 展开';
            }} else {{
                detailRow.classList.add('expanded');
                btn.textContent = '▼ 收起';
                loadDetail(resultIdx);
            }}
        }}
        
        // 加载详情数据（从内存中直接加载，无需AJAX）
        function loadDetail(resultIdx) {{
            const detailContent = document.getElementById(`detail-content-${{resultIdx}}`);
            
            // 检查缓存
            if (detailCache[resultIdx]) {{
                detailContent.innerHTML = detailCache[resultIdx];
                return;
            }}
            
            // 从全局结果中查找结果
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
                        <strong>💡 提示：</strong>如果看到"session 已经过期"错误，可以输入Token后点击"重新请求"按钮来重新测试此接口。
                        <button onclick="reRequestApi(` + resultIdx + `)" style="margin-left: 10px; padding: 5px 10px; background-color: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 12px;">🔄 重新请求</button>
                    </div>
                    
                    <div class="detail-header">📤 请求信息</div>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">请求头：</div>
                    <pre>${{requestHeaders}}</pre>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">查询参数：</div>
                    <pre>${{requestParams}}</pre>
                    <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 8px;">请求体：</div>
                    <pre>${{requestBody}}</pre>
                    
                    <div class="detail-header" style="margin-top: 15px;">📥 响应信息</div>
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
        
        // 测试Token有效性
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
                    alert('✅ Token有效！');
                    testBtn.textContent = '✅ Token有效';
                    testBtn.style.backgroundColor = '#28a745';
                }} else {{
                    alert('❌ Token无效：' + (result.message || '未知错误'));
                    testBtn.textContent = '❌ Token无效';
                    testBtn.style.backgroundColor = '#dc3545';
                }}
                
            }} catch (error) {{
                alert('❌ Token测试失败：' + error.message);
                testBtn.textContent = '❌ 测试失败';
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
        
        // 重新请求API
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
            detailContent.innerHTML = '<div class="loading">🔄 正在重新请求...</div>';
            
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
                
                // 清除缓存，重新加载详情
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
                
                alert('重新请求完成！');
                
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
        """生成分页页面HTML"""
        start_idx = (page - 1) * results_per_page
        end_idx = min(page * results_per_page, len(self.results))
        page_results = self.results[start_idx:end_idx]
        
        # 生成表格内容
        table_rows = ""
        for idx, result in enumerate(page_results):
            global_idx = start_idx + idx
            status_class = f"status-{result['status'].lower()}"
            status_lower = result['status'].lower()
            detail_id = f"detail-{global_idx}"
            
            table_rows += f"""
            <tr class="result-row result-{status_lower}" data-status="{status_lower}">
                <td><span class="expand-btn" onclick="toggleDetail('{detail_id}', {global_idx})">▶ 详情</span></td>
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
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Postman API 测试报告 - 第{page}页</title>
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
        <h1>Postman API 测试报告 - 第{page}页</h1>
        <p>第{page}页详细结果 (显示 {start_idx + 1}-{end_idx} / {len(self.results)})</p>
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
            <label>成功率:</label>
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
        <button class="filter-btn" onclick="filterResults('PASSED')">✓ 成功</button>
        <button class="filter-btn" onclick="filterResults('FAILED')">✗ 失败</button>
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
                btn.textContent = '▶ 详情';
            }} else {{
                detailRow.classList.add('expanded');
                btn.textContent = '▼ 详情';
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
                            <div class="detail-header">📤 请求信息</div>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">请求头：</div>
                            <pre>${{requestHeaders}}</pre>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">查询参数：</div>
                            <pre>${{requestParams}}</pre>
                            <div class="detail-header" style="font-size: 11px; font-weight: normal; margin-top: 5px;">请求体：</div>
                            <pre>${{requestBody}}</pre>
                            
                            <div class="detail-header" style="margin-top: 15px;">📥 响应信息</div>
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
    
    def print_console_report(self):
        """在控制台输出测试报告"""
        summary = self.generate_summary()
        
        print("\n" + "="*80)
        print("Postman API 测试报告".center(80))
        print("="*80)
        print(f"\n总计: {summary['total']} | 通过: {summary['passed']} | 失败: {summary['failed']} | 错误: {summary['error']}")
        print(f"成功率: {summary['success_rate']} | 耗时: {summary['duration']}")
        print(f"开始时间: {summary['start_time']} | 结束时间: {summary['end_time']}")
        
        print("\n" + "-"*80)
        print("详细结果:".ljust(80))
        print("-"*80)
        
        for result in self.results:
            status_symbol = "✓" if result['status'] == 'PASSED' else "✗" if result['status'] == 'FAILED' else "!"
            print(f"[{status_symbol}] {result['name']:30} | {result['method']:6} | {result['status']:8} | {result['status_code'] or '-'}")
            print(f"    URL: {result['url']}")
            print(f"    {result['message']}")
        
        print("="*80 + "\n")


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
    运行Postman接口测试
    
    :param postman_file: Postman JSON文件路径
    :param base_url: 基础URL（可选，覆盖Postman文件中的配置；为None时读取config.py中的BASE_URL）
    :param output_dir: 报告输出目录（默认：优先读config.py中的REPORT_OUTPUT_DIR，否则../reports）
    :param token: 手动指定认证token（可选，指定后跳过自动登录；为None时读取config.py中的TOKEN）
    :param report_name: 报告名称（可选，支持 .html 文件名；留空则自动命名）
    :param source_original_file: 原始上传文件名（可选，用于报告追溯与导出命名）
    :param results_per_page: 报告分页大小（默认30）
    :param selected_item_paths: 仅执行指定 item_path 的接口（可选）；为空则全量执行
    :param progress_callback: 进度回调（可选），用于上层展示执行进度
    :return: 测试报告对象
    """
    
    enable_checkpoint_recovery = False
    checkpoint_flush_every_n = 1
    checkpoint_dir = ""
    assertion_strict_mode = False

    # 从配置文件读取默认值
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

    if output_dir is None:
        # 报告输出到上级目录的reports文件夹
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')

    # 校验 base_url 格式，防止 SSRF：仅允许 http/https 协议
    if base_url is not None:
        from urllib.parse import urlparse as _urlparse
        _parsed = _urlparse(base_url)
        if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
            raise ValidationError(f"base_url 格式无效（仅支持 http/https）: {base_url!r}")

    logger.info("开始加载Postman文件: %s", postman_file)
    
    # 解析Postman文件
    parser = PostmanApiParser(postman_file)
    apis = parser.extract_apis()
    total_apis_count = len(apis)

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
    
    if base_url:
        parser.base_url = base_url
        for api in apis:
            api['full_url'] = urljoin(base_url, api['url']) if not api['url'].startswith('http') else api['url']
    
    selected_total_count = len(apis)
    apis_before_recovery = list(apis)
    logger.info("成功加载 %d 个API接口，基础URL: %s", len(apis), parser.base_url)
    if selected_path_set is not None:
        logger.info("本次执行范围：已选接口 %d / 全量 %d", len(apis), total_apis_count)

    checkpoint_path = ""
    collection_fingerprint = ""
    executed_item_paths: set = set()
    if enable_checkpoint_recovery:
        try:
            collection_fingerprint = _compute_collection_fingerprint(postman_file, parser.base_url, selected_item_paths)
            checkpoint_path = _checkpoint_file_path(output_dir, postman_file, collection_fingerprint, checkpoint_dir=checkpoint_dir)
            checkpoint = _load_checkpoint(checkpoint_path)
            if checkpoint:
                fingerprint_match = str(checkpoint.get("collection_fingerprint") or "") == collection_fingerprint
                base_url_match = str(checkpoint.get("base_url") or "") == str(parser.base_url or "")
                if fingerprint_match and base_url_match:
                    executed_item_paths = set(checkpoint.get("executed_item_paths") or [])
                    if executed_item_paths:
                        original_count = len(apis)
                        apis = [
                            api for api in apis
                            if _item_path_text(api.get("item_path")) not in executed_item_paths
                        ]
                        logger.info("断点恢复生效，跳过已执行接口 %d 个，待执行 %d 个", original_count - len(apis), len(apis))
                        if not apis:
                            # 防止生成空报告：若 checkpoint 覆盖全部接口，则回退为全量执行。
                            logger.info("checkpoint 覆盖全部接口，本次回退为全量执行以保持报告可读性。")
                            apis = list(apis_before_recovery)
                            executed_item_paths = set()
                else:
                    logger.warning("检测到 checkpoint 与当前集合不匹配，已忽略恢复数据。")
        except Exception as exc:
            logger.warning("初始化 checkpoint 失败，已降级为普通执行: %s", exc)

    if progress_callback:
        try:
            progress_callback({
                'stage': 'running',
                'total': len(apis),
                'total_all': total_apis_count,
                'completed': 0,
                'percent': 0,
                'current_name': '',
                'current_method': '',
                'current_url': '',
                'message': '开始执行测试',
            })
        except Exception:
            pass
    
    # 预获取认证token，保存为局部变量，通过实例传递，不使用类变量
    resolved_token: Optional[str] = None
    if token:
        # 使用手动指定的token（来自参数或配置文件），跳过自动登录
        resolved_token = token
        logger.info("使用手动指定的token: %s...", token[:20])
    else:
        auth_token = get_auth_token(apis, parser.base_url)
        if auth_token:
            resolved_token = auth_token
            logger.info("已获取认证token: %s...", auth_token[:20])
    
    # 创建报告对象
    report = PostmanTestReport()
    report.collection_name = parser.data.get('info', {}).get('name', '') if isinstance(parser.data, dict) else ''
    report.source_file = os.path.abspath(postman_file)
    report.source_original_file = str(source_original_file or '').strip()
    report.base_url = parser.base_url
    report.assertion_strict_mode = assertion_strict_mode
    
    # 执行测试 —— 所有 API 共享同一 Session，避免每次建立新 TCP 连接
    logger.info("开始执行测试，共 %d 个接口", len(apis))
    _shared_session = create_shared_session()
    request_timeout = resolve_request_timeout(default=(10, 30))

    execution_error: Optional[Exception] = None
    completed_count = 0

    def _flush_checkpoint(completed: bool, last_error: str = "") -> None:
        if not (enable_checkpoint_recovery and checkpoint_path):
            return
        payload = {
            "collection_fingerprint": collection_fingerprint,
            "base_url": str(parser.base_url or ""),
            "selected_total_count": selected_total_count,
            "executed_item_paths": sorted(executed_item_paths),
            "completed": bool(completed),
            "last_error": str(last_error or ""),
            "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        _save_checkpoint_atomic(checkpoint_path, payload)

    try:
        for idx, api in enumerate(apis, 1):
            logger.debug("[%d/%d] 测试: %s (%s %s)", idx, len(apis), api['name'], api['method'], api['url'])
            
            executor = PostmanTestExecutor(
                api,
                auth_token=resolved_token,
                session=_shared_session,
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
                _flush_checkpoint(completed=False)
            
            _log = logger.info if result['status'] == 'PASSED' else logger.warning
            _log("[%d/%d] %s %s → %s", idx, len(apis), api['method'], api['name'], result['status'])

            if progress_callback:
                try:
                    progress_callback({
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
                except Exception:
                    pass
    except Exception as exc:
        execution_error = exc
        logger.exception("执行过程中发生中断异常，将输出部分成功报告: %s", exc)
    finally:
        close_session(_shared_session)

    if enable_checkpoint_recovery:
        try:
            _flush_checkpoint(completed=(execution_error is None), last_error=str(execution_error or ""))
        except Exception as exc:
            logger.warning("写入 checkpoint 失败: %s", exc)

    report.execution_mode = 'partial' if execution_error is not None else 'full'
    report.interrupted = execution_error is not None
    report.interrupt_reason = str(execution_error or '')

    if progress_callback:
        try:
            progress_callback({
                'stage': 'finished' if execution_error is None else 'partial',
                'total': len(apis),
                'total_all': total_apis_count,
                'completed': completed_count,
                'percent': int(completed_count * 100 / len(apis)) if len(apis) > 0 else 100,
                'message': '执行完成' if execution_error is None else f'执行中断，已生成部分报告: {execution_error}',
            })
        except Exception:
            pass

    print("\n生成测试报告...")
    summary = report.generate_summary()
    
    # 保存HTML报告
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

    report.generate_html_report(report_file, results_per_page=results_per_page)
    logger.info("HTML报告已保存: %s", report_file)
    logger.info("报告元数据已保存: %s", report.generated_meta_file)
    if execution_error is not None:
        logger.warning("本次报告为部分成功报告，原因: %s", execution_error)
    
    # 打印控制台报告
    report.print_console_report()
    
    return report

if __name__ == '__main__':
    """
    使用示例:
    1. 将Postman导出的JSON文件放在项目目录
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
            # 兼容直接把第4个参数当分页大小的用法
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
        print("  token: 手动指定认证token（可选，指定后跳过自动登录，直接用于测试）")
