"""OpenAQ ground-station source adapter (UC-1, FR-11, E-8, ADR-0009)."""

from climate_index.adapters.openaq.admission import (
    admitted_locations,
    available_versions,
    load_artifact,
)
from climate_index.adapters.openaq.source import AdmittedLocation, OpenAQStationSource

__all__ = [
    "AdmittedLocation",
    "OpenAQStationSource",
    "admitted_locations",
    "available_versions",
    "load_artifact",
]
