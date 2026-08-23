from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest
from jsonschema.exceptions import SchemaError, ValidationError

from lumneo.hardware.domain.capability import (
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    Capability,
)
from lumneo.hardware.domain.enums import IdempotencyMode, RiskLevel


EXPECTED_FIELDS = (
    "id",
    "device_id",
    "operation",
    "description",
    "input_schema",
    "output_schema",
    "schema_version",
    "revision",
    "risk_level",
    "idempotency",
    "timeout_ms",
    "enabled",
)

INPUT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "brightness": {"type": "integer", "minimum": 0, "maximum": 100}
    },
    "required": ["brightness"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
        "changed": {"type": "boolean"},
    },
    "required": ["brightness", "changed"],
    "additionalProperties": False,
}


def _capability(**changes: object) -> Capability:
    values: dict[str, object] = {
        "id": "device-light-01.set_brightness",
        "device_id": "device-light-01",
        "operation": "set_brightness",
        "description": "Set light brightness from 0 to 100",
        "input_schema": INPUT_SCHEMA,
        "output_schema": OUTPUT_SCHEMA,
        "schema_version": "1.0.0",
        "revision": 2,
        "risk_level": RiskLevel.LOW,
        "idempotency": IdempotencyMode.IDEMPOTENT,
        "timeout_ms": 2_000,
        "enabled": True,
    }
    values.update(changes)
    return Capability(**values)  # type: ignore[arg-type]


def test_capability_has_exact_contract_fields() -> None:
    assert tuple(field.name for field in fields(Capability)) == EXPECTED_FIELDS


def test_capability_serializes_all_contract_fields() -> None:
    capability = _capability()

    serialized = capability.to_dict()

    assert tuple(serialized) == EXPECTED_FIELDS
    assert serialized["risk_level"] == "low"
    assert serialized["idempotency"] == "idempotent"
    assert serialized["schema_version"] == "1.0.0"
    assert serialized["revision"] == 2
    assert json.loads(json.dumps(serialized)) == serialized


@pytest.mark.parametrize("timeout_ms", [MIN_TIMEOUT_MS, 2_000, MAX_TIMEOUT_MS])
def test_timeout_accepts_phase_zero_bounds(timeout_ms: int) -> None:
    assert _capability(timeout_ms=timeout_ms).timeout_ms == timeout_ms


@pytest.mark.parametrize("timeout_ms", [99, 60_001, -1, 100.0, True])
def test_timeout_rejects_values_outside_phase_zero_contract(
    timeout_ms: object,
) -> None:
    with pytest.raises(ValueError, match="between 100 and 60000"):
        _capability(timeout_ms=timeout_ms)


def test_input_schema_accepts_valid_parameters() -> None:
    _capability().validate_input({"brightness": 75})


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"brightness": -1},
        {"brightness": 101},
        {"brightness": 50.5},
        {"brightness": 50, "protocol": "mqtt"},
    ],
)
def test_input_schema_rejects_invalid_parameters(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _capability().validate_input(parameters)


def test_output_schema_accepts_valid_output() -> None:
    _capability().validate_output({"brightness": 75, "changed": True})


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"brightness": 75},
        {"brightness": 101, "changed": True},
        {"brightness": 75, "changed": "yes"},
        {"brightness": 75, "changed": True, "raw_packet": "00ff"},
    ],
)
def test_output_schema_rejects_invalid_output(output: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _capability().validate_output(output)


def test_invalid_json_schema_is_rejected_at_construction() -> None:
    with pytest.raises(SchemaError):
        _capability(input_schema={"type": "not-a-json-schema-type"})


@pytest.mark.parametrize("field_name", ["input_schema", "output_schema"])
def test_schema_fields_require_dictionary(field_name: str) -> None:
    with pytest.raises(TypeError, match="JSON Schema dictionary"):
        _capability(**{field_name: []})


def test_schema_must_be_json_serializable() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        _capability(input_schema={"type": "object", "custom": object()})


def test_constructor_schema_mutation_does_not_change_capability() -> None:
    input_schema = {
        "type": "object",
        "properties": {"brightness": {"type": "integer"}},
    }
    capability = _capability(input_schema=input_schema)

    input_schema["type"] = "string"

    assert capability.input_schema["type"] == "object"


def test_serialized_schemas_are_detached_from_domain_state() -> None:
    capability = _capability()
    serialized = capability.to_dict()
    serialized_input = serialized["input_schema"]
    assert isinstance(serialized_input, dict)

    serialized_input["type"] = "string"

    assert capability.input_schema["type"] == "object"


@pytest.mark.parametrize("enabled", [True, False])
def test_enabled_state_is_preserved(enabled: bool) -> None:
    capability = _capability(enabled=enabled)

    assert capability.enabled is enabled
    assert capability.to_dict()["enabled"] is enabled


@pytest.mark.parametrize("enabled", [0, 1, "true", None])
def test_enabled_requires_boolean(enabled: object) -> None:
    with pytest.raises(TypeError, match="bool"):
        _capability(enabled=enabled)


def test_schema_version_and_revision_are_independent_surfaces() -> None:
    original = _capability(schema_version="2.1.0", revision=4)
    revised_configuration = replace(original, revision=5)

    assert revised_configuration.schema_version == "2.1.0"
    assert revised_configuration.revision == 5


@pytest.mark.parametrize("revision", [-1, 1.5, True])
def test_revision_requires_non_negative_integer(revision: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        _capability(revision=revision)


@pytest.mark.parametrize(
    "operation",
    [
        "mqtt_publish",
        "serial_write",
        "usb_transfer",
        "http_post",
        "bluetooth_send",
        "ble_write",
    ],
)
def test_protocol_operations_are_forbidden(operation: str) -> None:
    with pytest.raises(ValueError, match="not a transport protocol"):
        _capability(operation=operation)


@pytest.mark.parametrize("operation", ["Set_Brightness", " set_brightness", "set_brightness "])
def test_operation_requires_stable_lowercase_identifier(operation: str) -> None:
    with pytest.raises(ValueError, match="lowercase"):
        _capability(operation=operation)


def test_exact_risk_and_idempotency_values_are_preserved() -> None:
    assert {member.name: member.value for member in RiskLevel} == {
        "READ_ONLY": "read_only",
        "LOW": "low",
        "MEDIUM": "medium",
        "HIGH": "high",
        "CRITICAL": "critical",
    }
    assert {member.name: member.value for member in IdempotencyMode} == {
        "IDEMPOTENT": "idempotent",
        "KEY_REQUIRED": "key_required",
        "NON_IDEMPOTENT": "non_idempotent",
    }


def test_risk_and_idempotency_require_frozen_enum_types() -> None:
    with pytest.raises(TypeError, match="RiskLevel"):
        _capability(risk_level="low")
    with pytest.raises(TypeError, match="IdempotencyMode"):
        _capability(idempotency="idempotent")
