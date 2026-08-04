"""NFR-DQ4 seeded violations: no fabricated tier, no inherited tier.

D3 says every region-window with no qualifying coverage, or with coverage below
the frozen minimum, carries a documented lower provenance tier; that no window
receives a grade computed from data it does not have; and that no window inherits
a grade from a neighbour or from a previous window. The contract requires the two
branches to be seeded **separately, because they can fail independently**.

The guard is ``assert_tier_earned_by_this_window`` and every path goes through it.
It recomputes each tier from that record's own coverage and requires equality,
which is why ``covered_city_count`` is on the record: a tier that cannot be
rechecked against its own inputs cannot be shown not to have been inherited.

**Why the inheritance branch needs the seed most.** AFR guarantees the uncovered
branch a non-empty witness set: it has no reference-grade PM2.5 station covering
the capture window near any of its three cities at any radius tested, so an
uncovered window exists whether anyone arranges one or not. Inheritance has no
such guarantee. Worse, inheritance is invisible whenever the inherited tier
happens to equal the tier the window would have earned, so the guard can only see
it over a fixture where the neighbour and the previous window differ from the
target.

That makes the fixture a load-bearing part of the guard, so
``assert_fixture_can_expose_inheritance`` states the three properties the fixture
must have. And that function is itself a guard that would otherwise only ever be
seen passing, so it is handed three fixtures that each lack one property and
required to fail on each separately. Without that, the thing protecting the
inheritance seed from being vacuous is itself unverified, which is the same
recursion as a call-site gate that nothing checks the call site of.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from climate_index.config import Settings
from climate_index.core.engine import compute_records
from climate_index.core.models import (
    ClimateIndexRecord,
    Construction,
    ProvenanceTier,
    SatelliteEvent,
    StationObservation,
)
from climate_index.core.reconciliation import reconcile

HOUR_ONE = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
HOUR_TWO = HOUR_ONE + timedelta(hours=1)


def _settings() -> Settings:
    return Settings(_env_file=None)


# --- the fixture, built to make inheritance visible ---------------------------


def _station(region: str, city: str, ts: datetime, index: int) -> StationObservation:
    return StationObservation(
        ts=ts,
        region=region,
        city=city,
        station_id=f"{region}-{index}",
        pm25_ugm3=11.0,
        sample_count=1,
        construction=Construction.PROVIDER_HOURLY,
    )


def _satellite(region: str, city: str, ts: datetime) -> SatelliteEvent:
    return SatelliteEvent(
        ts=ts,
        region=region,
        city=city,
        cloud_cover_pct=40.0,
        vegetation_index=0.1,
        aerosol_index=1.0,
        model_pm25_ugm3=12.0,
    )


def _fixture() -> tuple[list[StationObservation], list[SatelliteEvent]]:
    """EUR is covered in hour one and not in hour two. AFR is never covered.

    Three properties, each deliberate:

    * both tiers appear, so a tier can be seen to move at all;
    * EUR's two consecutive windows differ, so carrying a previous window's tier
      forward changes an answer and is therefore detectable;
    * in hour one, EUR and AFR differ, so copying a neighbouring region's tier
      changes an answer and is therefore detectable.
    """
    settings = _settings()
    minimum = settings.station_min_per_city_window
    stations = [_station("EUR", "Amsterdam", HOUR_ONE, i) for i in range(minimum)]
    satellites = [
        _satellite("EUR", "Amsterdam", HOUR_ONE),
        _satellite("EUR", "Amsterdam", HOUR_TWO),
        _satellite("AFR", "Lagos", HOUR_ONE),
        _satellite("AFR", "Lagos", HOUR_TWO),
    ]
    return stations, satellites


def _run() -> list[ClimateIndexRecord]:
    settings = _settings()
    stations, satellites = _fixture()
    return reconcile(
        compute_records(satellites, settings),
        stations,
        satellites,
        settings,
        window=settings.reconciliation_windows["control"],
    )


# --- the guard ----------------------------------------------------------------


def assert_tier_earned_by_this_window(records: Sequence[ClimateIndexRecord]) -> int:
    """The NFR-DQ4 guard. Returns how many records it checked.

    A window's tier is a function of that window's own coverage and of nothing
    else. Recomputed from the record's own inputs, so a tier that arrived from a
    neighbour or from a previous window disagrees with the coverage it sits
    beside.
    """
    checked = 0
    for record in records:
        checked += 1
        covered = sum(1 for comparison in record.city_comparisons if comparison.covered)
        assert record.covered_city_count == covered, (
            f"{record.region} at {record.window_start.isoformat()}: the record says "
            f"{record.covered_city_count} covered cities, its own detail says {covered}"
        )
        earned = ProvenanceTier.STATION_CHECKED if covered else ProvenanceTier.UNCHECKED
        assert record.provenance_tier is earned, (
            f"{record.region} at {record.window_start.isoformat()}: carries "
            f"{record.provenance_tier} with {covered} covered cities, which earns {earned}"
        )
    return checked


def assert_fixture_can_expose_inheritance(records: Sequence[ClimateIndexRecord]) -> None:
    """The fixture must be able to make an inherited tier visible.

    Inheritance that copies the answer the window would have reached anyway is
    undetectable from the record, so the guard above is only meaningful over a
    fixture with all three of these.
    """
    tiers = {record.provenance_tier for record in records}
    assert tiers == {ProvenanceTier.STATION_CHECKED, ProvenanceTier.UNCHECKED}, (
        f"the fixture reaches only {sorted(t.value for t in tiers)}, so a tier cannot "
        "be seen to move"
    )

    by_region: dict[str, list[ClimateIndexRecord]] = {}
    for record in records:
        by_region.setdefault(record.region, []).append(record)
    consecutive = any(
        len({r.provenance_tier for r in sorted(rows, key=lambda r: r.window_start)}) > 1
        for rows in by_region.values()
    )
    assert consecutive, (
        "no region has two windows whose tiers differ, so carrying a previous "
        "window's tier forward would change no answer and go unseen"
    )

    by_window: dict[datetime, set[ProvenanceTier]] = {}
    for record in records:
        by_window.setdefault(record.window_start, set()).add(record.provenance_tier)
    assert any(len(tiers) > 1 for tiers in by_window.values()), (
        "no window holds two regions whose tiers differ, so copying a neighbour's "
        "tier would change no answer and go unseen"
    )


# --- the no-fault control -----------------------------------------------------


def test_the_shipped_pipeline_earns_every_tier_it_carries() -> None:
    records = _run()
    checked = assert_tier_earned_by_this_window(records)
    assert checked == 4, f"the guard examined {checked} records, expected 4"


def test_the_fixture_can_expose_inheritance() -> None:
    assert_fixture_can_expose_inheritance(_run())


# --- branch one: a computed tier forced onto an uncovered window ---------------


def test_a_computed_tier_on_an_uncovered_window_turns_the_guard_red() -> None:
    """AFR guarantees this branch a witness whether anyone arranges one or not."""
    records = _run()
    seeded = [
        record.model_copy(update={"provenance_tier": ProvenanceTier.STATION_CHECKED})
        if record.provenance_tier is ProvenanceTier.UNCHECKED
        else record
        for record in records
    ]
    assert seeded != records, "the seed changed nothing"
    with pytest.raises(AssertionError, match="which earns"):
        assert_tier_earned_by_this_window(seeded)


def test_a_forged_coverage_count_turns_the_guard_red() -> None:
    """The other half of the branch: the tier is honest, the coverage is not.

    A window that claims coverage it did not have would otherwise reach
    STATION_CHECKED legitimately, so the count is checked against the detail as
    well as the tier against the count.
    """
    records = _run()
    seeded = [records[0].model_copy(update={"covered_city_count": 7}), *records[1:]]
    with pytest.raises(AssertionError, match="its own detail says"):
        assert_tier_earned_by_this_window(seeded)


# --- branch two: inheritance, which has no guaranteed witness -----------------


def test_inheriting_a_previous_windows_tier_turns_the_guard_red() -> None:
    records = sorted(_run(), key=lambda r: (r.region, r.window_start))
    seeded: list[ClimateIndexRecord] = []
    previous: dict[str, ProvenanceTier] = {}
    for record in records:
        carried = previous.get(record.region)
        seeded.append(
            record.model_copy(update={"provenance_tier": carried})
            if carried is not None
            else record
        )
        previous[record.region] = record.provenance_tier
    assert seeded != records, "the seed changed nothing, so the fixture cannot show inheritance"
    with pytest.raises(AssertionError, match="which earns"):
        assert_tier_earned_by_this_window(seeded)


def test_inheriting_a_neighbouring_regions_tier_turns_the_guard_red() -> None:
    records = _run()
    donor = next(r for r in records if r.provenance_tier is ProvenanceTier.STATION_CHECKED)
    seeded = [
        record.model_copy(update={"provenance_tier": donor.provenance_tier})
        if record.window_start == donor.window_start and record.region != donor.region
        else record
        for record in records
    ]
    assert seeded != records, "the seed changed nothing"
    with pytest.raises(AssertionError, match="which earns"):
        assert_tier_earned_by_this_window(seeded)


# --- the meta-test's own red proof --------------------------------------------


def _record(region: str, start: datetime, tier: ProvenanceTier, covered: int) -> ClimateIndexRecord:
    """A minimal record, for handing the meta-test fixtures that are inadequate."""
    return ClimateIndexRecord(
        region=region,
        window_start=start,
        window_end=start + timedelta(hours=1),
        impact_index=50.0,
        temperature_anomaly=0.0,
        dryness_index=0.0,
        pollution_index=0.0,
        confidence="MEASURED",
        pm25_disagreement="NOT_COMPARED",
        provenance_tier=tier,
        flagged_city_count=0,
        covered_city_count=covered,
    )


def test_the_meta_test_rejects_a_fixture_that_spans_one_tier() -> None:
    """Property one: without both tiers, nothing can be seen to move at all."""
    same = [
        _record("EUR", HOUR_ONE, ProvenanceTier.UNCHECKED, 0),
        _record("EUR", HOUR_TWO, ProvenanceTier.UNCHECKED, 0),
        _record("AFR", HOUR_ONE, ProvenanceTier.UNCHECKED, 0),
    ]
    with pytest.raises(AssertionError, match="reaches only"):
        assert_fixture_can_expose_inheritance(same)


def test_the_meta_test_rejects_a_fixture_with_no_differing_previous_window() -> None:
    """Property two: both tiers exist, but never consecutively within a region.

    Each region is internally constant across time, so carrying a previous
    window's tier forward would change no answer and the previous-window seed
    would pass while proving nothing.
    """
    constant_in_time = [
        _record("EUR", HOUR_ONE, ProvenanceTier.STATION_CHECKED, 1),
        _record("EUR", HOUR_TWO, ProvenanceTier.STATION_CHECKED, 1),
        _record("AFR", HOUR_ONE, ProvenanceTier.UNCHECKED, 0),
        _record("AFR", HOUR_TWO, ProvenanceTier.UNCHECKED, 0),
    ]
    with pytest.raises(AssertionError, match="two windows whose tiers differ"):
        assert_fixture_can_expose_inheritance(constant_in_time)


def test_the_meta_test_rejects_a_fixture_with_no_differing_neighbour() -> None:
    """Property three: both tiers exist and move over time, but never side by side.

    Every region agrees with every other within any one window, so copying a
    neighbour's tier would change no answer and the neighbour seed would pass
    while proving nothing.
    """
    constant_across_regions = [
        _record("EUR", HOUR_ONE, ProvenanceTier.STATION_CHECKED, 1),
        _record("AFR", HOUR_ONE, ProvenanceTier.STATION_CHECKED, 1),
        _record("EUR", HOUR_TWO, ProvenanceTier.UNCHECKED, 0),
        _record("AFR", HOUR_TWO, ProvenanceTier.UNCHECKED, 0),
    ]
    with pytest.raises(AssertionError, match="two regions whose tiers differ"):
        assert_fixture_can_expose_inheritance(constant_across_regions)


def test_the_guard_covers_a_record_added_after_it_was_written() -> None:
    """The scope is every record it is handed, proven by adding one.

    The guards in this repository that failed did so with a populated but stale
    scope, not an empty one, so non-emptiness is not the check. A record is
    appended and the guard is required to notice it.
    """
    records = _run()
    clean = assert_tier_earned_by_this_window(records)
    added = [*records, _record("NAM", HOUR_ONE, ProvenanceTier.STATION_CHECKED, 0)]
    with pytest.raises(AssertionError, match="NAM"):
        assert_tier_earned_by_this_window(added)
    # And the added record really was extra scope rather than a replacement.
    assert len(added) == clean + 1


def test_the_meta_test_accepts_a_fixture_that_has_all_three() -> None:
    """The no-fault control for the meta-test itself.

    Three reds mean nothing if the function rejects everything, so the shape it
    is supposed to accept is asserted beside the three it must reject.
    """
    adequate = [
        _record("EUR", HOUR_ONE, ProvenanceTier.STATION_CHECKED, 1),
        _record("EUR", HOUR_TWO, ProvenanceTier.UNCHECKED, 0),
        _record("AFR", HOUR_ONE, ProvenanceTier.UNCHECKED, 0),
        _record("AFR", HOUR_TWO, ProvenanceTier.UNCHECKED, 0),
    ]
    assert_fixture_can_expose_inheritance(adequate)
