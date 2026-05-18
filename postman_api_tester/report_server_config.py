"""报告服务端配置常量与读取工具。

职责：
- 从 config.py 或环境变量读取配置
- 提供类型安全的配置访问辅助函数
"""

from typing import Any, Dict, Optional
from types import ModuleType

_cfg: Optional[ModuleType]
try:
    from postman_api_tester import config as _cfg
except Exception:
    _cfg = None


def _cfg_int(name: str, default: int) -> int:
    if _cfg is None:
        return int(default)
    try:
        return int(getattr(_cfg, name, default))
    except (TypeError, ValueError):
        return int(default)


def _cfg_bool(name: str, default: bool) -> bool:
    if _cfg is None:
        return bool(default)
    value = getattr(_cfg, name, default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _cfg_str(name: str, default: str) -> str:
    if _cfg is None:
        return str(default)
    value = getattr(_cfg, name, default)
    return str(value).strip() if value is not None else str(default)


def _cfg_dict(name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if default is None:
        default = {}
    if _cfg is None:
        return default
    value = getattr(_cfg, name, default)
    return value if isinstance(value, dict) else default


EnvironmentConfig = Dict[str, str]


def _normalize_environments(raw_environments: object) -> Dict[str, EnvironmentConfig]:
    if not isinstance(raw_environments, dict):
        return {}

    normalized: Dict[str, EnvironmentConfig] = {}
    for env_name, env_value in raw_environments.items():
        if not isinstance(env_value, dict):
            continue
        normalized[str(env_name)] = {
            "base_url": str(env_value.get("base_url", "") or "").strip(),
            "token": str(env_value.get("token", "") or "").strip(),
        }
    return normalized


# 运行时配置常量
RUN_RESULTS_PER_PAGE_DEFAULT = _cfg_int("RUN_RESULTS_PER_PAGE_DEFAULT", 30)
RUN_RESULTS_PER_PAGE_MIN = _cfg_int("RUN_RESULTS_PER_PAGE_MIN", 1)
RUN_RESULTS_PER_PAGE_MAX = _cfg_int("RUN_RESULTS_PER_PAGE_MAX", 100)

REPORT_VIEW_PAGE_SIZE_DEFAULT = _cfg_int("REPORT_VIEW_PAGE_SIZE_DEFAULT", 20)
REPORT_VIEW_PAGE_SIZE_MIN = _cfg_int("REPORT_VIEW_PAGE_SIZE_MIN", 1)
REPORT_VIEW_PAGE_SIZE_MAX = _cfg_int("REPORT_VIEW_PAGE_SIZE_MAX", 100)

RUN_STATUS_POLL_INTERVAL_MS = _cfg_int("RUN_STATUS_POLL_INTERVAL_MS", 3000)
ENABLE_SELECTIVE_RUN = _cfg_bool("ENABLE_SELECTIVE_RUN", True)
COLLECTION_PREVIEW_MAX_ITEMS = _cfg_int("COLLECTION_PREVIEW_MAX_ITEMS", 3000)

REPORT_EXPORT_DEFAULT_SCOPE = _cfg_str("REPORT_EXPORT_DEFAULT_SCOPE", "full").lower() or "full"
if REPORT_EXPORT_DEFAULT_SCOPE not in {"full", "report_only"}:
    REPORT_EXPORT_DEFAULT_SCOPE = "full"
REPORT_EXPORT_ALLOW_REPORT_ONLY = _cfg_bool("REPORT_EXPORT_ALLOW_REPORT_ONLY", True)
REPORT_EXPORT_INCLUDE_AUTH_DEFAULT = _cfg_bool("REPORT_EXPORT_INCLUDE_AUTH_DEFAULT", False)
REPORT_EXPORT_CHANNEL_MODE = _cfg_str("REPORT_EXPORT_CHANNEL_MODE", "auto").lower() or "auto"
if REPORT_EXPORT_CHANNEL_MODE not in {"auto", "legacy", "stream"}:
    REPORT_EXPORT_CHANNEL_MODE = "auto"
REPORT_EXPORT_STREAM_THRESHOLD = max(1, _cfg_int("REPORT_EXPORT_STREAM_THRESHOLD", 800))
ENABLE_MANUAL_CASES = _cfg_bool("ENABLE_MANUAL_CASES", True)
MANUAL_CASE_FOLDER_NAME = _cfg_str("MANUAL_CASE_FOLDER_NAME", "人工补录") or "人工补录"
ENABLE_ADHOC_RUN = _cfg_bool("ENABLE_ADHOC_RUN", True)
ADHOC_MAX_ITEMS = _cfg_int("ADHOC_MAX_ITEMS", 200)
ADHOC_DEFAULT_COLLECTION_NAME = _cfg_str("ADHOC_DEFAULT_COLLECTION_NAME", "报告中心临时测试") or "报告中心临时测试"
ENABLE_RESPONSE_TIME = _cfg_bool("ENABLE_RESPONSE_TIME", True)
ENABLE_RETRY_FAILURES = _cfg_bool("ENABLE_RETRY_FAILURES", True)
ENABLE_JUNIT_EXPORT = _cfg_bool("ENABLE_JUNIT_EXPORT", True)
ENABLE_REPORT_LIST_FILTER = _cfg_bool("ENABLE_REPORT_LIST_FILTER", True)
ENABLE_ASSERTIONS = _cfg_bool("ENABLE_ASSERTIONS", False)
ENABLE_REPORT_ANALYTICS = _cfg_bool("ENABLE_REPORT_ANALYTICS", True)
ENABLE_REPORT_ANALYTICS_CHARTS = _cfg_bool("ENABLE_REPORT_ANALYTICS_CHARTS", True)
REPORT_ANALYTICS_TOP_N_DEFAULT = _cfg_int("REPORT_ANALYTICS_TOP_N_DEFAULT", 10)
REPORT_ANALYTICS_TOP_N_MAX = _cfg_int("REPORT_ANALYTICS_TOP_N_MAX", 100)
REPORT_ANALYTICS_TREND_LIMIT_DEFAULT = _cfg_int("REPORT_ANALYTICS_TREND_LIMIT_DEFAULT", 20)
REPORT_ANALYTICS_TREND_LIMIT_MAX = _cfg_int("REPORT_ANALYTICS_TREND_LIMIT_MAX", 100)
REPORT_ANALYTICS_ENABLE_SAMPLES = _cfg_bool("REPORT_ANALYTICS_ENABLE_SAMPLES", False)
REPORT_ANALYTICS_HISTOGRAM_BUCKETS = _cfg_str("REPORT_ANALYTICS_HISTOGRAM_BUCKETS", "0,50,100,200,500,1000,3000,5000")
QUALITY_SCORE_FAILED_PENALTY = max(0, _cfg_int("QUALITY_SCORE_FAILED_PENALTY", 10))
QUALITY_SCORE_ERROR_PENALTY = max(0, _cfg_int("QUALITY_SCORE_ERROR_PENALTY", 15))
QUALITY_SCORE_SLOW_PENALTY = max(0, _cfg_int("QUALITY_SCORE_SLOW_PENALTY", 5))
QUALITY_SCORE_ASSERTION_MISSING_PENALTY = max(0, _cfg_int("QUALITY_SCORE_ASSERTION_MISSING_PENALTY", 2))

ENVIRONMENTS: Dict[str, EnvironmentConfig] = _normalize_environments(_cfg_dict("ENVIRONMENTS", {}))
DEFAULT_ENV_NAME: str = _cfg_str("DEFAULT_ENV_NAME", "")

JobParams = Dict[str, Any]
SummaryPayload = Dict[str, Any]
