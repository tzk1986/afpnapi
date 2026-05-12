import threading

from typing import Dict


REPORT_WRITE_LOCKS: Dict[str, threading.Lock] = {}
_REPORT_WRITE_LOCKS_META = threading.Lock()


def get_report_write_lock(report_name: str) -> threading.Lock:
    with _REPORT_WRITE_LOCKS_META:
        if report_name not in REPORT_WRITE_LOCKS:
            REPORT_WRITE_LOCKS[report_name] = threading.Lock()
        return REPORT_WRITE_LOCKS[report_name]