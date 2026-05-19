"""ExecutionPipeline 单元测试."""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from postman_api_tester.core.pipeline import ExecutionPipeline, ExecutionResult
from postman_api_tester.exceptions import ParseError


class MockConfig:
    """模拟配置对象."""

    def __init__(self) -> None:
        self.base_url = "http://localhost:8080"
        self.token = ""
        self.output_dir = tempfile.gettempdir()
        self.results_per_page = 30
        self.enable_checkpoint_recovery = False
        self.checkpoint_dir = tempfile.gettempdir()
        self.assertion_strict_mode = False
        self.collection_name = "Test Collection"


class TestExecutionPipeline:
    """ExecutionPipeline 测试套件."""

    def test_pipeline_init(self) -> None:
        """测试 Pipeline 初始化."""
        config = MockConfig()
        pipeline = ExecutionPipeline(config)
        assert pipeline.config == config
        assert pipeline.checkpoint_mgr is not None

    def test_pipeline_invalid_collection_file(self) -> None:
        """测试非法 Collection 文件抛出 ParseError."""
        config = MockConfig()
        pipeline = ExecutionPipeline(config)

        with pytest.raises(ParseError):
            pipeline.execute("/nonexistent/file.json")

    def test_execution_result_structure(self) -> None:
        """测试 ExecutionResult 结构."""
        result = ExecutionResult(
            success=True,
            results=[{"status": "PASSED"}],
            report_data={"summary": {"total": 1}},
        )
        assert result.success is True
        assert len(result.results) == 1
        assert result.report_data["summary"]["total"] == 1
