"""Simulated event source adapter (UC-1, ADR-0007).

Carries no external dependency, so the default source path never needs a
network to go green (the local-first rule, ADR-0002).
"""

from climate_index.adapters.simulated.source import SimulatedEventSource

__all__ = ["SimulatedEventSource"]
