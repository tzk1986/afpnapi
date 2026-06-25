"""concurrent_executor 模块单元测试。

覆盖 ConcurrentProgressTracker 和 execute_batch_concurrently 的正常/边界/异常路径。
"""

import pytest
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

from postman_api_tester.core.concurrent_executor import (
    ConcurrentProgressTracker,
    execute_batch_concurrently,
)


class TestConcurrentProgressTracker:
    """ConcurrentProgressTracker 测试。"""

    def test_initial_completed_is_zero(self):
        """初始 completed 为 0。"""
        tracker = ConcurrentProgressTracker(total=5, callback=None)
        assert tracker.completed == 0

    def test_on_item_done_increments_completed(self):
        """每次 on_item_done 增加 completed。"""
        tracker = ConcurrentProgressTracker(total=5, callback=None)
        tracker.on_item_done("api1", "GET", "/a", "PASSED")
        assert tracker.completed == 1
        tracker.on_item_done("api2", "POST", "/b", "FAILED")
        assert tracker.completed == 2

    def test_on_item_done_calls_callback(self):
        """on_item_done 应调用回调。"""
        payloads: List[Dict[str, Any]] = []

        def callback(payload):
            payloads.append(payload)

        tracker = ConcurrentProgressTracker(total=3, callback=callback)
        tracker.on_item_done("api1", "GET", "/test", "PASSED")

        assert len(payloads) == 1
        p = payloads[0]
        assert p["stage"] == "running"
        assert p["total"] == 3
        assert p["total_all"] == 3
        assert p["completed"] == 1
        assert p["percent"] == 33
        assert p["current_name"] == "api1"
        assert p["current_method"] == "GET"
        assert p["current_url"] == "/test"
        assert p["last_status"] == "PASSED"

    def test_on_item_done_percent_calculation(self):
        """百分比应正确计算。"""
        payloads: List[Dict[str, Any]] = []
        tracker = ConcurrentProgressTracker(total=4, callback=lambda p: payloads.append(p))

        for i in range(4):
            tracker.on_item_done(f"api{i}", "GET", f"/{i}", "PASSED")

        assert payloads[0]["percent"] == 25
        assert payloads[1]["percent"] == 50
        assert payloads[2]["percent"] == 75
        assert payloads[3]["percent"] == 100

    def test_on_item_done_with_zero_total(self):
        """total 为 0 时百分比应为 100。"""
        payloads: List[Dict[str, Any]] = []
        tracker = ConcurrentProgressTracker(total=0, callback=lambda p: payloads.append(p))
        tracker.on_item_done("api", "GET", "/x", "PASSED")
        assert payloads[0]["percent"] == 100

    def test_on_item_done_with_no_callback(self):
        """无回调时 on_item_done 不抛异常。"""
        tracker = ConcurrentProgressTracker(total=5, callback=None)
        tracker.on_item_done("api", "GET", "/x", "PASSED")
        assert tracker.completed == 1

    def test_callback_exception_does_not_break_tracker(self):
        """回调异常不影响 completed 计数。"""
        def bad_callback(payload):
            raise RuntimeError("callback error")

        tracker = ConcurrentProgressTracker(total=3, callback=bad_callback)
        tracker.on_item_done("api1", "GET", "/a", "PASSED")
        tracker.on_item_done("api2", "POST", "/b", "FAILED")
        assert tracker.completed == 2

    def test_thread_safety(self):
        """多线程并发调用 on_item_done 应安全。"""
        tracker = ConcurrentProgressTracker(total=100, callback=None)
        errors: List[Exception] = []

        def worker():
            try:
                for _ in range(10):
                    tracker.on_item_done("api", "GET", "/x", "PASSED")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert tracker.completed == 100

    def test_completed_property_thread_safety(self):
        """completed 属性在多线程下应返回正确值。"""
        tracker = ConcurrentProgressTracker(total=50, callback=None)

        def worker():
            for _ in range(5):
                tracker.on_item_done("api", "GET", "/x", "PASSED")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker.completed == 50


class TestExecuteBatchConcurrently:
    """execute_batch_concurrently 测试。"""

    def test_empty_work_items(self):
        """空工作列表返回空结果。"""
        results = execute_batch_concurrently(
            [],
            lambda x: x,
            max_workers=4,
        )
        assert results == []

    def test_single_item(self):
        """单个工作项直接执行。"""
        results = execute_batch_concurrently(
            [42],
            lambda x: x * 2,
            max_workers=4,
        )
        assert results == [84]

    def test_single_item_calls_on_item_done(self):
        """单个工作项也触发回调。"""
        done_calls: List[tuple] = []

        def on_done(item, result):
            done_calls.append((item, result))

        results = execute_batch_concurrently(
            [10],
            lambda x: x + 5,
            max_workers=4,
            on_item_done=on_done,
        )
        assert results == [15]
        assert len(done_calls) == 1
        assert done_calls[0] == (10, 15)

    def test_preserves_order(self):
        """结果顺序应与输入一致。"""
        results = execute_batch_concurrently(
            [1, 2, 3, 4, 5],
            lambda x: x * 10,
            max_workers=3,
        )
        assert results == [10, 20, 30, 40, 50]

    def test_calls_on_item_done_for_each(self):
        """每个工作项完成后都应触发回调。"""
        done_items: List[int] = []

        def on_done(item, result):
            done_items.append(item)

        execute_batch_concurrently(
            [1, 2, 3],
            lambda x: x,
            max_workers=2,
            on_item_done=on_done,
        )
        assert sorted(done_items) == [1, 2, 3]

    def test_max_workers_capped_to_item_count(self):
        """max_workers 不应超过工作项数量。"""
        results = execute_batch_concurrently(
            [1, 2],
            lambda x: x,
            max_workers=100,
        )
        assert results == [1, 2]

    def test_worker_exception_captured(self):
        """工作项异常应被捕获，不中断其他项。"""
        def flaky_worker(x):
            if x == 3:
                raise ValueError("bad value")
            return x * 2

        results = execute_batch_concurrently(
            [1, 2, 3, 4],
            flaky_worker,
            max_workers=2,
        )
        assert results[0] == 2
        assert results[1] == 4
        assert results[2] is None
        assert results[3] == 8

    def test_all_workers_fail_raises_exception(self):
        """所有工作项失败时抛出首个异常。"""
        def always_fail(x):
            raise RuntimeError(f"fail {x}")

        with pytest.raises(RuntimeError, match="fail"):
            execute_batch_concurrently(
                [1, 2, 3],
                always_fail,
                max_workers=2,
            )

    def test_partial_failure_returns_results(self):
        """部分失败时返回部分结果，不抛异常。"""
        def sometimes_fail(x):
            if x == 2:
                raise ValueError("fail")
            return x

        results = execute_batch_concurrently(
            [1, 2, 3],
            sometimes_fail,
            max_workers=2,
        )
        assert results[0] == 1
        assert results[1] is None
        assert results[2] == 3

    def test_concurrent_execution(self):
        """验证实际并行执行（耗时检查）。"""
        def slow_worker(x):
            time.sleep(0.05)
            return x

        start = time.monotonic()
        results = execute_batch_concurrently(
            list(range(5)),
            slow_worker,
            max_workers=5,
        )
        elapsed = time.monotonic() - start

        assert results == list(range(5))
        # 5 个 0.05s 任务在 5 线程下应约 0.05s 完成（非 0.25s）
        assert elapsed < 0.2

    def test_no_callback(self):
        """不提供 on_item_done 时正常工作。"""
        results = execute_batch_concurrently(
            [1, 2, 3],
            lambda x: x + 1,
            max_workers=2,
        )
        assert results == [2, 3, 4]

    def test_large_batch(self):
        """大批量工作项应正确处理。"""
        n = 100
        results = execute_batch_concurrently(
            list(range(n)),
            lambda x: x * 2,
            max_workers=10,
        )
        assert results == [x * 2 for x in range(n)]
