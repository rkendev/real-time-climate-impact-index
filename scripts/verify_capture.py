#!/usr/bin/env python3
"""Inspect a capture before the reconciliation run is spent on it.

One reconciliation run remains and it cannot be repeated, so the input is
verified before it is used. This is the same discipline as verifying two sensors
per city before capturing the full week, one level up: check the input before
spending the one run you cannot repeat.

It computes nothing about disagreement. It reads the captured station side and
the capture artifact, and reports what would be invisible in a rate. The per-city
median table is the part that matters most: three stations reading 0.03 is
obvious in a median table and invisible in a flag rate, which is exactly how the
ozone fault survived a full run and a disclosure.

Usage: python scripts/verify_capture.py --window control
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = REPO_ROOT / "data" / "capture"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "capture"


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest_artifact(window: str) -> dict[str, Any]:
    # Not "*-{window}.json": that also matches voided-{window}.json, which is a
    # list of attempts rather than a capture record. The same shape confusion
    # already broke the successor control once; a glob that spans two shapes is
    # a scope that lies about what it read.
    found = sorted(
        p for p in EVIDENCE_DIR.glob(f"*-{window}.json") if not p.name.startswith("voided-")
    )
    if not found:
        raise SystemExit(f"no capture artifact for {window!r}")
    loaded: dict[str, Any] = json.loads(found[-1].read_text())
    return loaded


def compare_resolution(window: str) -> list[str]:
    """The holdout must have been measured on the same instrument as the control.

    OpenAQ's sensor ordering at a location is stable within a window and not over
    time, observed directly on location 50 across two days. So the same location
    can resolve to a *different* sensor between two captures. The ambiguity
    refusal stops a wrong pick; it does not stop a different one, and every other
    check on the verification list would pass while the two halves of the
    measurement sat on different instruments.

    The admitted set is identical by construction, because admission brackets the
    whole fourteen days. Any difference here is therefore **resolution drift**,
    not a population change, and the two are reported as different things.

    The control artifact predates the per-location mapping and records the
    resolved sensor ids as a sorted list, so the comparison is on that list. It
    detects any location resolving to a sensor the control run did not use. The
    one thing it cannot see is two locations swapping sensors with each other,
    which is noted rather than claimed away.
    """
    if window == "control":
        return []
    control, holdout = latest_artifact("control"), latest_artifact(window)
    a = control.get("admission", {})
    b = holdout.get("admission", {})
    problems: list[str] = []
    if a.get("version") != b.get("version"):
        problems.append(
            f"admission artifact version differs: control {a.get('version')!r}, "
            f"{window} {b.get('version')!r} (a population change, not drift)"
        )
    ca, cb = sorted(a.get("sensor_ids") or []), sorted(b.get("sensor_ids") or [])
    if ca != cb:
        only_control = sorted(set(ca) - set(cb))
        only_holdout = sorted(set(cb) - set(ca))
        problems.append(
            f"RESOLUTION DRIFT: {len(only_control)} sensors used by the control run "
            f"and not by {window}, {len(only_holdout)} the reverse. "
            f"control-only {only_control[:8]}, {window}-only {only_holdout[:8]}"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", required=True, choices=("control", "holdout"))
    args = parser.parse_args(argv)

    art = latest_artifact(args.window)
    stations = _rows(CAPTURE_DIR / args.window / "station.jsonl")
    models = _rows(CAPTURE_DIR / args.window / "model.jsonl")

    res = art.get("sensor_resolution", {})
    print("== sensor identity ==")
    print(f"  locations admitted      : {res.get('locations_admitted')}")
    print(f"  resolved to pm25 sensor : {res.get('resolved_to_pm25_sensor')}")
    print(f"  refused                 : {res.get('refused')}")
    for loc, why in list((res.get("refusals") or {}).items())[:8]:
        print(f"      {loc}: {why[:88]}")

    gate = art.get("validity_gate", {})
    print("\n== per-row gate ==")
    for key in sorted(gate):
        print(f"  {key:<28} {gate[key]}")
    off = art.get("period_not_hour_aligned", {})
    if off.get("rows"):
        print(f"  off-hour rows by city      : {off.get('by_city')}")

    print("\n== realized bounds ==")
    for source, b in sorted((art.get("observed_bounds") or {}).items()):
        print(f"  {source:<8} {b.get('rows'):>6} rows  {b.get('min')} .. {b.get('max')}")
    req = art.get("window_requested", {})
    print(f"  requested: {req.get('name')} [{req.get('start')}, {req.get('end')})")

    print("\n== uniqueness of (station, hour) ==")
    pairs = Counter((r["station_id"], r["ts"]) for r in stations)
    dupes = [k for k, n in pairs.items() if n > 1]
    print(f"  station-hours: {len(pairs)}  duplicated: {len(dupes)}")

    print("\n== per-city station population ==")
    by_city: dict[str, list[float]] = defaultdict(list)
    stns: dict[str, set[str]] = defaultdict(set)
    hours: dict[str, set[str]] = defaultdict(set)
    for r in stations:
        by_city[r["city"]].append(r["pm25_ugm3"])
        stns[r["city"]].add(r["station_id"])
        hours[r["city"]].add(r["ts"])
    off_city = (off.get("by_city") or {}) if isinstance(off, dict) else {}
    print(
        f"  {'city':<13}{'stations':>9}{'rows':>7}{'hours':>7}"
        f"{'median':>9}{'min':>8}{'max':>9}{'off-hour':>10}"
    )
    for city in sorted(by_city):
        v = by_city[city]
        print(
            f"  {city:<13}{len(stns[city]):>9}{len(v):>7}{len(hours[city]):>7}"
            f"{st.median(v):>9.2f}{min(v):>8.1f}{max(v):>9.1f}{off_city.get(city, 0):>10}"
        )

    print("\n== city-windows that would qualify (>=3 stations) ==")
    per_hour: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in stations:
        per_hour[(r["city"], r["ts"])].add(r["station_id"])
    qualifying: Counter[str] = Counter()
    for (city, _), st_set in per_hour.items():
        if len(st_set) >= 3:
            qualifying[city] += 1
    for city in sorted(by_city):
        print(f"  {city:<13}{qualifying.get(city, 0):>6}")
    print(f"  {'TOTAL':<13}{sum(qualifying.values()):>6}")
    print(f"\nmodel rows: {len(models)}")

    print("\n== instrument identity against the control capture ==")
    problems = compare_resolution(args.window)
    if args.window == "control":
        print("  (control window; nothing to compare against)")
    elif problems:
        for line in problems:
            print(f"  FINDING: {line}")
        print("\n  STOP. The two halves were not measured on the same instrument.")
        return 3
    else:
        control_ids = latest_artifact("control").get("admission", {}).get("sensor_ids") or []
        print(f"  identical: all {len(control_ids)} resolved sensor ids match the control")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
