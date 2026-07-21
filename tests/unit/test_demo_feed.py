"""The demo backfill feeder produces a bounded, consumable, moving history.

The feeder is the only new thing in the refresh's write path, so it is held to
the committed pipeline's own contract: every envelope it publishes passes the
validation gate unchanged, lands on the event-time window it was aimed at, and
carries both stream types per region per window (which is what grades a row
MEASURED). The batch is bounded by the two configured counts, and the whole
series slides forward as the clock advances, which is what makes the demo read as
live rather than static.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from climate_index.adapters.memory import MemoryTransport
from climate_index.config import Settings
from climate_index.core.validation import ValidationGate
from climate_index.core.windowing import assign_window
from feed_history import backfill_envelopes, positive_int_from_env, publish_backfill, window_slots

REGIONS = ("EUR", "NAM", "AFR", "ASI")
WINDOW_MINUTES = 30
NOW = datetime(2026, 7, 21, 12, 20, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(regions=",".join(REGIONS), window_minutes=WINDOW_MINUTES)


def test_backfill_is_bounded_by_the_configured_counts() -> None:
    envelopes = backfill_envelopes(_settings(), windows=3, events_per_window=2, now=NOW)
    # windows x events per window x regions x the two stream types.
    assert len(envelopes) == 3 * 2 * len(REGIONS) * 2


def test_backfill_covers_the_expected_windows_and_never_stamps_the_future() -> None:
    windows = 4
    envelopes = backfill_envelopes(_settings(), windows=windows, events_per_window=2, now=NOW)

    timestamps = [datetime.fromisoformat(env.payload["ts"]) for env in envelopes]
    assert max(timestamps) <= NOW

    starts = {assign_window(ts, WINDOW_MINUTES)[0] for ts in timestamps}
    current_start, _ = assign_window(NOW, WINDOW_MINUTES)
    span = timedelta(minutes=WINDOW_MINUTES)
    assert starts == {current_start - span * age for age in range(windows)}


def test_every_region_and_window_carries_both_stream_types() -> None:
    envelopes = backfill_envelopes(_settings(), windows=3, events_per_window=2, now=NOW)

    seen: dict[tuple[str, datetime], set[str]] = {}
    for envelope in envelopes:
        ts = datetime.fromisoformat(envelope.payload["ts"])
        key = (envelope.key, assign_window(ts, WINDOW_MINUTES)[0])
        seen.setdefault(key, set()).add(str(envelope.event_type))

    assert len(seen) == 3 * len(REGIONS)
    assert all(types == {"weather", "satellite"} for types in seen.values())


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
    transport = MemoryTransport()
    envelopes = backfill_envelopes(_settings(), windows=2, events_per_window=2, now=NOW)

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
