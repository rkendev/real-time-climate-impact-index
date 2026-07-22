"""Open-Meteo event source adapter (UC-1, ADR-0007).

The HTTP client import stays lazy inside the adapter's run path, so importing
this package pulls in no client and test collection never dials one.
"""

from climate_index.adapters.openmeteo.source import OpenMeteoEventSource

__all__ = ["OpenMeteoEventSource"]
