"""report_lock_service 单元测试."""

import threading

import pytest

from postman_api_tester.services.report_lock_service import (
    REPORT_WRITE_LOCKS,
    get_report_write_lock,
)


@pytest.fixture(autouse=True)
def _clear_locks() -> None:
    """在每个测试后清空锁字典，确保隔离性."""
    yield
    REPORT_WRITE_LOCKS.clear()


# ---- get_report_write_lock ----


def _is_rlock(obj: object) -> bool:
    """判断对象是否为 threading 风格的 RLock（可重入锁）."""
    return type(obj).__name__ == "RLock" and hasattr(obj, "acquire") and hasattr(obj, "release")


def test_returns_rlock() -> None:
    """验证返回值是 RLock 实例."""
    lock = get_report_write_lock("rpt1")
    assert _is_rlock(lock)


def test_same_name_returns_same_lock() -> None:
    """同一报告名多次调用返回同一个 RLock 对象."""
    lock_a = get_report_write_lock("rpt1")
    lock_b = get_report_write_lock("rpt1")
    assert lock_a is lock_b


def test_different_names_return_different_locks() -> None:
    """不同报告名返回不同的 RLock 对象."""
    lock_x = get_report_write_lock("rpt_x")
    lock_y = get_report_write_lock("rpt_y")
    assert lock_x is not lock_y


def test_lock_is_reentrant() -> None:
    """验证锁本身支持可重入（RLock 特性）."""
    lock = get_report_write_lock("reentrant")
    # RLock 允许同一线程多次 acquire，不应死锁
    acquired = []
    with lock:
        acquired.append(1)
        with lock:
            acquired.append(2)
            with lock:
                acquired.append(3)
    assert acquired == [1, 2, 3]


def test_empty_string_name() -> None:
    """空字符串作为报告名也能正常工作."""
    lock = get_report_write_lock("")
    assert _is_rlock(lock)


def test_special_characters_in_name() -> None:
    """报告名包含特殊字符时行为正常."""
    name = "report-with/colons: and spaces"
    lock = get_report_write_lock(name)
    assert _is_rlock(lock)
    # 确认已存入字典
    assert name in REPORT_WRITE_LOCKS


def test_concurrent_access_to_get_lock() -> None:
    """多线程同时获取同一名称的锁，不会抛出异常."""
    errors: list[Exception] = []

    def acquire_and_release() -> None:
        try:
            lock = get_report_write_lock("concurrent")
            with lock:
                pass
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=acquire_and_release) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发获取锁时发生异常: {errors}"
