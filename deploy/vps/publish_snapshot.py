#!/usr/bin/env python3
"""Atomic publish of a refreshed demo snapshot (the reader/writer safety rule).

A refresh rebuilds the whole snapshot in a staging directory and this step moves
it over the served path with a single rename. That is what lets an always-on
dashboard and a periodic writer share one file safely:

* the writer only ever holds the staging database, so the DuckDB single-writer
  lock is never taken on the file the dashboard opens;
* the reader only ever opens the served path, read-only, per render, so it sees
  either the whole previous snapshot or the whole new one, never a half-written
  file (``os.replace`` is atomic within a filesystem, and an already-open handle
  keeps reading the snapshot it opened);
* a refresh that fails anywhere before this step publishes nothing, so the last
  good snapshot keeps serving.

Before the rename the staging snapshot is verified through the same read-only
factory the dashboard reads with (:func:`build_readonly_aggregate_store`), so what
is checked is exactly what will be served: every configured region present, the
natural keys unique (FR-6), and no write-ahead log left behind by a writer that
did not close cleanly.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from climate_index.config import Settings, get_settings
from climate_index.store_factory import build_readonly_aggregate_store, close_if_supported


class SnapshotError(RuntimeError):
    """A staging snapshot is not fit to serve, so nothing is published."""


@dataclass(frozen=True)
class SnapshotSummary:
    """What the verified snapshot contains (counts and boundaries only, NFR-O3)."""

    rows: int
    regions: tuple[str, ...]
    newest_window_start: datetime


def write_ahead_log(db_path: Path) -> Path:
    """Return the write-ahead log path DuckDB keeps beside an open database."""
    return db_path.with_name(db_path.name + ".wal")


def verify_snapshot(staging: Path, settings: Settings) -> SnapshotSummary:
    """Verify the staging snapshot through the dashboard read path, or raise."""
    if not staging.is_file():
        raise SnapshotError(f"staging snapshot missing: {staging}")
    if write_ahead_log(staging).exists():
        raise SnapshotError(
            f"staging snapshot has a write-ahead log (writer not closed): {staging}"
        )

    store = build_readonly_aggregate_store(
        settings.model_copy(update={"aggregate_store_path": staging})
    )
    try:
        rows: list[Mapping[str, Any]] = []
        for region in settings.region_list:
            series = store.read_region_series(region)
            if not series:
                raise SnapshotError(f"staging snapshot has no rows for region {region}")
            rows.extend(series)
    finally:
        close_if_supported(store)

    keys = [(row["region"], row["window_start"], row["window_end"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise SnapshotError("staging snapshot has duplicate natural keys (FR-6)")

    return SnapshotSummary(
        rows=len(rows),
        regions=settings.region_list,
        newest_window_start=max(row["window_start"] for row in rows),
    )


def publish_snapshot(staging: Path, served: Path, settings: Settings) -> SnapshotSummary:
    """Verify the staging snapshot, then rename it over the served path."""
    summary = verify_snapshot(staging, settings)
    served.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, served)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, required=True, help="Freshly built snapshot.")
    parser.add_argument("--served", type=Path, required=True, help="Path the dashboard reads.")
    args = parser.parse_args(argv)

    try:
        summary = publish_snapshot(args.staging, args.served, get_settings())
    except SnapshotError as err:
        print(f"snapshot not published: {err}")
        return 1
    print(
        f"published rows={summary.rows} regions={len(summary.regions)} "
        f"newest_window_start={summary.newest_window_start.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
