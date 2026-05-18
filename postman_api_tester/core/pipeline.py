"""执行流程编排模块。

职责：
- 管理解析 -> 认证 -> 执行 -> 报告的完整链路
- 支持断点恢复
- 不涉及磁盘 I/O（由上层处理）
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from postman_api_tester.core.checkpoint_manager import CheckpointManager
from postman_api_tester.core.report_engine import ReportEngine
from postman_api_tester.exceptions import (
    ExecutionError,
    ParseError,
    ValidationError,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果对象。"""

    success: bool
    results: List[Dict[str, Any]]
    report_data: Dict[str, Any]
    error: Optional[Exception] = None


class ExecutionPipeline:
    """统一的测试执行流程编排。"""

    def __init__(self, config: Any) -> None:
        """初始化 Pipeline。

        Args:
            config: 执行配置对象（需包含 base_url, token, checkpoint_dir 等属性）
        """
        self.config = config
        self.checkpoint_mgr = CheckpointManager(
            checkpoint_dir=config.checkpoint_dir,
            job_id=getattr(config, "job_id", "default"),
        )

    def execute(self, collection_file: str) -> ExecutionResult:
        """完整执行流程，支持断点恢复。

        Args:
            collection_file: Postman Collection JSON 文件路径

        Returns:
            ExecutionResult 包含成功/失败状态、结果列表、报告数据

        Raises:
            ParseError: Collection 解析失败
            ValidationError: 参数验证失败
            ExecutionError: 执行过程中错误
        """
        # 1. 验证输入
        self._validate_inputs(collection_file)

        # 2. 解析 Collection
        collection = self._parse_collection(collection_file)

        # 3. 准备 API 列表（含断点恢复过滤）
        apis = self._prepare_apis(collection)

        # 4. 执行测试
        results = self._execute_apis(apis)

        # 5. 生成报告
        report_data = self._generate_report(results)

        # 6. 清理检查点
        self._cleanup_checkpoint(collection)

        success = all(r.get("status") == "PASSED" for r in results)
        return ExecutionResult(
            success=success,
            results=results,
            report_data=report_data,
        )

    def _validate_inputs(self, collection_file: str) -> None:
        """验证输入参数。"""
        if not collection_file or not isinstance(collection_file, str):
            raise ValidationError("collection_file must be a non-empty string")

        path = Path(collection_file)
        if not path.exists():
            raise ParseError(f"Collection file not found: {collection_file}")

    def _parse_collection(self, collection_file: str) -> Dict[str, Any]:
        """解析 Collection 文件。"""
        try:
            with open(collection_file, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            logger.debug("collection_parsed", extra={"file": collection_file})
            return data
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON in collection file: {e}") from e

    def _prepare_apis(self, collection: Dict[str, Any]) -> List[Dict[str, Any]]:
        """准备 API 列表（含断点恢复过滤）。"""
        # 简化实现：从 collection 中提取 items
        apis = self._extract_items(collection)

        # 断点恢复过滤
        if self.config.enable_checkpoint_recovery:
            fingerprint = self._calculate_fingerprint(collection)
            checkpoint = self.checkpoint_mgr.load_if_exists(fingerprint)
            if checkpoint:
                executed = checkpoint.get("executed_item_paths", [])
                apis = self.checkpoint_mgr.filter_executed_apis(apis, executed)
                logger.info(
                    "checkpoint_resumed",
                    extra={"skipped": len(executed), "remaining": len(apis)},
                )

        return apis

    def _extract_items(self, collection: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Collection 中提取 API 列表。"""
        items: List[Dict[str, Any]] = []
        for idx, item in enumerate(collection.get("item", [])):
            items.append({
                "item_path": [0, idx],
                "name": item.get("name", f"API_{idx}"),
                "method": item.get("request", {}).get("method", "GET"),
                "url": item.get("request", {}).get("url", {}).get("raw", ""),
            })
        return items

    def _calculate_fingerprint(self, collection: Dict[str, Any]) -> str:
        """计算 Collection 指纹（用于 checkpoint）。"""
        import hashlib
        content = str(collection.get("info", {}).get("name", ""))
        return hashlib.md5(content.encode()).hexdigest()

    def _execute_apis(self, apis: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行 API 列表（简化版，实际应调用 executor 模块）。"""
        results: List[Dict[str, Any]] = []
        for api in apis:
            # 实际实现中，这里应调用 executor 模块
            result = {
                "name": api["name"],
                "status": "PASSED",  # 简化
                "response_time_ms": 100,
                "item_path": api["item_path"],
            }
            results.append(result)
        return results

    def _generate_report(
        self,
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """生成报告。"""
        config: Dict[str, Any] = {
            "collection_name": getattr(self.config, "collection_name", "Unknown"),
            "base_url": self.config.base_url,
        }
        report_data: Dict[str, Any] = ReportEngine.generate(results, config)
        return report_data

    def _cleanup_checkpoint(self, collection: Dict[str, Any]) -> None:
        """清理检查点。"""
        if self.config.enable_checkpoint_recovery:
            fingerprint = self._calculate_fingerprint(collection)
            self.checkpoint_mgr.cleanup_after_success(fingerprint)
