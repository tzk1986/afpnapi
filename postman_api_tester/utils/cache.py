"""Compatibility cache helpers.

Real cache invalidation logic is centralized in report_repository.
"""

from postman_api_tester.report_repository import invalidate_reports_cache  # noqa: F401

__all__ = ["invalidate_reports_cache"]
