"""Recorded fixture for AT-13: a reconciliation run that reaches every state.

**Every value here is synthetic.** No station reading, no model value and no
identifier in this module was transcribed from any provider. The licence rule in
section 5 of the contract permits committing raw values only from permissively
licensed stations, and the simplest way to stay inside it is to commit none: the
numbers below were chosen to sit on chosen sides of the frozen tolerance, which
is what AT-13 needs them to do and is not something a real hour would reliably
provide.

The fixture is deliberately built to reach three outcomes rather than one:

* EUR, fully covered and agreeing, so AGREED and STATION_CHECKED are reachable;
* ASI, fully covered and disagreeing well beyond the tolerance, so DISAGREED is
  reachable and the union rule has something to union;
* AFR, with no qualifying station at all, so UNCHECKED and NOT_COMPARED are
  reachable. This mirrors the real shape rather than inventing a case: AFR has no
  reference-grade PM2.5 station covering the capture window near any of its three
  cities at any radius tested, which the pre-flight established and D3 leans on.

NAM is present with coverage one below the frozen minimum, so the boundary is
exercised by a window that has stations and still is not covered. That is a
different failure from having none, and a fixture that only had the AFR case
would not tell them apart.

``test_at13_reconciliation.py`` asserts that this fixture really does span those
outcomes. Without that companion, AT-13's green would mean the apparatus ran, not
that it discriminated.
"""

from __future__ import annotations

from datetime import UTC, datetime

from climate_index.core.models import Construction, SatelliteEvent, StationObservation

# Two consecutive hours inside the control window, so the fixture also exercises
# more than one closed window per region.
HOUR_ONE = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
HOUR_TWO = datetime(2026, 7, 18, 11, 0, tzinfo=UTC)

# Every value below is synthetic and chosen, not observed. Recorded here so the
# provenance question has a written answer at the point of use.
VALUE_PROVENANCE = "SYNTHETIC: chosen to land either side of the frozen tolerance"

# Model values, one per city per hour. Held near a single figure so that the
# station side alone decides each outcome and a failure is attributable.
_MODEL = 12.0

# Station values. EUR sits within the tolerance of the model value; ASI sits far
# outside it. The median of each triple is what the rule uses, and the third EUR
# value is an outlier that the median must absorb.
_EUR_STATIONS = (11.0, 12.5, 240.0)
_ASI_STATIONS = (86.0, 88.0, 90.0)
# One below the frozen minimum of three, on purpose.
_NAM_STATIONS = (13.0, 13.5)

_CITIES = {
    "EUR": "Amsterdam",
    "ASI": "Delhi",
    "NAM": "New York",
    "AFR": "Lagos",
}


def _station(region: str, value: float, index: int, ts: datetime) -> StationObservation:
    return StationObservation(
        ts=ts,
        region=region,
        city=_CITIES[region],
        station_id=f"{region.lower()}-synthetic-{index}",
        pm25_ugm3=value,
        sample_count=1,
        construction=Construction.PROVIDER_HOURLY,
    )


def _satellite(region: str, ts: datetime) -> SatelliteEvent:
    return SatelliteEvent(
        ts=ts,
        region=region,
        city=_CITIES[region],
        cloud_cover_pct=40.0,
        vegetation_index=0.1,
        aerosol_index=1.0,
        model_pm25_ugm3=_MODEL,
    )


def stations() -> list[StationObservation]:
    """Every station hour in the fixture. AFR has none, which is the point."""
    rows: list[StationObservation] = []
    for ts in (HOUR_ONE, HOUR_TWO):
        for region, values in (
            ("EUR", _EUR_STATIONS),
            ("ASI", _ASI_STATIONS),
            ("NAM", _NAM_STATIONS),
        ):
            rows += [_station(region, value, i, ts) for i, value in enumerate(values)]
    return rows


def satellites() -> list[SatelliteEvent]:
    """Every model hour, including AFR, so AFR has a window to be UNCHECKED in."""
    return [
        _satellite(region, ts)
        for ts in (HOUR_ONE, HOUR_TWO)
        for region in ("EUR", "ASI", "NAM", "AFR")
    ]
