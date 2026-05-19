"""ReportServerApp 单元测试。"""

import pytest
from postman_api_tester.report_server_app import ReportServerApp


class TestReportServerApp:
    """ReportServerApp 测试套件。"""

    def test_create_app(self) -> None:
        """测试应用工厂创建。"""
        app = ReportServerApp.create_app()
        assert app is not None
        assert "report_server" in app.name

    def test_app_has_config(self) -> None:
        """测试应用已配置必要参数。"""
        app = ReportServerApp.create_app()
        assert "REPORTS_DIR" in app.config
        assert "UPLOADS_DIR" in app.config
        assert "EXPORTS_DIR" in app.config

    def test_app_template_folder(self) -> None:
        """测试模板文件夹已设置。"""
        app = ReportServerApp.create_app()
        assert app.template_folder is not None

    def test_resolve_reports_dir(self) -> None:
        """测试报告目录解析返回有效路径。"""
        path = ReportServerApp._resolve_reports_dir()
        assert path is not None
        assert path.is_absolute()
