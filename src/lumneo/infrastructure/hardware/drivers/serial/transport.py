"""Replaceable JSON-lines serial transport with an optional pyserial adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Protocol


class SerialAdapterUnavailable(RuntimeError):
    """The host serial implementation/dependency is unavailable."""


class SerialEndpointUnavailable(ConnectionError):
    """The configured endpoint cannot currently reach the device."""


class SerialProtocolError(ValueError):
    """The endpoint returned an invalid or mismatched protocol message."""


class SerialJsonTransport(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def request(self, message: dict[str, object]) -> dict[str, object]: ...


SerialTransportFactory = Callable[[str, int, int], SerialJsonTransport]


class PySerialJsonTransport:
    """Lazy pyserial implementation used by T51 physical composition."""

    def __init__(self, endpoint: str, baud_rate: int, timeout_ms: int) -> None:
        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as error:
            raise SerialAdapterUnavailable(
                "pyserial is required for the physical ESP8266 Driver"
            ) from error
        self._serial_module = serial
        self._endpoint = endpoint
        self._baud_rate = baud_rate
        self._timeout_seconds = timeout_ms / 1_000
        self._connection = None

    async def open(self) -> None:
        if self._connection is not None:
            return
        try:
            self._connection = await asyncio.to_thread(
                self._serial_module.Serial,
                self._endpoint,
                self._baud_rate,
                timeout=self._timeout_seconds,
                write_timeout=self._timeout_seconds,
            )
            # Opening a NodeMCU USB serial endpoint can pulse its auto-reset
            # circuit.  Let firmware finish booting, then discard the ROM boot
            # banner (which is not emitted at our protocol baud rate).
            await asyncio.sleep(2.0)
            await asyncio.to_thread(self._connection.reset_input_buffer)
        except Exception as error:
            raise SerialEndpointUnavailable(
                f"Cannot open serial endpoint {self._endpoint}"
            ) from error

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await asyncio.to_thread(connection.close)

    async def request(self, message: dict[str, object]) -> dict[str, object]:
        if self._connection is None:
            raise SerialEndpointUnavailable("Serial endpoint is not open")
        encoded = (
            json.dumps(message, separators=(",", ":"), allow_nan=False).encode("utf-8")
            + b"\n"
        )
        try:
            await asyncio.to_thread(self._connection.write, encoded)
            await asyncio.to_thread(self._connection.flush)
            line = await asyncio.to_thread(self._connection.readline)
        except Exception as error:
            raise SerialEndpointUnavailable("Serial request failed") from error
        if not line:
            raise TimeoutError("Serial response deadline expired")
        try:
            response = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SerialProtocolError("Device returned invalid JSON") from error
        if not isinstance(response, dict) or any(
            not isinstance(key, str) for key in response
        ):
            raise SerialProtocolError("Device response must be a JSON object")
        return response


__all__ = (
    "PySerialJsonTransport",
    "SerialAdapterUnavailable",
    "SerialEndpointUnavailable",
    "SerialJsonTransport",
    "SerialProtocolError",
    "SerialTransportFactory",
)
