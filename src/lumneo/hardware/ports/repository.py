"""Hardware persistence Port; concrete database mechanics live outside Domain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from ..domain.action import ActionResult, HardwareAction
from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.event import HardwareDomainEvent


Record = Mapping[str, object]


@runtime_checkable
class HardwareRepository(Protocol):
    async def save_device(self, device: Device) -> None: ...

    async def get_device(self, device_id: str) -> Device | None: ...

    async def list_devices(self) -> list[Device]: ...

    async def save_capability(self, capability: Capability) -> None: ...

    async def get_capability(self, capability_id: str) -> Capability | None: ...

    async def list_capabilities(self, device_id: str) -> list[Capability]: ...

    async def save_action(self, action: HardwareAction) -> None: ...

    async def get_action(self, action_id: str) -> HardwareAction | None: ...

    async def save_result(self, result: ActionResult) -> None: ...

    async def get_result(self, action_id: str) -> ActionResult | None: ...

    async def save_approval(self, approval: Record) -> None: ...

    async def list_approvals(self, action_id: str) -> list[Record]: ...

    async def append_transition(self, transition: Record) -> None: ...

    async def append_event(self, event: HardwareDomainEvent) -> None: ...

    async def append_reconciliation(self, reconciliation: Record) -> None: ...

    async def append_audit(self, audit: Record) -> None: ...

    async def list_audits(self, action_id: str) -> list[Record]: ...

    async def reserve_idempotency_key(
        self,
        *,
        requester: str,
        device_id: str,
        capability_id: str,
        idempotency_key: str,
        parameters_digest: str,
        action_id: str,
    ) -> bool: ...

    async def get_action_by_idempotency_key(
        self,
        *,
        requester: str,
        device_id: str,
        capability_id: str,
        idempotency_key: str,
    ) -> HardwareAction | None: ...

    async def get_action_record(self, action_id: str) -> Record | None: ...


__all__ = ("HardwareRepository", "Record")
