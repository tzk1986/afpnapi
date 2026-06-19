"""路由处理的基类，统一参数验证与响应包装。

所有 handler 模块中的路由函数应继承或使用这些静态方法。
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple
from flask import jsonify
from flask.typing import ResponseReturnValue
from postman_api_tester.exceptions import PostmanTestException, ValidationError

logger = logging.getLogger(__name__)


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
            extra={"event": "handler.error", "error_type": type(error).__name__, "error_code": error_code},
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


def json_error(message: str, status_code: int, error_code: str = "") -> ResponseReturnValue:
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
) -> Any:
    """查找报告，不存在时返回 JSON 错误响应。

    消除各路由文件中重复的 ``_repo_find_report + FileNotFoundError`` 模式。
    调用方应检查返回值是否为 tuple（Flask 响应），是则直接 return。

    Args:
        report_name: 报告名称
        error_code: 应用级错误码，如 COL_EXPORT_002
        find_report: 查找函数，默认使用 report_repository.find_report

    Returns:
        报告 dict（成功时），或 Flask 错误响应（失败时）
    """
    finder = find_report
    if finder is None:
        from postman_api_tester.report_repository import find_report as _default_finder
        finder = _default_finder
    try:
        return finder(report_name)
    except FileNotFoundError:
        return json_error(f"报告不存在：{report_name}", 404, error_code)
