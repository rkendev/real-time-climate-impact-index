"""Response shapes for the OpenAQ adapter tests, transcribed from live responses.

Provenance matters here, so every literal below carries it. A fixture written
from a documentation page is a *claim* about an API, and a claim written from
documentation is exactly the class of error the project's pre-flight exists to
catch: the pre-flight found that the docs page and the live response disagreed
about which fields exist, and later found a guidance document contradicting its
own table.

Each constant says which endpoint it came from and whether it was **observed**
(transcribed from a response that existed) or **derived** (an observed response
with one field changed, where the change is the thing under test). Nothing here
is written from documentation.

Observed during the pre-flight and the coverage re-verification of 2026-08-02 and
2026-08-03, against api.openaq.org/v3 with a registered key.
"""

from __future__ import annotations

from typing import Any

# Every fixture below that carries a measured value declares where that value
# came from and under what licence. The frozen rule permits raw station values as
# fixtures only from providers whose licence allows redistribution, and
# tests/hygiene/test_fixture_provenance.py enforces this declaration rather than
# trusting anyone to remember the rule. The rule was originally written for "the
# capture"; it was broken during a hand transcription, which is the same act
# under a different name, which is why the control is attached to the artifact
# and not to the activity.
#
# Adding a licence to the permitted list means first checking its
# redistributionAllowed flag on /v3/licenses. Only ODC-BY has been checked:
# commercialUseAllowed true, attributionRequired true, shareAlikeRequired false,
# modificationAllowed true, redistributionAllowed true.
MEASURED_VALUE_SOURCES: dict[str, dict[str, Any]] = {
    "HOUR_PROVIDER_HOURLY": {
        "location_id": 80,
        "sensor_id": 4235,
        "provider": "EEA",
        "licence": "ODC-BY",
        "note": "attribution required, carried in the README",
    },
    # Derived from the entry above by changing one field each, so they inherit
    # its provenance and its licence.
    "HOUR_FLAGGED": {"location_id": 80, "provider": "EEA", "licence": "ODC-BY"},
    "HOUR_NEGATIVE": {"location_id": 80, "provider": "EEA", "licence": "ODC-BY"},
    "HOUR_NO_SAMPLES": {"location_id": 80, "provider": "EEA", "licence": "ODC-BY"},
    "HOUR_NULL_VALUE": {"location_id": 80, "provider": "EEA", "licence": "ODC-BY"},
    # Structure observed, numbers invented. Carries no licensed measurement.
    "HOUR_COMPUTED_MEAN": {"synthetic": True, "licence": "SYNTHETIC"},
}

# ---------------------------------------------------------------------------
# GET /v3/locations  (OBSERVED: location 79, returned in a radius query around
# the Amsterdam grid point. Reproduced field for field, including the null
# locality and the null licenses that the licence rule turns on.)
# ---------------------------------------------------------------------------
LOCATION_REFERENCE_GRADE: dict[str, Any] = {
    "id": 79,
    "name": "Hilversum-J. Gerardtsweg",
    "locality": None,
    "timezone": "Europe/Amsterdam",
    "country": {"id": 94, "code": "NL", "name": "Netherlands"},
    "owner": {"id": 4, "name": "Unknown Governmental Organization"},
    "provider": {"id": 210, "name": "Netherlands"},
    "isMobile": False,
    "isMonitor": True,
    "instruments": [{"id": 2, "name": "Government Monitor"}],
    "sensors": [
        {
            "id": 4608,
            "name": "no2 µg/m³",
            "parameter": {"id": 5, "name": "no2", "units": "µg/m³", "displayName": "NO2"},
        },
        {
            "id": 118,
            "name": "pm25 µg/m³",
            "parameter": {
                "id": 2,
                "name": "pm25",
                "units": "µg/m³",
                "displayName": "PM2.5",
            },
        },
    ],
    "coordinates": {"latitude": 52.23510000000001, "longitude": 5.18155},
    "licenses": None,
    "bounds": [5.18155, 52.23510000000001, 5.18155, 52.23510000000001],
    "distance": 23991.39923552,
    "datetimeFirst": {"utc": "2016-01-30T01:00:00Z", "local": "2016-01-30T02:00:00+01:00"},
    "datetimeLast": {"utc": "2018-06-25T10:00:00Z", "local": "2018-06-25T12:00:00+02:00"},
}

# OBSERVED: location 3400895, "University of Lagos/Makoko", returned in a radius
# query around the Lagos grid point where 60 of the 61 fixed stations are
# non-monitor. Metadata only, no measured value, so no licence applies to what is
# committed here. Replaces an earlier invented variant: the frozen inclusion rule
# turns on isMonitor, and testing it against a station that exists is worth the
# one call it cost.
LOCATION_LOW_COST: dict[str, Any] = {
    **LOCATION_REFERENCE_GRADE,
    "id": 3400895,
    "name": "University of Lagos/Makoko",
    "isMonitor": False,
    "instruments": [{"id": 7, "name": "Unknown AirGradient Sensor"}],
    "provider": {"id": 66, "name": "AirGradient"},
    "licenses": [
        {
            "id": 41,
            "name": "CC BY 4.0",
            "attribution": {"name": "LAMATA", "url": None},
            "dateFrom": "2023-07-15",
            "dateTo": None,
        }
    ],
    "sensors": [
        {
            "id": 12178112,
            "name": "pm25 µg/m³",
            "parameter": {"id": 2, "name": "pm25", "units": "µg/m³", "displayName": "PM2.5"},
        }
    ],
}

# ---------------------------------------------------------------------------
# GET /v3/sensors/{id}/hours  (OBSERVED: sensor 4235, Amsterdam-Van
# Diemenstraat, for the hour beginning 2026-08-01T00:00Z. The half-open period,
# the flagInfo block and the coverage block are exactly as returned. Note the
# coverage block's own oddity, preserved rather than tidied: expectedInterval
# reads 24:00:00 for a one hour period and percentCoverage reads 2400.0. The
# adapter therefore reads observedCount and nothing else from it.)
# ---------------------------------------------------------------------------
HOUR_PROVIDER_HOURLY: dict[str, Any] = {
    "value": 2.7,
    "flagInfo": {"hasFlags": False},
    "parameter": {"id": 2, "name": "pm25", "units": "µg/m³", "displayName": None},
    "period": {
        "label": "1hour",
        "interval": "01:00:00",
        "datetimeFrom": {"utc": "2026-08-01T00:00:00Z", "local": "2026-08-01T02:00:00+02:00"},
        "datetimeTo": {"utc": "2026-08-01T01:00:00Z", "local": "2026-08-01T03:00:00+02:00"},
    },
    "coordinates": None,
    "summary": {
        "min": 2.7,
        "q02": 2.7,
        "q25": 2.7,
        "median": 2.7,
        "q75": 2.7,
        "max": 2.7,
        "avg": 2.7,
        "sd": None,
    },
    "coverage": {
        "expectedCount": 1,
        "expectedInterval": "24:00:00",
        "observedCount": 1,
        "observedInterval": "24:00:00",
        "percentComplete": 100.0,
        "percentCoverage": 2400.0,
        "datetimeFrom": {"utc": "2026-08-01T00:00:00Z", "local": "2026-08-01T02:00:00+02:00"},
        "datetimeTo": {"utc": "2026-08-01T01:00:00Z", "local": "2026-08-01T03:00:00+02:00"},
    },
}

# SYNTHETIC VALUES, OBSERVED STRUCTURE. This fixture previously carried the real
# readings of sensor 12234702 at location 5404, "Pusa, Delhi - IMD", whose
# provider is CPCB and whose licenses field is null. Unstated terms are not
# permissive, and the frozen rule permits committed raw station values only from
# providers whose licence allows redistribution, so those numbers should never
# have been committed. They were removed here; see adr/0009 for the disclosure,
# including the fact that removal at HEAD is not full compliance because the
# values remain in the public history.
#
# What is kept is the *structure*, which is knowledge about the API rather than a
# licensed measurement: the field layout, expectedInterval reading 01:00:00 on
# this network (which localises the 24:00:00 nonsense to the other one), and the
# arithmetic percentComplete = observedCount / expectedCount * 100, which held
# across every hour sampled. The numbers below are invented to satisfy that
# arithmetic and nothing else.
#
# No permissively licensed multi-sample hour was available to transcribe instead:
# every EEA, AirNow and Japanese station sampled reported observedCount of one,
# so the only observed multi-sample network is the one whose terms are unstated.
HOUR_COMPUTED_MEAN: dict[str, Any] = {
    **HOUR_PROVIDER_HOURLY,
    "value": 20.0,
    "summary": {
        "min": 16.0,
        "q02": 16.0,
        "q25": 18.0,
        "median": 20.0,
        "q75": 22.0,
        "max": 24.0,
        "avg": 20.0,
        "sd": 3.0,
    },
    "coverage": {
        **HOUR_PROVIDER_HOURLY["coverage"],
        "expectedCount": 4,
        "expectedInterval": "01:00:00",
        "observedCount": 4,
        "percentComplete": 100.0,
    },
}

# DERIVED from HOUR_PROVIDER_HOURLY: hasFlags flipped true. The field was
# observed on every sampled hour, always false; a flagged hour was never seen, so
# this is a constructed variant and is labelled as one. It exists because the
# frozen validity rule turns on exactly this flag.
HOUR_FLAGGED: dict[str, Any] = {
    **HOUR_PROVIDER_HOURLY,
    "flagInfo": {"hasFlags": True},
}

# DERIVED from HOUR_PROVIDER_HOURLY: a negative value, and an observed instance
# was sought and not found. Sensor 4235 reports a lifetime minimum of -10.2, so
# negatives demonstrably occur on it, but three sampled months covering 1710
# returned hours (January 2026, November 2025, April 2026) contained none. The
# search was bounded and abandoned rather than extended.
#
# Worth noting beside the inert-validity finding in ADR-0009: the frozen rule
# that retains negatives rather than clamping them protects against a case that
# is real in this sensor's history but was not present in any recent hour
# sampled.
HOUR_NEGATIVE: dict[str, Any] = {**HOUR_PROVIDER_HOURLY, "value": -3.4}

# DERIVED from HOUR_PROVIDER_HOURLY: observedCount zero. The frozen validity rule
# requires at least one underlying sample.
HOUR_NO_SAMPLES: dict[str, Any] = {
    **HOUR_PROVIDER_HOURLY,
    "coverage": {**HOUR_PROVIDER_HOURLY["coverage"], "observedCount": 0},
}

# DERIVED from HOUR_PROVIDER_HOURLY: a null value. Hours were observed to be
# absent from the results list entirely rather than present with a null (Berlin
# returned 18 hours of a 42 hour range), so this covers the shape the API has not
# been seen to produce but which the no-fabrication rule must survive.
HOUR_NULL_VALUE: dict[str, Any] = {**HOUR_PROVIDER_HOURLY, "value": None}


def hours_page(*results: dict[str, Any]) -> dict[str, Any]:
    """The envelope every list resource returns.

    OBSERVED: the meta block accompanies every /v3 list response. An empty
    results list is the observed shape for a range with no data, since absent
    hours are omitted rather than returned as nulls.
    """
    return {
        "meta": {"name": "openaq-api", "page": 1, "limit": 100, "found": len(results)},
        "results": list(results),
    }


def locations_page(*results: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {"name": "openaq-api", "page": 1, "limit": 1000, "found": len(results)},
        "results": list(results),
    }


# OBSERVED: the body returned for a request carrying no key, confirmed against
# /v3/locations, /v3/parameters and /v3/instruments, all 401.
UNAUTHORIZED: dict[str, Any] = {
    "message": "Unauthorized. A valid API key must be provided in the X-API-Key header."
}
