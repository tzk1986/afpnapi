"""Tests for execution_helpers module in core/execution_helpers.py."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from postman_api_tester.core.execution_helpers import (
    _resolve_output_dir,
    _validate_base_url,
    _filter_selected_apis,
    _resolve_report_file_path,
    _emit_progress,
)
from postman_api_tester.exceptions import ValidationError


class TestResolveOutputDir:
    """Tests for _resolve_output_dir function."""

    def test_explicit_output_dir_returned(self) -> None:
        result = _resolve_output_dir("/custom/path")
        assert result == "/custom/path"

    def test_none_falls_back_to_default(self) -> None:
        result = _resolve_output_dir(None)
        assert result.endswith("reports")

    def test_default_path_is_absolute(self) -> None:
        result = _resolve_output_dir(None)
        assert os.path.isabs(result)


class TestValidateBaseUrl:
    """Tests for _validate_base_url function."""

    def test_none_is_valid(self) -> None:
        # None base_url 不应抛出异常
        _validate_base_url(None)

    def test_http_url_is_valid(self) -> None:
        # HTTP URL 不应抛出异常
        _validate_base_url("http://example.com")

    def test_https_url_is_valid(self) -> None:
        # HTTPS URL 不应抛出异常
        _validate_base_url("https://api.example.com/v1")

    def test_ftp_url_raises(self) -> None:
        with pytest.raises(ValidationError, match="base_url 格式无效"):
            _validate_base_url("ftp://example.com")

    def test_javascript_url_raises(self) -> None:
        with pytest.raises(ValidationError, match="base_url 格式无效"):
            _validate_base_url("javascript:alert(1)")

    def test_empty_scheme_raises(self) -> None:
        with pytest.raises(ValidationError, match="base_url 格式无效"):
            _validate_base_url("example.com")

    def test_no_netloc_raises(self) -> None:
        with pytest.raises(ValidationError, match="base_url 格式无效"):
            _validate_base_url("http://")


class TestFilterSelectedApis:
    """Tests for _filter_selected_apis function."""

    def _make_api(self, item_path: List[int]) -> Dict[str, Any]:
        return {"item_path": item_path, "name": f"api_{'_'.join(map(str, item_path))}"}

    def test_none_selected_returns_all(self) -> None:
        apis = [self._make_api([0, 1]), self._make_api([0, 2])]
        result, path_set = _filter_selected_apis(apis, None)
        assert len(result) == 2
        assert path_set is None

    def test_invalid_only_paths_raises(self) -> None:
        apis = [self._make_api([0, 1])]
        with pytest.raises(ValidationError, match="selected_item_paths 格式无效"):
            _filter_selected_apis(apis, [["invalid"], [-1]])

    def test_invalid_path_format_ignored(self) -> None:
        apis = [self._make_api([0, 1])]
        with pytest.raises(ValidationError, match="selected_item_paths 格式无效"):
            _filter_selected_apis(apis, [[-1, "invalid"]])

    def test_matching_paths_filtered(self) -> None:
        apis = [self._make_api([0, 1]), self._make_api([0, 2]), self._make_api([0, 3])]
        result, path_set = _filter_selected_apis(apis, [[0, 1], [0, 3]])
        assert len(result) == 2
        assert result[0]["item_path"] == [0, 1]
        assert result[1]["item_path"] == [0, 3]

    def test_no_match_raises(self) -> None:
        apis = [self._make_api([0, 1])]
        with pytest.raises(ValidationError, match="未匹配到可执行接口"):
            _filter_selected_apis(apis, [[9, 9]])

    def test_path_set_is_tuple_set(self) -> None:
        apis = [self._make_api([0, 1])]
        _, path_set = _filter_selected_apis(apis, [[0, 1]])
        assert path_set == {(0, 1)}


class TestResolveReportFilePath:
    """Tests for _resolve_report_file_path function."""

    def test_default_name_with_timestamp(self, tmp_path: Path) -> None:
        result = _resolve_report_file_path(str(tmp_path), None)
        assert result.startswith(str(tmp_path))
        assert "postman_report_" in result
        assert result.endswith(".html")

    def test_custom_name_preserved(self, tmp_path: Path) -> None:
        result = _resolve_report_file_path(str(tmp_path), "my_report.html")
        assert "my_report.html" in result

    def test_custom_name_without_extension_gets_html(self, tmp_path: Path) -> None:
        result = _resolve_report_file_path(str(tmp_path), "my_report")
        assert result.endswith(".html")

    def test_path_traversal_sanitized(self, tmp_path: Path) -> None:
        result = _resolve_report_file_path(str(tmp_path), "../../../etc/passwd")
        assert ".." not in os.path.basename(result)

    def test_special_chars_sanitized(self, tmp_path: Path) -> None:
        result = _resolve_report_file_path(str(tmp_path), "report<>:\"|?*.html")
        basename = os.path.basename(result)
        assert "<" not in basename
        assert ">" not in basename

    def test_existing_file_gets_timestamp_suffix(self, tmp_path: Path) -> None:
        existing_file = tmp_path / "report.html"
        existing_file.write_text("existing")
        result = _resolve_report_file_path(str(tmp_path), "report.html")
        assert result != str(existing_file)


class TestEmitProgress:
    """Tests for _emit_progress function."""

    def test_none_callback_does_nothing(self) -> None:
        # None callback 不应抛出异常
        _emit_progress(None, {"stage": "running", "completed": 0})

    def test_callback_invoked_with_payload(self) -> None:
        callback = MagicMock()
        payload = {"stage": "running", "completed": 5}
        _emit_progress(callback, payload)
        callback.assert_called_once_with(payload)

    def test_callback_exception_swallowed(self) -> None:
        callback = MagicMock(side_effect=RuntimeError("callback error"))
        # callback 抛出异常不应传播
        _emit_progress(callback, {"stage": "running"})
        callback.assert_called_once()


class TestResolveRuntimeConfig:
    """Tests for _resolve_runtime_config function."""

    def test_explicit_params_take_priority(self) -> None:
        from postman_api_tester.core.execution_helpers import _resolve_runtime_config
        from postman_api_tester import config

        original_token = getattr(config, 'TOKEN', '')
        original_base_url = getattr(config, 'BASE_URL', '')
        original_output_dir = getattr(config, 'REPORT_OUTPUT_DIR', '')

        try:
            config.TOKEN = "config_token"
            config.BASE_URL = "http://config.com"
            config.REPORT_OUTPUT_DIR = "/config/output"

            token, base_url, output_dir, *_ = _resolve_runtime_config(
                "explicit_token",
                "http://explicit.com",
                "/explicit/output",
            )

            assert token == "explicit_token"
            assert base_url == "http://explicit.com"
            assert output_dir == "/explicit/output"
        finally:
            config.TOKEN = original_token
            config.BASE_URL = original_base_url
            config.REPORT_OUTPUT_DIR = original_output_dir

    def test_config_fallback_when_params_none(self) -> None:
        from postman_api_tester.core.execution_helpers import _resolve_runtime_config
        from postman_api_tester import config

        original_token = getattr(config, 'TOKEN', '')
        original_base_url = getattr(config, 'BASE_URL', '')
        original_output_dir = getattr(config, 'REPORT_OUTPUT_DIR', '')
        original_ckpt = getattr(config, 'ENABLE_CHECKPOINT_RECOVERY', False)
        original_flush = getattr(config, 'CHECKPOINT_FLUSH_EVERY_N', 1)
        original_ckpt_dir = getattr(config, 'CHECKPOINT_DIR', '')
        original_strict = getattr(config, 'ENABLE_ASSERTION_STRICT_MODE', False)

        try:
            config.TOKEN = "config_token"
            config.BASE_URL = "http://config.com"
            config.REPORT_OUTPUT_DIR = "/config/output"
            config.ENABLE_CHECKPOINT_RECOVERY = True
            config.CHECKPOINT_FLUSH_EVERY_N = 5
            config.CHECKPOINT_DIR = "/tmp/checkpoints"
            config.ENABLE_ASSERTION_STRICT_MODE = True

            token, base_url, output_dir, ckpt_enabled, ckpt_flush, ckpt_dir, strict = _resolve_runtime_config(
                None, None, None
            )

            assert token == "config_token"
            assert base_url == "http://config.com"
            assert output_dir == "/config/output"
            assert ckpt_enabled is True
            assert ckpt_flush == 5
            assert ckpt_dir == "/tmp/checkpoints"
            assert strict is True
        finally:
            config.TOKEN = original_token
            config.BASE_URL = original_base_url
            config.REPORT_OUTPUT_DIR = original_output_dir
            config.ENABLE_CHECKPOINT_RECOVERY = original_ckpt
            config.CHECKPOINT_FLUSH_EVERY_N = original_flush
            config.CHECKPOINT_DIR = original_ckpt_dir
            config.ENABLE_ASSERTION_STRICT_MODE = original_strict
