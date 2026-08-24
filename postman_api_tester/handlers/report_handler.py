"""Report handler — status filter normalization only.

开发导读:
- 职责：状态筛选值归一化（中英文与别名统一）。
- 其他报告展示函数（filter_report_results、paginate_items、compare_report_data）
  已统一至 models.py，由 services/report_results_service.py 消费。
"""

from typing import Optional


def normalize_status_filter(value: str) -> Optional[str]:
    """状态筛选值归一化：支持中英文与别名输入。"""
    normalized = str(value or "").strip().upper()
    if normalized in {"", "ALL", "RESULT", "全部", "结果"}:
        return None
    if normalized in {"PASSED", "SUCCESS", "成功"}:
        return "PASSED"
    if normalized in {"FAILED", "FAIL", "失败"}:
        return "FAILED"
    if normalized in {"ERROR", "错误"}:
        return "ERROR"
    return None


__all__ = [
    "normalize_status_filter",
]
