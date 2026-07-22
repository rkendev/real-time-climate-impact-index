#!/usr/bin/env python3
"""Derive the per-region monthly temperature normals for config (E-7, ADR-0007).

Operator tooling, run by hand. It is deliberately not imported by ``src/``, not
exercised by any test, and not wired to any make target or gate: it exists so
the constants in :mod:`climate_index.config` can be regenerated, and the
specification records the derivation parameters so those constants are
reproducible from the document alone even without this file.

What it computes, exactly as spec E-7 states it: for each region, the mean of
its configured representative cities, where a city's monthly value is the mean
of ERA5 daily mean temperature over a fixed multi-year window. The cities come
from ``Settings.region_locations``, so this script holds no copy of them
(INV-1: config is the single authority).

The archive endpoint is a required argument rather than a literal or a settings
field. It is dialled only here, only by an operator, and never by the pipeline,
so it has no business in the typed settings the running system reads (INV-1).

Usage::

    python scripts/derive_climatology.py --archive-url <archive endpoint>

Add ``--start`` and ``--end`` to move the climatology window off the 1991-2020
default that spec E-7 records. The output is a JSON object keyed by region with
twelve values each, January first, ready to paste into ``config.py`` or to set
as ``CII_REGION_MONTHLY_BASELINES``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from climate_index.config import MONTHS_IN_YEAR, CityLocation, get_settings

# The climatology window spec E-7 records. A standard 30 year WMO normals period.
DEFAULT_START = "1991-01-01"
DEFAULT_END = "2020-12-31"

# The ERA5 daily variable the normals are built from.
DAILY_VARIABLE = "temperature_2m_mean"


def fetch_city_daily(
    url: str,
    city: CityLocation,
    start: str,
    end: str,
    timeout: float,
    *,
    attempts: int = 5,
) -> tuple[list[str], list[float | None]]:
    """Return the (dates, daily mean temperatures) series for one city.

    A thirty year daily request is expensive in the provider's rate accounting,
    so a 429 is retried with a widening pause. That retry is appropriate *here*
    and expressly not in the event source: this is an operator regenerating a
    constant, where waiting is free and a partial answer is useless. The event
    source must never retry, because there a gap is data about the feed and
    hiding it would corrupt the confidence grade (ADR-0007).
    """
    query = urllib.parse.urlencode(
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": start,
            "end_date": end,
            "daily": DAILY_VARIABLE,
            "timezone": "UTC",
        }
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(f"{url}?{query}", timeout=timeout) as response:
                payload: dict[str, Any] = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts:
                raise
            pause = 20.0 * attempt
            print(f"    rate limited, waiting {pause:.0f}s", file=sys.stderr)
            time.sleep(pause)
    if payload.get("error"):
        raise RuntimeError(f"{city.name}: {payload.get('reason', 'archive request failed')}")
    daily = payload["daily"]
    return daily["time"], daily[DAILY_VARIABLE]


def monthly_means(dates: list[str], values: list[float | None]) -> list[float]:
    """Average a daily series into twelve calendar-month means, January first.

    Nulls are skipped rather than interpolated, the same no-fabrication rule the
    event source follows (ADR-0007). A month with no usable day at all is a
    failure worth stopping for, not a hole to paper over, so it raises.
    """
    buckets: dict[int, list[float]] = {month: [] for month in range(1, MONTHS_IN_YEAR + 1)}
    for date, value in zip(dates, values, strict=True):
        if value is not None:
            buckets[int(date[5:7])].append(value)
    empty = [month for month, samples in buckets.items() if not samples]
    if empty:
        raise RuntimeError(f"no usable daily values for month(s) {empty}")
    return [statistics.fmean(buckets[month]) for month in range(1, MONTHS_IN_YEAR + 1)]


def derive(
    url: str, start: str, end: str, timeout: float, pause: float = 0.0
) -> dict[str, list[float]]:
    """Return the per-region monthly normals, each region the mean of its cities."""
    settings = get_settings()
    normals: dict[str, list[float]] = {}
    first = True
    for region in settings.region_list:
        cities = settings.region_locations[region]
        per_city: list[list[float]] = []
        for city in cities:
            if not first and pause:
                time.sleep(pause)
            first = False
            dates, values = fetch_city_daily(url, city, start, end, timeout)
            city_months = monthly_means(dates, values)
            per_city.append(city_months)
            print(
                f"  {region} {city.name}: " + ", ".join(f"{value:.1f}" for value in city_months),
                file=sys.stderr,
            )
        normals[region] = [
            round(statistics.fmean([months[index] for months in per_city]), 1)
            for index in range(MONTHS_IN_YEAR)
        ]
    return normals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-url", required=True, help="ERA5 archive endpoint to query.")
    parser.add_argument("--start", default=DEFAULT_START, help="Climatology window start date.")
    parser.add_argument("--end", default=DEFAULT_END, help="Climatology window end date.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout.")
    parser.add_argument(
        "--pause",
        type=float,
        default=15.0,
        help="Seconds to wait between city requests, to stay inside the provider rate limit.",
    )
    args = parser.parse_args(argv)

    print(f"deriving {args.start}..{args.end} monthly normals", file=sys.stderr)
    normals = derive(args.archive_url, args.start, args.end, args.timeout, args.pause)
    print(json.dumps(normals, indent=4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
