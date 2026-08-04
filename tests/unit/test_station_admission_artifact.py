"""The admission artifact is pinned, so a hand edit or a silent refresh goes red.

The admitted station set is an outcome of the frozen rules rather than an input,
and it is the basis of a published figure. A cache that quietly refreshed, or a
file someone tidied by hand, would move that figure with nothing recording that
it had moved. These tests are the record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from climate_index.adapters.openaq import admitted_locations, available_versions, load_artifact

# The last recorded figure, from the re-verification of 2026-08-03 written up in
# adr/0009. Changing this number is changing a published result, so it changes
# here only alongside a new dated artifact and a diff recorded in that ADR.
RECORDED_TOTAL = 208
RECORDED_CITIES = 8
RECORDED_QUERIED = 12


def test_at_least_one_artifact_is_committed() -> None:
    assert available_versions(), "the adapter reads a committed artifact and derives none"


def test_the_totals_match_the_last_recorded_figure() -> None:
    totals = load_artifact()["totals"]
    assert totals["admitted_stations"] == RECORDED_TOTAL
    assert totals["admitted_cities"] == RECORDED_CITIES
    assert totals["cities_queried"] == RECORDED_QUERIED


def test_every_city_lists_exactly_as_many_ids_as_it_admits() -> None:
    """Internal consistency: a hand edit to one half and not the other goes red."""
    for city, entry in load_artifact()["cities"].items():
        listed = len(entry["sensor_location_ids"])
        assert listed == entry["funnel"]["admitted"], f"{city} lists {listed} ids"


def test_the_funnel_is_monotonic_in_every_city() -> None:
    """Each stage is a subset of the one before it, so the counts cannot increase."""
    for city, entry in load_artifact()["cities"].items():
        f = entry["funnel"]
        stages = [
            f["in_radius"],
            f["fixed"],
            f["reference_grade"],
            f["with_pm25_sensor"],
            f["admitted"],
        ]
        assert stages == sorted(stages, reverse=True), f"{city} funnel widens: {stages}"


def test_the_totals_agree_with_the_per_city_entries() -> None:
    artifact = load_artifact()
    cities = artifact["cities"]
    assert sum(c["funnel"]["admitted"] for c in cities.values()) == RECORDED_TOTAL
    assert sum(1 for c in cities.values() if c["funnel"]["admitted"]) == RECORDED_CITIES
    assert len(cities) == RECORDED_QUERIED
    assert len(admitted_locations(artifact)) == RECORDED_TOTAL


def test_the_run_that_produced_it_was_clean() -> None:
    """A zero from a run containing failures is not a zero (contract section 3)."""
    run = load_artifact()["run"]
    assert run["station_call_statuses"] == {"200": run["station_calls"]}
    assert run["rate_limited"] is False
    assert run["void_cities"] == []


def test_the_rule_parameters_are_recorded_with_the_result() -> None:
    """A count is not reproducible without the parameters that produced it."""
    rules = load_artifact()["rule_parameters"]
    assert rules["source_of_truth"].endswith("b81f1c9")
    assert rules["capture_window_start"] == "2026-07-17T00:00:00Z"
    assert rules["capture_window_end"] == "2026-07-31T00:00:00Z"
    for key in ("centre", "radius_rule", "reference_grade", "fixed", "parameter", "admission"):
        assert rules[key], f"{key} is missing from the recorded rule parameters"


def test_no_artifact_is_ever_overwritten(tmp_path: Path) -> None:
    """Re-derivation writes a new dated file; a named version resolves exactly."""
    (tmp_path / "2026-01-01.json").write_text(json.dumps({"cities": {}, "totals": {}}))
    (tmp_path / "2026-02-02.json").write_text(json.dumps({"cities": {}, "totals": {}}))
    assert available_versions(tmp_path) == ["2026-01-01", "2026-02-02"]
    assert load_artifact(directory=tmp_path)["version"] == "2026-02-02"
    assert load_artifact("2026-01-01", directory=tmp_path)["version"] == "2026-01-01"
    with pytest.raises(ValueError, match="2026-03-03"):
        load_artifact("2026-03-03", directory=tmp_path)


def test_a_missing_artifact_says_how_to_derive_one(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="recompute_station_admission"):
        load_artifact(directory=tmp_path)
