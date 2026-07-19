"""End-to-end local smoke on the in-memory path (UC-6, FR-7, FR-10, NFR-O1).

Produces a small batch through a MemoryTransport (no Kafka, local-first), runs
the committed processor, and asserts the pipeline is correct end to end:

* the aggregate store is non-empty, and
* it is duplicate-free (one row per region per event-time window, FR-6), and
* raw counts equal produced minus quarantined counts (FR-7).

A single deterministic malformed message is injected so the quarantine
subtraction in the FR-7 relationship is actually exercised. On success the local
smoke marker is written (the same marker ``scripts/pre_deploy_gate.sh`` checks,
NFR-C1), which is what unlocks the pre-deploy gate. The command exits non-zero on
a broken pipeline (FR-10). Logs are structured and metadata-only: counts,
per-region counts, and window boundaries, never payloads or secrets (NFR-O1,
NFR-O3).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBRawStore
from climate_index.adapters.memory import MemoryTransport
from climate_index.config import get_settings
from climate_index.logging_utils import StructuredLogger, get_logger
from climate_index.processor import process
from climate_index.producer import run_producer

# Default marker path, mirrored from scripts/pre_deploy_gate.sh (CII_SMOKE_MARKER).
# The shell gate and this writer share the same env var and default so the marker
# they agree on is single-sourced by the environment, not duplicated as config.
_DEFAULT_MARKER = ".smoke_ok"


class SmokeError(RuntimeError):
    """Raised when a smoke assertion fails (a broken pipeline)."""


@dataclass(frozen=True)
class SmokeResult:
    """The metadata-only outcome of a smoke run (counts only)."""

    produced: int
    consumed: int
    quarantined: int
    raw_count: int
    aggregate_rows: int
    marker_path: str


def _marker_path() -> Path:
    return Path(os.environ.get("CII_SMOKE_MARKER", _DEFAULT_MARKER))


def run_smoke(*, ticks: int = 3, logger: StructuredLogger | None = None) -> SmokeResult:
    """Run the in-memory pipeline, assert correctness, and write the marker.

    Raises :class:`SmokeError` if the aggregate store is empty, holds a duplicate
    natural key, or the FR-7 raw relationship does not hold. On success writes the
    marker and returns the run counts.
    """
    settings = get_settings()
    log = logger if logger is not None else get_logger("smoke")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        transport = MemoryTransport()
        produced = run_producer(transport, ticks=ticks, logger=log)
        # Inject one deterministic malformed message so the quarantine path (and
        # the FR-7 subtraction) is exercised, not merely asserted to be zero.
        malformed = {"event_type": "storm", "key": "EUR", "payload": {"region": "EUR"}}
        transport.publish("EUR", malformed)

        aggregate_store = DuckDBAggregateStore(tmp_dir / "aggregates.duckdb")
        raw_store = DuckDBRawStore(tmp_dir / "raw_events.duckdb")
        try:
            run = process(transport, aggregate_store, raw_store, settings, logger=log)

            all_rows: list[Mapping[str, Any]] = []
            for region in settings.region_list:
                rows = aggregate_store.read_region_series(region)
                for row in rows:
                    log.event(
                        "window",
                        region=region,
                        window_start=row["window_start"],
                        window_end=row["window_end"],
                        impact_index=row["impact_index"],
                    )
                all_rows.extend(rows)

            if not all_rows:
                raise SmokeError("aggregate store is empty after a smoke run")

            keys = [(row["region"], row["window_start"], row["window_end"]) for row in all_rows]
            if len(keys) != len(set(keys)):
                raise SmokeError("aggregate store holds duplicate natural keys (FR-6)")

            expected_raw = run.consumed - run.quarantined
            raw_count = raw_store.count()
            if raw_count != expected_raw:
                raise SmokeError(
                    f"raw count {raw_count} != produced minus quarantined {expected_raw} (FR-7)"
                )

            result = SmokeResult(
                produced=produced,
                consumed=run.consumed,
                quarantined=run.quarantined,
                raw_count=raw_count,
                aggregate_rows=len(all_rows),
                marker_path=str(_marker_path()),
            )
        finally:
            aggregate_store.close()
            raw_store.close()

    marker = _marker_path()
    marker.write_text("ok\n", encoding="utf-8")

    log.event(
        "smoke_ok",
        produced=result.produced,
        consumed=result.consumed,
        quarantined=result.quarantined,
        raw_count=result.raw_count,
        aggregate_rows=result.aggregate_rows,
        marker=result.marker_path,
    )
    return result


def main() -> None:
    """Entry point for ``make smoke``; exits non-zero on a broken pipeline (FR-10)."""
    settings = get_settings()
    log = get_logger("smoke", _log_level(settings.log_level))
    try:
        run_smoke(logger=log)
    except Exception as exc:  # noqa: BLE001 - report any failure as a red smoke, exit non-zero
        log.event("smoke_failed", error=type(exc).__name__, level=logging.ERROR)
        sys.exit(1)


def _log_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)


if __name__ == "__main__":
    main()
