from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import DeviceStatus, IdempotencyMode, RiskLevel
from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.service.capability_registry import CapabilityRegistry
from lumneo.hardware.service.device_registry import DeviceRegistry


class RecordingStatusHook:
    def __init__(self) -> None:
        self.events: list[HardwareDomainEvent] = []

    async def __call__(self, previous: Device, current: Device) -> None:
        self.events.append(
            HardwareDomainEvent(
                event_id=f"status-{current.id}-{current.version}",
                event_type="hardware.device.status_changed",
                device_id=current.id,
                action_id=None,
                timestamp=datetime.now(timezone.utc),
                payload={
                    "from_status": previous.status.value,
                    "to_status": current.status.value,
                    "device_version": current.version,
                },
                runtime_sequence=current.version,
                source_sequence=None,
                correlation_id=None,
                source="device-registry-test-hook",
            )
        )


def _device(
    device_id: str = "device-light-01",
    *,
    status: DeviceStatus = DeviceStatus.UNKNOWN,
    version: int = 0,
    capability_ids: tuple[str, ...] = (),
    device_type: str = "light",
) -> Device:
    return Device(
        id=device_id,
        type=device_type,
        name=device_id,
        status=status,
        capability_ids=capability_ids,
        driver_id="simulated",
        metadata={},
        last_seen_at=None,
        version=version,
    )


def _capability(
    capability_id: str = "device-light-01.turn_on",
    *,
    device_id: str = "device-light-01",
    enabled: bool = True,
) -> Capability:
    return Capability(
        id=capability_id,
        device_id=device_id,
        operation=capability_id.rsplit(".", 1)[-1],
        description="Test capability",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        schema_version="1.0.0",
        revision=0,
        risk_level=RiskLevel.LOW,
        idempotency=IdempotencyMode.IDEMPOTENT,
        timeout_ms=1_000,
        enabled=enabled,
    )


def _registries() -> tuple[DeviceRegistry, CapabilityRegistry, RecordingStatusHook]:
    hook = RecordingStatusHook()
    devices = DeviceRegistry(status_change_hook=hook)
    capabilities = CapabilityRegistry(device_registry=devices)
    return devices, capabilities, hook


def test_register_get_and_list_devices_with_filters() -> None:
    devices, _, _ = _registries()
    light = _device(status=DeviceStatus.ONLINE)
    sensor = _device(
        "device-sensor-01",
        status=DeviceStatus.OFFLINE,
        device_type="temperature_sensor",
    )
    devices.register(light)
    devices.register(sensor)

    assert devices.get(light.id) is light
    assert devices.get("missing") is None
    assert devices.list() == [light, sensor]
    assert devices.list(status=DeviceStatus.ONLINE) == [light]
    assert devices.list(type="temperature_sensor") == [sensor]


def test_duplicate_device_id_never_overwrites_original() -> None:
    devices, _, _ = _registries()
    original = _device()
    devices.register(original)

    with pytest.raises(ValueError, match="already registered"):
        devices.register(replace(original, name="Replacement"))

    assert devices.get(original.id) is original


def test_device_registration_rejects_business_supplied_capability_snapshot() -> None:
    devices, _, _ = _registries()

    with pytest.raises(ValueError, match="CapabilityRegistry derives"):
        devices.register(_device(capability_ids=("device-light-01.turn_on",)))


def test_capability_registration_derives_device_snapshot_and_version() -> None:
    devices, capabilities, _ = _registries()
    devices.register(_device(version=4))
    turn_on = _capability()
    brightness = _capability("device-light-01.set_brightness")

    capabilities.register(turn_on)
    capabilities.register(brightness)

    device = devices.get("device-light-01")
    assert device is not None
    assert device.capability_ids == (turn_on.id, brightness.id)
    assert device.version == 6
    assert capabilities.list(device_id=device.id) == [turn_on, brightness]


def test_duplicate_capability_never_overwrites_or_changes_snapshot() -> None:
    devices, capabilities, _ = _registries()
    devices.register(_device())
    original = _capability()
    capabilities.register(original)
    version_after_first = devices.get("device-light-01").version  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="already registered"):
        capabilities.register(replace(original, description="Replacement"))

    assert capabilities.get(original.id) is original
    assert devices.get("device-light-01").version == version_after_first  # type: ignore[union-attr]


def test_capability_requires_registered_device() -> None:
    _, capabilities, _ = _registries()

    with pytest.raises(KeyError, match="device not registered"):
        capabilities.register(_capability())


def test_capability_get_and_global_list() -> None:
    devices, capabilities, _ = _registries()
    devices.register(_device())
    devices.register(_device("device-light-02"))
    first = _capability()
    second = _capability("device-light-02.turn_off", device_id="device-light-02")
    capabilities.register(first)
    capabilities.register(second)

    assert capabilities.get(first.id) is first
    assert capabilities.get("missing") is None
    assert capabilities.list() == [first, second]
    assert capabilities.list(device_id="device-light-02") == [second]
    assert capabilities.list(device_id="missing") == []


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (DeviceStatus.UNKNOWN, DeviceStatus.OFFLINE),
        (DeviceStatus.OFFLINE, DeviceStatus.CONNECTING),
        (DeviceStatus.CONNECTING, DeviceStatus.ONLINE),
        (DeviceStatus.CONNECTING, DeviceStatus.ERROR),
        (DeviceStatus.ONLINE, DeviceStatus.DEGRADED),
        (DeviceStatus.ONLINE, DeviceStatus.OFFLINE),
        (DeviceStatus.DEGRADED, DeviceStatus.ONLINE),
        (DeviceStatus.DEGRADED, DeviceStatus.ERROR),
        (DeviceStatus.ERROR, DeviceStatus.CONNECTING),
        (DeviceStatus.DISABLED, DeviceStatus.OFFLINE),
    ],
)
def test_every_explicit_legal_status_transition_increments_version_and_emits_hook(
    from_status: DeviceStatus,
    to_status: DeviceStatus,
) -> None:
    devices, _, hook = _registries()
    devices.register(_device(status=from_status, version=7))

    updated = asyncio.run(devices.transition_status("device-light-01", to_status))

    assert updated.status is to_status
    assert updated.version == 8
    assert len(hook.events) == 1
    event = hook.events[0]
    assert event.event_type == "hardware.device.status_changed"
    assert event.payload == {
        "from_status": from_status.value,
        "to_status": to_status.value,
        "device_version": 8,
    }


@pytest.mark.parametrize(
    "from_status",
    [status for status in DeviceStatus if status is not DeviceStatus.DISABLED],
)
def test_every_non_disabled_state_can_transition_to_disabled(
    from_status: DeviceStatus,
) -> None:
    devices, _, hook = _registries()
    devices.register(_device(status=from_status, version=2))

    updated = asyncio.run(
        devices.transition_status("device-light-01", DeviceStatus.DISABLED)
    )

    assert updated.status is DeviceStatus.DISABLED
    assert updated.version == 3
    assert len(hook.events) == 1
    assert devices.is_action_eligible(updated.id) is False


def test_repeated_disable_is_idempotent_without_version_or_event() -> None:
    devices, _, hook = _registries()
    disabled = _device(status=DeviceStatus.DISABLED, version=12)
    devices.register(disabled)

    result = asyncio.run(
        devices.transition_status(disabled.id, DeviceStatus.DISABLED)
    )

    assert result is disabled
    assert result.version == 12
    assert hook.events == []


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (DeviceStatus.UNKNOWN, DeviceStatus.ONLINE),
        (DeviceStatus.OFFLINE, DeviceStatus.ONLINE),
        (DeviceStatus.ONLINE, DeviceStatus.CONNECTING),
        (DeviceStatus.ERROR, DeviceStatus.ONLINE),
        (DeviceStatus.DISABLED, DeviceStatus.ONLINE),
    ],
)
def test_illegal_status_transition_does_not_change_device_or_emit_event(
    from_status: DeviceStatus,
    to_status: DeviceStatus,
) -> None:
    devices, _, hook = _registries()
    original = _device(status=from_status, version=3)
    devices.register(original)

    with pytest.raises(ValueError, match="illegal device status transition"):
        asyncio.run(devices.transition_status(original.id, to_status))

    assert devices.get(original.id) is original
    assert hook.events == []


def test_non_disabled_same_state_transition_is_illegal() -> None:
    devices, _, hook = _registries()
    original = _device(status=DeviceStatus.ONLINE)
    devices.register(original)

    with pytest.raises(ValueError, match="self-transition"):
        asyncio.run(devices.transition_status(original.id, DeviceStatus.ONLINE))

    assert hook.events == []


@pytest.mark.parametrize(
    "status,eligible",
    [
        (DeviceStatus.ONLINE, True),
        (DeviceStatus.DEGRADED, True),
        (DeviceStatus.UNKNOWN, False),
        (DeviceStatus.OFFLINE, False),
        (DeviceStatus.CONNECTING, False),
        (DeviceStatus.ERROR, False),
        (DeviceStatus.DISABLED, False),
    ],
)
def test_device_action_eligibility_follows_state(status: DeviceStatus, eligible: bool) -> None:
    devices, _, _ = _registries()
    device = _device(status=status)
    devices.register(device)

    assert devices.is_action_eligible(device.id) is eligible


def test_disabled_capability_or_device_is_action_ineligible() -> None:
    devices, capabilities, _ = _registries()
    devices.register(_device(status=DeviceStatus.ONLINE))
    enabled = _capability()
    disabled = _capability("device-light-01.turn_off", enabled=False)
    capabilities.register(enabled)
    capabilities.register(disabled)

    assert capabilities.is_action_eligible(enabled.id) is True
    assert capabilities.is_action_eligible(disabled.id) is False

    asyncio.run(
        devices.transition_status("device-light-01", DeviceStatus.DISABLED)
    )
    assert capabilities.is_action_eligible(enabled.id) is False


def test_missing_registry_items_raise_on_behavior_queries() -> None:
    devices, capabilities, _ = _registries()

    with pytest.raises(KeyError, match="device not registered"):
        devices.is_action_eligible("missing")
    with pytest.raises(KeyError, match="capability not registered"):
        capabilities.is_action_eligible("missing")
