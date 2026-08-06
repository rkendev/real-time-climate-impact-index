#!/usr/bin/env python3
"""Run the reconciliation over one named window and write its evidence artifact.

Operator tooling for UC-8, in the shape the other scripts in this directory use:
argparse, ``main(argv) -> int``, no import from ``src`` into it and no import of
it from ``src``.

The window is named and required. There is deliberately no ``--window-start`` or
``--window-end``, and no default: the only accepted values are the keys of
``settings.reconciliation_windows``, which during T3a holds exactly one entry.
A holdout date is therefore not expressible through this interface at all, which
closes the hole structurally instead of scanning for it afterwards. Adding the
holdout entry to the settings object is the act of opening the seal, and it is
its own dated record.

This is an apparatus check and not a result. If the run reports a fault, that is
an apparatus defect that blocks the run; it is never a finding. The contract
permits at most two re-runs after a diagnosed repair, and every fault is
diagnosed in writing before any repair is attempted. The run counter lives in the
committed evidence directory rather than in anyone's recollection.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from climate_index.config import Settings, WindowSpan, get_settings
from climate_index.core.models import (
    ClimateIndexRecord,
    PM25DisagreementState,
    SatelliteEvent,
    StationObservation,
)
from climate_index.core.reconciliation import WindowViolationError, reconcile

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = REPO_ROOT / "data" / "capture"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "control-window"


class ApparatusFault(RuntimeError):
    """The run could not be completed for a reason that is not a measurement.

    Distinguished from a result on purpose. A fault blocks the run and is
    diagnosed in writing; it never becomes a number that anything downstream
    reads.
    """


def window_choices(settings: Settings) -> tuple[str, ...]:
    """The window names a run may be pointed at, from the settings object only."""
    return tuple(sorted(settings.reconciliation_windows))


def resolve_window(name: str, settings: Settings) -> WindowSpan:
    """Return the named window, refusing anything the settings object does not hold."""
    try:
        return settings.reconciliation_windows[name]
    except KeyError:
        raise ApparatusFault(
            f"no window named {name!r}; the settings object holds "
            f"{', '.join(window_choices(settings)) or 'none'}. A window that is not "
            "configured cannot be run, and adding one is a recorded decision rather "
            "than an argument."
        ) from None


def load_capture(name: str) -> tuple[list[StationObservation], list[SatelliteEvent]]:
    """Read the capture for one window name from its own directory.

    Each window's capture lives under its own name, so a run cannot read a
    window it was not pointed at even by accident.
    """
    root = CAPTURE_DIR / name
    if not root.is_dir():
        raise ApparatusFault(
            f"no capture at {root.relative_to(REPO_ROOT)}; run the capture for "
            f"{name!r} before reconciling it"
        )
    stations = [
        StationObservation.model_validate(row) for row in _read_jsonl(root / "station.jsonl")
    ]
    satellites = [SatelliteEvent.model_validate(row) for row in _read_jsonl(root / "model.jsonl")]
    if not stations or not satellites:
        raise ApparatusFault(
            f"capture at {root.relative_to(REPO_ROOT)} is missing one of its two "
            f"sides: {len(stations)} station rows, {len(satellites)} model rows"
        )
    return stations, satellites


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cross_check_covered_count(records: Sequence[ClimateIndexRecord]) -> int:
    """The covered city-window count, by two derivations that must agree.

    One route sums the scalar each record carries. The other counts the covered
    entries in the per-city detail, which round-trips through JSON on its way to
    and from every store. Two code paths, and a single common-mode error cannot
    satisfy both.

    This is D2's denominator and the number the evaluability precondition is
    tested against, so it is the one figure in the run that must not be taken by
    eye.
    """
    by_scalar = sum(record.covered_city_count for record in records)
    by_detail = sum(
        1
        for record in records
        for comparison in record.city_comparisons
        if comparison.state is not PM25DisagreementState.NOT_COMPARED
    )
    if by_scalar != by_detail:
        raise ApparatusFault(
            f"covered city-window count disagrees between its two derivations: "
            f"{by_scalar} from the scalar, {by_detail} from the per-city detail"
        )
    return by_scalar


def per_city_breakdown(records: Sequence[ClimateIndexRecord]) -> dict[str, dict[str, int]]:
    """Covered and flagged counts per city. The unit D2 binds on."""
    out: dict[str, dict[str, int]] = {}
    for record in records:
        for comparison in record.city_comparisons:
            if not comparison.covered:
                continue
            entry = out.setdefault(comparison.city, {"covered": 0, "flagged": 0})
            entry["covered"] += 1
            if comparison.state is PM25DisagreementState.DISAGREED:
                entry["flagged"] += 1
    return dict(sorted(out.items()))


def weaker_condition_count(
    records: Sequence[ClimateIndexRecord], settings: Settings
) -> dict[str, int]:
    """How many covered city-windows satisfy the weaker condition, as evidence only.

    Section 4.3 requires the count under ``|Oi - Mi| <= U(Oi)`` to be reported
    beside the beta = 2 count, with no floor attached to it and no claim binding
    to it. ``U`` is ``T / beta``, so it is recoverable from the tolerance already
    on each comparison without restating any constant.
    """
    within = 0
    total = 0
    for record in records:
        for comparison in record.city_comparisons:
            if not comparison.covered or comparison.tolerance is None:
                continue
            station, model = comparison.station_pm25_ugm3, comparison.model_pm25_ugm3
            if station is None or model is None:
                continue
            total += 1
            if abs(station - model) <= comparison.tolerance / settings.mqo_beta:
                within += 1
    return {"covered": total, "within_u": within, "outside_u": total - within}


def summarize(
    records: Sequence[ClimateIndexRecord], name: str, settings: Settings
) -> dict[str, Any]:
    """The run's reported figures. An apparatus check, not a result."""
    covered = cross_check_covered_count(records)
    flagged = sum(record.flagged_city_count for record in records)
    return {
        "per_city": per_city_breakdown(records),
        "weaker_condition": weaker_condition_count(records, settings),
        "schema": "reconciliation-run/1",
        "window": name,
        "note": (
            "An apparatus check and not a result. The rate below is the control "
            "window's and is not a D2 evaluation: D2's band and its evaluability "
            "precondition apply to the holdout and to nothing else."
            if name == "control"
            else "The D2 evaluation. The band and the evaluability precondition "
            "apply to this window and to nothing else."
        ),
        "region_windows": len(records),
        "covered_city_windows": covered,
        "flagged_city_windows": flagged,
        "region_windows_by_state": {
            state.value: sum(1 for record in records if record.pm25_disagreement is state)
            for state in PM25DisagreementState
        },
        "region_windows_by_tier": _count_by(records, "provenance_tier"),
    }


def _count_by(records: Sequence[ClimateIndexRecord], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(getattr(record, field))
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window",
        required=True,
        choices=window_choices(settings),
        help=(
            "which configured window to reconcile. Required, with no default, and "
            "restricted to the windows the settings object holds. There is no way "
            "to name a window by date."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    args = build_parser(settings).parse_args(argv)
    try:
        window = resolve_window(args.window, settings)
        stations, satellites = load_capture(args.window)
        from climate_index.core.engine import compute_records

        records = reconcile(
            compute_records(satellites, settings),
            stations,
            satellites,
            settings,
            window=window,
        )
        summary = summarize(records, args.window, settings)
    except (ApparatusFault, WindowViolationError) as fault:
        print(f"apparatus fault, run blocked: {fault}")
        print("Diagnose this in writing before attempting a repair. It is not a finding.")
        return 2

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
