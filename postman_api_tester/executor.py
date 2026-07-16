"""
Postman API 测试执行模块 - 单接口执行与结果收集

### 职责划分（async/sync）

**同步优先（SYNC-ONLY）**：
  - PostmanTestExecutor.execute_test() - 单接口执行（基于 requests.Session.method()）
  - PostmanTestExecutor.set_auth_token() / get_auth_token() - 认证令牌管理
  - PostmanTestExecutor._extract_message_and_err_code() - 响应解析

**说明**：
  所有导出接口均为**同步阻塞**操作。
  - HTTP 请求通过 requests 库完成（同步）
  - 断言评估与数据库反馈在同步上下文执行
  - 支持传入外部 requests.Session 以实现连接复用与并发（由上层管理 asyncio.gather 等）
  - 不提供原生 async/await 版本，保持简洁性
"""

import json
import logging
import time as _time_mod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, TYPE_CHECKING
if TYPE_CHECKING:
    from postman_api_tester.core.variable_context import VariableContext
from postman_api_tester.session import RequestTimeout

try:
    from postman_api_tester.assertions import evaluate_assertions as _evaluate_assertions
    _ASSERTIONS_AVAILABLE = True
except ImportError:
    _ASSERTIONS_AVAILABLE = False

from postman_api_tester.runtime_utils import normalize_url_and_params as _normalize_url_and_params
from postman_api_tester.db_feedback import build_db_feedback
from postman_api_tester.session import normalize_timeout
from postman_api_tester.parser import ApiConfig
from postman_api_tester.utils.response_parser import extract_msg_errcode as _extract_msg_errcode
from postman_api_tester.utils.judgment_utils import evaluate_result_judgment, resolve_judgment_params
from postman_api_tester import report_server_config as _rsc

logger = logging.getLogger(__name__)


JsonObject = Dict[str, object]
AssertionResult = Dict[str, object]


def _safe_int(value: object) -> int:
    """安全转换值为 int，失败时返回 0。"""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    return 0


# === 类型定义 ===
class TestResultRecord(TypedDict, total=False):
    """单个API测试结果记录（TypedDict 便于外部消费）"""
    name: str
    method: str
    url: str
    actual_request_url: str
    item_path: List[int]
    folder: str
    status: str  # 'PASSED', 'FAILED', 'ERROR'
    message: str
    err_code: str
    status_code: Optional[int]
    expected_status: int
    response_time_ms: int
    request_info: "RequestInfo"
    response_info: "ResponseInfo"
    assertion_results: List[AssertionResult]
    assertion_engine_error: str
    db_feedback: JsonObject
    data_index: int
    extracted_variables: Dict[str, str]
    repeat_index: int
    repeat_total: int
    repeat_group: str


class RequestInfo(TypedDict, total=False):
    """请求信息记录"""
    headers: Dict[str, str]
    params: JsonObject
    body: object


class ResponseInfo(TypedDict, total=False):
    """响应信息记录"""
    headers: Dict[str, str]
    body: object


class PostmanTestExecutor:
    """Postman API测试执行器"""

    def __init__(
        self,
        api_config: ApiConfig,
        auth_token: Optional[str] = None,
        session: Optional[object] = None,
        request_timeout: Optional[RequestTimeout] = None,
        assertion_strict_mode: bool = False,
        judgment_config: Optional[Dict[str, object]] = None,
        variable_context: Optional["VariableContext"] = None,
        repeat_index: int = 0,
        repeat_total: int = 1,
        repeat_group: str = "",
        uploaded_files: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        初始化执行器
        :param api_config: API配置信息
        :param auth_token: 认证token（可选）；每个实例独立持有，不共享，避免并发污染
        :param session: 可选的外部 requests.Session（由调用方统一管理生命周期）；
                        传入时本实例不拥有该 Session，execute_test 结束后不关闭它。
        :param request_timeout: 请求超时配置（connect_timeout, read_timeout）
        :param judgment_config: 任务级结果判定配置（可选），支持覆盖全局与集合配置
        :param variable_context: 可选的 VariableContext 实例，用于变量提取与替换
        :param repeat_index: 当前重复序号（从 0 开始），默认 0
        :param repeat_total: 总重复次数，默认 1
        :param repeat_group: 重复组标识，默认使用接口名
        :param uploaded_files: 上传文件路径映射（upload_key -> file_path），用于 formdata/binary 模式
        """
        import requests as _requests_mod
        self.api_config = dict(api_config)
        self.http_response: Optional[object] = None
        self.resp_status_code: Optional[int] = None
        self.response_data: Optional[object] = None
        self.variable_context: Optional["VariableContext"] = variable_context
        # 若调用方传入共享 Session 则复用；否则创建私有 Session（单独执行场景）
        self._owns_session = session is None
        self.session: object = session if session is not None else _requests_mod.Session()
        # 实例级别 token，不再使用类变量，避免多任务并发时互相覆盖
        self._auth_token: Optional[str] = auth_token or None
        self.request_timeout: Tuple[int, int] = normalize_timeout(request_timeout, default=(10, 30))
        self.assertion_strict_mode = bool(assertion_strict_mode)
        self.judgment_config: Optional[Dict[str, object]] = judgment_config if isinstance(judgment_config, dict) else None
        self._repeat_index = repeat_index
        self._repeat_total = repeat_total
        self._repeat_group = repeat_group or str(api_config.get('name') or '')
        self._uploaded_files: Dict[str, str] = uploaded_files if isinstance(uploaded_files, dict) else {}

    def start(self) -> None:
        """测试前准备"""
        pass

    def set_auth_token(self, token: str) -> None:
        """设置本实例的认证token（兼容旧调用）"""
        self._auth_token = token

    def get_auth_token(self) -> Optional[str]:
        """获取本实例的认证token"""
        return self._auth_token

    def _build_result_base(
        self,
        *,
        actual_request_url: str,
        status: str,
        message: str,
        err_code: str,
        status_code: Optional[int],
        response_time_ms: int,
        request_info: Optional[RequestInfo] = None,
        response_info: Optional[ResponseInfo] = None,
    ) -> TestResultRecord:
        """构建统一结果边界，避免不同分支字段漂移。"""
        api = self.api_config
        item_path_value = api.get('item_path')
        item_path = item_path_value if isinstance(item_path_value, list) else []
        expected_status_value = api.get('expected_status')
        expected_status = expected_status_value if isinstance(expected_status_value, int) else 200
        default_request_info: RequestInfo = {'headers': {}, 'params': {}, 'body': None}
        default_response_info: ResponseInfo = {'headers': {}, 'body': ''}
        return {
            'name': str(api.get('name') or ''),
            'method': str(api.get('method') or ''),
            'url': str(api.get('full_url') or ''),
            'actual_request_url': actual_request_url,
            'item_path': item_path,
            'expected_status': expected_status,
            'status': status,
            'message': message,
            'err_code': err_code,
            'status_code': status_code,
            'folder': str(api.get('folder') or ''),
            'response_time_ms': response_time_ms,
            'request_info': request_info or default_request_info,
            'response_info': response_info or default_response_info,
            'assertion_results': [],
            'assertion_engine_error': '',
            'data_index': _safe_int(api.get('data_index')),
            'extracted_variables': {},
            'repeat_index': self._repeat_index,
            'repeat_total': self._repeat_total,
            'repeat_group': self._repeat_group,
        }

    def _build_passed_result(
        self,
        *,
        actual_request_url: str,
        response_message: str,
        err_code: str,
        status_code: int,
        response_time_ms: int,
        request_info: RequestInfo,
        response_info: ResponseInfo,
        extracted_variables: Dict[str, str],
        assertion_results: List[AssertionResult],
        assertion_engine_error: str,
    ) -> TestResultRecord:
        """构建判定通过路径的结果（含断言校验结果）。"""
        assertion_failed = any(not a.get('passed') for a in assertion_results)
        if assertion_failed:
            fail_detail = '; '.join(str(a.get('message', '')) for a in assertion_results if not a.get('passed'))
            message = f'断言失败: {fail_detail}'
            status = 'FAILED'
        else:
            message = response_message
            status = 'PASSED'
        result = self._build_result_base(
            actual_request_url=actual_request_url,
            status=status,
            message=message,
            err_code=err_code,
            status_code=status_code,
            response_time_ms=response_time_ms,
            request_info=request_info,
            response_info=response_info,
        )
        result['assertion_results'] = assertion_results
        result['assertion_engine_error'] = assertion_engine_error
        result['extracted_variables'] = extracted_variables
        return result

    def _build_judgment_failed_result(
        self,
        *,
        actual_request_url: str,
        judgment_fail_reason: str,
        err_code: str,
        status_code: int,
        response_time_ms: int,
        request_info: RequestInfo,
        response_info: ResponseInfo,
        response_data: object,
        response_message: str,
        extracted_variables: Dict[str, str],
    ) -> TestResultRecord:
        """构建判定失败路径的结果（含数据库反馈）。"""
        db_feedback = build_db_feedback(
            status='FAILED',
            status_code=status_code,
            response_message=response_message,
            err_code=err_code,
            response_body=response_data,
        )
        fail_message = judgment_fail_reason
        if db_feedback.get('is_db_related'):
            fail_message = f"{judgment_fail_reason} | 数据库反馈: {db_feedback.get('title')}"
        result = self._build_result_base(
            actual_request_url=actual_request_url,
            status='FAILED',
            message=fail_message,
            err_code=err_code,
            status_code=status_code,
            response_time_ms=response_time_ms,
            request_info=request_info,
            response_info=response_info,
        )
        result['db_feedback'] = db_feedback
        result['extracted_variables'] = extracted_variables
        return result

    def _build_request_error_result(
        self,
        *,
        raw_url: str,
        headers: Dict[str, str],
        params: JsonObject,
        body: object,
        error: Exception,
    ) -> TestResultRecord:
        """构建请求异常路径的结果（含数据库反馈）。"""
        import requests as _requests
        if isinstance(error, _requests.exceptions.Timeout):
            err_type = '请求超时'
        elif isinstance(error, _requests.exceptions.ConnectionError):
            err_type = '连接失败'
        elif isinstance(error, _requests.exceptions.TooManyRedirects):
            err_type = '重定向过多'
        elif isinstance(error, _requests.exceptions.InvalidURL):
            err_type = 'URL无效'
        elif isinstance(error, _requests.exceptions.MissingSchema):
            err_type = 'URL缺少协议'
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            err_type = '数据处理异常'
        else:
            err_type = '请求异常'
        db_feedback = build_db_feedback(
            status='ERROR',
            status_code=None,
            response_message=str(error),
            err_code='',
            response_body=str(error),
        )
        error_message = f'[{err_type}] {error}'
        if db_feedback.get('is_db_related'):
            error_message = f"{error_message} | 数据库反馈: {db_feedback.get('title')}"
        error_request_info: RequestInfo = {'headers': headers, 'params': params, 'body': body}
        result = self._build_result_base(
            actual_request_url=raw_url,
            status='ERROR',
            message=error_message,
            err_code='',
            status_code=None,
            response_time_ms=0,
            request_info=error_request_info,
            response_info={'headers': {}, 'body': str(error)},
        )
        result['db_feedback'] = db_feedback
        return result

    def _execute_pre_request_and_substitute(self, api: ApiConfig) -> ApiConfig:
        """执行 pre-request 脚本并进行变量替换。"""
        if self.variable_context is None:
            return api

        from postman_api_tester.utils.variable_substitution import substitute_in_api_config

        local_vars: Dict[str, str] = {}
        pre_request_expr = api.get("x_pre_request")
        if pre_request_expr:
            from postman_api_tester.config import ENABLE_PRE_REQUEST_SCRIPT
            if ENABLE_PRE_REQUEST_SCRIPT:
                from postman_api_tester.utils.pre_request_executor import execute_pre_request
                local_vars = execute_pre_request(pre_request_expr, self.variable_context.variables)
                if local_vars:
                    logging.getLogger(__name__).debug("pre-request variables set: %s", list(local_vars.keys()))

        merged_vars = {**self.variable_context.variables, **local_vars}
        api = substitute_in_api_config(api, merged_vars)
        self.api_config = dict(api)
        return api

    def execute_test(self) -> TestResultRecord:
        """执行单个API测试，返回标准化结果记录"""
        from typing import cast
        api: ApiConfig = cast(ApiConfig, self.api_config)

        # 变量替换与 pre-request 脚本
        api = self._execute_pre_request_and_substitute(api)

        method = str(api.get('method') or 'GET').lower()
        raw_url = str(api.get('full_url') or '')
        raw_headers = api.get('headers')
        headers = dict(raw_headers) if isinstance(raw_headers, dict) else {}
        raw_params = api.get('params')
        params = raw_params if isinstance(raw_params, dict) else {}
        url, params = _normalize_url_and_params(raw_url, params)
        body = api.get('body')

        # 变量替换后 body 可能变为合法 JSON 字符串，尝试解析
        if isinstance(body, str) and body.strip().startswith(('{', '[')):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                pass

        # 注入认证 token（始终覆盖，确保使用最新 token）
        if self._auth_token:
            headers_lower = {k.lower(): k for k in headers}
            if 'authorization' in headers_lower:
                orig_key = headers_lower['authorization']
                headers[orig_key] = f'Bearer {self._auth_token}'
            else:
                for k in list(headers.keys()):
                    if k.lower() == 'token':
                        del headers[k]
                headers['token'] = self._auth_token

        try:
            response_time_ms: int = 0
            if method not in {'get', 'post', 'put', 'delete', 'patch'}:
                return self._build_result_base(
                    actual_request_url=raw_url,
                    status='FAILED',
                    message=f'不支持的HTTP方法: {method}',
                    err_code='',
                    status_code=None,
                    response_time_ms=0,
                    request_info={'headers': headers, 'params': params, 'body': body},
                    response_info={'headers': {}, 'body': ''},
                )

            request_kwargs: Dict[str, object] = {
                'params': params,
                'headers': headers,
                'timeout': self.request_timeout,
            }
            if method in {'post', 'put', 'patch'}:
                # 检查是否为 formdata 或 binary 模式
                body_dict = body if isinstance(body, dict) else None
                body_mode = body_dict.get('__body_mode') if body_dict else None
                if body_mode == 'formdata' and body_dict:
                    # 构建 multipart/form-data 请求
                    formdata_items: List[Dict[str, Any]] = body_dict.get('formdata', []) or []  # type: ignore[assignment]
                    data_rows: List[Tuple[str, str]] = []
                    file_rows: List[Tuple[str, Tuple[str, Any, str]]] = []
                    for item in formdata_items:
                        if not isinstance(item, dict):
                            continue
                        key = str(item.get('key', ''))
                        if item.get('type') == 'file':
                            upload_key = str(item.get('upload_key', ''))
                            file_path = self._uploaded_files.get(upload_key)
                            if file_path and Path(file_path).exists():
                                file_name = Path(file_path).name
                                file_rows.append((key, (file_name, open(file_path, 'rb'), 'application/octet-stream')))
                        else:
                            data_rows.append((key, str(item.get('value', ''))))
                    # 移除 Content-Type，让 requests 自动设置 multipart boundary
                    headers.pop('Content-Type', None)
                    headers.pop('content-type', None)
                    request_kwargs['headers'] = headers
                    request_kwargs['data'] = data_rows
                    request_kwargs['files'] = file_rows
                elif body_mode == 'binary' and body_dict:
                    # 构建 binary 请求
                    upload_key = str(body_dict.get('upload_key', ''))
                    file_path = self._uploaded_files.get(upload_key)
                    if file_path and Path(file_path).exists():
                        with open(file_path, 'rb') as f:
                            request_kwargs['data'] = f.read()
                        # 根据文件扩展名设置 Content-Type
                        ext = Path(file_path).suffix.lower()
                        content_type_map = {
                            '.json': 'application/json',
                            '.xml': 'application/xml',
                            '.txt': 'text/plain',
                            '.csv': 'text/csv',
                            '.pdf': 'application/pdf',
                            '.zip': 'application/zip',
                            '.png': 'image/png',
                            '.jpg': 'image/jpeg',
                            '.jpeg': 'image/jpeg',
                            '.gif': 'image/gif',
                        }
                        headers.setdefault('Content-Type', content_type_map.get(ext, 'application/octet-stream'))
                        request_kwargs['headers'] = headers
                    else:
                        request_kwargs['data'] = b''
                else:
                    request_kwargs['json'] = body

            _t0 = _time_mod.monotonic()
            response = getattr(self.session, method)(url, **request_kwargs)
            response_time_ms = round((_time_mod.monotonic() - _t0) * 1000)

            self.http_response = response
            self.resp_status_code = response.status_code
            actual_request_url = str(getattr(response.request, 'url', '') or url)

            try:
                self.response_data = response.json()
            except (json.JSONDecodeError, ValueError):
                self.response_data = response.text

            response_message, err_code = self._extract_message_and_err_code(self.response_data)

            # 验证响应
            expected_status_value = api.get('expected_status')
            expected_status = expected_status_value if isinstance(expected_status_value, int) else 200

            # 准备请求和响应详情
            request_info: RequestInfo = {
                'headers': headers,
                'params': params,
                'body': body
            }

            response_info: ResponseInfo = {
                'headers': dict(response.headers),
                'body': self.response_data
            }

            extracted_variables: Dict[str, str] = {}
            if self.variable_context is not None:
                raw_extract = api.get('x_extract')
                if isinstance(raw_extract, dict) and raw_extract:
                    extracted_variables = self.variable_context.update_from_extract(
                        raw_extract,
                        self.response_data,
                        dict(response.headers),
                    )

            # 可配置结果判定：优先级 任务级 > 集合接口级 x_* > 全局 config > 内置默认
            task_jcfg = self.judgment_config or {}

            def _opt_bool(val: object) -> Optional[bool]:
                return bool(val) if val is not None else None

            def _opt_str(val: object) -> Optional[str]:
                return str(val) if val is not None else None

            judgment_params = resolve_judgment_params(
                global_enable_err_code=_rsc.ENABLE_ERR_CODE_JUDGMENT,
                global_success_err_codes=_rsc.SUCCESS_ERR_CODES_SET,
                global_enable_message=_rsc.ENABLE_MESSAGE_JUDGMENT,
                global_success_messages=_rsc.SUCCESS_MESSAGES_SET,
                item_x_enable_err_code=_opt_bool(api.get('x_enable_err_code_judgment')),
                item_x_success_err_codes=_opt_str(api.get('x_success_err_codes')),
                item_x_enable_message=_opt_bool(api.get('x_enable_message_judgment')),
                item_x_success_messages=_opt_str(api.get('x_success_messages')),
                task_enable_err_code=_opt_bool(task_jcfg.get('enable_err_code_judgment')),
                task_success_err_codes=_opt_str(task_jcfg.get('success_err_codes')),
                task_enable_message=_opt_bool(task_jcfg.get('enable_message_judgment')),
                task_success_messages=_opt_str(task_jcfg.get('success_messages')),
            )

            judgment_passed, judgment_fail_reason = evaluate_result_judgment(
                status_code=self.resp_status_code,
                expected_status=expected_status,
                err_code=err_code,
                response_message=response_message,
                success_err_codes=judgment_params['success_err_codes'],
                success_messages=judgment_params['success_messages'],
                enable_err_code_judgment=judgment_params['enable_err_code_judgment'],
                enable_message_judgment=judgment_params['enable_message_judgment'],
            )

            if judgment_passed:
                # 升级五：断言校验
                assertion_results: List[AssertionResult] = []
                assertion_engine_error = ""
                raw_assertions = api.get('x_assertions')
                assertions_rules = [item for item in raw_assertions if isinstance(item, dict)] if isinstance(raw_assertions, list) else []
                if assertions_rules and _ASSERTIONS_AVAILABLE:
                    try:
                        assertion_results = _evaluate_assertions(self.response_data, assertions_rules)
                    except Exception as assertion_exc:
                        assertion_engine_error = str(assertion_exc)
                        logger.exception("断言引擎执行异常: %s", assertion_exc)
                        if self.assertion_strict_mode:
                            assertion_results = [{
                                'passed': False,
                                'message': f'断言引擎异常: {assertion_engine_error}',
                            }]
                return self._build_passed_result(
                    actual_request_url=actual_request_url,
                    response_message=response_message,
                    err_code=err_code,
                    status_code=self.resp_status_code,
                    response_time_ms=response_time_ms,
                    request_info=request_info,
                    response_info=response_info,
                    extracted_variables=extracted_variables,
                    assertion_results=assertion_results,
                    assertion_engine_error=assertion_engine_error,
                )
            else:
                return self._build_judgment_failed_result(
                    actual_request_url=actual_request_url,
                    judgment_fail_reason=judgment_fail_reason,
                    err_code=err_code,
                    status_code=self.resp_status_code,
                    response_time_ms=response_time_ms,
                    request_info=request_info,
                    response_info=response_info,
                    response_data=self.response_data,
                    response_message=response_message,
                    extracted_variables=extracted_variables,
                )

        except Exception as e:
            return self._build_request_error_result(
                raw_url=raw_url,
                headers=headers,
                params=params,
                body=body,
                error=e,
            )
        finally:
            # 仅当本实例拥有 Session（未传入外部 Session）时才关闭，避免提前终止共享连接池
            if self._owns_session:
                close_fn = getattr(self.session, 'close', None)
                if callable(close_fn):
                    close_fn()

    def _extract_message_and_err_code(self, response_data: object) -> Tuple[str, str]:
        """从响应体中提取 message 与 errCode 字段，委托到 response_parser.extract_msg_errcode。"""
        return _extract_msg_errcode(response_data)

