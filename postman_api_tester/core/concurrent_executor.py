"""并发执行引擎。

基于 ThreadPoolExecutor 实现批次内并行执行，配合 BatchScheduler 的分批计划，
在保持变量依赖正确性的前提下最大化并发吞吐。
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, Optional

from postman_api_tester.core.types import ProgressCallback

logger = logging.getLogger(__name__)


class ConcurrentProgressTracker:
    """并发模式下的线程安全进度追踪器。"""

    def __init__(
        self,
        total: int,
        callback: Optional[ProgressCallback],
    ) -> None:
        self._lock = threading.Lock()
        self._completed = 0
        self._total = total
        self._callback = callback

    def on_item_done(
        self,
        name: str,
        method: str,
        url: str,
        status: str,
    ) -> None:
        """报告一个接口执行完成，更新进度并触发回调。"""
        with self._lock:
            self._completed += 1
            completed = self._completed
        if self._callback is None:
            return
        total = self._total
        percent = int(completed * 100 / total) if total > 0 else 100
        try:
            self._callback({
                'stage': 'running',
                'total': total,
                'total_all': total,
                'completed': completed,
                'percent': percent,
                'current_name': name,
                'current_method': method,
                'current_url': url,
                'last_status': status,
            })
        except Exception:
            pass

    @property
    def completed(self) -> int:
        with self._lock:
            return self._completed


def execute_batch_concurrently(
    work_items: List[Any],
    worker_fn: Callable[[Any], Any],
    *,
    max_workers: int,
    on_item_done: Optional[Callable[[Any, Any], None]] = None,
) -> List[Any]:
    """在单批次内并行执行工作项，返回结果列表（保持输入顺序）。

    Args:
        work_items: 当前批次的工作项列表
        worker_fn: 每个工作项的执行函数
        max_workers: 最大线程数
        on_item_done: 每个工作项完成后的回调 (item, result) -> None

    Returns:
        与 work_items 顺序对应的结果列表
    """
    n = len(work_items)
    if n == 0:
        return []

    if n == 1:
        result = worker_fn(work_items[0])
        if on_item_done is not None:
            on_item_done(work_items[0], result)
        return [result]

    effective_workers = min(max_workers, n)
    results: List[Any] = [None] * n
    exceptions: List[BaseException] = []

    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        future_to_idx = {
            pool.submit(worker_fn, item): idx
            for idx, item in enumerate(work_items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results[idx] = result
                if on_item_done is not None:
                    on_item_done(work_items[idx], result)
            except BaseException as exc:
                exceptions.append(exc)
                results[idx] = None

    if exceptions and all(r is None for r in results):
        raise exceptions[0]

    return results
