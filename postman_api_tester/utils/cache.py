"""Compatibility cache helpers.

Real cache invalidation logic is centralized in report_repository.
"""

"""开发导读：
- 职责：缓存能力兼容转发层，避免历史导入路径失效。
- 真实实现：postman_api_tester.report_repository.invalidate_reports_cache。
"""

from postman_api_tester.report_repository import invalidate_reports_cache

__all__ = ["invalidate_reports_cache"]
