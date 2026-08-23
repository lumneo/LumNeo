"""Physical HardwareAction and ActionResult data contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .enums import ActionStatus
from .errors import HardwareError


PHYSICAL_ACTION_KIND = "physical_only"
TERMINAL_ACTION_STATUSES = frozenset(
    {
        ActionStatus.SUCCEEDED,
        ActionStatus.FAILED,
        ActionStatus.REJECTED,
        ActionStatus.TIMED_OUT,
        ActionStatus.CANCELLED,
        ActionStatus.RECONCILIATION_REQUIRED,
    }
)


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _copy_json_object(field_name: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dictionary")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} keys must be strings")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must contain only JSON-serializable values") from error
    return deepcopy(value)


def _validate_optional_string(field_name: str, value: object) -> None:
    if value is not None:
        _require_non_empty_string(field_name, value)


def _validate_optional_datetime(field_name: str, value: object) -> None:
    if value is not None and not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")


@dataclass(frozen=True, slots=True)
class HardwareAction:
    action_id: str
    action_kind: str
    device_id: str
    capability_id: str
    parameters: dict[str, object]
    requester: str
    status: ActionStatus
    idempotency_key: str | None
    timeout_ms: int
    correlation_id: str | None
    context_ref: dict[str, str] | None
    expected_device_version: int | None
    parameters_digest: str
    approval_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "action_id",
            "device_id",
            "capability_id",
            "requester",
            "parameters_digest",
        ):
            _require_non_empty_string(field_name, getattr(self, field_name))
        if self.action_kind != PHYSICAL_ACTION_KIND:
            raise ValueError(
                f"action_kind must be {PHYSICAL_ACTION_KIND!r} in Phase 0"
            )
        if not isinstance(self.status, ActionStatus):
            raise TypeError("status must be an ActionStatus")
        _validate_optional_string("idempotency_key", self.idempotency_key)
        _validate_optional_string("correlation_id", self.correlation_id)
        if type(self.timeout_ms) is not int or self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be a positive integer")
        if self.expected_device_version is not None and (
            type(self.expected_device_version) is not int
            or self.expected_device_version < 0
        ):
            raise ValueError("expected_device_version must be a non-negative integer or None")
        _validate_optional_datetime("approval_expires_at", self.approval_expires_at)
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be a datetime")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")

        object.__setattr__(
            self,
            "parameters",
            _copy_json_object("parameters", self.parameters),
        )
        if self.context_ref is not None:
            context_ref = _copy_json_object("context_ref", self.context_ref)
            if any(
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, str)
                or not value.strip()
                for key, value in context_ref.items()
            ):
                raise ValueError("context_ref must contain non-empty string keys and values")
            object.__setattr__(self, "context_ref", context_ref)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_kind": self.action_kind,
            "device_id": self.device_id,
            "capability_id": self.capability_id,
            "parameters": deepcopy(self.parameters),
            "requester": self.requester,
            "status": self.status.value,
            "idempotency_key": self.idempotency_key,
            "timeout_ms": self.timeout_ms,
            "correlation_id": self.correlation_id,
            "context_ref": deepcopy(self.context_ref),
            "expected_device_version": self.expected_device_version,
            "parameters_digest": self.parameters_digest,
            "approval_expires_at": (
                self.approval_expires_at.isoformat()
                if self.approval_expires_at is not None
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ActionResult:
    action_id: str
    status: ActionStatus
    output: dict[str, object] | None
    error: HardwareError | None
    started_at: datetime | None
    finished_at: datetime | None
    device_acknowledged: bool

    def __post_init__(self) -> None:
        _require_non_empty_string("action_id", self.action_id)
        if not isinstance(self.status, ActionStatus):
            raise TypeError("status must be an ActionStatus")
        if self.output is not None:
            object.__setattr__(self, "output", _copy_json_object("output", self.output))
        if self.error is not None and not isinstance(self.error, HardwareError):
            raise TypeError("error must be a HardwareError or None")
        _validate_optional_datetime("started_at", self.started_at)
        _validate_optional_datetime("finished_at", self.finished_at)
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not precede started_at")
        if type(self.device_acknowledged) is not bool:
            raise TypeError("device_acknowledged must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "status": self.status.value,
            "output": deepcopy(self.output),
            "error": self.error.to_dict() if self.error is not None else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "device_acknowledged": self.device_acknowledged,
        }


__all__ = (
    "ActionResult",
    "HardwareAction",
    "PHYSICAL_ACTION_KIND",
    "TERMINAL_ACTION_STATUSES",
)
