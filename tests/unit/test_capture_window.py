"""The capture script's pure parts, exercised before it is ever run.

No network is touched here. The fetch is a separate act from committing the
script, and the parts that decide what lands and what is recorded are exactly the
parts worth having under test before the one run that matters.

Two properties carry the most weight. The artifact must never contain a measured
value, because it is committed and the frozen licence rule bites on committed raw
values. And the realized timestamp bounds must be computed from the rows that
actually landed rather than from the window that was asked for, because a
declaration catches a mislabelled pull and only the realized bounds catch a
mis-executed one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from capture_window import (
    CaptureFault,
    assert_inside_window,
    bounds,
    build_artifact,
    build_parser,
    model_rows,
    station_rows,
)
from climate_index.config import Settings

# Taken from the configured control window rather than written as literals. Two
# reasons, and the second is the one that bit. It keeps this module exercising the
# window the capture will actually be pointed at; and the control window's
# exclusive end is the holdout's first day, so writing the boundary as a literal
# puts a holdout date on the run surface. The successor control caught exactly
# that here, which is what it is for.
_WINDOW = Settings(_env_file=None).reconciliation_windows["control"]
START = _WINDOW.start
END = _WINDOW.end

INSIDE = START + timedelta(days=1, hours=9)
LATER = START + timedelta(days=3, hours=5)
BEFORE = START - timedelta(hours=1)

SENSOR = {"sensor_id": 11, "station_id": "s-11", "city": "Amsterdam", "region": "EUR"}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hour(text: str, value: float, *, flags: bool = False, observed: int = 1) -> dict[str, object]:
    return {
        "period": {"datetimeFrom": {"utc": text}},
        "value": value,
        "hasFlags": flags,
        "coverage": {"observedCount": observed},
    }


# --- what qualifies as a station row ------------------------------------------


def test_a_clean_hour_becomes_one_row() -> None:
    rows = station_rows({"results": [_hour(_stamp(INSIDE), 12.5)]}, SENSOR)
    assert len(rows) == 1
    assert rows[0]["pm25_ugm3"] == 12.5
    assert rows[0]["city"] == "Amsterdam"
    assert rows[0]["ts"] == _stamp(INSIDE)


def test_a_flagged_hour_is_dropped_and_a_zero_sample_hour_is_dropped() -> None:
    payload = {
        "results": [
            _hour(_stamp(INSIDE), 12.5, flags=True),
            _hour(_stamp(LATER), 12.5, observed=0),
        ]
    }
    assert station_rows(payload, SENSOR) == []


def test_a_negative_reading_is_retained() -> None:
    """The frozen rules retain them, and the tolerance floor is why it matters."""
    rows = station_rows({"results": [_hour(_stamp(INSIDE), -3.2)]}, SENSOR)
    assert rows[0]["pm25_ugm3"] == -3.2


def test_construction_is_recorded_from_the_sample_count() -> None:
    """The axis the CPCB confound is visible on, and the reason for the endpoint."""
    one = station_rows({"results": [_hour(_stamp(INSIDE), 12.5, observed=1)]}, SENSOR)
    many = station_rows({"results": [_hour(_stamp(INSIDE), 12.5, observed=4)]}, SENSOR)
    assert one[0]["construction"] == "PROVIDER_HOURLY"
    assert many[0]["construction"] == "COMPUTED_MEAN"


def test_a_malformed_row_is_skipped_rather_than_guessed() -> None:
    payload = {"results": [{"value": 12.5}, {"period": {}, "value": None}, "nonsense"]}
    assert station_rows(payload, SENSOR) == []


# --- the model side -----------------------------------------------------------


def test_model_hours_outside_the_window_are_not_captured() -> None:
    payload = {
        "hourly": {
            "time": [
                _stamp(BEFORE)[:-4],
                _stamp(INSIDE)[:-4],
                _stamp(END)[:-4],
            ],
            "pm2_5": [5.0, 9.0, 7.0],
        }
    }
    rows = model_rows(payload, "EUR", "Amsterdam", START, END)
    assert [row["ts"] for row in rows] == [_stamp(INSIDE)]


def test_a_null_model_hour_is_omitted_rather_than_zeroed() -> None:
    payload = {"hourly": {"time": [_stamp(INSIDE)[:-4]], "pm2_5": [None]}}
    assert model_rows(payload, "EUR", "Amsterdam", START, END) == []


# --- realized bounds, and the window assertion --------------------------------


def test_bounds_are_the_rows_that_landed_not_the_window_requested() -> None:
    middle = START + timedelta(days=2, hours=23)
    rows = [{"ts": _stamp(LATER)}, {"ts": _stamp(INSIDE)}, {"ts": _stamp(middle)}]
    assert bounds(rows) == {"rows": 3, "min": _stamp(INSIDE), "max": _stamp(LATER)}


def test_bounds_of_nothing_say_nothing_rather_than_inventing_a_span() -> None:
    assert bounds([]) == {"rows": 0, "min": None, "max": None}


def test_a_row_outside_the_requested_window_blocks_the_capture() -> None:
    """Refused, not filtered: a mislabelled capture is the thing being prevented."""
    rows = [{"ts": _stamp(INSIDE)}, {"ts": _stamp(BEFORE)}]
    with pytest.raises(CaptureFault, match="outside the requested window"):
        assert_inside_window(rows, START, END)


def test_the_window_assertion_accepts_a_capture_that_is_inside_it() -> None:
    """The no-fault control: a check that rejects everything proves nothing."""
    assert_inside_window([{"ts": _stamp(INSIDE)}], START, END)


# --- the artifact -------------------------------------------------------------


def _artifact() -> dict[str, object]:
    from capture_window import CallLog

    stations = [
        {"ts": _stamp(INSIDE), "city": "Amsterdam", "pm25_ugm3": 12.5},
        {"ts": _stamp(LATER), "city": "Amsterdam", "pm25_ugm3": -3.25},
    ]
    models = [{"ts": _stamp(INSIDE), "city": "Amsterdam", "model_pm25_ugm3": 9.75}]
    return build_artifact(
        name="control",
        start=START,
        end=END,
        stations=stations,
        models=models,
        admission_version="2026-08-03",
        sensor_ids=[11, 12],
        station_log=CallLog(),
        model_log=CallLog(),
        now=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )


def test_the_artifact_records_realized_bounds_per_source() -> None:
    record = _artifact()
    assert record["observed_bounds"]["station"]["max"] == _stamp(LATER)
    assert record["observed_bounds"]["model"]["max"] == _stamp(INSIDE)
    assert record["window_requested"]["name"] == "control"


def test_the_artifact_carries_no_measured_value() -> None:
    """It is committed, and the licence rule bites on committed raw values.

    Checked by searching the serialized artifact for the values that went in,
    rather than by reading the fields it is known to have. A field added later
    that leaked a value would pass a field-by-field check and fail this one.
    """
    text = json.dumps(_artifact())
    for value in ("12.5", "-3.25", "9.75"):
        assert value not in text, f"the artifact leaked the measured value {value}"


def test_the_leak_check_would_notice_a_leaked_value() -> None:
    """The absence check above must be able to fail."""
    record = _artifact()
    record["observed_bounds"]["station"]["max_value"] = 12.5  # type: ignore[index]
    assert "12.5" in json.dumps(record)


def test_the_artifact_names_the_endpoint_and_why_it_is_not_the_archive() -> None:
    """The reason travels with the artifact, not only with the commit message."""
    source = str(_artifact()["station_source"])
    assert "/v3/sensors/{id}/hours" in source
    assert "archive" in source and "computed mean" in source


# --- the window is named, never dated -----------------------------------------


def test_the_capture_requires_an_explicit_window_and_offers_only_control() -> None:
    choices = tuple(sorted(Settings(_env_file=None).reconciliation_windows))
    assert choices == ("control",)
    parser = build_parser(choices)
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--window", "holdout"])
    assert parser.parse_args(["--window", "control"]).window == "control"


def test_the_capture_takes_no_date_arguments_at_all() -> None:
    """A date argument would be a route around the named-window restriction."""
    parser = build_parser(("control",))
    flags = {action.option_strings[0] for action in parser._actions if action.option_strings}
    assert flags == {"-h", "--window"}
