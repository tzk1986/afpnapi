"""
基于 Seldom 框架的 Postman API 测试 - 简化版本
使用 Seldom 的 TestCase 直接执行 API 测试
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
        self.file_path = file_path
        self.data = None
        self.base_url = ""
        self.collections = []
        self.load_file()

    def load_file(self):
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON文件格式错误: {e}")

    def extract_base_url(self) -> str:
        if self.data.get('variable'):
            for var in self.data['variable']:
                if var.get('key') == 'baseUrl' or var.get('key') == 'base_url':
                    self.base_url = var.get('value', '')

        if not self.base_url:
            items = self.data.get('item', [])
            if items and items[0].get('request'):
                url = items[0]['request'].get('url')
                if isinstance(url, dict):
                    self.base_url = f"{url.get('protocol', 'https')}://{url.get('host', 'localhost')}"
                elif isinstance(url, str):
                    match = re.match(r'(https?://[^/]+)', url)
                    if match:
                        self.base_url = match.group(1)

        return self.base_url

    def extract_apis(self) -> List[Dict[str, Any]]:
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
        if 'item' in item and not 'request' in item:
            folder_name = item.get('name', '')
            for sub_item in item['item']:
                api_info = self._parse_item(sub_item, folder_name)
                if api_info:
                    self.collections.append(api_info)
            return None

        if 'request' in item:
            return self._parse_request(item, parent_name)

        return None

    def _parse_request(self, item: Dict, parent_name: str = "") -> Dict:
        request = item.get('request', {})
        name = item.get('name', 'Unknown')

        url = request.get('url', '')
        if isinstance(url, dict):
            url = self._build_url_from_dict(url)

        method = request.get('method', 'GET').upper()

        headers = {}
        for header in request.get('header', []):
            if header.get('disabled'):
                continue
            headers[header.get('key', '')] = header.get('value', '')

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

        params = {}
        for query in request.get('url', {}).get('query', []) if isinstance(request.get('url'), dict) else []:
            if not query.get('disabled'):
                params[query.get('key')] = query.get('value')

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
        path = '/'.join(url_dict.get('path', []))
        if path and not path.startswith('/'):
            path = '/' + path

        query = ''
        if url_dict.get('query'):
            query_parts = [f"{q.get('key')}={q.get('value')}" for q in url_dict['query']]
            query = '?' + '&'.join(query_parts)

        return path + query


# 全局变量存储测试结果
test_results = []


class PostmanAPITest(seldom.TestCase):
    """基于 Seldom 的 Postman API 测试类"""

    def __init__(self, api_config: Dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_config = api_config
        # 使用不同的属性名避免与 seldom 的 response/status_code 冲突
        self.api_response = None
        self.api_status_code = None
        self.api_response_data = None

    def test_api_request(self):
        """执行 API 测试"""
        api = self.api_config
        method = api['method'].lower()
        url = api['full_url']  # 使用完整URL
        headers = api.get('headers', {})
        params = api.get('params', {})
        body = api.get('body')

        try:
            # 使用 seldom 的 HTTP 方法
            if method == 'get':
                self.api_response = self.get(url, params=params, headers=headers)
            elif method == 'post':
                self.api_response = self.post(url, json=body, params=params, headers=headers)
            elif method == 'put':
                self.api_response = self.put(url, json=body, params=params, headers=headers)
            elif method == 'delete':
                self.api_response = self.delete(url, params=params, headers=headers)
            else:
                self.fail(f'不支持的HTTP方法: {method}')
                return

            # 通过 seldom 的 response 属性获取数据（只读）
            self.api_status_code = self.response.status_code

            try:
                self.api_response_data = self.response.json()
            except:
                self.api_response_data = self.response.text

            # 验证响应状态码
            expected_status = api.get('expected_status', 200)
            self.assertEqual(self.api_status_code, expected_status,
                           f'期望状态码: {expected_status}, 实际: {self.api_status_code}')

            # 记录成功结果
            result = {
                'name': api['name'],
                'method': api['method'],
                'url': api['full_url'],
                'status': 'PASSED',
                'message': f'响应状态码: {self.api_status_code}',
                'status_code': self.api_status_code,
                'folder': api.get('folder', '')
            }
            test_results.append(result)

        except Exception as e:
            # 记录失败结果
            result = {
                'name': api['name'],
                'method': api['method'],
                'url': api['full_url'],
                'status': 'FAILED',
                'message': str(e),
                'status_code': None,
                'folder': api.get('folder', '')
            }
            test_results.append(result)
            self.fail(f'API测试失败: {str(e)}')


def run_seldom_tests(postman_file: str, base_url: str = None):
    """
    运行基于 Seldom 的 Postman 测试

    :param postman_file: Postman JSON文件路径
    :param base_url: 基础URL（可选）
    """

    global test_results
    test_results = []  # 重置结果

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

    # 创建测试实例列表
    test_instances = []
    for api in apis:
        test_instance = PostmanAPITest(api)
        test_instances.append(test_instance)

    print(f"\n准备运行 {len(test_instances)} 个测试用例...")

    # 注意：seldom.main() 对于动态创建的测试类可能不工作，我们直接手动运行测试
    # 我们需要手动运行测试

    print("\n手动执行 API 测试...")
    for idx, test_instance in enumerate(test_instances, 1):
        api = test_instance.api_config
        print(f"  [{idx}/{len(test_instances)}] 测试: {api['name']} ({api['method']} {api['url']})")

        try:
            test_instance.test_api_request()
            print("    ✓ PASSED")
        except Exception as e:
            print(f"    ✗ FAILED: {str(e)}")

    return test_results


if __name__ == '__main__':
    if len(sys.argv) > 1:
        postman_file = sys.argv[1]
        base_url = sys.argv[2] if len(sys.argv) > 2 else None

        results = run_seldom_tests(postman_file, base_url)

        print(f"\n测试完成，共执行 {len(results)} 个API测试")
        passed = len([r for r in results if r['status'] == 'PASSED'])
        print(f"通过: {passed}, 失败: {len(results) - passed}")

    else:
        print("使用方法:")
        print("  python simple_seldom_tester.py <postman_file_path> [base_url]")
        print("\n参数说明:")
        print("  postman_file_path: Postman导出的JSON文件路径（必需）")
        print("  base_url: 基础URL（可选，将覆盖Postman文件中的配置）")