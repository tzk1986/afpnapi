"""Compatibility handler package.

This package mirrors the planned handler layout and re-exports
current service-layer implementations without changing runtime behavior.
"""

"""开发导读：
- 目录定位：handlers 负责"路由编排与边界收口"，services 负责业务实现。
- 迁移策略：优先保持同名 API 稳定，通过薄封装转发降低迁移风险。
- 维护原则：新增能力优先落到对应 handler+service，避免回填到单体入口文件。
"""
