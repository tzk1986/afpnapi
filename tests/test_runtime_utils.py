"""runtime_utils 模块单元测试。

覆盖 normalize_url_and_params、merge_url_with_params、item_path_text、
checkpoint_key、checkpoint_file_path、load_checkpoint、save_checkpoint_atomic、
compute_collection_fingerprint。
"""

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

import pytest

from postman_api_tester.runtime_utils import (
	checkpoint_file_path,
	checkpoint_key,
	compute_collection_fingerprint,
	item_path_text,
	load_checkpoint,
	merge_url_with_params,
	normalize_url_and_params,
	save_checkpoint_atomic,
)


class TestNormalizeUrlAndParams:
	"""normalize_url_and_params() URL 与参数合并测试。"""

	def test_url_without_params(self) -> None:
		url, params = normalize_url_and_params("https://example.com/api", None)
		assert url == "https://example.com/api"
		assert params == {}

	def test_url_with_query_string(self) -> None:
		url, params = normalize_url_and_params("https://example.com/api?a=1&b=2", None)
		assert url == "https://example.com/api"
		assert params == {"a": "1", "b": "2"}

	def test_params_dict_merged(self) -> None:
		url, params = normalize_url_and_params("https://example.com/api?a=1", {"b": "2"})
		assert url == "https://example.com/api"
		assert params == {"a": "1", "b": "2"}

	def test_params_override_query(self) -> None:
		url, params = normalize_url_and_params("https://example.com/api?a=1", {"a": "99"})
		assert params["a"] == "99"

	def test_empty_url(self) -> None:
		url, params = normalize_url_and_params("", None)
		assert url == ""
		assert params == {}

	def test_blank_url(self) -> None:
		url, params = normalize_url_and_params("  ", None)
		assert url == ""
		assert params == {}

	def test_url_with_fragment(self) -> None:
		url, params = normalize_url_and_params("https://example.com/api?x=1#section", None)
		assert url == "https://example.com/api#section"
		assert params == {"x": "1"}

	def test_blank_query_values_preserved(self) -> None:
		url, params = normalize_url_and_params("https://example.com/api?key=", None)
		assert params == {"key": ""}


class TestMergeUrlWithParams:
	"""merge_url_with_params() 完整 URL 拼接测试。"""

	def test_basic_merge(self) -> None:
		result = merge_url_with_params("https://example.com/api", {"a": "1"})
		assert "a=1" in result

	def test_merge_with_existing_query(self) -> None:
		result = merge_url_with_params("https://example.com/api?a=1", {"b": "2"})
		assert "a=1" in result
		assert "b=2" in result

	def test_empty_params(self) -> None:
		result = merge_url_with_params("https://example.com/api", {})
		assert result == "https://example.com/api"

	def test_none_value_becomes_empty(self) -> None:
		result = merge_url_with_params("https://example.com/api", {"key": None})
		assert "key=" in result

	def test_numeric_value_converted(self) -> None:
		result = merge_url_with_params("https://example.com/api", {"page": 42})
		assert "page=42" in result


class TestItemPathText:
	"""item_path_text() 路径序列化测试。"""

	def test_simple_path(self) -> None:
		assert item_path_text([0, 2, 1]) == "0.2.1"

	def test_empty_list(self) -> None:
		assert item_path_text([]) == ""

	def test_single_element(self) -> None:
		assert item_path_text([3]) == "3"

	def test_not_a_list(self) -> None:
		assert item_path_text("0.2.1") == ""

	def test_negative_index(self) -> None:
		assert item_path_text([0, -1]) == ""

	def test_non_int_element(self) -> None:
		assert item_path_text([0, "a"]) == ""

	def test_none_input(self) -> None:
		assert item_path_text(None) == ""


class TestCheckpointKey:
	"""checkpoint_key() 复合键生成测试。"""

	def test_default_data_index(self) -> None:
		assert checkpoint_key([0, 2, 1]) == "0.2.1"

	def test_zero_data_index(self) -> None:
		assert checkpoint_key([0, 2, 1], data_index=0) == "0.2.1"

	def test_positive_data_index(self) -> None:
		assert checkpoint_key([0, 2, 1], data_index=3) == "0.2.1#3"

	def test_empty_path(self) -> None:
		assert checkpoint_key([]) == ""

	def test_invalid_path(self) -> None:
		assert checkpoint_key(None) == ""


class TestCheckpointFilePath:
	"""checkpoint_file_path() 路径生成测试。"""

	def test_default_checkpoint_dir(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			result = checkpoint_file_path(tmpdir, "test.json", "abcdef1234567890")
			assert "checkpoints" in result
			assert result.endswith(".checkpoint.json")
			assert "test_" in result

	def test_custom_checkpoint_dir(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			custom = os.path.join(tmpdir, "my_checkpoints")
			result = checkpoint_file_path(tmpdir, "test.json", "abcdef1234567890", checkpoint_dir=custom)
			assert "my_checkpoints" in result

	def test_fingerprint_truncated(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			result = checkpoint_file_path(tmpdir, "test.json", "abcdef1234567890abcdef")
			basename = os.path.basename(result)
			assert "abcdef1234567890" in basename

	def test_special_chars_in_filename(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			result = checkpoint_file_path(tmpdir, "my file (1).json", "abcdef1234567890")
			basename = os.path.basename(result)
			assert " " not in basename
			assert "(" not in basename


class TestLoadCheckpoint:
	"""load_checkpoint() checkpoint 加载测试。"""

	def test_nonexistent_file(self) -> None:
		assert load_checkpoint("/nonexistent/path.json") is None

	def test_empty_path(self) -> None:
		assert load_checkpoint("") is None

	def test_valid_checkpoint(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"executed_item_paths": ["0.1", "0.2"]}, f)
			f.flush()
			result = load_checkpoint(f.name)
		os.unlink(f.name)
		assert result is not None
		assert result["executed_item_paths"] == ["0.1", "0.2"]

	def test_invalid_json(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			f.write("not json")
			f.flush()
			result = load_checkpoint(f.name)
		os.unlink(f.name)
		assert result is None

	def test_non_dict_json(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump([1, 2, 3], f)
			f.flush()
			result = load_checkpoint(f.name)
		os.unlink(f.name)
		assert result is None

	def test_missing_executed_key(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"other": "data"}, f)
			f.flush()
			result = load_checkpoint(f.name)
		os.unlink(f.name)
		assert result is None

	def test_non_list_executed(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"executed_item_paths": "not a list"}, f)
			f.flush()
			result = load_checkpoint(f.name)
		os.unlink(f.name)
		assert result is None

	def test_non_string_items_in_list(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"executed_item_paths": [1, 2]}, f)
			f.flush()
			result = load_checkpoint(f.name)
		os.unlink(f.name)
		assert result is None


class TestSaveCheckpointAtomic:
	"""save_checkpoint_atomic() 原子写入测试。"""

	def test_save_and_load(self) -> None:
		with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
			path = f.name
		data = {"executed_item_paths": ["0.1"], "status": "running"}
		save_checkpoint_atomic(path, data)
		loaded = load_checkpoint(path)
		os.unlink(path)
		assert loaded is not None
		assert loaded["executed_item_paths"] == ["0.1"]

	def test_no_tmp_left_on_success(self) -> None:
		with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
			path = f.name
		save_checkpoint_atomic(path, {"executed_item_paths": []})
		assert not os.path.exists(f"{path}.tmp")
		os.unlink(path)

	def test_overwrite_existing(self) -> None:
		with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
			path = f.name
		save_checkpoint_atomic(path, {"executed_item_paths": ["0.1"]})
		save_checkpoint_atomic(path, {"executed_item_paths": ["0.1", "0.2"]})
		loaded = load_checkpoint(path)
		os.unlink(path)
		assert loaded is not None
		assert len(loaded["executed_item_paths"]) == 2


class TestComputeCollectionFingerprint:
	"""compute_collection_fingerprint() 指纹计算测试。"""

	def test_same_input_same_hash(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"info": {"name": "test"}}, f)
			f.flush()
			h1 = compute_collection_fingerprint(f.name, "https://api.example.com", None)
			h2 = compute_collection_fingerprint(f.name, "https://api.example.com", None)
		os.unlink(f.name)
		assert h1 == h2

	def test_different_url_different_hash(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"info": {}}, f)
			f.flush()
			h1 = compute_collection_fingerprint(f.name, "https://a.com", None)
			h2 = compute_collection_fingerprint(f.name, "https://b.com", None)
		os.unlink(f.name)
		assert h1 != h2

	def test_different_content_different_hash(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f1:
			json.dump({"v": 1}, f1)
			f1.flush()
			h1 = compute_collection_fingerprint(f1.name, "", None)
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f2:
			json.dump({"v": 2}, f2)
			f2.flush()
			h2 = compute_collection_fingerprint(f2.name, "", None)
		os.unlink(f1.name)
		os.unlink(f2.name)
		assert h1 != h2

	def test_selected_items_affect_hash(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({"info": {}}, f)
			f.flush()
			h1 = compute_collection_fingerprint(f.name, "", None)
			h2 = compute_collection_fingerprint(f.name, "", [[0, 1]])
		os.unlink(f.name)
		assert h1 != h2

	def test_with_data_file(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as pf:
			json.dump({"info": {}}, pf)
			pf.flush()
			with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as df:
				df.write("a,b\n1,2\n")
				df.flush()
				h1 = compute_collection_fingerprint(pf.name, "", None, data_file="")
				h2 = compute_collection_fingerprint(pf.name, "", None, data_file=df.name)
			os.unlink(df.name)
		os.unlink(pf.name)
		assert h1 != h2

	def test_returns_hex_string(self) -> None:
		with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
			json.dump({}, f)
			f.flush()
			result = compute_collection_fingerprint(f.name, "", None)
		os.unlink(f.name)
		assert len(result) == 64
		assert all(c in "0123456789abcdef" for c in result)
