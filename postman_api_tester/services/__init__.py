"""Service layer modules."""

"""开发导读：
- 目录定位：services 负责稳定业务实现，供 handlers 路由层调用。
- 设计目标：集中规则、减少重复逻辑、保持对外函数签名稳定。
- 维护原则：跨路由复用逻辑优先沉到 services，避免回填到 handler。
"""
