class PostmanTestException(Exception):
    """Base exception for postman_api_tester runtime and validation errors."""


class ParseError(PostmanTestException, ValueError):
    """Raised when collection input cannot be parsed."""


class ValidationError(PostmanTestException, ValueError):
    """Raised when caller input fails runtime validation."""


class ExecutionError(PostmanTestException, RuntimeError):
    """Raised when request execution fails unexpectedly."""
