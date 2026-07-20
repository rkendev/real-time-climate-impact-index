"""NFR-P3: the dashboard read serves a region series under one second at p95.

Seeds at least twenty-four hours of windows into the serving store, then times the
read-only region read (the exact path the dashboard serves) over a sample and
reports the p95. On the DynamoDB serving store this must be under one second
(docs/10_prd.md NFR-P3). The percentile logic is unit-tested offline against moto;
the real p95 is measured in the paid window.

Run in the paid window with the AWS backend configured:
    CII_AGGREGATE_BACKEND=aws python scripts/verify_nfr_p3.py
Exits 0 when the p95 is under one second, 1 when it is not, 2 if the AWS backend is
not configured.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from climate_index.config import get_settings

if TYPE_CHECKING:
    from climate_index.interfaces.store import AggregateStore, ReadOnlyAggregateStore

_WINDOW_MINUTES = 30
# At a 30-minute window, forty-eight windows is a full twenty-four hours, the
# minimum store depth NFR-P3 requires.
_MIN_WINDOWS = 48
_DEFAULT_SAMPLES = 50
_TARGET_SECONDS = 1.0


@dataclass(frozen=True)
class LatencyResult:
    """A measured read latency distribution for one region."""

    samples: int
    p95_seconds: float
    within_target: bool


def percentile(sorted_values: list[float], quantile: float) -> float:
    """Nearest-rank percentile of an already-sorted list (empty list is zero)."""
    if not sorted_values:
        return 0.0
    rank = int(round(quantile * (len(sorted_values) - 1)))
    return sorted_values[min(rank, len(sorted_values) - 1)]


def seed_windows(store: AggregateStore, region: str, count: int = _MIN_WINDOWS) -> int:
    """Write ``count`` consecutive windows for ``region``; return the count."""
    from climate_index.core.models import ClimateIndexRecord, Confidence

    base = datetime(2026, 7, 19, 0, 0, tzinfo=UTC)
    for index in range(count):
        start = base + timedelta(minutes=_WINDOW_MINUTES * index)
        record = ClimateIndexRecord(
            region=region,
            window_start=start,
            window_end=start + timedelta(minutes=_WINDOW_MINUTES),
            impact_index=50.0,
            temperature_anomaly=1.0,
            dryness_index=0.5,
            pollution_index=0.5,
            confidence=Confidence.MEASURED,
        )
        store.upsert(record.model_dump(mode="python"))
    return count


def measure_p95(
    reader: ReadOnlyAggregateStore,
    region: str,
    samples: int = _DEFAULT_SAMPLES,
    *,
    timer: Callable[[], float] = time.perf_counter,
) -> LatencyResult:
    """Time ``samples`` region reads and return the p95 against the one-second target.

    ``timer`` is injected so a test can drive a deterministic distribution without
    depending on wall-clock timing.
    """
    durations: list[float] = []
    for _ in range(samples):
        start = timer()
        reader.read_region_series(region)
        durations.append(timer() - start)
    durations.sort()
    p95 = percentile(durations, 0.95)
    return LatencyResult(samples=samples, p95_seconds=p95, within_target=p95 < _TARGET_SECONDS)


def main() -> int:
    settings = get_settings()
    if settings.aggregate_backend != "aws":
        print(
            "verify_nfr_p3: set CII_AGGREGATE_BACKEND=aws to measure the serving store",
            file=sys.stderr,
        )
        return 2

    from climate_index.store_factory import build_aggregate_store, build_readonly_aggregate_store

    region = settings.region_list[0]
    seed_windows(build_aggregate_store(settings), region)
    result = measure_p95(build_readonly_aggregate_store(settings), region)

    p95_ms = result.p95_seconds * 1000.0
    if not result.within_target:
        print(
            f"NFR-P3 FAILED: p95 {p95_ms:.0f} ms over {result.samples} reads (>= 1000 ms)",
            file=sys.stderr,
        )
        return 1
    print(f"NFR-P3 OK: p95 {p95_ms:.0f} ms over {result.samples} reads for {region} (< 1000 ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
