"""断点恢复管理模块。

职责：
- 按 collection_fingerprint 保存/加载执行进度
- 支持原子性读写（先写临时文件再重命名）
- 执行成功后自动清理 checkpoint
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from postman_api_tester.exceptions import CheckpointRecoveryFailed

logger = logging.getLogger(__name__)


def _item_path_text(path: Any) -> str:
    """将 item_path 列表转换为字符串键。"""
    if not isinstance(path, list):
        return ""
    if not all(isinstance(index, int) and index >= 0 for index in path):
        return ""
    return ".".join(str(index) for index in path)


class CheckpointManager:
    """断点恢复管理器。"""

    def __init__(self, checkpoint_dir: str | Path, job_id: str = "default") -> None:
        """初始化。

        Args:
            checkpoint_dir: checkpoint 文件存放目录
            job_id: 任务标识（用于日志追踪）
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.job_id = job_id
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """确保 checkpoint 目录存在。"""
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise CheckpointRecoveryFailed(
                f"Cannot create checkpoint directory: {self.checkpoint_dir}"
            ) from e

    def _checkpoint_path(self, fingerprint: str) -> Path:
        """生成 checkpoint 文件路径。"""
        return self.checkpoint_dir / f"checkpoint_{fingerprint}.json"

    def save(
        self,
        fingerprint: str,
        executed_item_paths: List[List[int]],
    ) -> None:
        """保存 checkpoint（原子写入）。

        Args:
            fingerprint: collection 指纹
            executed_item_paths: 已执行的 item_path 列表
        """
        self._ensure_directory()
        checkpoint_path = self._checkpoint_path(fingerprint)
        data: Dict[str, Any] = {
            "fingerprint": fingerprint,
            "executed_item_paths": executed_item_paths,
            "timestamp": datetime.now().isoformat(),
            "job_id": self.job_id,
        }

        try:
            # 原子写入：先写临时文件，再重命名
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(self.checkpoint_dir),
                delete=False,
                suffix=".tmp",
            ) as f:
                json.dump(data, f, ensure_ascii=False)
                temp_path = f.name

            os.replace(temp_path, checkpoint_path)
            logger.debug(
                "checkpoint_saved",
                extra={"fingerprint": fingerprint, "count": len(executed_item_paths)},
            )
        except OSError as e:
            raise CheckpointRecoveryFailed(f"Failed to save checkpoint: {e}") from e

    def load_if_exists(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """加载 checkpoint（如果不存在则返回 None）。

        Args:
            fingerprint: collection 指纹

        Returns:
            checkpoint 数据或 None
        """
        checkpoint_path = self._checkpoint_path(fingerprint)
        if not checkpoint_path.exists():
            return None

        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            logger.info(
                "checkpoint_loaded",
                extra={
                    "fingerprint": fingerprint,
                    "count": len(data.get("executed_item_paths", [])),
                },
            )
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Corrupted checkpoint, removing: {e}")
            checkpoint_path.unlink(missing_ok=True)
            return None

    def cleanup_after_success(self, fingerprint: str) -> None:
        """执行成功后清理 checkpoint。"""
        checkpoint_path = self._checkpoint_path(fingerprint)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.debug("checkpoint_cleaned", extra={"fingerprint": fingerprint})

    @staticmethod
    def filter_executed_apis(
        apis: List[Dict[str, Any]],
        executed_item_paths: List[List[int]],
    ) -> List[Dict[str, Any]]:
        """过滤掉已执行的 API。

        Args:
            apis: 全部 API 列表
            executed_item_paths: 已执行的 item_path 列表

        Returns:
            未执行的 API 列表
        """
        executed_set = {_item_path_text(p) for p in executed_item_paths}
        return [
            api for api in apis
            if _item_path_text(api.get("item_path")) not in executed_set
        ]
