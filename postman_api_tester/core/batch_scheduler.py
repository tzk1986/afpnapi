"""依赖感知的分批调度器。

分析接口列表中的变量生产/消费关系，将无依赖的接口分为同一批次并行执行，
有依赖的接口按拓扑顺序分批。当 ENABLE_VARIABLE_EXTRACTION=False 时，
所有接口无依赖，全部放入同一批次。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List, Set

from postman_api_tester.parser import ApiConfig
from postman_api_tester.utils.variable_substitution import (
    _BASE_URL_VARIABLES,
    extract_referenced_variables,
)

logger = logging.getLogger(__name__)


def extract_produced_variables(api: ApiConfig) -> Set[str]:
    """提取接口通过 x_extract 产出的变量名集合。"""
    raw_extract = api.get("x_extract")
    if not isinstance(raw_extract, dict):
        return set()
    return {k for k in raw_extract if isinstance(k, str)}


def _collect_strings(obj: Any, accumulator: List[str]) -> None:
    """递归收集对象中的所有字符串值。"""
    if isinstance(obj, str):
        accumulator.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, accumulator)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, accumulator)


def extract_consumed_variables(api: ApiConfig) -> Set[str]:
    """提取接口在 URL/headers/params/body 中引用的变量名集合。"""
    refs: Set[str] = set()
    targets: List[str] = []

    if "url" in api:
        targets.append(str(api["url"]))
    if "full_url" in api:
        targets.append(str(api["full_url"]))

    raw_headers = api.get("headers")
    if isinstance(raw_headers, dict):
        for k, v in raw_headers.items():
            targets.append(str(k))
            targets.append(str(v))

    raw_params = api.get("params")
    if isinstance(raw_params, dict):
        for pk, pv in raw_params.items():
            targets.append(str(pk))
            if isinstance(pv, str):
                targets.append(pv)

    body = api.get("body")
    if isinstance(body, str):
        targets.append(body)
    elif isinstance(body, (dict, list)):
        _collect_strings(body, targets)

    for target in targets:
        refs |= extract_referenced_variables(target)

    return refs - _BASE_URL_VARIABLES


class BatchScheduler:
    """分析接口变量依赖，输出可并行执行的分批计划。"""

    def __init__(self, apis: List[ApiConfig]) -> None:
        self._apis = apis

    def compute_batches(self) -> List[List[int]]:
        """返回批次列表，每批是接口索引列表，批次间必须串行。

        算法：
        1. 构建 producer_map: {变量名: 产出该变量的接口索引集合}
        2. 构建 consumer_deps: {接口索引: 依赖的变量名集合}
        3. 拓扑排序分层：同一层内的接口可并行
        """
        n = len(self._apis)
        if n == 0:
            return []

        producer_map: Dict[str, List[int]] = {}
        consumer_deps: Dict[int, Set[str]] = {}

        for idx, api in enumerate(self._apis):
            produced = extract_produced_variables(api)
            for var_name in produced:
                producer_map.setdefault(var_name, []).append(idx)

            consumed = extract_consumed_variables(api)
            if consumed:
                consumer_deps[idx] = consumed

        edges: Dict[int, Set[int]] = {i: set() for i in range(n)}
        in_degree: Dict[int, int] = {i: 0 for i in range(n)}

        for consumer_idx, deps in consumer_deps.items():
            for var_name in deps:
                for producer_idx in producer_map.get(var_name, []):
                    if producer_idx < consumer_idx and consumer_idx not in edges[producer_idx]:
                        edges[producer_idx].add(consumer_idx)
                        in_degree[consumer_idx] += 1

        queue: deque[int] = deque()
        for i in range(n):
            if in_degree[i] == 0:
                queue.append(i)

        batches: List[List[int]] = []
        while queue:
            batch = sorted(queue)
            batches.append(batch)
            next_queue: deque[int] = deque()
            for node in batch:
                for neighbor in edges[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        if sum(len(b) for b in batches) < n:
            logger.warning(
                "检测到循环依赖，%d 个接口无法分批，降级为全串行执行。",
                n - sum(len(b) for b in batches),
            )
            missing = set(range(n)) - {i for b in batches for i in b}
            if missing:
                batches.append(sorted(missing))

        return batches
