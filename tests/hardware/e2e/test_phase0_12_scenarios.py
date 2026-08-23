from __future__ import annotations

import asyncio

from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.simulation.faults import FaultProfile
from lumneo.runtime.tools.hardware import HardwareExecuteTool

from tests.hardware.execution.test_executor import NOW
from tests.hardware.integration.composition import build_integration_harness


def _input(capability: str, parameters: dict[str, object], **extra: object):
    payload = {
        "device_id": capability.rsplit(".", 1)[0],
        "capability_id": capability,
        "parameters": parameters,
        "requester": "agent-e2e",
    }
    payload.update(extra)
    return payload


def test_01_agent_queries_available_devices() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        return await harness.facade.list_devices()

    devices = asyncio.run(scenario())
    assert {device.id for device in devices} == {
        "simulated-light-01",
        "simulated-temperature-01",
    }


def test_02_agent_queries_device_capabilities() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        return await harness.facade.list_capabilities("simulated-light-01")

    capabilities = asyncio.run(scenario())
    assert {item.operation for item in capabilities} == {
        "get_state",
        "turn_on",
        "turn_off",
        "set_brightness",
    }


def test_03_agent_turns_on_simulated_light() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        return await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.turn_on", {})
        )

    output = asyncio.run(scenario())
    assert output["action"]["status"] == "succeeded"
    assert output["result"]["output"]["on"] is True


def test_04_agent_sets_brightness_and_receives_state_event() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        received = []

        async def handler(event):
            received.append(event)

        await harness.subscribe("hardware.action.succeeded", handler)
        output = await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.set_brightness", {"brightness": 64})
        )
        return output, received

    output, received = asyncio.run(scenario())
    assert output["result"]["output"]["brightness"] == 64
    assert len(received) == 1
    assert received[0].action_id == output["action"]["action_id"]


def test_05_agent_reads_simulated_temperature() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        return await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-temperature-01.read_temperature", {})
        )

    output = asyncio.run(scenario())
    assert output["result"]["output"] == {
        "value": 22.5,
        "unit": "celsius",
        "measured_at": NOW.isoformat(),
    }


def test_06_invalid_brightness_is_rejected() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        return await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.set_brightness", {"brightness": 101})
        )

    output = asyncio.run(scenario())
    assert output["action"]["status"] == "failed"
    assert output["result"]["error"]["code"] == "INVALID_PARAMETERS"


def test_07_offline_device_action_fails_before_driver() -> None:
    async def scenario():
        harness = await build_integration_harness(
            now=NOW,
            light_fault=FaultProfile(offline=True),
        )
        output = await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.turn_on", {})
        )
        return output, harness.light_execution_count

    output, calls = asyncio.run(scenario())
    assert output["result"]["error"]["code"] == "DEVICE_OFFLINE"
    assert calls == 0


def test_08_approval_required_action_is_blocked_until_approved() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW, low_auto_approve=False)
        output = await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.turn_on", {})
        )
        calls_before = harness.light_execution_count
        approved = await harness.facade.approve_action(
            output["action"]["action_id"],
            "human-e2e",
        )
        return output, calls_before, approved, harness.light_execution_count

    output, calls_before, approved, calls_after = asyncio.run(scenario())
    assert output["action"]["status"] == "awaiting_approval"
    assert calls_before == 0
    assert approved.status is ActionStatus.SUCCEEDED
    assert calls_after == 1


def test_09_rejected_action_is_never_executed() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW, low_auto_approve=False)
        output = await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.turn_on", {})
        )
        rejected = await harness.facade.reject_action(
            output["action"]["action_id"],
            "human-e2e",
            "denied",
        )
        return rejected, harness.light_execution_count

    rejected, calls = asyncio.run(scenario())
    assert rejected.status is ActionStatus.REJECTED
    assert calls == 0


def test_10_timeout_cancel_driver_error_and_unknown_outcome_terminals() -> None:
    async def scenario():
        timeout_harness = await build_integration_harness(now=NOW, block_light=True)
        unknown = await HardwareExecuteTool(timeout_harness.facade).invoke(
            _input("simulated-light-01.turn_on", {}, timeout_ms=1)
        )

        cancel_harness = await build_integration_harness(
            now=NOW,
            block_light=True,
            cancel_confirmed=True,
        )
        submission = asyncio.create_task(
            HardwareExecuteTool(cancel_harness.facade).invoke(
                _input("simulated-light-01.turn_on", {})
            )
        )
        await cancel_harness.wait_until_light_started()
        cancelled = await cancel_harness.facade.cancel_action(
            "integration-action-1",
            "agent-e2e",
        )
        cancel_harness.release_light()
        returned = await submission

        error_harness = await build_integration_harness(
            now=NOW,
            light_fault=FaultProfile(driver_error="deterministic driver error"),
        )
        driver_error = await HardwareExecuteTool(error_harness.facade).invoke(
            _input("simulated-light-01.turn_on", {})
        )
        return unknown, cancelled, returned, driver_error

    unknown, cancelled, returned, driver_error = asyncio.run(scenario())
    assert unknown["action"]["status"] == "reconciliation_required"
    assert unknown["result"]["error"]["code"] == "ACTION_TIMEOUT"
    assert cancelled.status is ActionStatus.CANCELLED
    assert returned["action"]["status"] == "cancelled"
    assert driver_error["action"]["status"] == "failed"
    assert driver_error["result"]["error"]["code"] == "DRIVER_ERROR"


def test_11_same_idempotency_key_executes_once() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW, key_required=True)
        tool = HardwareExecuteTool(harness.facade)
        payload = _input(
            "simulated-light-01.set_brightness",
            {"brightness": 33},
            idempotency_key="e2e-key",
        )
        first = await tool.invoke(payload)
        second = await tool.invoke(payload)
        return first, second, harness.light_execution_count

    first, second, calls = asyncio.run(scenario())
    assert second["action"]["action_id"] == first["action"]["action_id"]
    assert calls == 1


def test_12_action_id_returns_complete_action_record() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        output = await HardwareExecuteTool(harness.facade).invoke(
            _input("simulated-light-01.turn_on", {})
        )
        record = await harness.facade.get_action_record(output["action"]["action_id"])
        return output, record

    output, record = asyncio.run(scenario())
    assert record["action"].action_id == output["action"]["action_id"]
    assert record["result"] is not None
    assert record["transitions"]
    assert record["events"]
    assert record["audits"]
    assert "approvals" in record and "reconciliations" in record
