from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest

from lumneo.hardware.domain.action import ActionResult, HardwareAction
from lumneo.hardware.domain.enums import ActionStatus, IdempotencyMode
from lumneo.hardware.domain.errors import HardwareError
from lumneo.hardware.execution.lifecycle import ActionLifecycle
from lumneo.hardware.execution.recovery import RecoveryDisposition, RestartRecoveryService
from lumneo.infrastructure.hardware.persistence.in_memory_repository import InMemoryHardwareRepository

from tests.hardware.execution.test_executor import NOW, _action, _composition


class RetrySequenceMixin:
    failures_before_success = 0

    async def execute(self, action: HardwareAction) -> ActionResult:
        self.execute_calls += 1
        if self.execute_calls <= self.failures_before_success:
            return ActionResult(
                action.action_id,
                ActionStatus.FAILED,
                None,
                HardwareError("DRIVER_UNAVAILABLE", "transient", True, {}),
                NOW,
                NOW,
                False,
            )
        return ActionResult(
            action.action_id,
            ActionStatus.SUCCEEDED,
            {"on": False, "brightness": action.parameters["brightness"]},
            None,
            NOW,
            NOW,
            True,
        )


def test_idempotent_retryable_failure_retries_at_most_twice_with_same_action() -> None:
    async def scenario(failures: int):
        executor, _, driver, _, capability = await _composition()

        class RetryDriver(RetrySequenceMixin, type(driver)):
            failures_before_success = failures

        retry_driver = RetryDriver()
        await retry_driver.initialize()
        await retry_driver.connect("simulated-light-01")
        executor._dispatcher._drivers[driver.driver_id] = retry_driver
        action = _action(capability.id, {"brightness": 20})
        result = await executor.execute(action)
        return result, retry_driver.execute_calls

    recovered, recovered_calls = asyncio.run(scenario(2))
    exhausted, exhausted_calls = asyncio.run(scenario(99))
    assert recovered.status is ActionStatus.SUCCEEDED
    assert recovered_calls == 3
    assert exhausted.status is ActionStatus.FAILED
    assert exhausted_calls == 3


def test_non_retryable_failure_is_not_retried_even_when_idempotent() -> None:
    async def scenario():
        executor, _, driver, _, capability = await _composition()

        class NonRetryableDriver(type(driver)):
            async def execute(self, action: HardwareAction) -> ActionResult:
                self.execute_calls += 1
                return ActionResult(
                    action.action_id,
                    ActionStatus.FAILED,
                    None,
                    HardwareError("DRIVER_ERROR", "permanent", False, {}),
                    NOW,
                    NOW,
                    False,
                )

        failing = NonRetryableDriver()
        await failing.initialize()
        await failing.connect("simulated-light-01")
        executor._dispatcher._drivers[driver.driver_id] = failing
        result = await executor.execute(_action(capability.id, {"brightness": 20}))
        return result, failing.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert calls == 1


def test_key_required_same_key_returns_original_without_duplicate_execution() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition()
        capability = replace(capability, idempotency=IdempotencyMode.KEY_REQUIRED)
        await repository.save_capability(capability)
        first = _action(
            capability.id,
            {"brightness": 20},
            action_id="original-action",
            idempotency_key="stable-key",
        )
        duplicate = _action(
            capability.id,
            {"brightness": 20},
            action_id="duplicate-action",
            idempotency_key="stable-key",
        )
        first_result = await executor.execute(first)
        duplicate_result = await executor.execute(duplicate)
        return first_result, duplicate_result, driver.execute_calls

    first, duplicate, calls = asyncio.run(scenario())
    assert first.status is ActionStatus.SUCCEEDED
    assert duplicate == first
    assert duplicate.action_id == "original-action"
    assert calls == 1


def test_key_required_rejects_missing_key_and_changed_digest_without_driver() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition()
        capability = replace(capability, idempotency=IdempotencyMode.KEY_REQUIRED)
        await repository.save_capability(capability)
        missing = await executor.execute(
            _action(capability.id, {"brightness": 20}, action_id="missing")
        )
        original = await executor.execute(
            _action(
                capability.id,
                {"brightness": 20},
                action_id="original",
                idempotency_key="key",
            )
        )
        changed = await executor.execute(
            _action(
                capability.id,
                {"brightness": 21},
                action_id="changed",
                idempotency_key="key",
                parameters_digest="sha256:changed",
            )
        )
        return missing, original, changed, driver.execute_calls

    missing, original, changed, calls = asyncio.run(scenario())
    assert missing.error is not None and missing.error.code == "INVALID_PARAMETERS"
    assert original.status is ActionStatus.SUCCEEDED
    assert changed.error is not None and changed.error.code == "CONFLICT"
    assert calls == 1


async def _recover(action: HardwareAction):
    repository = InMemoryHardwareRepository()
    await repository.save_action(action)
    lifecycle = ActionLifecycle(
        transition_hook=lambda transition: repository.append_transition(transition.to_record()),
        clock=lambda: NOW,
    )
    service = RestartRecoveryService(repository, lifecycle, clock=lambda: NOW)
    result = await service.recover(action.action_id)
    return result, repository


@pytest.mark.parametrize(
    "status",
    [ActionStatus.CREATED, ActionStatus.VALIDATING, ActionStatus.APPROVED],
)
def test_restart_revalidates_safe_resumable_states(status: ActionStatus) -> None:
    result, _ = asyncio.run(_recover(_action("capability-1", {}, status=status)))
    assert result.action.status is status
    assert result.disposition is RecoveryDisposition.REVALIDATE
    assert result.automatic_retry is False


def test_restart_waits_for_live_approval_and_rejects_expired_approval() -> None:
    waiting, _ = asyncio.run(
        _recover(
            _action(
                "capability-1",
                {},
                status=ActionStatus.AWAITING_APPROVAL,
                approval_expires_at=NOW + timedelta(minutes=1),
            )
        )
    )
    expired, repository = asyncio.run(
        _recover(
            _action(
                "capability-1",
                {},
                status=ActionStatus.AWAITING_APPROVAL,
                approval_expires_at=NOW - timedelta(seconds=1),
            )
        )
    )
    assert waiting.disposition is RecoveryDisposition.WAIT_FOR_APPROVAL
    assert expired.action.status is ActionStatus.REJECTED
    assert expired.reason_code == "approval_expired"
    assert asyncio.run(repository.get_result("action-1")).status is ActionStatus.REJECTED


def test_running_restart_becomes_reconciliation_without_retry() -> None:
    result, repository = asyncio.run(
        _recover(_action("capability-1", {}, status=ActionStatus.RUNNING))
    )
    record = asyncio.run(repository.get_action_record("action-1"))
    assert result.action.status is ActionStatus.RECONCILIATION_REQUIRED
    assert result.disposition is RecoveryDisposition.TERMINAL
    assert result.automatic_retry is False
    assert record is not None
    assert record["result"].status is ActionStatus.RECONCILIATION_REQUIRED
    assert record["reconciliations"][0]["automatic_retry"] is False


def test_reconciliation_terminal_is_immutable_and_never_retried() -> None:
    result, _ = asyncio.run(
        _recover(
            _action("capability-1", {}, status=ActionStatus.RECONCILIATION_REQUIRED)
        )
    )
    assert result.action.status is ActionStatus.RECONCILIATION_REQUIRED
    assert result.disposition is RecoveryDisposition.TERMINAL
    assert result.automatic_retry is False
