import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from postman_api_tester.exceptions import ParseError

logger = logging.getLogger(__name__)


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
            raise ParseError(f"文件不存在: {self.file_path}")

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            raise ParseError(f"JSON文件格式错误: {e}")

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

        for index, item in enumerate(items):
            apis.extend(self._parse_item(item, item_path=[index]))

        self.collections = apis
        return apis

    def _parse_item(self, item: Dict, parent_name: str = "", item_path: Optional[List[int]] = None) -> List[Dict]:
        """
        递归解析item（可能是文件夹或请求）
        :param item: item对象
        :param parent_name: 父级名称
        :return: API信息列表
        """
        apis = []

        item_path = list(item_path or [])

        # 如果是文件夹，递归处理
        if 'item' in item and not 'request' in item:
            folder_name = item.get('name', '')
            for sub_index, sub_item in enumerate(item['item']):
                apis.extend(self._parse_item(sub_item, folder_name, item_path=item_path + [sub_index]))

        # 解析请求
        elif 'request' in item:
            api_info = self._parse_request(item, parent_name, item_path=item_path)
            if api_info:
                # 校验必填字段：name/method/url 任一缺失则跳过，避免执行层崩溃
                _missing = [k for k in ('name', 'method', 'url') if not api_info.get(k)]
                if _missing:
                    logger.warning("跳过无效 API（字段缺失: %s）: %s", _missing, api_info)
                else:
                    apis.append(api_info)

        return apis

    def _parse_request(self, item: Dict, parent_name: str = "", item_path: Optional[List[int]] = None) -> Dict:
        """
        解析单个请求
        :param item: item对象
        :param parent_name: 父级名称（文件夹）
        :return: API信息
        """
        request = item.get('request', {})

        # 解析URL
        url = request.get('url', '')
        if isinstance(url, dict):
            url = self._build_url_from_dict(url)

        # 解析方法
        method = request.get('method', 'GET').upper()
        name = self._normalize_api_name(item.get('name', ''), method, url)

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
                except (json.JSONDecodeError, ValueError, TypeError):
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
        # 兼容报告中心 ad-hoc 请求写入的扩展字段 x_expected_status。
        try:
            expected_status = int(request.get('x_expected_status', 200))
        except (TypeError, ValueError):
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
            'description': item.get('description', ''),
            'item_path': list(item_path or []),
        }

    def _normalize_api_name(self, name: Any, method: str, url: str) -> str:
        text = str(name or '').strip()
        if text and not re.fullmatch(r'[?？\s_]+', text):
            return text

        url_text = str(url or '').strip()
        if not url_text:
            return f"{method} 接口"

        if url_text.startswith('{{baseUrl}}'):
            url_text = url_text[len('{{baseUrl}}'):] or '/'
        elif url_text.startswith('{{base_url}}'):
            url_text = url_text[len('{{base_url}}'):] or '/'

        match = re.match(r'https?://[^/]+(.*)$', url_text)
        if match:
            url_text = match.group(1) or '/'

        if not url_text.startswith('/'):
            url_text = '/' + url_text

        return f"{method} {url_text}"

    def _build_url_from_dict(self, url_dict: Dict) -> str:
        """
        从字典格式的URL构建字符串URL
        :param url_dict: URL字典
        :return: URL字符串
        """
        path_parts = url_dict.get('path', [])
        path = '/'.join(path_parts) if isinstance(path_parts, list) else ''
        if path and not path.startswith('/'):
            path = '/' + path

        # 兼容仅提供 raw 的 URL（常见于导出后再次导入场景）
        if not path:
            raw_url = str(url_dict.get('raw') or '').strip()
            if raw_url:
                if raw_url.startswith('http://') or raw_url.startswith('https://'):
                    return raw_url
                if raw_url.startswith('{{') and '}}' in raw_url:
                    _, suffix = raw_url.split('}}', 1)
                    suffix = suffix.strip()
                    if suffix and not suffix.startswith('/'):
                        suffix = '/' + suffix
                    return suffix
                return raw_url

        query = ''
        if url_dict.get('query'):
            query_parts = [f"{q.get('key')}={q.get('value')}" for q in url_dict['query']]
            query = '?' + '&'.join(query_parts)

        return path + query
