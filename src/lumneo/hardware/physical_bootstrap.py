"""Composition root for the first physical ESP8266 device."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from lumneo.infrastructure.hardware.drivers.serial.esp8266_nodemcu import (
    Esp8266NodeMcuSerialDriver,
    SerialDriverConfig,
)
from lumneo.infrastructure.hardware.drivers.serial.transport import (
    PySerialJsonTransport,
    SerialTransportFactory,
)
from lumneo.infrastructure.hardware.event_bus.in_process import InProcessEventBus
from lumneo.infrastructure.hardware.permission.local_policy import (
    LocalPermissionGate,
    LocalPermissionPolicyConfig,
)
from lumneo.infrastructure.hardware.persistence.in_memory_repository import (
    InMemoryHardwareRepository,
)

from .execution.dispatcher import ActionDispatcher
from .execution.executor import ActionExecutor
from .execution.lifecycle import ActionLifecycle
from .facade.hardware_facade import HardwareFacade
from .service.approval import ApprovalService
from .service.audit import AuditService
from .service.capability_registry import CapabilityRegistry
from .service.device_registry import DeviceRegistry


async def build_esp8266_nodemcu_facade(
    endpoint: str,
    *,
    baud_rate: int = 115_200,
    request_timeout_ms: int = 2_000,
    low_auto_approve: bool = False,
    transport_factory: SerialTransportFactory = PySerialJsonTransport,
    clock: Callable[[], datetime] | None = None,
    action_id_factory: Callable[[], str] | None = None,
) -> HardwareFacade:
    """Discover and connect one board, exposing it only through HardwareFacade."""
    facade, _ = await _compose_esp8266_nodemcu(
        endpoint,
        baud_rate=baud_rate,
        request_timeout_ms=request_timeout_ms,
        low_auto_approve=low_auto_approve,
        transport_factory=transport_factory,
        clock=clock,
        action_id_factory=action_id_factory,
    )
    return facade


@asynccontextmanager
async def esp8266_nodemcu_session(
    endpoint: str,
    *,
    baud_rate: int = 115_200,
    request_timeout_ms: int = 2_000,
    low_auto_approve: bool = False,
    transport_factory: SerialTransportFactory = PySerialJsonTransport,
    clock: Callable[[], datetime] | None = None,
    action_id_factory: Callable[[], str] | None = None,
) -> AsyncIterator[HardwareFacade]:
    """Yield only the Facade and reliably release its serial endpoint on exit."""
    facade, driver = await _compose_esp8266_nodemcu(
        endpoint,
        baud_rate=baud_rate,
        request_timeout_ms=request_timeout_ms,
        low_auto_approve=low_auto_approve,
        transport_factory=transport_factory,
        clock=clock,
        action_id_factory=action_id_factory,
    )
    try:
        yield facade
    finally:
        await driver.shutdown()


async def _compose_esp8266_nodemcu(
    endpoint: str,
    *,
    baud_rate: int,
    request_timeout_ms: int,
    low_auto_approve: bool,
    transport_factory: SerialTransportFactory,
    clock: Callable[[], datetime] | None,
    action_id_factory: Callable[[], str] | None,
) -> tuple[HardwareFacade, Esp8266NodeMcuSerialDriver]:
    repository = InMemoryHardwareRepository()
    event_bus = InProcessEventBus()
    device_registry = DeviceRegistry(status_change_hook=_noop_status_change)
    capability_registry = CapabilityRegistry(device_registry=device_registry)
    dispatcher = ActionDispatcher()
    driver = Esp8266NodeMcuSerialDriver(
        SerialDriverConfig(endpoint, baud_rate, request_timeout_ms),
        transport_factory=transport_factory,
        clock=clock,
    )
    await driver.initialize()
    discovered = await driver.discover()
    if not discovered:
        await driver.shutdown()
        raise ConnectionError(f"No ESP8266 protocol device discovered at {endpoint}")
    device = discovered[0]
    await driver.connect(device.id)
    connected = driver.get_device(device.id)
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

    executor = ActionExecutor(
        repository=repository,
        permission_gate=LocalPermissionGate(
            LocalPermissionPolicyConfig(low_auto_approve=low_auto_approve)
        ),
        event_bus=event_bus,
        event_builder=event_builder,
        dispatcher=dispatcher,
        lifecycle=lifecycle,
        audit_writer=AuditService(repository, clock=clock),
        clock=clock,
    )
    facade = HardwareFacade(
        device_registry=device_registry,
        capability_registry=capability_registry,
        executor=executor,
        approval_service=ApprovalService(repository, clock=clock),
        repository=repository,
        clock=clock,
        action_id_factory=action_id_factory,
    )
    return facade, driver


async def _noop_status_change(before, after) -> None:
    return None


__all__ = ("build_esp8266_nodemcu_facade", "esp8266_nodemcu_session")
