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

from datetime import UTC, datetime

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
)

# Columns added after the table first shipped, with their DDL type. Existing
# database files predate them, so the store adds each one idempotently on open
# rather than relying on CREATE TABLE IF NOT EXISTS, which does not alter a table
# that already exists. Appended to AGGREGATE_COLUMNS above in the same order.
ADDED_COLUMNS: tuple[tuple[str, str], ...] = (("model_pm25_ugm3", "DOUBLE"),)


def to_naive_utc(value: datetime | str) -> datetime:
    """Normalize a datetime or ISO string to a naive UTC datetime for storage."""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.replace(tzinfo=None)


def to_aware_utc(value: datetime) -> datetime:
    """Reattach UTC to a naive datetime read back from storage."""
    return value.replace(tzinfo=UTC)
