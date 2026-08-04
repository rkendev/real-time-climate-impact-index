#!/usr/bin/env python3
"""Capture one named measurement window from both sources, and record what landed.

Operator tooling, in the shape `recompute_station_admission.py` established:
argparse, ``main(argv) -> int``, never imported by ``src/``. It is committed
before it is run, for the same reason that script was: a capture produced by code
nobody else has is a capture nobody else can reproduce.

**The station side is `/v3/sensors/{id}/hours`, not the S3 archive.** Section 5 of
the contract names that endpoint for the half-open hour ``[H, H+1)``, and the
choice is load-bearing rather than incidental. The archive carries raw irregular
instants, so using it would mean computing the hourly value locally for every
station. That would make every station a computed mean, which would destroy the
provider-hourly against computed-mean breakdown the contract requires as a
reported output, and would collapse the one axis on which the CPCB construction
confound is visible at all. It would also mean the frozen rule was set aside
because a keyless route was cheaper. So the key is required and the archive is
not an admissible source for a station value.

The window is named, never dated. The only accepted names are the keys of
``settings.reconciliation_windows``, so this script cannot be pointed at a window
the settings object does not hold, and each window's capture lands under its own
directory.

Two things the artifact records that a declaration alone would not give:

* the realized minimum and maximum observation timestamp **per source**, so that
  "we asked for this window" and "what landed is this window" are separately
  established. Metadata saying "control window" is not the same as data that is
  one, and only the second catches a mis-executed pull;
* no measured value, anywhere. The artifact is committed, the captured rows are
  not, and the frozen licence rule bites on committed raw values. Counts,
  timestamps and statuses only.

A capture is one clean run or it is voided and re-run from scratch. On any
fault or interruption, whatever landed is deleted and the attempt is appended to
a voided-attempt history beside the artifact. Stitching two partial runs together
would produce a status distribution describing two runs and timestamp bounds that
could straddle them, and neither would describe anything that happened.

Usage: CII_OPENAQ_API_KEY=... python scripts/capture_window.py --window control
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = REPO_ROOT / "data" / "capture"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "capture"

# Published as 60 requests a minute and 2000 an hour, with 429 on exceed and a
# documented risk of a ban for repeatedly exceeding. Paced below the per-minute
# limit, the same figure the admission recomputation used.
PACE_SECONDS = 1.1
# The station endpoint returns one row per hour, so a seven-day window is 168
# rows and a single page at this limit. Paging is still implemented, because a
# silent truncation would look exactly like a sparse sensor.
PAGE_LIMIT = 1000

# Joined onto CII_OPENAQ_BASE_URL, which already carries the version segment.
# No /v3 here: the first capture attempt was voided by a 404 on
# https://api.openaq.org/v3/v3/sensors/80/hours because this constant restated it.
# The shipped adapter builds the same URL at source.py:240 and has always been
# right; the fix is to match it rather than to restate the path a second time.
OPENAQ_HOURS_PATH = "/sensors/{sensor_id}/hours"
OPEN_METEO_AIR_QUALITY = "https://air-quality-api.open-meteo.com/v1/air-quality"


class CaptureFault(RuntimeError):
    """The capture could not be completed for a reason that is not a measurement."""


# The rate-limit headers the provider documents. Recorded at the first and the
# last response of a run, so how much headroom there was at the start and how
# much was left at the end are both facts about this run rather than estimates.
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-used",
    "x-ratelimit-reset",
)


@dataclass
class CallLog:
    """Every response's status, so a zero can be told from a failure."""

    statuses: Counter[int] = field(default_factory=Counter)
    rate_limited: bool = False
    first_headers: dict[str, str] | None = None
    last_headers: dict[str, str] | None = None

    def record(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.statuses[status] += 1
        if status == 429:
            self.rate_limited = True
        if headers:
            if self.first_headers is None:
                self.first_headers = headers
            self.last_headers = headers

    def as_dict(self) -> dict[str, Any]:
        """What actually happened. A field absent means it was never observed.

        The rate-limit blocks are omitted rather than defaulted when the provider
        sent no such header, because an empty block and a block of zeros are
        different claims and only one of them would be true.
        """
        record: dict[str, Any] = {
            "calls": sum(self.statuses.values()),
            "statuses": {str(code): count for code, count in sorted(self.statuses.items())},
            "rate_limited": self.rate_limited,
        }
        if self.first_headers:
            record["rate_limit_at_start"] = self.first_headers
        if self.last_headers:
            record["rate_limit_at_end"] = self.last_headers
        return record


class PacedClient:
    """A paced HTTP client that records every response it receives."""

    def __init__(self, log: CallLog, headers: dict[str, str] | None = None) -> None:
        self._log = log
        self._headers = headers or {}
        self._last = 0.0

    def get(self, url: str) -> dict[str, Any]:
        wait = PACE_SECONDS - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers=self._headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                self._log.record(response.status, _rate_limit(response.headers))
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            self._log.record(error.code, _rate_limit(error.headers))
            raise CaptureFault(f"{url.split('?')[0]} returned {error.code}") from error
        except urllib.error.URLError as error:
            self._log.record(0)
            raise CaptureFault(f"{url.split('?')[0]} did not answer: {error.reason}") from error
        finally:
            self._last = time.monotonic()
        if not isinstance(payload, dict):
            raise CaptureFault(f"{url.split('?')[0]} returned a non-object body")
        return payload


def _rate_limit(headers: Any) -> dict[str, str]:
    """The provider's rate-limit headers, as sent. Absent ones are simply absent."""
    if headers is None:
        return {}
    return {
        name: str(headers.get(name)) for name in RATE_LIMIT_HEADERS if headers.get(name) is not None
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def void_history(name: str) -> list[dict[str, Any]]:
    """Voided attempts at this window, read back from the record they were written to.

    A capture is one clean run or it is voided and re-run from scratch. Stitching
    two partial runs together would give a status distribution describing two runs
    and timestamp bounds that could straddle them, and neither would describe
    anything that happened. So a voided attempt is deleted from the data and
    written to this history instead: the run did happen, and a record showing four
    attempts and one capture is more honest than one showing a capture.
    """
    path = EVIDENCE_DIR / f"voided-{name}.json"
    if not path.is_file():
        return []
    loaded = json.loads(path.read_text())
    return loaded if isinstance(loaded, list) else []


def record_void(name: str, reason: str, station_log: CallLog, model_log: CallLog) -> Path:
    """Append a voided attempt, and remove whatever it left on disk."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"voided-{name}.json"
    history = void_history(name)
    history.append(
        {
            "voided_at": _iso(datetime.now(UTC)),
            "reason": reason,
            "station": station_log.as_dict(),
            "model": model_log.as_dict(),
        }
    )
    path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")
    root = CAPTURE_DIR / name
    if root.is_dir():
        for child in root.iterdir():
            child.unlink()
        root.rmdir()
    return path


def _parse_hour(value: Any) -> datetime | None:
    """The start of the half-open hour a row covers, as timezone-aware UTC."""
    if not isinstance(value, dict):
        return None
    text = value.get("utc")
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def station_rows(
    payload: dict[str, Any],
    sensor: dict[str, Any],
    gate: Counter[str] | None = None,
) -> list[dict[str, Any]]:
    """Turn one page of hourly rows into E-8 shaped dicts, applying only validity.

    Validity is the provider's own quality flag and at least one underlying
    sample, exactly as section 5 freezes it, and nothing else is applied here.
    Coverage, the median and the tolerance all belong to the reconciliation, and
    applying any of them at capture time would bake a frozen rule into the data
    rather than into the code that reads it.

    Negative readings are retained. The frozen rules retain them, and discarding
    them would bias the station value upward precisely where the tolerance floor
    dominates.
    """
    tally = gate if gate is not None else Counter()
    rows: list[dict[str, Any]] = []
    for entry in payload.get("results", []):
        tally["returned"] += 1
        if not isinstance(entry, dict):
            tally["malformed"] += 1
            continue
        moment = _parse_hour(entry.get("period", {}).get("datetimeFrom"))
        value = entry.get("value")
        coverage = entry.get("coverage") or {}
        observed = coverage.get("observedCount")
        if value is None:
            # Counted separately: section 5 pre-commits to reporting hours
            # returned with a null value alongside the two gate conditions.
            tally["null_value"] += 1
            continue
        if moment is None or not isinstance(value, int | float):
            tally["malformed"] += 1
            continue
        if entry.get("hasFlags"):
            tally["has_flags_true"] += 1
            continue
        if not isinstance(observed, int) or observed < 1:
            tally["observed_count_below_one"] += 1
            continue
        tally["retained"] += 1
        rows.append(
            {
                "ts": _iso(moment),
                "region": sensor["region"],
                "city": sensor["city"],
                "station_id": str(sensor["station_id"]),
                "pm25_ugm3": float(value),
                "sample_count": int(observed),
                # Recorded, never gated on. One sample is a provider-validated
                # hourly value; more than one is a mean the provider computed.
                "construction": "PROVIDER_HOURLY" if observed == 1 else "COMPUTED_MEAN",
            }
        )
    return rows


def station_url(base_url: str, sensor_id: int, start: datetime, end: datetime, page: int) -> str:
    """The station request URL, extracted so it can be asserted without a network.

    Pulled out of the fetch loop by the repair for attempt 1. The whole module was
    tested from the response inwards, so the one thing deciding whether a response
    arrives at all had no test at all, and a doubled version segment survived to
    the first live call.
    """
    query = urllib.parse.urlencode(
        {
            "datetime_from": _iso(start),
            "datetime_to": _iso(end),
            "limit": PAGE_LIMIT,
            "page": page,
        }
    )
    path = OPENAQ_HOURS_PATH.format(sensor_id=sensor_id)
    return f"{base_url.rstrip('/')}{path}?{query}"


def fetch_station_side(
    client: PacedClient,
    base_url: str,
    sensors: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    gate: Counter[str] | None = None,
) -> list[dict[str, Any]]:
    """One paged call chain per admitted sensor over the window."""
    rows: list[dict[str, Any]] = []
    for sensor in sensors:
        page = 1
        while True:
            payload = client.get(station_url(base_url, int(sensor["sensor_id"]), start, end, page))
            batch = station_rows(payload, sensor, gate)
            rows += batch
            found = payload.get("meta", {}).get("found")
            if len(payload.get("results", [])) < PAGE_LIMIT:
                break
            if isinstance(found, int) and page * PAGE_LIMIT >= found:
                break
            page += 1
    return rows


def model_rows(
    payload: dict[str, Any], region: str, city: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Turn one city's hourly series into E-3 shaped dicts inside the window."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    pm25 = hourly.get("pm2_5") or []
    rows: list[dict[str, Any]] = []
    for text, value in zip(times, pm25, strict=False):
        if value is None:
            continue
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00")).replace(tzinfo=UTC)
        if not (start <= moment < end):
            continue
        rows.append(
            {
                "ts": _iso(moment),
                "region": region,
                "city": city,
                # Cloud cover and vegetation are not part of the comparison and
                # are not fetched for it. Fixed, declared values keep E-3
                # constructible without implying a measurement was taken.
                "cloud_cover_pct": 0.0,
                "vegetation_index": 0.0,
                "aerosol_index": 0.0,
                "model_pm25_ugm3": float(value),
            }
        )
    return rows


def bounds(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The realized timestamp span of what actually landed, and the row count.

    Timestamps and a count only. No measured value appears here, because this
    goes into a committed artifact and the frozen licence rule bites on committed
    raw values.
    """
    if not rows:
        return {"rows": 0, "min": None, "max": None}
    stamps = sorted(row["ts"] for row in rows)
    return {"rows": len(rows), "min": stamps[0], "max": stamps[-1]}


def assert_inside_window(rows: list[dict[str, Any]], start: datetime, end: datetime) -> None:
    """Every captured row falls in the window the run was pointed at.

    Refused rather than filtered. A capture labelled with one window that quietly
    contains hours from another is the failure the label exists to prevent, and
    silently dropping them would hide a provider returning something other than
    what was asked for.
    """
    stray = [
        row["ts"]
        for row in rows
        if not (start <= datetime.fromisoformat(row["ts"].replace("Z", "+00:00")) < end)
    ]
    if stray:
        raise CaptureFault(
            f"{len(stray)} captured rows fall outside the requested window "
            f"[{_iso(start)}, {_iso(end)}), first {stray[0]}"
        )


def head_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def build_artifact(
    *,
    name: str,
    start: datetime,
    end: datetime,
    stations: list[dict[str, Any]],
    models: list[dict[str, Any]],
    admission_version: str,
    sensor_ids: list[int],
    station_log: CallLog,
    model_log: CallLog,
    now: datetime,
    voided: list[dict[str, Any]] | None = None,
    gate: Counter[str] | None = None,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The dated evidence artifact, in the form the admission artifact established."""
    voided = voided if voided is not None else []
    per_city: dict[str, dict[str, int]] = {}
    for row in stations:
        per_city.setdefault(row["city"], {"station_rows": 0, "model_rows": 0})["station_rows"] += 1
    for row in models:
        per_city.setdefault(row["city"], {"station_rows": 0, "model_rows": 0})["model_rows"] += 1
    return {
        "schema": "window-capture/1",
        "derived_at": _iso(now),
        "derived_by": f"scripts/capture_window.py at commit {head_commit()}",
        "note": (
            "A committed, dated record of one capture. The captured rows themselves "
            "are not committed: the frozen licence rule bites on committed raw "
            "values, so this artifact carries counts, timestamps and statuses and "
            "no measured value of any kind."
        ),
        "station_source": (
            "OpenAQ /v3/sensors/{id}/hours, the provider's own hourly value for the "
            "half-open hour, per section 5. Not the S3 archive: the archive carries "
            "raw instants, so using it would compute every hourly value locally and "
            "make every station a computed mean, destroying the construction "
            "breakdown the contract requires as a reported output."
        ),
        "window_requested": {"name": name, "start": _iso(start), "end": _iso(end)},
        "observed_bounds": {"station": bounds(stations), "model": bounds(models)},
        "admission": {
            "version": admission_version,
            "sensors": len(sensor_ids),
            "sensor_ids": sorted(sensor_ids),
        },
        "run": {
            "station": station_log.as_dict(),
            "model": model_log.as_dict(),
            "pace_seconds_between_calls": PACE_SECONDS,
        },
        "per_city": dict(sorted(per_city.items())),
        # Every attempt that was voided before this one succeeded. Present even
        # when empty, because "no attempt was voided" and "voided attempts were
        # not recorded" are different claims.
        "voided_attempts": voided,
        # The pre-committed reporting obligation from section 5: how many hours
        # the provider returned, and how many each frozen validity condition
        # removed. Counted rather than inferred, because a gate that filters
        # without counting cannot report whether it ever fired. The first capture
        # did filter without counting, which is recorded in ADR-0009.
        "validity_gate": dict(sorted((gate or Counter()).items())),
        # How many admitted locations resolved to a PM2.5 sensor, and why any did
        # not. Recorded because the fault this repairs was invisible in the values.
        "sensor_resolution": resolution or {},
    }


def write_capture(name: str, stations: list[dict[str, Any]], models: list[dict[str, Any]]) -> Path:
    root = CAPTURE_DIR / name
    root.mkdir(parents=True, exist_ok=True)
    for filename, rows in (("station.jsonl", stations), ("model.jsonl", models)):
        (root / filename).write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        )
    return root


def build_parser(choices: tuple[str, ...]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window",
        required=True,
        choices=choices,
        help=(
            "which configured window to capture. Required, with no default, and "
            "restricted to the windows the settings object holds. There is no way "
            "to name a window by date."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from climate_index.adapters.openaq.admission import (
        SensorIdentityError,
        admitted_locations,
        load_artifact,
        resolve_pm25_sensor,
    )
    from climate_index.config import get_settings

    settings = get_settings()
    choices = tuple(sorted(settings.reconciliation_windows))
    args = build_parser(choices).parse_args(argv)

    # Either name works: the settings key, which is what the adapter reads, or
    # the bare operator name the admission recomputation established. Never a
    # tracked file (INV-1).
    key = settings.openaq_api_key or os.environ.get("OPENAQ_API_KEY", "")
    if not key:
        print("No API key. Set CII_OPENAQ_API_KEY or OPENAQ_API_KEY. It is a", file=sys.stderr)
        print("secret and belongs in the environment, never in a tracked file.", file=sys.stderr)
        return 2
    base_url = settings.openaq_base_url
    if not base_url:
        print("CII_OPENAQ_BASE_URL is not set (INV-1: no endpoint literal).", file=sys.stderr)
        return 2

    window = settings.reconciliation_windows[args.window]
    artifact = load_artifact(settings.station_admission_version or None)
    admitted = admitted_locations(artifact)

    station_log, model_log = CallLog(), CallLog()
    gate: Counter[str] = Counter()
    resolve_log = CallLog()
    resolution: dict[str, Any] = {}
    resolved: list[Any] = []
    try:
        # Resolve every admitted location to its PM2.5 sensor, and assert that
        # each really measures pm25 in the expected units. This step did not
        # exist for the whole of T2: a location id was used where a sensor id
        # belonged, and the provider answered with unrelated sensors, three New
        # York stations returning ozone in ppm recorded as PM2.5. The assertion
        # is the repair; the lookup is only plumbing (ADR-0009).
        resolver = PacedClient(resolve_log, {"X-API-Key": key})
        refused: dict[str, str] = {}
        for location in admitted:
            payload = resolver.get(f"{base_url.rstrip('/')}/locations/{location.location_id}")
            try:
                sensor_id = resolve_pm25_sensor(payload, location.location_id)
            except SensorIdentityError as bad:
                refused[str(location.location_id)] = str(bad)
                continue
            resolved.append(replace(location, pm25_sensor_id=sensor_id))
        resolution = {
            "locations_admitted": len(admitted),
            "resolved_to_pm25_sensor": len(resolved),
            "refused": len(refused),
            "refusals": dict(sorted(refused.items())),
            "call_log": resolve_log.as_dict(),
        }
        if not resolved:
            raise CaptureFault("no admitted location resolved to a PM2.5 sensor")
        # Built only after resolution, so a location whose PM2.5 sensor was never
        # resolved cannot reach a fetch. Ordering is the guard here.
        sensors = [
            {
                "sensor_id": location.pm25_sensor_id,
                "station_id": location.station_id,
                "city": location.city,
                "region": location.region,
            }
            for location in resolved
        ]
        stations = fetch_station_side(
            PacedClient(station_log, {"X-API-Key": key}),
            base_url,
            sensors,
            window.start,
            window.end,
            gate,
        )
        models: list[dict[str, Any]] = []
        model_client = PacedClient(model_log)
        for region, cities in sorted(settings.region_locations.items()):
            for city in cities:
                query = urllib.parse.urlencode(
                    {
                        "latitude": city.latitude,
                        "longitude": city.longitude,
                        "hourly": "pm2_5",
                        "start_date": window.start.date().isoformat(),
                        "end_date": (window.end.date().isoformat()),
                        "timezone": "UTC",
                    }
                )
                payload = model_client.get(f"{OPEN_METEO_AIR_QUALITY}?{query}")
                models += model_rows(payload, region, city.name, window.start, window.end)

        assert_inside_window(stations, window.start, window.end)
        assert_inside_window(models, window.start, window.end)
        if not stations or not models:
            raise CaptureFault(
                f"one side of the capture is empty: {len(stations)} station rows, "
                f"{len(models)} model rows"
            )
    except (CaptureFault, KeyboardInterrupt) as fault:
        # Voided, not resumed. Whatever landed is deleted and the attempt is
        # written to the history, so a later reader sees the attempt rather than
        # a capture that quietly came from two runs at different times.
        path = record_void(args.window, str(fault) or type(fault).__name__, station_log, model_log)
        print(f"capture voided, nothing kept: {fault}", file=sys.stderr)
        print(f"attempt recorded in {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        print("Re-run from scratch. Do not resume.", file=sys.stderr)
        return 2

    root = write_capture(args.window, stations, models)
    now = datetime.now(UTC)
    record = build_artifact(
        name=args.window,
        start=window.start,
        end=window.end,
        stations=stations,
        models=models,
        admission_version=str(artifact.get("derived_at", ""))[:10],
        sensor_ids=[int(loc.pm25_sensor_id or 0) for loc in resolved],
        resolution=resolution,
        station_log=station_log,
        model_log=model_log,
        now=now,
        voided=void_history(args.window),
        gate=gate,
    )
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{now.date().isoformat()}-{args.window}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"captured to {root.relative_to(REPO_ROOT)}")
    print(f"artifact {path.relative_to(REPO_ROOT)}")
    print(json.dumps(record["observed_bounds"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
