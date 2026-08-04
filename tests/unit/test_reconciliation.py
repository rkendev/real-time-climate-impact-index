"""The reconciliation rule (UC-8, FR-12, FR-13, E-9 to E-12).

Every number these tests assert against is the contract's, reached through the
settings object. The tolerance values are recomputed here from the formula rather
than hardcoded, except where the contract states a figure in prose, in which case
that figure is asserted directly: those are the places a transcription error
would be invisible to a test that derived the number the same way the code does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from climate_index.config import Settings, WindowSpan
from climate_index.core.engine import compute_records
from climate_index.core.models import (
    ClimateIndexRecord,
    Confidence,
    Construction,
    PM25DisagreementState,
    ProvenanceTier,
    SatelliteEvent,
    StationObservation,
)
from climate_index.core.reconciliation import (
    WindowViolationError,
    compare_city,
    mqo_tolerance,
    reconcile,
)

TS = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(_env_file=None)


def _window() -> WindowSpan:
    return _settings().reconciliation_windows["control"]


def _station(pm25: float, *, city: str = "Amsterdam", station: str = "s1") -> StationObservation:
    return StationObservation(
        ts=TS,
        region="EUR",
        city=city,
        station_id=station,
        pm25_ugm3=pm25,
        sample_count=1,
        construction=Construction.PROVIDER_HOURLY,
    )


def _satellite(pm25: float, *, city: str = "Amsterdam") -> SatelliteEvent:
    return SatelliteEvent(
        ts=TS,
        region="EUR",
        city=city,
        cloud_cover_pct=50.0,
        vegetation_index=0.0,
        aerosol_index=1.0,
        model_pm25_ugm3=pm25,
    )


def _three(city: str = "Amsterdam", values: tuple[float, ...] = (10.0, 10.0, 10.0)):
    return [_station(value, city=city, station=f"s{index}") for index, value in enumerate(values)]


# --- the tolerance -----------------------------------------------------------


def test_the_tolerance_matches_the_figures_the_contract_states_in_prose() -> None:
    """Section 4.1 states three values of T. They are asserted, not re-derived.

    Deriving them the same way the code does would agree with a transposed
    constant just as happily. These three come from the document's own prose and
    are the only external check on the implementation of the formula.
    """
    settings = _settings()
    assert mqo_tolerance(0.0, settings) == pytest.approx(9.0, abs=0.05)
    assert mqo_tolerance(10.0, settings) == pytest.approx(11.0, abs=0.5)
    assert mqo_tolerance(25.0, settings) == pytest.approx(18.0, abs=0.5)


def test_the_tolerance_widens_with_concentration() -> None:
    settings = _settings()
    values = [mqo_tolerance(value, settings) for value in (0.0, 10.0, 25.0, 100.0)]
    assert values == sorted(values)


def test_a_retained_negative_reading_does_not_widen_the_tolerance() -> None:
    """Negatives are retained by the frozen rules, and near zero T is at its floor.

    Squaring a signed value would make the tolerance grow as a reading fell
    further below zero, which would quietly excuse disagreement exactly where the
    floor is supposed to dominate.
    """
    settings = _settings()
    assert mqo_tolerance(-10.2, settings) == pytest.approx(mqo_tolerance(10.2, settings))


def test_no_threshold_constant_appears_in_the_module() -> None:
    """Section 9 forbids it. The values live in the settings object alone."""
    from pathlib import Path

    import climate_index.core.reconciliation as module

    source = Path(module.__file__).read_text()
    for constant in ("0.36", "25.0", "0.50", "2.0"):
        assert constant not in source, f"threshold constant {constant} is written into the module"


# --- one city-window ---------------------------------------------------------


def test_a_difference_inside_the_tolerance_agrees() -> None:
    state, tolerance = compare_city(10.0, 15.0, 3, _settings())
    assert state is PM25DisagreementState.AGREED
    assert tolerance is not None and abs(10.0 - 15.0) <= tolerance


def test_a_difference_beyond_the_tolerance_disagrees() -> None:
    state, tolerance = compare_city(10.0, 40.0, 3, _settings())
    assert state is PM25DisagreementState.DISAGREED
    assert tolerance is not None and abs(10.0 - 40.0) > tolerance


def test_the_comparison_is_strict_at_the_boundary() -> None:
    """Flagged when the difference exceeds T, so equality agrees."""
    settings = _settings()
    tolerance = mqo_tolerance(10.0, settings)
    assert compare_city(10.0, 10.0 + tolerance, 3, settings)[0] is PM25DisagreementState.AGREED


def test_coverage_below_the_frozen_minimum_is_not_compared() -> None:
    settings = _settings()
    below = settings.station_min_per_city_window - 1
    assert compare_city(10.0, 40.0, below, settings)[0] is PM25DisagreementState.NOT_COMPARED
    at = settings.station_min_per_city_window
    assert compare_city(10.0, 40.0, at, settings)[0] is PM25DisagreementState.DISAGREED


def test_a_missing_value_on_either_side_is_not_compared() -> None:
    settings = _settings()
    assert compare_city(None, 10.0, 3, settings)[0] is PM25DisagreementState.NOT_COMPARED
    assert compare_city(10.0, None, 3, settings)[0] is PM25DisagreementState.NOT_COMPARED


# --- the region-window -------------------------------------------------------


def _reconciled(
    stations: list[StationObservation], satellites: list[SatelliteEvent]
) -> ClimateIndexRecord:
    settings = _settings()
    records = compute_records(satellites, settings)
    return reconcile(records, stations, satellites, settings, window=_window())[0]


def test_the_city_value_is_the_median_not_the_mean() -> None:
    """One bad station must not carry the window."""
    stations = _three(values=(10.0, 10.0, 250.0))
    record = _reconciled(stations, [_satellite(10.0)])
    assert record.city_comparisons[0].station_pm25_ugm3 == 10.0


def test_a_covered_agreeing_window_is_station_checked_and_agreed() -> None:
    record = _reconciled(_three(), [_satellite(12.0)])
    assert record.pm25_disagreement is PM25DisagreementState.AGREED
    assert record.provenance_tier is ProvenanceTier.STATION_CHECKED
    assert record.covered_city_count == 1
    assert record.flagged_city_count == 0


def test_one_flagged_city_carries_the_region_by_union() -> None:
    stations = _three("Amsterdam") + _three("Berlin", values=(80.0, 80.0, 80.0))
    satellites = [_satellite(12.0, city="Amsterdam"), _satellite(12.0, city="Berlin")]
    record = _reconciled(stations, satellites)
    assert record.pm25_disagreement is PM25DisagreementState.DISAGREED
    assert record.covered_city_count == 2
    assert record.flagged_city_count == 1
    flagged = [
        c.city for c in record.city_comparisons if c.state is PM25DisagreementState.DISAGREED
    ]
    assert flagged == ["Berlin"], "the record must name which cities drove the state"


def test_both_values_survive_and_neither_is_replaced() -> None:
    """NFR-DQ3, in the shape that makes it checkable rather than asserted."""
    stations = _three(values=(80.0, 80.0, 80.0))
    record = _reconciled(stations, [_satellite(12.0)])
    comparison = record.city_comparisons[0]
    assert comparison.station_pm25_ugm3 == 80.0
    assert comparison.model_pm25_ugm3 == 12.0
    assert comparison.station_pm25_ugm3 != comparison.model_pm25_ugm3
    mean = (80.0 + 12.0) / 2
    assert mean not in (comparison.station_pm25_ugm3, comparison.model_pm25_ugm3)


def test_an_uncovered_window_is_unchecked_and_not_compared() -> None:
    settings = _settings()
    below = [
        _station(10.0, station=f"s{i}") for i in range(settings.station_min_per_city_window - 1)
    ]
    record = _reconciled(below, [_satellite(12.0)])
    assert record.provenance_tier is ProvenanceTier.UNCHECKED
    assert record.pm25_disagreement is PM25DisagreementState.NOT_COMPARED
    assert record.covered_city_count == 0
    # The city still appears, with its count, so the shortfall is visible.
    assert record.city_comparisons[0].station_count == settings.station_min_per_city_window - 1


def test_a_window_with_no_station_at_all_is_unchecked() -> None:
    record = _reconciled([], [_satellite(12.0)])
    assert record.provenance_tier is ProvenanceTier.UNCHECKED
    assert record.city_comparisons[0].station_pm25_ugm3 is None


# --- what reconciliation must not touch --------------------------------------


def test_reconciliation_changes_no_index_value_and_no_confidence_grade() -> None:
    """AT-13's core claim, at unit scale: the comparison stays out of the index."""
    stations = _three(values=(80.0, 80.0, 80.0))
    satellites = [_satellite(12.0)]
    settings = _settings()
    before = compute_records(satellites, settings)
    after = reconcile(before, stations, satellites, settings, window=_window())
    for original, reconciled in zip(before, after, strict=True):
        assert reconciled.pollution_index == original.pollution_index
        assert reconciled.impact_index == original.impact_index
        assert reconciled.temperature_anomaly == original.temperature_anomaly
        assert reconciled.dryness_index == original.dryness_index
        assert reconciled.confidence is original.confidence
        assert reconciled.model_pm25_ugm3 == original.model_pm25_ugm3


def test_the_fixture_can_actually_move_the_state() -> None:
    """Without this, the test above passes over inputs that could not disagree.

    The lesson from the station-boundary guard: a grade that cannot move cannot
    be seen not to move, so an invariance claim over an inert fixture is not
    evidence. This pins that the same fixture does produce DISAGREED.
    """
    record = _reconciled(_three(values=(80.0, 80.0, 80.0)), [_satellite(12.0)])
    assert record.pm25_disagreement is PM25DisagreementState.DISAGREED


def test_the_grader_still_reads_only_the_index_streams() -> None:
    """Station coverage feeds the tier and nothing else (NFR-DQ2, frozen)."""
    satellites = [_satellite(12.0)]
    settings = _settings()
    without = compute_records(satellites, settings)
    with_stations = reconcile(without, _three(), satellites, settings, window=_window())
    assert with_stations[0].confidence is without[0].confidence


# --- the window is not optional ----------------------------------------------


def test_a_station_hour_outside_the_window_refuses_the_run() -> None:
    outside = _window().end + timedelta(hours=1)
    stray = StationObservation(
        ts=outside,
        region="EUR",
        city="Amsterdam",
        station_id="s9",
        pm25_ugm3=10.0,
        sample_count=1,
        construction=Construction.PROVIDER_HOURLY,
    )
    with pytest.raises(WindowViolationError, match="outside the run window"):
        reconcile([], [stray], [], _settings(), window=_window())


def test_a_model_hour_outside_the_window_refuses_the_run() -> None:
    outside = _window().start - timedelta(hours=1)
    stray = SatelliteEvent(
        ts=outside,
        region="EUR",
        city="Amsterdam",
        cloud_cover_pct=1.0,
        vegetation_index=0.0,
        aerosol_index=1.0,
        model_pm25_ugm3=5.0,
    )
    with pytest.raises(WindowViolationError):
        reconcile([], [], [stray], _settings(), window=_window())


def test_the_window_is_refused_rather_than_filtered() -> None:
    """A stray hour stops the run; it is never silently dropped.

    Filtering would let a run labelled with one window quietly measure another,
    and the label is what every downstream record and artifact carries.
    """
    inside = _three()
    outside = [_station(10.0, station="stray").model_copy(update={"ts": _window().end})]
    with pytest.raises(WindowViolationError):
        reconcile([], inside + outside, [], _settings(), window=_window())


def test_the_window_end_is_exclusive() -> None:
    window = _window()
    assert window.contains(window.start)
    assert not window.contains(window.end)


# --- the two-route count cross-check -----------------------------------------


def test_the_covered_count_agrees_by_both_derivations() -> None:
    """The scalar and the per-city detail must give the same denominator.

    That count is what D2's evaluability precondition is tested against, so it is
    established twice rather than read once.
    """
    from reconcile import cross_check_covered_count

    stations = _three("Amsterdam") + _three("Berlin", values=(80.0, 80.0, 80.0))
    satellites = [_satellite(12.0, city="Amsterdam"), _satellite(12.0, city="Berlin")]
    settings = _settings()
    records = reconcile(
        compute_records(satellites, settings), stations, satellites, settings, window=_window()
    )
    assert cross_check_covered_count(records) == 2


def test_the_cross_check_would_notice_a_disagreement() -> None:
    """The check must be able to fail, not pass vacuously."""
    from reconcile import ApparatusFault, cross_check_covered_count

    stations = _three()
    satellites = [_satellite(12.0)]
    settings = _settings()
    records = reconcile(
        compute_records(satellites, settings), stations, satellites, settings, window=_window()
    )
    tampered = [records[0].model_copy(update={"covered_city_count": 99})]
    with pytest.raises(ApparatusFault, match="disagrees between its two derivations"):
        cross_check_covered_count(tampered)


def test_an_unreconciled_record_states_that_it_is_unreconciled() -> None:
    record = compute_records([_satellite(12.0)], _settings())[0]
    assert record.pm25_disagreement is PM25DisagreementState.NOT_COMPARED
    assert record.provenance_tier is ProvenanceTier.UNCHECKED
    assert record.city_comparisons == ()
    # A single satellite event is below sparsity_min_events, so the committed
    # grader says AMBIGUOUS. Asserted rather than glossed over: it is the
    # evidence that the confidence grade is still the grader's call on the index
    # streams and owes nothing to the two new states beside it.
    assert record.confidence is Confidence.AMBIGUOUS
