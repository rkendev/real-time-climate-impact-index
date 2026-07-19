"""DuckDB-backed aggregate and raw stores (UC-4, FR-6, FR-7, NFR-R1).

The aggregate store persists one :class:`ClimateIndexRecord` per natural key
``(region, window_start, window_end)`` and is idempotent on that key via
``INSERT OR REPLACE`` on a primary key, so replaying a window overwrites its row
rather than appending a duplicate (AT-5). The raw store appends validated events
for audit and replay (FR-7). Both take their file path from config (INV-1); no
endpoint or secret literal appears here.

This is the local half of the store mapping in ADR-0003: the same interface maps
to an S3 Iceberg MERGE (idempotent aggregate of record) plus a DynamoDB upsert in
the cloud, a Phase 2 adapter swap. The consumer offset-commit-after-write loop
(ADR-0002) is Track H and is deliberately not implemented here.

Timestamps are stored as naive UTC ``TIMESTAMP`` columns (DuckDB reads a
``TIMESTAMP WITH TIME ZONE`` only via an optional dependency we do not pin); UTC
is reattached on read so callers always see timezone-aware UTC datetimes,
consistent with the event models.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

_AGGREGATE_COLUMNS = (
    "region",
    "window_start",
    "window_end",
    "impact_index",
    "temperature_anomaly",
    "dryness_index",
    "pollution_index",
    "confidence",
)


def _to_naive_utc(value: datetime | str) -> datetime:
    """Normalize a datetime or ISO string to a naive UTC datetime for storage."""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.replace(tzinfo=None)


def _to_aware_utc(value: datetime) -> datetime:
    """Reattach UTC to a naive datetime read back from storage."""
    return value.replace(tzinfo=UTC)


class DuckDBAggregateStore:
    """Idempotent aggregate-of-record store keyed on the natural key (FR-6)."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(db_path))
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS climate_index (
                region VARCHAR NOT NULL,
                window_start TIMESTAMP NOT NULL,
                window_end TIMESTAMP NOT NULL,
                impact_index DOUBLE NOT NULL,
                temperature_anomaly DOUBLE NOT NULL,
                dryness_index DOUBLE NOT NULL,
                pollution_index DOUBLE NOT NULL,
                confidence VARCHAR NOT NULL,
                PRIMARY KEY (region, window_start, window_end)
            )
            """
        )

    def upsert(self, record: Mapping[str, Any]) -> None:
        """Insert or replace the row for this natural key (idempotent, AT-5)."""
        values = [
            str(record["region"]),
            _to_naive_utc(record["window_start"]),
            _to_naive_utc(record["window_end"]),
            float(record["impact_index"]),
            float(record["temperature_anomaly"]),
            float(record["dryness_index"]),
            float(record["pollution_index"]),
            str(record["confidence"]),
        ]
        placeholders = ", ".join(["?"] * len(_AGGREGATE_COLUMNS))
        self._con.execute(f"INSERT OR REPLACE INTO climate_index VALUES ({placeholders})", values)

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the region's rows ordered by window start (read-only, INV-2)."""
        columns = ", ".join(_AGGREGATE_COLUMNS)
        result = self._con.execute(
            f"SELECT {columns} FROM climate_index WHERE region = ? ORDER BY window_start",
            [region],
        )
        rows: list[Mapping[str, Any]] = []
        for row in result.fetchall():
            record = dict(zip(_AGGREGATE_COLUMNS, row, strict=True))
            record["window_start"] = _to_aware_utc(record["window_start"])
            record["window_end"] = _to_aware_utc(record["window_end"])
            rows.append(record)
        return rows

    def close(self) -> None:
        self._con.close()


class DuckDBRawStore:
    """Append-only store for validated raw events (FR-7)."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(db_path))
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_events (
                event_type VARCHAR NOT NULL,
                region VARCHAR NOT NULL,
                ts TIMESTAMP NOT NULL,
                payload JSON NOT NULL
            )
            """
        )

    def append(self, event: Mapping[str, Any]) -> None:
        """Append one validated event.

        ``event`` carries ``event_type``, ``region``, ``ts`` (a datetime or ISO
        string), and ``payload`` (the validated event body as a mapping).
        """
        payload = event["payload"]
        self._con.execute(
            "INSERT INTO raw_events VALUES (?, ?, ?, ?)",
            [
                str(event["event_type"]),
                str(event["region"]),
                _to_naive_utc(event["ts"]),
                json.dumps(payload),
            ],
        )

    def count(self) -> int:
        """Return the number of appended raw events (FR-7 audit)."""
        row = self._con.execute("SELECT count(*) FROM raw_events").fetchone()
        return int(row[0]) if row is not None else 0

    def close(self) -> None:
        self._con.close()
