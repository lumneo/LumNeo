from __future__ import annotations

import asyncio
import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumneo.hardware.domain.action import PHYSICAL_ACTION_KIND, HardwareAction
from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.execution.lifecycle import (
    LEGAL_ACTION_TRANSITIONS,
    ActionLifecycle,
    ActionTransition,
    ActionTransitionError,
    StaleActionError,
)


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
IMPLEMENTATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "lumneo"
    / "hardware"
    / "execution"
    / "lifecycle.py"
)

EXPECTED_LEGAL_TRANSITIONS = {
    (ActionStatus.CREATED, ActionStatus.VALIDATING),
    (ActionStatus.CREATED, ActionStatus.CANCELLED),
    (ActionStatus.VALIDATING, ActionStatus.FAILED),
    (ActionStatus.VALIDATING, ActionStatus.AWAITING_APPROVAL),
    (ActionStatus.VALIDATING, ActionStatus.APPROVED),
    (ActionStatus.VALIDATING, ActionStatus.CANCELLED),
    (ActionStatus.AWAITING_APPROVAL, ActionStatus.APPROVED),
    (ActionStatus.AWAITING_APPROVAL, ActionStatus.REJECTED),
    (ActionStatus.AWAITING_APPROVAL, ActionStatus.CANCELLED),
    (ActionStatus.APPROVED, ActionStatus.RUNNING),
    (ActionStatus.APPROVED, ActionStatus.CANCELLED),
    (ActionStatus.RUNNING, ActionStatus.SUCCEEDED),
    (ActionStatus.RUNNING, ActionStatus.FAILED),
    (ActionStatus.RUNNING, ActionStatus.TIMED_OUT),
    (ActionStatus.RUNNING, ActionStatus.CANCELLED),
    (ActionStatus.RUNNING, ActionStatus.RECONCILIATION_REQUIRED),
}


def _action(status: ActionStatus, action_id: str = "action-1") -> HardwareAction:
    return HardwareAction(
        action_id=action_id,
        action_kind=PHYSICAL_ACTION_KIND,
        device_id="device-1",
        capability_id="device-1.turn_on",
        parameters={},
        requester="test",
        status=status,
        idempotency_key=None,
        timeout_ms=1_000,
        correlation_id=None,
        context_ref=None,
        expected_device_version=None,
        parameters_digest="sha256:test",
        approval_expires_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


class RecordingHook:
    def __init__(self) -> None:
        self.transitions: list[ActionTransition] = []

    async def __call__(self, transition: ActionTransition) -> None:
        self.transitions.append(transition)


def test_legal_transition_table_matches_contract_exactly() -> None:
    actual = {
        (from_status, to_status)
        for from_status, targets in LEGAL_ACTION_TRANSITIONS.items()
        for to_status in targets
    }
    assert set(LEGAL_ACTION_TRANSITIONS) == set(ActionStatus)
    assert actual == EXPECTED_LEGAL_TRANSITIONS


@pytest.mark.parametrize(
    "from_status,to_status",
    sorted(EXPECTED_LEGAL_TRANSITIONS, key=lambda pair: (pair[0].value, pair[1].value)),
)
def test_every_legal_transition_is_accepted_and_recorded(
    from_status: ActionStatus,
    to_status: ActionStatus,
) -> None:
    hook = RecordingHook()
    lifecycle = ActionLifecycle(transition_hook=hook, clock=lambda: NOW)
    action = _action(from_status)

    updated = asyncio.run(
        lifecycle.transition(
            action,
            to_status,
            reason_code="test_transition",
            reason_detail="contract path",
            actor="test",
        )
    )

    assert updated.status is to_status
    assert updated.updated_at == NOW
    assert lifecycle.current(action.action_id) == (to_status, 1)
    assert hook.transitions[0].to_record() == {
        "action_id": "action-1",
        "from_status": from_status.value,
        "to_status": to_status.value,
        "reason_code": "test_transition",
        "reason_detail": "contract path",
        "actor": "test",
        "occurred_at": "2026-08-23T12:00:00+00:00",
        "action_version": 1,
    }


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (ActionStatus.CREATED, ActionStatus.RUNNING),
        (ActionStatus.VALIDATING, ActionStatus.SUCCEEDED),
        (ActionStatus.AWAITING_APPROVAL, ActionStatus.RUNNING),
        (ActionStatus.APPROVED, ActionStatus.SUCCEEDED),
        (ActionStatus.RUNNING, ActionStatus.APPROVED),
    ],
)
def test_representative_illegal_transitions_are_rejected(
    from_status: ActionStatus,
    to_status: ActionStatus,
) -> None:
    hook = RecordingHook()
    lifecycle = ActionLifecycle(transition_hook=hook)

    with pytest.raises(ActionTransitionError, match="illegal action transition"):
        asyncio.run(
            lifecycle.transition(
                _action(from_status),
                to_status,
                reason_code="illegal",
                actor="test",
            )
        )

    assert hook.transitions == []


@pytest.mark.parametrize(
    "terminal",
    [
        ActionStatus.SUCCEEDED,
        ActionStatus.FAILED,
        ActionStatus.REJECTED,
        ActionStatus.TIMED_OUT,
        ActionStatus.CANCELLED,
        ActionStatus.RECONCILIATION_REQUIRED,
    ],
)
def test_terminal_states_are_immutable(terminal: ActionStatus) -> None:
    lifecycle = ActionLifecycle(transition_hook=RecordingHook())

    with pytest.raises(ActionTransitionError, match="illegal action transition"):
        asyncio.run(
            lifecycle.transition(
                _action(terminal),
                ActionStatus.CREATED,
                reason_code="rollback",
                actor="test",
            )
        )


def test_complete_success_path_increments_transition_version() -> None:
    async def scenario() -> tuple[HardwareAction, list[ActionTransition]]:
        hook = RecordingHook()
        lifecycle = ActionLifecycle(transition_hook=hook, clock=lambda: NOW)
        action = _action(ActionStatus.CREATED)
        for status in (
            ActionStatus.VALIDATING,
            ActionStatus.APPROVED,
            ActionStatus.RUNNING,
            ActionStatus.SUCCEEDED,
        ):
            action = await lifecycle.transition(
                action,
                status,
                reason_code="pipeline",
                actor="executor",
            )
        return action, hook.transitions

    action, transitions = asyncio.run(scenario())
    assert action.status is ActionStatus.SUCCEEDED
    assert [item.action_version for item in transitions] == [1, 2, 3, 4]


def test_same_running_snapshot_cannot_win_two_terminal_transitions() -> None:
    async def scenario():
        lifecycle = ActionLifecycle(transition_hook=RecordingHook(), clock=lambda: NOW)
        running = _action(ActionStatus.RUNNING)
        lifecycle.register(running, action_version=4)

        async def finish(status: ActionStatus):
            try:
                return await lifecycle.transition(
                    running,
                    status,
                    reason_code="terminal_race",
                    actor="executor",
                )
            except Exception as error:
                return error

        return await asyncio.gather(
            finish(ActionStatus.SUCCEEDED),
            finish(ActionStatus.TIMED_OUT),
        )

    results = asyncio.run(scenario())
    winners = [result for result in results if isinstance(result, HardwareAction)]
    losers = [result for result in results if isinstance(result, StaleActionError)]
    assert len(winners) == 1
    assert len(losers) == 1


def test_stale_action_snapshot_is_rejected_after_transition() -> None:
    async def scenario() -> None:
        lifecycle = ActionLifecycle(transition_hook=RecordingHook(), clock=lambda: NOW)
        created = _action(ActionStatus.CREATED)
        await lifecycle.transition(
            created,
            ActionStatus.VALIDATING,
            reason_code="start",
            actor="executor",
        )
        with pytest.raises(StaleActionError, match="stale action status"):
            await lifecycle.transition(
                created,
                ActionStatus.CANCELLED,
                reason_code="late_cancel",
                actor="user",
            )

    asyncio.run(scenario())


def test_failed_recording_hook_does_not_advance_lifecycle_state() -> None:
    async def broken_hook(transition: ActionTransition) -> None:
        raise RuntimeError("persistence unavailable")

    lifecycle = ActionLifecycle(transition_hook=broken_hook)
    action = _action(ActionStatus.CREATED)
    lifecycle.register(action, action_version=2)

    with pytest.raises(RuntimeError, match="persistence unavailable"):
        asyncio.run(
            lifecycle.transition(
                action,
                ActionStatus.VALIDATING,
                reason_code="start",
                actor="executor",
            )
        )

    assert lifecycle.current(action.action_id) == (ActionStatus.CREATED, 2)


def test_lifecycle_has_no_driver_permission_or_database_import() -> None:
    tree = ast.parse(IMPLEMENTATION_PATH.read_text(encoding="utf-8"))
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(
        forbidden in module
        for module in modules
        for forbidden in ("driver", "permission", "sqlalchemy", "sqlite3")
    )
