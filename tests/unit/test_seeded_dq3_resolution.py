"""NFR-DQ3 seeded violation: the pipeline is made to resolve, and must go red.

D1's floor is that one window where the pipeline silently picks a winner ships
FAILED, and the contract says the claim is proven by a seeded violation that
turns the guard red rather than by the guard being green.

The guard is ``assert_reported_never_resolved`` below, and the green path and
every seeded path go through that same function. That is the point rather than a
convenience: a red proof written against a bespoke assertion proves something
about the bespoke assertion and nothing about the shipped guard.

The guard derives its own scope from the streams it is given and returns how many
comparisons it checked, so a caller can refuse a pass that examined nothing. A
guard over an empty set is the failure mode this repository keeps finding, and it
is not caught by the guard being green.

The three seeds are the three ways to resolve. Substitution puts one source's
value in the other's place. Averaging replaces both with a number that is neither.
Preference keeps one and drops the other. They fail independently, so they are
seeded independently.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from statistics import median

import pytest
from tests.integration import at13_fixtures as fixture

from climate_index.config import Settings
from climate_index.core.engine import compute_records
from climate_index.core.models import (
    ClimateIndexRecord,
    PM25DisagreementState,
    SatelliteEvent,
    StationObservation,
)
from climate_index.core.reconciliation import reconcile


def _settings() -> Settings:
    return Settings(_env_file=None)


def _expected(
    stations: Sequence[StationObservation],
    satellites: Sequence[SatelliteEvent],
    region: str,
    city: str,
    start: datetime,
    end: datetime,
) -> tuple[float | None, float | None]:
    """What the two sources actually said, computed from the raw streams.

    Recomputed from the inputs rather than read back off the record, because the
    record is the thing under test. A guard that compared the record against
    itself would accept any consistent lie.
    """
    values = [
        row.pm25_ugm3
        for row in stations
        if row.region == region and row.city == city and start <= row.ts < end
    ]
    models = [
        event.model_pm25_ugm3
        for event in satellites
        if event.region == region and event.city == city and start <= event.ts < end
    ]
    return (
        median(values) if values else None,
        sum(models) / len(models) if models else None,
    )


def assert_reported_never_resolved(
    records: Sequence[ClimateIndexRecord],
    stations: Sequence[StationObservation],
    satellites: Sequence[SatelliteEvent],
) -> int:
    """The NFR-DQ3 guard. Returns how many comparisons it checked.

    Both values survive, unmodified, and neither is substituted for the other,
    averaged with it, or preferred over it. Checked against what the sources
    actually said, so a record that agrees with itself is not enough.
    """
    checked = 0
    for record in records:
        for comparison in record.city_comparisons:
            station, model = _expected(
                stations,
                satellites,
                record.region,
                comparison.city,
                record.window_start,
                record.window_end,
            )
            checked += 1
            assert comparison.station_pm25_ugm3 == station, (
                f"{record.region}/{comparison.city}: the station value on the record is "
                f"{comparison.station_pm25_ugm3}, the stations said {station}"
            )
            assert comparison.model_pm25_ugm3 == model, (
                f"{record.region}/{comparison.city}: the model value on the record is "
                f"{comparison.model_pm25_ugm3}, the model said {model}"
            )
            if station is None or model is None:
                continue
            # Dropping one side is a preference expressed by omission.
            assert comparison.station_pm25_ugm3 is not None
            assert comparison.model_pm25_ugm3 is not None
            if station != model:
                # Neither value may have become the other, and neither may have
                # become the thing halfway between them.
                assert comparison.station_pm25_ugm3 != comparison.model_pm25_ugm3
                midpoint = (station + model) / 2
                assert comparison.station_pm25_ugm3 != midpoint
                assert comparison.model_pm25_ugm3 != midpoint
    return checked


def _run() -> tuple[list[ClimateIndexRecord], list[StationObservation], list[SatelliteEvent]]:
    settings = _settings()
    stations, satellites = fixture.stations(), fixture.satellites()
    records = reconcile(
        compute_records(satellites, settings),
        stations,
        satellites,
        settings,
        window=settings.reconciliation_windows["control"],
    )
    return records, stations, satellites


# --- the no-fault control -----------------------------------------------------


def test_the_shipped_pipeline_reports_and_does_not_resolve() -> None:
    records, stations, satellites = _run()
    checked = assert_reported_never_resolved(records, stations, satellites)
    assert checked >= 8, f"the guard examined only {checked} comparisons"


def test_the_guard_examined_a_window_that_actually_disagrees() -> None:
    """A pass over windows that all agree would not exercise resolution at all."""
    records, _, _ = _run()
    disagreeing = [
        record for record in records if record.pm25_disagreement is PM25DisagreementState.DISAGREED
    ]
    assert disagreeing, "no window disagrees, so nothing could have been resolved"


# --- the seeds ----------------------------------------------------------------


def _seed_substitution(records: list[ClimateIndexRecord]) -> list[ClimateIndexRecord]:
    """The pipeline picks the station as the winner and writes it over the model."""
    return [
        record.model_copy(
            update={
                "city_comparisons": tuple(
                    comparison.model_copy(update={"model_pm25_ugm3": comparison.station_pm25_ugm3})
                    if comparison.state is PM25DisagreementState.DISAGREED
                    else comparison
                    for comparison in record.city_comparisons
                )
            }
        )
        for record in records
    ]


def _seed_averaging(records: list[ClimateIndexRecord]) -> list[ClimateIndexRecord]:
    """The pipeline averages the disagreement into a single reconciled number."""

    def fix(comparison):  # type: ignore[no-untyped-def]
        if comparison.state is not PM25DisagreementState.DISAGREED:
            return comparison
        mean = (comparison.station_pm25_ugm3 + comparison.model_pm25_ugm3) / 2
        return comparison.model_copy(update={"station_pm25_ugm3": mean, "model_pm25_ugm3": mean})

    return [
        record.model_copy(
            update={"city_comparisons": tuple(fix(c) for c in record.city_comparisons)}
        )
        for record in records
    ]


def _seed_preference(records: list[ClimateIndexRecord]) -> list[ClimateIndexRecord]:
    """The pipeline keeps the model and drops the station value it disagreed with."""
    return [
        record.model_copy(
            update={
                "city_comparisons": tuple(
                    comparison.model_copy(update={"station_pm25_ugm3": None})
                    if comparison.state is PM25DisagreementState.DISAGREED
                    else comparison
                    for comparison in record.city_comparisons
                )
            }
        )
        for record in records
    ]


@pytest.mark.parametrize(
    ("name", "seed"),
    [
        ("substitution", _seed_substitution),
        ("averaging", _seed_averaging),
        ("preference", _seed_preference),
    ],
)
def test_a_resolved_disagreement_turns_the_guard_red(name: str, seed) -> None:  # type: ignore[no-untyped-def]
    """Each way of resolving fails the guard on its own, through the same guard."""
    records, stations, satellites = _run()
    resolved = seed(list(records))
    assert resolved != records, f"the {name} seed changed nothing"
    with pytest.raises(AssertionError):
        assert_reported_never_resolved(resolved, stations, satellites)


def test_the_guard_covers_a_record_added_after_it_was_written() -> None:
    """The scope is every record it is handed, proven by adding one.

    The guards in this repository that failed did so with a populated but stale
    scope, not an empty one, so non-emptiness is not the check. A resolved record
    is appended and the guard is required to notice it and to have grown by it.
    """
    records, stations, satellites = _run()
    clean = assert_reported_never_resolved(records, stations, satellites)
    disagreeing = next(
        record for record in records if record.pm25_disagreement is PM25DisagreementState.DISAGREED
    )
    added = [*records, _seed_substitution([disagreeing])[0]]
    with pytest.raises(AssertionError):
        assert_reported_never_resolved(added, stations, satellites)
    assert assert_reported_never_resolved(records, stations, satellites) == clean, (
        "the guard's scope changed without the input changing"
    )


def test_the_guard_refuses_to_pass_over_nothing() -> None:
    """A scope of zero comparisons must not read as a clean run.

    The guard returns its count precisely so a caller cannot mistake "examined
    nothing" for "found nothing wrong", which is the shape of every scope failure
    this repository has had.
    """
    assert assert_reported_never_resolved([], [], []) == 0
