"""Reads the committed, dated station admission artifact (FR-11, ADR-0009).

The admitted station set is an **outcome** of the frozen rules in
``PREREGISTRATION.md``, not an input to them. That distinction did real work
once already: when the coverage re-verification corrected Madrid from zero to
six, the correction was to evidence rather than to a predicate, and only because
the admitted-city block was labelled an outcome was there a clean way to make it.

So this module reads a committed artifact and never derives one. Specifically it
does not re-derive on startup, on a miss, or on any schedule. A set that silently
refreshed could move a published figure with nothing recording that it had, and
the drift would be invisible in exactly the way the throttled probe's zeros were.

Re-derivation is a deliberate act: run ``scripts/recompute_station_admission.py``,
which writes a **new** dated file beside the old one, and record the diff in
``adr/0009``. Nothing overwrites an existing artifact.

Station and sensor identifiers are metadata rather than measured values, so the
frozen licence rule, which restricts committing raw station readings, does not
apply to them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from climate_index.adapters.openaq.source import AdmittedLocation

# Dated artifacts live here, newest last. The filename is the derivation date.
PM25_PARAMETER = "pm25"
# The units the provider reports PM2.5 in. Asserted, not assumed: the fault this
# guards against returned ozone in ppm, which is a different quantity in
# different units and was recorded as though it were this one.
PM25_UNITS = "µg/m³"

ADMISSION_DIR = Path(__file__).resolve().parents[4] / "docs" / "evidence" / "station-admission"


def available_versions(directory: Path | None = None) -> list[str]:
    """Every committed artifact version, oldest first, by derivation date."""
    root = directory if directory is not None else ADMISSION_DIR
    return sorted(path.stem for path in root.glob("*.json"))


def load_artifact(version: str | None = None, directory: Path | None = None) -> dict[str, Any]:
    """Load one artifact, defaulting to the newest committed version.

    The version is returned inside the payload so that whatever consumes it can
    record which one it used, which is the point of dating them.
    """
    root = directory if directory is not None else ADMISSION_DIR
    versions = available_versions(root)
    if not versions:
        raise FileNotFoundError(
            f"no station admission artifact under {root}. "
            "Run scripts/recompute_station_admission.py to derive one."
        )
    chosen = version if version is not None else versions[-1]
    if chosen not in versions:
        raise ValueError(f"no station admission artifact for {chosen!r}; have {versions}")
    payload: dict[str, Any] = json.loads((root / f"{chosen}.json").read_text())
    payload["version"] = chosen
    return payload


def admitted_locations(artifact: dict[str, Any]) -> tuple[AdmittedLocation, ...]:
    """The admitted monitoring locations an artifact lists, flattened across cities.

    The artifact records **location** identifiers, under a key correctly named
    ``sensor_location_ids``, and its funnel counts are counts of locations. In the
    OpenAQ model a location is the monitoring station, so a location id is the
    right value for ``station_id`` and the wrong value for anything named
    ``sensor_id``.

    This function used to return ``AdmittedSensor`` with the location id assigned
    to ``sensor_id``, and a docstring saying the sensor identifier was "resolved by
    the adapter at fetch time". Nothing resolved it. Every
    ``/v3/sensors/{id}/hours`` call therefore used a location id in a sensor id's
    place, and because the two id spaces overlap numerically the provider answered
    with unrelated sensors: three of four New York stations returned ozone in parts
    per million, which was recorded as PM2.5 in micrograms per cubic metre. The
    diagnosis is in ADR-0009.

    A location is now what this returns, and resolving one to its PM2.5 sensor is
    an explicit, asserted step (:func:`resolve_pm25_sensor`) rather than an
    implicit one nobody performed.
    """
    locations: list[AdmittedLocation] = []
    for city, entry in artifact["cities"].items():
        for location_id in entry["sensor_location_ids"]:
            locations.append(
                AdmittedLocation(
                    location_id=int(location_id),
                    station_id=str(location_id),
                    city=city,
                    region=str(entry["region"]),
                )
            )
    return tuple(locations)


class SensorIdentityError(ValueError):
    """A sensor did not measure what the field naming it claimed it measured.

    Raised rather than filtered, and raised on the parameter rather than on the
    value. The fault this exists for produced numbers that were type-correct and
    range-plausible and simply were not PM2.5, so nothing about the values could
    have revealed it. Only asking what the sensor measures can.
    """


def check_pm25_sensor(sensor: Mapping[str, Any], location_id: int) -> int:
    """Assert one sensor really is PM2.5 in the expected units, and return its id.

    The semantic assertion. An identifier's name is a claim about what it
    identifies, and this is the only check in this repository that tests such a
    claim against the source of truth.
    """
    parameter = sensor.get("parameter") or {}
    name = str(parameter.get("name", ""))
    units = str(parameter.get("units", ""))
    if name != PM25_PARAMETER or units != PM25_UNITS:
        raise SensorIdentityError(
            f"sensor {sensor.get('id')} at location {location_id} measures "
            f"{name!r} in {units!r}, not {PM25_PARAMETER!r} in {PM25_UNITS!r}"
        )
    return int(sensor["id"])


class AmbiguousSensorError(SensorIdentityError):
    """More than one PM2.5 sensor at a location covers the window.

    Counted separately from "none covers it", because they are different facts
    and only one of them is about availability. Refused rather than resolved: an
    arbitrary choice between two valid candidates is the same class of defect as
    the original identifier fault and would be invisible in the output.
    """


def pm25_candidates(payload: Mapping[str, Any], location_id: int) -> list[int]:
    """Every PM2.5 sensor id at one location, from its ``/v3/locations`` body.

    Returns all of them rather than the first. A location may carry more than one
    PM2.5 sensor, and location 50 carries two of which one stopped reporting in
    2018; taking the first is an unrecorded choice even when the first is alive.
    """
    results = payload.get("results") or []
    if not results:
        raise SensorIdentityError(f"location {location_id} returned no body")
    sensors = (results[0] or {}).get("sensors") or []
    found = [
        check_pm25_sensor(sensor, location_id)
        for sensor in sensors
        if str((sensor.get("parameter") or {}).get("name", "")) == PM25_PARAMETER
    ]
    if not found:
        offered = sorted(str((s.get("parameter") or {}).get("name", "?")) for s in sensors)
        raise SensorIdentityError(
            f"location {location_id} has no {PM25_PARAMETER} sensor; it offers {offered}"
        )
    return found


def brackets_window(meta: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    """Whether one sensor's own reporting span brackets the capture window.

    Read from ``/v3/sensors/{id}``, which is the sensor's own metadata, rather
    than from the location's. The admitted set was derived from location-level
    dates, and a location stays "current" while any of its sensors reports, so a
    location can bracket the window with a PM2.5 sensor that died years earlier.
    """
    first = _instant(meta.get("datetimeFirst"))
    last = _instant(meta.get("datetimeLast"))
    if first is None or last is None:
        return False
    return first <= start and last >= end


def _instant(value: Any) -> datetime | None:
    text = (value or {}).get("utc") if isinstance(value, dict) else None
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def choose_pm25_sensor(covering: Sequence[int], location_id: int, candidates: Sequence[int]) -> int:
    """Exactly one covering candidate is taken. None or several are refused.

    Refusing on "several" rather than picking is the point. Two valid candidates
    is not a tie to be broken by list order; it is a question the capture cannot
    answer, and answering it arbitrarily would be invisible in every downstream
    number.
    """
    if not covering:
        raise SensorIdentityError(
            f"location {location_id} has {len(candidates)} {PM25_PARAMETER} sensor(s) "
            f"{list(candidates)}, none covering the capture window"
        )
    if len(covering) > 1:
        raise AmbiguousSensorError(
            f"location {location_id} has {len(covering)} {PM25_PARAMETER} sensors "
            f"{list(covering)} covering the capture window; refusing to choose"
        )
    return covering[0]
