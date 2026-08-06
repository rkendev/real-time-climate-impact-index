"""The semantic assertion: a sensor must measure what its field claims (ADR-0009).

The apparatus fault this exists for was not a wrong value. It was a wrong
*entity*: a location id was used where a sensor id belonged, and three of four
New York stations returned ozone in parts per million which was recorded as PM2.5
in micrograms per cubic metre. Ozone at 0.03 ppm is type-correct, range-plausible
and simply not PM2.5, so nothing about the number could reveal it.

An identifier's name is a claim about what it identifies. No test in this
repository had ever checked a claim of that kind. This is that test, and the
seeded violations use the two real ozone sensors the diagnostic found.
"""

from __future__ import annotations

import pytest

from climate_index.adapters.openaq.admission import (
    PM25_PARAMETER,
    PM25_UNITS,
    SensorIdentityError,
    pm25_candidates,
)

# Transcribed from live /v3/locations responses during the fault diagnosis.
# Metadata only: ids, names, parameters and units, no measured value, so the
# frozen licence rule does not bite.
FORT_LEE = {
    "results": [
        {
            "id": 857,
            "name": "Fort Lee Near Road",
            "sensors": [
                {"id": 1536, "parameter": {"name": "co", "units": "ppm"}},
                {"id": 1535, "parameter": {"name": "no2", "units": "ppm"}},
                {"id": 1534, "parameter": {"name": "pm25", "units": PM25_UNITS}},
            ],
        }
    ]
}
JERSEY_CITY = {
    "results": [
        {
            "id": 928,
            "name": "Jersey City FH",
            "sensors": [{"id": 5077566, "parameter": {"name": "pm25", "units": PM25_UNITS}}],
        }
    ]
}
# What /sensors/857 actually is, which is what the faulty code was reading.
OZONE_ONLY = {
    "results": [{"id": 857, "sensors": [{"id": 857, "parameter": {"name": "o3", "units": "ppm"}}]}]
}


def test_a_location_resolves_to_its_pm25_sensor_not_its_location_id() -> None:
    """The whole fault in one assertion: 857 resolves to 1534, never to 857."""
    assert pm25_candidates(FORT_LEE, 857) == [1534]
    assert pm25_candidates(JERSEY_CITY, 928) == [5077566]


def test_a_location_offering_only_ozone_is_refused() -> None:
    """The seeded violation, using the real sensor that caused the fault.

    This is the check that would have caught it. Pointed at what /sensors/857
    actually serves, it refuses instead of returning numbers.
    """
    with pytest.raises(SensorIdentityError, match="no pm25 sensor"):
        pm25_candidates(OZONE_ONLY, 857)


def test_the_refusal_names_what_was_offered_instead() -> None:
    """A refusal that does not say what it found is a refusal nobody can diagnose."""
    with pytest.raises(SensorIdentityError, match=r"\['o3'\]"):
        pm25_candidates(OZONE_ONLY, 857)


def test_right_parameter_in_wrong_units_is_refused() -> None:
    """Units are asserted too, not just the parameter name.

    A pm25 sensor reporting ppm would be a different quantity under a familiar
    name, which is the same class of fault one level down.
    """
    wrong_units = {
        "results": [
            {"id": 1, "sensors": [{"id": 2, "parameter": {"name": PM25_PARAMETER, "units": "ppm"}}]}
        ]
    }
    with pytest.raises(SensorIdentityError, match="not 'pm25'|µg/m³"):
        pm25_candidates(wrong_units, 1)


def test_a_location_with_no_sensors_or_no_body_is_refused() -> None:
    with pytest.raises(SensorIdentityError, match="no pm25 sensor"):
        pm25_candidates({"results": [{"id": 5, "sensors": []}]}, 5)
    with pytest.raises(SensorIdentityError, match="returned no body"):
        pm25_candidates({"results": []}, 5)


def test_the_hours_query_refuses_an_unresolved_location() -> None:
    """Defence in depth: even if resolution is skipped, no hours query goes out.

    The faulty code queried hours directly from the location id. This makes that
    impossible rather than merely wrong.
    """
    from climate_index.adapters.openaq.source import AdmittedLocation, OpenAQStationSource

    unresolved = AdmittedLocation(location_id=857, station_id="857", city="New York", region="NAM")
    assert unresolved.pm25_sensor_id is None
    source = OpenAQStationSource(
        base_url="https://example.invalid/v3", api_key="x", sensors=(unresolved,), lag_hours=48
    )
    with pytest.raises(ValueError, match="no resolved PM2.5 sensor"):
        source._fetch_one(None, None, unresolved, __import__("datetime").datetime.now())
