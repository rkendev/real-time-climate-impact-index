"""Deterministic validation and quarantine gate (UC-2, FR-3, NFR-DQ1, INV-3).

Parse an EventEnvelope, validate its payload against the schema for its
event_type, and decide accept-or-quarantine by schema and range checks alone,
never by model judgment. On pass the validated event is returned for the caller
to forward. On fail a QuarantineRecord is produced with a short reason_code and a
quarantine counter increments; the invalid event is never returned and never
written as data (INV-3).

Reason codes and their deterministic precedence:
- ``range``: a field is present and correctly typed but outside its allowed
  bound (pydantic ``greater_than[_equal]`` / ``less_than[_equal]``).
- ``parse``: the payload is not a mapping, or a value cannot be parsed into its
  type at all (pydantic ``*_parsing``, ``dict_type``, ``json_invalid``).
- ``schema``: anything else (unknown event_type, missing field, wrong type,
  unknown region, non-UTC timestamp).
Range is checked first, then parse, then schema, so a single error picks exactly
one code.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from climate_index.core.models import (
    EventEnvelope,
    EventType,
    QuarantineRecord,
    ReasonCode,
    SatelliteEvent,
    WeatherEvent,
)
from climate_index.logging_utils import StructuredLogger, get_logger

_MODEL_BY_TYPE: dict[EventType, type[WeatherEvent] | type[SatelliteEvent]] = {
    EventType.WEATHER: WeatherEvent,
    EventType.SATELLITE: SatelliteEvent,
}

_RANGE_TYPES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}
_PARSE_TYPES = {"dict_type", "json_invalid"}


def _classify(exc: ValidationError) -> ReasonCode:
    """Map a pydantic error to a single reason code by fixed precedence."""
    types = {error["type"] for error in exc.errors()}
    if types & _RANGE_TYPES:
        return ReasonCode.RANGE
    if types & _PARSE_TYPES or any(name.endswith("_parsing") for name in types):
        return ReasonCode.PARSE
    return ReasonCode.SCHEMA


class _GateError(Exception):
    """Internal signal carrying the reason a message was rejected."""

    def __init__(self, event_type: str, reason_code: ReasonCode) -> None:
        super().__init__(reason_code.value)
        self.event_type = event_type
        self.reason_code = reason_code


class ValidationGate:
    """Deterministic accept-or-quarantine gate for consumed messages (UC-2)."""

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._log = logger if logger is not None else get_logger("validation_gate")
        self.forwarded_count = 0
        self.quarantined_count = 0
        self.quarantines: list[QuarantineRecord] = []

    def validate(self, message: Mapping[str, Any]) -> WeatherEvent | SatelliteEvent | None:
        """Return the validated event to forward, or None if it was quarantined."""
        try:
            event = self._parse(message)
        except _GateError as err:
            self._quarantine(message, err.event_type, err.reason_code)
            return None
        self.forwarded_count += 1
        return event

    def _parse(self, message: Mapping[str, Any]) -> WeatherEvent | SatelliteEvent:
        if not isinstance(message, Mapping):
            raise _GateError("unknown", ReasonCode.PARSE)
        try:
            envelope = EventEnvelope.model_validate(message)
        except ValidationError as exc:
            claimed = str(message.get("event_type", "unknown"))
            raise _GateError(claimed, _classify(exc)) from exc
        model = _MODEL_BY_TYPE[envelope.event_type]
        try:
            return model.model_validate(envelope.payload)
        except ValidationError as exc:
            raise _GateError(str(envelope.event_type), _classify(exc)) from exc

    def _quarantine(
        self, message: Mapping[str, Any], event_type: str, reason_code: ReasonCode
    ) -> None:
        raw = dict(message) if isinstance(message, Mapping) else {"value": message}
        self.quarantines.append(
            QuarantineRecord(
                ts_received=datetime.now(UTC),
                event_type=event_type,
                reason_code=reason_code,
                raw=raw,
            )
        )
        self.quarantined_count += 1
        self._log.event("event_quarantined", event_type=event_type, reason_code=reason_code.value)
