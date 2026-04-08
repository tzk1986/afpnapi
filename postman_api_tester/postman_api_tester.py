"""
Postman API 文件测试模块
用于读取从APIFox/Postman导出的接口文件，动态生成并执行测试用例
"""

import json
import os
import sys
from typing import Dict, List, Any, Optional
from datetime import datetime
import re
import seldom
from urllib.parse import urljoin


class PostmanApiParser:
    """Postman接口文件解析器"""
    
    def __init__(self, file_path: str):
        """
        初始化解析器
        :param file_path: Postman导出的JSON文件路径
        """
        self.file_path = file_path
        self.data = None
        self.base_url = ""
        self.collections = []
        self.load_file()
    
    def load_file(self):
        """加载并解析Postman文件"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON文件格式错误: {e}")
    
    def extract_base_url(self) -> str:
        """
        从Postman文件中提取基础URL
        :return: 基础URL
        """
        if self.data.get('variable'):
            for var in self.data['variable']:
                if var.get('key') == 'baseUrl' or var.get('key') == 'base_url':
                    self.base_url = var.get('value', '')
        
        # 如果没有找到baseUrl变量，尝试从第一个请求中提取
        if not self.base_url:
            items = self.data.get('item', [])
            if items and items[0].get('request'):
                url = items[0]['request'].get('url')
                if isinstance(url, dict):
                    self.base_url = f"{url.get('protocol', 'https')}://{url.get('host', 'localhost')}"
                elif isinstance(url, str):
                    # 提取协议和主机
                    match = re.match(r'(https?://[^/]+)', url)
                    if match:
                        self.base_url = match.group(1)
        
        return self.base_url
    
    def extract_apis(self) -> List[Dict[str, Any]]:
        """
        提取所有API接口信息
        :return: API列表
        """
        apis = []
        items = self.data.get('item', [])
        
        self.extract_base_url()
        
        for item in items:
            api_info = self._parse_item(item)
            if api_info:
                apis.append(api_info)
        
        self.collections = apis
        return apis
    
    def _parse_item(self, item: Dict, parent_name: str = "") -> Optional[Dict]:
        """
        递归解析item（可能是文件夹或请求）
        :param item: item对象
        :param parent_name: 父级名称
        :return: API信息或None
        """
        # 如果是文件夹，递归处理
        if 'item' in item and not 'request' in item:
            folder_name = item.get('name', '')
            for sub_item in item['item']:
                api_info = self._parse_item(sub_item, folder_name)
                if api_info:
                    self.collections.append(api_info)
            return None
        
        # 解析请求
        if 'request' in item:
            return self._parse_request(item, parent_name)
        
        return None
    
    def _parse_request(self, item: Dict, parent_name: str = "") -> Dict:
        """
        解析单个请求
        :param item: item对象
        :param parent_name: 父级名称（文件夹）
        :return: API信息
        """
        request = item.get('request', {})
        name = item.get('name', 'Unknown')
        
        # 解析URL
        url = request.get('url', '')
        if isinstance(url, dict):
            url = self._build_url_from_dict(url)
        
        # 解析方法
        method = request.get('method', 'GET').upper()
        
        # 解析请求头
        headers = {}
        for header in request.get('header', []):
            if header.get('disabled'):
                continue
            headers[header.get('key', '')] = header.get('value', '')
        
        # 解析请求体
        body = None
        body_data = request.get('body', {})
        if body_data:
            if body_data.get('mode') == 'raw':
                try:
                    body = json.loads(body_data.get('raw', '{}'))
                except:
                    body = body_data.get('raw', '')
            elif body_data.get('mode') == 'formdata':
                body = {}
                for item_data in body_data.get('formdata', []):
                    if not item_data.get('disabled'):
                        body[item_data.get('key')] = item_data.get('value')
            elif body_data.get('mode') == 'urlencoded':
                body = {}
                for item_data in body_data.get('urlencoded', []):
                    if not item_data.get('disabled'):
                        body[item_data.get('key')] = item_data.get('value')
        
        # 解析参数
        params = {}
        for query in request.get('url', {}).get('query', []) if isinstance(request.get('url'), dict) else []:
            if not query.get('disabled'):
                params[query.get('key')] = query.get('value')
        
        # 解析预期响应
        expected_status = 200
        tests = item.get('event', [])
        for event in tests:
            if event.get('listen') == 'test':
                script = event.get('script', {}).get('exec', '')
                if '200' in str(script):
                    expected_status = 200
        
        return {
            'name': name,
            'folder': parent_name,
            'method': method,
            'url': url,
            'full_url': urljoin(self.base_url, url) if not url.startswith('http') else url,
            'headers': headers,
            'body': body,
            'params': params,
            'expected_status': expected_status,
            'description': item.get('description', '')
        }
    
    def _build_url_from_dict(self, url_dict: Dict) -> str:
        """
        从字典格式的URL构建字符串URL
        :param url_dict: URL字典
        :return: URL字符串
        """
        path = '/'.join(url_dict.get('path', []))
        if path and not path.startswith('/'):
            path = '/' + path
        
        query = ''
        if url_dict.get('query'):
            query_parts = [f"{q.get('key')}={q.get('value')}" for q in url_dict['query']]
            query = '?' + '&'.join(query_parts)
        
        return path + query


class PostmanTestExecutor:
    """Postman API测试执行器"""
    
    test_results = []
    
    def __init__(self, api_config: Dict):
        """
        初始化执行器
        :param api_config: API配置信息
        """
        import requests
        self.api_config = api_config
        self.http_response = None
        self.resp_status_code = None
        self.response_data = None
        self.session = requests.Session()
    
    def start(self):
        """测试前准备"""
        pass
    
    def execute_test(self):
        """执行单个API测试"""
        api = self.api_config
        method = api['method'].lower()
        url = api['url']
        headers = api.get('headers', {})
        params = api.get('params', {})
        body = api.get('body')
        
        try:
            # 发送请求
            if method == 'get':
                response = self.session.get(url, params=params, headers=headers)
            elif method == 'post':
                response = self.session.post(url, json=body, params=params, headers=headers)
            elif method == 'put':
                response = self.session.put(url, json=body, params=params, headers=headers)
            elif method == 'delete':
                response = self.session.delete(url, params=params, headers=headers)
            elif method == 'patch':
                response = self.session.patch(url, json=body, params=params, headers=headers)
            else:
                return {
                    'name': api['name'],
                    'method': api['method'],
                    'url': api['full_url'],
                    'status': 'FAILED',
                    'message': f'不支持的HTTP方法: {method}',
                    'status_code': None
                }
            
            self.http_response = response
            self.resp_status_code = response.status_code
            
            try:
                self.response_data = response.json()
            except:
                self.response_data = response.text
            
            # 验证响应
            expected_status = api.get('expected_status', 200)
            if self.resp_status_code == expected_status:
                return {
                    'name': api['name'],
                    'method': api['method'],
                    'url': api['full_url'],
                    'status': 'PASSED',
                    'message': f'响应状态码: {self.resp_status_code}',
                    'status_code': self.resp_status_code,
                    'folder': api.get('folder', '')
                }
            else:
                return {
                    'name': api['name'],
                    'method': api['method'],
                    'url': api['full_url'],
                    'status': 'FAILED',
                    'message': f'期望状态码: {expected_status}, 实际: {self.resp_status_code}',
                    'status_code': self.resp_status_code,
                    'folder': api.get('folder', '')
                }
        
        except Exception as e:
            return {
                'name': api['name'],
                'method': api['method'],
                'url': api['full_url'],
                'status': 'ERROR',
                'message': str(e),
                'status_code': None,
                'folder': api.get('folder', '')
            }


class PostmanTestReport:
    """Postman测试报告生成器"""
    
    def __init__(self):
        self.results = []
        self.start_time = datetime.now()
        self.end_time = None
    
    def add_result(self, result: Dict):
        """添加测试结果"""
        self.results.append(result)
    
    def add_results(self, results: List[Dict]):
        """批量添加测试结果"""
        self.results.extend(results)
    
    def generate_summary(self) -> Dict:
        """生成测试摘要"""
        self.end_time = datetime.now()
        
        total = len(self.results)
        passed = len([r for r in self.results if r['status'] == 'PASSED'])
        failed = len([r for r in self.results if r['status'] == 'FAILED'])
        error = len([r for r in self.results if r['status'] == 'ERROR'])
        
        duration = (self.end_time - self.start_time).total_seconds()
        
        return {
            'total': total,
            'passed': passed,
            'failed': failed,
            'error': error,
            'success_rate': f"{(passed/total*100):.2f}%" if total > 0 else "0%",
            'duration': f"{duration:.2f}s",
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def generate_html_report(self, output_path: str):
        """生成HTML报告"""
        summary = self.generate_summary()
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Postman API 测试报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .header {{ background-color: #333; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .summary {{ background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-item {{ display: inline-block; margin-right: 30px; }}
        .summary-item label {{ font-weight: bold; margin-right: 10px; }}
        table {{ width: 100%; border-collapse: collapse; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th {{ background-color: #f0f0f0; padding: 12px; text-align: left; font-weight: bold; border-bottom: 2px solid #ddd; }}
        td {{ padding: 12px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background-color: #f9f9f9; }}
        .status-passed {{ color: green; font-weight: bold; }}
        .status-failed {{ color: red; font-weight: bold; }}
        .status-error {{ color: orange; font-weight: bold; }}
        .url {{ color: #0066cc; font-family: monospace; }}
        .detail {{ font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Postman API 测试报告</h1>
        <p>自动化接口测试结果汇总</p>
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
        <br>
        <div style="margin-top: 10px; font-size: 12px; color: #666;">
            <p>开始时间: {summary['start_time']}</p>
            <p>结束时间: {summary['end_time']}</p>
        </div>
    </div>
    
    <h2>详细结果</h2>
    <table>
        <thead>
            <tr>
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
"""
        
        for result in self.results:
            status_class = f"status-{result['status'].lower()}"
            html_content += f"""
            <tr>
                <td>{result['name']}</td>
                <td>{result.get('folder', '-')}</td>
                <td>{result['method']}</td>
                <td><span class="url">{result['url']}</span></td>
                <td><span class="{status_class}">{result['status']}</span></td>
                <td>{result['status_code'] or '-'}</td>
                <td><span class="detail">{result['message']}</span></td>
            </tr>
"""
        
        html_content += """
        </tbody>
    </table>
</body>
</html>
"""
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
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


def run_postman_tests(postman_file: str, base_url: str = None, output_dir: str = None) -> PostmanTestReport:
    """
    运行Postman接口测试
    
    :param postman_file: Postman JSON文件路径
    :param base_url: 基础URL（可选，将覆盖Postman文件中的配置）
    :param output_dir: 报告输出目录（默认：../reports）
    :return: 测试报告对象
    """
    
    if output_dir is None:
        # 报告输出到上级目录的reports文件夹
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')
    
    print(f"\n开始加载Postman文件: {postman_file}")
    
    # 解析Postman文件
    parser = PostmanApiParser(postman_file)
    apis = parser.extract_apis()
    
    if base_url:
        parser.base_url = base_url
        for api in apis:
            api['full_url'] = urljoin(base_url, api['url']) if not api['url'].startswith('http') else api['url']
    
    print(f"✓ 成功加载 {len(apis)} 个API接口")
    print(f"  基础URL: {parser.base_url}")
    
    # 创建报告对象
    report = PostmanTestReport()
    
    # 执行测试
    print("\n开始执行测试...")
    for idx, api in enumerate(apis, 1):
        print(f"  [{idx}/{len(apis)}] 测试: {api['name']} ({api['method']} {api['url']}) ...", end='')
        
        executor = PostmanTestExecutor(api)
        executor.start()
        result = executor.execute_test()
        report.add_result(result)
        
        status_symbol = "✓" if result['status'] == 'PASSED' else "✗" if result['status'] == 'FAILED' else "!"
        print(f" {status_symbol} {result['status']}")
    
    # 生成报告
    print("\n生成测试报告...")
    summary = report.generate_summary()
    
    # 保存HTML报告
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = os.path.join(output_dir, f'postman_report_{timestamp}.html')
    report.generate_html_report(report_file)
    print(f"✓ HTML报告已保存: {report_file}")
    
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
        
        run_postman_tests(postman_file, base_url, output_dir)
    else:
        print("使用方法:")
        print("  python postman_api_tester.py <postman_file_path> [base_url] [output_dir]")
        print("\n参数说明:")
        print("  postman_file_path: Postman导出的JSON文件路径（必需）")
        print("  base_url: 基础URL（可选，将覆盖Postman文件中的配置）")
        print("  output_dir: 报告输出目录（可选，默认：../reports）")
