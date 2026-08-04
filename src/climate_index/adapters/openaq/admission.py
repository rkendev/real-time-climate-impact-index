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
from pathlib import Path
from typing import Any

from climate_index.adapters.openaq.source import AdmittedSensor

# Dated artifacts live here, newest last. The filename is the derivation date.
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


def admitted_sensors(artifact: dict[str, Any]) -> tuple[AdmittedSensor, ...]:
    """The admitted sensors an artifact lists, flattened across cities.

    The artifact records station location identifiers. The sensor identifier for
    a station's PM2.5 stream is resolved by the adapter at fetch time, so the
    location id is what is carried here.
    """
    sensors: list[AdmittedSensor] = []
    for city, entry in artifact["cities"].items():
        for location_id in entry["sensor_location_ids"]:
            sensors.append(
                AdmittedSensor(
                    sensor_id=int(location_id),
                    station_id=str(location_id),
                    city=city,
                    region=str(entry["region"]),
                )
            )
    return tuple(sensors)
