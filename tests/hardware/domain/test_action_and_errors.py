from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from lumneo.hardware.domain.action import (
    PHYSICAL_ACTION_KIND,
    TERMINAL_ACTION_STATUSES,
    ActionResult,
    HardwareAction,
)
from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.domain.errors import (
    DEFAULT_RETRYABLE,
    FROZEN_ERROR_CODES,
    HardwareError,
)


NOW = datetime(2026, 8, 23, 8, 0, tzinfo=timezone.utc)

EXPECTED_ACTION_FIELDS = (
    "action_id",
    "action_kind",
    "device_id",
    "capability_id",
    "parameters",
    "requester",
    "status",
    "idempotency_key",
    "timeout_ms",
    "correlation_id",
    "context_ref",
    "expected_device_version",
    "parameters_digest",
    "approval_expires_at",
    "created_at",
    "updated_at",
)

EXPECTED_RESULT_FIELDS = (
    "action_id",
    "status",
    "output",
    "error",
    "started_at",
    "finished_at",
    "device_acknowledged",
)

EXPECTED_ERROR_FIELDS = ("code", "message", "retryable", "details")

EXPECTED_ERROR_CODES = (
    "DEVICE_NOT_FOUND",
    "DEVICE_OFFLINE",
    "DEVICE_DISABLED",
    "CAPABILITY_NOT_FOUND",
    "CAPABILITY_DISABLED",
    "INVALID_PARAMETERS",
    "APPROVAL_REQUIRED",
    "ACTION_REJECTED",
    "ACTION_TIMEOUT",
    "ACTION_CANCELLED",
    "DRIVER_UNAVAILABLE",
    "DRIVER_ERROR",
    "OUTPUT_VALIDATION_FAILED",
    "CONFLICT",
    "INTERNAL_ERROR",
)


def _action(**changes: object) -> HardwareAction:
    values: dict[str, object] = {
        "action_id": "action-01",
        "action_kind": PHYSICAL_ACTION_KIND,
        "device_id": "device-light-01",
        "capability_id": "device-light-01.set_brightness",
        "parameters": {"brightness": 75},
        "requester": "agent:hardware-assistant",
        "status": ActionStatus.CREATED,
        "idempotency_key": "request-42",
        "timeout_ms": 2_000,
        "correlation_id": "conversation-7",
        "context_ref": {"project_id": "project-3", "build_id": "build-9"},
        "expected_device_version": 4,
        "parameters_digest": "sha256:abc123",
        "approval_expires_at": NOW + timedelta(minutes=5),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return HardwareAction(**values)  # type: ignore[arg-type]


def _error(**changes: object) -> HardwareError:
    values: dict[str, object] = {
        "code": "DEVICE_OFFLINE",
        "message": "Device is offline",
        "retryable": True,
        "details": {"device_id": "device-light-01"},
    }
    values.update(changes)
    return HardwareError(**values)  # type: ignore[arg-type]


def test_models_have_exact_contract_fields() -> None:
    assert tuple(field.name for field in fields(HardwareAction)) == EXPECTED_ACTION_FIELDS
    assert tuple(field.name for field in fields(ActionResult)) == EXPECTED_RESULT_FIELDS
    assert tuple(field.name for field in fields(HardwareError)) == EXPECTED_ERROR_FIELDS


def test_action_serializes_all_contract_fields() -> None:
    serialized = _action().to_dict()

    assert tuple(serialized) == EXPECTED_ACTION_FIELDS
    assert serialized["action_kind"] == "physical_only"
    assert serialized["status"] == "created"
    assert serialized["approval_expires_at"] == "2026-08-23T08:05:00+00:00"
    assert json.loads(json.dumps(serialized)) == serialized


@pytest.mark.parametrize("action_kind", ["compile", "build", "simulate", "upload"])
def test_phase_zero_rejects_non_physical_action_kind(action_kind: str) -> None:
    with pytest.raises(ValueError, match="physical_only"):
        _action(action_kind=action_kind)


def test_context_ref_is_trace_only_string_data_and_serializes() -> None:
    action = _action(context_ref={"project_id": "p1", "workflow_id": "w1"})

    assert action.context_ref == {"project_id": "p1", "workflow_id": "w1"}
    assert action.to_dict()["context_ref"] == action.context_ref


@pytest.mark.parametrize(
    "context_ref",
    [{"project_id": 1}, {"": "project-1"}, {"project_id": ""}],
)
def test_context_ref_rejects_non_string_or_blank_trace_values(
    context_ref: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        _action(context_ref=context_ref)


def test_action_parameters_and_context_are_detached_from_inputs() -> None:
    parameters: dict[str, object] = {"brightness": 75}
    context = {"project_id": "p1"}
    action = _action(parameters=parameters, context_ref=context)

    parameters["brightness"] = 10
    context["project_id"] = "p2"

    assert action.parameters == {"brightness": 75}
    assert action.context_ref == {"project_id": "p1"}


@pytest.mark.parametrize("timeout_ms", [0, -1, 1.5, True])
def test_action_timeout_must_be_positive_integer(timeout_ms: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _action(timeout_ms=timeout_ms)


@pytest.mark.parametrize("version", [-1, 1.5, True])
def test_expected_device_version_validation(version: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        _action(expected_device_version=version)


def test_action_timestamps_cannot_move_backwards() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        _action(updated_at=NOW - timedelta(seconds=1))


def test_all_frozen_error_codes_are_exact_and_constructible() -> None:
    assert FROZEN_ERROR_CODES == EXPECTED_ERROR_CODES
    assert tuple(DEFAULT_RETRYABLE) == EXPECTED_ERROR_CODES
    for code in EXPECTED_ERROR_CODES:
        retryable = DEFAULT_RETRYABLE[code]
        error = _error(code=code, retryable=False if retryable is None else retryable)
        assert error.code == code


def test_unknown_error_code_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown HardwareError code"):
        _error(code="CONVENIENCE_ERROR")


def test_error_serializes_and_detaches_details() -> None:
    details: dict[str, object] = {"attempt": 1}
    error = _error(details=details)
    details["attempt"] = 2

    serialized = error.to_dict()
    assert serialized == {
        "code": "DEVICE_OFFLINE",
        "message": "Device is offline",
        "retryable": True,
        "details": {"attempt": 1},
    }
    assert json.loads(json.dumps(serialized)) == serialized


def test_error_rejects_non_serializable_details() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        _error(details={"callback": object()})


def test_terminal_status_set_matches_contract_exactly() -> None:
    assert TERMINAL_ACTION_STATUSES == {
        ActionStatus.SUCCEEDED,
        ActionStatus.FAILED,
        ActionStatus.REJECTED,
        ActionStatus.TIMED_OUT,
        ActionStatus.CANCELLED,
        ActionStatus.RECONCILIATION_REQUIRED,
    }


@pytest.mark.parametrize("status", sorted(TERMINAL_ACTION_STATUSES, key=lambda item: item.value))
def test_action_result_supports_every_terminal_status(status: ActionStatus) -> None:
    result = ActionResult(
        action_id="action-01",
        status=status,
        output=None,
        error=None,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=1),
        device_acknowledged=False,
    )

    assert result.status is status


def test_action_result_serializes_nested_error_and_output() -> None:
    result = ActionResult(
        action_id="action-01",
        status=ActionStatus.FAILED,
        output={"partial": True},
        error=_error(code="DRIVER_ERROR", retryable=False),
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=1),
        device_acknowledged=False,
    )

    serialized = result.to_dict()

    assert tuple(serialized) == EXPECTED_RESULT_FIELDS
    assert serialized["status"] == "failed"
    assert serialized["error"]["code"] == "DRIVER_ERROR"  # type: ignore[index]
    assert json.loads(json.dumps(serialized)) == serialized


def test_action_result_rejects_backwards_timestamps() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        ActionResult(
            action_id="action-01",
            status=ActionStatus.FAILED,
            output=None,
            error=_error(),
            started_at=NOW,
            finished_at=NOW - timedelta(seconds=1),
            device_acknowledged=False,
        )


def test_action_result_requires_hardware_error_and_boolean_ack() -> None:
    with pytest.raises(TypeError, match="HardwareError"):
        ActionResult("a", ActionStatus.FAILED, None, "error", NOW, NOW, False)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="bool"):
        ActionResult("a", ActionStatus.SUCCEEDED, {}, None, NOW, NOW, 1)  # type: ignore[arg-type]
