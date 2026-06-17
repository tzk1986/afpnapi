"""batch_scheduler 单元测试。"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from postman_api_tester.core.batch_scheduler import (
    BatchScheduler,
    extract_consumed_variables,
    extract_produced_variables,
)


def _make_api(
    *,
    name: str = "req",
    url: str = "http://example.com/api",
    headers: Dict[str, str] | None = None,
    params: Dict[str, str] | None = None,
    body: Any = None,
    x_extract: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    api: Dict[str, Any] = {"name": name, "method": "GET", "url": url, "full_url": url}
    if headers:
        api["headers"] = headers
    if params:
        api["params"] = params
    if body is not None:
        api["body"] = body
    if x_extract:
        api["x_extract"] = x_extract
    return api


class TestExtractProducedVariables:

    def test_no_x_extract(self) -> None:
        assert extract_produced_variables({"name": "req"}) == set()

    def test_empty_x_extract(self) -> None:
        assert extract_produced_variables({"name": "req", "x_extract": {}}) == set()

    def test_single_producer(self) -> None:
        result = extract_produced_variables({"x_extract": {"token": "$.data.token"}})
        assert result == {"token"}

    def test_multiple_producers(self) -> None:
        result = extract_produced_variables({
            "x_extract": {"token": "$.data.token", "user_id": "$.data.id"},
        })
        assert result == {"token", "user_id"}

    def test_non_dict_x_extract(self) -> None:
        assert extract_produced_variables({"x_extract": "invalid"}) == set()


class TestExtractConsumedVariables:

    def test_no_variables(self) -> None:
        api = _make_api(url="http://example.com/api")
        assert extract_consumed_variables(api) == set()

    def test_url_variable(self) -> None:
        api = _make_api(url="http://example.com/{{user_id}}/info")
        result = extract_consumed_variables(api)
        assert "user_id" in result

    def test_header_variable(self) -> None:
        api = _make_api(headers={"Authorization": "Bearer {{token}}"})
        result = extract_consumed_variables(api)
        assert "token" in result

    def test_body_variable(self) -> None:
        api = _make_api(body='{"user": "{{username}}"}')
        result = extract_consumed_variables(api)
        assert "username" in result

    def test_params_variable(self) -> None:
        api = _make_api(params={"page": "{{page_num}}"})
        result = extract_consumed_variables(api)
        assert "page_num" in result

    def test_base_url_excluded(self) -> None:
        api = _make_api(url="{{baseUrl}}/api")
        result = extract_consumed_variables(api)
        assert "baseUrl" not in result

    def test_base_url_variant_excluded(self) -> None:
        api = _make_api(url="{{base_url}}/api")
        result = extract_consumed_variables(api)
        assert "base_url" not in result

    def test_nested_body_variables(self) -> None:
        api = _make_api(body={"outer": {"inner": "{{deep_var}}"}})
        result = extract_consumed_variables(api)
        assert "deep_var" in result

    def test_multiple_variables(self) -> None:
        api = _make_api(
            url="http://{{host}}/{{path}}",
            headers={"X-Token": "{{token}}"},
        )
        result = extract_consumed_variables(api)
        assert result == {"host", "path", "token"}


class TestBatchScheduler:

    def test_empty_list(self) -> None:
        scheduler = BatchScheduler([])
        assert scheduler.compute_batches() == []

    def test_single_api(self) -> None:
        apis = [_make_api(name="req1")]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 1
        assert batches[0] == [0]

    def test_no_dependencies_all_in_one_batch(self) -> None:
        apis = [
            _make_api(name="a"),
            _make_api(name="b"),
            _make_api(name="c"),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 1
        assert sorted(batches[0]) == [0, 1, 2]

    def test_linear_chain_three_batches(self) -> None:
        apis = [
            _make_api(name="a", x_extract={"token": "$.token"}),
            _make_api(name="b", url="http://example.com/{{token}}", x_extract={"order_id": "$.id"}),
            _make_api(name="c", url="http://example.com/order/{{order_id}}"),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 3
        assert batches[0] == [0]
        assert batches[1] == [1]
        assert batches[2] == [2]

    def test_independent_and_depend_mixed(self) -> None:
        apis = [
            _make_api(name="a", x_extract={"token": "$.token"}),
            _make_api(name="b"),
            _make_api(name="c"),
            _make_api(name="d", headers={"Authorization": "Bearer {{token}}"}),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 2
        assert sorted(batches[0]) == [0, 1, 2]
        assert batches[1] == [3]

    def test_producer_after_consumer_no_edge(self) -> None:
        apis = [
            _make_api(name="consumer", url="http://example.com/{{token}}"),
            _make_api(name="producer", x_extract={"token": "$.token"}),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 1
        assert sorted(batches[0]) == [0, 1]

    def test_multiple_producers_same_variable(self) -> None:
        apis = [
            _make_api(name="a", x_extract={"token": "$.token"}),
            _make_api(name="b", x_extract={"token": "$.other_token"}),
            _make_api(name="c", headers={"Auth": "{{token}}"}),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 2
        assert sorted(batches[0]) == [0, 1]
        assert batches[1] == [2]

    def test_diamond_dependency(self) -> None:
        apis = [
            _make_api(name="root", x_extract={"base": "$.base"}),
            _make_api(name="left", url="http://{{base}}/left", x_extract={"left_id": "$.id"}),
            _make_api(name="right", url="http://{{base}}/right", x_extract={"right_id": "$.id"}),
            _make_api(name="merge", url="http://{{left_id}}/{{right_id}}"),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        assert len(batches) == 3
        assert batches[0] == [0]
        assert sorted(batches[1]) == [1, 2]
        assert batches[2] == [3]

    def test_all_indices_covered(self) -> None:
        apis = [
            _make_api(name="a", x_extract={"x": "$.x"}),
            _make_api(name="b", url="http://{{x}}/b", x_extract={"y": "$.y"}),
            _make_api(name="c", url="http://{{y}}/c"),
            _make_api(name="d"),
            _make_api(name="e"),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        all_indices = {i for b in batches for i in b}
        assert all_indices == {0, 1, 2, 3, 4}

    def test_batch_order_respects_dependencies(self) -> None:
        apis = [
            _make_api(name="a", x_extract={"v1": "$.v1"}),
            _make_api(name="b", headers={"H": "{{v1}}"}, x_extract={"v2": "$.v2"}),
            _make_api(name="c", params={"p": "{{v2}}"}),
        ]
        scheduler = BatchScheduler(apis)
        batches = scheduler.compute_batches()
        position = {}
        for batch_idx, batch in enumerate(batches):
            for api_idx in batch:
                position[api_idx] = batch_idx
        assert position[0] < position[1]
        assert position[1] < position[2]
