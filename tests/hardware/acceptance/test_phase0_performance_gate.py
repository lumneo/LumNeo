from __future__ import annotations

import asyncio
import math
from time import perf_counter_ns

from lumneo.hardware.domain.enums import ActionStatus
from lumneo.infrastructure.hardware.event_bus.in_process import InProcessEventBus

from tests.hardware.execution.test_executor import NOW
from tests.hardware.integration.composition import build_integration_harness


def _p95_ms(samples_ns: list[int]) -> float:
    ordered = sorted(samples_ns)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index] / 1_000_000


def test_registry_query_p95_is_at_most_10ms() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        samples = []
        for _ in range(500):
            started = perf_counter_ns()
            await harness.facade.list_capabilities("simulated-light-01")
            samples.append(perf_counter_ns() - started)
        return _p95_ms(samples)

    p95 = asyncio.run(scenario())
    print(f"METRIC registry_query_p95_ms={p95:.6f} threshold_ms=10")
    assert p95 <= 10


def test_validation_enqueue_and_simulated_completion_p95_is_at_most_50ms() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        samples = []
        for _ in range(200):
            started = perf_counter_ns()
            action = await harness.facade.submit_action(
                device_id="simulated-temperature-01",
                capability_id="simulated-temperature-01.read_temperature",
                parameters={},
                requester="performance",
            )
            samples.append(perf_counter_ns() - started)
            assert action.status is ActionStatus.SUCCEEDED
        return _p95_ms(samples)

    p95 = asyncio.run(scenario())
    print(f"METRIC validation_enqueue_p95_ms={p95:.6f} threshold_ms=50")
    assert p95 <= 50


def test_in_process_event_dispatch_p95_is_at_most_50ms() -> None:
    async def scenario():
        bus = InProcessEventBus()
        received = 0

        async def handler(event):
            nonlocal received
            received += 1

        await bus.subscribe("hardware.performance.event", handler)
        samples = []
        for _ in range(500):
            event = await bus.create_event(
                event_type="hardware.performance.event",
                payload={},
                source="performance_gate",
                timestamp=NOW,
            )
            started = perf_counter_ns()
            await bus.publish(event)
            samples.append(perf_counter_ns() - started)
        return _p95_ms(samples), received

    p95, received = asyncio.run(scenario())
    print(f"METRIC event_dispatch_p95_ms={p95:.6f} threshold_ms=50")
    assert received == 500
    assert p95 <= 50


def test_twenty_concurrent_simulated_actions_complete() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        actions = await asyncio.gather(
            *(
                harness.facade.submit_action(
                    device_id="simulated-temperature-01",
                    capability_id="simulated-temperature-01.read_temperature",
                    parameters={},
                    requester=f"concurrent-{index}",
                )
                for index in range(20)
            )
        )
        return actions

    actions = asyncio.run(scenario())
    print(f"METRIC concurrent_actions_completed={len(actions)} required=20")
    assert len(actions) == 20
    assert all(action.status is ActionStatus.SUCCEEDED for action in actions)


def test_one_thousand_actions_have_no_lost_audit_records() -> None:
    async def scenario():
        harness = await build_integration_harness(now=NOW)
        action_ids = []
        for index in range(1_000):
            action = await harness.facade.submit_action(
                device_id="simulated-temperature-01",
                capability_id="simulated-temperature-01.read_temperature",
                parameters={},
                requester=f"audit-load-{index}",
            )
            assert action.status is ActionStatus.SUCCEEDED
            action_ids.append(action.action_id)
        audit_count = 0
        for action_id in action_ids:
            record = await harness.facade.get_action_record(action_id)
            audit_count += len(record["audits"])
        return len(action_ids), len(set(action_ids)), audit_count

    submitted, unique, audits = asyncio.run(scenario())
    print(
        f"METRIC actions_submitted={submitted} unique_action_ids={unique} "
        f"audit_records={audits}"
    )
    assert submitted == unique == audits == 1_000
