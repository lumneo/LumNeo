"""Deterministic Phase 0 local permission policy."""

from __future__ import annotations

from dataclasses import dataclass

from lumneo.hardware.domain.action import HardwareAction
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.enums import RiskLevel
from lumneo.hardware.ports.permission_gate import (
    PermissionDecision,
    PermissionEvaluation,
)


@dataclass(frozen=True, slots=True)
class LocalPermissionPolicyConfig:
    """Explicit policy switches; no learned or historical authorization."""

    low_auto_approve: bool = False

    def __post_init__(self) -> None:
        if type(self.low_auto_approve) is not bool:
            raise TypeError("low_auto_approve must be a bool")


class LocalPermissionGate:
    def __init__(self, config: LocalPermissionPolicyConfig | None = None) -> None:
        self._config = config or LocalPermissionPolicyConfig()

    async def evaluate(
        self,
        action: HardwareAction,
        capability: Capability,
    ) -> PermissionEvaluation:
        """Evaluate the frozen risk matrix after caller-side schema validation."""
        risk = capability.risk_level
        if risk is RiskLevel.READ_ONLY:
            return self._evaluation(
                PermissionDecision.APPROVED,
                risk,
                "read_only_auto_approved",
                "READ_ONLY is auto-approved by the Phase 0 local policy",
            )
        if risk is RiskLevel.LOW:
            if self._config.low_auto_approve:
                return self._evaluation(
                    PermissionDecision.APPROVED,
                    risk,
                    "low_auto_approved",
                    "LOW auto-approval is explicitly enabled",
                )
            return self._evaluation(
                PermissionDecision.APPROVAL_REQUIRED,
                risk,
                "low_confirmation_required",
                "LOW auto-approval is disabled",
            )
        if risk is RiskLevel.MEDIUM:
            return self._evaluation(
                PermissionDecision.APPROVAL_REQUIRED,
                risk,
                "medium_confirmation_required",
                "MEDIUM requires per-action confirmation",
            )
        if risk is RiskLevel.HIGH:
            return self._evaluation(
                PermissionDecision.APPROVAL_REQUIRED,
                risk,
                "high_explicit_confirmation_required",
                "HIGH requires explicit non-model approval",
            )
        return self._evaluation(
            PermissionDecision.REJECTED,
            RiskLevel.CRITICAL,
            "critical_rejected_phase_0",
            "CRITICAL actions are forbidden in Phase 0",
        )

    @staticmethod
    def _evaluation(
        decision: PermissionDecision,
        risk: RiskLevel,
        reason_code: str,
        reason_detail: str,
    ) -> PermissionEvaluation:
        return PermissionEvaluation(decision, risk, reason_code, reason_detail)


__all__ = ("LocalPermissionGate", "LocalPermissionPolicyConfig")
