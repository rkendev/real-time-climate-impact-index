"""Event-time bucketing tests (UC-3, FR-5, ADR-0002).

Boundaries are a deterministic function of event time: the same events reproduce
the same window keys across replays, an event on a boundary lands in exactly one
bucket, and events in different sub-intervals produce different windows.
"""

from __future__ import annotations

from datetime import UTC, datetime

from climate_index.core.models import WeatherEvent
from climate_index.core.windowing import assign_window


def test_floor_to_window_start() -> None:
    ts = datetime(2026, 7, 19, 12, 15, 30, 500000, tzinfo=UTC)
    start, end = assign_window(ts, 30)
    assert start == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 19, 12, 30, tzinfo=UTC)


def test_boundary_event_opens_its_window() -> None:
    # Half-open [start, end): an event exactly on a boundary belongs to the
    # window that boundary opens, not the one it closes.
    start, end = assign_window(datetime(2026, 7, 19, 12, 30, tzinfo=UTC), 30)
    assert start == datetime(2026, 7, 19, 12, 30, tzinfo=UTC)
    assert end == datetime(2026, 7, 19, 13, 0, tzinfo=UTC)


def test_just_before_boundary_stays_in_prior_window() -> None:
    start, _ = assign_window(datetime(2026, 7, 19, 12, 29, 59, tzinfo=UTC), 30)
    assert start == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def test_events_in_different_subintervals_produce_two_windows() -> None:
    first = assign_window(datetime(2026, 7, 19, 12, 15, tzinfo=UTC), 30)
    second = assign_window(datetime(2026, 7, 19, 12, 45, tzinfo=UTC), 30)
    assert first != second
    assert second[0] == first[1]  # the second window opens where the first closes


def test_window_length_matches_configured_size() -> None:
    start, end = assign_window(datetime(2026, 7, 19, 9, 7, tzinfo=UTC), 45)
    assert (end - start).total_seconds() == 45 * 60


def test_rejects_non_positive_window() -> None:
    try:
        assign_window(datetime(2026, 7, 19, 12, 0, tzinfo=UTC), 0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for a non-positive window")


def test_same_events_yield_same_keys_on_replay() -> None:
    events = [
        WeatherEvent(
            ts=datetime(2026, 7, 19, 12, m, tzinfo=UTC),
            region="EUR",
            temperature_c=15.0,
            rainfall_mm=1.0,
            wind_speed_ms=1.0,
        )
        for m in (5, 20, 35, 50)
    ]
    first_pass = [assign_window(event.ts, 30) for event in events]
    second_pass = [assign_window(event.ts, 30) for event in events]
    assert first_pass == second_pass
    # Two 30-minute buckets over the hour, each seen twice.
    assert len(set(first_pass)) == 2
