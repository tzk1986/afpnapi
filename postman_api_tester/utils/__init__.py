"""Compatibility utility package.

This package mirrors the planned utility layout and re-exports
current stable implementations.
"""

"""开发导读：
- 目录定位：utils 提供跨服务复用的纯工具函数（无路由语义）。
- 维护原则：同类能力集中维护，避免在 services/handlers 内重复实现。
- 兼容策略：保留桥接模块，逐步向稳定实现文件收口。
"""
