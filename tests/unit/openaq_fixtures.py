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

# DERIVED from LOCATION_REFERENCE_GRADE: isMonitor flipped false, which is the
# discriminator the frozen inclusion rule uses. The flag itself was observed on
# /v3/instruments, where it is false for every sensor-class instrument and true
# for Government Monitor, BAM 1020, BAM 1022, AIO 2, Serinus 30 and MA350.
LOCATION_LOW_COST: dict[str, Any] = {
    **LOCATION_REFERENCE_GRADE,
    "id": 900001,
    "isMonitor": False,
    "instruments": [{"id": 4, "name": "Clarity Sensor"}],
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

# OBSERVED shape, from the CPCB (Delhi) network, where observedCount ran 2, 3 and
# 4 across the sampled hours because that provider supplies fifteen minute raw
# data which the rollup means into an hour. The distinction the frozen rules
# record as a per-station attribute and never gate on.
HOUR_COMPUTED_MEAN: dict[str, Any] = {
    **HOUR_PROVIDER_HOURLY,
    "value": 61.5,
    "coverage": {**HOUR_PROVIDER_HOURLY["coverage"], "observedCount": 4},
}

# DERIVED from HOUR_PROVIDER_HOURLY: hasFlags flipped true. The field was
# observed on every sampled hour, always false; a flagged hour was never seen, so
# this is a constructed variant and is labelled as one. It exists because the
# frozen validity rule turns on exactly this flag.
HOUR_FLAGGED: dict[str, Any] = {
    **HOUR_PROVIDER_HOURLY,
    "flagInfo": {"hasFlags": True},
}

# DERIVED from HOUR_PROVIDER_HOURLY: a negative value. Not observed on an hourly
# rollup, but the sensor summary for sensor 4235 reported a lifetime minimum of
# -10.2, so negative readings demonstrably occur on this sensor. The frozen rule
# retains them rather than clamping.
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
