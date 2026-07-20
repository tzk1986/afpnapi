"""Compatibility layer for result-related utilities.

Real implementations are centralized in report_utils and response_parser.
"""

"""开发导读：
- 职责：结果工具兼容导出层，避免历史模块引用中断。
- 真实实现：compute_summary 在 report_utils，extract_msg_errcode 在 response_parser。
"""

from postman_api_tester.utils.report_utils import compute_summary
from postman_api_tester.utils.response_parser import extract_msg_errcode

__all__ = ["extract_msg_errcode", "compute_summary"]
