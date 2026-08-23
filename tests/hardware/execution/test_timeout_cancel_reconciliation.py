from __future__ import annotations

import asyncio

from lumneo.hardware.domain.action import ActionResult, HardwareAction
from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.execution.reliability import ConfirmedNotExecutedTimeout

from .test_executor import NOW, _action, _composition


class ControlledDriverMixin:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancel_confirmed = False

    async def execute(self, action: HardwareAction) -> ActionResult:
        self.execute_calls += 1
        self.started.set()
        await self.release.wait()
        return ActionResult(
            action.action_id,
            ActionStatus.SUCCEEDED,
            {"on": False, "brightness": action.parameters["brightness"]},
            None,
            NOW,
            NOW,
            True,
        )

    async def cancel(self, action_id: str) -> bool:
        return self.cancel_confirmed


def _install_driver(executor, old_driver, new_driver) -> None:
    executor._dispatcher._drivers[old_driver.driver_id] = new_driver


def test_local_timeout_with_possible_execution_requires_reconciliation_and_no_retry() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition()

        class SlowDriver(ControlledDriverMixin, type(driver)):
            pass

        slow = SlowDriver()
        await slow.initialize()
        await slow.connect("simulated-light-01")
        _install_driver(executor, driver, slow)
        result = await executor.execute(
            _action(capability.id, {"brightness": 20}, timeout_ms=1)
        )
        slow.release.set()
        await asyncio.gather(*executor._background_tasks)
        return (
            result,
            await repository.get_action_record("action-1"),
            slow.execute_calls,
        )

    result, record, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.RECONCILIATION_REQUIRED
    assert result.error is not None and result.error.code == "ACTION_TIMEOUT"
    assert result.error.details["automatic_retry"] is False
    assert calls == 1
    assert record is not None
    assert record["reconciliations"][0]["record_kind"] == "outcome_unknown"
    assert record["action"].status is ActionStatus.RECONCILIATION_REQUIRED
    assert record["reconciliations"][1]["record_kind"] == "late_result"
    assert record["reconciliations"][1]["accepted_status"] == "reconciliation_required"


def test_adapter_confirmed_not_executed_timeout_is_timed_out() -> None:
    async def scenario():
        executor, _, driver, _, capability = await _composition()

        class ConfirmingDriver(type(driver)):
            async def execute(self, action: HardwareAction) -> ActionResult:
                self.execute_calls += 1
                raise ConfirmedNotExecutedTimeout

        confirming = ConfirmingDriver()
        await confirming.initialize()
        await confirming.connect("simulated-light-01")
        _install_driver(executor, driver, confirming)
        return await executor.execute(_action(capability.id, {"brightness": 20}))

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.TIMED_OUT
    assert result.error is not None
    assert result.error.details["outcome_certainty"] == "confirmed_not_executed"


def test_cancel_before_running_never_calls_driver() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition()
        action = _action(capability.id, {"brightness": 20})
        await repository.save_action(action)
        result = await executor.cancel(action.action_id, requester=action.requester)
        return result, await repository.get_action(action.action_id), driver.execute_calls

    result, stored, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.CANCELLED
    assert stored is not None and stored.status is ActionStatus.CANCELLED
    assert calls == 0


def test_running_cancel_requires_driver_confirmation() -> None:
    async def scenario(confirm: bool):
        executor, repository, driver, _, capability = await _composition()

        class ControlledDriver(ControlledDriverMixin, type(driver)):
            pass

        controlled = ControlledDriver()
        controlled.cancel_confirmed = confirm
        await controlled.initialize()
        await controlled.connect("simulated-light-01")
        _install_driver(executor, driver, controlled)
        execution = asyncio.create_task(
            executor.execute(_action(capability.id, {"brightness": 20}))
        )
        await controlled.started.wait()
        cancellation = await executor.cancel("action-1", requester="test")
        stored = await repository.get_action("action-1")
        controlled.release.set()
        completed = await execution
        return cancellation, stored, completed

    unconfirmed, still_running, completed = asyncio.run(scenario(False))
    assert unconfirmed.error is not None
    assert unconfirmed.error.code == "CONFLICT"
    assert still_running is not None and still_running.status is ActionStatus.RUNNING
    assert completed.status is ActionStatus.SUCCEEDED

    confirmed, cancelled, completed = asyncio.run(scenario(True))
    assert confirmed.status is ActionStatus.CANCELLED
    assert cancelled is not None and cancelled.status is ActionStatus.CANCELLED
    assert completed.status is ActionStatus.CANCELLED


def test_first_terminal_wins_and_late_driver_result_is_audit_only() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition()

        class ControlledDriver(ControlledDriverMixin, type(driver)):
            pass

        controlled = ControlledDriver()
        controlled.cancel_confirmed = True
        await controlled.initialize()
        await controlled.connect("simulated-light-01")
        _install_driver(executor, driver, controlled)
        execution = asyncio.create_task(
            executor.execute(_action(capability.id, {"brightness": 20}))
        )
        await controlled.started.wait()
        cancelled = await executor.cancel("action-1", requester="test")
        controlled.release.set()
        returned = await execution
        record = await repository.get_action_record("action-1")
        return cancelled, returned, record

    cancelled, returned, record = asyncio.run(scenario())
    assert cancelled.status is returned.status is ActionStatus.CANCELLED
    assert record is not None
    assert record["action"].status is ActionStatus.CANCELLED
    late = [
        item for item in record["reconciliations"]
        if item["record_kind"] == "late_result"
    ]
    assert len(late) == 1
    assert late[0]["late_result"]["status"] == "succeeded"


def test_driver_terminal_wins_before_later_cancel_request() -> None:
    async def scenario():
        executor, repository, _, _, capability = await _composition()
        succeeded = await executor.execute(_action(capability.id, {"brightness": 20}))
        cancellation = await executor.cancel("action-1", requester="test")
        return succeeded, cancellation, await repository.get_action("action-1")

    succeeded, cancellation, stored = asyncio.run(scenario())
    assert succeeded.status is ActionStatus.SUCCEEDED
    assert cancellation.error is not None and cancellation.error.code == "CONFLICT"
    assert stored is not None and stored.status is ActionStatus.SUCCEEDED


def test_unauthorized_or_terminal_cancel_does_not_change_state() -> None:
    async def scenario():
        executor, repository, _, _, capability = await _composition()
        action = _action(capability.id, {"brightness": 20})
        await repository.save_action(action)
        denied = await executor.cancel(action.action_id, requester="someone-else")
        accepted = await executor.cancel(action.action_id, requester="test")
        conflict = await executor.cancel(action.action_id, requester="test")
        return denied, accepted, conflict, await repository.get_action(action.action_id)

    denied, accepted, conflict, stored = asyncio.run(scenario())
    assert denied.error is not None and denied.error.code == "ACTION_REJECTED"
    assert accepted.status is ActionStatus.CANCELLED
    assert conflict.error is not None and conflict.error.code == "CONFLICT"
    assert stored is not None and stored.status is ActionStatus.CANCELLED
