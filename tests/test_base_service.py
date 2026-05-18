"""BaseService 单元测试."""

import logging
from typing import Generator

import pytest
from postman_api_tester.services.base_service import BaseService
from postman_api_tester.exceptions import ExecutionError, ValidationError


@pytest.fixture  # type: ignore[untyped-decorator]
def caplog_fixture(caplog: pytest.LogCaptureFixture) -> Generator[pytest.LogCaptureFixture, None, None]:
    """提供日志捕获 fixture."""
    caplog.set_level(logging.INFO, logger="postman_api_tester.services.base_service")
    yield caplog


def test_safe_execute_success() -> None:
    """验证安全执行成功."""
    def success_func(a: int, b: int) -> int:
        return a + b

    result = BaseService.safe_execute(success_func, 2, 3)
    assert result == 5


def test_safe_execute_postman_exception() -> None:
    """验证 PostmanTestException 直接抛出."""
    def failing_func() -> None:
        raise ValidationError("Validation failed")

    with pytest.raises(ValidationError, match="Validation failed"):
        BaseService.safe_execute(failing_func)


def test_safe_execute_unexpected_exception() -> None:
    """验证其他异常被包装为 ExecutionError."""
    def failing_func() -> None:
        raise RuntimeError("Unexpected error")

    with pytest.raises(ExecutionError, match="Unexpected error"):
        BaseService.safe_execute(failing_func)


def test_log_event(caplog_fixture: pytest.LogCaptureFixture) -> None:
    """验证事件日志记录."""
    BaseService.log_event("test_event", "info", user_id="123", action="create")
    assert "test_event" in caplog_fixture.text
