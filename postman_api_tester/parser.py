"""
Postman Collection 解析模块 - 集合解析与 API 配置提取

### 职责划分（async/sync）

**同步优先（SYNC-ONLY）**：
  - PostmanApiParser.extract_apis() - 集合解析与 API 提取
  - PostmanApiParser.extract_base_url() - 基础 URL 提取
  - PostmanApiParser._parse_item() - 递归项解析
  - PostmanApiParser._parse_request() - 请求解析

**说明**：
  所有导出接口均为**同步阻塞**操作。
  - JSON 文件 I/O 使用同步模式（load_file()）
  - 集合递归解析在同步上下文完成
  - 不提供原生 async 版本
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, TypedDict, Union
from urllib.parse import urljoin

from postman_api_tester.exceptions import ParseError

logger = logging.getLogger(__name__)


JsonObject = Dict[str, object]
AssertionConfig = Dict[str, object]


# === 类型定义 ===
class ApiConfig(TypedDict, total=False):
    """单个 API 配置信息（TypedDict 便于外部消费）"""
    name: str
    folder: str
    method: str
    url: str
    full_url: str
    headers: Dict[str, str]
    body: Optional[Union[str, JsonObject]]
    params: JsonObject
    expected_status: int
    description: str
    item_path: List[int]
    x_assertions: Optional[List[AssertionConfig]]
    x_expected_status: Optional[int]
    x_success_err_codes: Optional[str]
    x_success_messages: Optional[str]
    x_enable_err_code_judgment: Optional[bool]
    x_enable_message_judgment: Optional[bool]
    x_extract: Optional[Dict[str, str]]
    x_pre_request: Optional[Dict[str, str]]
    x_repeat: Optional[int]
    data_index: int
    data_row: Dict[str, str]


class PostmanApiParser:
    """Postman接口文件解析器"""

    def __init__(self, file_path: str) -> None:
        """
        初始化解析器
        :param file_path: Postman导出的JSON文件路径
        """
        self.file_path = file_path
        self.data: JsonObject = {}
        self.base_url = ""
        self.collections: List[ApiConfig] = []
        self.load_file()

    def load_file(self) -> None:
        """加载并解析Postman文件"""
        if not os.path.exists(self.file_path):
            raise ParseError(f"文件不存在: {self.file_path}")

        try:
            with open(self.file_path, encoding='utf-8') as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            raise ParseError(f"JSON文件格式错误: {e}") from e

    def extract_base_url(self) -> str:
        """
        从Postman文件中提取基础URL
        :return: 基础URL
        """
        raw_variables = self.data.get('variable')
        if isinstance(raw_variables, list):
            for var in raw_variables:
                if not isinstance(var, dict):
                    continue
                if var.get('key') == 'baseUrl' or var.get('key') == 'base_url':
                    self.base_url = var.get('value', '')

        # 如果没有找到baseUrl变量，尝试从第一个请求中提取
        if not self.base_url:
            raw_items = self.data.get('item')
            items = raw_items if isinstance(raw_items, list) else []
            first_item = items[0] if items and isinstance(items[0], dict) else None
            first_request = first_item.get('request') if isinstance(first_item, dict) else None
            if isinstance(first_request, dict):
                url = first_request.get('url')
                if isinstance(url, dict):
                    protocol = url.get('protocol', 'https')
                    if str(protocol).lower() not in ('http', 'https'):
                        logger.warning("ignoring non-http protocol in collection base_url: %s", protocol)
                    else:
                        self.base_url = f"{protocol}://{url.get('host', 'localhost')}"
                elif isinstance(url, str):
                    # 提取协议和主机
                    match = re.match(r'(https?://[^/]+)', url)
                    if match:
                        self.base_url = match.group(1)

        return self.base_url

    def extract_apis(self) -> List[ApiConfig]:
        """
        提取所有API接口信息
        :return: API列表
        """
        apis = []
        raw_items = self.data.get('item')
        items = raw_items if isinstance(raw_items, list) else []

        self.extract_base_url()

        for index, item in enumerate(items):
            apis.extend(self._parse_item(item, item_path=[index]))

        self.collections = apis
        return apis

    def _parse_item(self, item: Dict[str, Any], parent_name: str = "", item_path: Optional[List[int]] = None) -> List[ApiConfig]:
        """
        递归解析item（可能是文件夹或请求）
        :param item: item对象
        :param parent_name: 父级名称
        :return: API信息列表
        """
        apis = []

        item_path = list(item_path or [])

        # 如果是文件夹，递归处理
        if 'item' in item and 'request' not in item:
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

    def _parse_body(self, body_data: Dict[str, Any]) -> Any:
        """解析请求体，支持 raw/formdata/urlencoded/file 模式。"""
        if not body_data:
            return None

        mode = body_data.get('mode')
        if mode == 'raw':
            try:
                return json.loads(body_data.get('raw', '{}'))
            except (json.JSONDecodeError, ValueError, TypeError):
                return body_data.get('raw', '')
        elif mode == 'urlencoded':
            body = {}
            items = body_data.get(mode, [])
            for item_data in items:
                if not item_data.get('disabled'):
                    body[item_data.get('key')] = item_data.get('value')
            return body
        elif mode == 'formdata':
            # 保留完整结构，包括 type 和 upload_key，供执行器处理文件上传
            items = body_data.get(mode, [])
            formdata_items = []
            for item_data in items:
                if not item_data.get('disabled'):
                    formdata_items.append({
                        'key': item_data.get('key', ''),
                        'value': item_data.get('value', ''),
                        'type': item_data.get('type', 'text'),
                        'file_name': item_data.get('file_name', ''),
                        'upload_key': item_data.get('upload_key', ''),
                    })
            return {'__body_mode': 'formdata', 'formdata': formdata_items}
        elif mode == 'file':
            # binary 模式，保留文件名信息
            return {
                '__body_mode': 'binary',
                'file_name': body_data.get('src', ''),
                'upload_key': body_data.get('upload_key', ''),
            }
        return None

    def _parse_x_extensions(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """解析 x_* 扩展字段，返回非空字段字典。"""
        extensions: Dict[str, Any] = {}

        # 字符串类型扩展
        for field in ('x_success_err_codes', 'x_success_messages'):
            str_value = request.get(field)
            if str_value is not None:
                str_value = str(str_value).strip() or None
                if str_value is not None:
                    extensions[field] = str_value

        # 布尔类型扩展
        bool_fields = ('x_enable_err_code_judgment', 'x_enable_message_judgment')
        for field in bool_fields:
            bool_value: Any = request.get(field)
            if bool_value is not None:
                if not isinstance(bool_value, bool):
                    bool_value = str(bool_value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
                extensions[field] = bool_value

        # 字典类型扩展
        dict_fields = ('x_extract', 'x_pre_request')
        for field in dict_fields:
            value_raw = request.get(field)
            if isinstance(value_raw, dict) and value_raw:
                dict_value = {str(k): str(v) for k, v in value_raw.items() if isinstance(v, str)}
                if dict_value:
                    extensions[field] = dict_value

        # 整数类型扩展
        repeat_raw = request.get('x_repeat')
        if repeat_raw is not None:
            try:
                repeat_val = max(1, min(int(repeat_raw), 10))
                extensions['x_repeat'] = repeat_val
            except (TypeError, ValueError):
                pass

        return extensions

    def _parse_request(self, item: Dict[str, Any], parent_name: str = "", item_path: Optional[List[int]] = None) -> ApiConfig:
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
        body = self._parse_body(request.get('body', {}))

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

        # 解析 x_* 扩展字段
        extensions = self._parse_x_extensions(request)

        result: ApiConfig = {
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

        # 合并扩展字段
        for key, val in extensions.items():
            result[key] = val  # type: ignore[literal-required]

        return result

    def _normalize_api_name(self, name: object, method: str, url: str) -> str:
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

    def _build_url_from_dict(self, url_dict: JsonObject) -> str:
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
                if raw_url.startswith(('http://', 'https://')):
                    return raw_url
                if raw_url.startswith('{{') and '}}' in raw_url:
                    _, suffix = raw_url.split('}}', 1)
                    suffix = suffix.strip()
                    if suffix and not suffix.startswith('/'):
                        suffix = '/' + suffix
                    return suffix
                return raw_url

        query = ''
        raw_query = url_dict.get('query')
        if isinstance(raw_query, list):
            query_parts = [f"{q.get('key')}={q.get('value')}" for q in raw_query if isinstance(q, dict)]
            query = '?' + '&'.join(query_parts)

        return path + query
