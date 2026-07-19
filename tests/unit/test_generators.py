"""AT-1 (UC-1, FR-1): the generators produce schema-valid events.

This test imports no transport: only the generators and the models. A subprocess
check proves the generator import graph pulls in no transport or Kafka client, so
the pure generator path never triggers the transport import chain.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from climate_index.config import get_settings
from climate_index.core.generators import (
    _AEROSOL_INDEX_RANGE,
    _CLOUD_COVER_PCT_RANGE,
    _RAINFALL_MM_RANGE,
    _TEMPERATURE_C_RANGE,
    _VEGETATION_INDEX_RANGE,
    _WIND_SPEED_MS_RANGE,
    generate_satellite_event,
    generate_weather_event,
)
from climate_index.core.models import SatelliteEvent, WeatherEvent

REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLES = 100


def _in_range(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


def test_weather_generator_produces_valid_events_across_regions() -> None:
    for region in get_settings().region_list:
        for _ in range(_SAMPLES):
            event = generate_weather_event(region)
            assert isinstance(event, WeatherEvent)
            assert event.region == region
            assert event.ts.utcoffset() == timedelta(0)
            assert _in_range(event.temperature_c, _TEMPERATURE_C_RANGE)
            assert _in_range(event.rainfall_mm, _RAINFALL_MM_RANGE)
            assert _in_range(event.wind_speed_ms, _WIND_SPEED_MS_RANGE)


def test_satellite_generator_produces_valid_events_across_regions() -> None:
    for region in get_settings().region_list:
        for _ in range(_SAMPLES):
            event = generate_satellite_event(region)
            assert isinstance(event, SatelliteEvent)
            assert event.region == region
            assert event.ts.utcoffset() == timedelta(0)
            assert _in_range(event.cloud_cover_pct, _CLOUD_COVER_PCT_RANGE)
            assert _in_range(event.vegetation_index, _VEGETATION_INDEX_RANGE)
            assert _in_range(event.aerosol_index, _AEROSOL_INDEX_RANGE)


def test_generator_import_graph_has_no_transport_or_kafka() -> None:
    code = (
        "import sys\n"
        "import climate_index.core.generators\n"
        "bad = [m for m in sys.modules if 'kafka' in m "
        "or m.startswith('climate_index.adapters') "
        "or m == 'climate_index.interfaces.transport']\n"
        "assert not bad, bad\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("CII_")}
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
