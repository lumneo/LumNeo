"""Deterministic action classification and transition after process restart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, unique

from ..domain.action import ActionResult, HardwareAction, TERMINAL_ACTION_STATUSES
from ..domain.enums import ActionStatus
from ..domain.errors import HardwareError
from ..ports.repository import HardwareRepository
from .lifecycle import ActionLifecycle


@unique
class RecoveryDisposition(str, Enum):
    REVALIDATE = "revalidate"
    WAIT_FOR_APPROVAL = "wait_for_approval"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    action: HardwareAction
    disposition: RecoveryDisposition
    automatic_retry: bool
    reason_code: str


class RestartRecoveryService:
    def __init__(
        self,
        repository: HardwareRepository,
        lifecycle: ActionLifecycle,
        *,
        clock=None,
    ) -> None:
        self._repository = repository
        self._lifecycle = lifecycle
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def recover(self, action_id: str) -> RecoveryResult:
        action = await self._repository.get_action(action_id)
        if action is None:
            raise LookupError(f"Action not found: {action_id}")
        if action.status in {ActionStatus.CREATED, ActionStatus.VALIDATING, ActionStatus.APPROVED}:
            return RecoveryResult(
                action,
                RecoveryDisposition.REVALIDATE,
                False,
                f"restart_{action.status.value}_requires_revalidation",
            )
        if action.status is ActionStatus.AWAITING_APPROVAL:
            expiry = await self._approval_expiry(action)
            if expiry is None or self._clock() < expiry:
                return RecoveryResult(
                    action,
                    RecoveryDisposition.WAIT_FOR_APPROVAL,
                    False,
                    "restart_wait_for_approval",
                )
            rejected = await self._lifecycle.transition(
                action,
                ActionStatus.REJECTED,
                reason_code="approval_expired",
                reason_detail="Approval expired during restart recovery",
                actor="restart_recovery",
            )
            await self._repository.save_action(rejected)
            await self._repository.save_result(
                ActionResult(
                    action.action_id,
                    ActionStatus.REJECTED,
                    None,
                    HardwareError("ACTION_REJECTED", "Approval expired", False, {}),
                    None,
                    self._clock(),
                    False,
                )
            )
            return RecoveryResult(
                rejected,
                RecoveryDisposition.TERMINAL,
                False,
                "approval_expired",
            )
        if action.status is ActionStatus.RUNNING:
            unknown = await self._lifecycle.transition(
                action,
                ActionStatus.RECONCILIATION_REQUIRED,
                reason_code="restart_outcome_unknown",
                reason_detail="Process restarted while physical execution was running",
                actor="restart_recovery",
            )
            await self._repository.save_action(unknown)
            await self._repository.save_result(
                ActionResult(
                    action.action_id,
                    ActionStatus.RECONCILIATION_REQUIRED,
                    None,
                    HardwareError(
                        "ACTION_TIMEOUT",
                        "Physical outcome is unknown after restart",
                        False,
                        {"automatic_retry": False},
                    ),
                    None,
                    self._clock(),
                    False,
                )
            )
            await self._repository.append_reconciliation(
                {
                    "record_kind": "restart_outcome_unknown",
                    "action_id": action.action_id,
                    "automatic_retry": False,
                    "observed_at": self._clock().isoformat(),
                }
            )
            return RecoveryResult(
                unknown,
                RecoveryDisposition.TERMINAL,
                False,
                "restart_outcome_unknown",
            )
        if action.status in TERMINAL_ACTION_STATUSES:
            return RecoveryResult(
                action,
                RecoveryDisposition.TERMINAL,
                False,
                "restart_terminal_immutable",
            )
        raise AssertionError(f"Unhandled action status: {action.status.value}")

    async def _approval_expiry(self, action: HardwareAction) -> datetime | None:
        if action.approval_expires_at is not None:
            return action.approval_expires_at
        approvals = await self._repository.list_approvals(action.action_id)
        if not approvals:
            return None
        value = approvals[-1].get("expires_at")
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


__all__ = (
    "RecoveryDisposition",
    "RecoveryResult",
    "RestartRecoveryService",
)
