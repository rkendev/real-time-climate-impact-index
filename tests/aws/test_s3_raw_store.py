"""S3 raw store: append-only, retrievable JSON audit trail (UC-4, FR-7).

Offline against the moto server, no spend. Append writes a retrievable object, N
appends yield N retrievable records (raw is deliberately not deduplicated), and
the stored body parses back to the event.
"""

from __future__ import annotations

import json
from typing import Any

from climate_index.adapters.aws.s3_raw_store import S3RawStore
from climate_index.interfaces import RawStore

_EVENT = {
    "event_type": "weather",
    "region": "EUR",
    "ts": "2026-07-19T12:15:00+00:00",
    "payload": {"region": "EUR", "temperature_c": 20.0, "rainfall_mm": 3.0},
}


def _store(ctx: Any) -> S3RawStore:
    return S3RawStore(
        bucket=ctx.raw_bucket,
        prefix=ctx.raw_prefix,
        region=ctx.region,
        endpoint_url=ctx.endpoint,
    )


def _list_bodies(ctx: Any) -> list[bytes]:
    import boto3

    client = boto3.client("s3", endpoint_url=ctx.endpoint, region_name=ctx.region)
    listing = client.list_objects_v2(Bucket=ctx.raw_bucket, Prefix=ctx.raw_prefix)
    keys = [obj["Key"] for obj in listing.get("Contents", [])]
    return [client.get_object(Bucket=ctx.raw_bucket, Key=key)["Body"].read() for key in keys]


def test_store_satisfies_protocol(aws_ctx: Any) -> None:
    assert isinstance(_store(aws_ctx), RawStore)


def test_append_writes_retrievable_json(aws_ctx: Any) -> None:
    _store(aws_ctx).append(_EVENT)
    bodies = _list_bodies(aws_ctx)
    assert len(bodies) == 1
    assert json.loads(bodies[0]) == _EVENT


def test_n_appends_yield_n_retrievable_records(aws_ctx: Any) -> None:
    # Raw is append-only and not deduplicated: the same event appended three
    # times yields three distinct objects (FR-7, NFR-R1 applies to the aggregate
    # only).
    store = _store(aws_ctx)
    for _ in range(3):
        store.append(_EVENT)
    bodies = _list_bodies(aws_ctx)
    assert len(bodies) == 3
    assert all(json.loads(body) == _EVENT for body in bodies)


def test_body_parses_back_to_event(aws_ctx: Any) -> None:
    other = {
        "event_type": "satellite",
        "region": "NAM",
        "ts": "2026-07-19T13:00:00+00:00",
        "payload": {"region": "NAM", "cloud_cover_pct": 40.0, "vegetation_index": 0.5},
    }
    _store(aws_ctx).append(other)
    bodies = _list_bodies(aws_ctx)
    assert len(bodies) == 1
    assert json.loads(bodies[0]) == other
