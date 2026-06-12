"""请求串联变量上下文。

在 ``_execute_api_suite()`` 生命周期内共享，用于跨接口传递提取的变量。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from postman_api_tester.utils.extract_utils import extract_from_response

logger = logging.getLogger(__name__)


class VariableContext:
    """请求串联变量上下文。

    在同一 suite 执行期间持有所有已提取的变量，供后续接口的 ``{{variable}}`` 替换使用。
    """

    def __init__(self, initial_variables: Optional[Dict[str, str]] = None) -> None:
        self._variables: Dict[str, str] = dict(initial_variables or {})

    @property
    def variables(self) -> Dict[str, str]:
        """返回变量字典副本，防止外部直接修改内部状态。"""
        return dict(self._variables)

    def get(self, name: str, default: str = "") -> str:
        return self._variables.get(name, default)

    def set(self, name: str, value: str) -> None:
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
