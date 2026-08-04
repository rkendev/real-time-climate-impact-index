"""Shared DuckDB aggregate schema and timestamp helpers (single source).

The aggregate column order and the naive-UTC/aware-UTC conversions are used by
both the read-write store (:mod:`climate_index.adapters.duckdb.store`) and the
read-only reader (:mod:`climate_index.adapters.duckdb.reader`). They live here so
neither the constant nor the conversions are duplicated: the read-only reader can
share them without importing the writer module (INV-2, AT-6).

Timestamps are stored as naive UTC ``TIMESTAMP`` columns (DuckDB reads a
``TIMESTAMP WITH TIME ZONE`` only via an optional dependency we do not pin); UTC
is reattached on read so callers always see timezone-aware UTC datetimes,
consistent with the event models.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from climate_index.core.models import PM25DisagreementState, ProvenanceTier

AGGREGATE_COLUMNS = (
    "region",
    "window_start",
    "window_end",
    "impact_index",
    "temperature_anomaly",
    "dryness_index",
    "pollution_index",
    "confidence",
    "model_pm25_ugm3",
    "pm25_disagreement",
    "provenance_tier",
    "flagged_city_count",
    "covered_city_count",
    "city_comparisons",
)

# Columns added after the table first shipped, with their DDL type. Existing
# database files predate them, so the store adds each one idempotently on open
# rather than relying on CREATE TABLE IF NOT EXISTS, which does not alter a table
# that already exists. Appended to AGGREGATE_COLUMNS above in the same order.
#
# All additive, and none of them touches the natural key: the key stays
# (region, window_start, window_end) and the INSERT OR REPLACE still matches on
# it, so a replay overwrites as before. city_comparisons is one JSON column
# rather than a second table, because a table would mean a second natural key and
# therefore a second idempotency proof, which the frozen scope does not admit.
ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("model_pm25_ugm3", "DOUBLE"),
    ("pm25_disagreement", "VARCHAR"),
    ("provenance_tier", "VARCHAR"),
    ("flagged_city_count", "INTEGER"),
    ("covered_city_count", "INTEGER"),
    ("city_comparisons", "JSON"),
)


def legacy_states(record: dict[str, Any]) -> dict[str, Any]:
    """Map a row written before E-10 and E-11 existed onto the two documented states.

    The single place the legacy mapping happens on this store, so it is visible
    rather than spread through the readers. A row from before reconciliation
    existed reads back NULL, and NULL means the window was never compared and its
    coverage was never examined. That is exactly what NOT_COMPARED and UNCHECKED
    say, so the mapping states the truth about an old row rather than inventing a
    grade for it.

    This is deliberately not a model default. A default would make "never
    reconciled" and "reconciled and found not comparable" the same value
    everywhere, and telling those apart is what the no-inherited-grade rule needs
    (NFR-DQ4).
    """
    if record.get("pm25_disagreement") is None:
        record["pm25_disagreement"] = PM25DisagreementState.NOT_COMPARED
    if record.get("provenance_tier") is None:
        record["provenance_tier"] = ProvenanceTier.UNCHECKED
    if record.get("flagged_city_count") is None:
        record["flagged_city_count"] = 0
    if record.get("covered_city_count") is None:
        record["covered_city_count"] = 0
    raw = record.get("city_comparisons")
    record["city_comparisons"] = tuple(json.loads(raw)) if isinstance(raw, str) else ()
    return record


def to_naive_utc(value: datetime | str) -> datetime:
    """Normalize a datetime or ISO string to a naive UTC datetime for storage."""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.replace(tzinfo=None)


def to_aware_utc(value: datetime) -> datetime:
    """Reattach UTC to a naive datetime read back from storage."""
    return value.replace(tzinfo=UTC)
