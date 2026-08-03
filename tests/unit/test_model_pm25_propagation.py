"""E-5 model PM2.5: the field reaches every surface, and a null stays absent.

The value is a reported summary of the model side (spec E-5). It is nullable
because a window with no satellite event has none, and because every row written
before the field existed has none: backfilling the shipped index is out of scope
per the contract frozen in PREREGISTRATION.md at b81f1c9.

The load-bearing property here is that a null is never rendered or stored as a
number. A null shown as a value is a fabricated measurement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest

from climate_index.adapters.aws._dynamo import from_item, to_item
from climate_index.adapters.duckdb._schema import AGGREGATE_COLUMNS
from climate_index.adapters.duckdb.reader import DuckDBReadOnlyAggregateStore
from climate_index.adapters.duckdb.store import DuckDBAggregateStore
from climate_index.core.engine import compute_records
from climate_index.core.models import SatelliteEvent, WeatherEvent

TS = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

# The aggregate column set exactly as it shipped before this field existed. Used
# to build an old-format database file, so the migration is tested against a real
# old file rather than against a description of one.
LEGACY_COLUMNS = (
    "region",
    "window_start",
    "window_end",
    "impact_index",
    "temperature_anomaly",
    "dryness_index",
    "pollution_index",
    "confidence",
)


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "region": "EUR",
        "window_start": TS,
        "window_end": datetime(2026, 8, 1, 12, 30, tzinfo=UTC),
        "impact_index": 42.0,
        "temperature_anomaly": 1.0,
        "dryness_index": 0.2,
        "pollution_index": 0.3,
        "confidence": "MEASURED",
        "model_pm25_ugm3": 9.4,
    }
    record.update(overrides)
    return record


def _legacy_db(tmp_path: Path) -> Path:
    """Build an old-schema database file in a temporary directory.

    This never opens, copies from, or writes to data/aggregates.duckdb. A test
    that reached for the development database would make the suite depend on an
    untracked file that is not a build artifact.
    """
    db_path = tmp_path / "legacy.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE climate_index (
            region VARCHAR NOT NULL,
            window_start TIMESTAMP NOT NULL,
            window_end TIMESTAMP NOT NULL,
            impact_index DOUBLE NOT NULL,
            temperature_anomaly DOUBLE NOT NULL,
            dryness_index DOUBLE NOT NULL,
            pollution_index DOUBLE NOT NULL,
            confidence VARCHAR NOT NULL,
            PRIMARY KEY (region, window_start, window_end)
        )
        """
    )
    con.execute(
        "INSERT INTO climate_index VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "EUR",
            TS.replace(tzinfo=None),
            datetime(2026, 8, 1, 12, 30),
            42.0,
            1.0,
            0.2,
            0.3,
            "MEASURED",
        ],
    )
    con.close()
    return db_path


def test_the_legacy_fixture_really_lacks_the_column(tmp_path: Path) -> None:
    """Without this, the migration test could pass over an already-migrated file."""
    con = duckdb.connect(str(_legacy_db(tmp_path)), read_only=True)
    columns = {row[0] for row in con.execute("DESCRIBE climate_index").fetchall()}
    con.close()
    assert set(LEGACY_COLUMNS) == columns
    assert "model_pm25_ugm3" not in columns


def test_the_writer_migrates_an_old_file_in_place(tmp_path: Path) -> None:
    db_path = _legacy_db(tmp_path)
    store = DuckDBAggregateStore(db_path)
    rows = store.read_region_series("EUR")
    store.close()
    assert len(rows) == 1
    # The pre-existing row keeps its values and reports the new one as absent.
    assert rows[0]["impact_index"] == 42.0
    assert rows[0]["model_pm25_ugm3"] is None


def test_opening_twice_is_idempotent(tmp_path: Path) -> None:
    db_path = _legacy_db(tmp_path)
    DuckDBAggregateStore(db_path).close()
    store = DuckDBAggregateStore(db_path)
    store.upsert(_record())
    rows = store.read_region_series("EUR")
    store.close()
    assert rows[0]["model_pm25_ugm3"] == 9.4


def test_the_read_only_reader_tolerates_an_unmigrated_file(tmp_path: Path) -> None:
    """The reader cannot migrate (INV-2), so it must read an old file regardless."""
    rows = DuckDBReadOnlyAggregateStore(_legacy_db(tmp_path)).read_region_series("EUR")
    assert len(rows) == 1
    assert rows[0]["model_pm25_ugm3"] is None
    assert set(rows[0]) == set(AGGREGATE_COLUMNS)


@pytest.mark.parametrize("value", [9.4, None])
def test_duckdb_round_trips_a_value_and_a_null(tmp_path: Path, value: float | None) -> None:
    store = DuckDBAggregateStore(tmp_path / "agg.duckdb")
    store.upsert(_record(model_pm25_ugm3=value))
    rows = store.read_region_series("EUR")
    store.close()
    assert rows[0]["model_pm25_ugm3"] == value


def test_dynamo_omits_the_attribute_when_absent() -> None:
    with_value = to_item(_record())
    without = to_item(_record(model_pm25_ugm3=None))
    assert with_value["model_pm25_ugm3"] == Decimal("9.4")
    # Omitted, not written as a null or a zero.
    assert "model_pm25_ugm3" not in without
    assert from_item(with_value)["model_pm25_ugm3"] == 9.4
    assert from_item(without)["model_pm25_ugm3"] is None


def _satellite(pm25: float) -> SatelliteEvent:
    return SatelliteEvent(
        ts=TS,
        region="EUR",
        cloud_cover_pct=50.0,
        vegetation_index=0.0,
        aerosol_index=1.0,
        model_pm25_ugm3=pm25,
    )


def test_the_engine_means_the_window_and_reports_none_without_satellite() -> None:
    records = compute_records([_satellite(8.0), _satellite(12.0)])
    assert records[0].model_pm25_ugm3 == pytest.approx(10.0)

    weather_only = compute_records(
        [WeatherEvent(ts=TS, region="EUR", temperature_c=20.0, rainfall_mm=0.0, wind_speed_ms=1.0)]
    )
    # None rather than 0.0: zero is a real concentration the provider returns.
    assert weather_only[0].model_pm25_ugm3 is None
