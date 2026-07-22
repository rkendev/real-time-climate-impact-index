"""Typed settings object, populated entirely from the environment (INV-1).

This module is the single authority for every connection detail, path, the
region set (E-1), the per-region baselines, the index weights and thresholds
(E-7), the window size, the log level, and the wording the read-only dashboard
explains itself with (UC-5). No secret or endpoint literal, and no copy of these
structural constants, appears anywhere else in the codebase. The example values
are mirrored in .env.example for local overrides.

INV-1 / NFR-SEC1: connection and endpoint fields carry no literal value here.
They default to None (or to a plain filesystem path, which is neither an
endpoint nor a secret) and are populated from the environment when a concrete
adapter needs them in a later phase. The one URL that does carry a default is
the public source repository link the dashboard renders: a documentation
pointer, never dialled by the code and never a credential.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Calendar months in a year. The monthly reference tables below carry exactly
# this many entries per region, index 0 being January (E-7).
MONTHS_IN_YEAR = 12


class CityLocation(BaseModel):
    """One representative city for a region: a name and its coordinates (E-7).

    Structural reference data, like the baselines, not a connection detail: a
    latitude and longitude are neither an endpoint nor a secret (INV-1). The
    real event source fetches one reading per city per stream, so a region's
    cities are its sampling points and a window normally holds several events
    per region (UC-1, ADR-0007).
    """

    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


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

    # E-7 representative cities per region: the sampling points the real event
    # source fetches (UC-1, ADR-0007). Three per region, so one city failing to
    # answer thins a window rather than emptying it, and the sparsity and
    # composition rules keep doing real work. Adding a city is configuration,
    # not code (NFR-S1). Coordinates are structural reference data, like the
    # baselines below; neither an endpoint nor a secret (INV-1).
    region_locations: dict[str, list[CityLocation]] = Field(
        default_factory=lambda: {
            "EUR": [
                CityLocation(name="Amsterdam", latitude=52.3676, longitude=4.9041),
                CityLocation(name="Berlin", latitude=52.5200, longitude=13.4050),
                CityLocation(name="Madrid", latitude=40.4168, longitude=-3.7038),
            ],
            "NAM": [
                CityLocation(name="New York", latitude=40.7128, longitude=-74.0060),
                CityLocation(name="Chicago", latitude=41.8781, longitude=-87.6298),
                CityLocation(name="Los Angeles", latitude=34.0522, longitude=-118.2437),
            ],
            "AFR": [
                CityLocation(name="Lagos", latitude=6.5244, longitude=3.3792),
                CityLocation(name="Nairobi", latitude=-1.2921, longitude=36.8219),
                CityLocation(name="Cairo", latitude=30.0444, longitude=31.2357),
            ],
            "ASI": [
                CityLocation(name="Tokyo", latitude=35.6762, longitude=139.6503),
                CityLocation(name="Delhi", latitude=28.6139, longitude=77.2090),
                CityLocation(name="Jakarta", latitude=-6.2088, longitude=106.8456),
            ],
        }
    )

    # E-7 per-region monthly temperature normals, degrees Celsius, one value per
    # calendar month with January first. These replace the single annual scalar
    # above: the anomaly for a window is its mean temperature minus the normal
    # for the window's own month, so a July window is measured against July.
    #
    # Derived, not invented, by exactly the recipe spec E-7 records: for each
    # region, the mean of its three cities above, where a city's monthly value is
    # the mean of ERA5 daily mean temperature over 1991-01-01 to 2020-12-31 from
    # the Open-Meteo archive endpoint. scripts/derive_climatology.py regenerates
    # them; the spec records the parameters so the numbers are reproducible
    # without it. One mechanism serves both configured sources (UC-1).
    region_monthly_baselines: dict[str, list[float]] = Field(
        default_factory=lambda: {
            "EUR": [3.1, 3.9, 6.7, 10.3, 14.5, 18.4, 21.1, 20.9, 16.9, 12.0, 7.1, 4.0],
            "NAM": [2.4, 3.1, 6.5, 11.2, 16.1, 20.9, 23.9, 23.7, 20.8, 15.2, 9.4, 4.5],
            "AFR": [20.1, 21.0, 22.1, 22.9, 23.7, 23.9, 23.7, 23.7, 23.7, 23.1, 21.6, 20.3],
            "ASI": [14.3, 15.7, 18.8, 22.7, 25.7, 26.9, 27.1, 27.2, 25.9, 23.2, 19.5, 15.9],
        }
    )

    # E-3 per-region monthly vegetation reference, one value per calendar month,
    # January first. Used by the real event source only, which has no live
    # per-coordinate vegetation feed available at this integration cost
    # (ADR-0007). Unlike the temperature normals above these are NOT derived
    # from a dataset: they are approximate published seasonal climatology,
    # inside the E-3 schema bound of minus one to one, and the specification,
    # the ADR, and the dashboard notice all state that they are a configured
    # reference and not a measurement. Nothing may present them as observed.
    region_monthly_vegetation: dict[str, list[float]] = Field(
        default_factory=lambda: {
            # Temperate, strong growing season.
            "EUR": [0.26, 0.27, 0.33, 0.44, 0.54, 0.58, 0.58, 0.55, 0.48, 0.38, 0.30, 0.26],
            # Temperate with an arid member, so a slightly lower summer peak.
            "NAM": [0.23, 0.24, 0.30, 0.42, 0.53, 0.58, 0.58, 0.56, 0.48, 0.37, 0.28, 0.24],
            # Mixed tropical and arid, so the weakest seasonal swing of the four.
            "AFR": [0.36, 0.36, 0.38, 0.42, 0.44, 0.43, 0.41, 0.40, 0.41, 0.43, 0.41, 0.38],
            # Monsoon driven, so the peak lags into late summer.
            "ASI": [0.34, 0.34, 0.37, 0.43, 0.50, 0.56, 0.61, 0.62, 0.58, 0.50, 0.42, 0.36],
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

    # NFR-DQ2 sparsity threshold: a window with fewer than this many validated
    # events is graded AMBIGUOUS regardless of stream composition. A config
    # constant, not a literal buried in the compute core.
    sparsity_min_events: int = 2

    # E-7 formula shape constants. The spec leaves the exact bounded form of the
    # dryness, pollution, and temperature-anomaly normalization to the
    # implementation; these are the tunable saturation points of the chosen form
    # and live here so the compute core carries no magic numbers. Documented in
    # core/features.py and flagged for a possible spec update.
    #
    # Rainfall (mm) at or above which the rain sub-score of dryness saturates to
    # zero (fully wet). Below it, dryness rises linearly toward one at zero rain.
    dryness_rainfall_saturation_mm: float = 20.0
    # Aerosol index at or above which the aerosol sub-score of pollution
    # saturates to one. Below it the sub-score scales linearly from zero.
    pollution_aerosol_saturation: float = 2.0
    # Temperature anomaly (degrees C above baseline) at or above which the heat
    # contribution to the impact index saturates to one. Cooler-than-baseline
    # windows contribute zero.
    temperature_anomaly_scale_c: float = 10.0

    # UC-5 display framing. The read-only dashboard states no definition of its
    # own: every explanatory phrase it shows is one of these constants, and each
    # traces to the specification. The index scale and direction come from spec
    # E-5 (impact_index, normalized zero to one hundred) and E-7 (the weighted
    # combination of the three component metrics). Text, neither an endpoint nor
    # a secret. The label bands are not repeated here: the page renders them from
    # ``label_thresholds`` above, which stays their single authority.
    index_summary: str = (
        "The Climate Impact Index scores each region from 0 to 100 by combining a temperature "
        "anomaly, a dryness index, and a pollution index. Higher means greater climate impact."
    )
    index_axis_label: str = "Impact index (0 to 100)"
    # How a window start is written on the chart's time axis. The label is
    # produced on the server from the stored UTC instant and handed to the chart
    # as a plain category, because a datetime handed to the browser is localized
    # there: an axis titled UTC would then show the viewer's own clock. A 24 hour
    # pattern, so the newest tick states the same instant as the freshness line.
    window_axis_time_format: str = "%H:%M"
    # The two mode-accurate feed notices (UC-5). The dashboard renders whichever
    # one matches ``source_backend``; it selects, it does not compose. Keeping
    # both here means the page can never state a provenance the pipeline is not
    # actually running.
    simulated_feed_notice: str = (
        "The feed is simulated: weather and satellite readings are generated by the producer, "
        "not collected from real world observations."
    )
    # Deliberately says "readings" and not "observations": the weather and air
    # quality products behind the real source are model analyses, not station
    # measurements, and this page does not overclaim. It also states the
    # vegetation term honestly (E-3) and states what a missing reading does,
    # because that is the whole reason the confidence grade is worth reading.
    real_feed_notice: str = (
        "The feed is real: hourly weather and air quality readings for representative cities in "
        "each region, fetched from Open-Meteo and republished on the refresh cadence into hourly "
        "windows. The vegetation term is a monthly reference value from configuration, not a "
        "reading. A reading that fails to arrive is left out rather than filled in, which is what "
        "lowers a window's confidence grade."
    )
    # Attribution the real source's terms require, rendered in the about panel.
    source_attribution: str = (
        "Weather and air quality data by Open-Meteo. Atmospheric composition from the "
        "CAMS ENSEMBLE data provider."
    )

    # NFR-DQ2 confidence tiers and what drives each, in descending order of
    # provenance strength. The keys are the grades stored on every aggregate row
    # (E-5); the glosses restate the rule that core/confidence.py applies, so the
    # page can explain a grade without computing one.
    confidence_tier_glosses: dict[str, str] = Field(
        default_factory=lambda: {
            "MEASURED": "both stream types present in the window",
            "INFERRED": "one stream type only, so a component is imputed",
            "AMBIGUOUS": "fewer validated events than the sparsity threshold",
        }
    )

    # NFR-DQ2 tier colours for the dashboard's confidence strip, keyed like the
    # glosses above and held here as their single authority (INV-1). They read the
    # way a viewer expects without consulting the legend: the strongest tier calm
    # (teal), the imputed tier amber, the sparse tier warm red. Teal rather than
    # green so the strongest and weakest stay apart under red/green colour vision
    # deficiency. Presentation only: a colour never feeds or alters a grade.
    confidence_tier_colors: dict[str, str] = Field(
        default_factory=lambda: {
            "MEASURED": "#2C7A7B",
            "INFERRED": "#B7791F",
            "AMBIGUOUS": "#C0392B",
        }
    )

    # UC-1 to UC-5 in one line, for the dashboard's about panel.
    pipeline_summary: str = (
        "The configured source publishes to Kafka, a deterministic gate validates or quarantines "
        "each event, the processor buckets events into event-time windows and computes the index "
        "with its confidence grade, and this page reads the published snapshot read-only."
    )

    # Public source repository for the about panel. A published documentation
    # link, not a service endpoint the code connects to and not a secret: nothing
    # here is dialled, it is rendered as a link (INV-1).
    source_repository_url: str = "https://github.com/rkendev/real-time-climate-impact-index"

    # How often the live demo republishes its snapshot, as a systemd time span.
    # The demo environment file carries the operative value and the dashboard unit
    # loads it, so the page states the cadence actually in force rather than a
    # guess. The default matches the tracked demo.env.example.
    demo_refresh_interval: str = "30min"

    # Share of the demo backfill's windows that receive sparser coverage, so the
    # committed confidence computation grades them below the top tier and the
    # provenance signal is visible on the page (NFR-DQ2, NFR-R4). A demo input
    # knob only: it varies what the feeder publishes, never what a grade says.
    demo_degraded_window_fraction: float = 0.25

    # NFR-O1 log verbosity for the structured logger.
    log_level: str = "INFO"

    # Which event source the composition root builds (see
    # climate_index.source_factory), the same shape as aggregate_backend below.
    # "simulated" is the default, so with nothing set the producer, the smoke
    # checks, and the local quickstart stay offline and deterministic exactly as
    # before. "real" builds the Open-Meteo fetch adapter (UC-1, ADR-0007). A
    # backend name, not an endpoint or a secret.
    source_backend: str = "simulated"

    # Connection details: no endpoint or secret literal (INV-1). Populated from
    # the environment when a concrete transport/store adapter runs (Phase 2).
    transport_bootstrap_servers: str | None = None

    # Real event source endpoints (ADR-0007). None until set per environment,
    # exactly like transport_bootstrap_servers above: no URL literal appears in
    # source (INV-1), and the example values live in .env.example and in the
    # git-ignored demo environment only. The real source refuses to run rather
    # than guessing when either is unset.
    open_meteo_weather_url: str | None = None
    open_meteo_air_quality_url: str | None = None

    # How long a single source fetch may take before it counts as a miss. A miss
    # emits no event and is logged and counted; it is never retried in a loop and
    # never replaced with a substituted value (UC-1 no-fabrication rule).
    source_fetch_timeout_s: float = 10.0

    # When true, the consumer entry point drains the broker once and exits instead
    # of looping. The container consumer role loops by default (a live service);
    # the offline broker smoke sets this so a single drain is deterministic.
    consumer_oneshot: bool = False

    # Local store locations. A relative filesystem path is neither an endpoint
    # nor a secret; example overrides live in .env.example.
    raw_store_path: Path = Path("data/raw")
    aggregate_store_path: Path = Path("data/aggregates.duckdb")

    # Which aggregate-store backend the composition root builds (see
    # climate_index.store_factory). "duckdb" is the local default; "aws" builds
    # the S3 Iceberg aggregate-of-record fanned out to the DynamoDB serving store
    # (ADR-0003). A backend name, not an endpoint or secret.
    aggregate_backend: str = "duckdb"

    # Phase 2 AWS connection details (INV-1): no endpoint, bucket, table, or
    # secret literal here. The region and endpoint override default to None and
    # are populated from the environment when an AWS adapter runs. The endpoint
    # override is None in production (real AWS) and set only by the test fixture
    # (the moto server URL).
    aws_region: str | None = None
    aws_endpoint_url: str | None = None

    # Cost-allocation tag value (ADR-0005), the single definition of the project
    # tag. The teardown audit (AT-11) filters on it, and Terraform receives the
    # same value through TF_VAR_project_tag injected from this field by the Make
    # targets, so the tag the audit checks and the tag applied to resources
    # cannot drift. A plain structural label, neither an endpoint nor a secret.
    project_tag: str = "climate-index"

    # S3 Iceberg aggregate-of-record (ADR-0003). The warehouse bucket is a
    # connection detail (None until provisioned); the namespace and table name
    # are plain structural identifiers, neither endpoints nor secrets, so they
    # carry authoritative defaults here. The catalog properties select and
    # configure the catalog: the pyiceberg SQL (SQLite) catalog in tests versus
    # the Glue catalog on AWS. Supplied as JSON, like the other dict fields.
    iceberg_warehouse_bucket: str | None = None
    iceberg_namespace: str = "climate_index"
    iceberg_table: str = "climate_index"
    iceberg_catalog_properties: dict[str, str] = Field(default_factory=dict)

    # DynamoDB serving store (ADR-0003). The table name is a connection detail,
    # None until provisioned; the key model (pk region, sk window_start) is fixed
    # in the adapter, not configured.
    dynamo_table: str | None = None

    # S3 raw store (FR-7). The bucket is a connection detail (None until
    # provisioned); the prefix under it is a plain path segment, so it defaults.
    raw_s3_bucket: str | None = None
    raw_s3_prefix: str = "raw"

    @property
    def region_list(self) -> tuple[str, ...]:
        """The configured regions as an ordered tuple of non-empty codes."""
        return tuple(code.strip() for code in self.regions.split(",") if code.strip())

    @model_validator(mode="after")
    def _check_monthly_tables(self) -> Settings:
        """Every monthly reference row is twelve long and inside its schema bound.

        This checks the shape of the tables, not that they cover ``region_list``.
        Coverage is deliberately left to the point of use: a region set can be
        overridden from the environment for a test or a narrow deployment
        without having to restate every reference table, and the real event
        source refuses to start with a named error when a region it is asked to
        fetch has no locations. A silently short row, by contrast, would produce
        a wrong anomaly rather than an error, so it is caught here.
        """
        for name, table in (
            ("region_monthly_baselines", self.region_monthly_baselines),
            ("region_monthly_vegetation", self.region_monthly_vegetation),
        ):
            for region, values in table.items():
                if len(values) != MONTHS_IN_YEAR:
                    raise ValueError(
                        f"{name}[{region!r}] must hold {MONTHS_IN_YEAR} monthly values, "
                        f"got {len(values)}"
                    )
        for region, values in self.region_monthly_vegetation.items():
            if not all(-1.0 <= value <= 1.0 for value in values):
                raise ValueError(
                    f"region_monthly_vegetation[{region!r}] holds a value outside the "
                    "E-3 bound of minus one to one"
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance populated from the environment."""
    return Settings()
