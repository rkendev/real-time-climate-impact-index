"""Store-agnostic fan-out: writes both, reads serving, converges on retry (UC-4).

The fan-out logic (writes both stores, reads the serving store, durability leads)
is proven with lightweight in-memory recorders. The partial-failure-then-retry
convergence is proven end to end against the real Iceberg and DynamoDB adapters
under the moto server, so a retry after a serving failure leaves exactly one row
in each store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from climate_index.adapters.aws.dynamo_store import DynamoAggregateStore
from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
from climate_index.adapters.composite import CompositeAggregateStore
from climate_index.interfaces import AggregateStore


class _Recorder:
    """An in-memory AggregateStore that records what it received."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def upsert(self, record: Mapping[str, Any]) -> None:
        self.records.append(dict(record))

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        return [record for record in self.records if record["region"] == region]


class _Boom:
    """An AggregateStore whose upsert always fails."""

    def upsert(self, record: Mapping[str, Any]) -> None:
        raise RuntimeError("durable store down")

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        return []


class _FailOnce:
    """Wrap a store so its first upsert fails, then delegates."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._failed = False

    def upsert(self, record: Mapping[str, Any]) -> None:
        if not self._failed:
            self._failed = True
            raise RuntimeError("serving store transient failure")
        self._inner.upsert(record)

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        return self._inner.read_region_series(region)


def test_composite_satisfies_protocol() -> None:
    composite = CompositeAggregateStore(_Recorder(), _Recorder())
    assert isinstance(composite, AggregateStore)


def test_upsert_writes_both_stores(make_record: Any) -> None:
    durable, serving = _Recorder(), _Recorder()
    CompositeAggregateStore(durable, serving).upsert(make_record(window_hour=12, impact=75.25))
    assert len(durable.records) == 1
    assert len(serving.records) == 1
    assert durable.records[0]["impact_index"] == 75.25
    assert serving.records[0]["impact_index"] == 75.25


def test_read_delegates_to_serving_store(make_record: Any) -> None:
    durable, serving = _Recorder(), _Recorder()
    composite = CompositeAggregateStore(durable, serving)
    composite.upsert(make_record(window_hour=12, impact=75.25))
    # A record only the serving store holds is visible through the composite read;
    # the durable store is not consulted on reads.
    serving.upsert(make_record(window_hour=13, impact=80.0))
    assert len(composite.read_region_series("EUR")) == 2
    assert len(durable.records) == 1


def test_durability_leads_serving_not_written_on_durable_failure(make_record: Any) -> None:
    serving = _Recorder()
    composite = CompositeAggregateStore(_Boom(), serving)
    with pytest.raises(RuntimeError):
        composite.upsert(make_record(window_hour=12, impact=75.25))
    assert serving.records == []


def _iceberg(ctx: Any) -> IcebergAggregateStore:
    return IcebergAggregateStore(
        catalog_properties=ctx.catalog_properties,
        namespace=ctx.namespace,
        table_name=ctx.table_name,
    )


def _dynamo(ctx: Any) -> DynamoAggregateStore:
    return DynamoAggregateStore(
        table_name=ctx.dynamo_table,
        region=ctx.region,
        endpoint_url=ctx.endpoint,
    )


def test_partial_failure_then_retry_converges(aws_ctx: Any, make_record: Any) -> None:
    durable = _iceberg(aws_ctx)
    inner_serving = _dynamo(aws_ctx)
    serving = _FailOnce(inner_serving)
    composite = CompositeAggregateStore(durable, serving)
    record = make_record(window_hour=12, impact=75.25)

    # First attempt: durable write succeeds, serving fails, error surfaces.
    with pytest.raises(RuntimeError):
        composite.upsert(record)
    assert len(durable.read_region_series("EUR")) == 1
    assert len(inner_serving.read_region_series("EUR")) == 0

    # Retry: both writes are idempotent, so this converges to one row in each.
    composite.upsert(dict(record))
    assert len(durable.read_region_series("EUR")) == 1
    assert len(inner_serving.read_region_series("EUR")) == 1
