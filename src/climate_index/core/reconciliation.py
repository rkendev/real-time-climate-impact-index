"""UC-8: compare station PM2.5 against the model analysis, and report (FR-12, FR-13).

Runs after the index is computed and changes none of its values. It sets two
fields on a record that the index itself never touches: the PM2.5 disagreement
state (E-10) and the provenance tier (E-11). The confidence grade, the component
metrics and the impact index are read-only here, which is what keeps the
comparison out of the number it grades.

Every rule this module applies is frozen in ``PREREGISTRATION.md`` and reaches it
through the settings object, which the contract's section 9 makes the single
authority. No threshold constant appears in this file. The values are checked
back against the contract by ``tests/hygiene/test_settings_match_contract.py``.

Reported, never resolved. Where the two sources disagree, both values are
carried and neither is substituted for the other, averaged with it, or preferred.
Where they cannot be compared, that is stated rather than approximated.

The window is required and is not defaulted. A reconciliation run is always
pointed at a named window from the settings object, and every observation handed
to it must fall inside that window or the run refuses. That refusal is not
defensive tidiness: it is the third layer of the seal, after the entry point
offering no way to name an unadmitted window and the capture holding no data from
one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from math import sqrt
from statistics import median

from climate_index.config import Settings, WindowSpan, get_settings
from climate_index.core.models import (
    CityComparison,
    ClimateIndexRecord,
    PM25DisagreementState,
    ProvenanceTier,
    SatelliteEvent,
    StationObservation,
)


class WindowViolationError(ValueError):
    """An input carried a timestamp outside the window the run was pointed at.

    Raised rather than filtered. Silently dropping the stray hour would let a run
    labelled with one window quietly measure another, which is the failure the
    window argument exists to prevent.
    """


def mqo_tolerance(station_value: float, settings: Settings | None = None) -> float:
    """Return ``T(O)``, the tolerance at a station value, in micrograms per cubic metre.

    ``T(O) = beta * U(O)`` with
    ``U(O) = Ur(RV) * sqrt((1 - a^2) * O^2 + a^2 * RV^2)``.

    The station value is used as the guidance uses it, as the measurement. The
    magnitude is taken because the expression is defined on a concentration and a
    retained negative reading is a measurement near the detection limit rather
    than a negative concentration; squaring it would otherwise widen the
    tolerance as the reading fell further below zero.
    """
    resolved = settings if settings is not None else get_settings()
    relative = resolved.mqo_relative_uncertainty_at_reference
    reference = resolved.mqo_reference_value_ugm3
    alpha = resolved.mqo_alpha
    observed = abs(station_value)
    uncertainty = relative * sqrt((1.0 - alpha**2) * observed**2 + alpha**2 * reference**2)
    return resolved.mqo_beta * uncertainty


def compare_city(
    station_value: float | None,
    model_value: float | None,
    station_count: int,
    settings: Settings | None = None,
) -> tuple[PM25DisagreementState, float | None]:
    """Grade one city-window, returning its state and the tolerance that decided it.

    AGREED or DISAGREED only where the window is covered and both values exist.
    Everything else is NOT_COMPARED, which is a statement about coverage and not
    a judgement about either source.
    """
    resolved = settings if settings is not None else get_settings()
    if station_count < resolved.station_min_per_city_window:
        return PM25DisagreementState.NOT_COMPARED, None
    if station_value is None or model_value is None:
        return PM25DisagreementState.NOT_COMPARED, None
    tolerance = mqo_tolerance(station_value, resolved)
    flagged = abs(station_value - model_value) > tolerance
    return (
        PM25DisagreementState.DISAGREED if flagged else PM25DisagreementState.AGREED,
        tolerance,
    )


def _check_window(moments: Iterable[datetime], window: WindowSpan) -> None:
    stray = sorted({moment for moment in moments if not window.contains(moment)})
    if stray:
        raise WindowViolationError(
            f"{len(stray)} observation timestamps fall outside the run window "
            f"[{window.start.isoformat()}, {window.end.isoformat()}), "
            f"first {stray[0].isoformat()}"
        )


def _city_values(
    stations: Sequence[StationObservation],
) -> tuple[float | None, int]:
    """The city value and its qualifying station count.

    The median rather than the mean, so one bad station does not carry the
    window. Validity was already decided upstream by the provider's own quality
    flag and by at least one underlying sample; nothing is discarded here, and in
    particular negative readings are retained.
    """
    if not stations:
        return None, 0
    return median(observation.pm25_ugm3 for observation in stations), len(stations)


def reconcile(
    records: Sequence[ClimateIndexRecord],
    stations: Sequence[StationObservation],
    satellites: Sequence[SatelliteEvent],
    settings: Settings | None = None,
    *,
    window: WindowSpan,
) -> list[ClimateIndexRecord]:
    """Set E-10 and E-11 on each record from the station and model streams (UC-8).

    Returns new records. Nothing is mutated, and no field the index computed is
    read except to copy it forward, so a reconciled run and an unreconciled run
    differ in exactly the two states and the three fields that support them.
    """
    resolved = settings if settings is not None else get_settings()
    _check_window(
        [observation.ts for observation in stations] + [event.ts for event in satellites],
        window,
    )

    station_index: dict[tuple[str, str, datetime, datetime], list[StationObservation]] = {}
    model_index: dict[tuple[str, str, datetime, datetime], list[float]] = {}
    for record in records:
        span = (record.window_start, record.window_end)
        for observation in stations:
            if observation.region == record.region and span[0] <= observation.ts < span[1]:
                key = (record.region, observation.city, *span)
                station_index.setdefault(key, []).append(observation)
        for event in satellites:
            if event.region == record.region and span[0] <= event.ts < span[1]:
                key = (record.region, event.city, *span)
                model_index.setdefault(key, []).append(event.model_pm25_ugm3)

    return [_reconcile_one(record, station_index, model_index, resolved) for record in records]


def _reconcile_one(
    record: ClimateIndexRecord,
    station_index: Mapping[tuple[str, str, datetime, datetime], list[StationObservation]],
    model_index: Mapping[tuple[str, str, datetime, datetime], list[float]],
    settings: Settings,
) -> ClimateIndexRecord:
    span = (record.window_start, record.window_end)
    cities = sorted(
        {key[1] for key in station_index if key[0] == record.region and key[2:] == span}
        | {key[1] for key in model_index if key[0] == record.region and key[2:] == span}
    )

    comparisons: list[CityComparison] = []
    for city in cities:
        key = (record.region, city, *span)
        station_value, station_count = _city_values(station_index.get(key, []))
        models = model_index.get(key, [])
        model_value = sum(models) / len(models) if models else None
        state, tolerance = compare_city(station_value, model_value, station_count, settings)
        comparisons.append(
            CityComparison(
                city=city,
                station_pm25_ugm3=station_value,
                model_pm25_ugm3=model_value,
                tolerance=tolerance,
                station_count=station_count,
                state=state,
            )
        )

    covered = [comparison for comparison in comparisons if comparison.covered]
    flagged = [
        comparison for comparison in covered if comparison.state is PM25DisagreementState.DISAGREED
    ]
    # The union rule: the region carries the state when at least one of its
    # covered cities is flagged. The region index is built from all of its
    # cities, so if any covered constituent disagrees then the region's number is
    # partly built on a value that disagrees.
    if flagged:
        state = PM25DisagreementState.DISAGREED
    elif covered:
        state = PM25DisagreementState.AGREED
    else:
        state = PM25DisagreementState.NOT_COMPARED

    return record.model_copy(
        update={
            "pm25_disagreement": state,
            # Decided by this window's own coverage and nothing else. Never from
            # a neighbouring region, never from a previous window (NFR-DQ4).
            "provenance_tier": (
                ProvenanceTier.STATION_CHECKED if covered else ProvenanceTier.UNCHECKED
            ),
            "flagged_city_count": len(flagged),
            "covered_city_count": len(covered),
            "city_comparisons": tuple(comparisons),
        }
    )
