"""server_routes 单元测试。"""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from postman_api_tester.handlers.server_routes import (
    api_environments,
    api_report_delete,
    health,
    log_metrics,
)


@pytest.fixture  # type: ignore[untyped-decorator]
def app_context() -> Generator[None, None, None]:
    """提供 Flask 应用上下文。"""
    app = Flask(__name__)
    with app.test_request_context():
        yield


class TestHealth:
    """健康检查端点测试。"""

    def test_health_returns_dict(self, app_context: None) -> None:
        """health 返回字典 payload。"""
        with patch(
            "postman_api_tester.handlers.server_routes.build_health_payload"
        ) as mock_build:
            mock_build.return_value = {"status": "ok"}
            result = health()
            assert result.json == {"status": "ok"}
            mock_build.assert_called_once()


class TestLogMetrics:
    """日志指标端点测试。"""

    def test_log_metrics_returns_dict(self, app_context: None) -> None:
        """log_metrics 返回字典 payload。"""
        with patch(
            "postman_api_tester.handlers.server_routes.get_log_metrics_snapshot"
        ) as mock_snap:
            mock_snap.return_value = {"counter": 1}
            result = log_metrics()
            assert result.json == {"counter": 1}


class TestApiEnvironments:
    """环境列表端点测试。"""

    def test_api_environments_with_empty_envs(self, app_context: None) -> None:
        """空环境配置返回空列表。"""
        with patch(
            "postman_api_tester.handlers.server_routes.ENVIRONMENTS", {}
        ), patch(
            "postman_api_tester.handlers.server_routes.DEFAULT_ENV_NAME", ""
        ), patch(
            "postman_api_tester.handlers.server_routes.build_environments_payload"
        ) as mock_build:
            mock_build.return_value = {"envs": [], "default": ""}
            result = api_environments()
            assert result.json == {"envs": [], "default": ""}

    def test_api_environments_hides_token(self, app_context: None) -> None:
        """环境列表不暴露 token 值。"""
        with patch(
            "postman_api_tester.handlers.server_routes.ENVIRONMENTS",
            {"prod": {"base_url": "http://x", "token": "secret"}},
        ), patch(
            "postman_api_tester.handlers.server_routes.DEFAULT_ENV_NAME", "prod"
        ), patch(
            "postman_api_tester.handlers.server_routes.build_environments_payload"
        ) as mock_build:
            mock_build.return_value = {"envs": [{"name": "prod", "base_url": "http://x", "has_token": True}]}
            result = api_environments()
            payload = mock_build.call_args[1]
            env_list = payload["env_list"]
            assert env_list[0]["has_token"] is True
            assert "token" not in env_list[0]


class TestApiReportDelete:
    """报告删除端点测试。"""

    def test_api_report_delete_success(self, app_context: None) -> None:
        """删除存在的报告返回成功。"""
        with patch(
            "postman_api_tester.services.report_delete_service.delete_report_artifacts"
        ) as mock_delete:
            mock_delete.return_value = ["file1.json"]
            result = api_report_delete("test_report")
            # jsonify 返回 Response 对象
            from flask import Response
            assert isinstance(result, Response)

    def test_api_report_delete_not_found(self, app_context: None) -> None:
        """删除不存在的报告返回 404。"""
        with patch(
            "postman_api_tester.services.report_delete_service.delete_report_artifacts"
        ) as mock_delete:
            mock_delete.side_effect = FileNotFoundError()
            result = api_report_delete("missing_report")
            assert isinstance(result, tuple)
            assert result[1] == 404
