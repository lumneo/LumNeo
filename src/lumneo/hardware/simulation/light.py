"""Deterministic Phase 0 simulated light."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.enums import DeviceStatus, IdempotencyMode, RiskLevel
from ..domain.errors import HardwareError
from .base import SimulatedDriverBase
from .faults import FaultProfile


class SimulatedLightDriver(SimulatedDriverBase):
    def __init__(
        self,
        *,
        device_id: str = "simulated-light-01",
        fault_profile: FaultProfile | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        driver_id = "simulated-light-driver"
        capabilities = _light_capabilities(device_id)
        super().__init__(
            device=Device(
                id=device_id,
                type="light",
                name="Simulated Light",
                status=DeviceStatus.OFFLINE,
                capability_ids=(),
                driver_id=driver_id,
                metadata={"simulated": True},
                last_seen_at=None,
                version=0,
            ),
            capabilities=capabilities,
            fault_profile=fault_profile,
            clock=clock,
        )
        self._is_on = False
        self._brightness = 0

    def _execute_operation(
        self,
        operation: str,
        parameters: dict[str, object],
    ) -> dict[str, object] | HardwareError:
        if operation == "get_state":
            return self._state()
        if operation == "turn_on":
            self._is_on = True
            return self._state()
        if operation == "turn_off":
            self._is_on = False
            return self._state()
        if operation == "set_brightness":
            brightness = parameters.get("brightness")
            if type(brightness) is not int or not 0 <= brightness <= 100:
                return HardwareError(
                    "INVALID_PARAMETERS",
                    "brightness must be an integer from 0 to 100",
                    False,
                    {},
                )
            self._brightness = brightness
            return self._state()
        return HardwareError("CAPABILITY_NOT_FOUND", "Unknown light operation", False, {})

    def _state(self) -> dict[str, object]:
        return {"on": self._is_on, "brightness": self._brightness}


def _light_capabilities(device_id: str) -> tuple[Capability, ...]:
    state_schema: dict[str, object] = {
        "type": "object",
        "properties": {"on": {"type": "boolean"}, "brightness": {"type": "integer"}},
        "required": ["on", "brightness"],
        "additionalProperties": False,
    }
    empty_input: dict[str, object] = {
        "type": "object",
        "maxProperties": 0,
        "additionalProperties": False,
    }

    def capability(
        operation: str,
        risk: RiskLevel,
        input_schema: dict[str, object],
    ) -> Capability:
        return Capability(
            id=f"{device_id}.{operation}",
            device_id=device_id,
            operation=operation,
            description=f"Simulated light {operation}",
            input_schema=input_schema,
            output_schema=state_schema,
            schema_version="1.0.0",
            revision=0,
            risk_level=risk,
            idempotency=IdempotencyMode.IDEMPOTENT,
            timeout_ms=1_000,
            enabled=True,
        )

    return (
        capability("get_state", RiskLevel.READ_ONLY, empty_input),
        capability("turn_on", RiskLevel.LOW, empty_input),
        capability("turn_off", RiskLevel.LOW, empty_input),
        capability(
            "set_brightness",
            RiskLevel.LOW,
            {
                "type": "object",
                "properties": {
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["brightness"],
                "additionalProperties": False,
            },
        ),
    )


__all__ = ("SimulatedLightDriver",)
