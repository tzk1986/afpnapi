"""报告中心包级启动入口。

用法:
    python -m postman_api_tester

等效于原根目录 python report_server.py。
"""

from postman_api_tester.report_server import app
from postman_api_tester.report_server_app import ReportServerApp

if __name__ == "__main__":
    ReportServerApp.run_app(app)
