#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Postman API 测试配置文件

在此处填写测试所需的配置信息。
token 优先级：命令行参数 > 环境变量 POSTMAN_TOKEN > 此文件中的 TOKEN 默认值 > 自动登录获取

开发导读:
- 该文件是运行时集中配置入口，统一管理 token、超时、日志、分页与导出策略。
- 新增配置项时建议补充默认值与环境变量映射，保持命令行与服务端行为一致。
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
# 日志系统配置
# LOG_LEVEL: 日志级别（DEBUG/INFO/WARNING/ERROR）
# LOG_FORMAT: 日志格式（structured/json）
# LOG_SAMPLE_RATE: 高频日志采样率（0.0 ~ 1.0，默认 10%）
# LOG_ALERT_ERROR_WINDOW_SECONDS: ERROR 速率统计窗口（秒）
# LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN: ERROR 告警阈值（每分钟）
# ==============================================================
LOG_LEVEL = str(os.environ.get("LOG_LEVEL", "INFO")).strip().upper() or "INFO"
LOG_FORMAT = str(os.environ.get("LOG_FORMAT", "structured")).strip().lower() or "structured"
if LOG_FORMAT not in {"structured", "json"}:
    LOG_FORMAT = "structured"
try:
    LOG_SAMPLE_RATE = float(os.environ.get("LOG_SAMPLE_RATE", "0.1"))
except (TypeError, ValueError):
    LOG_SAMPLE_RATE = 0.1
LOG_SAMPLE_RATE = min(max(LOG_SAMPLE_RATE, 0.0), 1.0)
LOG_ALERT_ERROR_WINDOW_SECONDS = max(60, int(os.environ.get("LOG_ALERT_ERROR_WINDOW_SECONDS", "300")))
try:
    LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN = float(os.environ.get("LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN", "10"))
except (TypeError, ValueError):
    LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN = 10.0
LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN = max(0.0, LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN)

# ==============================================================
# 任务历史记录上限
# 超出上限时最早的任务记录会被淘汰（已在 report_server.py 中实现）
# ==============================================================
RUN_JOBS_MAX = int(os.environ.get("RUN_JOBS_MAX", "200"))

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
# REPORT_EXPORT_CHANNEL_MODE: 导出通道模式（auto | legacy | stream）
# REPORT_EXPORT_STREAM_THRESHOLD: 导出自动分流阈值（按报告总接口数判断，>= 阈值走流式导出）
# 示例（保持当前推荐默认）：
# REPORT_EXPORT_DEFAULT_SCOPE = "full"
# REPORT_EXPORT_ALLOW_REPORT_ONLY = True
# REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = False
# REPORT_EXPORT_CHANNEL_MODE = "auto"
# REPORT_EXPORT_STREAM_THRESHOLD = 800
# 示例（仅用于排障临时策略）：
# REPORT_EXPORT_DEFAULT_SCOPE = "report_only"
# REPORT_EXPORT_ALLOW_REPORT_ONLY = True
# REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = True
# REPORT_EXPORT_CHANNEL_MODE = "stream"
# REPORT_EXPORT_STREAM_THRESHOLD = 300
# ============================================================== 
REPORT_EXPORT_DEFAULT_SCOPE = str(os.environ.get("REPORT_EXPORT_DEFAULT_SCOPE", "full")).strip().lower() or "full"
REPORT_EXPORT_ALLOW_REPORT_ONLY = str(os.environ.get("REPORT_EXPORT_ALLOW_REPORT_ONLY", "true")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = str(os.environ.get("REPORT_EXPORT_INCLUDE_AUTH_DEFAULT", "false")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
REPORT_EXPORT_CHANNEL_MODE = str(os.environ.get("REPORT_EXPORT_CHANNEL_MODE", "auto")).strip().lower() or "auto"
if REPORT_EXPORT_CHANNEL_MODE not in {"auto", "legacy", "stream"}:
    REPORT_EXPORT_CHANNEL_MODE = "auto"
REPORT_EXPORT_STREAM_THRESHOLD = max(1, int(os.environ.get("REPORT_EXPORT_STREAM_THRESHOLD", "800")))

# ==============================================================
# 人工用例管理配置
# ENABLE_MANUAL_CASES: 是否启用报告页人工用例能力
# MANUAL_CASE_FOLDER_NAME: 人工用例默认目录名称（可在页面手动修改）
# ==============================================================
ENABLE_MANUAL_CASES = str(os.environ.get("ENABLE_MANUAL_CASES", "true")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
MANUAL_CASE_FOLDER_NAME = str(os.environ.get("MANUAL_CASE_FOLDER_NAME", "人工补录")).strip() or "人工补录"

# ==============================================================
# 报告中心直接新增接口测试（ad-hoc）配置
# ENABLE_ADHOC_RUN: 是否启用“直接新增接口测试并执行”能力
# ADHOC_MAX_ITEMS: 单次 ad-hoc 任务允许的最大接口数量
# ADHOC_DEFAULT_COLLECTION_NAME: ad-hoc 任务默认集合名
# ============================================================== 
ENABLE_ADHOC_RUN = str(os.environ.get("ENABLE_ADHOC_RUN", "true")).strip().lower() in {
	"1", "true", "yes", "y", "on"
}
ADHOC_MAX_ITEMS = int(os.environ.get("ADHOC_MAX_ITEMS", "200"))
ADHOC_DEFAULT_COLLECTION_NAME = str(os.environ.get("ADHOC_DEFAULT_COLLECTION_NAME", "报告中心临时测试")).strip() or "报告中心临时测试"

# ==============================================================
# 升级三：响应时间记录与展示
# ENABLE_RESPONSE_TIME: 是否在执行结果中记录并展示接口响应时间
# ==============================================================
ENABLE_RESPONSE_TIME = str(os.environ.get("ENABLE_RESPONSE_TIME", "true")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}

# ==============================================================
# 升级二：一键重试全部失败用例
# ENABLE_RETRY_FAILURES: 是否在报告详情页显示"重试失败接口"按钮
# ==============================================================
ENABLE_RETRY_FAILURES = str(os.environ.get("ENABLE_RETRY_FAILURES", "true")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}

# ==============================================================
# 升级四：多环境配置切换
# ENVIRONMENTS_JSON: JSON 字符串，格式 {"env_name": {"base_url": "...", "token": ""}}
# DEFAULT_ENV_NAME: 默认选中的环境名（为空则不预选）
# ==============================================================
import json as _json_cfg
# _ENVIRONMENTS_JSON = os.environ.get("ENVIRONMENTS_JSON", "{}") # 无配置时

_ENVIRONMENTS_JSON = os.environ.get("ENVIRONMENTS_JSON", '''
{
  "生产环境": {"base_url": "http://10.50.11.130:11000", "token": ""},
  "测试环境": {"base_url": "http://10.50.11.120:8090", "token": ""},
  "本地开发": {"base_url": "http://127.0.0.1:8080", "token": ""}
}
''')
try:
    ENVIRONMENTS: dict = _json_cfg.loads(_ENVIRONMENTS_JSON)
    if not isinstance(ENVIRONMENTS, dict):
        ENVIRONMENTS = {}
except Exception:
    ENVIRONMENTS = {}
DEFAULT_ENV_NAME: str = os.environ.get("DEFAULT_ENV_NAME", "")

# ==============================================================
# 升级五：断言规则增强（JSONPath 校验）
# ENABLE_ASSERTIONS: 是否启用 JSONPath 断言校验（默认 false，需要安装 jsonpath-ng）
# ASSERTIONS_ENGINE: 断言引擎，目前仅支持 'jsonpath'
# ==============================================================
ENABLE_ASSERTIONS = str(os.environ.get("ENABLE_ASSERTIONS", "false")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}
ASSERTIONS_ENGINE = str(os.environ.get("ASSERTIONS_ENGINE", "jsonpath")).strip() or "jsonpath"

# ==============================================================
# 1.1 错误恢复与容错
# ENABLE_CHECKPOINT_RECOVERY: 是否启用断点恢复（默认 false，保持 v1.2.0 行为）
# CHECKPOINT_FLUSH_EVERY_N: 每执行多少条接口写一次 checkpoint（最小 1）
# CHECKPOINT_DIR: checkpoint 文件目录（为空则默认 reports/checkpoints）
# ENABLE_ASSERTION_STRICT_MODE: 断言引擎异常是否按 FAILED 处理
# 示例（保持兼容模式）：
# ENABLE_CHECKPOINT_RECOVERY = False
# CHECKPOINT_FLUSH_EVERY_N = 1
# CHECKPOINT_DIR = ""
# ENABLE_ASSERTION_STRICT_MODE = False
# 示例（大集合长跑任务推荐）：
# ENABLE_CHECKPOINT_RECOVERY = True
# CHECKPOINT_FLUSH_EVERY_N = 5
# CHECKPOINT_DIR = r"D:\\api-test-reports\\checkpoints"
# ENABLE_ASSERTION_STRICT_MODE = True
# ============================================================== 
ENABLE_CHECKPOINT_RECOVERY = str(os.environ.get("ENABLE_CHECKPOINT_RECOVERY", "false")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}
CHECKPOINT_FLUSH_EVERY_N = max(1, int(os.environ.get("CHECKPOINT_FLUSH_EVERY_N", "1")))
CHECKPOINT_DIR = str(os.environ.get("CHECKPOINT_DIR", "")).strip()
ENABLE_ASSERTION_STRICT_MODE = str(os.environ.get("ENABLE_ASSERTION_STRICT_MODE", "false")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}

# ==============================================================
# 升级七：JUnit XML 报告导出
# ENABLE_JUNIT_EXPORT: 是否启用 JUnit XML 导出接口
# ==============================================================
ENABLE_JUNIT_EXPORT = str(os.environ.get("ENABLE_JUNIT_EXPORT", "true")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}

# ==============================================================
# 升级八：首页历史列表搜索与筛选
# ENABLE_REPORT_LIST_FILTER: 是否在首页显示高级筛选栏
# ==============================================================
ENABLE_REPORT_LIST_FILTER = str(os.environ.get("ENABLE_REPORT_LIST_FILTER", "true")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}

# ==============================================================
# 2.1 测试结果分析与报告洞察
# ENABLE_REPORT_ANALYTICS: 是否启用 /api/report-analytics 接口
# REPORT_ANALYTICS_TOP_N_DEFAULT/MAX: TopN 参数默认值与上限
# REPORT_ANALYTICS_TREND_LIMIT_DEFAULT/MAX: 趋势报告数量默认值与上限
# REPORT_ANALYTICS_ENABLE_SAMPLES: 是否默认返回错误样本
# REPORT_ANALYTICS_HISTOGRAM_BUCKETS: 逗号分隔响应时间桶边界（ms）
# QUALITY_SCORE_*: 质量评分扣分项阈值
# ==============================================================
ENABLE_REPORT_ANALYTICS = str(os.environ.get("ENABLE_REPORT_ANALYTICS", "true")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}
REPORT_ANALYTICS_TOP_N_DEFAULT = int(os.environ.get("REPORT_ANALYTICS_TOP_N_DEFAULT", "10"))
REPORT_ANALYTICS_TOP_N_MAX = int(os.environ.get("REPORT_ANALYTICS_TOP_N_MAX", "100"))
REPORT_ANALYTICS_TREND_LIMIT_DEFAULT = int(os.environ.get("REPORT_ANALYTICS_TREND_LIMIT_DEFAULT", "20"))
REPORT_ANALYTICS_TREND_LIMIT_MAX = int(os.environ.get("REPORT_ANALYTICS_TREND_LIMIT_MAX", "100"))
REPORT_ANALYTICS_ENABLE_SAMPLES = str(os.environ.get("REPORT_ANALYTICS_ENABLE_SAMPLES", "false")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}
REPORT_ANALYTICS_HISTOGRAM_BUCKETS = str(
    os.environ.get("REPORT_ANALYTICS_HISTOGRAM_BUCKETS", "0,50,100,200,500,1000,3000,5000")
).strip()

QUALITY_SCORE_FAILED_PENALTY = int(os.environ.get("QUALITY_SCORE_FAILED_PENALTY", "10"))
QUALITY_SCORE_ERROR_PENALTY = int(os.environ.get("QUALITY_SCORE_ERROR_PENALTY", "15"))
QUALITY_SCORE_SLOW_PENALTY = int(os.environ.get("QUALITY_SCORE_SLOW_PENALTY", "5"))
QUALITY_SCORE_ASSERTION_MISSING_PENALTY = int(os.environ.get("QUALITY_SCORE_ASSERTION_MISSING_PENALTY", "2"))

# ==============================================================
# 安全脱敏配置（请求头）
# SENSITIVE_HEADERS: 逗号分隔的敏感头列表（可扩展）
# 说明：运行时会与内置默认值合并，避免误删关键脱敏项。
# ==============================================================
_DEFAULT_SENSITIVE_HEADERS = (
    "authorization",
    "token",
    "access_token",
    "auth_token",
    "x-token",
    "x-access-token",
    "access-token",
    "cookie",
    "set-cookie",
    "session",
    "x-csrf-token",
    "api-key",
    "apikey",
    "secret",
)
_SENSITIVE_HEADERS_TEXT = str(os.environ.get("SENSITIVE_HEADERS", "")).strip()
if _SENSITIVE_HEADERS_TEXT:
    SENSITIVE_HEADERS = tuple(
        item.strip().lower()
        for item in _SENSITIVE_HEADERS_TEXT.split(",")
        if item.strip()
    )
else:
    SENSITIVE_HEADERS = _DEFAULT_SENSITIVE_HEADERS
