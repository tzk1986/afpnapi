import json
import logging
import random
import time
from collections import Counter
from collections import deque
from datetime import datetime
from threading import Lock
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
) -> None:
    global _METRICS_HANDLER

    root_logger = logging.getLogger()
    root_logger.setLevel(_parse_log_level(level))

    formatter: logging.Formatter
    if str(log_format).strip().lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = StructuredFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
    if stream_handlers:
        for handler in stream_handlers:
            handler.setFormatter(formatter)
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

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
        },
    )


def configure_logging_from_config(service_name: str) -> None:
    try:
        from postman_api_tester import config as cfg
        level = getattr(cfg, "LOG_LEVEL", "INFO")
        log_format = getattr(cfg, "LOG_FORMAT", "structured")
    except Exception:
        level = "INFO"
        log_format = "structured"
    configure_logging(level=level, log_format=log_format, service_name=service_name)


def get_log_sample_rate(default: float = 0.1) -> float:
    try:
        from postman_api_tester import config as cfg
        configured = getattr(cfg, "LOG_SAMPLE_RATE", default)
    except Exception:
        configured = default
    return _parse_sample_rate(configured, default=default)


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
    try:
        from postman_api_tester import config as cfg
        window_seconds = int(getattr(cfg, "LOG_ALERT_ERROR_WINDOW_SECONDS", 300))
        threshold_per_min = float(getattr(cfg, "LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN", 10.0))
    except Exception:
        window_seconds = 300
        threshold_per_min = 10.0
    return {
        "window_seconds": float(max(60, window_seconds)),
        "threshold_per_min": float(max(0.0, threshold_per_min)),
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
