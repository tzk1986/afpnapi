"""
Postman API 自动化测试工具

基于Seldom框架的Postman接口测试自动化解决方案
支持读取APIFox/Postman导出的接口文件，自动执行测试，生成详细报告
"""

from .postman_api_tester import (
    PostmanApiParser,
    PostmanTestExecutor,
    PostmanTestReport,
    run_postman_tests
)

__version__ = "1.0.1"
__author__ = "API Testing Team"

__all__ = [
    'PostmanApiParser',
    'PostmanTestExecutor',
    'PostmanTestReport',
    'run_postman_tests'
]
