"""Open-Meteo source adapter (UC-1, ADR-0007).

Every test drives httpx.MockTransport, so nothing here dials the network. The
payload shapes are copied from real probe responses, including the detail that
matters most: the API returns a NAIVE ISO timestamp even when asked for
timezone=UTC, and the entity models reject naive datetimes.

The bulk of these tests are about what the adapter refuses to do. A timeout, an
error status, an error body, a missing field, a null field, and a schema
violation must each produce no event and a counted skip, because a gap is the
signal the confidence grader reads and a substituted value would corrupt it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from climate_index.adapters.openmeteo import OpenMeteoEventSource
from climate_index.config import CityLocation, Settings
from climate_index.core.models import SatelliteEvent, WeatherEvent
from climate_index.interfaces import EventSource

WEATHER_URL = "https://weather.invalid/v1/forecast"
AIR_URL = "https://air.invalid/v1/air-quality"

# A July timestamp, so the configured EUR July vegetation reference (0.58) is
# the one that lands on the satellite event.
NAIVE_TS = "2026-07-22T11:30"
EXPECTED_TS = datetime(2026, 7, 22, 11, 30, tzinfo=UTC)

# Shapes taken from live probe responses.
WEATHER_OK: dict[str, Any] = {
    "utc_offset_seconds": 0,
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "m/s"},
    "current": {
        "time": NAIVE_TS,
        "interval": 900,
        "temperature_2m": 17.4,
        "precipitation": 0.0,
        "wind_speed_10m": 5.1,
        "cloud_cover": 100,
    },
}
AIR_OK: dict[str, Any] = {
    "utc_offset_seconds": 0,
    "current": {"time": NAIVE_TS, "interval": 3600, "aerosol_optical_depth": 0.18},
}

ONE_CITY = {"EUR": [CityLocation(name="Amsterdam", latitude=52.3676, longitude=4.9041)]}


def _vegetation() -> dict[str, list[float]]:
    return {"EUR": Settings(_env_file=None).region_monthly_vegetation["EUR"]}


def _source(handler: Any, **kwargs: Any) -> OpenMeteoEventSource:
    """Build a one-city source whose every request is answered by ``handler``."""
    return OpenMeteoEventSource(
        weather_url=WEATHER_URL,
        air_quality_url=AIR_URL,
        locations=kwargs.pop("locations", ONE_CITY),
        monthly_vegetation=_vegetation(),
        regions=kwargs.pop("regions", ["EUR"]),
        timeout_s=1.0,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _router(weather: Any, air: Any) -> Any:
    """Answer the weather URL with one response and the air quality URL with another.

    Each side may be a dict (200 with that JSON), an httpx.Response, or an
    exception instance to raise.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        chosen = weather if str(request.url).startswith(WEATHER_URL) else air
        if isinstance(chosen, Exception):
            raise chosen
        if isinstance(chosen, httpx.Response):
            return chosen
        return httpx.Response(200, json=chosen)

    return handler


def test_it_satisfies_the_source_protocol_structurally() -> None:
    assert isinstance(_source(_router(WEATHER_OK, AIR_OK)), EventSource)


def test_a_good_tick_maps_both_streams_with_the_right_units() -> None:
    events = _source(_router(WEATHER_OK, AIR_OK)).fetch_tick()

    weather = [e for e in events if isinstance(e, WeatherEvent)]
    satellite = [e for e in events if isinstance(e, SatelliteEvent)]
    assert len(weather) == 1
    assert len(satellite) == 1

    assert weather[0].region == "EUR"
    assert weather[0].temperature_c == pytest.approx(17.4)
    # precipitation is mm and wind_speed_unit=ms yields m/s, so neither converts.
    assert weather[0].rainfall_mm == pytest.approx(0.0)
    assert weather[0].wind_speed_ms == pytest.approx(5.1)

    # Cloud cover comes from the FORECAST call, aerosol from the air quality one.
    assert satellite[0].cloud_cover_pct == pytest.approx(100.0)
    assert satellite[0].aerosol_index == pytest.approx(0.18)
    # Vegetation is the configured July reference, not anything fetched (E-3).
    assert satellite[0].vegetation_index == pytest.approx(_vegetation()["EUR"][6])


def test_the_naive_api_timestamp_becomes_utc_aware() -> None:
    """The API returns "2026-07-22T11:30" with no offset; the models reject naive."""
    events = _source(_router(WEATHER_OK, AIR_OK)).fetch_tick()
    for event in events:
        assert event.ts.tzinfo is not None
        assert event.ts.utcoffset() == EXPECTED_TS.utcoffset()
        assert event.ts == EXPECTED_TS


def test_a_non_utc_response_is_refused_rather_than_stamped_utc() -> None:
    """A non-zero offset means the clock is not UTC, so attaching UTC would shift it."""
    shifted = {**WEATHER_OK, "utc_offset_seconds": 7200}
    source = _source(_router(shifted, {**AIR_OK, "utc_offset_seconds": 7200}))
    assert source.fetch_tick() == []
    assert source.missing_count > 0


def test_a_timeout_yields_no_event_and_a_counter() -> None:
    source = _source(_router(httpx.TimeoutException("slow"), httpx.TimeoutException("slow")))
    assert source.fetch_tick() == []
    assert source.missing_count == 2


def test_an_error_status_yields_no_event_and_a_counter() -> None:
    source = _source(_router(httpx.Response(500), httpx.Response(500)))
    assert source.fetch_tick() == []
    assert source.missing_count == 2


def test_a_provider_error_body_yields_no_event() -> None:
    """A 200 carrying {"error": true} is how the API reports a bad variable."""
    error_body = {"error": True, "reason": "invalid variable"}
    source = _source(_router(error_body, error_body))
    assert source.fetch_tick() == []
    assert source.missing_count == 2


def test_a_null_field_yields_no_event_and_is_never_substituted() -> None:
    nulled = {**WEATHER_OK, "current": {**WEATHER_OK["current"], "temperature_2m": None}}
    source = _source(_router(nulled, AIR_OK))
    events = source.fetch_tick()

    # No weather event: the reading is absent, not zero and not interpolated.
    assert [e for e in events if isinstance(e, WeatherEvent)] == []
    assert source.missing_count == 1
    # The satellite event still forms: its inputs (cloud cover, aerosol) are intact.
    assert len([e for e in events if isinstance(e, SatelliteEvent)]) == 1


def test_a_missing_field_yields_no_event() -> None:
    without = {k: v for k, v in WEATHER_OK["current"].items() if k != "wind_speed_10m"}
    source = _source(_router({**WEATHER_OK, "current": without}, AIR_OK))
    assert [e for e in source.fetch_tick() if isinstance(e, WeatherEvent)] == []


def test_the_satellite_event_needs_both_calls() -> None:
    """Its cloud cover is from the forecast call and its aerosol from the other."""
    # Air quality fails, forecast succeeds: weather survives, pollution does not.
    source = _source(_router(WEATHER_OK, httpx.Response(503)))
    events = source.fetch_tick()
    assert len([e for e in events if isinstance(e, WeatherEvent)]) == 1
    assert [e for e in events if isinstance(e, SatelliteEvent)] == []

    # Forecast fails, air quality succeeds: neither survives, because the
    # satellite event has no cloud cover without the forecast payload.
    source = _source(_router(httpx.Response(503), AIR_OK))
    assert source.fetch_tick() == []


def test_a_schema_violating_payload_yields_no_event() -> None:
    """Negative rainfall violates the E-2 bound, so nothing half formed is published."""
    bad = {**WEATHER_OK, "current": {**WEATHER_OK["current"], "precipitation": -5.0}}
    source = _source(_router(bad, AIR_OK))
    assert [e for e in source.fetch_tick() if isinstance(e, WeatherEvent)] == []
    assert source.missing_count >= 1


def test_a_cloud_cover_out_of_range_yields_no_satellite_event() -> None:
    bad = {**WEATHER_OK, "current": {**WEATHER_OK["current"], "cloud_cover": 150}}
    source = _source(_router(bad, AIR_OK))
    events = source.fetch_tick()
    assert [e for e in events if isinstance(e, SatelliteEvent)] == []
    # The weather event is unaffected: cloud cover is not one of its fields.
    assert len([e for e in events if isinstance(e, WeatherEvent)]) == 1


def test_one_city_failing_does_not_erase_its_region() -> None:
    """The reason each city is fetched separately rather than batched."""
    cities = {
        "EUR": [
            CityLocation(name="Amsterdam", latitude=52.3676, longitude=4.9041),
            CityLocation(name="Berlin", latitude=52.52, longitude=13.405),
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        # Berlin's longitude appears in its query; fail only that city.
        if "13.405" in str(request.url):
            return httpx.Response(503)
        chosen = AIR_OK if str(request.url).startswith(AIR_URL) else WEATHER_OK
        return httpx.Response(200, json=chosen)

    source = _source(handler, locations=cities)
    events = source.fetch_tick()
    assert len(events) == 2  # Amsterdam's pair only
    assert {e.region for e in events} == {"EUR"}


def test_the_request_asks_for_the_verified_variables_and_units() -> None:
    """Pins the probe findings: cloud_cover (not cloud_cover_total), ms, UTC."""
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        chosen = AIR_OK if str(request.url).startswith(AIR_URL) else WEATHER_OK
        return httpx.Response(200, json=chosen)

    _source(handler).fetch_tick()

    weather_url = next(u for u in seen if str(u).startswith(WEATHER_URL))
    assert weather_url.params["current"] == (
        "temperature_2m,precipitation,wind_speed_10m,cloud_cover"
    )
    assert "cloud_cover_total" not in str(weather_url)
    assert weather_url.params["wind_speed_unit"] == "ms"
    assert weather_url.params["timezone"] == "UTC"

    air_url = next(u for u in seen if str(u).startswith(AIR_URL))
    assert air_url.params["current"] == "aerosol_optical_depth"
    assert air_url.params["timezone"] == "UTC"


def test_from_settings_refuses_when_an_endpoint_is_unset() -> None:
    """No URL literal lives in source, so an unset endpoint fails loudly (INV-1)."""
    with pytest.raises(ValueError, match="CII_OPEN_METEO"):
        OpenMeteoEventSource.from_settings(Settings(_env_file=None))


def test_it_refuses_a_region_with_no_configured_locations() -> None:
    with pytest.raises(ValueError, match="no configured locations"):
        _source(_router(WEATHER_OK, AIR_OK), regions=["NAM"])


# ---------------------------------------------------------------------------
# Historical fetch (the live demo backfill)
# ---------------------------------------------------------------------------

HOURLY_WEATHER: dict[str, Any] = {
    "utc_offset_seconds": 0,
    "hourly": {
        "time": ["2026-07-22T09:00", "2026-07-22T10:00", "2026-07-22T11:00"],
        "temperature_2m": [16.0, 17.0, 18.0],
        "precipitation": [0.0, 0.1, 0.0],
        "wind_speed_10m": [4.0, 4.5, 5.0],
        "cloud_cover": [80, 90, 100],
    },
}
HOURLY_AIR: dict[str, Any] = {
    "utc_offset_seconds": 0,
    "hourly": {
        "time": ["2026-07-22T09:00", "2026-07-22T10:00", "2026-07-22T11:00"],
        "aerosol_optical_depth": [0.20, 0.21, 0.22],
    },
}
CUTOFF = datetime(2026, 7, 22, 11, 30, tzinfo=UTC)


def test_history_emits_a_pair_per_hourly_slot() -> None:
    source = _source(_router(HOURLY_WEATHER, HOURLY_AIR))
    events = source.fetch_history(not_after=CUTOFF)

    assert len(events) == 6  # three hours, two streams
    weather = sorted((e for e in events if isinstance(e, WeatherEvent)), key=lambda e: e.ts)
    assert [e.ts.hour for e in weather] == [9, 10, 11]
    assert [e.temperature_c for e in weather] == pytest.approx([16.0, 17.0, 18.0])
    for event in events:
        assert event.ts.tzinfo is not None


def test_history_excludes_future_hours() -> None:
    """Publishing a forecast value as a reading would be its own fabrication."""
    source = _source(_router(HOURLY_WEATHER, HOURLY_AIR))
    events = source.fetch_history(not_after=datetime(2026, 7, 22, 10, 0, tzinfo=UTC))
    hours = {e.ts.hour for e in events}
    assert hours == {9, 10}
    assert 11 not in hours


def test_a_null_in_an_hourly_array_skips_only_that_slot() -> None:
    """The no-fabrication rule per slot: never interpolated from its neighbours."""
    holed = {
        **HOURLY_WEATHER,
        "hourly": {**HOURLY_WEATHER["hourly"], "temperature_2m": [16.0, None, 18.0]},
    }
    source = _source(_router(holed, HOURLY_AIR))
    events = source.fetch_history(not_after=CUTOFF)

    weather = [e for e in events if isinstance(e, WeatherEvent)]
    assert [e.ts.hour for e in weather] == [9, 11]
    # The 10:00 temperature is absent, not averaged from 16.0 and 18.0.
    assert all(e.temperature_c != pytest.approx(17.0) for e in weather)
    assert source.missing_count >= 1


def test_a_null_aerosol_hour_drops_only_the_satellite_event() -> None:
    holed = {
        **HOURLY_AIR,
        "hourly": {**HOURLY_AIR["hourly"], "aerosol_optical_depth": [0.20, None, 0.22]},
    }
    source = _source(_router(HOURLY_WEATHER, holed))
    events = source.fetch_history(not_after=CUTOFF)

    assert [e.ts.hour for e in events if isinstance(e, WeatherEvent)] == [9, 10, 11]
    assert [e.ts.hour for e in events if isinstance(e, SatelliteEvent)] == [9, 11]


def test_history_aligns_the_two_series_by_timestamp_not_by_position() -> None:
    """The air series starts an hour later, so only the shared hours pair up."""
    offset_air = {
        **HOURLY_AIR,
        "hourly": {
            "time": ["2026-07-22T10:00", "2026-07-22T11:00"],
            "aerosol_optical_depth": [0.21, 0.22],
        },
    }
    source = _source(_router(HOURLY_WEATHER, offset_air))
    events = source.fetch_history(not_after=CUTOFF)

    satellite = sorted((e for e in events if isinstance(e, SatelliteEvent)), key=lambda e: e.ts)
    assert [e.ts.hour for e in satellite] == [10, 11]
    # 10:00 gets 0.21, which is only true if alignment is by time, not index.
    assert satellite[0].aerosol_index == pytest.approx(0.21)


def test_history_asks_for_past_days() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        chosen = HOURLY_AIR if str(request.url).startswith(AIR_URL) else HOURLY_WEATHER
        return httpx.Response(200, json=chosen)

    _source(handler).fetch_history(past_days=2, not_after=CUTOFF)
    for url in seen:
        assert url.params["past_days"] == "2"
        assert "hourly" in url.params
