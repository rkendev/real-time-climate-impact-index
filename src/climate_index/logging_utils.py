"""Structured, metadata-only logging (NFR-O1, NFR-O3).

Every component emits structured records carrying the component name, event
counts, per-region counts where useful, and window boundaries in the processor.
The emit API accepts a short event name plus scalar metadata keyword arguments
only; it has no parameter for and never serializes an event payload or a secret.
This keeps telemetry to counts, rates, and boundaries (NFR-O3).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_CONFIGURED: set[str] = set()


def _configure(component: str, level: int) -> logging.Logger:
    """Return a component logger with a single stdout handler, configured once."""
    logger = logging.getLogger(f"climate_index.{component}")
    if component not in _CONFIGURED:
        handler = logging.StreamHandler(stream=sys.stdout)
        # The message is already a JSON object built by StructuredLogger, so the
        # handler formats it verbatim.
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _CONFIGURED.add(component)
    logger.setLevel(level)
    return logger


class StructuredLogger:
    """A metadata-only structured logger bound to one component name."""

    def __init__(self, component: str, logger: logging.Logger) -> None:
        self._component = component
        self._logger = logger

    def event(self, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
        """Emit one structured record.

        ``event`` is a short machine-readable name. ``fields`` must be scalar
        metadata only (counts, rates, window boundaries); do not pass raw event
        payloads or secrets. Values are coerced to JSON via ``str`` as a fallback.
        """
        record: dict[str, Any] = {"component": self._component, "event": event}
        record.update(fields)
        self._logger.log(level, json.dumps(record, sort_keys=True, default=str))

    def heartbeat(self, **fields: Any) -> None:
        """Emit a liveness heartbeat record (NFR-O2)."""
        self.event("heartbeat", **fields)


def get_logger(component: str, level: int = logging.INFO) -> StructuredLogger:
    """Return a StructuredLogger for ``component`` at the given level."""
    return StructuredLogger(component, _configure(component, level))
