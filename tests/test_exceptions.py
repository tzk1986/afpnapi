"""异常体系单元测试."""

import pytest
from postman_api_tester.exceptions import (
    PostmanTestException,
    ParseError,
    InvalidCollectionFormat,
    UnsupportedSpecVersion,
    CollectionStructureError,
    ValidationError,
    InvalidParameter,
    MissingAuthToken,
    InvalidUrl,
    InvalidAssertion,
    ExecutionError,
    RequestTimeout,
    AssertionFailure,
    CheckpointRecoveryFailed,
    NetworkError,
    FileOperationError,
    CacheError,
)


def test_exception_hierarchy() -> None:
    """验证异常继承关系."""
    # ParseError 族
    assert issubclass(InvalidCollectionFormat, ParseError)
    assert issubclass(UnsupportedSpecVersion, ParseError)
    assert issubclass(CollectionStructureError, ParseError)

    # ValidationError 族
    assert issubclass(InvalidParameter, ValidationError)
    assert issubclass(MissingAuthToken, ValidationError)
    assert issubclass(InvalidUrl, ValidationError)
    assert issubclass(InvalidAssertion, ValidationError)

    # ExecutionError 族
    assert issubclass(RequestTimeout, ExecutionError)
    assert issubclass(AssertionFailure, ExecutionError)
    assert issubclass(CheckpointRecoveryFailed, ExecutionError)
    assert issubclass(NetworkError, ExecutionError)

    # 根类
    assert issubclass(ParseError, PostmanTestException)
    assert issubclass(ValidationError, PostmanTestException)
    assert issubclass(ExecutionError, PostmanTestException)
    assert issubclass(FileOperationError, PostmanTestException)
    assert issubclass(CacheError, PostmanTestException)


def test_exception_instantiation() -> None:
    """验证异常可实例化."""
    exc = InvalidCollectionFormat("Invalid JSON at line 1")
    assert "Invalid JSON" in str(exc)
    assert isinstance(exc, ParseError)
    assert isinstance(exc, PostmanTestException)


def test_exception_with_cause() -> None:
    """验证异常链."""
    try:
        raise ValueError("JSON error")
    except ValueError as e:
        try:
            raise InvalidCollectionFormat("Parse failed") from e
        except InvalidCollectionFormat as exc:
            assert exc.__cause__.__class__.__name__ == "ValueError"
