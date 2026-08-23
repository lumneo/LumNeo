"""Hardware domain-event and signal-event contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


_SENSITIVE_PAYLOAD_KEYS = frozenset(
    {"password", "secret", "token", "api_key", "credential"}
)
_SIGNAL_EVENT_TYPES = frozenset(
    {
        "gpio_change",
        "analog_change",
        "serial_output",
        "device_runtime_state_changed",
    }
)


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_optional_string(field_name: str, value: object) -> None:
    if value is not None:
        _require_non_empty_string(field_name, value)


def _validate_utc(timestamp: object) -> None:
    if not isinstance(timestamp, datetime):
        raise TypeError("timestamp must be a datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")


def _find_sensitive_key(value: object, path: str = "payload") -> str | None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized = key.casefold() if isinstance(key, str) else ""
            nested_path = f"{path}.{key}"
            if normalized in _SENSITIVE_PAYLOAD_KEYS:
                return nested_path
            found = _find_sensitive_key(nested_value, nested_path)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, nested_value in enumerate(value):
            found = _find_sensitive_key(nested_value, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _copy_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dictionary")
    if any(not isinstance(key, str) for key in payload):
        raise ValueError("payload keys must be strings")
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("payload must contain only JSON-serializable values") from error
    sensitive_path = _find_sensitive_key(payload)
    if sensitive_path is not None:
        raise ValueError(f"payload must not contain sensitive key: {sensitive_path}")
    return deepcopy(payload)


def _validate_sequence(field_name: str, value: object, *, optional: bool) -> None:
    if optional and value is None:
        return
    if type(value) is not int or value < 0:
        suffix = " or None" if optional else ""
        raise ValueError(f"{field_name} must be a non-negative integer{suffix}")


@dataclass(frozen=True, slots=True)
class HardwareDomainEvent:
    event_id: str
    event_type: str
    device_id: str | None
    action_id: str | None
    timestamp: datetime
    payload: dict[str, object]
    runtime_sequence: int
    source_sequence: int | None
    correlation_id: str | None
    source: str

    def __post_init__(self) -> None:
        _require_non_empty_string("event_id", self.event_id)
        _require_non_empty_string("event_type", self.event_type)
        _validate_optional_string("device_id", self.device_id)
        _validate_optional_string("action_id", self.action_id)
        _validate_optional_string("correlation_id", self.correlation_id)
        _require_non_empty_string("source", self.source)
        if not self.event_type.startswith("hardware."):
            raise ValueError("domain event_type must use the 'hardware.' prefix")
        if self.event_type.removeprefix("hardware.") in _SIGNAL_EVENT_TYPES:
            raise ValueError("signal/telemetry type cannot be a HardwareDomainEvent")
        _validate_utc(self.timestamp)
        _validate_sequence("runtime_sequence", self.runtime_sequence, optional=False)
        _validate_sequence("source_sequence", self.source_sequence, optional=True)
        object.__setattr__(self, "payload", _copy_payload(self.payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "device_id": self.device_id,
            "action_id": self.action_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": deepcopy(self.payload),
            "runtime_sequence": self.runtime_sequence,
            "source_sequence": self.source_sequence,
            "correlation_id": self.correlation_id,
            "source": self.source,
        }


# Accepted ADR-0002 permits this name only as a compatibility alias. It is the
# same type and therefore cannot develop a second schema or behavior.
HardwareEvent = HardwareDomainEvent


@dataclass(frozen=True, slots=True)
class HardwareSignalEvent:
    signal_id: str
    signal_type: str
    device_id: str
    timestamp: datetime
    payload: dict[str, object]
    source_sequence: int | None
    source: str

    def __post_init__(self) -> None:
        _require_non_empty_string("signal_id", self.signal_id)
        _require_non_empty_string("signal_type", self.signal_type)
        _require_non_empty_string("device_id", self.device_id)
        _require_non_empty_string("source", self.source)
        if self.signal_type.startswith("hardware."):
            raise ValueError("signal_type must not use the domain-event namespace")
        _validate_utc(self.timestamp)
        _validate_sequence("source_sequence", self.source_sequence, optional=True)
        object.__setattr__(self, "payload", _copy_payload(self.payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": deepcopy(self.payload),
            "source_sequence": self.source_sequence,
            "source": self.source,
        }


def new_domain_event(
    *,
    event_type: str,
    payload: dict[str, object],
    runtime_sequence: int,
    source: str,
    device_id: str | None = None,
    action_id: str | None = None,
    source_sequence: int | None = None,
    correlation_id: str | None = None,
    timestamp: datetime | None = None,
) -> HardwareDomainEvent:
    return HardwareDomainEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        device_id=device_id,
        action_id=action_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        payload=payload,
        runtime_sequence=runtime_sequence,
        source_sequence=source_sequence,
        correlation_id=correlation_id,
        source=source,
    )


def new_signal_event(
    *,
    signal_type: str,
    device_id: str,
    payload: dict[str, object],
    source: str,
    source_sequence: int | None = None,
    timestamp: datetime | None = None,
) -> HardwareSignalEvent:
    return HardwareSignalEvent(
        signal_id=str(uuid4()),
        signal_type=signal_type,
        device_id=device_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        payload=payload,
        source_sequence=source_sequence,
        source=source,
    )


__all__ = (
    "HardwareDomainEvent",
    "HardwareEvent",
    "HardwareSignalEvent",
    "new_domain_event",
    "new_signal_event",
)
