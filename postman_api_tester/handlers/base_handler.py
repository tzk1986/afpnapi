"""路由处理的基类，统一参数验证与响应包装。

所有 handler 模块中的路由函数应继承或使用这些静态方法。
"""

import logging
from datetime import datetime
from typing import Any, Optional, Type, Tuple
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
    ) -> ResponseReturnValue:
        """统一错误响应包装。

        Args:
            error: 异常对象
            status_code: HTTP 状态码

        Returns:
            Flask 错误响应
        """
        logger.error(f"Handler error: {type(error).__name__}: {error}")
        return BaseHandler.json_response(
            {
                "error": type(error).__name__,
                "details": str(error),
            },
            status_code=status_code,
            message="Error",
        )


def json_error(message: str, status_code: int) -> ResponseReturnValue:
    """快捷 JSON 错误响应，统一各路由文件的 _json_error 实现。"""
    return BaseHandler.error_response(ValidationError(message), status_code)
