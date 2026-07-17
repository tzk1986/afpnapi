"""开发导读：
- 职责：结构化日志封装、采样日志与告警窗口统计。
- 入口：log_structured()/log_sampled()/check_error_rate_alert() 等。
- 目标：统一事件字段与健康检查可观测数据来源。
"""

import json
import logging
import random
import time
from collections import Counter
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
import threading
from typing import Any, Deque, Dict, Mapping, Optional

_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys())


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [ _safe_value(item) for item in value ]
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    return str(value)


def _extra_fields(record: logging.LogRecord) -> Dict[str, Any]:
    extras: Dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
            continue
        extras[key] = _safe_value(value)
    return extras


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = _extra_fields(record)
        if not extras:
            return base
        kv_pairs = " ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in sorted(extras.items()))
        return f"{base} | {kv_pairs}"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_extra_fields(record))
        return json.dumps(payload, ensure_ascii=False)


class LogMetricsHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self._lock = Lock()
        self._total = 0
        self._by_level: Counter[str] = Counter()
        self._by_logger: Counter[str] = Counter()
        self._by_event: Counter[str] = Counter()
        self._error_timestamps: Deque[float] = deque()

    def emit(self, record: logging.LogRecord) -> None:
        event = getattr(record, "event", "")
        now_ts = time.time()
        with self._lock:
            self._total += 1
            self._by_level[record.levelname] += 1
            self._by_logger[record.name] += 1
            if isinstance(event, str) and event:
                self._by_event[event] += 1
            if record.levelno >= logging.ERROR:
                self._error_timestamps.append(now_ts)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total": self._total,
                "by_level": dict(self._by_level),
                "by_logger": dict(self._by_logger),
                "by_event": dict(self._by_event),
            }

    def error_count_since(self, window_seconds: int) -> int:
        now_ts = time.time()
        lower_bound = now_ts - float(max(1, window_seconds))
        with self._lock:
            while self._error_timestamps and self._error_timestamps[0] < lower_bound:
                self._error_timestamps.popleft()
            return len(self._error_timestamps)


_METRICS_HANDLER: Optional[LogMetricsHandler] = None


def _parse_log_level(level_text: Any, default: int = logging.INFO) -> int:
    if isinstance(level_text, int):
        return level_text
    level_name = str(level_text or "").strip().upper()
    return getattr(logging, level_name, default)


def _parse_sample_rate(raw_value: Any, default: float = 0.1) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(value, 0.0), 1.0)


def configure_logging(
    *,
    level: Any = "INFO",
    log_format: str = "structured",
    service_name: str = "postman_api_tester",
    log_file: str = "",
    log_file_max_bytes: int = 10 * 1024 * 1024,
    log_file_backup_count: int = 5,
) -> None:
    global _METRICS_HANDLER

    root_logger = logging.getLogger()
    root_logger.setLevel(_parse_log_level(level))

    formatter: logging.Formatter
    if str(log_format).strip().lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = StructuredFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    if stream_handlers:
        for handler in stream_handlers:
            handler.setFormatter(formatter)
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    if log_file:
        log_path = Path(log_file).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        has_file_handler = any(
            isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_path)
            for h in root_logger.handlers
        )
        if not has_file_handler:
            file_handler = RotatingFileHandler(
                str(log_path),
                maxBytes=log_file_max_bytes,
                backupCount=log_file_backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

    if _METRICS_HANDLER is None:
        _METRICS_HANDLER = LogMetricsHandler()
        root_logger.addHandler(_METRICS_HANDLER)

    logging.getLogger(__name__).info(
        "logging_configured",
        extra={
            "event": "logging.configure.applied",
            "service": service_name,
            "log_level": logging.getLevelName(root_logger.level),
            "log_format": str(log_format).strip().lower() or "structured",
            "log_file": log_file or "",
        },
    )


def configure_logging_from_config(service_name: str) -> None:
    from postman_api_tester.report_server_config import (
        LOG_LEVEL,
        LOG_FORMAT,
        LOG_FILE,
        LOG_FILE_MAX_BYTES,
        LOG_FILE_BACKUP_COUNT,
    )
    configure_logging(
        level=LOG_LEVEL,
        log_format=LOG_FORMAT,
        service_name=service_name,
        log_file=LOG_FILE,
        log_file_max_bytes=LOG_FILE_MAX_BYTES,
        log_file_backup_count=LOG_FILE_BACKUP_COUNT,
    )
    # 启动日志清理线程（仅当配置了日志文件时）
    if LOG_FILE:
        log_dir = str(Path(LOG_FILE).expanduser().resolve().parent)
        _start_log_cleanup(log_dir)


def get_log_sample_rate(default: float = 0.1) -> float:
    from postman_api_tester.report_server_config import LOG_SAMPLE_RATE
    return _parse_sample_rate(LOG_SAMPLE_RATE, default=default)


def log_sampled(
    logger: logging.Logger,
    level: int,
    message: str,
    *args: object,
    sample_rate: float = 0.1,
    extra: Optional[Mapping[str, object]] = None,
) -> None:
    if sample_rate >= 1.0 or random.random() <= sample_rate:
        logger.log(level, message, *args, extra=dict(extra or {}))


def get_log_metrics_snapshot() -> Dict[str, Any]:
    if _METRICS_HANDLER is None:
        return {
            "total": 0,
            "by_level": {},
            "by_logger": {},
            "by_event": {},
        }
    return _METRICS_HANDLER.snapshot()


def _get_alert_config() -> Dict[str, float]:
    from postman_api_tester.report_server_config import (
        LOG_ALERT_ERROR_WINDOW_SECONDS,
        LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN,
    )
    return {
        "window_seconds": float(LOG_ALERT_ERROR_WINDOW_SECONDS),
        "threshold_per_min": float(LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN),
    }


def get_log_alert_snapshot() -> Dict[str, Any]:
    cfg = _get_alert_config()
    window_seconds = int(cfg["window_seconds"])
    threshold_per_min = float(cfg["threshold_per_min"])

    if _METRICS_HANDLER is None:
        return {
            "status": "ok",
            "alert_triggered": False,
            "metric": "error_rate_per_min",
            "window_seconds": window_seconds,
            "threshold": threshold_per_min,
            "current": 0.0,
            "error_count": 0,
        }

    error_count = _METRICS_HANDLER.error_count_since(window_seconds)
    current_rate_per_min = round((error_count * 60.0) / float(window_seconds), 3)
    alert_triggered = current_rate_per_min >= threshold_per_min
    return {
        "status": "warning" if alert_triggered else "ok",
        "alert_triggered": alert_triggered,
        "metric": "error_rate_per_min",
        "window_seconds": window_seconds,
        "threshold": threshold_per_min,
        "current": current_rate_per_min,
        "error_count": error_count,
    }


# ── 日志清理 ──

_LOG_CLEANUP_INTERVAL = 86400  # 每天检查一次
_LOG_RETENTION_DAYS = 10


def cleanup_old_logs(log_dir: str, retention_days: int = _LOG_RETENTION_DAYS) -> int:
    """清理指定目录下超过保留期的日志文件。

    Args:
        log_dir: 日志文件目录
        retention_days: 保留天数，默认 7 天

    Returns:
        删除的文件数量
    """

    cutoff = time.time() - retention_days * 86400
    removed = 0
    log_path = Path(log_dir)
    if not log_path.is_dir():
        return 0

    for pattern in ("*.log", "*.log.*"):
        for filepath in log_path.glob(pattern):
            try:
                if filepath.stat().st_mtime < cutoff:
                    filepath.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def _start_log_cleanup(log_dir: str) -> None:
    """启动后台日志清理线程。"""
    def _cleanup_loop() -> None:
        while True:
            time.sleep(_LOG_CLEANUP_INTERVAL)
            try:
                removed = cleanup_old_logs(log_dir)
                if removed:
                    logging.getLogger(__name__).info(
                        "log_cleanup",
                        extra={
                            "event": "log.cleanup",
                            "removed_count": removed,
                            "log_dir": log_dir,
                        },
                    )
            except Exception:
                pass

    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()
