"""开发导读：
- 职责：按报告名提供写锁，避免并发写回同一报告文件时互相覆盖。
- 入口：get_report_write_lock()。
- 关系：由 meta/patch 等写入服务统一复用。
"""

import threading

from typing import Dict


REPORT_WRITE_LOCKS: Dict[str, threading.RLock] = {}
_REPORT_WRITE_LOCKS_META = threading.Lock()


def get_report_write_lock(report_name: str) -> threading.RLock:
    with _REPORT_WRITE_LOCKS_META:
        if report_name not in REPORT_WRITE_LOCKS:
            REPORT_WRITE_LOCKS[report_name] = threading.RLock()
        return REPORT_WRITE_LOCKS[report_name]