"""CheckpointManager 单元测试."""

import json
import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from postman_api_tester.core.checkpoint_manager import CheckpointManager
from postman_api_tester.exceptions import CheckpointRecoveryFailed


@pytest.fixture  # type: ignore[untyped-decorator]
def temp_checkpoint_dir() -> Generator[Path, None, None]:
    """提供临时 checkpoint 目录."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestCheckpointManager:
    """CheckpointManager 测试套件."""

    def test_save_and_load_checkpoint(self, temp_checkpoint_dir: Path) -> None:
        """测试保存和加载 checkpoint."""
        mgr = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        fingerprint = "test_fp_123"
        executed = [[0, 1], [0, 2]]

        mgr.save(fingerprint, executed)
        loaded = mgr.load_if_exists(fingerprint)

        assert loaded is not None
        assert loaded["executed_item_paths"] == executed
        assert "timestamp" in loaded

    def test_load_nonexistent_checkpoint(self, temp_checkpoint_dir: Path) -> None:
        """测试加载不存在的 checkpoint."""
        mgr = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        loaded = mgr.load_if_exists("nonexistent_fp")
        assert loaded is None

    def test_cleanup_after_success(self, temp_checkpoint_dir: Path) -> None:
        """测试成功后清理 checkpoint."""
        mgr = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        fingerprint = "test_fp_456"
        mgr.save(fingerprint, [[0, 1]])
        mgr.cleanup_after_success(fingerprint)

        loaded = mgr.load_if_exists(fingerprint)
        assert loaded is None

    def test_filter_executed_apis(self, temp_checkpoint_dir: Path) -> None:
        """测试过滤已执行 API."""
        mgr = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        apis = [
            {"item_path": [0, 0], "name": "API1"},
            {"item_path": [0, 1], "name": "API2"},
            {"item_path": [0, 2], "name": "API3"},
        ]
        executed = [[0, 0], [0, 2]]

        filtered = mgr.filter_executed_apis(apis, executed)
        assert len(filtered) == 1
        assert filtered[0]["name"] == "API2"

    def test_invalid_checkpoint_dir_raises_error(self) -> None:
        """测试非法目录权限时抛出异常."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            # 使用已存在的文件作为目录路径，会导致 NotADirectoryError
            file_path = f.name
        try:
            with pytest.raises(CheckpointRecoveryFailed):
                mgr = CheckpointManager(checkpoint_dir=file_path)
                mgr.save("fp", [])
        finally:
            os.unlink(file_path)
