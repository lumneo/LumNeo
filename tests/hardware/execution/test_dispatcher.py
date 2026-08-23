from __future__ import annotations

import asyncio
import ast
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumneo.hardware.domain.action import PHYSICAL_ACTION_KIND, HardwareAction
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus
from lumneo.hardware.execution.dispatcher import ActionDispatcher, DispatchError
from lumneo.hardware.simulation.light import SimulatedLightDriver


NOW = datetime(2026, 8, 23, 13, 0, tzinfo=timezone.utc)
IMPLEMENTATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "lumneo"
    / "hardware"
    / "execution"
    / "dispatcher.py"
)


def _contracts() -> tuple[SimulatedLightDriver, Device, Capability, HardwareAction]:
    driver = SimulatedLightDriver()
    device = Device(
        id="simulated-light-01",
        type="light",
        name="Light",
        status=DeviceStatus.ONLINE,
        capability_ids=(),
        driver_id=driver.driver_id,
        metadata={},
        last_seen_at=NOW,
        version=0,
    )
    capability = next(item for item in driver.capabilities if item.operation == "turn_on")
    action = HardwareAction(
        action_id="action-1",
        action_kind=PHYSICAL_ACTION_KIND,
        device_id=device.id,
        capability_id=capability.id,
        parameters={},
        requester="test",
        status=ActionStatus.APPROVED,
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
    return driver, device, capability, action


def test_resolve_selects_registered_healthy_driver_without_executing() -> None:
    async def scenario():
        driver, device, capability, action = _contracts()
        dispatcher = ActionDispatcher()
        dispatcher.register_driver(driver)
        await driver.initialize()

        resolved = await dispatcher.resolve(action, device, capability)
        return driver, resolved

    driver, resolved = asyncio.run(scenario())
    assert resolved is driver


def test_unknown_driver_returns_explicit_driver_unavailable_error() -> None:
    async def scenario() -> None:
        _, device, capability, action = _contracts()
        dispatcher = ActionDispatcher()
        with pytest.raises(DispatchError) as captured:
            await dispatcher.resolve(action, device, capability)
        assert captured.value.error.code == "DRIVER_UNAVAILABLE"
        assert captured.value.error.retryable is True
        assert captured.value.error.details == {"driver_id": device.driver_id}

    asyncio.run(scenario())


def test_registered_but_uninitialized_driver_is_unavailable() -> None:
    async def scenario() -> None:
        driver, device, capability, action = _contracts()
        dispatcher = ActionDispatcher()
        dispatcher.register_driver(driver)
        with pytest.raises(DispatchError) as captured:
            await dispatcher.resolve(action, device, capability)
        assert captured.value.error.code == "DRIVER_UNAVAILABLE"
        assert captured.value.error.message == "driver is not initialized"

    asyncio.run(scenario())


def test_duplicate_driver_registration_never_overwrites() -> None:
    driver, _, _, _ = _contracts()
    dispatcher = ActionDispatcher()
    dispatcher.register_driver(driver)

    with pytest.raises(ValueError, match="already registered"):
        dispatcher.register_driver(SimulatedLightDriver())

    assert dispatcher.get_driver(driver.driver_id) is driver


@pytest.mark.parametrize(
    "mismatch",
    ["action_device", "action_capability", "capability_device"],
)
def test_contract_relationship_mismatch_returns_conflict(mismatch: str) -> None:
    async def scenario() -> None:
        driver, device, capability, action = _contracts()
        dispatcher = ActionDispatcher()
        dispatcher.register_driver(driver)
        await driver.initialize()
        if mismatch == "action_device":
            changed_action = replace(action, device_id="other-device")
            changed_capability = capability
        elif mismatch == "action_capability":
            changed_action = replace(action, capability_id="other-capability")
            changed_capability = capability
        else:
            changed_action = action
            changed_capability = replace(capability, device_id="other-device")
        with pytest.raises(DispatchError) as captured:
            await dispatcher.resolve(changed_action, device, changed_capability)
        assert captured.value.error.code == "CONFLICT"
        assert captured.value.error.retryable is False

    asyncio.run(scenario())


def test_dispatcher_imports_no_runtime_protocol_or_database_implementation() -> None:
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
        for forbidden in (
            "lumneo.runtime",
            "serial",
            "usb",
            "sqlalchemy",
            "sqlite3",
            "permission",
        )
    )
