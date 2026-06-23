"""业务逻辑层的基类，统一错误处理与日志。

所有 service 类应继承这个基类。
"""

import logging
from typing import Any, Callable
from datetime import datetime
from postman_api_tester.exceptions import PostmanTestException, ExecutionError

logger = logging.getLogger(__name__)


class BaseService:
    """业务逻辑层的基类."""

    @staticmethod
    def safe_execute(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """安全执行业务逻辑，统一错误捕获。

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            PostmanTestException: 业务异常直接抛出
            ExecutionError: 其他异常被包装
        """
        try:
            result = func(*args, **kwargs)
            logger.debug("Service execution successful: %s", func.__name__, extra={"event": "service.success", "func_name": func.__name__})
            return result
        except PostmanTestException:
            # PostmanTestException 直接抛出，不做包装
            raise
        except Exception as e:
            logger.error("Unexpected error in %s: %s: %s", func.__name__, type(e).__name__, e, extra={"event": "service.error", "func_name": func.__name__, "error_type": type(e).__name__})
            raise ExecutionError(f"Service execution failed: {str(e)}") from e

    @staticmethod
    def log_event(
        event_name: str,
        level: str = "info",
        **extra_fields: Any,
    ) -> None:
        """结构化日志事件。

        Args:
            event_name: 事件名称
            level: 日志级别（info/warning/error/debug）
            **extra_fields: 额外的上下文字段
        """
        log_data = {
            "event": event_name,
            "timestamp": datetime.now().isoformat(),
            **extra_fields,
        }

        getattr(logger, level)(
            event_name,
            extra=log_data,
        )
