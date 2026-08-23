"""Capability domain model from Hardware OS Contract section 4.2."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from jsonschema.protocols import Validator
from jsonschema.validators import validator_for

from .enums import IdempotencyMode, RiskLevel


MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 60_000

_PROTOCOL_OPERATION_PREFIXES = (
    "ble_",
    "bluetooth_",
    "http_",
    "mqtt_",
    "serial_",
    "usb_",
)


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validated_schema(field_name: str, schema: object) -> dict[str, object]:
    if not isinstance(schema, dict):
        raise TypeError(f"{field_name} must be a JSON Schema dictionary")
    try:
        json.dumps(schema, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be JSON-serializable") from error

    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return deepcopy(schema)


@dataclass(frozen=True, slots=True)
class Capability:
    """Protocol-neutral operation contract advertised by a Device."""

    id: str
    device_id: str
    operation: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    schema_version: str
    revision: int
    risk_level: RiskLevel
    idempotency: IdempotencyMode
    timeout_ms: int
    enabled: bool

    def __post_init__(self) -> None:
        _require_non_empty_string("id", self.id)
        _require_non_empty_string("device_id", self.device_id)
        _require_non_empty_string("operation", self.operation)
        _require_non_empty_string("description", self.description)
        _require_non_empty_string("schema_version", self.schema_version)

        if self.operation != self.operation.strip() or self.operation != self.operation.casefold():
            raise ValueError("operation must be a stable lowercase identifier")
        if self.operation.startswith(_PROTOCOL_OPERATION_PREFIXES):
            raise ValueError("operation must describe a capability, not a transport protocol")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be a non-negative integer")
        if not isinstance(self.risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel")
        if not isinstance(self.idempotency, IdempotencyMode):
            raise TypeError("idempotency must be an IdempotencyMode")
        if type(self.timeout_ms) is not int or not (
            MIN_TIMEOUT_MS <= self.timeout_ms <= MAX_TIMEOUT_MS
        ):
            raise ValueError(
                f"timeout_ms must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}"
            )
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be a bool")

        object.__setattr__(
            self,
            "input_schema",
            _validated_schema("input_schema", self.input_schema),
        )
        object.__setattr__(
            self,
            "output_schema",
            _validated_schema("output_schema", self.output_schema),
        )

    @staticmethod
    def _validator(schema: dict[str, object]) -> Validator:
        validator_class = validator_for(schema)
        return validator_class(schema)

    def validate_input(self, parameters: dict[str, object]) -> None:
        """Raise jsonschema.ValidationError when input violates the contract."""

        self._validator(self.input_schema).validate(parameters)

    def validate_output(self, output: dict[str, object]) -> None:
        """Raise jsonschema.ValidationError when output violates the contract."""

        self._validator(self.output_schema).validate(output)

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible representation."""

        return {
            "id": self.id,
            "device_id": self.device_id,
            "operation": self.operation,
            "description": self.description,
            "input_schema": deepcopy(self.input_schema),
            "output_schema": deepcopy(self.output_schema),
            "schema_version": self.schema_version,
            "revision": self.revision,
            "risk_level": self.risk_level.value,
            "idempotency": self.idempotency.value,
            "timeout_ms": self.timeout_ms,
            "enabled": self.enabled,
        }


__all__ = ("Capability", "MAX_TIMEOUT_MS", "MIN_TIMEOUT_MS")
