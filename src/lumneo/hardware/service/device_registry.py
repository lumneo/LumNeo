"""Authoritative in-process Device registration and state semantics."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from ..domain.device import Device
from ..domain.enums import DeviceStatus


DeviceStatusChangeHook = Callable[[Device, Device], Awaitable[None]]

_LEGAL_STATUS_TRANSITIONS: dict[DeviceStatus, frozenset[DeviceStatus]] = {
    DeviceStatus.UNKNOWN: frozenset({DeviceStatus.OFFLINE}),
    DeviceStatus.OFFLINE: frozenset({DeviceStatus.CONNECTING}),
    DeviceStatus.CONNECTING: frozenset({DeviceStatus.ONLINE, DeviceStatus.ERROR}),
    DeviceStatus.ONLINE: frozenset({DeviceStatus.DEGRADED, DeviceStatus.OFFLINE}),
    DeviceStatus.DEGRADED: frozenset({DeviceStatus.ONLINE, DeviceStatus.ERROR}),
    DeviceStatus.ERROR: frozenset({DeviceStatus.CONNECTING}),
    DeviceStatus.DISABLED: frozenset({DeviceStatus.OFFLINE}),
}

_ACTION_ELIGIBLE_STATUSES = frozenset(
    {DeviceStatus.ONLINE, DeviceStatus.DEGRADED}
)


class DeviceRegistry:
    def __init__(self, *, status_change_hook: DeviceStatusChangeHook) -> None:
        self._devices: dict[str, Device] = {}
        self._status_change_hook = status_change_hook

    def register(self, device: Device) -> None:
        if device.id in self._devices:
            raise ValueError(f"device already registered: {device.id}")
        if device.capability_ids:
            raise ValueError(
                "Device capability_ids must be empty at registration; "
                "CapabilityRegistry derives the snapshot"
            )
        self._devices[device.id] = device

    def get(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def list(
        self,
        *,
        status: DeviceStatus | None = None,
        type: str | None = None,
    ) -> list[Device]:
        return [
            device
            for device in self._devices.values()
            if (status is None or device.status is status)
            and (type is None or device.type == type)
        ]

    def is_action_eligible(self, device_id: str) -> bool:
        device = self._require(device_id)
        return device.status in _ACTION_ELIGIBLE_STATUSES

    async def transition_status(
        self,
        device_id: str,
        new_status: DeviceStatus,
    ) -> Device:
        if not isinstance(new_status, DeviceStatus):
            raise TypeError("new_status must be a DeviceStatus")
        current = self._require(device_id)

        if current.status is new_status:
            if new_status is DeviceStatus.DISABLED:
                return current
            raise ValueError(f"illegal device status self-transition: {new_status.value}")

        is_disable = new_status is DeviceStatus.DISABLED and current.status is not DeviceStatus.DISABLED
        if not is_disable and new_status not in _LEGAL_STATUS_TRANSITIONS[current.status]:
            raise ValueError(
                f"illegal device status transition: {current.status.value} -> {new_status.value}"
            )

        updated = replace(current, status=new_status, version=current.version + 1)
        self._devices[device_id] = updated
        await self._status_change_hook(current, updated)
        return updated

    def _replace_capability_snapshot(
        self,
        device_id: str,
        capability_ids: tuple[str, ...],
    ) -> Device:
        """Registry-only relationship update used by CapabilityRegistry."""

        current = self._require(device_id)
        if current.capability_ids == capability_ids:
            return current
        updated = replace(
            current,
            capability_ids=capability_ids,
            version=current.version + 1,
        )
        self._devices[device_id] = updated
        return updated

    def _require(self, device_id: str) -> Device:
        device = self.get(device_id)
        if device is None:
            raise KeyError(f"device not registered: {device_id}")
        return device


__all__ = ("DeviceRegistry", "DeviceStatusChangeHook")
