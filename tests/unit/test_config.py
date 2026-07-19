"""Config reads every value from the environment and holds no endpoint literal.

Covers E-1 (region set), E-7 (baselines, weights, thresholds), the window size,
and the log level, plus the INV-1 property that the transport endpoint has no
default literal (it is populated from the environment only).
"""

from __future__ import annotations

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
