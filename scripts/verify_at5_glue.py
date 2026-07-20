"""AT-5 against the real Glue catalog: replaying a window yields exactly one row.

Moto never exercises the Glue catalog plane, so this check belongs to the paid
window against real AWS: it upserts the same aggregate record twice through the
Iceberg store (a replay of one window) and asserts the catalog-backed MERGE on the
natural key left exactly one row (FR-6, NFR-R1). The measurement logic is
unit-tested offline against the SQL-catalog fixture; only the against-Glue run is a
paid step.

Run in the paid window with the AWS backend configured:
    CII_AGGREGATE_BACKEND=aws python scripts/verify_at5_glue.py
Exits 0 on the idempotent result, 1 if a replay left more than one row, 2 if the
AWS backend is not configured.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from climate_index.config import get_settings

if TYPE_CHECKING:
    from climate_index.config import Settings
    from climate_index.interfaces.store import AggregateStore

_NaturalKey = tuple[Any, Any, Any]


@dataclass(frozen=True)
class IdempotencyResult:
    """The outcome of a replay: how many rows the natural key holds afterward."""

    region: str
    rows_after_replay: int
    idempotent: bool


def _natural_key(row: Mapping[str, Any]) -> _NaturalKey:
    return (row["region"], row["window_start"], row["window_end"])


def verify_iceberg_idempotent(
    store: AggregateStore, record: Mapping[str, Any]
) -> IdempotencyResult:
    """Upsert the record twice (a replay) and count the rows for its natural key.

    Idempotent means the second upsert produced no duplicate: exactly one row
    carries the natural key after the replay. This is AT-5 stated as a function so
    the paid-window main and the offline fixture test share one assertion.
    """
    region = str(record["region"])
    store.upsert(record)
    store.upsert(record)
    key = _natural_key(record)
    matching = [row for row in store.read_region_series(region) if _natural_key(row) == key]
    return IdempotencyResult(
        region=region,
        rows_after_replay=len(matching),
        idempotent=len(matching) == 1,
    )


def _sample_record(settings: Settings) -> dict[str, Any]:
    """A deterministic aggregate record for the first configured region."""
    from climate_index.core.models import ClimateIndexRecord, Confidence

    region = settings.region_list[0]
    record = ClimateIndexRecord(
        region=region,
        window_start=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 7, 20, 12, 30, tzinfo=UTC),
        impact_index=64.0,
        temperature_anomaly=8.0,
        dryness_index=0.5,
        pollution_index=0.5,
        confidence=Confidence.MEASURED,
    )
    return record.model_dump(mode="python")


def main() -> int:
    settings = get_settings()
    if settings.aggregate_backend != "aws":
        print("verify_at5_glue: set CII_AGGREGATE_BACKEND=aws to run against Glue", file=sys.stderr)
        return 2

    from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore

    store = IcebergAggregateStore.from_settings(settings)
    result = verify_iceberg_idempotent(store, _sample_record(settings))
    if not result.idempotent:
        print(
            f"AT-5 FAILED: replay left {result.rows_after_replay} rows for {result.region}",
            file=sys.stderr,
        )
        return 1
    print(f"AT-5 OK: replaying one window left exactly one Iceberg row for {result.region}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
