"""Deterministic Phase 0 simulated temperature sensor."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.enums import DeviceStatus, IdempotencyMode, RiskLevel
from ..domain.errors import HardwareError
from .base import SimulatedDriverBase
from .faults import FaultProfile


class SimulatedTemperatureSensorDriver(SimulatedDriverBase):
    def __init__(
        self,
        *,
        device_id: str = "simulated-temperature-01",
        temperature_celsius: float = 22.5,
        fault_profile: FaultProfile | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(temperature_celsius, bool) or not isinstance(
            temperature_celsius, (int, float)
        ):
            raise TypeError("temperature_celsius must be a number")
        self._temperature_celsius = float(temperature_celsius)
        self._measurement_clock = clock or (lambda: datetime.now(timezone.utc))
        driver_id = "simulated-temperature-driver"
        capability = _temperature_capability(device_id)
        super().__init__(
            device=Device(
                id=device_id,
                type="temperature_sensor",
                name="Simulated Temperature Sensor",
                status=DeviceStatus.OFFLINE,
                capability_ids=(),
                driver_id=driver_id,
                metadata={"simulated": True},
                last_seen_at=None,
                version=0,
            ),
            capabilities=(capability,),
            fault_profile=fault_profile,
            clock=clock,
        )

    def _execute_operation(
        self,
        operation: str,
        parameters: dict[str, object],
    ) -> dict[str, object] | HardwareError:
        if operation != "read_temperature":
            return HardwareError(
                "CAPABILITY_NOT_FOUND",
                "Unknown temperature operation",
                False,
                {},
            )
        return {
            "value": self._temperature_celsius,
            "unit": "celsius",
            "measured_at": self._measurement_clock().isoformat(),
        }


def _temperature_capability(device_id: str) -> Capability:
    return Capability(
        id=f"{device_id}.read_temperature",
        device_id=device_id,
        operation="read_temperature",
        description="Read deterministic simulated temperature",
        input_schema={
            "type": "object",
            "maxProperties": 0,
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "unit": {"const": "celsius"},
                "measured_at": {"type": "string", "format": "date-time"},
            },
            "required": ["value", "unit", "measured_at"],
            "additionalProperties": False,
        },
        schema_version="1.0.0",
        revision=0,
        risk_level=RiskLevel.READ_ONLY,
        idempotency=IdempotencyMode.IDEMPOTENT,
        timeout_ms=1_000,
        enabled=True,
    )


__all__ = ("SimulatedTemperatureSensorDriver",)
