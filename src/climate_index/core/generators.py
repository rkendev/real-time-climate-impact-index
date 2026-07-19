"""Synthetic event generators (UC-1, FR-1).

Pure domain logic: given a region, produce one valid WeatherEvent or
SatelliteEvent stamped with a UTC timestamp. These functions import no transport
(that is the producer's job), so the AT-1 generator test runs without ever
touching a transport client.

The spec leaves the plausible numeric ranges of ``temperature_c`` and
``aerosol_index`` to the generator (they are not schema bounds), so the sampling
ranges are documented constants here. Bounded schema fields are sampled inside
their contract limits.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from climate_index.core.models import SatelliteEvent, WeatherEvent

# Documented weather sampling ranges (degrees C, mm, m/s).
_TEMPERATURE_C_RANGE = (-20.0, 45.0)
_RAINFALL_MM_RANGE = (0.0, 50.0)
_WIND_SPEED_MS_RANGE = (0.0, 30.0)

# Documented satellite sampling ranges. Cloud, vegetation stay inside their
# schema bounds; aerosol has no schema bound so its plausible range lives here.
_CLOUD_COVER_PCT_RANGE = (0.0, 100.0)
_VEGETATION_INDEX_RANGE = (-1.0, 1.0)
_AEROSOL_INDEX_RANGE = (0.0, 5.0)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def generate_weather_event(region: str, *, ts: datetime | None = None) -> WeatherEvent:
    """Return one valid WeatherEvent for ``region`` (FR-1)."""
    return WeatherEvent(
        ts=ts if ts is not None else _now_utc(),
        region=region,
        temperature_c=random.uniform(*_TEMPERATURE_C_RANGE),
        rainfall_mm=random.uniform(*_RAINFALL_MM_RANGE),
        wind_speed_ms=random.uniform(*_WIND_SPEED_MS_RANGE),
    )


def generate_satellite_event(region: str, *, ts: datetime | None = None) -> SatelliteEvent:
    """Return one valid SatelliteEvent for ``region`` (FR-1)."""
    return SatelliteEvent(
        ts=ts if ts is not None else _now_utc(),
        region=region,
        cloud_cover_pct=random.uniform(*_CLOUD_COVER_PCT_RANGE),
        vegetation_index=random.uniform(*_VEGETATION_INDEX_RANGE),
        aerosol_index=random.uniform(*_AEROSOL_INDEX_RANGE),
    )
