"""Compatibility layer for result-related utilities.

Real implementations are centralized in report_utils and response_parser.
"""

from postman_api_tester.utils.report_utils import compute_summary  # noqa: F401
from postman_api_tester.utils.response_parser import extract_msg_errcode  # noqa: F401

__all__ = ["extract_msg_errcode", "compute_summary"]
