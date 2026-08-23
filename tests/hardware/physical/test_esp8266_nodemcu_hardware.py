from __future__ import annotations

import asyncio
import os
from itertools import count

import pytest

from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus
from lumneo.hardware.physical_bootstrap import esp8266_nodemcu_session
from lumneo.infrastructure.hardware.drivers.serial.esp8266_nodemcu import (
    Esp8266NodeMcuSerialDriver,
    SerialDriverConfig,
)


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        os.getenv("LUMNEO_RUN_HARDWARE_TESTS") != "1",
        reason="requires a flashed ESP8266 NodeMCU v3",
    ),
]


def test_real_board_identity_state_and_confirmable_write_use_action_path() -> None:
    async def scenario():
        endpoint = os.getenv("LUMNEO_HARDWARE_PORT", "COM3")
        sequence = count(1)
        async with esp8266_nodemcu_session(
            endpoint,
            low_auto_approve=False,
            action_id_factory=lambda: f"physical-com3-{next(sequence)}",
        ) as facade:
            device = (await facade.list_devices())[0]
            capabilities = {
                item.operation: item for item in await facade.list_capabilities(device.id)
            }
            initial = await facade.submit_action(
                device_id=device.id,
                capability_id=capabilities["get_state"].id,
                parameters={},
                requester="t51-hardware-smoke",
            )
            on_waiting = await facade.submit_action(
                device_id=device.id,
                capability_id=capabilities["turn_on"].id,
                parameters={},
                requester="t51-hardware-smoke",
            )
            on = await facade.approve_action(on_waiting.action_id, "t51-human")
            off_waiting = await facade.submit_action(
                device_id=device.id,
                capability_id=capabilities["turn_off"].id,
                parameters={},
                requester="t51-hardware-smoke",
            )
            off = await facade.approve_action(off_waiting.action_id, "t51-human")
            records = [
                await facade.get_action_record(action.action_id)
                for action in (initial, on, off)
            ]
            return device, initial, on_waiting, on, off_waiting, off, records

    device, initial, on_waiting, on, off_waiting, off, records = asyncio.run(scenario())
    assert device.status is DeviceStatus.ONLINE
    assert device.id.startswith("esp8266:") and "com" not in device.id.casefold()
    assert initial.status is ActionStatus.SUCCEEDED
    assert type(records[0]["result"].output["on"]) is bool
    assert on_waiting.status is off_waiting.status is ActionStatus.AWAITING_APPROVAL
    assert on.status is off.status is ActionStatus.SUCCEEDED
    assert records[1]["result"].output == {"on": True}
    assert records[2]["result"].output == {"on": False}
    assert all(record["events"] and record["audits"] for record in records)


def test_real_board_identity_is_stable_across_controlled_reconnect() -> None:
    async def scenario():
        endpoint = os.getenv("LUMNEO_HARDWARE_PORT", "COM3")
        driver = Esp8266NodeMcuSerialDriver(SerialDriverConfig(endpoint))
        await driver.initialize()
        try:
            first = (await driver.discover())[0]
            await driver.connect(first.id)
            await driver.disconnect(first.id)
            second = (await driver.discover())[0]
            await driver.connect(second.id)
            return first, driver.get_device(second.id)
        finally:
            await driver.shutdown()

    first, second = asyncio.run(scenario())
    assert first.id == second.id
    assert first.metadata == second.metadata
    assert second.status is DeviceStatus.ONLINE
    assert "com" not in str(second.to_dict()).casefold()
