"""AT-6 (UC-5, FR-8, INV-2): the dashboard is strictly read-only.

Two checks. First, a static import audit of ``app/dashboard.py``: it must import
no store writer and no index-compute path, and it must read through the read-only
reader and the display-safe verbal-label mapper. Second, a render smoke: the app
builds its view from a seeded store through the read-only reader without error.

The import audit parses the source with the AST (it never imports the module),
mirroring the AT-10 cloud-SDK audit. The render smoke loads the module from its
file path (``app/`` is not on the import path) under a non-main name, so its
``main()`` never fires and no Streamlit server starts.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBReadOnlyAggregateStore
from climate_index.core.models import ClimateIndexRecord, Confidence

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = REPO_ROOT / "app" / "dashboard.py"

# Modules that carry the index-compute path or a store writer. The dashboard must
# import none of them (INV-2).
FORBIDDEN_MODULES = {
    "climate_index.core.features",
    "climate_index.core.engine",
    "climate_index.core.confidence",
    "climate_index.core.windowing",
    "climate_index.processor",
    "climate_index.consumer",
    "climate_index.adapters.duckdb.store",
}
# Writer or compute symbols that must never be imported into the dashboard.
FORBIDDEN_NAMES = {
    "DuckDBAggregateStore",
    "DuckDBRawStore",
    "compute_records",
    "process",
    "run_processor",
    "impact_index",
    "dryness_index",
    "pollution_index",
    "temperature_anomaly",
    "upsert",
    "append",
}


def _imports(source: str) -> tuple[set[str], set[str]]:
    """Return (imported module paths, imported symbol names) from the source."""
    tree = ast.parse(source)
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return modules, names


def test_dashboard_imports_no_writer_or_compute_path() -> None:
    modules, names = _imports(DASHBOARD.read_text(encoding="utf-8"))

    offending_modules = modules & FORBIDDEN_MODULES
    assert not offending_modules, f"dashboard imports a writer/compute module: {offending_modules}"

    offending_names = names & FORBIDDEN_NAMES
    assert not offending_names, f"dashboard imports a writer/compute symbol: {offending_names}"


def test_dashboard_reads_read_only_and_labels_for_display() -> None:
    modules, names = _imports(DASHBOARD.read_text(encoding="utf-8"))
    # It reads through the config-driven read-only factory (never a concrete writer
    # or a hardcoded backend reader) and formats with the display-safe label. It is
    # typed against the read-only Protocol, so it holds no write capability.
    assert "build_readonly_aggregate_store" in names
    assert "ReadOnlyAggregateStore" in names
    assert "verbal_label" in names
    assert "climate_index.store_factory" in modules
    assert "climate_index.labels" in modules
    # The factory is the only door to a reader: no concrete backend reader is
    # imported straight into the dashboard.
    assert "climate_index.adapters.duckdb.reader" not in modules
    assert "climate_index.adapters.aws.dynamo_reader" not in modules


def test_dashboard_source_issues_no_writes() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    for fragment in (".upsert(", ".append(", "INSERT ", "INSERT\n", " REPLACE"):
        assert fragment not in source, f"dashboard source contains a write fragment: {fragment!r}"


def _load_dashboard_module() -> object:
    spec = importlib.util.spec_from_file_location("dashboard_under_test", DASHBOARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve the module's namespace, and
    # so importing under a non-main name means main() never fires (no UI starts).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_builds_view_from_seeded_store(tmp_path: Path) -> None:
    db_path = tmp_path / "aggregates.duckdb"
    writer = DuckDBAggregateStore(db_path)
    starts = [datetime(2026, 7, 19, hour, 0, tzinfo=UTC) for hour in (10, 11, 12)]
    for index, start in enumerate(starts):
        record = ClimateIndexRecord(
            region="EUR",
            window_start=start,
            window_end=start.replace(hour=start.hour, minute=30),
            impact_index=10.0 + 30.0 * index,
            temperature_anomaly=1.0,
            dryness_index=0.5,
            pollution_index=0.5,
            confidence=Confidence.MEASURED,
        )
        writer.upsert(record.model_dump(mode="python"))
    writer.close()

    module = _load_dashboard_module()

    reader = DuckDBReadOnlyAggregateStore(db_path)
    try:
        rows = reader.read_region_series("EUR")
    finally:
        reader.close()

    view = module.build_region_view(rows, "EUR")  # type: ignore[attr-defined]
    assert view.region == "EUR"
    assert len(view.impact_series) == 3
    assert view.impact_series == (10.0, 40.0, 70.0)
    assert view.current_value == 70.0
    assert view.label == "high"  # 70.0 is above the medium_max band
    assert view.confidence == Confidence.MEASURED.value


def test_dashboard_build_view_handles_empty_series() -> None:
    module = _load_dashboard_module()
    view = module.build_region_view([], "AFR")  # type: ignore[attr-defined]
    assert view.current_value is None
    assert view.label is None
    assert view.impact_series == ()
