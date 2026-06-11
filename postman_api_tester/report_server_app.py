"""报告服务应用工厂与生命周期管理。

职责：
- 创建 Flask app 实例
- 配置应用参数
- 初始化全局组件（报告目录、仓库等）
- 注册中间件
- 提供生产级 WSGI 服务器入口
"""

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, Response, request

from postman_api_tester.report_meta_repository import configure_reports_dir, configure_scan_excludes
from postman_api_tester.report_repository import configure_report_repository
from postman_api_tester.report_job_store import configure_run_jobs
from postman_api_tester.utils.logging_utils import (
    configure_logging_from_config,
    get_log_sample_rate,
    log_sampled,
)

configure_logging_from_config(service_name="report_server")
logger = logging.getLogger(__name__)
ACCESS_LOG_SAMPLE_RATE = get_log_sample_rate(default=0.1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ReportServerApp:
    """报告服务应用工厂。"""

    @staticmethod
    def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
        """创建 Flask app 实例。

        Args:
            config: 可选配置字典

        Returns:
            配置完成的 Flask 应用实例
        """
        template_folder = str((PROJECT_ROOT / "templates").resolve())
        app = Flask(__name__, template_folder=template_folder)

        # 加载配置
        app_config = config or {}
        app.config.update(app_config)

        # 初始化组件
        ReportServerApp._initialize_components(app)

        # 注册中间件
        ReportServerApp._register_middleware(app)

        logger.info("ReportServerApp created successfully")
        return app

    @staticmethod
    def _initialize_components(app: Flask) -> None:
        """初始化全局组件。"""
        reports_dir = ReportServerApp._resolve_reports_dir()
        reports_dir.mkdir(parents=True, exist_ok=True)
        app.config["REPORTS_DIR"] = reports_dir

        uploads_dir = (PROJECT_ROOT / "uploaded_collections").resolve()
        uploads_dir.mkdir(parents=True, exist_ok=True)
        app.config["UPLOADS_DIR"] = uploads_dir

        exports_dir = (uploads_dir / "exports").resolve()
        exports_dir.mkdir(parents=True, exist_ok=True)
        app.config["EXPORTS_DIR"] = exports_dir

        configure_reports_dir(reports_dir)
        from postman_api_tester.report_server_config import REPORT_SCAN_EXCLUDE_DIRS
        configure_scan_excludes(REPORT_SCAN_EXCLUDE_DIRS)
        configure_report_repository(reports_dir, cache_ttl=30.0)

        max_jobs = 200
        try:
            from postman_api_tester import config as cfg

            max_jobs = int(getattr(cfg, "RUN_JOBS_MAX", 200))
        except Exception:
            pass
        configure_run_jobs(max_jobs)

        logger.debug("Components initialized: reports_dir=%s", reports_dir)

    @staticmethod
    def _resolve_reports_dir() -> Path:
        """解析报告目录。"""
        env_dir = (
            os.environ.get("POSTMAN_REPORTS_DIR")
            or os.environ.get("REPORTS_DIR")
            or ""
        ).strip()
        if env_dir:
            return Path(env_dir).expanduser().resolve()

        try:
            from postman_api_tester import config as cfg

            cfg_dir = getattr(cfg, "REPORT_OUTPUT_DIR", "").strip()
            if cfg_dir:
                return Path(cfg_dir).expanduser().resolve()
        except Exception:
            pass

        return (PROJECT_ROOT / "reports").resolve()

    @staticmethod
    def _register_middleware(app: Flask) -> None:
        """注册请求/响应中间件。"""

        @app.before_request
        def _capture_request_start() -> None:
            """记录请求开始时间。"""
            request.environ["_request_start_at"] = time.perf_counter()
            request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
            request.environ["_request_id"] = request_id

        @app.after_request
        def _log_access(response: Response) -> Response:
            """记录请求访问日志。"""
            started_at = request.environ.get("_request_start_at")
            duration_ms = 0
            if isinstance(started_at, (int, float)):
                duration_ms = round((time.perf_counter() - started_at) * 1000)

            request_id = str(request.environ.get("_request_id") or "")
            extra_payload = {
                "event": "http.access.logged",
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": int(response.status_code),
                "duration_ms": duration_ms,
                "remote_addr": request.remote_addr or "",
            }
            if request.user_agent and request.user_agent.string:
                extra_payload["user_agent"] = request.user_agent.string

            level = logging.WARNING if response.status_code >= 500 else logging.INFO
            sample_rate = 1.0 if response.status_code >= 400 else ACCESS_LOG_SAMPLE_RATE
            log_sampled(
                logger,
                level,
                "http_request",
                sample_rate=sample_rate,
                extra=extra_payload,
            )
            if request_id:
                response.headers["X-Request-Id"] = request_id
            return response

    @staticmethod
    def run_app(app: Flask) -> None:
        """运行应用。"""
        reports_dir = app.config.get("REPORTS_DIR")
        if reports_dir:
            reports_dir.mkdir(parents=True, exist_ok=True)

        try:
            from postman_api_tester.config import REPORT_SERVER_PORT, REPORT_SERVER_HOST
            port = REPORT_SERVER_PORT
            host = REPORT_SERVER_HOST
        except ImportError:
            port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
            host = os.environ.get("REPORT_SERVER_HOST", "0.0.0.0")

        logger.info("报告目录: %s", reports_dir)
        logger.info("报告服务启动: http://127.0.0.1:%d", port)

        try:
            from waitress import serve

            logger.info("使用 waitress WSGI 服务器（生产模式）")
            serve(app, host=host, port=port)
        except ImportError:
            logger.warning(
                "waitress 未安装，降级使用 Flask 开发服务器（建议 pip install waitress）"
            )
            app.run(host=host, port=port, debug=False)
