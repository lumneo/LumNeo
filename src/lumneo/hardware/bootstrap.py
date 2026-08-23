"""Phase 0 composition root that exposes only HardwareFacade."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .execution.dispatcher import ActionDispatcher
from .execution.executor import ActionExecutor
from .execution.lifecycle import ActionLifecycle
from .facade.hardware_facade import HardwareFacade
from .service.approval import ApprovalService
from .service.audit import AuditService
from .service.capability_registry import CapabilityRegistry
from .service.device_registry import DeviceRegistry
from .simulation.light import SimulatedLightDriver
from .simulation.temperature_sensor import SimulatedTemperatureSensorDriver
from lumneo.infrastructure.hardware.event_bus.in_process import InProcessEventBus
from lumneo.infrastructure.hardware.permission.local_policy import (
    LocalPermissionGate,
    LocalPermissionPolicyConfig,
)
from lumneo.infrastructure.hardware.persistence.in_memory_repository import (
    InMemoryHardwareRepository,
)


async def build_simulated_hardware_facade(
    *,
    low_auto_approve: bool = True,
    clock: Callable[[], datetime] | None = None,
    action_id_factory: Callable[[], str] | None = None,
) -> HardwareFacade:
    repository = InMemoryHardwareRepository()
    event_bus = InProcessEventBus()
    device_registry = DeviceRegistry(status_change_hook=_noop_status_change)
    capability_registry = CapabilityRegistry(device_registry=device_registry)
    dispatcher = ActionDispatcher()
    drivers = (
        SimulatedLightDriver(clock=clock),
        SimulatedTemperatureSensorDriver(clock=clock),
    )
    for driver in drivers:
        await driver.initialize()
        discovered = await driver.discover()
        device = discovered[0]
        await driver.connect(device.id)
        connected = (await driver.discover())[0]
        device_registry.register(connected)
        dispatcher.register_driver(driver)
        for capability in driver.capabilities:
            capability_registry.register(capability)
            await repository.save_capability(capability)
        await repository.save_device(device_registry.get(connected.id))  # type: ignore[arg-type]

    lifecycle = ActionLifecycle(
        transition_hook=lambda transition: repository.append_transition(
            transition.to_record()
        ),
        clock=clock,
    )

    async def event_builder(action):
        return await event_bus.create_event(
            event_type=f"hardware.action.{action.status.value}",
            device_id=action.device_id,
            action_id=action.action_id,
            payload={"status": action.status.value},
            source="action_executor",
            correlation_id=action.correlation_id,
            timestamp=clock() if clock is not None else None,
        )

    permission_gate = LocalPermissionGate(
        LocalPermissionPolicyConfig(low_auto_approve=low_auto_approve)
    )
    audit = AuditService(repository, clock=clock)
    executor = ActionExecutor(
        repository=repository,
        permission_gate=permission_gate,
        event_bus=event_bus,
        event_builder=event_builder,
        dispatcher=dispatcher,
        lifecycle=lifecycle,
        audit_writer=audit,
        clock=clock,
    )
    approval_service = ApprovalService(repository, clock=clock)
    return HardwareFacade(
        device_registry=device_registry,
        capability_registry=capability_registry,
        executor=executor,
        approval_service=approval_service,
        repository=repository,
        clock=clock,
        action_id_factory=action_id_factory,
    )


async def _noop_status_change(before, after) -> None:
    return None


__all__ = ("build_simulated_hardware_facade",)
