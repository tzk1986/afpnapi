"""统一异常定义模块。

开发导读:
- 定义解析、校验、执行、资源四类核心异常。
- 用于跨层统一错误语义与调用方捕获策略。
- 异常抛出时必须指定根因（使用 from e）。
"""


# ===== 基类 =====

class PostmanTestException(Exception):
    """Base exception for postman_api_tester runtime and validation errors."""


# ===== 解析异常（Tier 1：Collection 加载时） =====

class ParseError(PostmanTestException, ValueError):
    """Raised when collection input cannot be parsed."""


class InvalidCollectionFormat(ParseError):
    """Collection JSON 格式不合法."""


class UnsupportedSpecVersion(ParseError):
    """Collection spec 版本不支持."""


class CollectionStructureError(ParseError):
    """Collection 结构不符合预期."""


# ===== 校验异常（Tier 2：参数验证时） =====

class ValidationError(PostmanTestException, ValueError):
    """Raised when caller input fails runtime validation."""


class InvalidParameter(ValidationError):
    """参数类型或值不合法."""


class MissingAuthToken(ValidationError):
    """认证 token 缺失."""


class InvalidUrl(ValidationError):
    """URL 格式不合法."""


class InvalidAssertion(ValidationError):
    """断言配置不合法."""


# ===== 执行异常（Tier 3：运行时） =====

class ExecutionError(PostmanTestException, RuntimeError):
    """Raised when request execution fails unexpectedly."""


class RequestTimeout(ExecutionError):
    """请求超时."""


class AssertionFailure(ExecutionError):
    """断言执行失败."""


class CheckpointRecoveryFailed(ExecutionError):
    """断点恢复失败."""


class NetworkError(ExecutionError):
    """网络连接错误."""


# ===== 资源异常（Tier 4：资源管理） =====

class FileOperationError(PostmanTestException):
    """文件操作异常."""


class CacheError(PostmanTestException):
    """缓存异常."""
