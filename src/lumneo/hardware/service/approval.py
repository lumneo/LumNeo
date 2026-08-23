"""Approval decisions bound to an exact physical action snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from ..domain.action import HardwareAction
from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.enums import ActionStatus, DeviceStatus, RiskLevel
from ..ports.permission_gate import PermissionDecision
from ..ports.repository import HardwareRepository


DEFAULT_APPROVAL_TTL = timedelta(minutes=5)
MAX_APPROVAL_TTL = timedelta(minutes=30)
ApproverKind = Literal["human", "model", "service"]


@dataclass(frozen=True, slots=True)
class ApprovalValidation:
    valid: bool
    reason_code: str
    reason_detail: str


@dataclass(frozen=True, slots=True)
class ApprovalDecisionRecord:
    action_id: str
    parameters_digest: str
    approver: str
    approver_kind: ApproverKind
    decision: PermissionDecision
    decided_at: datetime
    expires_at: datetime
    device_version: int
    capability_revision: int
    reason: str | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "parameters_digest": self.parameters_digest,
            "approver": self.approver,
            "approver_kind": self.approver_kind,
            "decision": self.decision.value,
            "decided_at": self.decided_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "device_version": self.device_version,
            "capability_revision": self.capability_revision,
            "reason": self.reason,
        }


class ApprovalError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ApprovalService:
    def __init__(self, repository: HardwareRepository, *, clock=None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def approve(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
        *,
        approver: str,
        approver_kind: ApproverKind = "human",
        ttl: timedelta = DEFAULT_APPROVAL_TTL,
    ) -> ApprovalDecisionRecord:
        if capability.risk_level is RiskLevel.HIGH and approver_kind == "model":
            raise ApprovalError("ACTION_REJECTED", "A model cannot approve a HIGH-risk action")
        return await self._decide(
            action,
            device,
            capability,
            approver=approver,
            approver_kind=approver_kind,
            decision=PermissionDecision.APPROVED,
            ttl=ttl,
        )

    async def reject(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
        *,
        approver: str,
        approver_kind: ApproverKind = "human",
        ttl: timedelta = DEFAULT_APPROVAL_TTL,
        reason: str | None = None,
    ) -> ApprovalDecisionRecord:
        return await self._decide(
            action,
            device,
            capability,
            approver=approver,
            approver_kind=approver_kind,
            decision=PermissionDecision.REJECTED,
            ttl=ttl,
            reason=reason,
        )

    async def _decide(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
        *,
        approver: str,
        approver_kind: ApproverKind,
        decision: PermissionDecision,
        ttl: timedelta,
        reason: str | None = None,
    ) -> ApprovalDecisionRecord:
        if action.status is not ActionStatus.AWAITING_APPROVAL:
            raise ApprovalError("CONFLICT", "Action is not awaiting approval")
        if not isinstance(approver, str) or not approver.strip():
            raise ValueError("approver must be a non-empty string")
        if approver_kind not in {"human", "model", "service"}:
            raise ValueError("approver_kind must be human, model, or service")
        if not isinstance(ttl, timedelta) or ttl <= timedelta(0):
            raise ValueError("ttl must be a positive timedelta")
        if ttl > MAX_APPROVAL_TTL:
            raise ValueError("ttl must not exceed 30 minutes")
        now = self._clock()
        record = ApprovalDecisionRecord(
            action.action_id,
            action.parameters_digest,
            approver,
            approver_kind,
            decision,
            now,
            now + ttl,
            device.version,
            capability.revision,
            reason,
        )
        await self._repository.save_approval(record.to_record())
        return record

    async def validate(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
    ) -> ApprovalValidation:
        records = await self._repository.list_approvals(action.action_id)
        if not records:
            return self._invalid("approval_missing", "No approval decision exists")
        record = records[-1]
        if record.get("decision") != PermissionDecision.APPROVED.value:
            return self._invalid("approval_rejected", "The latest decision is not approval")
        if record.get("parameters_digest") != action.parameters_digest:
            return self._invalid("approval_digest_changed", "Action parameters changed")
        if record.get("device_version") != device.version:
            return self._invalid("approval_device_changed", "Device version changed")
        if record.get("capability_revision") != capability.revision:
            return self._invalid("approval_capability_changed", "Capability revision changed")
        if device.status not in {DeviceStatus.ONLINE, DeviceStatus.DEGRADED}:
            return self._invalid("approval_device_unavailable", "Device is not executable")
        if not capability.enabled:
            return self._invalid("approval_capability_disabled", "Capability is disabled")
        expires_at = record.get("expires_at")
        if not isinstance(expires_at, str):
            return self._invalid("approval_invalid", "Approval expiry is invalid")
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            return self._invalid("approval_invalid", "Approval expiry is invalid")
        if self._clock() >= expiry:
            return self._invalid("approval_expired", "Approval expired")
        return ApprovalValidation(True, "approval_valid", "Approval binding is current")

    @staticmethod
    def _invalid(code: str, detail: str) -> ApprovalValidation:
        return ApprovalValidation(False, code, detail)


__all__ = (
    "ApprovalDecisionRecord",
    "ApprovalError",
    "ApprovalService",
    "ApprovalValidation",
    "DEFAULT_APPROVAL_TTL",
    "MAX_APPROVAL_TTL",
)
