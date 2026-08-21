"""路由处理的基类，统一参数验证与响应包装。

所有 handler 模块中的路由函数应继承或使用这些静态方法。
"""

import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union

from flask import Flask, jsonify
from flask.typing import ResponseReturnValue

from postman_api_tester.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ReportNotFoundError(Exception):
    """报告未找到异常。"""

    def __init__(self, message: str, error_code: str = "") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


def register_error_handlers(app: Flask) -> None:
    """为 Flask app 注册全局异常处理器。

    在应用工厂和测试 fixture 中均应调用，确保异常返回统一 JSON 格式。
    """

    @app.errorhandler(ReportNotFoundError)
    def _handle_report_not_found(exc: ReportNotFoundError):  # type: ignore[no-untyped-def]
        response_body: Dict[str, Any] = {
            "code": "error",
            "message": exc.message,
            "data": None,
            "timestamp": datetime.now().isoformat(),
        }
        if exc.error_code:
            response_body["error_code"] = exc.error_code
        return jsonify(response_body), 404


class BaseHandler:
    """路由处理基类."""

    @staticmethod
    def validate_required_param(
        value: Any,
        param_name: str,
        param_type: Optional[type] = str,
    ) -> Any:
        """统一参数验证。

        Args:
            value: 参数值
            param_name: 参数名（用于错误消息）
            param_type: 期望的参数类型，None 表示跳过类型检查

        Returns:
            验证通过的参数值

        Raises:
            ValidationError: 参数缺失或类型不匹配
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(f"Missing required parameter: {param_name}")

        if param_type and not isinstance(value, param_type):
            raise ValidationError(
                f"Invalid type for {param_name}: expected {param_type.__name__}, got {type(value).__name__}"
            )

        return value

    @staticmethod
    def validate_string_length(
        value: str,
        param_name: str,
        max_length: int,
        min_length: int = 0,
    ) -> str:
        """字符串长度验证。

        Args:
            value: 字符串值
            param_name: 参数名（用于错误消息）
            max_length: 最大长度
            min_length: 最小长度（默认 0）

        Returns:
            验证通过的字符串

        Raises:
            ValidationError: 长度超出范围
        """
        if not isinstance(value, str):
            raise ValidationError(f"Invalid type for {param_name}: expected str")

        length = len(value)
        if length < min_length:
            raise ValidationError(f"{param_name} too short: {length} < {min_length}")
        if length > max_length:
            raise ValidationError(f"{param_name} too long: {length} > {max_length}")

        return value

    @staticmethod
    def validate_non_empty_string(
        value: Any,
        param_name: str,
        max_length: int = 255,
    ) -> str:
        """非空字符串验证（含长度检查）。

        Args:
            value: 参数值
            param_name: 参数名（用于错误消息）
            max_length: 最大长度（默认 255）

        Returns:
            验证通过的字符串

        Raises:
            ValidationError: 参数为空、非字符串或超长
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{param_name} 不能为空")

        value = value.strip()
        if len(value) > max_length:
            raise ValidationError(f"{param_name} too long: {len(value)} > {max_length}")

        return value

    @staticmethod
    def json_response(
        data: Any,
        status_code: int = 200,
        message: str = "OK",
    ) -> ResponseReturnValue:
        """统一 JSON 响应包装。

        Args:
            data: 响应数据
            status_code: HTTP 状态码
            message: 响应消息

        Returns:
            Flask 响应元组 (Response, status_code)
        """
        response_body = {
            "code": status_code,
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        return jsonify(response_body), status_code

    @staticmethod
    def error_response(
        error: Exception,
        status_code: int = 500,
        error_code: str = "",
    ) -> ResponseReturnValue:
        """统一错误响应包装。

        Args:
            error: 异常对象
            status_code: HTTP 状态码
            error_code: 应用级错误码，格式为 模块前缀_序号（如 CE_PARSE_001）

        Returns:
            Flask 错误响应
        """
        logger.error(
            "handler error: %s: %s",
            type(error).__name__,
            error,
            extra={
                "event": "handler.error",
                "error_type": type(error).__name__,
                "error_code": error_code,
            },
        )
        response_body = {
            "code": status_code,
            "message": "Error",
            "data": {
                "error": type(error).__name__,
                "details": str(error),
            },
            "timestamp": datetime.now().isoformat(),
        }
        if error_code:
            response_body["error_code"] = error_code
        return jsonify(response_body), status_code


def json_error(
    message: str, status_code: int, error_code: str = ""
) -> ResponseReturnValue:
    """快捷 JSON 错误响应，统一各路由文件的 _json_error 实现。

    错误码命名规则：模块前缀_序号，如 CE_PARSE_001。
    - CE_  = Collection Editor
    - COL_ = Collection 预览/导出
    - JOB_ = 任务执行
    - RPT_ = 报告相关
    - HTTP_ = 代理/重发请求
    - AUTH_ = 认证相关
    - COM_ = 通用错误
    """
    return BaseHandler.error_response(ValidationError(message), status_code, error_code)


def get_report_or_error(
    report_name: str,
    error_code: str,
    find_report: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """查找报告，不存在时抛出 ``ReportNotFoundError``。

    消除各路由文件中重复的 ``isinstance(report, tuple)`` 检查。
    Flask 全局错误处理器捕获 ``ReportNotFoundError`` 并返回 JSON 错误响应。

    Args:
        report_name: 报告名称
        error_code: 应用级错误码，如 COL_EXPORT_002
        find_report: 查找函数，默认使用 report_repository.find_report

    Returns:
        报告 dict

    Raises:
        ReportNotFoundError: 报告未找到时抛出
    """
    finder = find_report
    if finder is None:
        from postman_api_tester.report_repository import find_report as _default_finder

        finder = _default_finder
    try:
        return finder(report_name)
    except FileNotFoundError as exc:
        raise ReportNotFoundError(str(exc), error_code) from exc


_ErrorMap = Dict[Type[Exception], Tuple[int, str]]


def handle_api_errors(error_map: _ErrorMap) -> Callable:
    """路由函数异常统一捕获装饰器。

    消除 handler 中重复的 ``try / except FileNotFoundError / except ValueError /
    except Exception`` 模式。每种异常映射到 (HTTP 状态码, 错误码)。

    Args:
        error_map: 异常类型到 (status_code, error_code) 的映射。
            未列出的异常类型不会被捕获。

    Example::

        @handle_api_errors({
            FileNotFoundError: (404, "RPT_MANUAL_003"),
            ValueError:        (400, "RPT_MANUAL_004"),
            Exception:         (500, "RPT_MANUAL_004"),
        })
        def api_manual_case_add():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> ResponseReturnValue:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                for exc_type, (status, code) in error_map.items():
                    if isinstance(exc, exc_type):
                        if status >= 500:
                            logger.exception("%s error", func.__name__)
                        return json_error(str(exc), status, code)
                raise

        return wrapper

    return decorator
