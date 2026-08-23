from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import count

from lumneo.hardware.domain.enums import IdempotencyMode
from lumneo.hardware.execution.dispatcher import ActionDispatcher
from lumneo.hardware.execution.executor import ActionExecutor
from lumneo.hardware.execution.lifecycle import ActionLifecycle
from lumneo.hardware.facade import HardwareFacade
from lumneo.hardware.service.approval import ApprovalService
from lumneo.hardware.service.audit import AuditService
from lumneo.hardware.service.capability_registry import CapabilityRegistry
from lumneo.hardware.service.device_registry import DeviceRegistry
from lumneo.hardware.simulation.faults import FaultProfile
from lumneo.hardware.simulation.light import SimulatedLightDriver
from lumneo.hardware.simulation.temperature_sensor import SimulatedTemperatureSensorDriver
from lumneo.infrastructure.hardware.event_bus.in_process import InProcessEventBus
from lumneo.infrastructure.hardware.permission.local_policy import (
    LocalPermissionGate,
    LocalPermissionPolicyConfig,
)
from lumneo.infrastructure.hardware.persistence.in_memory_repository import InMemoryHardwareRepository


class ControlledLightDriver(SimulatedLightDriver):
    def __init__(self, *, block: bool, cancel_confirmed: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self.execute_calls = 0
        self.started = asyncio.Event()
        self.release_event = asyncio.Event()
        self.block = block
        self.cancel_confirmed = cancel_confirmed

    async def execute(self, action):
        self.execute_calls += 1
        self.started.set()
        if self.block:
            await self.release_event.wait()
        return await super().execute(action)

    async def cancel(self, action_id: str) -> bool:
        return self.cancel_confirmed


@dataclass(slots=True)
class IntegrationHarness:
    facade: HardwareFacade
    _light: ControlledLightDriver
    _event_bus: InProcessEventBus

    @property
    def light_execution_count(self) -> int:
        return self._light.execute_calls

    async def wait_until_light_started(self) -> None:
        await self._light.started.wait()

    def release_light(self) -> None:
        self._light.release_event.set()

    async def subscribe(self, event_type, handler) -> str:
        return await self._event_bus.subscribe(event_type, handler)


async def build_integration_harness(
    *,
    now: datetime,
    low_auto_approve: bool = True,
    light_fault: FaultProfile | None = None,
    key_required: bool = False,
    block_light: bool = False,
    cancel_confirmed: bool = False,
) -> IntegrationHarness:
    repository = InMemoryHardwareRepository()
    event_bus = InProcessEventBus()
    devices = DeviceRegistry(status_change_hook=_noop)
    capabilities = CapabilityRegistry(device_registry=devices)
    dispatcher = ActionDispatcher()
    light = ControlledLightDriver(
        block=block_light,
        cancel_confirmed=cancel_confirmed,
        fault_profile=light_fault,
        clock=lambda: now,
    )
    temperature = SimulatedTemperatureSensorDriver(clock=lambda: now)
    for driver in (light, temperature):
        await driver.initialize()
        discovered = (await driver.discover())[0]
        await driver.connect(discovered.id)
        connected = (await driver.discover())[0]
        devices.register(connected)
        dispatcher.register_driver(driver)
        for advertised in driver.capabilities:
            capability = (
                replace(advertised, idempotency=IdempotencyMode.KEY_REQUIRED)
                if key_required and advertised.operation == "set_brightness"
                else advertised
            )
            capabilities.register(capability)
            await repository.save_capability(capability)
        current = devices.get(connected.id)
        assert current is not None
        await repository.save_device(current)
    lifecycle = ActionLifecycle(
        transition_hook=lambda transition: repository.append_transition(transition.to_record()),
        clock=lambda: now,
    )

    async def event_builder(action):
        return await event_bus.create_event(
            event_type=f"hardware.action.{action.status.value}",
            device_id=action.device_id,
            action_id=action.action_id,
            payload={"status": action.status.value},
            source="action_executor",
            correlation_id=action.correlation_id,
            timestamp=now,
        )

    ids = count(1)
    executor = ActionExecutor(
        repository=repository,
        permission_gate=LocalPermissionGate(
            LocalPermissionPolicyConfig(low_auto_approve=low_auto_approve)
        ),
        event_bus=event_bus,
        event_builder=event_builder,
        dispatcher=dispatcher,
        lifecycle=lifecycle,
        audit_writer=AuditService(repository, clock=lambda: now),
        clock=lambda: now,
    )
    facade = HardwareFacade(
        device_registry=devices,
        capability_registry=capabilities,
        executor=executor,
        approval_service=ApprovalService(repository, clock=lambda: now),
        repository=repository,
        clock=lambda: now,
        action_id_factory=lambda: f"integration-action-{next(ids)}",
    )
    return IntegrationHarness(facade, light, event_bus)


async def _noop(before, after) -> None:
    return None
