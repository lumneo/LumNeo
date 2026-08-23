"""Low-risk NodeMCU v3 board-LED Driver over a JSON-lines serial transport."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from lumneo.hardware.domain.action import ActionResult, HardwareAction
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus, IdempotencyMode, RiskLevel
from lumneo.hardware.domain.errors import HardwareError
from lumneo.hardware.ports.driver import DriverHealth

from .transport import (
    PySerialJsonTransport,
    SerialAdapterUnavailable,
    SerialEndpointUnavailable,
    SerialJsonTransport,
    SerialProtocolError,
    SerialTransportFactory,
)


@dataclass(frozen=True, slots=True)
class SerialDriverConfig:
    endpoint: str
    baud_rate: int = 115_200
    request_timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, str) or not self.endpoint.strip():
            raise ValueError("endpoint must be a non-empty string")
        if type(self.baud_rate) is not int or self.baud_rate <= 0:
            raise ValueError("baud_rate must be a positive integer")
        if type(self.request_timeout_ms) is not int or not 100 <= self.request_timeout_ms <= 60_000:
            raise ValueError("request_timeout_ms must be between 100 and 60000")


class Esp8266NodeMcuSerialDriver:
    driver_id = "esp8266-nodemcu-serial-driver"

    def __init__(
        self,
        config: SerialDriverConfig,
        *,
        transport_factory: SerialTransportFactory = PySerialJsonTransport,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._transport_factory = transport_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._transport: SerialJsonTransport | None = None
        self._adapter_error: str | None = "Driver is not initialized"
        self._device: Device | None = None
        self._chip_id: str | None = None
        self._firmware_version: str | None = None

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        if self._device is None:
            return ()
        return deepcopy(_capabilities(self._device.id, self._config.request_timeout_ms))

    async def initialize(self) -> None:
        try:
            self._transport = self._transport_factory(
                self._config.endpoint,
                self._config.baud_rate,
                self._config.request_timeout_ms,
            )
        except SerialAdapterUnavailable as error:
            self._transport = None
            self._adapter_error = str(error)
        else:
            self._adapter_error = None

    async def shutdown(self) -> None:
        if self._transport is not None:
            await self._transport.close()
        self._transport = None
        self._adapter_error = "Driver is shut down"
        self._set_status(DeviceStatus.OFFLINE)

    async def health_check(self) -> DriverHealth:
        return DriverHealth(
            self._adapter_error is None,
            self._adapter_error,
            self._clock(),
        )

    async def discover(self) -> list[Device]:
        transport = self._require_adapter()
        try:
            await transport.open()
            identity = await transport.request({"command": "hello", "protocol": 1})
            self._accept_identity(identity)
        except SerialEndpointUnavailable:
            self._set_status(DeviceStatus.OFFLINE)
            return [deepcopy(self._device)] if self._device is not None else []
        finally:
            await transport.close()
        assert self._device is not None
        self._set_status(DeviceStatus.OFFLINE)
        return [deepcopy(self._device)]

    async def connect(self, device_id: str) -> None:
        self._require_device(device_id)
        transport = self._require_adapter()
        try:
            await transport.open()
            identity = await transport.request({"command": "hello", "protocol": 1})
            self._accept_identity(identity)
        except (SerialEndpointUnavailable, SerialProtocolError, TimeoutError):
            self._set_status(DeviceStatus.OFFLINE)
            await transport.close()
            raise
        self._set_status(DeviceStatus.ONLINE)

    async def disconnect(self, device_id: str) -> None:
        self._require_device(device_id)
        if self._transport is not None:
            await self._transport.close()
        self._set_status(DeviceStatus.OFFLINE)

    async def rebind_endpoint(self, endpoint: str) -> None:
        """Change transport endpoint without changing the discovered Device identity."""
        if self._transport is not None:
            await self._transport.close()
        self._config = replace(self._config, endpoint=endpoint)
        self._transport = None
        self._set_status(DeviceStatus.OFFLINE)
        await self.initialize()

    async def get_status(self, device_id: str) -> DeviceStatus:
        return self._require_device(device_id).status

    def get_device(self, device_id: str) -> Device:
        """Return a detached snapshot without probing or resetting the endpoint."""
        return deepcopy(self._require_device(device_id))

    async def execute(self, action: HardwareAction) -> ActionResult:
        started_at = self._clock()
        try:
            device = self._require_device(action.device_id)
        except KeyError:
            return self._failure(
                action,
                started_at,
                "DEVICE_NOT_FOUND",
                "Action targets a different physical device",
                False,
            )
        if device.status is not DeviceStatus.ONLINE:
            return self._failure(
                action,
                started_at,
                "DEVICE_OFFLINE",
                "ESP8266 is not connected",
                True,
            )
        capability = next(
            (item for item in self.capabilities if item.id == action.capability_id),
            None,
        )
        if capability is None:
            return self._failure(
                action,
                started_at,
                "CAPABILITY_NOT_FOUND",
                "Capability is not provided by this ESP8266",
                False,
            )
        message: dict[str, object] = {
            "command": "get_state" if capability.operation == "get_state" else "set_led",
            "action_id": action.action_id,
        }
        if capability.operation in {"turn_on", "turn_off"}:
            message["on"] = capability.operation == "turn_on"
        try:
            response = await self._require_adapter().request(message)
            output = self._validated_response(action, capability, response)
        except TimeoutError:
            raise
        except SerialEndpointUnavailable:
            self._set_status(DeviceStatus.OFFLINE)
            return self._failure(
                action,
                started_at,
                "DEVICE_OFFLINE",
                "ESP8266 disconnected during execution",
                True,
            )
        except SerialProtocolError as error:
            return self._failure(
                action,
                started_at,
                "DRIVER_ERROR",
                str(error),
                False,
            )
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
        if self._device is None or self._device.status is not DeviceStatus.ONLINE:
            return False
        try:
            response = await self._require_adapter().request(
                {"command": "cancel", "action_id": action_id}
            )
        except (SerialEndpointUnavailable, SerialProtocolError, TimeoutError):
            return False
        return (
            response.get("type") == "ack"
            and response.get("action_id") == action_id
            and response.get("cancelled") is True
        )

    def _accept_identity(self, response: dict[str, object]) -> None:
        if response.get("type") != "identity":
            raise SerialProtocolError("hello response must be an identity message")
        chip_id = response.get("chip_id")
        firmware = response.get("firmware")
        if not isinstance(chip_id, str) or not chip_id.strip():
            raise SerialProtocolError("identity requires chip_id")
        if not isinstance(firmware, str) or not firmware.strip():
            raise SerialProtocolError("identity requires firmware")
        normalized = chip_id.strip().casefold()
        if self._chip_id is not None and normalized != self._chip_id:
            raise SerialProtocolError("endpoint resolved to a different ESP8266 identity")
        self._chip_id = normalized
        self._firmware_version = firmware
        if self._device is None:
            self._device = Device(
                id=f"esp8266:{normalized}",
                type="indicator_light",
                name="NodeMCU v3 Board LED",
                status=DeviceStatus.OFFLINE,
                capability_ids=(),
                driver_id=self.driver_id,
                metadata={"board": "nodemcu_v3", "firmware": firmware},
                last_seen_at=self._clock(),
                version=0,
            )

    def _validated_response(
        self,
        action: HardwareAction,
        capability: Capability,
        response: dict[str, object],
    ) -> dict[str, object]:
        if response.get("action_id") != action.action_id:
            raise SerialProtocolError("response action_id does not match request")
        expected_type = "state" if capability.operation == "get_state" else "ack"
        if response.get("type") != expected_type:
            raise SerialProtocolError(f"expected {expected_type} response")
        if expected_type == "ack" and response.get("accepted") is not True:
            raise SerialProtocolError("device did not acknowledge the write")
        if type(response.get("on")) is not bool:
            raise SerialProtocolError("response requires boolean on state")
        return {"on": response["on"]}

    def _require_adapter(self) -> SerialJsonTransport:
        if self._adapter_error is not None or self._transport is None:
            raise SerialAdapterUnavailable(self._adapter_error or "Serial adapter unavailable")
        return self._transport

    def _require_device(self, device_id: str) -> Device:
        if self._device is None or self._device.id != device_id:
            raise KeyError(f"Device not found: {device_id}")
        return self._device

    def _set_status(self, status: DeviceStatus) -> None:
        if self._device is None or self._device.status is status:
            return
        self._device = replace(
            self._device,
            status=status,
            last_seen_at=self._clock(),
            version=self._device.version + 1,
        )

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


def _capabilities(device_id: str, timeout_ms: int) -> tuple[Capability, ...]:
    output_schema = {
        "type": "object",
        "properties": {"on": {"type": "boolean"}},
        "required": ["on"],
        "additionalProperties": False,
    }
    empty_input = {"type": "object", "maxProperties": 0, "additionalProperties": False}
    return tuple(
        Capability(
            id=f"{device_id}.{operation}",
            device_id=device_id,
            operation=operation,
            description=f"NodeMCU v3 board LED {operation}",
            input_schema=empty_input,
            output_schema=output_schema,
            schema_version="1.0.0",
            revision=0,
            risk_level=risk,
            idempotency=IdempotencyMode.IDEMPOTENT,
            timeout_ms=timeout_ms,
            enabled=True,
        )
        for operation, risk in (
            ("get_state", RiskLevel.READ_ONLY),
            ("turn_on", RiskLevel.LOW),
            ("turn_off", RiskLevel.LOW),
        )
    )


__all__ = ("Esp8266NodeMcuSerialDriver", "SerialDriverConfig")
