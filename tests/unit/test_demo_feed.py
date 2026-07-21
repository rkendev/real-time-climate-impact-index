"""The demo backfill feeder produces a bounded, consumable, moving history.

The feeder is the only new thing in the refresh's write path, so it is held to
the committed pipeline's own contract: every envelope it publishes passes the
validation gate unchanged, lands on the event-time window it was aimed at, and
carries the coverage it meant to carry. The batch is bounded by the two
configured counts, and the whole series slides forward as the clock advances,
which is what makes the demo read as live rather than static.

Coverage is deliberately uneven: most windows carry both stream types per region
(the top tier), a deterministic minority carries weather only, and the oldest of
those carries a single reading. The tier assertions below run the feeder's output
through the committed validation gate and the committed engine, so what they
check is what ``grade_confidence`` decides from that input. The feeder sets no
grade, and neither does this test.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from climate_index.adapters.memory import MemoryTransport
from climate_index.config import Settings
from climate_index.core.engine import compute_records
from climate_index.core.models import Confidence
from climate_index.core.validation import ValidationGate
from climate_index.core.windowing import assign_window
from feed_history import (
    backfill_envelopes,
    degraded_window_ages,
    positive_int_from_env,
    publish_backfill,
    window_slots,
)

REGIONS = ("EUR", "NAM", "AFR", "ASI")
WINDOW_MINUTES = 30
NOW = datetime(2026, 7, 21, 12, 20, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    return Settings(
        regions=",".join(REGIONS),
        window_minutes=WINDOW_MINUTES,
        _env_file=None,
        **overrides,
    )


def _records(settings: Settings, **kwargs: object) -> list[object]:
    """Run the feeder's output through the committed gate and engine."""
    envelopes = backfill_envelopes(settings, now=NOW, **kwargs)  # type: ignore[arg-type]
    gate = ValidationGate()
    events = [gate.validate(env.model_dump(mode="json")) for env in envelopes]
    assert gate.quarantined_count == 0
    return compute_records([event for event in events if event is not None], settings)


def test_backfill_is_bounded_by_the_configured_counts() -> None:
    settings = _settings()
    envelopes = backfill_envelopes(settings, windows=8, events_per_window=2, now=NOW)

    degraded = degraded_window_ages(8, settings.demo_degraded_window_fraction)
    sparse = max(degraded)
    full = 8 - len(degraded)
    expected = (
        full * 2 * len(REGIONS) * 2  # both stream types at every slot
        + (len(degraded) - 1) * 2 * len(REGIONS)  # weather only
        + len(REGIONS)  # the sparse window: one reading per region
    )
    assert len(envelopes) == expected
    assert sparse == max(degraded)


def test_backfill_covers_the_expected_windows_and_never_stamps_the_future() -> None:
    windows = 4
    envelopes = backfill_envelopes(_settings(), windows=windows, events_per_window=2, now=NOW)

    timestamps = [datetime.fromisoformat(env.payload["ts"]) for env in envelopes]
    assert max(timestamps) <= NOW

    starts = {assign_window(ts, WINDOW_MINUTES)[0] for ts in timestamps}
    current_start, _ = assign_window(NOW, WINDOW_MINUTES)
    span = timedelta(minutes=WINDOW_MINUTES)
    assert starts == {current_start - span * age for age in range(windows)}


def test_coverage_is_full_except_on_the_degraded_minority() -> None:
    settings = _settings()
    windows = 12
    envelopes = backfill_envelopes(settings, windows=windows, events_per_window=2, now=NOW)
    degraded = degraded_window_ages(windows, settings.demo_degraded_window_fraction)
    current_start, _ = assign_window(NOW, WINDOW_MINUTES)
    span = timedelta(minutes=WINDOW_MINUTES)

    seen: dict[tuple[str, datetime], list[str]] = {}
    for envelope in envelopes:
        ts = datetime.fromisoformat(envelope.payload["ts"])
        key = (envelope.key, assign_window(ts, WINDOW_MINUTES)[0])
        seen.setdefault(key, []).append(str(envelope.event_type))

    assert len(seen) == windows * len(REGIONS)  # every region in every window
    for (_, start), types in seen.items():
        age = round((current_start - start) / span)
        if age not in degraded:
            assert set(types) == {"weather", "satellite"}
        elif age == max(degraded):
            assert types == ["weather"]  # a single reading: sparse input
        else:
            assert set(types) == {"weather"}


def test_the_committed_compute_grades_a_mixed_but_top_heavy_snapshot() -> None:
    """The tier mix comes from the pipeline reading varied input, not from here."""
    settings = _settings()
    windows = 12
    records = _records(settings, windows=windows, events_per_window=2)

    grades = Counter(record.confidence for record in records)  # type: ignore[attr-defined]
    assert grades[Confidence.MEASURED] > sum(
        count for grade, count in grades.items() if grade is not Confidence.MEASURED
    )
    assert grades[Confidence.INFERRED] >= len(REGIONS)  # at least one window, every region
    assert grades[Confidence.AMBIGUOUS] >= len(REGIONS)
    assert sum(grades.values()) == windows * len(REGIONS)

    # The window the page leads with is the fully covered one.
    newest = max(record.window_start for record in records)  # type: ignore[attr-defined]
    assert all(
        record.confidence is Confidence.MEASURED  # type: ignore[attr-defined]
        for record in records
        if record.window_start == newest  # type: ignore[attr-defined]
    )


def test_every_region_sees_the_degraded_windows() -> None:
    """A viewer sees the mechanism whichever region they select."""
    settings = _settings()
    records = _records(settings, windows=12, events_per_window=2)

    for region in REGIONS:
        grades = {
            record.confidence  # type: ignore[attr-defined]
            for record in records
            if record.region == region  # type: ignore[attr-defined]
        }
        assert grades == {Confidence.MEASURED, Confidence.INFERRED, Confidence.AMBIGUOUS}


def test_degraded_ages_are_deterministic_and_a_minority() -> None:
    settings = _settings()
    fraction = settings.demo_degraded_window_fraction

    ages = degraded_window_ages(12, fraction)
    assert ages == degraded_window_ages(12, fraction)  # same shape on every refresh
    assert 0 not in ages  # the newest window is never thinned
    assert len(ages) < 12 - len(ages)  # the top tier stays the majority
    assert all(1 <= age < 12 for age in ages)

    # Always at least one, so no snapshot hides the mechanism.
    assert len(degraded_window_ages(2, fraction)) == 1
    assert len(degraded_window_ages(3, 0.01)) == 1
    # No room for a contrast in a single-window backfill, and none is faked.
    assert degraded_window_ages(1, fraction) == ()
    assert degraded_window_ages(12, 0.0) == ()


def test_the_series_advances_with_the_clock() -> None:
    settings = _settings()
    later = NOW + timedelta(minutes=WINDOW_MINUTES)

    def newest(now: datetime) -> datetime:
        envelopes = backfill_envelopes(settings, windows=3, events_per_window=1, now=now)
        return max(
            assign_window(datetime.fromisoformat(env.payload["ts"]), WINDOW_MINUTES)[0]
            for env in envelopes
        )

    assert newest(later) == newest(NOW) + timedelta(minutes=WINDOW_MINUTES)


def test_published_envelopes_all_pass_the_committed_validation_gate() -> None:
    """Thinner coverage never means a malformed event: nothing is quarantined."""
    transport = MemoryTransport()
    envelopes = backfill_envelopes(_settings(), windows=4, events_per_window=2, now=NOW)

    published = publish_backfill(transport, envelopes)
    assert published == len(envelopes) == len(transport)

    gate = ValidationGate()
    for key, value in transport.consume():
        assert key in REGIONS  # region-keyed for partitioning (NFR-S2)
        assert gate.validate(value) is not None
    assert gate.quarantined_count == 0
    assert gate.forwarded_count == len(envelopes)


def test_window_slots_stay_inside_the_window_and_stop_at_the_current_instant() -> None:
    window_start = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    inside = window_slots(window_start, WINDOW_MINUTES, 3, not_after=NOW)
    assert inside == (
        window_start + timedelta(minutes=7.5),
        window_start + timedelta(minutes=15),
        window_start + timedelta(minutes=20),  # capped at NOW, still inside the window
    )
    assert all(assign_window(ts, WINDOW_MINUTES)[0] == window_start for ts in inside)


def test_counts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="windows must be positive"):
        backfill_envelopes(_settings(), windows=0, events_per_window=1, now=NOW)
    with pytest.raises(ValueError, match="events_per_window must be positive"):
        window_slots(NOW, WINDOW_MINUTES, 0, not_after=NOW)


def test_counts_come_from_the_environment_with_a_bounded_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CII_DEMO_WINDOWS", raising=False)
    assert positive_int_from_env("CII_DEMO_WINDOWS", 12) == 12
    monkeypatch.setenv("CII_DEMO_WINDOWS", "6")
    assert positive_int_from_env("CII_DEMO_WINDOWS", 12) == 6
    monkeypatch.setenv("CII_DEMO_WINDOWS", "0")
    with pytest.raises(ValueError, match="must be positive"):
        positive_int_from_env("CII_DEMO_WINDOWS", 12)
