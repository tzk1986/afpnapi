"""Ad-hoc handler concrete implementations."""

"""开发导读：
- 职责：将 ad-hoc 页面输入标准化，并组装为可复用的 Postman Collection v2.1。
- 入口：normalize_adhoc_case()、build_adhoc_collection()。
- 输出：返回可直接落盘并交给统一执行链路的 collection 字典。
- 关系：实际实现已统一到 utils/collection_utils.py，本文件仅负责转发。
"""

from typing import Any, Dict, List, Optional

from postman_api_tester.utils.collection_utils import (
    build_adhoc_collection as build_adhoc_collection,
    normalize_adhoc_case as normalize_adhoc_case,
)


__all__ = ["normalize_adhoc_case", "build_adhoc_collection"]
