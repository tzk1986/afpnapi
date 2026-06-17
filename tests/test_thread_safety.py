"""线程安全单元测试。"""

from __future__ import annotations

import threading
from typing import Any, Dict, List

import pytest

from postman_api_tester.core.concurrent_executor import (
    ConcurrentProgressTracker,
    execute_batch_concurrently,
)
from postman_api_tester.core.variable_context import VariableContext
from postman_api_tester.postman_api_tester import PostmanTestReport


class TestPostmanTestReportThreadSafety:

    def test_concurrent_add_result_no_data_loss(self) -> None:
        report = PostmanTestReport()
        num_threads = 20
        items_per_thread = 50

        def add_items(thread_id: int) -> None:
            for i in range(items_per_thread):
                report.add_result({
                    'name': f'req_{thread_id}_{i}',
                    'status': 'PASSED',
                    'method': 'GET',
                    'url': 'http://example.com',
                    'actual_request_url': 'http://example.com',
                    'item_path': [thread_id, i],
                    'expected_status': 200,
                    'message': '',
                    'err_code': '',
                    'status_code': 200,
                    'folder': '',
                    'response_time_ms': 10,
                    'request_info': {'headers': {}, 'params': {}, 'body': None},
                    'response_info': {'headers': {}, 'body': ''},
                    'assertion_results': [],
                    'assertion_engine_error': '',
                    'data_index': 0,
                    'extracted_variables': {},
                })

        threads = [threading.Thread(target=add_items, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(report.results) == num_threads * items_per_thread

    def test_concurrent_add_results_batch(self) -> None:
        report = PostmanTestReport()
        num_threads = 10

        def add_batch(thread_id: int) -> None:
            batch = [{
                'name': f'req_{thread_id}_{i}',
                'status': 'PASSED',
                'method': 'GET',
                'url': '',
                'actual_request_url': '',
                'item_path': [],
                'expected_status': 200,
                'message': '',
                'err_code': '',
                'status_code': 200,
                'folder': '',
                'response_time_ms': 0,
                'request_info': {'headers': {}, 'params': {}, 'body': None},
                'response_info': {'headers': {}, 'body': ''},
                'assertion_results': [],
                'assertion_engine_error': '',
                'data_index': 0,
                'extracted_variables': {},
            } for i in range(20)]
            report.add_results(batch)

        threads = [threading.Thread(target=add_batch, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(report.results) == num_threads * 20


class TestVariableContextThreadSafety:

    def test_concurrent_set_and_get(self) -> None:
        ctx = VariableContext()
        num_threads = 20

        def set_vars(thread_id: int) -> None:
            for i in range(50):
                ctx.set(f"var_{thread_id}_{i}", f"value_{thread_id}_{i}")

        threads = [threading.Thread(target=set_vars, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_vars = ctx.variables
        assert len(all_vars) == num_threads * 50

    def test_concurrent_update_from_extract(self) -> None:
        ctx = VariableContext()
        num_threads = 10

        def extract_vars(thread_id: int) -> None:
            extract_config = {
                f"token_{thread_id}": "$.token",
                f"id_{thread_id}": "$.id",
            }
            response_data = {"token": f"t{thread_id}", "id": f"i{thread_id}"}
            ctx.update_from_extract(extract_config, response_data, {})

        threads = [threading.Thread(target=extract_vars, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_vars = ctx.variables
        for t in range(num_threads):
            assert ctx.get(f"token_{t}") == f"t{t}"
            assert ctx.get(f"id_{t}") == f"i{t}"

    def test_variables_returns_snapshot(self) -> None:
        ctx = VariableContext({"a": "1"})
        snapshot = ctx.variables
        ctx.set("b", "2")
        assert "b" not in snapshot


class TestConcurrentProgressTracker:

    def test_concurrent_progress_counting(self) -> None:
        events: List[Dict[str, Any]] = []
        lock = threading.Lock()

        def callback(payload: Dict[str, Any]) -> None:
            with lock:
                events.append(payload)

        tracker = ConcurrentProgressTracker(total=100, callback=callback)
        num_threads = 10

        def report_done(thread_id: int) -> None:
            for i in range(10):
                tracker.on_item_done(f"req_{thread_id}_{i}", "GET", "/api", "PASSED")

        threads = [threading.Thread(target=report_done, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker.completed == 100
        assert len(events) == 100

    def test_no_callback_no_error(self) -> None:
        tracker = ConcurrentProgressTracker(total=10, callback=None)
        tracker.on_item_done("req", "GET", "/api", "PASSED")
        assert tracker.completed == 1

    def test_none_callback_completed_still_tracks(self) -> None:
        tracker = ConcurrentProgressTracker(total=5, callback=None)
        for i in range(5):
            tracker.on_item_done(f"r{i}", "GET", "/", "PASSED")
        assert tracker.completed == 5


class TestExecuteBatchConcurrently:

    def test_basic_parallel_execution(self) -> None:
        results = execute_batch_concurrently(
            [1, 2, 3, 4, 5],
            lambda x: x * 2,
            max_workers=3,
        )
        assert results == [2, 4, 6, 8, 10]

    def test_preserves_order(self) -> None:
        import time
        def slow_fn(x: int) -> int:
            time.sleep(0.01 * (5 - x))
            return x

        results = execute_batch_concurrently(
            [1, 2, 3, 4, 5],
            slow_fn,
            max_workers=5,
        )
        assert results == [1, 2, 3, 4, 5]

    def test_on_item_done_callback(self) -> None:
        done_items: List[int] = []

        def on_done(item: int, result: int) -> None:
            done_items.append(item)

        execute_batch_concurrently(
            [10, 20, 30],
            lambda x: x + 1,
            max_workers=2,
            on_item_done=on_done,
        )
        assert sorted(done_items) == [10, 20, 30]

    def test_empty_list(self) -> None:
        results = execute_batch_concurrently([], lambda x: x, max_workers=3)
        assert results == []

    def test_single_item(self) -> None:
        results = execute_batch_concurrently([42], lambda x: x * 2, max_workers=3)
        assert results == [84]

    def test_exception_in_single_item(self) -> None:
        def failing_fn(x: int) -> int:
            raise ValueError(f"fail: {x}")

        with pytest.raises(ValueError, match="fail"):
            execute_batch_concurrently([1], failing_fn, max_workers=1)

    def test_partial_failure_returns_none(self) -> None:
        def maybe_fail(x: int) -> int:
            if x == 2:
                raise ValueError("fail")
            return x

        results = execute_batch_concurrently(
            [1, 2, 3],
            maybe_fail,
            max_workers=3,
        )
        assert results[0] == 1
        assert results[1] is None
        assert results[2] == 3
