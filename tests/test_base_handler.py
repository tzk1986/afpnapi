"""BaseHandler 单元测试."""

from typing import Generator

import pytest
from flask import Flask
from postman_api_tester.handlers.base_handler import BaseHandler
from postman_api_tester.exceptions import ValidationError


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 应用上下文."""
    app = Flask(__name__)
    with app.app_context():
        yield


def test_validate_required_param_success() -> None:
    """验证参数校验成功."""
    result = BaseHandler.validate_required_param("value", "param_name", str)
    assert result == "value"


def test_validate_required_param_missing() -> None:
    """验证缺失参数抛异常."""
    with pytest.raises(ValidationError, match="Missing required parameter"):
        BaseHandler.validate_required_param(None, "param_name", str)


def test_validate_required_param_empty_string() -> None:
    """验证空字符串抛异常."""
    with pytest.raises(ValidationError, match="Missing required parameter"):
        BaseHandler.validate_required_param("  ", "param_name", str)


def test_validate_required_param_wrong_type() -> None:
    """验证类型不匹配抛异常."""
    with pytest.raises(ValidationError, match="Invalid type"):
        BaseHandler.validate_required_param(123, "param_name", str)


def test_json_response(app_context: None) -> None:
    """验证 JSON 响应包装."""
    response, status = BaseHandler.json_response({"key": "value"}, 200)
    assert status == 200
    import json
    data = json.loads(response.get_data(as_text=True))
    assert data["code"] == 200
    assert data["data"] == {"key": "value"}
    assert "timestamp" in data


def test_error_response(app_context: None) -> None:
    """验证错误响应包装."""
    error = ValidationError("Test error")
    response, status = BaseHandler.error_response(error, 400)
    assert status == 400
    import json
    data = json.loads(response.get_data(as_text=True))
    assert data["code"] == 400
    assert "ValidationError" in data["data"]["error"]
