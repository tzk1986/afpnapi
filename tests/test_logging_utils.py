"""logging_utils 单元测试。

覆盖 _safe_value、_extra_fields、StructuredFormatter、JsonFormatter、
_parse_log_level、_parse_sample_rate、LogMetricsHandler。
"""

import json
import logging
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import pytest

from postman_api_tester.utils.logging_utils import (
	JsonFormatter,
	LogMetricsHandler,
	StructuredFormatter,
	configure_logging,
	_extra_fields,
	_parse_log_level,
	_parse_sample_rate,
	_safe_value,
)


class TestSafeValue:
	"""_safe_value() 类型安全转换测试。"""

	def test_primitives_pass_through(self) -> None:
		assert _safe_value("hello") == "hello"
		assert _safe_value(42) == 42
		assert _safe_value(3.14) == 3.14
		assert _safe_value(True) is True
		assert _safe_value(None) is None

	def test_list_converted(self) -> None:
		assert _safe_value([1, "a", None]) == [1, "a", None]

	def test_tuple_converted_to_list(self) -> None:
		assert _safe_value((1, 2)) == [1, 2]

	def test_set_converted_to_list(self) -> None:
		result = _safe_value({1})
		assert result == [1]

	def test_dict_keys_stringified(self) -> None:
		result = _safe_value({1: "a", 2: "b"})
		assert result == {"1": "a", "2": "b"}

	def test_nested_structures(self) -> None:
		result = _safe_value({"key": [1, {"nested": True}]})
		assert result == {"key": [1, {"nested": True}]}

	def test_unknown_type_converted_to_string(self) -> None:
		result = _safe_value(object())
		assert isinstance(result, str)


class TestExtraFields:
	"""_extra_fields() 日志记录额外字段提取测试。"""

	def test_no_extra_fields(self) -> None:
		record = logging.makeLogRecord({"msg": "test", "levelname": "INFO"})
		assert _extra_fields(record) == {}

	def test_custom_fields_extracted(self) -> None:
		record = logging.makeLogRecord({
			"msg": "test",
			"levelname": "INFO",
			"event": "handler.request",
			"status_code": 200,
		})
		extras = _extra_fields(record)
		assert extras["event"] == "handler.request"
		assert extras["status_code"] == 200

	def test_private_fields_excluded(self) -> None:
		record = logging.makeLogRecord({
			"msg": "test",
			"_internal": "hidden",
			"visible": "shown",
		})
		extras = _extra_fields(record)
		assert "_internal" not in extras
		assert extras["visible"] == "shown"


class TestStructuredFormatter:
	"""StructuredFormatter 格式化测试。"""

	def test_basic_format(self) -> None:
		formatter = StructuredFormatter("%(message)s")
		record = logging.makeLogRecord({"msg": "hello", "levelname": "INFO", "levelno": logging.INFO})
		result = formatter.format(record)
		assert result.startswith("hello")

	def test_with_extra_fields(self) -> None:
		formatter = StructuredFormatter("%(message)s")
		record = logging.makeLogRecord({
			"msg": "request completed",
			"event": "handler.done",
			"status_code": 200,
		})
		result = formatter.format(record)
		assert "request completed" in result
		assert "event=" in result
		assert "status_code=" in result


class TestJsonFormatter:
	"""JsonFormatter 格式化测试。"""

	def test_produces_valid_json(self) -> None:
		formatter = JsonFormatter()
		record = logging.makeLogRecord({
			"msg": "test message",
			"levelname": "INFO",
			"name": "test.logger",
		})
		result = formatter.format(record)
		parsed = json.loads(result)
		assert parsed["message"] == "test message"
		assert parsed["level"] == "INFO"
		assert parsed["logger"] == "test.logger"
		assert "timestamp" in parsed

	def test_extra_fields_in_json(self) -> None:
		formatter = JsonFormatter()
		record = logging.makeLogRecord({
			"msg": "test",
			"levelname": "WARNING",
			"name": "test",
			"event": "test.event",
		})
		result = formatter.format(record)
		parsed = json.loads(result)
		assert parsed["event"] == "test.event"


class TestParseLogLevel:
	"""_parse_log_level() 日志级别解析测试。"""

	def test_string_levels(self) -> None:
		assert _parse_log_level("DEBUG") == logging.DEBUG
		assert _parse_log_level("INFO") == logging.INFO
		assert _parse_log_level("WARNING") == logging.WARNING
		assert _parse_log_level("ERROR") == logging.ERROR

	def test_case_insensitive(self) -> None:
		assert _parse_log_level("info") == logging.INFO
		assert _parse_log_level("Info") == logging.INFO

	def test_int_passthrough(self) -> None:
		assert _parse_log_level(logging.DEBUG) == logging.DEBUG

	def test_invalid_defaults_to_info(self) -> None:
		assert _parse_log_level("INVALID") == logging.INFO

	def test_none_defaults_to_info(self) -> None:
		assert _parse_log_level(None) == logging.INFO


class TestParseSampleRate:
	"""_parse_sample_rate() 采样率解析测试。"""

	def test_valid_rate(self) -> None:
		assert _parse_sample_rate(0.5) == 0.5

	def test_clamped_to_0(self) -> None:
		assert _parse_sample_rate(-0.5) == 0.0

	def test_clamped_to_1(self) -> None:
		assert _parse_sample_rate(1.5) == 1.0

	def test_invalid_returns_default(self) -> None:
		assert _parse_sample_rate("not_a_number") == 0.1

	def test_none_returns_default(self) -> None:
		assert _parse_sample_rate(None) == 0.1


class TestLogMetricsHandler:
	"""LogMetricsHandler 指标追踪测试。"""

	def test_emit_increments_total(self) -> None:
		handler = LogMetricsHandler()
		record = logging.makeLogRecord({"msg": "test", "levelname": "INFO", "levelno": logging.INFO, "name": "test"})
		handler.emit(record)
		handler.emit(record)
		snapshot = handler.snapshot()
		assert snapshot["total"] == 2

	def test_emit_tracks_by_level(self) -> None:
		handler = LogMetricsHandler()
		handler.emit(logging.makeLogRecord({"msg": "a", "levelname": "INFO", "levelno": logging.INFO, "name": "t"}))
		handler.emit(logging.makeLogRecord({"msg": "b", "levelname": "ERROR", "levelno": logging.ERROR, "name": "t"}))
		snapshot = handler.snapshot()
		assert snapshot["by_level"]["INFO"] == 1
		assert snapshot["by_level"]["ERROR"] == 1

	def test_emit_tracks_by_event(self) -> None:
		handler = LogMetricsHandler()
		record = logging.makeLogRecord({
			"msg": "test",
			"levelname": "INFO",
			"levelno": logging.INFO,
			"name": "test",
			"event": "handler.call",
		})
		handler.emit(record)
		assert handler.snapshot()["by_event"]["handler.call"] == 1

	def test_error_count_since(self) -> None:
		handler = LogMetricsHandler()
		handler.emit(logging.makeLogRecord({"msg": "err", "levelname": "ERROR", "levelno": logging.ERROR, "name": "t"}))
		count = handler.error_count_since(window_seconds=60)
		assert count == 1


class TestConfigureLoggingFileHandler:
	"""configure_logging() 文件日志支持测试。"""

	def test_log_file_creates_rotating_handler(self) -> None:
		with tempfile.TemporaryDirectory() as tmp_dir:
			log_file = str(Path(tmp_dir) / "test.log")
			root_logger = logging.getLogger()
			original_handlers = list(root_logger.handlers)
			try:
				configure_logging(log_file=log_file)
				expected_path = str(Path(log_file).expanduser().resolve())
				matching = [
					h for h in root_logger.handlers
					if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == expected_path
				]
				assert len(matching) >= 1, f"未找到 log_file={expected_path} 的 RotatingFileHandler"
			finally:
				for h in list(root_logger.handlers):
					if h not in original_handlers:
						root_logger.removeHandler(h)
						h.close()

	def test_log_file_empty_does_not_add_handler(self) -> None:
		root_logger = logging.getLogger()
		original_handlers = list(root_logger.handlers)
		try:
			configure_logging(log_file="")
			new_handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]
			original_file = [h for h in original_handlers if isinstance(h, RotatingFileHandler)]
			assert len(new_handlers) == len(original_file)
		finally:
			for h in list(root_logger.handlers):
				if h not in original_handlers:
					root_logger.removeHandler(h)
					h.close()

	def test_log_file_creates_parent_directory(self) -> None:
		with tempfile.TemporaryDirectory() as tmp_dir:
			log_file = str(Path(tmp_dir) / "nested" / "dir" / "test.log")
			root_logger = logging.getLogger()
			original_handlers = list(root_logger.handlers)
			try:
				configure_logging(log_file=log_file)
				assert Path(log_file).parent.exists()
			finally:
				for h in list(root_logger.handlers):
					if h not in original_handlers:
						root_logger.removeHandler(h)
						h.close()

	def test_duplicate_log_file_does_not_add_handler(self) -> None:
		with tempfile.TemporaryDirectory() as tmp_dir:
			log_file = str(Path(tmp_dir) / "test.log")
			root_logger = logging.getLogger()
			original_handlers = list(root_logger.handlers)
			try:
				configure_logging(log_file=log_file)
				count_before = sum(1 for h in root_logger.handlers if isinstance(h, RotatingFileHandler))
				configure_logging(log_file=log_file)
				count_after = sum(1 for h in root_logger.handlers if isinstance(h, RotatingFileHandler))
				assert count_after == count_before
			finally:
				for h in list(root_logger.handlers):
					if h not in original_handlers:
						root_logger.removeHandler(h)
						h.close()
