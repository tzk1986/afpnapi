#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告中心兼容启动器。

用法:
    python report_server.py

访问地址:
    http://127.0.0.1:5000
"""

from postman_api_tester.report_server import app
from postman_api_tester.report_server_app import ReportServerApp

if __name__ == "__main__":
    ReportServerApp.run_app(app)
