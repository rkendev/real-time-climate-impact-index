"""Composition root for the event source (UC-1, INV-6, ADR-0007).

The factory returns the simulated adapter by default and the Open-Meteo adapter
for the real backend, both behind the same EventSource Protocol, and refuses an
unknown name. It also has to stay client-free at import time, so importing it
(and selecting the simulated branch) must pull in no HTTP client.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from climate_index.adapters.openmeteo import OpenMeteoEventSource
from climate_index.adapters.simulated import SimulatedEventSource
from climate_index.config import Settings
from climate_index.interfaces import EventSource
from climate_index.source_factory import build_event_source

REAL_URLS = {
    "open_meteo_weather_url": "https://weather.invalid/v1/forecast",
    "open_meteo_air_quality_url": "https://air.invalid/v1/air-quality",
}


def test_the_default_backend_is_the_simulated_source() -> None:
    source = build_event_source(Settings(_env_file=None))
    assert isinstance(source, EventSource)
    assert isinstance(source, SimulatedEventSource)


def test_the_real_backend_returns_the_open_meteo_source() -> None:
    """Construction alone dials nothing: the client is lazy, so no mock is needed."""
    settings = Settings(_env_file=None, source_backend="real", **REAL_URLS)
    source = build_event_source(settings)
    assert isinstance(source, EventSource)
    assert isinstance(source, OpenMeteoEventSource)


def test_an_unknown_backend_is_refused() -> None:
    settings = Settings(_env_file=None, source_backend="teleport")
    with pytest.raises(ValueError, match="unknown source backend"):
        build_event_source(settings)


def test_the_real_backend_refuses_without_its_endpoints() -> None:
    """No URL literal lives in source, so an unset endpoint fails loudly (INV-1)."""
    settings = Settings(_env_file=None, source_backend="real")
    with pytest.raises(ValueError, match="CII_OPEN_METEO"):
        build_event_source(settings)


def test_the_source_is_built_for_the_regions_it_is_given() -> None:
    source = build_event_source(Settings(_env_file=None), ["EUR", "NAM"])
    assert isinstance(source, SimulatedEventSource)
    assert source.regions == ("EUR", "NAM")
    assert {event.region for event in source.fetch_tick()} == {"EUR", "NAM"}


def test_importing_the_factory_pulls_in_no_http_client() -> None:
    """INV-6 in practice: the adapters keep their clients lazy, so the root stays clean.

    Run in a fresh interpreter, because any earlier test in this session may
    already have imported httpx for its own mock transport.
    """
    script = (
        "import sys;"
        "import climate_index.source_factory as f;"
        "from climate_index.config import Settings;"
        "f.build_event_source(Settings(_env_file=None));"
        "print('httpx' in sys.modules)"
    )
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", result.stdout
