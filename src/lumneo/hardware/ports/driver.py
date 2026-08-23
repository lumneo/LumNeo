"""Abstract physical/simulated DeviceDriver Port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..domain.action import ActionResult, HardwareAction
from ..domain.device import Device
from ..domain.enums import DeviceStatus


@dataclass(frozen=True, slots=True)
class DriverHealth:
    available: bool
    message: str | None
    checked_at: datetime

    def __post_init__(self) -> None:
        if type(self.available) is not bool:
            raise TypeError("available must be a bool")
        if self.message is not None and not isinstance(self.message, str):
            raise TypeError("message must be a string or None")
        if not isinstance(self.checked_at, datetime):
            raise TypeError("checked_at must be a datetime")


@runtime_checkable
class DeviceDriver(Protocol):
    @property
    def driver_id(self) -> str: ...

    async def initialize(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def health_check(self) -> DriverHealth: ...

    async def discover(self) -> list[Device]: ...

    async def connect(self, device_id: str) -> None: ...

    async def disconnect(self, device_id: str) -> None: ...

    async def get_status(self, device_id: str) -> DeviceStatus: ...

    async def execute(self, action: HardwareAction) -> ActionResult: ...

    async def cancel(self, action_id: str) -> bool: ...


__all__ = ("DeviceDriver", "DriverHealth")
