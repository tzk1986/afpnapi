"""统一异常定义模块。

开发导读:
- 定义解析、校验、执行三类核心异常。
- 用于跨层统一错误语义与调用方捕获策略。
"""

class PostmanTestException(Exception):
    """Base exception for postman_api_tester runtime and validation errors."""


class ParseError(PostmanTestException, ValueError):
    """Raised when collection input cannot be parsed."""


class ValidationError(PostmanTestException, ValueError):
    """Raised when caller input fails runtime validation."""


class ExecutionError(PostmanTestException, RuntimeError):
    """Raised when request execution fails unexpectedly."""
