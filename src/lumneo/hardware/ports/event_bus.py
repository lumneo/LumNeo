"""Process-independent EventBus abstraction owned by Hardware OS."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from ..domain.event import HardwareDomainEvent


EventHandler = Callable[[HardwareDomainEvent], Awaitable[None]]


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, event: HardwareDomainEvent) -> None: ...

    async def subscribe(self, event_type: str, handler: EventHandler) -> str: ...

    async def unsubscribe(self, subscription_id: str) -> None: ...


__all__ = ("EventBus", "EventHandler")
