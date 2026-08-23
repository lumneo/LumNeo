from __future__ import annotations

import asyncio
from itertools import count

from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus
from lumneo.hardware.facade import HardwareFacade
from lumneo.hardware.physical_bootstrap import build_esp8266_nodemcu_facade

from tests.hardware.infrastructure.drivers.test_esp8266_serial_driver import (
    MockBoard,
    MockTransportFactory,
)


def test_mocked_physical_device_uses_facade_permission_and_audit_path() -> None:
    async def scenario():
        sequence = count(1)
        facade = await build_esp8266_nodemcu_facade(
            "COM3",
            low_auto_approve=False,
            transport_factory=MockTransportFactory({"COM3": MockBoard()}),
            action_id_factory=lambda: f"physical-fallback-{next(sequence)}",
        )
        device = (await facade.list_devices())[0]
        capabilities = {
            item.operation: item for item in await facade.list_capabilities(device.id)
        }
        read = await facade.submit_action(
            device_id=device.id,
            capability_id=capabilities["get_state"].id,
            parameters={},
            requester="ci-fallback",
        )
        waiting = await facade.submit_action(
            device_id=device.id,
            capability_id=capabilities["turn_on"].id,
            parameters={},
            requester="ci-fallback",
        )
        written = await facade.approve_action(waiting.action_id, "ci-approver")
        return facade, device, read, waiting, written, await facade.get_action_record(written.action_id)

    facade, device, read, waiting, written, record = asyncio.run(scenario())
    assert type(facade) is HardwareFacade
    assert device.id == "esp8266:a1b2c3"
    assert device.status is DeviceStatus.ONLINE
    assert "com3" not in str(device.to_dict()).casefold()
    assert read.status is ActionStatus.SUCCEEDED
    assert waiting.status is ActionStatus.AWAITING_APPROVAL
    assert written.status is ActionStatus.SUCCEEDED
    assert record["result"].output == {"on": True}
    assert record["approvals"][0]["approver"] == "ci-approver"
    assert record["events"] and len(record["audits"]) == 2
