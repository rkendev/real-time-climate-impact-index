"""Recompute station admission from the frozen rules and report the funnel.

Operator tooling, like `derive_climatology.py`: never imported by `src/`, never
run by a test or a gate. It exists so the admission figures in
`PREREGISTRATION.md` are reproducible by someone who does not trust the author,
and so a zero can be told apart from a failure.

What it applies, all frozen in `PREREGISTRATION.md` at commit b81f1c9 and none of
them re-decided here:

* the mapping centre is the grid point the model provider returns, not the
  configured city coordinate, because a city sits at an arbitrary position inside
  its cell and a station near the city can fall in a neighbouring one;
* ``R = min(half-diagonal of the serving cell, 25 km)``, the second term being the
  station API's maximum radius;
* reference grade only, ``isMonitor`` true and ``isMobile`` false;
* admitted when the PM2.5 sensor's first and last timestamps bracket the capture
  window.

What it deliberately does not do: fetch a single measured value, station or model.
It reads metadata only. No station value and no model value are brought together
anywhere in this file, because reconciliation is a later task and the holdout is
sealed until then.

Rate limits are published as 60 requests per minute and 2000 per hour, with 429 on
exceed and a documented risk of a temporary or permanent ban for repeatedly
exceeding. Calls are paced below the per-minute limit, every response's status and
rate-limit headers are recorded, and a city whose chain contains any non-200 is
reported VOID rather than as a result.

Usage: OPENAQ_API_KEY=... python scripts/recompute_station_admission.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Frozen capture window (PREREGISTRATION.md section 5).
CAPTURE_START = datetime(2026, 7, 17, tzinfo=UTC)
CAPTURE_END = datetime(2026, 7, 31, tzinfo=UTC)

# The twelve configured sampling points (E-7). Held here rather than imported so
# this script stays runnable against a checkout without the package installed,
# and so a change to config cannot silently change a published figure.
CITIES: tuple[tuple[str, str, float, float], ...] = (
    ("EUR", "Amsterdam", 52.3676, 4.9041),
    ("EUR", "Berlin", 52.5200, 13.4050),
    ("EUR", "Madrid", 40.4168, -3.7038),
    ("NAM", "New York", 40.7128, -74.0060),
    ("NAM", "Chicago", 41.8781, -87.6298),
    ("NAM", "Los Angeles", 34.0522, -118.2437),
    ("AFR", "Lagos", 6.5244, 3.3792),
    ("AFR", "Nairobi", -1.2921, 36.8219),
    ("AFR", "Cairo", 30.0444, 31.2357),
    ("ASI", "Tokyo", 35.6762, 139.6503),
    ("ASI", "Delhi", 28.6139, 77.2090),
    ("ASI", "Jakarta", -6.2088, 106.8456),
)

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
STATIONS_URL = "https://api.openaq.org/v3"
PM25 = "pm25"
RADIUS_CAP_M = 25_000
DEGREE_KM = 111.32
PACE_SECONDS = 1.1  # about 54 calls a minute against a limit of 60


@dataclass
class Call:
    """One HTTP response, recorded so a zero can be told from a failure."""

    url: str
    status: int
    body_bytes: int
    remaining: str = ""
    limit: str = ""
    reset: str = ""


@dataclass
class CityResult:
    region: str
    city: str
    domain: str
    grid_lat: float
    grid_lon: float
    radius_m: int
    cap_bound: bool
    in_radius: int = 0
    fixed: int = 0
    reference_grade: int = 0
    with_pm25_sensor: int = 0
    admitted: int = 0
    admitted_ids: list[int] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    @property
    def statuses(self) -> Counter[int]:
        return Counter(call.status for call in self.calls)

    @property
    def void(self) -> bool:
        """Any non-200 anywhere in this city's chain invalidates its result."""
        return any(call.status != 200 for call in self.calls)


class Client:
    """A paced HTTP client that records every response."""

    def __init__(self, key: str) -> None:
        self._key = key
        self._last = 0.0
        self.calls: list[Call] = []

    def get(self, url: str, *, keyed: bool) -> tuple[dict[str, Any] | None, Call]:
        if keyed:
            wait = PACE_SECONDS - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
        headers = {"X-API-Key": self._key} if keyed else {}
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                call = Call(
                    url=url.split("?")[0],
                    status=response.status,
                    body_bytes=len(raw),
                    remaining=response.headers.get("x-ratelimit-remaining", ""),
                    limit=response.headers.get("x-ratelimit-limit", ""),
                    reset=response.headers.get("x-ratelimit-reset", ""),
                )
                payload = json.loads(raw)
        except urllib.error.HTTPError as error:
            call = Call(
                url=url.split("?")[0],
                status=error.code,
                body_bytes=0,
                remaining=error.headers.get("x-ratelimit-remaining", ""),
                limit=error.headers.get("x-ratelimit-limit", ""),
                reset=error.headers.get("x-ratelimit-reset", ""),
            )
            payload = None
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed
            call = Call(url=url.split("?")[0], status=-1, body_bytes=0, remaining=str(error)[:40])
            payload = None
        finally:
            if keyed:
                self._last = time.monotonic()
        self.calls.append(call)
        return payload, call


def half_diagonal_m(step_degrees: float, latitude: float) -> float:
    """Half the diagonal of a model grid cell at this latitude, in metres."""
    north_south = step_degrees * DEGREE_KM
    east_west = step_degrees * DEGREE_KM * math.cos(math.radians(latitude))
    return 0.5 * math.hypot(north_south, east_west) * 1000.0


def grid_point(client: Client, latitude: float, longitude: float) -> tuple[str, float, float]:
    """The serving domain and the grid point the model provider returns."""
    europe = (
        f"{AIR_QUALITY_URL}?latitude={latitude}&longitude={longitude}"
        "&hourly=pm2_5&forecast_days=1&models=cams_europe"
    )
    payload, _ = client.get(europe, keyed=False)
    if payload is not None and not payload.get("error"):
        return "cams_europe", float(payload["latitude"]), float(payload["longitude"])
    globe = (
        f"{AIR_QUALITY_URL}?latitude={latitude}&longitude={longitude}"
        "&hourly=pm2_5&forecast_days=1&models=cams_global"
    )
    payload, _ = client.get(globe, keyed=False)
    if payload is None:
        raise RuntimeError(f"no grid point for {latitude},{longitude}")
    return "cams_global", float(payload["latitude"]), float(payload["longitude"])


def iso_utc(value: Any) -> datetime | None:
    text = (value or {}).get("utc")
    return None if not text else datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def run_city(client: Client, region: str, city: str, lat: float, lon: float) -> CityResult:
    start = len(client.calls)
    domain, glat, glon = grid_point(client, lat, lon)
    step = 0.1 if domain == "cams_europe" else 0.4
    exact = half_diagonal_m(step, glat)
    radius = int(min(exact, RADIUS_CAP_M))
    result = CityResult(
        region=region,
        city=city,
        domain=domain,
        grid_lat=glat,
        grid_lon=glon,
        radius_m=radius,
        cap_bound=exact > RADIUS_CAP_M,
    )

    # Deliberately unfiltered by parameter, so the funnel can separate "no station"
    # from "no station measuring PM2.5".
    page = 1
    locations: list[dict[str, Any]] = []
    while True:
        url = (
            f"{STATIONS_URL}/locations?coordinates={glat},{glon}"
            f"&radius={radius}&limit=1000&page={page}"
        )
        payload, _ = client.get(url, keyed=True)
        if payload is None:
            break
        batch = payload.get("results", [])
        locations.extend(batch)
        if len(batch) < 1000:
            break
        page += 1

    result.in_radius = len(locations)
    fixed = [loc for loc in locations if not loc.get("isMobile")]
    result.fixed = len(fixed)
    monitors = [loc for loc in fixed if loc.get("isMonitor")]
    result.reference_grade = len(monitors)
    candidates = [
        loc
        for loc in monitors
        if any(s.get("parameter", {}).get("name") == PM25 for s in loc.get("sensors", []))
    ]
    result.with_pm25_sensor = len(candidates)

    for location in candidates:
        url = f"{STATIONS_URL}/locations/{location['id']}/sensors"
        payload, _ = client.get(url, keyed=True)
        if payload is None:
            continue
        for sensor in payload.get("results", []):
            if sensor.get("parameter", {}).get("name") != PM25:
                continue
            first = iso_utc(sensor.get("datetimeFirst"))
            last = iso_utc(sensor.get("datetimeLast"))
            brackets = (
                first is not None
                and last is not None
                and first <= CAPTURE_START
                and last >= CAPTURE_END
            )
            if brackets:
                result.admitted += 1
                result.admitted_ids.append(int(location["id"]))
            break

    result.calls = client.calls[start:]
    return result


def main() -> int:
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key:
        print("OPENAQ_API_KEY is not set. It is a secret and belongs in the", file=sys.stderr)
        print("environment, never in a tracked file.", file=sys.stderr)
        return 2

    client = Client(key)
    results = [run_city(client, *city) for city in CITIES]

    print(f"capture window {CAPTURE_START.date()} to {CAPTURE_END.date()}, half open\n")
    header = (
        f"{'':<4}{'city':<13}{'dom':<5}{'R km':>6}{'cap':>4}"
        f"{'inR':>6}{'fixed':>7}{'refgrade':>10}{'pm25':>6}{'admitted':>10}  statuses"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        flag = " VOID" if r.void else ""
        statuses = ", ".join(f"{code}x{n}" for code, n in sorted(r.statuses.items()))
        print(
            f"{r.region:<4}{r.city:<13}{'EU' if r.domain == 'cams_europe' else 'GL':<5}"
            f"{r.radius_m / 1000:>6.1f}{'yes' if r.cap_bound else 'no':>4}"
            f"{r.in_radius:>6}{r.fixed:>7}{r.reference_grade:>10}"
            f"{r.with_pm25_sensor:>6}{r.admitted:>10}  {statuses}{flag}"
        )

    total = sum(r.admitted for r in results)
    cities = sum(1 for r in results if r.admitted > 0)
    every_call = [c for r in results for c in r.calls]
    codes = Counter(c.status for c in every_call)
    print(f"\n{total} admitted stations across {cities} cities")
    print(f"{len(every_call)} calls, statuses {dict(sorted(codes.items()))}")
    print(f"any 429: {'YES' if codes.get(429) else 'no'}")
    print(f"void cities: {[r.city for r in results if r.void] or 'none'}")
    print("\nzeros, stated with their evidence:")
    for r in results:
        if r.admitted == 0:
            ok = sum(1 for c in r.calls if c.status == 200)
            print(
                f"  {r.city:<12} zero admitted from {ok} successful 200 responses, "
                f"no 429: {'no' if not any(c.status == 429 for c in r.calls) else 'YES'}"
            )
    print("\nadmitted station ids per city, for reproducibility:")
    for r in results:
        if r.admitted:
            print(f"  {r.city:<12} {sorted(r.admitted_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
