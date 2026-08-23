from __future__ import annotations

import asyncio
from itertools import count

import pytest

from lumneo.hardware.bootstrap import build_simulated_hardware_facade
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus
from lumneo.hardware.facade import HardwareFacade

from tests.hardware.execution.test_executor import NOW


def _ids():
    sequence = count(1)
    return lambda: f"facade-action-{next(sequence)}"


def test_bootstrap_returns_only_facade_and_all_query_methods_work() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        devices = await facade.list_devices()
        lights = await facade.list_devices(status=DeviceStatus.ONLINE, type="light")
        light = await facade.get_device("simulated-light-01")
        capabilities = await facade.list_capabilities(light.id)
        return facade, devices, lights, light, capabilities

    facade, devices, lights, light, capabilities = asyncio.run(scenario())
    assert type(facade) is HardwareFacade
    assert {device.id for device in devices} == {
        "simulated-light-01",
        "simulated-temperature-01",
    }
    assert lights == [light]
    assert {capability.operation for capability in capabilities} == {
        "get_state",
        "turn_on",
        "turn_off",
        "set_brightness",
    }
    public_names = {name for name in dir(facade) if not name.startswith("_")}
    assert "repository" not in public_names
    assert "executor" not in public_names
    assert "driver" not in public_names
    assert "permission_gate" not in public_names


def test_submit_get_and_complete_record_flow_through_facade() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        action = await facade.submit_action(
            device_id="simulated-temperature-01",
            capability_id="simulated-temperature-01.read_temperature",
            parameters={},
            requester="agent-1",
            correlation_id="correlation-1",
        )
        return action, await facade.get_action(action.action_id), await facade.get_action_record(action.action_id)

    submitted, queried, record = asyncio.run(scenario())
    assert submitted == queried
    assert submitted.status is ActionStatus.SUCCEEDED
    assert record["action"] == submitted
    assert record["result"].output["value"] == 22.5
    assert len(record["transitions"]) == 4
    assert len(record["events"]) == 1
    assert len(record["audits"]) == 1


def test_approve_action_revalidates_and_executes() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            low_auto_approve=False,
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        waiting = await facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="agent-1",
        )
        before = await facade.get_action_record(waiting.action_id)
        approved = await facade.approve_action(waiting.action_id, "human-1")
        after = await facade.get_action_record(waiting.action_id)
        return waiting, before, approved, after

    waiting, before, approved, after = asyncio.run(scenario())
    assert waiting.status is ActionStatus.AWAITING_APPROVAL
    assert before["result"].status is ActionStatus.AWAITING_APPROVAL
    assert approved.status is ActionStatus.SUCCEEDED
    assert after["result"].output["on"] is True
    assert after["approvals"][0]["approver"] == "human-1"
    assert len(after["audits"]) == 2


def test_reject_action_records_reason_and_never_runs() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            low_auto_approve=False,
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        waiting = await facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="agent-1",
        )
        rejected = await facade.reject_action(
            waiting.action_id,
            "human-1",
            "Not now",
        )
        return rejected, await facade.get_action_record(waiting.action_id)

    rejected, record = asyncio.run(scenario())
    assert rejected.status is ActionStatus.REJECTED
    assert record["approvals"][0]["decision"] == "rejected"
    assert record["approvals"][0]["reason"] == "Not now"
    assert all(item["to_status"] != "running" for item in record["transitions"])


def test_cancel_action_before_execution_and_missing_queries() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            low_auto_approve=False,
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        waiting = await facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_off",
            parameters={},
            requester="agent-1",
        )
        cancelled = await facade.cancel_action(waiting.action_id, "agent-1")
        with pytest.raises(KeyError):
            await facade.get_device("missing-device")
        with pytest.raises(KeyError):
            await facade.get_action("missing-action")
        return cancelled, await facade.get_action_record(waiting.action_id)

    cancelled, record = asyncio.run(scenario())
    assert cancelled.status is ActionStatus.CANCELLED
    assert record["result"].status is ActionStatus.CANCELLED
