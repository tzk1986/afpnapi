"""请求串联变量上下文。

在 ``_execute_api_suite()`` 生命周期内共享，用于跨接口传递提取的变量。
支持将变量持久化到 JSON 文件，跨执行周期复用。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from postman_api_tester.utils.extract_utils import extract_from_response

logger = logging.getLogger(__name__)


class VariableContext:
    """请求串联变量上下文。

    在同一 suite 执行期间持有所有已提取的变量，供后续接口的 ``{{variable}}`` 替换使用。
    线程安全：并发执行模式下多线程可同时读写变量。
    """

    def __init__(self, initial_variables: Optional[Dict[str, str]] = None) -> None:
        self._variables: Dict[str, str] = dict(initial_variables or {})
        self._lock = threading.Lock()

    @property
    def variables(self) -> Dict[str, str]:
        """返回变量字典副本，防止外部直接修改内部状态。"""
        with self._lock:
            return dict(self._variables)

    def get(self, name: str, default: str = "") -> str:
        with self._lock:
            return self._variables.get(name, default)

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self._variables[name] = value

    def update_from_extract(
        self,
        extract_config: Dict[str, str],
        response_data: Any,
        response_headers: Dict[str, str],
    ) -> Dict[str, str]:
        """根据 x_extract 配置从响应中提取变量并更新上下文。

        返回本次成功提取的变量字典（用于报告记录）。
        提取失败的字段不写入上下文（不覆盖已有值）。
        """
        extracted = extract_from_response(response_data, response_headers, extract_config)
        with self._lock:
            for var_name, value in extracted.items():
                self._variables[var_name] = value
                logger.debug("variable extracted: %s = %s", var_name, value[:50] if len(value) > 50 else value)

        failed_keys = set(extract_config.keys()) - set(extracted.keys())
        for var_name in failed_keys:
            logger.warning(
                "variable extraction failed: %s (expression: %s)",
                var_name,
                extract_config.get(var_name, ""),
            )
        return extracted

    def save_to_file(self, path: str, max_count: int = 1000) -> None:
        """将当前变量快照持久化到 JSON 文件。

        - 最多保存 ``max_count`` 个变量，超出则截断（按插入顺序）。
        - 写入失败时记录警告，不抛出异常。
        """
        with self._lock:
            snapshot = dict(self._variables)
        if len(snapshot) > max_count:
            logger.warning(
                "变量数量 %d 超过上限 %d，仅保存前 %d 个",
                len(snapshot), max_count, max_count,
            )
            snapshot = dict(list(snapshot.items())[:max_count])
        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "variables": snapshot,
        }
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("全局变量文件写入失败: %s (%s)", path, exc)

    @classmethod
    def load_from_file(
        cls,
        path: str,
        initial_variables: Optional[Dict[str, str]] = None,
        max_count: int = 1000,
    ) -> VariableContext:
        """从文件加载变量，与 initial_variables 合并（initial_variables 优先）。

        - 文件不存在或解析失败时返回空上下文（仅含 initial_variables）。
        - 合并后变量数量超过 ``max_count`` 时截断。
        """
        file_vars: Dict[str, str] = {}
        p = Path(path)
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                raw_vars = raw.get("variables", {})
                if isinstance(raw_vars, dict):
                    file_vars = {str(k): str(v) for k, v in raw_vars.items()}
            except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
                logger.warning("全局变量文件读取失败，已忽略: %s (%s)", path, exc)

        merged: Dict[str, str] = {**file_vars, **(initial_variables or {})}
        if len(merged) > max_count:
            logger.warning(
                "合并后变量数量 %d 超过上限 %d，截断处理",
                len(merged), max_count,
            )
            merged = dict(list(merged.items())[:max_count])
        return cls(initial_variables=merged)
