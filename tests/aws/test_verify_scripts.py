"""Offline coverage for the paid-window verification scripts (AT-5, NFR-P3).

The against-Glue and against-DynamoDB runs are inherently paid-window checks, but
their measurement logic is proven here offline: AT-5 idempotency against the SQL
catalog fixture (the same MERGE the Glue run exercises), and the NFR-P3 percentile
math against a deterministic injected timer plus a real moto-backed read. No spend.
"""

from __future__ import annotations

from typing import Any

from climate_index.adapters.aws.dynamo_reader import DynamoReadOnlyAggregateStore
from climate_index.adapters.aws.dynamo_store import DynamoAggregateStore
from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
from verify_at5_glue import IdempotencyResult, verify_iceberg_idempotent
from verify_nfr_p3 import measure_p95, percentile, seed_windows


def test_at5_replay_leaves_exactly_one_row(aws_ctx: Any, make_record: Any) -> None:
    store = IcebergAggregateStore(
        catalog_properties=aws_ctx.catalog_properties,
        namespace=aws_ctx.namespace,
        table_name=aws_ctx.table_name,
    )
    result = verify_iceberg_idempotent(store, make_record(window_hour=9, impact=42.0))
    assert isinstance(result, IdempotencyResult)
    assert result.rows_after_replay == 1
    assert result.idempotent is True


def test_percentile_is_nearest_rank() -> None:
    values = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]
    # Nearest-rank p95 over ten sorted values lands on the last element.
    assert percentile(values, 0.95) == 1.00
    assert percentile(values, 0.5) == 0.50
    assert percentile([], 0.95) == 0.0


def test_measure_p95_uses_injected_timer_and_flags_target(aws_ctx: Any) -> None:
    writer = DynamoAggregateStore(
        table_name=aws_ctx.dynamo_table, region=aws_ctx.region, endpoint_url=aws_ctx.endpoint
    )
    seed_windows(writer, "EUR", count=48)
    reader = DynamoReadOnlyAggregateStore(
        table_name=aws_ctx.dynamo_table, region=aws_ctx.region, endpoint_url=aws_ctx.endpoint
    )

    # A deterministic clock: each read appears to take a fixed 0.2 s, so the p95 is
    # 0.2 s and comfortably under the one-second target. This exercises the timing
    # loop and the target flag without depending on wall-clock jitter.
    ticks = iter(float(n) * 0.2 for n in range(1000))

    def fake_timer() -> float:
        return next(ticks)

    result = measure_p95(reader, "EUR", samples=10, timer=fake_timer)
    assert result.samples == 10
    assert abs(result.p95_seconds - 0.2) < 1e-9
    assert result.within_target is True


def test_measure_p95_reads_seeded_windows_over_real_moto(aws_ctx: Any) -> None:
    # A full read against moto (no injected timer): proves the seeded 24h of windows
    # are actually served through the read-only path the dashboard uses.
    writer = DynamoAggregateStore(
        table_name=aws_ctx.dynamo_table, region=aws_ctx.region, endpoint_url=aws_ctx.endpoint
    )
    seeded = seed_windows(writer, "NAM", count=48)
    reader = DynamoReadOnlyAggregateStore(
        table_name=aws_ctx.dynamo_table, region=aws_ctx.region, endpoint_url=aws_ctx.endpoint
    )
    rows = reader.read_region_series("NAM")
    assert seeded == 48
    assert len(rows) == 48
