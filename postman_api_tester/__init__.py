"""Postman API 自动化测试工具包。

开发导读:
- 作为对外入口统一导出解析器、执行器、报告对象与运行函数。
- 业务调用建议优先使用 run_postman_tests，避免直接依赖内部细节。
"""

from .parser import PostmanApiParser
from .executor import PostmanTestExecutor
from .postman_api_tester import (
    PostmanTestReport,
    run_postman_tests
)

__version__ = "1.24.3"
__author__ = "API Testing Team"

__all__ = [
    'PostmanApiParser',
    'PostmanTestExecutor',
    'PostmanTestReport',
    'run_postman_tests'
]
