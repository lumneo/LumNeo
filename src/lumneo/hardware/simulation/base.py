"""Shared deterministic DeviceDriver behavior for Contract test devices."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from ..domain.action import ActionResult, HardwareAction
from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.enums import ActionStatus, DeviceStatus
from ..domain.errors import HardwareError
from ..ports.driver import DriverHealth
from .faults import FaultProfile


Clock = Callable[[], datetime]


class SimulatedDriverBase(ABC):
    def __init__(
        self,
        *,
        device: Device,
        capabilities: tuple[Capability, ...],
        fault_profile: FaultProfile | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._device = device
        self._capabilities = capabilities
        self.fault_profile = fault_profile or FaultProfile()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._available = False

    @property
    def driver_id(self) -> str:
        return self._device.driver_id

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return deepcopy(self._capabilities)

    async def initialize(self) -> None:
        self._available = True

    async def shutdown(self) -> None:
        self._available = False
        self._device = replace(self._device, status=DeviceStatus.OFFLINE)

    async def health_check(self) -> DriverHealth:
        return DriverHealth(
            available=self._available,
            message=None if self._available else "driver is not initialized",
            checked_at=self._clock(),
        )

    async def discover(self) -> list[Device]:
        device = self._effective_device()
        return [deepcopy(device)]

    async def connect(self, device_id: str) -> None:
        self._require_device(device_id)
        if not self._available:
            raise RuntimeError("driver is not initialized")
        status = DeviceStatus.OFFLINE if self.fault_profile.offline else DeviceStatus.ONLINE
        self._device = replace(self._device, status=status)

    async def disconnect(self, device_id: str) -> None:
        self._require_device(device_id)
        self._device = replace(self._device, status=DeviceStatus.OFFLINE)

    async def get_status(self, device_id: str) -> DeviceStatus:
        self._require_device(device_id)
        return self._effective_device().status

    async def execute(self, action: HardwareAction) -> ActionResult:
        started_at = self._clock()
        if action.device_id != self._device.id:
            return self._failure(
                action,
                started_at,
                "DEVICE_NOT_FOUND",
                "Device is not owned by this driver",
                False,
            )
        capability = next(
            (item for item in self._capabilities if item.id == action.capability_id),
            None,
        )
        if capability is None:
            return self._failure(
                action,
                started_at,
                "CAPABILITY_NOT_FOUND",
                "Capability is not owned by this driver",
                False,
            )
        if not self._available:
            return self._failure(
                action,
                started_at,
                "DRIVER_UNAVAILABLE",
                "Driver is not initialized",
                True,
            )
        if self.fault_profile.offline or self._device.status is DeviceStatus.OFFLINE:
            return self._failure(
                action,
                started_at,
                "DEVICE_OFFLINE",
                "Simulated device is offline",
                True,
            )
        if self.fault_profile.delay_ms:
            await asyncio.sleep(self.fault_profile.delay_ms / 1_000)
        if self.fault_profile.timeout:
            raise TimeoutError("deterministic simulated timeout")
        if self.fault_profile.driver_error is not None:
            return self._failure(
                action,
                started_at,
                "DRIVER_ERROR",
                self.fault_profile.driver_error,
                False,
            )
        if self.fault_profile.consume_fail_next():
            return self._failure(
                action,
                started_at,
                "DRIVER_ERROR",
                "deterministic fail_next_n failure",
                True,
            )

        output = self._execute_operation(capability.operation, action.parameters)
        if isinstance(output, HardwareError):
            return ActionResult(
                action.action_id,
                ActionStatus.FAILED,
                None,
                output,
                started_at,
                self._clock(),
                False,
            )
        if self.fault_profile.invalid_output:
            output = {"invalid_output": True}
        return ActionResult(
            action.action_id,
            ActionStatus.SUCCEEDED,
            output,
            None,
            started_at,
            self._clock(),
            True,
        )

    async def cancel(self, action_id: str) -> bool:
        return False

    def _effective_device(self) -> Device:
        if self.fault_profile.offline:
            return replace(self._device, status=DeviceStatus.OFFLINE)
        return self._device

    def _require_device(self, device_id: str) -> None:
        if device_id != self._device.id:
            raise KeyError(f"device not found: {device_id}")

    def _failure(
        self,
        action: HardwareAction,
        started_at: datetime,
        code: str,
        message: str,
        retryable: bool,
    ) -> ActionResult:
        return ActionResult(
            action.action_id,
            ActionStatus.FAILED,
            None,
            HardwareError(code, message, retryable, {"driver_id": self.driver_id}),
            started_at,
            self._clock(),
            False,
        )

    @abstractmethod
    def _execute_operation(
        self,
        operation: str,
        parameters: dict[str, object],
    ) -> dict[str, object] | HardwareError: ...


__all__ = ("Clock", "SimulatedDriverBase")
