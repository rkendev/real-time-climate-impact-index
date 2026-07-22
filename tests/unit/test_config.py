"""Config reads every value from the environment and holds no endpoint literal.

Covers E-1 (region set), E-7 (baselines, weights, thresholds), the window size,
and the log level, plus the INV-1 property that the transport endpoint has no
default literal (it is populated from the environment only).
"""

from __future__ import annotations

import re

import pytest

from climate_index.config import Settings


def test_defaults_are_the_single_authority() -> None:
    settings = Settings(_env_file=None)
    assert settings.region_list == ("EUR", "NAM", "AFR", "ASI")
    assert settings.window_minutes == 30
    assert settings.log_level == "INFO"
    assert set(settings.index_weights) == {
        "temperature_anomaly",
        "dryness_index",
        "pollution_index",
    }
    assert set(settings.label_thresholds) == {"low_max", "medium_max"}
    assert settings.region_baselines["EUR"] == 12.0


def test_display_constants_are_the_single_authority(  # UC-5, NFR-DQ2
) -> None:
    settings = Settings(_env_file=None)
    # The page's plain-language framing states the scale and the direction (E-5, E-7).
    assert "0 to 100" in settings.index_summary
    assert "Higher means" in settings.index_summary
    assert "simulated" in settings.simulated_feed_notice.lower()
    # The tier glosses cover exactly the three grades an aggregate row can carry.
    assert set(settings.confidence_tier_glosses) == {"MEASURED", "INFERRED", "AMBIGUOUS"}
    assert all(gloss for gloss in settings.confidence_tier_glosses.values())
    # Every tier the page can show has a colour, keyed and ordered like the
    # glosses, so the strip cannot colour a grade the legend does not name.
    assert list(settings.confidence_tier_colors) == list(settings.confidence_tier_glosses)
    assert all(
        re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
        for color in settings.confidence_tier_colors.values()
    )
    # The chart's time axis is written on the server on a 24 hour clock, so a
    # window at 14:00 UTC can never read as 2 PM in someone's local afternoon.
    assert "%H" in settings.window_axis_time_format
    assert "%M" in settings.window_axis_time_format
    assert "%I" not in settings.window_axis_time_format
    assert "%p" not in settings.window_axis_time_format
    assert settings.pipeline_summary
    assert settings.source_repository_url.startswith("https://")
    assert settings.demo_refresh_interval
    # A minority share, so the demo keeps a top-tier majority.
    assert 0.0 < settings.demo_degraded_window_fraction < 0.5


def test_monthly_reference_tables_are_the_single_authority() -> None:  # E-7, E-3
    settings = Settings(_env_file=None)
    for region in settings.region_list:
        # Twelve values per region, January first, for both monthly tables.
        assert len(settings.region_monthly_baselines[region]) == 12
        assert len(settings.region_monthly_vegetation[region]) == 12
        # Every vegetation reference sits inside the E-3 schema bound.
        assert all(-1.0 <= value <= 1.0 for value in settings.region_monthly_vegetation[region])
        # Three sampling cities, so one city failing thins a window, not empties it.
        assert len(settings.region_locations[region]) == 3
        for city in settings.region_locations[region]:
            assert city.name
            assert -90.0 <= city.latitude <= 90.0
            assert -180.0 <= city.longitude <= 180.0
    # The derived normals carry a real seasonal swing rather than a flat scalar,
    # which is the whole point of replacing the annual baseline.
    northern = settings.region_monthly_baselines["EUR"]
    assert max(northern) - min(northern) > 10.0
    # July is warmer than January in both northern-hemisphere region sets.
    for region in ("EUR", "NAM"):
        assert (
            settings.region_monthly_baselines[region][6]
            > (settings.region_monthly_baselines[region][0])
        )


def test_a_short_monthly_row_is_rejected() -> None:
    """A silently short row would yield a wrong anomaly, not an error, so it fails."""
    with pytest.raises(ValueError, match="12 monthly values"):
        Settings(_env_file=None, region_monthly_baselines={"EUR": [1.0, 2.0, 3.0]})


def test_an_out_of_bound_vegetation_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="minus one to one"):
        Settings(_env_file=None, region_monthly_vegetation={"EUR": [2.0] * 12})


def test_source_backend_defaults_to_simulated_with_no_endpoint_literals() -> None:
    """The default is offline and deterministic, and carries no URL (INV-1)."""
    settings = Settings(_env_file=None)
    assert settings.source_backend == "simulated"
    assert settings.open_meteo_weather_url is None
    assert settings.open_meteo_air_quality_url is None
    assert settings.source_fetch_timeout_s > 0


def test_both_feed_notices_are_mode_accurate() -> None:  # UC-5
    settings = Settings(_env_file=None)
    assert "simulated" in settings.simulated_feed_notice.lower()
    real = settings.real_feed_notice.lower()
    # Says readings, never observations: the products behind the real source are
    # model analyses, not station measurements, and the page does not overclaim.
    assert "readings" in real
    assert "observation" not in real
    # States the vegetation term honestly (E-3) and what a missing reading does.
    assert "vegetation" in real
    assert "not a reading" in real
    assert "left out rather than filled in" in real
    # The provider attribution the source's terms require.
    assert "Open-Meteo" in settings.source_attribution
    assert "CAMS" in settings.source_attribution


def test_transport_endpoint_has_no_literal_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.transport_bootstrap_servers is None


def test_env_overrides_scalars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CII_WINDOW_MINUTES", "15")
    monkeypatch.setenv("CII_REGIONS", "AAA, BBB , CCC")
    monkeypatch.setenv("CII_LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert settings.window_minutes == 15
    assert settings.region_list == ("AAA", "BBB", "CCC")
    assert settings.log_level == "DEBUG"


def test_env_overrides_json_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CII_INDEX_WEIGHTS",
        '{"temperature_anomaly": 1.0, "dryness_index": 0.0, "pollution_index": 0.0}',
    )
    settings = Settings(_env_file=None)
    assert settings.index_weights["temperature_anomaly"] == 1.0
    assert settings.index_weights["pollution_index"] == 0.0
