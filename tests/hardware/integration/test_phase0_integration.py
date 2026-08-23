from __future__ import annotations

import asyncio
from datetime import timezone

from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.simulation.faults import FaultProfile

from tests.hardware.execution.test_executor import NOW
from tests.hardware.integration.composition import build_integration_harness


def test_a1_a2_registry_queries_are_available_only_through_facade() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        devices = await harness.facade.list_devices()
        capabilities = await harness.facade.list_capabilities("simulated-light-01")
        return devices, capabilities

    devices, capabilities = asyncio.run(scenario())
    assert len(devices) == 2
    assert len(capabilities) == 4


def test_a3_all_simulated_operations_complete_through_facade() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        facade = harness.facade
        actions = []
        for capability_id, parameters in (
            ("simulated-light-01.turn_on", {}),
            ("simulated-light-01.set_brightness", {"brightness": 55}),
            ("simulated-light-01.turn_off", {}),
            ("simulated-temperature-01.read_temperature", {}),
        ):
            actions.append(
                await facade.submit_action(
                    device_id=capability_id.rsplit(".", 1)[0],
                    capability_id=capability_id,
                    parameters=parameters,
                    requester="integration",
                )
            )
        return actions

    actions = asyncio.run(scenario())
    assert all(action.status is ActionStatus.SUCCEEDED for action in actions)


def test_a3_invalid_and_offline_actions_never_reach_driver() -> None:
    async def scenario():
        invalid_harness = await build_integration_harness(now=NOW)
        invalid = await invalid_harness.facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.set_brightness",
            parameters={"brightness": 101},
            requester="integration",
        )
        offline_harness = await build_integration_harness(
            now=NOW,
            light_fault=FaultProfile(offline=True),
        )
        offline = await offline_harness.facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="integration",
        )
        return (
            invalid,
            invalid_harness.light_execution_count,
            offline,
            offline_harness.light_execution_count,
        )

    invalid, invalid_calls, offline, offline_calls = asyncio.run(scenario())
    assert invalid.status is offline.status is ActionStatus.FAILED
    assert invalid_calls == offline_calls == 0


def test_a3_invalid_driver_output_is_failed_and_audited() -> None:
    async def scenario():
        harness = await build_integration_harness(
            now=NOW,
            light_fault=FaultProfile(invalid_output=True),
        )
        action = await harness.facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="integration",
        )
        return action, await harness.facade.get_action_record(action.action_id)

    action, record = asyncio.run(scenario())
    assert action.status is ActionStatus.FAILED
    assert record["result"].error.code == "OUTPUT_VALIDATION_FAILED"
    assert len(record["audits"]) == 1


def test_a4_approval_blocks_then_human_approval_executes() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW, low_auto_approve=False)
        waiting = await harness.facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="integration",
        )
        calls_before = harness.light_execution_count
        approved = await harness.facade.approve_action(waiting.action_id, "human-1")
        return waiting, calls_before, approved, harness.light_execution_count

    waiting, calls_before, approved, calls_after = asyncio.run(scenario())
    assert waiting.status is ActionStatus.AWAITING_APPROVAL
    assert calls_before == 0
    assert approved.status is ActionStatus.SUCCEEDED
    assert calls_after == 1


def test_a5_unknown_timeout_is_reconciled_without_retry() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW, block_light=True)
        action = await harness.facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="integration",
            timeout_ms=1,
        )
        return action, harness.light_execution_count, await harness.facade.get_action_record(action.action_id)

    action, calls, record = asyncio.run(scenario())
    assert action.status is ActionStatus.RECONCILIATION_REQUIRED
    assert calls == 1
    assert record["reconciliations"][0]["automatic_retry"] is False


def test_a5_confirmed_running_cancel_wins_terminal_race() -> None:
    async def scenario():
        harness = await build_integration_harness(
            now=NOW,
            block_light=True,
            cancel_confirmed=True,
        )
        submission = asyncio.create_task(
            harness.facade.submit_action(
                device_id="simulated-light-01",
                capability_id="simulated-light-01.turn_on",
                parameters={},
                requester="integration",
            )
        )
        await harness.wait_until_light_started()
        cancelled = await harness.facade.cancel_action("integration-action-1", "integration")
        harness.release_light()
        submitted = await submission
        return cancelled, submitted

    cancelled, submitted = asyncio.run(scenario())
    assert cancelled.status is submitted.status is ActionStatus.CANCELLED


def test_a5_key_required_same_key_executes_once() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW, key_required=True)
        inputs = {
            "device_id": "simulated-light-01",
            "capability_id": "simulated-light-01.set_brightness",
            "parameters": {"brightness": 25},
            "requester": "integration",
            "idempotency_key": "stable-key",
        }
        first = await harness.facade.submit_action(**inputs)
        second = await harness.facade.submit_action(**inputs)
        return first, second, harness.light_execution_count

    first, second, calls = asyncio.run(scenario())
    assert second.action_id == first.action_id
    assert calls == 1


def test_a6_event_failure_isolated_and_complete_record_keeps_event_and_audit() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        received = []

        async def failing(event):
            raise RuntimeError("consumer failure")

        async def healthy(event):
            received.append(event.event_id)

        await harness.subscribe("hardware.action.succeeded", failing)
        await harness.subscribe("hardware.action.succeeded", healthy)
        action = await harness.facade.submit_action(
            device_id="simulated-light-01",
            capability_id="simulated-light-01.turn_on",
            parameters={},
            requester="integration",
        )
        return action, received, await harness.facade.get_action_record(action.action_id)

    action, received, record = asyncio.run(scenario())
    assert action.status is ActionStatus.SUCCEEDED
    assert received == [record["events"][0].event_id]
    assert record["events"][0].timestamp.tzinfo is timezone.utc
    assert len(record["audits"]) == 1
