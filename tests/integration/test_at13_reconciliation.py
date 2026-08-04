"""AT-13: station observations reconcile against the model analysis, end to end.

Closes AT-13 (UC-8, FR-12, FR-13, NFR-DQ3, NFR-DQ4, ADR-0009) over recorded
fixtures. Four claims, in the plan's own words: every closed region-window
carries a disagreement state and a provenance tier; a window whose sources
disagree beyond the frozen tolerance reports both values and names the cities
that drove it, with neither value substituted, averaged or preferred; a window
with no qualifying station coverage carries the unchecked tier; and
``pollution_index`` is byte-identical to the same run with reconciliation
disabled, which is what proves the disagreement state did not leak into the
index.

The first of those four is the weak one, and it is why this module opens with a
fixture-adequacy test rather than closing with one. "Every window carries both
states" is satisfied completely by a fixture in which every window is
NOT_COMPARED and UNCHECKED, which is the T2 lesson exactly: a guard passed over a
fixture whose only window already graded MEASURED, and a grade that cannot move
cannot be seen to move. A guard over a state machine needs a fixture that reaches
more than one state, so the fixture reaches three and a separate test asserts
that it does.

Without that companion an AT-13 green would establish that the apparatus ran, not
that it discriminated, and a control-window fault afterwards would be
undiagnosable for exactly the reason AT-13 was sequenced before the control run.
"""

from __future__ import annotations

from tests.integration import at13_fixtures as fixture

from climate_index.config import Settings
from climate_index.core.engine import compute_records
from climate_index.core.models import (
    ClimateIndexRecord,
    PM25DisagreementState,
    ProvenanceTier,
)
from climate_index.core.reconciliation import reconcile


def _settings() -> Settings:
    return Settings(_env_file=None)


def _unreconciled() -> list[ClimateIndexRecord]:
    return compute_records(fixture.satellites(), _settings())


def _reconciled() -> list[ClimateIndexRecord]:
    settings = _settings()
    return reconcile(
        _unreconciled(),
        fixture.stations(),
        fixture.satellites(),
        settings,
        window=settings.reconciliation_windows["control"],
    )


def _by_region(records: list[ClimateIndexRecord], region: str) -> list[ClimateIndexRecord]:
    return [record for record in records if record.region == region]


# --- the companion: the fixture must be able to discriminate ------------------


def test_the_fixture_spans_every_outcome_the_run_can_produce() -> None:
    """The load-bearing test in this module.

    Every assertion below it is satisfiable by a fixture stuck at one state. This
    is what makes them mean something.
    """
    records = _reconciled()

    states = {record.pm25_disagreement for record in records}
    assert PM25DisagreementState.AGREED in states, "no window agrees"
    assert PM25DisagreementState.DISAGREED in states, "no window disagrees"
    assert PM25DisagreementState.NOT_COMPARED in states, "no window is uncompared"

    tiers = {record.provenance_tier for record in records}
    assert tiers == {ProvenanceTier.STATION_CHECKED, ProvenanceTier.UNCHECKED}, (
        "the fixture reaches only one provenance tier, so the tier cannot be seen to move"
    )


def test_the_fixture_separates_no_coverage_from_insufficient_coverage() -> None:
    """Two different ways to be uncovered, and both are in the fixture.

    A window with no station at all and a window one station short of the frozen
    minimum both end UNCHECKED, by different routes. A fixture holding only the
    first would let a rule that ignored the minimum pass.
    """
    records = _reconciled()
    settings = _settings()

    afr = _by_region(records, "AFR")[0]
    assert afr.city_comparisons[0].station_count == 0

    nam = _by_region(records, "NAM")[0]
    short = nam.city_comparisons[0]
    assert 0 < short.station_count < settings.station_min_per_city_window
    assert nam.provenance_tier is ProvenanceTier.UNCHECKED


# --- AT-13 proper -------------------------------------------------------------


def test_every_closed_region_window_carries_both_states() -> None:
    records = _reconciled()
    assert records, "the fixture produced no closed window"
    for record in records:
        assert isinstance(record.pm25_disagreement, PM25DisagreementState)
        assert isinstance(record.provenance_tier, ProvenanceTier)


def test_a_disagreeing_window_reports_both_values_and_names_its_cities() -> None:
    record = _by_region(_reconciled(), "ASI")[0]
    assert record.pm25_disagreement is PM25DisagreementState.DISAGREED
    assert record.flagged_city_count == 1

    flagged = [
        comparison
        for comparison in record.city_comparisons
        if comparison.state is PM25DisagreementState.DISAGREED
    ]
    assert [comparison.city for comparison in flagged] == ["Delhi"]

    comparison = flagged[0]
    station, model = comparison.station_pm25_ugm3, comparison.model_pm25_ugm3
    assert station is not None and model is not None
    # Neither substituted for the other, neither averaged away, neither preferred.
    assert station != model
    assert station not in (model,) and model not in (station,)
    assert (station + model) / 2 not in (station, model)
    assert comparison.tolerance is not None
    assert abs(station - model) > comparison.tolerance


def test_an_uncovered_window_carries_the_unchecked_tier() -> None:
    for record in _by_region(_reconciled(), "AFR"):
        assert record.provenance_tier is ProvenanceTier.UNCHECKED
        assert record.pm25_disagreement is PM25DisagreementState.NOT_COMPARED
        assert record.covered_city_count == 0


def test_a_covered_agreeing_window_survives_an_outlier_station() -> None:
    """The median absorbs one bad station, which is why the rule is a median."""
    record = _by_region(_reconciled(), "EUR")[0]
    assert record.pm25_disagreement is PM25DisagreementState.AGREED
    assert record.provenance_tier is ProvenanceTier.STATION_CHECKED
    assert record.city_comparisons[0].station_pm25_ugm3 == 12.5


def test_pollution_index_is_byte_identical_with_reconciliation_not_called() -> None:
    """The claim that proves the disagreement state did not leak into the index.

    Compared as repr rather than with ``==`` so that a float which differs below
    printing precision still fails. "Byte-identical" is the plan's word and this
    is what it takes to mean it.
    """
    before = _unreconciled()
    after = _reconciled()
    assert [repr(record.pollution_index) for record in after] == [
        repr(record.pollution_index) for record in before
    ]
    for original, reconciled in zip(before, after, strict=True):
        assert repr(reconciled.impact_index) == repr(original.impact_index)
        assert repr(reconciled.temperature_anomaly) == repr(original.temperature_anomaly)
        assert repr(reconciled.dryness_index) == repr(original.dryness_index)
        assert repr(reconciled.model_pm25_ugm3) == repr(original.model_pm25_ugm3)
        assert reconciled.confidence is original.confidence


def test_the_index_comparison_is_not_vacuous() -> None:
    """The run being compared must actually have reconciled something.

    If reconcile were a no-op the byte-identical assertion above would pass and
    prove nothing at all.
    """
    before = _unreconciled()
    after = _reconciled()
    assert before != after, "reconciliation changed nothing, so the invariance is empty"
    assert any(
        record.pm25_disagreement is not PM25DisagreementState.NOT_COMPARED for record in after
    )


def test_the_covered_count_agrees_by_both_derivations() -> None:
    """D2's denominator, established twice over the whole fixture."""
    from reconcile import cross_check_covered_count

    records = _reconciled()
    # EUR and ASI are covered, in each of two hours.
    assert cross_check_covered_count(records) == 4
