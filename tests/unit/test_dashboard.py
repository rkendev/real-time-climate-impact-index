"""AT-6 (UC-5, FR-8, INV-2): the dashboard is strictly read-only, and it explains itself.

Two checks. First, a static import audit of ``app/dashboard.py``: it must import
no store writer and no index-compute path, and it must read through the read-only
reader and the display-safe verbal-label mapper. Second, a render smoke: the app
builds its view from a seeded store through the read-only reader without error.

A third group covers the explanatory layer the page owes a first-time viewer
(UC-5 presentation): the plain-language framing, the simulated-feed statement,
the freshness and cadence line, both legends, the chart labelling, and the source
link. Each is asserted against the configured value, so the page is held to
config as the single authority rather than to a duplicated literal here. The
render is driven through a recording stand-in for ``st``, so what is asserted is
what the page actually emits, with no Streamlit server involved.

The import audit parses the source with the AST (it never imports the module),
mirroring the AT-10 cloud-SDK audit. The render smoke loads the module from its
file path (``app/`` is not on the import path) under a non-main name, so its
``main()`` never fires and no Streamlit server starts.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBReadOnlyAggregateStore
from climate_index.config import Settings
from climate_index.core.models import ClimateIndexRecord, Confidence
from climate_index.labels import verbal_label

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


def _seed_store(tmp_path: Path) -> Path:
    """Seed three EUR windows through the writer and return the store path.

    The middle window is stored INFERRED so the read path carries a mixed set of
    grades, which is what the page's per-window confidence cue has to show.
    """
    db_path = tmp_path / "aggregates.duckdb"
    writer = DuckDBAggregateStore(db_path)
    starts = [datetime(2026, 7, 19, hour, 0, tzinfo=UTC) for hour in (10, 11, 12)]
    grades = (Confidence.MEASURED, Confidence.INFERRED, Confidence.MEASURED)
    for index, (start, grade) in enumerate(zip(starts, grades, strict=True)):
        record = ClimateIndexRecord(
            region="EUR",
            window_start=start,
            window_end=start.replace(hour=start.hour, minute=30),
            impact_index=10.0 + 30.0 * index,
            temperature_anomaly=1.0,
            dryness_index=0.5,
            pollution_index=0.5,
            confidence=grade,
        )
        writer.upsert(record.model_dump(mode="python"))
    writer.close()
    return db_path


def test_dashboard_builds_view_from_seeded_store(tmp_path: Path) -> None:
    db_path = _seed_store(tmp_path)

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
    assert view.confidence_series == ()


def test_view_carries_the_stored_grade_of_every_window() -> None:
    """The per-window grades are the stored values, read straight through."""
    module = _load_dashboard_module()
    start = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
    grades = (Confidence.MEASURED, Confidence.INFERRED, Confidence.AMBIGUOUS)
    rows = [
        {
            "window_start": start + timedelta(minutes=30 * position),
            "window_end": start + timedelta(minutes=30 * (position + 1)),
            "impact_index": 40.0 + position,
            "confidence": grade.value,
        }
        for position, grade in enumerate(grades)
    ]

    view = module.build_region_view(rows, "EUR")  # type: ignore[attr-defined]
    assert view.confidence_series == tuple(grade.value for grade in grades)
    assert view.confidence == Confidence.AMBIGUOUS.value  # the newest window's grade
    assert view.window_starts[-1] == start + timedelta(minutes=60)


def test_legends_are_rendered_from_config_not_from_page_literals() -> None:
    module = _load_dashboard_module()
    settings = Settings(_env_file=None)

    bands = module.band_legend_lines(settings)  # type: ignore[attr-defined]
    assert len(bands) == 3
    for cutoff in settings.label_thresholds.values():
        assert any(f"{cutoff:g}" in line for line in bands)
    # The bands agree with the mapper the page labels with (FR-9).
    assert verbal_label(settings.label_thresholds["low_max"], settings) == "low"
    assert verbal_label(settings.label_thresholds["medium_max"], settings) == "medium"

    tiers = module.tier_legend_lines(settings)  # type: ignore[attr-defined]
    assert len(tiers) == len(settings.confidence_tier_glosses)
    for tier, gloss in settings.confidence_tier_glosses.items():
        assert f"{tier}: {gloss}" in tiers
    assert (
        module.tier_gloss(Confidence.INFERRED.value, settings)
        == (  # type: ignore[attr-defined]
            settings.confidence_tier_glosses["INFERRED"]
        )
    )
    # An unknown or absent grade degrades to no gloss rather than to a guess.
    assert module.tier_gloss(None, settings) == ""  # type: ignore[attr-defined]
    assert module.tier_gloss("UNKNOWN", settings) == ""  # type: ignore[attr-defined]


class _Recorder:
    """A stand-in for ``st`` that records every call's text (no server, no widgets)."""

    def __init__(self, calls: list[tuple[str, tuple[object, ...], dict[str, object]]]) -> None:
        self.calls = calls

    def __getattr__(self, name: str) -> object:
        def record(*args: object, **kwargs: object) -> _Recorder:
            self.calls.append((name, args, kwargs))
            return self

        return record

    def selectbox(self, label: str, options: list[str]) -> str:
        self.calls.append(("selectbox", (label, options), {}))
        return options[0]

    def columns(self, count: int) -> tuple[_Recorder, ...]:
        self.calls.append(("columns", (count,), {}))
        return tuple(self for _ in range(count))

    def expander(self, label: str) -> _Recorder:
        self.calls.append(("expander", (label,), {}))
        return self

    def __enter__(self) -> _Recorder:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def text(self) -> str:
        """Every string the page emitted, positional arguments and keywords alike."""
        parts: list[str] = []
        for _, args, kwargs in self.calls:
            parts.extend(str(arg) for arg in args)
            parts.extend(str(value) for value in kwargs.values())
        return "\n".join(parts)


def _render_and_record(
    module: object,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _Recorder:
    settings = Settings(_env_file=None)
    recorder = _Recorder([])
    monkeypatch.setattr(module, "st", recorder)
    reader = DuckDBReadOnlyAggregateStore(db_path)
    try:
        module.render(reader, settings)  # type: ignore[attr-defined]
    finally:
        reader.close()
    return recorder


def test_page_explains_the_index_the_feed_the_tiers_and_the_bands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _seed_store(tmp_path)
    settings = Settings(_env_file=None)
    module = _load_dashboard_module()

    page = _render_and_record(module, db_path, monkeypatch).text()

    # What the index is, its scale, and its direction, plus the simulated feed.
    assert settings.index_summary in page
    assert settings.simulated_feed_notice in page
    # When it last moved and how often it refreshes.
    assert "2026-07-19 12:00 UTC" in page
    assert settings.demo_refresh_interval in page
    assert f"{settings.window_minutes} minute" in page
    # Both legends, and the current window's tier read back with its gloss.
    for tier, gloss in settings.confidence_tier_glosses.items():
        assert f"{tier}: {gloss}" in page
    assert settings.confidence_tier_glosses[Confidence.MEASURED.value] in page
    for cutoff in settings.label_thresholds.values():
        assert f"{cutoff:g}" in page
    # The pipeline description and the link back to the source.
    assert settings.pipeline_summary in page
    assert settings.source_repository_url in page


def test_chart_carries_real_times_units_and_a_per_window_confidence_cue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _seed_store(tmp_path)
    settings = Settings(_env_file=None)
    module = _load_dashboard_module()

    recorder = _render_and_record(module, db_path, monkeypatch)
    charts = {name: (args, kwargs) for name, args, kwargs in recorder.calls if "chart" in name}

    line_args, line_kwargs = charts["line_chart"]
    assert line_kwargs["x_label"] == module.WINDOW_COLUMN  # type: ignore[attr-defined]
    assert line_kwargs["y_label"] == settings.index_axis_label  # the index and its range
    series = line_args[0]
    assert series[module.WINDOW_COLUMN][0] == datetime(2026, 7, 19, 10, 0, tzinfo=UTC)  # type: ignore[attr-defined]
    assert series[settings.index_axis_label] == [10.0, 40.0, 70.0]

    strip_args, strip_kwargs = charts["bar_chart"]
    assert strip_kwargs["color"] == module.CONFIDENCE_COLUMN  # type: ignore[attr-defined]
    # The cue is the grade the pipeline stored for each window, unmodified.
    assert strip_args[0][module.CONFIDENCE_COLUMN] == [  # type: ignore[attr-defined]
        Confidence.MEASURED.value,
        Confidence.INFERRED.value,
        Confidence.MEASURED.value,
    ]
