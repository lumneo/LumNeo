from __future__ import annotations

import asyncio
import ast
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from lumneo.hardware.domain.action import ActionResult, HardwareAction
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus, RiskLevel
from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.ports import (
    DeviceDriver,
    DriverHealth,
    EventBus,
    HardwareRepository,
    PermissionDecision,
    PermissionEvaluation,
    PermissionGate,
)


PORTS_ROOT = Path(__file__).resolve().parents[3] / "src" / "lumneo" / "hardware" / "ports"


class FakeDriver:
    driver_id = "fake-driver"

    async def initialize(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def health_check(self) -> DriverHealth:
        return DriverHealth(True, None, datetime.now(timezone.utc))

    async def discover(self) -> list[Device]:
        return []

    async def connect(self, device_id: str) -> None: ...

    async def disconnect(self, device_id: str) -> None: ...

    async def get_status(self, device_id: str) -> DeviceStatus:
        return DeviceStatus.OFFLINE

    async def execute(self, action: HardwareAction) -> ActionResult:
        return ActionResult(action.action_id, ActionStatus.SUCCEEDED, {}, None, None, None, True)

    async def cancel(self, action_id: str) -> bool:
        return True


class FakePermissionGate:
    async def evaluate(
        self,
        action: HardwareAction,
        capability: Capability,
    ) -> PermissionEvaluation:
        return PermissionEvaluation(
            PermissionDecision.APPROVED,
            capability.risk_level,
            "fake_policy",
            None,
        )


class FakeEventBus:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[HardwareDomainEvent], Awaitable[None]]] = {}

    async def publish(self, event: HardwareDomainEvent) -> None:
        for handler in self.handlers.values():
            await handler(event)

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[HardwareDomainEvent], Awaitable[None]],
    ) -> str:
        subscription_id = f"subscription-{len(self.handlers) + 1}"
        self.handlers[subscription_id] = handler
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        self.handlers.pop(subscription_id, None)


class FakeRepository:
    async def save_device(self, device: Device) -> None: ...
    async def get_device(self, device_id: str) -> Device | None: return None
    async def list_devices(self) -> list[Device]: return []
    async def save_capability(self, capability: Capability) -> None: ...
    async def get_capability(self, capability_id: str) -> Capability | None: return None
    async def list_capabilities(self, device_id: str) -> list[Capability]: return []
    async def save_action(self, action: HardwareAction) -> None: ...
    async def get_action(self, action_id: str) -> HardwareAction | None: return None
    async def save_result(self, result: ActionResult) -> None: ...
    async def get_result(self, action_id: str) -> ActionResult | None: return None
    async def save_approval(self, approval: Mapping[str, object]) -> None: ...
    async def list_approvals(self, action_id: str) -> list[Mapping[str, object]]: return []
    async def append_transition(self, transition: Mapping[str, object]) -> None: ...
    async def append_event(self, event: HardwareDomainEvent) -> None: ...
    async def append_reconciliation(self, reconciliation: Mapping[str, object]) -> None: ...
    async def append_audit(self, audit: Mapping[str, object]) -> None: ...
    async def list_audits(self, action_id: str) -> list[Mapping[str, object]]: return []
    async def reserve_idempotency_key(self, **scope: str) -> bool: return True
    async def get_action_by_idempotency_key(self, **scope: str) -> HardwareAction | None: return None
    async def get_action_record(self, action_id: str) -> Mapping[str, object] | None: return None


def test_fake_implementations_satisfy_runtime_checkable_ports() -> None:
    assert isinstance(FakeDriver(), DeviceDriver)
    assert isinstance(FakePermissionGate(), PermissionGate)
    assert isinstance(FakeEventBus(), EventBus)
    assert isinstance(FakeRepository(), HardwareRepository)


def test_driver_lifecycle_and_health_contract() -> None:
    driver = FakeDriver()

    asyncio.run(driver.initialize())
    health = asyncio.run(driver.health_check())
    discovered = asyncio.run(driver.discover())
    status = asyncio.run(driver.get_status("device-1"))
    cancelled = asyncio.run(driver.cancel("action-1"))
    asyncio.run(driver.shutdown())

    assert health.available is True
    assert discovered == []
    assert status is DeviceStatus.OFFLINE
    assert cancelled is True


def test_permission_decision_and_evaluation_match_accepted_adr() -> None:
    assert {member.name: member.value for member in PermissionDecision} == {
        "APPROVED": "approved",
        "APPROVAL_REQUIRED": "approval_required",
        "REJECTED": "rejected",
    }
    evaluation = PermissionEvaluation(
        PermissionDecision.APPROVAL_REQUIRED,
        RiskLevel.HIGH,
        "explicit_confirmation",
        "A human approver is required",
    )
    assert evaluation.effective_risk is RiskLevel.HIGH


def test_event_bus_fake_exercises_publish_subscribe_unsubscribe() -> None:
    bus = FakeEventBus()
    received: list[str] = []

    async def handler(event: HardwareDomainEvent) -> None:
        received.append(event.event_id)

    event = HardwareDomainEvent(
        "event-1",
        "hardware.device.connected",
        "device-1",
        None,
        datetime.now(timezone.utc),
        {},
        0,
        None,
        None,
        "test",
    )
    subscription_id = asyncio.run(bus.subscribe(event.event_type, handler))
    asyncio.run(bus.publish(event))
    asyncio.run(bus.unsubscribe(subscription_id))
    asyncio.run(bus.publish(event))

    assert received == ["event-1"]


def test_repository_port_contains_contract_and_adr_persistence_surface() -> None:
    required_methods = {
        "save_device",
        "get_device",
        "list_devices",
        "save_capability",
        "get_capability",
        "list_capabilities",
        "save_action",
        "get_action",
        "save_result",
        "get_result",
        "save_approval",
        "list_approvals",
        "append_transition",
        "append_event",
        "append_reconciliation",
        "append_audit",
        "list_audits",
        "reserve_idempotency_key",
        "get_action_by_idempotency_key",
        "get_action_record",
    }

    assert required_methods <= set(HardwareRepository.__dict__)


def test_ports_import_only_domain_and_standard_library() -> None:
    forbidden_roots = {
        "fastapi",
        "sqlalchemy",
        "sqlite3",
        "serial",
        "usb",
        "mqtt",
        "redis",
        "lumneo.infrastructure",
        "lumneo.runtime",
    }
    imported: set[str] = set()
    for source_path in PORTS_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module)

    violations = {
        imported_module
        for imported_module in imported
        if any(
            imported_module == root or imported_module.startswith(f"{root}.")
            for root in forbidden_roots
        )
    }
    assert violations == set()
