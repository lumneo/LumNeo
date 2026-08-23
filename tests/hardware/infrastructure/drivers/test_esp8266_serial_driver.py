from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from lumneo.hardware.domain.action import PHYSICAL_ACTION_KIND, HardwareAction
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus, RiskLevel
from lumneo.hardware.ports.driver import DeviceDriver
from lumneo.infrastructure.hardware.drivers.serial.esp8266_nodemcu import (
    Esp8266NodeMcuSerialDriver,
    SerialDriverConfig,
)
from lumneo.infrastructure.hardware.drivers.serial.transport import (
    SerialAdapterUnavailable,
    SerialEndpointUnavailable,
)


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=timezone.utc)


@dataclass
class MockBoard:
    chip_id: str = "A1B2C3"
    firmware: str = "1.0.0"
    on: bool = False
    reachable: bool = True
    response_action_id: str | None = None


class MockSerialTransport:
    def __init__(self, endpoint: str, boards: dict[str, MockBoard]) -> None:
        self.endpoint = endpoint
        self.boards = boards
        self.opened = False
        self.requests: list[dict[str, object]] = []

    async def open(self) -> None:
        board = self.boards.get(self.endpoint)
        if board is None or not board.reachable:
            raise SerialEndpointUnavailable(f"offline: {self.endpoint}")
        self.opened = True

    async def close(self) -> None:
        self.opened = False

    async def request(self, message: dict[str, object]) -> dict[str, object]:
        if not self.opened:
            raise SerialEndpointUnavailable("not open")
        self.requests.append(dict(message))
        board = self.boards[self.endpoint]
        if not board.reachable:
            raise SerialEndpointUnavailable("USB removed")
        command = message["command"]
        if command == "hello":
            return {
                "type": "identity",
                "chip_id": board.chip_id,
                "firmware": board.firmware,
            }
        action_id = board.response_action_id or message["action_id"]
        if command == "get_state":
            return {"type": "state", "action_id": action_id, "on": board.on}
        if command == "set_led":
            board.on = bool(message["on"])
            return {
                "type": "ack",
                "action_id": action_id,
                "accepted": True,
                "on": board.on,
            }
        if command == "cancel":
            return {"type": "ack", "action_id": action_id, "cancelled": True}
        raise AssertionError(f"unexpected command: {command}")


class MockTransportFactory:
    def __init__(
        self,
        boards: dict[str, MockBoard],
        *,
        adapter_available: bool = True,
    ) -> None:
        self.boards = boards
        self.adapter_available = adapter_available
        self.transports: list[MockSerialTransport] = []

    def __call__(self, endpoint: str, baud_rate: int, timeout_ms: int):
        if not self.adapter_available:
            raise SerialAdapterUnavailable("mock serial adapter missing")
        transport = MockSerialTransport(endpoint, self.boards)
        self.transports.append(transport)
        return transport


def _action(
    device_id: str,
    operation: str,
    *,
    action_id: str = "physical-action-1",
) -> HardwareAction:
    return HardwareAction(
        action_id,
        PHYSICAL_ACTION_KIND,
        device_id,
        f"{device_id}.{operation}",
        {},
        "physical-test",
        ActionStatus.RUNNING,
        None,
        2_000,
        None,
        None,
        None,
        "sha256:test",
        None,
        NOW,
        NOW,
    )


def test_driver_satisfies_port_and_mocked_lifecycle_and_actions() -> None:
    async def scenario():
        factory = MockTransportFactory({"COM3": MockBoard()})
        driver = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=factory,
            clock=lambda: NOW,
        )
        assert isinstance(driver, DeviceDriver)
        before = await driver.health_check()
        await driver.initialize()
        ready = await driver.health_check()
        discovered = await driver.discover()
        device = discovered[0]
        await driver.connect(device.id)
        online = await driver.get_status(device.id)
        turned_on = await driver.execute(_action(device.id, "turn_on"))
        state = await driver.execute(
            _action(device.id, "get_state", action_id="physical-action-2")
        )
        cancelled = await driver.cancel("physical-action-3")
        await driver.disconnect(device.id)
        offline = await driver.get_status(device.id)
        await driver.shutdown()
        stopped = await driver.health_check()
        return before, ready, device, online, turned_on, state, cancelled, offline, stopped, driver

    before, ready, device, online, turned_on, state, cancelled, offline, stopped, driver = asyncio.run(scenario())
    assert before.available is False
    assert ready.available is True
    assert device.id == "esp8266:a1b2c3"
    assert online is DeviceStatus.ONLINE
    assert turned_on.status is state.status is ActionStatus.SUCCEEDED
    assert turned_on.output == state.output == {"on": True}
    assert cancelled is True
    assert offline is DeviceStatus.OFFLINE
    assert stopped.available is False
    assert {capability.risk_level for capability in driver.capabilities} == {
        RiskLevel.READ_ONLY,
        RiskLevel.LOW,
    }


def test_endpoint_change_does_not_change_device_identity_or_leak_transport() -> None:
    async def scenario():
        board = MockBoard()
        factory = MockTransportFactory({"COM3": board, "COM7": board})
        driver = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=factory,
            clock=lambda: NOW,
        )
        await driver.initialize()
        first = (await driver.discover())[0]
        await driver.rebind_endpoint("COM7")
        second = (await driver.discover())[0]
        return first, second, driver.capabilities

    first, second, capabilities = asyncio.run(scenario())
    assert second.id == first.id == "esp8266:a1b2c3"
    assert second.metadata == first.metadata
    serialized = str(second.to_dict()).casefold()
    assert "com3" not in serialized and "com7" not in serialized
    assert all(capability.device_id == first.id for capability in capabilities)


def test_adapter_unavailable_is_distinct_from_device_offline() -> None:
    async def scenario():
        missing_adapter = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=MockTransportFactory({}, adapter_available=False),
            clock=lambda: NOW,
        )
        await missing_adapter.initialize()
        adapter_health = await missing_adapter.health_check()

        board = MockBoard()
        factory = MockTransportFactory({"COM3": board})
        offline_device = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=factory,
            clock=lambda: NOW,
        )
        await offline_device.initialize()
        known = (await offline_device.discover())[0]
        await offline_device.rebind_endpoint("COM99")
        rediscovered = await offline_device.discover()
        device_health = await offline_device.health_check()
        return adapter_health, known, rediscovered, device_health

    adapter_health, known, rediscovered, device_health = asyncio.run(scenario())
    assert adapter_health.available is False
    assert "adapter" in (adapter_health.message or "")
    assert device_health.available is True
    assert rediscovered[0].id == known.id
    assert rediscovered[0].status is DeviceStatus.OFFLINE


def test_mismatched_action_ack_is_driver_error_not_success() -> None:
    async def scenario():
        board = MockBoard(response_action_id="some-other-action")
        driver = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=MockTransportFactory({"COM3": board}),
            clock=lambda: NOW,
        )
        await driver.initialize()
        device = (await driver.discover())[0]
        await driver.connect(device.id)
        return await driver.execute(_action(device.id, "turn_on"))

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert result.error is not None and result.error.code == "DRIVER_ERROR"
    assert result.device_acknowledged is False


def test_endpoint_failure_during_action_marks_device_offline() -> None:
    async def scenario():
        board = MockBoard()
        driver = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=MockTransportFactory({"COM3": board}),
            clock=lambda: NOW,
        )
        await driver.initialize()
        device = (await driver.discover())[0]
        await driver.connect(device.id)
        board.reachable = False
        result = await driver.execute(_action(device.id, "turn_on"))
        return result, await driver.get_status(device.id)

    result, status = asyncio.run(scenario())
    assert result.error is not None and result.error.code == "DEVICE_OFFLINE"
    assert status is DeviceStatus.OFFLINE


@pytest.mark.parametrize(
    "config",
    [
        lambda: SerialDriverConfig(""),
        lambda: SerialDriverConfig("COM3", baud_rate=0),
        lambda: SerialDriverConfig("COM3", request_timeout_ms=99),
        lambda: SerialDriverConfig("COM3", request_timeout_ms=60_001),
    ],
)
def test_serial_config_rejects_invalid_values(config) -> None:
    with pytest.raises(ValueError):
        config()
