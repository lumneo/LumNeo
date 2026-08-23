"""Frozen Hardware OS error contract from section 4.6."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


FROZEN_ERROR_CODES = (
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

DEFAULT_RETRYABLE: dict[str, bool | None] = {
    "DEVICE_NOT_FOUND": False,
    "DEVICE_OFFLINE": True,
    "DEVICE_DISABLED": False,
    "CAPABILITY_NOT_FOUND": False,
    "CAPABILITY_DISABLED": False,
    "INVALID_PARAMETERS": False,
    "APPROVAL_REQUIRED": False,
    "ACTION_REJECTED": False,
    "ACTION_TIMEOUT": None,
    "ACTION_CANCELLED": False,
    "DRIVER_UNAVAILABLE": True,
    "DRIVER_ERROR": None,
    "OUTPUT_VALIDATION_FAILED": False,
    "CONFLICT": False,
    "INTERNAL_ERROR": False,
}


@dataclass(frozen=True, slots=True)
class HardwareError:
    code: str
    message: str
    retryable: bool
    details: dict[str, object]

    def __post_init__(self) -> None:
        if self.code not in FROZEN_ERROR_CODES:
            raise ValueError(f"unknown HardwareError code: {self.code}")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if type(self.retryable) is not bool:
            raise TypeError("retryable must be a bool")
        if not isinstance(self.details, dict):
            raise TypeError("details must be a dictionary")
        try:
            json.dumps(self.details, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("details must contain only JSON-serializable values") from error
        object.__setattr__(self, "details", deepcopy(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": deepcopy(self.details),
        }


__all__ = ("DEFAULT_RETRYABLE", "FROZEN_ERROR_CODES", "HardwareError")
