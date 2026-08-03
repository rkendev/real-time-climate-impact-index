"""FR-11 OpenAQ station source: parsing, no fabrication, and failure isolation.

Every response shape comes from tests/unit/openaq_fixtures.py, where each literal
records whether it was observed against the live API or derived from one that
was. No shape here is written from a documentation page.

No network: httpx.MockTransport serves every call, as the Open-Meteo adapter's
tests already do.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from tests.unit.openaq_fixtures import (
    HOUR_COMPUTED_MEAN,
    HOUR_FLAGGED,
    HOUR_NEGATIVE,
    HOUR_NO_SAMPLES,
    HOUR_NULL_VALUE,
    HOUR_PROVIDER_HOURLY,
    UNAUTHORIZED,
    hours_page,
)

from climate_index.adapters.composite_source import CompositeEventSource
from climate_index.adapters.openaq.source import AdmittedSensor, OpenAQStationSource
from climate_index.config import Settings
from climate_index.core.models import Construction, StationObservation, WeatherEvent

BASE = "https://stations.invalid/v3"
NOW = datetime(2026, 8, 3, 14, 30, tzinfo=UTC)
SENSOR = AdmittedSensor(sensor_id=4235, station_id="80", city="Amsterdam", region="EUR")


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def event(self, name: str, **fields: Any) -> None:
        self.events.append((name, fields))

    def reasons(self) -> list[str]:
        return [f.get("reason", "") for n, f in self.events if n == "station_reading_unavailable"]


def _source(
    handler: Any, *, sensors: tuple[AdmittedSensor, ...] = (SENSOR,)
) -> tuple[OpenAQStationSource, _Recorder]:
    log = _Recorder()
    source = OpenAQStationSource(
        base_url=BASE,
        api_key="not-a-real-key",
        sensors=sensors,
        lag_hours=48,
        pace_s=0.0,
        logger=log,
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    return source, log


def _serving(payload: Any, status: int = 200) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def test_a_provider_hourly_value_becomes_one_observation() -> None:
    source, _ = _source(_serving(hours_page(HOUR_PROVIDER_HOURLY)))
    events = source.fetch_tick()
    assert len(events) == 1
    observation = events[0]
    assert isinstance(observation, StationObservation)
    assert observation.pm25_ugm3 == 2.7
    assert observation.sample_count == 1
    assert observation.construction is Construction.PROVIDER_HOURLY
    assert observation.region == "EUR"
    assert observation.station_id == "80"
    assert source.missing_count == 0


def test_a_computed_mean_is_recorded_as_such_and_still_emitted() -> None:
    """Recorded, never gated on: excluding the odd network after seeing it is the
    move the licence rule already had to correct."""
    source, _ = _source(_serving(hours_page(HOUR_COMPUTED_MEAN)))
    observation = source.fetch_tick()[0]
    assert observation.sample_count == 4
    assert observation.construction is Construction.COMPUTED_MEAN


def test_a_negative_reading_is_retained() -> None:
    source, _ = _source(_serving(hours_page(HOUR_NEGATIVE)))
    assert source.fetch_tick()[0].pm25_ugm3 == -3.4


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (hours_page(), "no_hour_returned"),
        (hours_page(HOUR_FLAGGED), "provider_flagged"),
        (hours_page(HOUR_NO_SAMPLES), "no_underlying_sample"),
        (hours_page(HOUR_NULL_VALUE), "missing_field"),
    ],
)
def test_an_unusable_hour_emits_nothing_and_is_counted(payload: Any, reason: str) -> None:
    """The no-fabrication rule: absent, flagged and empty are each their own cause."""
    source, log = _source(_serving(payload))
    assert source.fetch_tick() == []
    assert source.missing_count == 1
    assert log.reasons() == [reason]


@pytest.mark.parametrize(
    ("status", "reason"),
    [(429, "rate_limited"), (401, "http_status"), (500, "http_status")],
)
def test_a_non_success_is_counted_and_never_retried(status: int, reason: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json=UNAUTHORIZED)

    source, log = _source(handler)
    assert source.fetch_tick() == []
    assert calls == 1, "a 429 or error must not be retried in a loop"
    assert log.reasons() == [reason]


def test_a_timeout_is_counted_rather_than_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    source, log = _source(handler)
    assert source.fetch_tick() == []
    assert log.reasons() == ["timeout"]


def test_one_bad_sensor_does_not_cost_the_others() -> None:
    other = AdmittedSensor(sensor_id=118, station_id="79", city="Amsterdam", region="EUR")

    def handler(request: httpx.Request) -> httpx.Response:
        if "/sensors/4235/" in str(request.url):
            return httpx.Response(500, json={})
        return httpx.Response(200, json=hours_page(HOUR_PROVIDER_HOURLY))

    source, _ = _source(handler, sensors=(SENSOR, other))
    events = source.fetch_tick()
    assert [e.station_id for e in events] == ["79"]
    assert source.missing_count == 1


def test_the_settled_hour_respects_the_frozen_lag() -> None:
    source, _ = _source(_serving(hours_page()))
    assert source.settled_hour() == datetime(2026, 8, 1, 14, 0, tzinfo=UTC)


def test_from_settings_refuses_by_name_when_the_url_is_unset() -> None:
    settings = Settings(_env_file=None, openaq_api_key="x")
    with pytest.raises(ValueError, match="CII_OPENAQ_BASE_URL"):
        OpenAQStationSource.from_settings(settings, [SENSOR])


def test_from_settings_refuses_by_name_when_the_key_is_unset() -> None:
    settings = Settings(_env_file=None, openaq_base_url=BASE)
    with pytest.raises(ValueError, match="CII_OPENAQ_API_KEY"):
        OpenAQStationSource.from_settings(settings, [SENSOR])


def test_the_adapter_imports_no_http_client_at_module_scope() -> None:
    """INV-6: the client is imported lazily inside the run path."""
    import ast
    from pathlib import Path

    module = Path("src/climate_index/adapters/openaq/source.py")
    tree = ast.parse(module.read_text())
    top_level = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "httpx" not in top_level


# --------------------------------------------------------------------------
# The composite. A swallowed failure here would forge the project's headline.
# --------------------------------------------------------------------------


class _Raising:
    def fetch_tick(self) -> list[Any]:
        raise RuntimeError("the station provider is unreachable")


class _Working:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def fetch_tick(self) -> list[Any]:
        return list(self._events)


def _weather() -> WeatherEvent:
    return WeatherEvent(
        ts=NOW, region="EUR", temperature_c=20.0, rainfall_mm=0.0, wind_speed_ms=2.0
    )


def test_one_source_raising_does_not_stop_the_other() -> None:
    log = _Recorder()
    composite = CompositeEventSource(
        [("stations", _Raising()), ("model", _Working([_weather()]))], logger=log
    )
    events = composite.fetch_tick()
    assert [type(e).__name__ for e in events] == ["WeatherEvent"]


def test_a_raised_failure_is_counted_and_named() -> None:
    """It must be distinguishable from an absent reading.

    An absent reading is a fact about the world and is what the confidence and
    provenance grades read. A raised failure is a fact about this process and
    carries no information about coverage. Conflating them would let an adapter
    fault masquerade as the finding this project publishes.
    """
    log = _Recorder()
    composite = CompositeEventSource(
        [("stations", _Raising()), ("model", _Working([_weather()]))], logger=log
    )
    composite.fetch_tick()
    assert composite.source_failure_counts == {"stations": 1, "model": 0}
    assert [name for name, _ in log.events] == ["source_tick_failed"]
    assert log.events[0][1]["source"] == "stations"


def test_a_source_returning_nothing_is_not_counted_as_a_failure() -> None:
    """The distinction the counter exists to make, asserted from the other side."""
    composite = CompositeEventSource(
        [("stations", _Working([])), ("model", _Working([_weather()]))], logger=_Recorder()
    )
    assert len(composite.fetch_tick()) == 1
    assert composite.source_failure_counts == {"stations": 0, "model": 0}


def test_every_source_raising_yields_an_empty_tick_rather_than_an_exception() -> None:
    composite = CompositeEventSource([("a", _Raising()), ("b", _Raising())], logger=_Recorder())
    assert composite.fetch_tick() == []
    assert composite.source_failure_counts == {"a": 1, "b": 1}
