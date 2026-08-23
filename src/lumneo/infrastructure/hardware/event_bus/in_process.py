"""Phase 0 process-local, at-least-once-compatible Hardware EventBus."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from lumneo.hardware.domain.event import HardwareDomainEvent, new_domain_event
from lumneo.hardware.ports.event_bus import EventHandler


@dataclass(frozen=True, slots=True)
class HandlerFailure:
    subscription_id: str
    event_id: str
    error: Exception


class InProcessEventBus:
    """In-memory bus with failure isolation and process-lifetime sequence state.

    The bus deliberately provides no cross-process or cross-restart durability.
    Re-publishing an event is permitted; consumers that cause side effects must use
    ``DeduplicatingEventHandler`` or equivalent durable consumer-owned tracking.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, tuple[str, EventHandler]] = {}
        self._subscription_lock = asyncio.Lock()
        self._sequence_lock = asyncio.Lock()
        self._allocated_sequences: dict[str, int] = {}
        self._published_sequences: dict[str, int] = {}
        self._published_event_positions: dict[str, tuple[str, int]] = {}
        self._handler_failures: list[HandlerFailure] = []

    @property
    def handler_failures(self) -> tuple[HandlerFailure, ...]:
        return tuple(self._handler_failures)

    async def create_event(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        source: str,
        device_id: str | None = None,
        action_id: str | None = None,
        source_sequence: int | None = None,
        correlation_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> HardwareDomainEvent:
        stream = self._stream_key(device_id=device_id, source=source)
        async with self._sequence_lock:
            sequence = self._allocated_sequences.get(stream, -1) + 1
            self._allocated_sequences[stream] = sequence
        return new_domain_event(
            event_type=event_type,
            device_id=device_id,
            action_id=action_id,
            timestamp=timestamp,
            payload=payload,
            runtime_sequence=sequence,
            source_sequence=source_sequence,
            correlation_id=correlation_id,
            source=source,
        )

    async def publish(self, event: HardwareDomainEvent) -> None:
        if not isinstance(event, HardwareDomainEvent):
            raise TypeError("event must be a HardwareDomainEvent")
        await self._accept_sequence(event)

        async with self._subscription_lock:
            subscriptions = tuple(
                (subscription_id, handler)
                for subscription_id, (event_type, handler) in self._subscriptions.items()
                if event_type == event.event_type
            )

        if not subscriptions:
            return
        results = await asyncio.gather(
            *(handler(event) for _, handler in subscriptions),
            return_exceptions=True,
        )
        for (subscription_id, _), result in zip(subscriptions, results, strict=True):
            if isinstance(result, BaseException):
                error = result if isinstance(result, Exception) else RuntimeError(str(result))
                self._handler_failures.append(
                    HandlerFailure(subscription_id, event.event_id, error)
                )

    async def subscribe(self, event_type: str, handler: EventHandler) -> str:
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        subscription_id = str(uuid4())
        async with self._subscription_lock:
            self._subscriptions[subscription_id] = (event_type, handler)
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        async with self._subscription_lock:
            self._subscriptions.pop(subscription_id, None)

    async def _accept_sequence(self, event: HardwareDomainEvent) -> None:
        stream = self._stream_key(device_id=event.device_id, source=event.source)
        position = (stream, event.runtime_sequence)
        async with self._sequence_lock:
            previous_position = self._published_event_positions.get(event.event_id)
            if previous_position is not None:
                if previous_position != position:
                    raise ValueError("event_id cannot be reused at a different sequence")
                return
            previous_sequence = self._published_sequences.get(stream, -1)
            if event.runtime_sequence <= previous_sequence:
                raise ValueError("runtime_sequence must increase within its event stream")
            self._published_sequences[stream] = event.runtime_sequence
            self._allocated_sequences[stream] = max(
                self._allocated_sequences.get(stream, -1),
                event.runtime_sequence,
            )
            self._published_event_positions[event.event_id] = position

    @staticmethod
    def _stream_key(*, device_id: str | None, source: str) -> str:
        return f"device:{device_id}" if device_id is not None else f"source:{source}"


class DeduplicatingEventHandler:
    """Process-local consumer wrapper that de-duplicates successful event IDs."""

    def __init__(self, handler: EventHandler) -> None:
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handler = handler
        self._processed_event_ids: set[str] = set()
        self._in_flight_event_ids: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def processed_event_ids(self) -> frozenset[str]:
        return frozenset(self._processed_event_ids)

    async def __call__(self, event: HardwareDomainEvent) -> None:
        async with self._lock:
            if (
                event.event_id in self._processed_event_ids
                or event.event_id in self._in_flight_event_ids
            ):
                return
            self._in_flight_event_ids.add(event.event_id)
        try:
            await self._handler(event)
        except BaseException:
            async with self._lock:
                self._in_flight_event_ids.discard(event.event_id)
            raise
        async with self._lock:
            self._in_flight_event_ids.discard(event.event_id)
            self._processed_event_ids.add(event.event_id)


__all__ = (
    "DeduplicatingEventHandler",
    "HandlerFailure",
    "InProcessEventBus",
)
