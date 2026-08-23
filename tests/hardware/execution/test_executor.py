from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from lumneo.hardware.domain.action import PHYSICAL_ACTION_KIND, ActionResult, HardwareAction
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus, IdempotencyMode, RiskLevel
from lumneo.hardware.execution.dispatcher import ActionDispatcher
from lumneo.hardware.execution.executor import ActionExecutor
from lumneo.hardware.execution.lifecycle import ActionLifecycle
from lumneo.hardware.ports.permission_gate import (
    PermissionDecision,
    PermissionEvaluation,
)
from lumneo.hardware.simulation.faults import FaultProfile
from lumneo.hardware.simulation.light import SimulatedLightDriver
from lumneo.infrastructure.hardware.event_bus.in_process import InProcessEventBus
from lumneo.infrastructure.hardware.persistence.in_memory_repository import (
    InMemoryHardwareRepository,
)


NOW = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)


class FixedPermissionGate:
    def __init__(self, decision: PermissionDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def evaluate(self, action, capability) -> PermissionEvaluation:
        self.calls += 1
        return PermissionEvaluation(
            self.decision,
            capability.risk_level,
            f"permission_{self.decision.value}",
            None,
        )


class CountingLightDriver(SimulatedLightDriver):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.execute_calls = 0

    async def execute(self, action: HardwareAction) -> ActionResult:
        self.execute_calls += 1
        return await super().execute(action)


def _action(capability_id: str, parameters: dict[str, object], **changes: object) -> HardwareAction:
    values: dict[str, object] = {
        "action_id": "action-1",
        "action_kind": PHYSICAL_ACTION_KIND,
        "device_id": "simulated-light-01",
        "capability_id": capability_id,
        "parameters": parameters,
        "requester": "test",
        "status": ActionStatus.CREATED,
        "idempotency_key": None,
        "timeout_ms": 1_000,
        "correlation_id": None,
        "context_ref": None,
        "expected_device_version": None,
        "parameters_digest": "sha256:test",
        "approval_expires_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return HardwareAction(**values)  # type: ignore[arg-type]


async def _composition(
    *,
    decision: PermissionDecision = PermissionDecision.APPROVED,
    device_status: DeviceStatus = DeviceStatus.ONLINE,
    capability_enabled: bool = True,
    fault_profile: FaultProfile | None = None,
    trace: list[str] | None = None,
):
    repository = InMemoryHardwareRepository()
    bus = InProcessEventBus()
    driver = CountingLightDriver(fault_profile=fault_profile)
    await driver.initialize()
    await driver.connect("simulated-light-01")
    dispatcher = ActionDispatcher()
    dispatcher.register_driver(driver)
    capability = next(item for item in driver.capabilities if item.operation == "set_brightness")
    if not capability_enabled:
        capability = replace(capability, enabled=False)
    device = Device(
        "simulated-light-01",
        "light",
        "Light",
        device_status,
        (),
        driver.driver_id,
        {},
        NOW,
        0,
    )
    await repository.save_device(device)
    await repository.save_capability(capability)
    lifecycle = ActionLifecycle(
        transition_hook=lambda transition: repository.append_transition(
            transition.to_record()
        ),
        clock=lambda: NOW,
    )
    gate = FixedPermissionGate(decision)

    async def build_event(action: HardwareAction):
        return await bus.create_event(
            event_type=f"hardware.action.{action.status.value}",
            device_id=action.device_id,
            action_id=action.action_id,
            payload={"status": action.status.value},
            source="action_executor",
        )

    executor = ActionExecutor(
        repository=repository,
        permission_gate=gate,
        event_bus=bus,
        event_builder=build_event,
        dispatcher=dispatcher,
        lifecycle=lifecycle,
        observer=trace.append if trace is not None else None,
        clock=lambda: NOW,
    )
    return executor, repository, driver, gate, capability


def test_successful_simulated_action_preserves_observable_13_step_order() -> None:
    async def scenario():
        trace: list[str] = []
        executor, repository, driver, _, capability = await _composition(trace=trace)
        result = await executor.execute(
            _action(capability.id, {"brightness": 75})
        )
        return trace, result, await repository.get_action("action-1"), driver.execute_calls

    trace, result, stored, calls = asyncio.run(scenario())
    assert trace == [
        "1.create",
        "2.lookup",
        "3.state_validate",
        "4.schema_validate",
        "5.idempotency",
        "6.permission",
        "7.persist_state",
        "8.driver",
        "9.outcome",
        "10.output_validate",
        "11.terminal_persist",
        "12.event",
        "13.return",
    ]
    assert result.status is ActionStatus.SUCCEEDED
    assert result.output == {"on": False, "brightness": 75}
    assert stored is not None and stored.status is ActionStatus.SUCCEEDED
    assert calls == 1


def test_invalid_parameters_never_call_driver() -> None:
    async def scenario():
        executor, _, driver, gate, capability = await _composition()
        result = await executor.execute(_action(capability.id, {"brightness": 101}))
        return result, driver.execute_calls, gate.calls

    result, calls, permission_calls = asyncio.run(scenario())
    assert result.error is not None and result.error.code == "INVALID_PARAMETERS"
    assert calls == 0
    assert permission_calls == 0


def test_offline_or_disabled_device_never_calls_driver() -> None:
    async def scenario(status: DeviceStatus):
        executor, _, driver, _, capability = await _composition(device_status=status)
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, driver.execute_calls

    offline, offline_calls = asyncio.run(scenario(DeviceStatus.OFFLINE))
    disabled, disabled_calls = asyncio.run(scenario(DeviceStatus.DISABLED))
    assert offline.error is not None and offline.error.code == "DEVICE_OFFLINE"
    assert disabled.error is not None and disabled.error.code == "DEVICE_DISABLED"
    assert offline_calls == disabled_calls == 0


def test_disabled_capability_never_calls_driver() -> None:
    async def scenario():
        executor, _, driver, _, capability = await _composition(capability_enabled=False)
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, driver.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.error is not None and result.error.code == "CAPABILITY_DISABLED"
    assert calls == 0


def test_permission_rejection_never_calls_driver_and_persists_rejected() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition(
            decision=PermissionDecision.REJECTED
        )
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, await repository.get_action("action-1"), driver.execute_calls

    result, stored, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.REJECTED
    assert result.error is not None and result.error.code == "ACTION_REJECTED"
    assert stored is not None and stored.status is ActionStatus.REJECTED
    assert calls == 0


def test_approval_required_waits_without_driver_call() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition(
            decision=PermissionDecision.APPROVAL_REQUIRED
        )
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, await repository.get_action("action-1"), driver.execute_calls

    result, stored, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.AWAITING_APPROVAL
    assert result.error is not None and result.error.code == "APPROVAL_REQUIRED"
    assert stored is not None and stored.status is ActionStatus.AWAITING_APPROVAL
    assert calls == 0


def test_invalid_driver_output_becomes_output_validation_failure() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition(
            fault_profile=FaultProfile(invalid_output=True)
        )
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, await repository.get_action("action-1"), driver.execute_calls

    result, stored, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert result.error is not None and result.error.code == "OUTPUT_VALIDATION_FAILED"
    assert stored is not None and stored.status is ActionStatus.FAILED
    assert calls == 1


def test_non_idempotent_failure_is_not_retried() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition(
            fault_profile=FaultProfile(driver_error="failed")
        )
        capability = replace(capability, idempotency=IdempotencyMode.NON_IDEMPOTENT)
        await repository.save_capability(capability)
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, driver.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert calls == 1
