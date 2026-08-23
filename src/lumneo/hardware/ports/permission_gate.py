"""Permission evaluation Port and accepted decision contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Protocol, runtime_checkable

from ..domain.action import HardwareAction
from ..domain.capability import Capability
from ..domain.enums import RiskLevel


@unique
class PermissionDecision(str, Enum):
    APPROVED = "approved"
    APPROVAL_REQUIRED = "approval_required"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PermissionEvaluation:
    decision: PermissionDecision
    effective_risk: RiskLevel
    reason_code: str
    reason_detail: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PermissionDecision):
            raise TypeError("decision must be a PermissionDecision")
        if not isinstance(self.effective_risk, RiskLevel):
            raise TypeError("effective_risk must be a RiskLevel")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code must be a non-empty string")
        if self.reason_detail is not None and not isinstance(self.reason_detail, str):
            raise TypeError("reason_detail must be a string or None")


@runtime_checkable
class PermissionGate(Protocol):
    async def evaluate(
        self,
        action: HardwareAction,
        capability: Capability,
    ) -> PermissionEvaluation: ...


__all__ = ("PermissionDecision", "PermissionEvaluation", "PermissionGate")
