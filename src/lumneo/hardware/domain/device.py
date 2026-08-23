"""Device domain model from Hardware OS Contract section 4.1."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .enums import DeviceStatus


_SENSITIVE_METADATA_KEYS = frozenset(
    {"password", "secret", "token", "api_key", "credential"}
)


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _find_sensitive_key(value: object, path: str = "metadata") -> str | None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = key.casefold() if isinstance(key, str) else ""
            nested_path = f"{path}.{key}"
            if normalized_key in _SENSITIVE_METADATA_KEYS:
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


@dataclass(frozen=True, slots=True)
class Device:
    """Stable device identity with a Registry-derived capability snapshot."""

    id: str
    type: str
    name: str
    status: DeviceStatus
    capability_ids: tuple[str, ...]
    driver_id: str
    metadata: dict[str, object]
    last_seen_at: datetime | None
    version: int

    def __post_init__(self) -> None:
        _require_non_empty_string("id", self.id)
        _require_non_empty_string("type", self.type)
        _require_non_empty_string("name", self.name)
        _require_non_empty_string("driver_id", self.driver_id)

        if self.type != self.type.strip() or self.type != self.type.casefold():
            raise ValueError("type must be a stable lowercase identifier")
        if not isinstance(self.status, DeviceStatus):
            raise TypeError("status must be a DeviceStatus")
        if not isinstance(self.capability_ids, tuple):
            raise TypeError("capability_ids must be a read-only tuple snapshot")
        if any(not isinstance(item, str) or not item.strip() for item in self.capability_ids):
            raise ValueError("capability_ids must contain non-empty strings")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")
        if self.last_seen_at is not None and not isinstance(self.last_seen_at, datetime):
            raise TypeError("last_seen_at must be a datetime or None")
        if type(self.version) is not int or self.version < 0:
            raise ValueError("version must be a non-negative integer")

        try:
            json.dumps(self.metadata, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("metadata must contain only JSON-serializable values") from error

        sensitive_path = _find_sensitive_key(self.metadata)
        if sensitive_path is not None:
            raise ValueError(f"metadata must not contain sensitive key: {sensitive_path}")

        # Detach the model from the caller's mutable input while retaining the exact
        # Contract field shape (dict[str, object]).
        object.__setattr__(self, "metadata", deepcopy(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation using Contract string values."""

        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "status": self.status.value,
            "capability_ids": list(self.capability_ids),
            "driver_id": self.driver_id,
            "metadata": deepcopy(self.metadata),
            "last_seen_at": (
                self.last_seen_at.isoformat() if self.last_seen_at is not None else None
            ),
            "version": self.version,
        }


__all__ = ("Device",)
