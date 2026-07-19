"""Typed settings object, populated entirely from the environment (INV-1).

This module is the single authority for every connection detail, path, the
region set (E-1), the per-region baselines, the index weights and thresholds
(E-7), the window size, and the log level. No secret or endpoint literal, and no
copy of these structural constants, appears anywhere else in the codebase. The
example values are mirrored in .env.example for local overrides.

INV-1 / NFR-SEC1: connection and endpoint fields carry no literal value here.
They default to None (or to a plain filesystem path, which is neither an
endpoint nor a secret) and are populated from the environment when a concrete
adapter needs them in a later phase.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-populated settings for the climate_index pipeline.

    Every field reads from an environment variable prefixed ``CII_`` (for
    example ``CII_WINDOW_MINUTES``), optionally sourced from a local ``.env``
    file. Structural constants (regions, baselines, weights, thresholds) keep
    their authoritative defaults here; connection details do not.
    """

    model_config = SettingsConfigDict(
        env_prefix="CII_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # E-1 RegionCode set. A comma-separated string so env parsing stays simple
    # (no JSON needed); adding a region is a configuration change, not code
    # (NFR-S1). Use ``region_list`` for the parsed tuple.
    regions: str = "EUR,NAM,AFR,ASI"

    # E-7 per-region temperature normal baselines (degrees Celsius). The mean
    # temperature in a window minus this baseline is the temperature anomaly.
    region_baselines: dict[str, float] = Field(
        default_factory=lambda: {
            "EUR": 12.0,
            "NAM": 14.0,
            "AFR": 24.0,
            "ASI": 20.0,
        }
    )

    # E-7 index weights: the weighted combination of the three component metrics
    # that forms the impact index. Keys are the component names.
    index_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "temperature_anomaly": 0.4,
            "dryness_index": 0.3,
            "pollution_index": 0.3,
        }
    )

    # E-7 / FR-9 verbal-label band boundaries on the 0..100 index. Values at or
    # below ``low_max`` are "low"; at or below ``medium_max`` are "medium"; above
    # are "high".
    label_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "low_max": 33.34,
            "medium_max": 66.67,
        }
    )

    # FR-5 event-time tumbling window size in minutes.
    window_minutes: int = 30

    # NFR-O1 log verbosity for the structured logger.
    log_level: str = "INFO"

    # Connection details: no endpoint or secret literal (INV-1). Populated from
    # the environment when a concrete transport/store adapter runs (Phase 2).
    transport_bootstrap_servers: str | None = None

    # Local store locations. A relative filesystem path is neither an endpoint
    # nor a secret; example overrides live in .env.example.
    raw_store_path: Path = Path("data/raw")
    aggregate_store_path: Path = Path("data/aggregates.duckdb")

    @property
    def region_list(self) -> tuple[str, ...]:
        """The configured regions as an ordered tuple of non-empty codes."""
        return tuple(code.strip() for code in self.regions.split(",") if code.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance populated from the environment."""
    return Settings()
