"""Deterministic process-local HardwareRepository adapter for Phase 0 tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy

from lumneo.hardware.domain.action import ActionResult, HardwareAction
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.ports.repository import Record


IdempotencyScope = tuple[str, str, str, str]


class InMemoryHardwareRepository:
    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._capabilities: dict[str, Capability] = {}
        self._actions: dict[str, HardwareAction] = {}
        self._results: dict[str, ActionResult] = {}
        self._approvals: list[dict[str, object]] = []
        self._transitions: list[dict[str, object]] = []
        self._events: list[HardwareDomainEvent] = []
        self._reconciliations: list[dict[str, object]] = []
        self._audits: list[dict[str, object]] = []
        self._idempotency: dict[IdempotencyScope, tuple[str, str]] = {}
        self._idempotency_lock = asyncio.Lock()

    async def save_device(self, device: Device) -> None:
        self._devices[device.id] = deepcopy(device)

    async def get_device(self, device_id: str) -> Device | None:
        return deepcopy(self._devices.get(device_id))

    async def list_devices(self) -> list[Device]:
        return deepcopy(list(self._devices.values()))

    async def save_capability(self, capability: Capability) -> None:
        self._capabilities[capability.id] = deepcopy(capability)

    async def get_capability(self, capability_id: str) -> Capability | None:
        return deepcopy(self._capabilities.get(capability_id))

    async def list_capabilities(self, device_id: str) -> list[Capability]:
        return deepcopy(
            [
                capability
                for capability in self._capabilities.values()
                if capability.device_id == device_id
            ]
        )

    async def save_action(self, action: HardwareAction) -> None:
        self._actions[action.action_id] = deepcopy(action)

    async def get_action(self, action_id: str) -> HardwareAction | None:
        return deepcopy(self._actions.get(action_id))

    async def save_result(self, result: ActionResult) -> None:
        self._results[result.action_id] = deepcopy(result)

    async def get_result(self, action_id: str) -> ActionResult | None:
        return deepcopy(self._results.get(action_id))

    async def save_approval(self, approval: Record) -> None:
        self._approvals.append(self._copy_record(approval))

    async def list_approvals(self, action_id: str) -> list[Record]:
        return deepcopy(
            [record for record in self._approvals if record.get("action_id") == action_id]
        )

    async def append_transition(self, transition: Record) -> None:
        self._transitions.append(self._copy_record(transition))

    async def append_event(self, event: HardwareDomainEvent) -> None:
        self._events.append(deepcopy(event))

    async def append_reconciliation(self, reconciliation: Record) -> None:
        self._reconciliations.append(self._copy_record(reconciliation))

    async def append_audit(self, audit: Record) -> None:
        self._audits.append(self._copy_record(audit))

    async def list_audits(self, action_id: str) -> list[Record]:
        return deepcopy(
            [record for record in self._audits if record.get("action_id") == action_id]
        )

    async def reserve_idempotency_key(
        self,
        *,
        requester: str,
        device_id: str,
        capability_id: str,
        idempotency_key: str,
        parameters_digest: str,
        action_id: str,
    ) -> bool:
        scope = (requester, device_id, capability_id, idempotency_key)
        async with self._idempotency_lock:
            if scope in self._idempotency:
                return False
            self._idempotency[scope] = (parameters_digest, action_id)
            return True

    async def get_action_by_idempotency_key(
        self,
        *,
        requester: str,
        device_id: str,
        capability_id: str,
        idempotency_key: str,
    ) -> HardwareAction | None:
        scope = (requester, device_id, capability_id, idempotency_key)
        reservation = self._idempotency.get(scope)
        if reservation is None:
            return None
        _, action_id = reservation
        return await self.get_action(action_id)

    async def get_action_record(self, action_id: str) -> Record | None:
        action = self._actions.get(action_id)
        if action is None:
            return None
        return deepcopy(
            {
                "action": action,
                "result": self._results.get(action_id),
                "approvals": [
                    record
                    for record in self._approvals
                    if record.get("action_id") == action_id
                ],
                "transitions": [
                    record
                    for record in self._transitions
                    if record.get("action_id") == action_id
                ],
                "events": [event for event in self._events if event.action_id == action_id],
                "reconciliations": [
                    record
                    for record in self._reconciliations
                    if record.get("action_id") == action_id
                ],
                "audits": [
                    record
                    for record in self._audits
                    if record.get("action_id") == action_id
                ],
            }
        )

    @staticmethod
    def _copy_record(record: Mapping[str, object]) -> dict[str, object]:
        return deepcopy(dict(record))


__all__ = ("InMemoryHardwareRepository",)
