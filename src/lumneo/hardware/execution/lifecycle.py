"""Guarded HardwareAction state machine with transition-recording hook."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ..domain.action import HardwareAction, TERMINAL_ACTION_STATUSES
from ..domain.enums import ActionStatus


LEGAL_ACTION_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    ActionStatus.CREATED: frozenset(
        {ActionStatus.VALIDATING, ActionStatus.CANCELLED}
    ),
    ActionStatus.VALIDATING: frozenset(
        {
            ActionStatus.FAILED,
            ActionStatus.AWAITING_APPROVAL,
            ActionStatus.APPROVED,
            ActionStatus.CANCELLED,
        }
    ),
    ActionStatus.AWAITING_APPROVAL: frozenset(
        {ActionStatus.APPROVED, ActionStatus.REJECTED, ActionStatus.CANCELLED}
    ),
    ActionStatus.APPROVED: frozenset(
        {ActionStatus.RUNNING, ActionStatus.CANCELLED}
    ),
    ActionStatus.RUNNING: frozenset(
        {
            ActionStatus.SUCCEEDED,
            ActionStatus.FAILED,
            ActionStatus.TIMED_OUT,
            ActionStatus.CANCELLED,
            ActionStatus.RECONCILIATION_REQUIRED,
        }
    ),
    **{status: frozenset() for status in TERMINAL_ACTION_STATUSES},
}


@dataclass(frozen=True, slots=True)
class ActionTransition:
    action_id: str
    from_status: ActionStatus
    to_status: ActionStatus
    reason_code: str
    reason_detail: str | None
    actor: str
    occurred_at: datetime
    action_version: int

    def to_record(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "actor": self.actor,
            "occurred_at": self.occurred_at.isoformat(),
            "action_version": self.action_version,
        }


TransitionHook = Callable[[ActionTransition], Awaitable[None]]


class ActionTransitionError(ValueError):
    pass


class StaleActionError(ActionTransitionError):
    pass


class ActionLifecycle:
    def __init__(
        self,
        *,
        transition_hook: TransitionHook,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._transition_hook = transition_hook
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._states: dict[str, tuple[ActionStatus, int]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def register(self, action: HardwareAction, *, action_version: int = 0) -> None:
        if type(action_version) is not int or action_version < 0:
            raise ValueError("action_version must be a non-negative integer")
        if action.action_id in self._states:
            raise ValueError(f"action already registered: {action.action_id}")
        self._states[action.action_id] = (action.status, action_version)
        self._locks[action.action_id] = asyncio.Lock()

    def current(self, action_id: str) -> tuple[ActionStatus, int] | None:
        return self._states.get(action_id)

    async def transition(
        self,
        action: HardwareAction,
        to_status: ActionStatus,
        *,
        reason_code: str,
        actor: str,
        reason_detail: str | None = None,
    ) -> HardwareAction:
        if not isinstance(to_status, ActionStatus):
            raise TypeError("to_status must be an ActionStatus")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValueError("reason_code must be a non-empty string")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        if reason_detail is not None and not isinstance(reason_detail, str):
            raise TypeError("reason_detail must be a string or None")

        if action.action_id not in self._states:
            self.register(action)
        lock = self._locks[action.action_id]
        async with lock:
            current_status, current_version = self._states[action.action_id]
            if action.status is not current_status:
                raise StaleActionError(
                    f"stale action status: supplied {action.status.value}, "
                    f"current {current_status.value}"
                )
            if to_status not in LEGAL_ACTION_TRANSITIONS[current_status]:
                raise ActionTransitionError(
                    f"illegal action transition: {current_status.value} -> {to_status.value}"
                )

            occurred_at = self._clock()
            next_version = current_version + 1
            transition = ActionTransition(
                action_id=action.action_id,
                from_status=current_status,
                to_status=to_status,
                reason_code=reason_code,
                reason_detail=reason_detail,
                actor=actor,
                occurred_at=occurred_at,
                action_version=next_version,
            )
            await self._transition_hook(transition)
            updated = replace(action, status=to_status, updated_at=occurred_at)
            self._states[action.action_id] = (to_status, next_version)
            return updated


__all__ = (
    "ActionLifecycle",
    "ActionTransition",
    "ActionTransitionError",
    "LEGAL_ACTION_TRANSITIONS",
    "StaleActionError",
    "TransitionHook",
)
