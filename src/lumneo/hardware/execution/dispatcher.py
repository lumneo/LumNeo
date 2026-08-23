"""Protocol-neutral routing from Hardware contracts to a DeviceDriver Port."""

from __future__ import annotations

from ..domain.action import HardwareAction
from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.errors import HardwareError
from ..ports.driver import DeviceDriver


class DispatchError(Exception):
    def __init__(self, error: HardwareError) -> None:
        self.error = error
        super().__init__(error.message)


class ActionDispatcher:
    def __init__(self) -> None:
        self._drivers: dict[str, DeviceDriver] = {}

    def register_driver(self, driver: DeviceDriver) -> None:
        driver_id = driver.driver_id
        if not isinstance(driver_id, str) or not driver_id.strip():
            raise ValueError("driver_id must be a non-empty string")
        if driver_id in self._drivers:
            raise ValueError(f"driver already registered: {driver_id}")
        self._drivers[driver_id] = driver

    def get_driver(self, driver_id: str) -> DeviceDriver | None:
        return self._drivers.get(driver_id)

    async def resolve(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
    ) -> DeviceDriver:
        if action.device_id != device.id:
            raise self._conflict(
                "Action device_id does not match resolved Device",
                action_device_id=action.device_id,
                device_id=device.id,
            )
        if action.capability_id != capability.id:
            raise self._conflict(
                "Action capability_id does not match resolved Capability",
                action_capability_id=action.capability_id,
                capability_id=capability.id,
            )
        if capability.device_id != device.id:
            raise self._conflict(
                "Capability does not belong to resolved Device",
                capability_device_id=capability.device_id,
                device_id=device.id,
            )

        driver = self._drivers.get(device.driver_id)
        if driver is None:
            raise DispatchError(
                HardwareError(
                    "DRIVER_UNAVAILABLE",
                    f"Driver is not registered: {device.driver_id}",
                    True,
                    {"driver_id": device.driver_id},
                )
            )
        health = await driver.health_check()
        if not health.available:
            raise DispatchError(
                HardwareError(
                    "DRIVER_UNAVAILABLE",
                    health.message or f"Driver is unavailable: {device.driver_id}",
                    True,
                    {"driver_id": device.driver_id},
                )
            )
        return driver

    @staticmethod
    def _conflict(message: str, **details: object) -> DispatchError:
        return DispatchError(HardwareError("CONFLICT", message, False, details))


__all__ = ("ActionDispatcher", "DispatchError")
