#!/usr/bin/env python
"""
Postman API 测试配置文件

在此处填写测试所需的配置信息。
token 优先级：命令行参数 > 环境变量 POSTMAN_TOKEN > 此文件中的 TOKEN 默认值 > 自动登录获取

开发导读:
- 该文件是运行时集中配置入口，统一管理 token、超时、日志、分页与导出策略。
- 新增配置项时建议补充默认值与环境变量映射，保持命令行与服务端行为一致。
"""

import json as _json_cfg
import os
from typing import Any, Dict

_TRUTHY = frozenset(("1", "true", "yes", "y", "on"))


def _env_bool(key: str, default: str = "false") -> bool:
    return str(os.environ.get(key, default)).strip().lower() in _TRUTHY


def _env_int(key: str, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    """安全读取整数环境变量，非法值回退到 default。"""
    raw = os.environ.get(key)
    if raw is None:
        val = default
    else:
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = default
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


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
REQUEST_CONNECT_TIMEOUT = _env_int("REQUEST_CONNECT_TIMEOUT", 10, lo=1, hi=300)
REQUEST_READ_TIMEOUT = _env_int("REQUEST_READ_TIMEOUT", 30, lo=1, hi=300)

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
RUN_JOBS_MAX = _env_int("RUN_JOBS_MAX", 200, lo=1, hi=100000)

# ==============================================================
# 运行页与结果页分页配置（集中管理）
# ==============================================================
RUN_RESULTS_PER_PAGE_DEFAULT = _env_int("RUN_RESULTS_PER_PAGE_DEFAULT", 30, lo=1, hi=1000)
RUN_RESULTS_PER_PAGE_MIN = _env_int("RUN_RESULTS_PER_PAGE_MIN", 1, lo=1, hi=100)
RUN_RESULTS_PER_PAGE_MAX = _env_int("RUN_RESULTS_PER_PAGE_MAX", 100, lo=1, hi=1000)

REPORT_VIEW_PAGE_SIZE_DEFAULT = _env_int("REPORT_VIEW_PAGE_SIZE_DEFAULT", 20, lo=1, hi=1000)
REPORT_VIEW_PAGE_SIZE_MIN = _env_int("REPORT_VIEW_PAGE_SIZE_MIN", 1, lo=1, hi=100)
REPORT_VIEW_PAGE_SIZE_MAX = _env_int("REPORT_VIEW_PAGE_SIZE_MAX", 100, lo=1, hi=1000)

# ==============================================================
# 上传执行任务轮询配置
# ==============================================================
RUN_STATUS_POLL_INTERVAL_MS = _env_int("RUN_STATUS_POLL_INTERVAL_MS", 3000, lo=100)

# ==============================================================
# 可选接口执行（导入后选择接口再执行）
# ENABLE_SELECTIVE_RUN: 是否启用“仅执行已选接口”能力
# COLLECTION_PREVIEW_MAX_ITEMS: 单次预览最多返回的接口数量（防止超大集合拖慢页面）
# ==============================================================
ENABLE_SELECTIVE_RUN = _env_bool("ENABLE_SELECTIVE_RUN", "true")
COLLECTION_PREVIEW_MAX_ITEMS = _env_int("COLLECTION_PREVIEW_MAX_ITEMS", 3000, lo=1, hi=100000)

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
REPORT_EXPORT_ALLOW_REPORT_ONLY = _env_bool("REPORT_EXPORT_ALLOW_REPORT_ONLY", "true")
REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = _env_bool("REPORT_EXPORT_INCLUDE_AUTH_DEFAULT", "false")
REPORT_EXPORT_CHANNEL_MODE = str(os.environ.get("REPORT_EXPORT_CHANNEL_MODE", "auto")).strip().lower() or "auto"
if REPORT_EXPORT_CHANNEL_MODE not in {"auto", "legacy", "stream"}:
    REPORT_EXPORT_CHANNEL_MODE = "auto"
REPORT_EXPORT_STREAM_THRESHOLD = _env_int("REPORT_EXPORT_STREAM_THRESHOLD", 800, lo=1)

# ==============================================================
# 人工用例管理配置
# ENABLE_MANUAL_CASES: 是否启用报告页人工用例能力
# MANUAL_CASE_FOLDER_NAME: 人工用例默认目录名称（可在页面手动修改）
# ==============================================================
ENABLE_MANUAL_CASES = _env_bool("ENABLE_MANUAL_CASES", "true")
MANUAL_CASE_FOLDER_NAME = str(os.environ.get("MANUAL_CASE_FOLDER_NAME", "人工补录")).strip() or "人工补录"

# ==============================================================
# 报告中心直接新增接口测试（ad-hoc）配置
# ENABLE_ADHOC_RUN: 是否启用“直接新增接口测试并执行”能力
# ADHOC_MAX_ITEMS: 单次 ad-hoc 任务允许的最大接口数量
# ADHOC_DEFAULT_COLLECTION_NAME: ad-hoc 任务默认集合名
# ==============================================================
ENABLE_ADHOC_RUN = _env_bool("ENABLE_ADHOC_RUN", "true")
ADHOC_MAX_ITEMS = _env_int("ADHOC_MAX_ITEMS", 200, lo=1, hi=10000)
ADHOC_DEFAULT_COLLECTION_NAME = str(os.environ.get("ADHOC_DEFAULT_COLLECTION_NAME", "报告中心临时测试")).strip() or "报告中心临时测试"

# ==============================================================
# 升级三：响应时间记录与展示
# ENABLE_RESPONSE_TIME: 是否在执行结果中记录并展示接口响应时间
# ==============================================================
ENABLE_RESPONSE_TIME = _env_bool("ENABLE_RESPONSE_TIME", "true")

# ==============================================================
# 升级二：一键重试全部失败用例
# ENABLE_RETRY_FAILURES: 是否在报告详情页显示"重试失败接口"按钮
# ==============================================================
ENABLE_RETRY_FAILURES = _env_bool("ENABLE_RETRY_FAILURES", "true")

# ==============================================================
# 升级四：多环境配置切换
# ENVIRONMENTS_JSON: JSON 字符串，格式 {"env_name": {"base_url": "...", "token": ""}}
# DEFAULT_ENV_NAME: 默认选中的环境名（为空则不预选）
# ==============================================================
# _ENVIRONMENTS_JSON = os.environ.get("ENVIRONMENTS_JSON", "{}") # 无配置时

_ENVIRONMENTS_JSON = os.environ.get("ENVIRONMENTS_JSON", '''
{
  "生产环境": {"base_url": "http://10.50.11.130:11000", "token": ""},
  "测试环境": {"base_url": "http://10.50.11.120:8090", "token": ""},
  "本地开发": {"base_url": "http://127.0.0.1:8080", "token": ""}
}
''')
try:
    ENVIRONMENTS: Dict[str, Any] = _json_cfg.loads(_ENVIRONMENTS_JSON)
    if not isinstance(ENVIRONMENTS, dict):
        ENVIRONMENTS = {}
except _json_cfg.JSONDecodeError:
    ENVIRONMENTS = {}
DEFAULT_ENV_NAME: str = os.environ.get("DEFAULT_ENV_NAME", "")

# ==============================================================
# 升级五：断言规则增强（JSONPath 校验）
# ENABLE_ASSERTIONS: 是否启用 JSONPath 断言校验（默认 false，需要安装 jsonpath-ng）
# ASSERTIONS_ENGINE: 断言引擎，目前仅支持 'jsonpath'
# ==============================================================
ENABLE_ASSERTIONS = _env_bool("ENABLE_ASSERTIONS", "false")
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
ENABLE_CHECKPOINT_RECOVERY = _env_bool("ENABLE_CHECKPOINT_RECOVERY", "false")
CHECKPOINT_FLUSH_EVERY_N = _env_int("CHECKPOINT_FLUSH_EVERY_N", 1, lo=1)
CHECKPOINT_DIR = str(os.environ.get("CHECKPOINT_DIR", "")).strip()
ENABLE_ASSERTION_STRICT_MODE = _env_bool("ENABLE_ASSERTION_STRICT_MODE", "false")

# ==============================================================
# 升级七：JUnit XML 报告导出
# ENABLE_JUNIT_EXPORT: 是否启用 JUnit XML 导出接口
# ==============================================================
ENABLE_JUNIT_EXPORT = _env_bool("ENABLE_JUNIT_EXPORT", "true")

# ==============================================================
# 升级八：首页历史列表搜索与筛选
# ENABLE_REPORT_LIST_FILTER: 是否在首页显示高级筛选栏
# ==============================================================
ENABLE_REPORT_LIST_FILTER = _env_bool("ENABLE_REPORT_LIST_FILTER", "true")

# ==============================================================
# 2.1 测试结果分析与报告洞察
# ENABLE_REPORT_ANALYTICS: 是否启用 /api/report-analytics 接口
# REPORT_ANALYTICS_TOP_N_DEFAULT/MAX: TopN 参数默认值与上限
# REPORT_ANALYTICS_TREND_LIMIT_DEFAULT/MAX: 趋势报告数量默认值与上限
# REPORT_ANALYTICS_ENABLE_SAMPLES: 是否默认返回错误样本
# REPORT_ANALYTICS_HISTOGRAM_BUCKETS: 逗号分隔响应时间桶边界（ms）
# QUALITY_SCORE_*: 质量评分扣分项阈值
# ==============================================================
ENABLE_REPORT_ANALYTICS = _env_bool("ENABLE_REPORT_ANALYTICS", "true")
REPORT_ANALYTICS_TOP_N_DEFAULT = _env_int("REPORT_ANALYTICS_TOP_N_DEFAULT", 10, lo=1, hi=1000)
REPORT_ANALYTICS_TOP_N_MAX = _env_int("REPORT_ANALYTICS_TOP_N_MAX", 100, lo=1, hi=10000)
REPORT_ANALYTICS_TREND_LIMIT_DEFAULT = _env_int("REPORT_ANALYTICS_TREND_LIMIT_DEFAULT", 20, lo=1, hi=1000)
REPORT_ANALYTICS_TREND_LIMIT_MAX = _env_int("REPORT_ANALYTICS_TREND_LIMIT_MAX", 100, lo=1, hi=10000)
REPORT_ANALYTICS_ENABLE_SAMPLES = _env_bool("REPORT_ANALYTICS_ENABLE_SAMPLES", "false")
ENABLE_REPORT_ANALYTICS_CHARTS = _env_bool("ENABLE_REPORT_ANALYTICS_CHARTS", "true")
REPORT_ANALYTICS_HISTOGRAM_BUCKETS = str(
    os.environ.get("REPORT_ANALYTICS_HISTOGRAM_BUCKETS", "0,50,100,200,500,1000,3000,5000")
).strip()

QUALITY_SCORE_FAILED_PENALTY = _env_int("QUALITY_SCORE_FAILED_PENALTY", 10, lo=0, hi=100)
QUALITY_SCORE_ERROR_PENALTY = _env_int("QUALITY_SCORE_ERROR_PENALTY", 15, lo=0, hi=100)
QUALITY_SCORE_SLOW_PENALTY = _env_int("QUALITY_SCORE_SLOW_PENALTY", 5, lo=0, hi=100)
QUALITY_SCORE_ASSERTION_MISSING_PENALTY = _env_int("QUALITY_SCORE_ASSERTION_MISSING_PENALTY", 2, lo=0, hi=100)

# ==============================================================
# 报告服务端口与主机配置
# REPORT_SERVER_PORT: Flask 服务监听端口
# REPORT_SERVER_HOST: Flask 服务监听地址
# ==============================================================
REPORT_SERVER_PORT = _env_int("REPORT_SERVER_PORT", 5000, lo=1, hi=65535)
REPORT_SERVER_HOST = str(os.environ.get("REPORT_SERVER_HOST", "0.0.0.0")).strip() or "0.0.0.0"

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

# ==============================================================
# SSRF 防护：Proxy 端点域名白名单
# PROXY_ALLOWED_HOSTS: 逗号分隔的允许代理访问的域名列表。
#   - 空列表（默认）：不做域名限制（保持兼容，仅校验 http/https 协议）
#   - 非空列表：仅允许列表中的域名，其余请求拒绝（403）
# 示例：PROXY_ALLOWED_HOSTS = "api.example.com,10.50.11.130"
# ==============================================================
_PROXY_ALLOWED_HOSTS_TEXT = str(os.environ.get("PROXY_ALLOWED_HOSTS", "")).strip()
PROXY_ALLOWED_HOSTS: tuple = tuple(
    item.strip().lower()
    for item in _PROXY_ALLOWED_HOSTS_TEXT.split(",")
    if item.strip()
) if _PROXY_ALLOWED_HOSTS_TEXT else ()

# ==============================================================
# 可配置结果自动判定条件（errCode & message）
# ENABLE_ERR_CODE_JUDGMENT: 是否启用 errCode 参与结果判定
#   False（默认）= 保持当前行为，不检查 errCode
#   True = errCode 必须匹配 SUCCESS_ERR_CODES 中任一值才判定为成功
# SUCCESS_ERR_CODES: 视为成功的 errCode 值列表（逗号分隔，匹配时忽略大小写）
#   默认值: "0"
# ENABLE_MESSAGE_JUDGMENT: 是否启用 message 参与结果判定
#   True（默认）= 保持当前行为，message 为空或匹配 SUCCESS_MESSAGES 时通过
#   False = 不检查 message
# SUCCESS_MESSAGES: 视为成功的 message 值列表（逗号分隔，匹配时忽略大小写）
#   默认值: "success"（保持当前行为：空字符串或 success 视为成功）
# 支持 Web 界面运行时覆盖和集合内 x_* 字段接口级覆盖。
# ==============================================================
ENABLE_ERR_CODE_JUDGMENT = _env_bool("ENABLE_ERR_CODE_JUDGMENT", "false")
SUCCESS_ERR_CODES = str(os.environ.get("SUCCESS_ERR_CODES", "0")).strip()
ENABLE_MESSAGE_JUDGMENT = _env_bool("ENABLE_MESSAGE_JUDGMENT", "true")
SUCCESS_MESSAGES = str(os.environ.get("SUCCESS_MESSAGES", "success")).strip()

# ==============================================================
# P0 功能开关：数据驱动测试 + 请求串联与变量提取
# ==============================================================

# ENABLE_DATA_DRIVEN: 是否启用数据驱动测试（CSV/JSON 数据文件展开接口）
ENABLE_DATA_DRIVEN = _env_bool("ENABLE_DATA_DRIVEN", "true")

# ENABLE_VARIABLE_EXTRACTION: 是否启用请求串联与变量提取（x_extract 配置解析）
ENABLE_VARIABLE_EXTRACTION = _env_bool("ENABLE_VARIABLE_EXTRACTION", "true")

# DATA_FILE_MAX_ROWS: 数据文件最大行数限制
DATA_FILE_MAX_ROWS = _env_int("DATA_FILE_MAX_ROWS", 10000, lo=1, hi=1000000)

# DATA_FILE_MAX_SIZE: 数据文件最大字节数（默认 10MB）
DATA_FILE_MAX_SIZE = _env_int("DATA_FILE_MAX_SIZE", 10 * 1024 * 1024, lo=1024, hi=100 * 1024 * 1024)

# ==============================================================
# P0 功能开关：并发执行引擎
# ENABLE_CONCURRENT: 是否启用并发执行（默认 false，保持串行行为）
# CONCURRENT_WORKERS: 并发执行最大线程数（默认 10）
# 启用后，无变量依赖的接口将并行执行，显著缩短大批量测试耗时。
# 依赖变量提取链的接口自动按拓扑序分批，保证正确性。
# ==============================================================
ENABLE_CONCURRENT = _env_bool("ENABLE_CONCURRENT", "false")
CONCURRENT_WORKERS = _env_int("CONCURRENT_WORKERS", 10, lo=1, hi=100)

# ==============================================================
# P0 功能开关：变量函数与持久化
# ENABLE_VARIABLE_FUNCTIONS: 是否启用内置变量函数（{{timestamp()}} 等）
# GLOBAL_VARIABLES_FILE: 全局变量持久化文件路径（空则不启用持久化）
# GLOBAL_VARIABLES_MAX_COUNT: 全局变量最大数量（默认 1000）
# ==============================================================
ENABLE_VARIABLE_FUNCTIONS = _env_bool("ENABLE_VARIABLE_FUNCTIONS", "true")
GLOBAL_VARIABLES_FILE = os.environ.get("GLOBAL_VARIABLES_FILE", "variables.json")
GLOBAL_VARIABLES_MAX_COUNT = _env_int("GLOBAL_VARIABLES_MAX_COUNT", 1000, lo=1, hi=100000)
ENABLE_PRE_REQUEST_SCRIPT = _env_bool("ENABLE_PRE_REQUEST_SCRIPT", "false")

# ==============================================================
# UI 测试执行配置
# ==============================================================

# UI_EXECUTION_RESULTS_DIR: 执行结果存储目录（默认 ui_testing_cases）
UI_EXECUTION_RESULTS_DIR = str(os.environ.get("UI_EXECUTION_RESULTS_DIR", "")).strip()

# UI_EXECUTION_DEFAULT_DELAY_MS: 步骤间默认间隔（毫秒）
UI_EXECUTION_DEFAULT_DELAY_MS = _env_int("UI_EXECUTION_DEFAULT_DELAY_MS", 500, lo=100, hi=10000)

# UI_EXECUTION_DEFAULT_TIMEOUT_MS: 单步默认超时（毫秒）
UI_EXECUTION_DEFAULT_TIMEOUT_MS = _env_int("UI_EXECUTION_DEFAULT_TIMEOUT_MS", 5000, lo=1000, hi=300000)

# UI_EXECUTION_MAX_CONCURRENT: 同时执行的最大任务数（防止资源耗尽）
UI_EXECUTION_MAX_CONCURRENT = _env_int("UI_EXECUTION_MAX_CONCURRENT", 5, lo=1, hi=50)

# UI_EXECUTION_RETENTION_DAYS: 执行结果保留天数（过期自动清理）
UI_EXECUTION_RETENTION_DAYS = _env_int("UI_EXECUTION_RETENTION_DAYS", 30, lo=1, hi=365)

# UI_HEADLESS_ENABLED: 是否启用无头浏览器执行模式（需安装 playwright）
UI_HEADLESS_ENABLED = _env_bool("UI_HEADLESS_ENABLED", "false")

# UI_HEADLESS_BROWSER: 无头浏览器类型（chromium / firefox / webkit）
UI_HEADLESS_BROWSER = str(os.environ.get("UI_HEADLESS_BROWSER", "chromium")).strip().lower()

# UI_HEADLESS_TIMEOUT_S: 无头执行全局超时（秒）
UI_HEADLESS_TIMEOUT_S = _env_int("UI_HEADLESS_TIMEOUT_S", 300, lo=30, hi=3600)
