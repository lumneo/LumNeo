from __future__ import annotations

import asyncio
from itertools import count

from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.physical_bootstrap import esp8266_nodemcu_session
from lumneo.infrastructure.hardware.drivers.serial.esp8266_nodemcu import (
    Esp8266NodeMcuSerialDriver,
    SerialDriverConfig,
)

from tests.hardware.infrastructure.drivers.test_esp8266_serial_driver import (
    MockBoard,
    MockSerialTransport,
    MockTransportFactory,
)


class WriteTimeoutTransport(MockSerialTransport):
    async def request(self, message: dict[str, object]) -> dict[str, object]:
        if message["command"] == "set_led":
            self.requests.append(dict(message))
            raise TimeoutError("ACK deliberately suppressed after dispatch")
        return await super().request(message)


class WriteTimeoutFactory(MockTransportFactory):
    def __call__(self, endpoint: str, baud_rate: int, timeout_ms: int):
        transport = WriteTimeoutTransport(endpoint, self.boards)
        self.transports.append(transport)
        return transport


def test_reconnect_and_endpoint_change_preserve_identity_without_protocol_leakage() -> None:
    async def scenario():
        board = MockBoard(chip_id="D3EF6F")
        driver = Esp8266NodeMcuSerialDriver(
            SerialDriverConfig("COM3"),
            transport_factory=MockTransportFactory({"COM3": board, "COM8": board}),
        )
        await driver.initialize()
        first = (await driver.discover())[0]
        await driver.connect(first.id)
        await driver.disconnect(first.id)
        await driver.rebind_endpoint("COM8")
        second = (await driver.discover())[0]
        await driver.connect(second.id)
        connected = driver.get_device(second.id)
        await driver.shutdown()
        return first, connected, driver.capabilities

    first, second, capabilities = asyncio.run(scenario())
    assert first.id == second.id == "esp8266:d3ef6f"
    assert first.metadata == second.metadata
    exposed = str((second.to_dict(), [item.to_dict() for item in capabilities])).casefold()
    assert "com3" not in exposed and "com8" not in exposed


def test_forced_disconnect_is_failed_and_traceable_instead_of_false_success() -> None:
    async def scenario():
        sequence = count(1)
        board = MockBoard()
        factory = MockTransportFactory({"COM3": board})
        async with esp8266_nodemcu_session(
            "COM3",
            low_auto_approve=False,
            transport_factory=factory,
            action_id_factory=lambda: f"disconnect-{next(sequence)}",
        ) as facade:
            device = (await facade.list_devices())[0]
            capabilities = {
                item.operation: item
                for item in await facade.list_capabilities(device.id)
            }
            board.reachable = False
            action = await facade.submit_action(
                device_id=device.id,
                capability_id=capabilities["get_state"].id,
                parameters={},
                requester="t52-acceptance",
                correlation_id="forced-disconnect",
            )
            return action, await facade.get_action_record(action.action_id)

    action, record = asyncio.run(scenario())
    assert action.status is ActionStatus.FAILED
    assert record["result"].error.code == "DEVICE_OFFLINE"
    assert record["result"].device_acknowledged is False
    assert record["events"] and len(record["audits"]) == 1
    assert record["action"].correlation_id == "forced-disconnect"


def test_write_timeout_after_dispatch_is_unknown_audited_and_never_retried() -> None:
    async def scenario():
        sequence = count(1)
        factory = WriteTimeoutFactory({"COM3": MockBoard()})
        async with esp8266_nodemcu_session(
            "COM3",
            low_auto_approve=False,
            transport_factory=factory,
            action_id_factory=lambda: f"timeout-{next(sequence)}",
        ) as facade:
            device = (await facade.list_devices())[0]
            capability = next(
                item
                for item in await facade.list_capabilities(device.id)
                if item.operation == "turn_on"
            )
            waiting = await facade.submit_action(
                device_id=device.id,
                capability_id=capability.id,
                parameters={},
                requester="t52-acceptance",
            )
            finished = await facade.approve_action(waiting.action_id, "t52-human")
            record = await facade.get_action_record(finished.action_id)
            writes = [
                request
                for request in factory.transports[0].requests
                if request["command"] == "set_led"
            ]
            return waiting, finished, record, writes

    waiting, finished, record, writes = asyncio.run(scenario())
    assert waiting.status is ActionStatus.AWAITING_APPROVAL
    assert finished.status is ActionStatus.RECONCILIATION_REQUIRED
    assert record["result"].error.code == "ACTION_TIMEOUT"
    assert record["result"].error.details["automatic_retry"] is False
    assert record["result"].device_acknowledged is False
    assert len(writes) == 1
    assert record["reconciliations"][0]["record_kind"] == "outcome_unknown"
    assert record["events"] and len(record["audits"]) == 2
    assert "com3" not in str(record).casefold()
