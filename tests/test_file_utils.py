"""file_utils 单元测试：atomic_write_json、sanitize_export_name、safe_report_artifact。"""

import json
import os
from pathlib import Path

import pytest

from postman_api_tester.utils.file_utils import (
    atomic_write_json,
    safe_report_artifact,
    sanitize_export_name,
)


class TestAtomicWriteJson:
    """atomic_write_json() 原子写入测试。"""

    def test_writes_json_file(self, tmp_path: Path) -> None:
        """正常写入 JSON 文件，内容正确。"""
        target = tmp_path / "test.json"
        data = {"key": "value", "num": 42}
        atomic_write_json(target, data)
        assert target.exists()
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """目标路径父目录不存在时自动创建。"""
        target = tmp_path / "sub" / "dir" / "test.json"
        atomic_write_json(target, {"ok": True})
        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """覆盖已有文件，内容替换为新数据。"""
        target = tmp_path / "test.json"
        target.write_text(json.dumps({"old": True}), encoding="utf-8")
        atomic_write_json(target, {"new": True})
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == {"new": True}
        assert loaded.get("old") is None

    def test_cleans_up_temp_file_on_failure(self, tmp_path: Path) -> None:
        """写入失败时临时文件应被清理。"""
        target = tmp_path / "test.json"
        before = set(tmp_path.iterdir())
        with pytest.raises(TypeError):
            atomic_write_json(target, object())
        after = set(tmp_path.iterdir())
        assert before == after

    def test_ensure_ascii_false(self, tmp_path: Path) -> None:
        """中文内容应原样写入，不被转义。"""
        target = tmp_path / "cn.json"
        atomic_write_json(target, {"msg": "你好世界"})
        content = target.read_text(encoding="utf-8")
        assert "你好世界" in content
        assert "\\u" not in content


class TestSanitizeExportName:
    """sanitize_export_name() 文件名清洗测试。"""

    def test_removes_special_chars(self) -> None:
        assert sanitize_export_name("test<>:file.json") == "test_file.json"

    def test_handles_path_traversal(self) -> None:
        result = sanitize_export_name("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_empty_returns_collection(self) -> None:
        assert sanitize_export_name("") == "collection"
        assert sanitize_export_name(None) == "collection"  # type: ignore[arg-type]


class TestSafeReportArtifact:
    """safe_report_artifact() 路径安全测试。"""

    def test_valid_path(self, tmp_path: Path) -> None:
        result = safe_report_artifact(tmp_path, "sub/report.json")
        assert result is not None
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_path_traversal_returns_none(self, tmp_path: Path) -> None:
        result = safe_report_artifact(tmp_path, "../../etc/passwd")
        assert result is None

    def test_empty_name_returns_none(self, tmp_path: Path) -> None:
        assert safe_report_artifact(tmp_path, "") is None
        assert safe_report_artifact(tmp_path, "  ") is None
