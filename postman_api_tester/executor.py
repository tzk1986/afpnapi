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
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union

try:
    from postman_api_tester.assertions import evaluate_assertions as _evaluate_assertions
    _ASSERTIONS_AVAILABLE = True
except ImportError:
    _ASSERTIONS_AVAILABLE = False

from postman_api_tester.runtime_utils import normalize_url_and_params as _normalize_url_and_params
from postman_api_tester.db_feedback import build_db_feedback
from postman_api_tester.session import normalize_timeout

logger = logging.getLogger(__name__)


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
    request_info: Dict[str, Any]
    response_info: Dict[str, Any]
    assertion_results: List[Dict[str, Any]]
    assertion_engine_error: str
    db_feedback: Dict[str, Any]


class RequestInfo(TypedDict, total=False):
    """请求信息记录"""
    headers: Dict[str, str]
    params: Dict[str, Any]
    body: Optional[Union[str, Dict]]


class ResponseInfo(TypedDict, total=False):
    """响应信息记录"""
    headers: Dict[str, str]
    body: Union[str, Dict, Any]


class PostmanTestExecutor:
    """Postman API测试执行器"""

    def __init__(
        self,
        api_config: Dict,
        auth_token: str = None,
        session=None,
        request_timeout: Optional[Tuple[int, int]] = None,
        assertion_strict_mode: bool = False,
    ):
        """
        初始化执行器
        :param api_config: API配置信息
        :param auth_token: 认证token（可选）；每个实例独立持有，不共享，避免并发污染
        :param session: 可选的外部 requests.Session（由调用方统一管理生命周期）；
                        传入时本实例不拥有该 Session，execute_test 结束后不关闭它。
        :param request_timeout: 请求超时配置（connect_timeout, read_timeout）
        """
        import requests as _requests_mod
        self.api_config = api_config
        self.http_response = None
        self.resp_status_code = None
        self.response_data = None
        # 若调用方传入共享 Session 则复用；否则创建私有 Session（单独执行场景）
        self._owns_session = session is None
        self.session = session if session is not None else _requests_mod.Session()
        # 实例级别 token，不再使用类变量，避免多任务并发时互相覆盖
        self._auth_token: Optional[str] = auth_token or None
        self.request_timeout: Tuple[int, int] = normalize_timeout(request_timeout, default=(10, 30))
        self.assertion_strict_mode = bool(assertion_strict_mode)

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
        return {
            'name': api['name'],
            'method': api['method'],
            'url': api['full_url'],
            'actual_request_url': actual_request_url,
            'item_path': api.get('item_path', []),
            'expected_status': api.get('expected_status', 200),
            'status': status,
            'message': message,
            'err_code': err_code,
            'status_code': status_code,
            'folder': api.get('folder', ''),
            'response_time_ms': response_time_ms,
            'request_info': dict(request_info or {'headers': {}, 'params': {}, 'body': None}),
            'response_info': dict(response_info or {'headers': {}, 'body': ''}),
            'assertion_results': [],
            'assertion_engine_error': '',
        }

    def execute_test(self) -> TestResultRecord:
        """执行单个API测试，返回标准化结果记录"""
        api = self.api_config
        method = api['method'].lower()
        raw_url = api['full_url']  # 使用完整URL
        headers = api.get('headers', {}).copy()  # 复制headers避免修改原数据
        params = api.get('params', {})
        url, params = _normalize_url_and_params(raw_url, params)
        body = api.get('body')

        # 自动添加认证token（如果存在则始终覆盖，确保使用最新token）
        if self._auth_token:
            # 大小写不敏感地查找已有认证头，避免重复键
            headers_lower = {k.lower(): k for k in headers}
            if 'authorization' in headers_lower:
                orig_key = headers_lower['authorization']
                headers[orig_key] = f'Bearer {self._auth_token}'
            else:
                # 删除大小写不一致的 token 键，统一用小写 token
                for k in list(headers.keys()):
                    if k.lower() == 'token':
                        del headers[k]
                headers['token'] = self._auth_token

        try:
            import requests as _requests
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

            request_kwargs = {
                'params': params,
                'headers': headers,
                'timeout': self.request_timeout,
            }
            if method in {'post', 'put', 'patch'}:
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
            expected_status = api.get('expected_status', 200)

            # 准备请求和响应详情
            request_info = {
                'headers': headers,
                'params': params,
                'body': body
            }

            response_info = {
                'headers': dict(response.headers),
                'body': self.response_data
            }

            status_code_ok = self.resp_status_code == expected_status
            normalized_message = str(response_message or "").strip().lower()
            message_ok = (normalized_message == "") or (normalized_message == "success")

            if status_code_ok and message_ok:
                # 升级五：断言校验
                assertion_results: List[Dict] = []
                assertion_failed = False
                assertion_engine_error = ""
                assertions_rules = api.get('x_assertions') or []
                if assertions_rules and _ASSERTIONS_AVAILABLE:
                    try:
                        assertion_results = _evaluate_assertions(self.response_data, assertions_rules)
                        assertion_failed = any(not a.get('passed') for a in assertion_results)
                    except Exception as assertion_exc:
                        assertion_engine_error = str(assertion_exc)
                        logger.exception("断言引擎执行异常: %s", assertion_exc)
                        if self.assertion_strict_mode:
                            assertion_failed = True
                            assertion_results = [{
                                'passed': False,
                                'message': f'断言引擎异常: {assertion_engine_error}',
                            }]
                result = self._build_result_base(
                    actual_request_url=actual_request_url,
                    status='FAILED' if assertion_failed else 'PASSED',
                    message=('断言失败: ' + '; '.join(a['message'] for a in assertion_results if not a.get('passed'))) if assertion_failed else response_message,
                    err_code=err_code,
                    status_code=self.resp_status_code,
                    response_time_ms=response_time_ms,
                    request_info=request_info,
                    response_info=response_info,
                )
                result['assertion_results'] = assertion_results
                result['assertion_engine_error'] = assertion_engine_error
                return result
            else:
                if not status_code_ok:
                    fail_message = f'期望状态码: {expected_status}, 实际: {self.resp_status_code}; message: {response_message}'
                else:
                    fail_message = f'message 不满足成功条件(应为空或 success), 实际返回: {response_message}'

                db_feedback = build_db_feedback(
                    status='FAILED',
                    status_code=self.resp_status_code,
                    response_message=response_message,
                    err_code=err_code,
                    response_body=self.response_data,
                )
                fail_message_with_hint = fail_message
                if db_feedback.get('is_db_related'):
                    fail_message_with_hint = f"{fail_message} | 数据库反馈: {db_feedback.get('title')}"

                result = self._build_result_base(
                    actual_request_url=actual_request_url,
                    status='FAILED',
                    message=fail_message_with_hint,
                    err_code=err_code,
                    status_code=self.resp_status_code,
                    response_time_ms=response_time_ms,
                    request_info=request_info,
                    response_info=response_info,
                )
                result['db_feedback'] = db_feedback
                return result

        except Exception as e:
            import requests as _requests
            err_type = '请求超时' if isinstance(e, _requests.exceptions.Timeout) else '请求异常'

            db_feedback = build_db_feedback(
                status='ERROR',
                status_code=None,
                response_message=str(e),
                err_code='',
                response_body=str(e),
            )
            error_message = f'[{err_type}] {e}'
            if db_feedback.get('is_db_related'):
                error_message = f"{error_message} | 数据库反馈: {db_feedback.get('title')}"

            result = self._build_result_base(
                actual_request_url=raw_url,
                status='ERROR',
                message=error_message,
                err_code='',
                status_code=None,
                response_time_ms=0,
                request_info={'headers': headers, 'params': params, 'body': body},
                response_info={'headers': {}, 'body': str(e)},
            )
            result['db_feedback'] = db_feedback
            return result
        finally:
            # 仅当本实例拥有 Session（未传入外部 Session）时才关闭，避免提前终止共享连接池
            if self._owns_session:
                self.session.close()

    def _extract_message_and_err_code(self, response_data: Any) -> Tuple[str, str]:
        """从响应体中提取 message 与 errCode 字段，用于成功判定与报告查询。"""
        if not isinstance(response_data, dict):
            return "", ""

        message_keys = ["message", "msg", "error_message", "errorMessage", "errMsg"]
        err_code_keys = ["errCode", "errcode", "errorCode", "error_code", "code"]

        def pick_text(data: Dict[str, Any], keys: List[str]) -> str:
            for key in keys:
                if key in data and data[key] is not None:
                    return str(data[key]).strip()
            return ""

        message = pick_text(response_data, message_keys)
        err_code = pick_text(response_data, err_code_keys)

        payload = response_data.get("data")
        if isinstance(payload, dict):
            if not message:
                message = pick_text(payload, message_keys)
            if not err_code:
                err_code = pick_text(payload, err_code_keys)

        return message, err_code

