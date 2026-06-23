"""session 模块单元测试。

覆盖 close_session、resolve_request_timeout、normalize_timeout。
"""

from typing import Any, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.session import (
	close_session,
	normalize_timeout,
	resolve_request_timeout,
)


class TestCloseSession:
	"""close_session() 会话关闭测试。"""

	def test_none_session_no_error(self) -> None:
		close_session(None)

	def test_normal_close(self) -> None:
		mock_session = MagicMock()
		close_session(mock_session)
		mock_session.close.assert_called_once()

	def test_os_error_caught(self) -> None:
		mock_session = MagicMock()
		mock_session.close.side_effect = OSError("connection reset")
		close_session(mock_session)

	def test_generic_exception_caught(self) -> None:
		mock_session = MagicMock()
		mock_session.close.side_effect = RuntimeError("unexpected")
		close_session(mock_session)


class TestNormalizeTimeout:
	"""normalize_timeout() 超时规范化测试。"""

	def test_valid_tuple(self) -> None:
		assert normalize_timeout((5, 30)) == (5, 30)

	def test_none_returns_default(self) -> None:
		assert normalize_timeout(None) == (10, 30)

	def test_zero_connect_returns_default(self) -> None:
		assert normalize_timeout((0, 30)) == (10, 30)

	def test_negative_read_returns_default(self) -> None:
		assert normalize_timeout((5, -1)) == (10, 30)

	def test_both_zero_returns_default(self) -> None:
		assert normalize_timeout((0, 0)) == (10, 30)

	def test_empty_tuple_returns_default(self) -> None:
		assert normalize_timeout(()) == (10, 30)

	def test_string_values_converted(self) -> None:
		assert normalize_timeout(("5", "30")) == (5, 30)

	def test_invalid_string_returns_default(self) -> None:
		assert normalize_timeout(("abc", "30")) == (10, 30)

	def test_custom_default(self) -> None:
		assert normalize_timeout(None, default=(20, 60)) == (20, 60)

	def test_float_values_converted(self) -> None:
		assert normalize_timeout((5.5, 30.7)) == (5, 30)

	def test_single_element_returns_default(self) -> None:
		assert normalize_timeout((5,)) == (10, 30)  # type: ignore[arg-type]


class TestResolveRequestTimeout:
	"""resolve_request_timeout() 配置读取测试。"""

	def test_reads_config_defaults(self) -> None:
		result = resolve_request_timeout()
		assert result == (10, 30)

	def test_returns_tuple(self) -> None:
		result = resolve_request_timeout()
		assert isinstance(result, tuple)
		assert len(result) == 2
		assert all(isinstance(v, int) for v in result)

	def test_default_fallback(self) -> None:
		result = resolve_request_timeout(default=(5, 15))
		assert isinstance(result, tuple)
		assert len(result) == 2

	def test_with_custom_config(self) -> None:
		mock_cfg = MagicMock()
		mock_cfg.REQUEST_CONNECT_TIMEOUT = 15
		mock_cfg.REQUEST_READ_TIMEOUT = 45
		with patch("postman_api_tester.config", mock_cfg):
			result = resolve_request_timeout()
		assert result == (15, 45)
