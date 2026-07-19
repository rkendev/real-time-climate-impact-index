"""Read-only DuckDB aggregate reader for the dashboard (UC-5, INV-2, NFR-SEC3).

The dashboard serves the aggregate store through this reader alone. The
connection is opened ``read_only=True`` so the process holds no write capability,
and the class exposes only :meth:`read_region_series` and :meth:`close`: there is
no ``upsert`` or ``append`` here, and this module imports no writer and no index
compute path. That is what makes the dashboard strictly read-only (INV-2, AT-6).

The aggregate column order and the UTC reattachment are shared through
:mod:`climate_index.adapters.duckdb._schema`, so this reader duplicates neither
the schema constant nor the store's writer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb

from climate_index.adapters.duckdb._schema import AGGREGATE_COLUMNS, to_aware_utc


class DuckDBReadOnlyAggregateStore:
    """Read-only view of the aggregate store, keyed for per-region series reads."""

    def __init__(self, db_path: Path) -> None:
        # read_only=True opens without any write capability and requires the
        # database file to already exist (seeded by the processor). A dashboard
        # never creates the store; it only reads what a run produced.
        self._con = duckdb.connect(str(db_path), read_only=True)

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the region's rows ordered by window start (read-only, INV-2)."""
        columns = ", ".join(AGGREGATE_COLUMNS)
        result = self._con.execute(
            f"SELECT {columns} FROM climate_index WHERE region = ? ORDER BY window_start",
            [region],
        )
        rows: list[Mapping[str, Any]] = []
        for row in result.fetchall():
            record = dict(zip(AGGREGATE_COLUMNS, row, strict=True))
            record["window_start"] = to_aware_utc(record["window_start"])
            record["window_end"] = to_aware_utc(record["window_end"])
            rows.append(record)
        return rows

    def close(self) -> None:
        self._con.close()
