#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Postman API 测试配置文件

在此处填写测试所需的配置信息。
token 优先级：命令行参数 > 环境变量 POSTMAN_TOKEN > 此文件中的 TOKEN 默认值 > 自动登录获取
"""

import os

# ==============================================================
# 认证 Token 配置
# 优先读取环境变量 POSTMAN_TOKEN；未设置时使用下方默认值。
# 建议生产环境通过 set POSTMAN_TOKEN=xxx 设置，不要将真实 token 提交到代码库。
# 设为空字符串 "" 则使用自动登录获取 token（可能因账号问题失败）。
# ==============================================================
TOKEN = os.environ.get("POSTMAN_TOKEN", "")

# ==============================================================
# 测试目标地址
# 优先读取环境变量 POSTMAN_BASE_URL；未设置时使用下方默认值。
# 示例: BASE_URL = "http://10.50.11.120:8090"
# ==============================================================
BASE_URL = os.environ.get("POSTMAN_BASE_URL", "http://10.50.11.130:11000")

# ==============================================================
# 报告输出目录配置（可选）
# 为空字符串时，默认输出到项目根目录下的 reports 文件夹。
# 可配置绝对路径，例如：r"D:\\api-test-reports"
# ============================================================== 
REPORT_OUTPUT_DIR = ""

# ==============================================================
# 请求超时配置（秒）
# REQUEST_CONNECT_TIMEOUT: 与服务器建立连接的最长等待时间
# REQUEST_READ_TIMEOUT:    等待服务器响应数据的最长时间
# ==============================================================
REQUEST_CONNECT_TIMEOUT = int(os.environ.get("REQUEST_CONNECT_TIMEOUT", "10"))
REQUEST_READ_TIMEOUT = int(os.environ.get("REQUEST_READ_TIMEOUT", "30"))

# ==============================================================
# 任务历史记录上限
# 超出上限时最早的任务记录会被淘汰（已在 report_server.py 中实现）
# ==============================================================
RUN_JOBS_MAX = int(os.environ.get("RUN_JOBS_MAX", "200"))

# ==============================================================
# 报告服务模板渲染模式
# 可选值："inline" 或 "external"
# - inline: 使用内嵌模板（更稳妥）
# - external: 优先使用 templates/*.html，失败自动降级 inline
# ==============================================================
REPORT_TEMPLATE_MODE = str(os.environ.get("REPORT_TEMPLATE_MODE", "external")).strip().lower() or "inline"

# ==============================================================
# 运行页与结果页分页配置（集中管理）
# ============================================================== 
RUN_RESULTS_PER_PAGE_DEFAULT = int(os.environ.get("RUN_RESULTS_PER_PAGE_DEFAULT", "30"))
RUN_RESULTS_PER_PAGE_MIN = int(os.environ.get("RUN_RESULTS_PER_PAGE_MIN", "1"))
RUN_RESULTS_PER_PAGE_MAX = int(os.environ.get("RUN_RESULTS_PER_PAGE_MAX", "100"))

REPORT_VIEW_PAGE_SIZE_DEFAULT = int(os.environ.get("REPORT_VIEW_PAGE_SIZE_DEFAULT", "20"))
REPORT_VIEW_PAGE_SIZE_MIN = int(os.environ.get("REPORT_VIEW_PAGE_SIZE_MIN", "1"))
REPORT_VIEW_PAGE_SIZE_MAX = int(os.environ.get("REPORT_VIEW_PAGE_SIZE_MAX", "100"))

# ==============================================================
# 上传执行任务轮询配置
# ============================================================== 
RUN_STATUS_POLL_INTERVAL_MS = int(os.environ.get("RUN_STATUS_POLL_INTERVAL_MS", "3000"))

# ==============================================================
# 可选接口执行（导入后选择接口再执行）
# ENABLE_SELECTIVE_RUN: 是否启用“仅执行已选接口”能力
# COLLECTION_PREVIEW_MAX_ITEMS: 单次预览最多返回的接口数量（防止超大集合拖慢页面）
# ============================================================== 
ENABLE_SELECTIVE_RUN = str(os.environ.get("ENABLE_SELECTIVE_RUN", "true")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
COLLECTION_PREVIEW_MAX_ITEMS = int(os.environ.get("COLLECTION_PREVIEW_MAX_ITEMS", "3000"))

# ==============================================================
# 报告导出范围配置
# REPORT_EXPORT_DEFAULT_SCOPE: full | report_only
# REPORT_EXPORT_ALLOW_REPORT_ONLY: 是否允许“仅导出本次报告接口”
# REPORT_EXPORT_INCLUDE_AUTH_DEFAULT: 导出时是否默认包含认证头
# ============================================================== 
REPORT_EXPORT_DEFAULT_SCOPE = str(os.environ.get("REPORT_EXPORT_DEFAULT_SCOPE", "full")).strip().lower() or "full"
REPORT_EXPORT_ALLOW_REPORT_ONLY = str(os.environ.get("REPORT_EXPORT_ALLOW_REPORT_ONLY", "true")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = str(os.environ.get("REPORT_EXPORT_INCLUDE_AUTH_DEFAULT", "false")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
