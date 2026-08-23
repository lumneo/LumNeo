from __future__ import annotations

import asyncio
import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.ports.event_bus import EventBus
from lumneo.infrastructure.hardware.event_bus.in_process import (
    DeduplicatingEventHandler,
    InProcessEventBus,
)


IMPLEMENTATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "lumneo"
    / "infrastructure"
    / "hardware"
    / "event_bus"
    / "in_process.py"
)


def _event(
    event_id: str = "event-1",
    *,
    event_type: str = "hardware.action.succeeded",
    sequence: int = 0,
    device_id: str | None = "device-1",
    source: str = "test",
) -> HardwareDomainEvent:
    return HardwareDomainEvent(
        event_id,
        event_type,
        device_id,
        "action-1",
        datetime.now(timezone.utc),
        {},
        sequence,
        None,
        None,
        source,
    )


def test_adapter_structurally_conforms_to_event_bus_port() -> None:
    assert isinstance(InProcessEventBus(), EventBus)


def test_publish_delivers_only_to_matching_subscribers() -> None:
    async def scenario() -> tuple[list[str], list[str]]:
        bus = InProcessEventBus()
        matching: list[str] = []
        other: list[str] = []

        async def matching_handler(event: HardwareDomainEvent) -> None:
            matching.append(event.event_id)

        async def other_handler(event: HardwareDomainEvent) -> None:
            other.append(event.event_id)

        await bus.subscribe("hardware.action.succeeded", matching_handler)
        await bus.subscribe("hardware.action.failed", other_handler)
        await bus.publish(_event())
        return matching, other

    matching, other = asyncio.run(scenario())
    assert matching == ["event-1"]
    assert other == []


def test_unsubscribe_stops_future_delivery_and_unknown_id_is_noop() -> None:
    async def scenario() -> list[str]:
        bus = InProcessEventBus()
        received: list[str] = []

        async def handler(event: HardwareDomainEvent) -> None:
            received.append(event.event_id)

        subscription_id = await bus.subscribe("hardware.action.succeeded", handler)
        await bus.unsubscribe(subscription_id)
        await bus.unsubscribe("missing")
        await bus.publish(_event())
        return received

    assert asyncio.run(scenario()) == []


def test_multiple_subscribers_run_and_one_failure_is_isolated() -> None:
    async def scenario() -> tuple[list[str], InProcessEventBus]:
        bus = InProcessEventBus()
        received: list[str] = []

        async def broken(event: HardwareDomainEvent) -> None:
            raise RuntimeError("consumer failed")

        async def healthy(event: HardwareDomainEvent) -> None:
            received.append(event.event_id)

        await bus.subscribe("hardware.action.succeeded", broken)
        await bus.subscribe("hardware.action.succeeded", healthy)
        await bus.publish(_event())
        return received, bus

    received, bus = asyncio.run(scenario())
    assert received == ["event-1"]
    assert len(bus.handler_failures) == 1
    assert str(bus.handler_failures[0].error) == "consumer failed"


def test_republish_is_at_least_once_compatible_and_deduplicating_consumer_runs_once() -> None:
    async def scenario() -> tuple[list[str], frozenset[str]]:
        bus = InProcessEventBus()
        side_effects: list[str] = []

        async def side_effect(event: HardwareDomainEvent) -> None:
            side_effects.append(event.event_id)

        deduplicated = DeduplicatingEventHandler(side_effect)
        await bus.subscribe("hardware.action.succeeded", deduplicated)
        event = _event()
        await bus.publish(event)
        await bus.publish(event)
        return side_effects, deduplicated.processed_event_ids

    side_effects, processed = asyncio.run(scenario())
    assert side_effects == ["event-1"]
    assert processed == {"event-1"}


def test_failed_deduplicating_consumer_can_retry_same_event() -> None:
    async def scenario() -> tuple[int, frozenset[str]]:
        attempts = 0

        async def flaky(event: HardwareDomainEvent) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient")

        handler = DeduplicatingEventHandler(flaky)
        event = _event()
        with pytest.raises(RuntimeError, match="transient"):
            await handler(event)
        await handler(event)
        return attempts, handler.processed_event_ids

    attempts, processed = asyncio.run(scenario())
    assert attempts == 2
    assert processed == {"event-1"}


def test_new_consumer_instance_does_not_claim_cross_restart_deduplication() -> None:
    async def scenario() -> list[str]:
        side_effects: list[str] = []

        async def side_effect(event: HardwareDomainEvent) -> None:
            side_effects.append(event.event_id)

        event = _event()
        await DeduplicatingEventHandler(side_effect)(event)
        await DeduplicatingEventHandler(side_effect)(event)
        return side_effects

    assert asyncio.run(scenario()) == ["event-1", "event-1"]


def test_create_event_assigns_monotonic_sequences_per_stream() -> None:
    async def scenario() -> tuple[list[int], list[int], list[int]]:
        bus = InProcessEventBus()
        first_device = [
            await bus.create_event(
                event_type="hardware.device.status_changed",
                device_id="device-1",
                payload={},
                source="registry",
            )
            for _ in range(3)
        ]
        second_device = [
            await bus.create_event(
                event_type="hardware.device.status_changed",
                device_id="device-2",
                payload={},
                source="registry",
            )
            for _ in range(2)
        ]
        global_events = [
            await bus.create_event(
                event_type="hardware.action.created",
                payload={},
                source="executor",
            )
            for _ in range(2)
        ]
        return (
            [event.runtime_sequence for event in first_device],
            [event.runtime_sequence for event in second_device],
            [event.runtime_sequence for event in global_events],
        )

    assert asyncio.run(scenario()) == ([0, 1, 2], [0, 1], [0, 1])


def test_publish_rejects_new_event_with_non_increasing_stream_sequence() -> None:
    async def scenario() -> None:
        bus = InProcessEventBus()
        await bus.publish(_event("event-2", sequence=2))
        with pytest.raises(ValueError, match="must increase"):
            await bus.publish(_event("event-1", sequence=1))

    asyncio.run(scenario())


def test_subscription_ids_are_unique() -> None:
    async def scenario() -> tuple[str, str]:
        bus = InProcessEventBus()

        async def handler(event: HardwareDomainEvent) -> None: ...

        return (
            await bus.subscribe("hardware.action.succeeded", handler),
            await bus.subscribe("hardware.action.succeeded", handler),
        )

    first, second = asyncio.run(scenario())
    assert first != second


def test_adapter_has_no_cross_process_broker_imports() -> None:
    tree = ast.parse(IMPLEMENTATION_PATH.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert not any(
        name == root or name.startswith(f"{root}.")
        for name in imported
        for root in ("redis", "kafka", "aiokafka", "pika", "nats")
    )
