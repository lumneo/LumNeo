"""The only stable public entry point into Hardware OS."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import uuid4

from ..domain.action import PHYSICAL_ACTION_KIND, HardwareAction
from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.enums import ActionStatus, DeviceStatus
from ..execution.executor import ActionExecutor
from ..ports.repository import HardwareRepository, Record
from ..service.approval import ApprovalService
from ..service.capability_registry import CapabilityRegistry
from ..service.device_registry import DeviceRegistry


class HardwareFacade:
    def __init__(
        self,
        *,
        device_registry: DeviceRegistry,
        capability_registry: CapabilityRegistry,
        executor: ActionExecutor,
        approval_service: ApprovalService,
        repository: HardwareRepository,
        clock: Callable[[], datetime] | None = None,
        action_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._device_registry = device_registry
        self._capability_registry = capability_registry
        self._executor = executor
        self._approval_service = approval_service
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._action_id_factory = action_id_factory or (lambda: str(uuid4()))

    async def list_devices(
        self,
        *,
        status: DeviceStatus | None = None,
        type: str | None = None,
    ) -> list[Device]:
        return self._device_registry.list(status=status, type=type)

    async def get_device(self, device_id: str) -> Device:
        device = self._device_registry.get(device_id)
        if device is None:
            raise KeyError(f"Device not found: {device_id}")
        return device

    async def list_capabilities(self, device_id: str) -> list[Capability]:
        await self.get_device(device_id)
        return self._capability_registry.list(device_id=device_id)

    async def submit_action(
        self,
        *,
        device_id: str,
        capability_id: str,
        parameters: dict[str, object],
        requester: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        context_ref: dict[str, str] | None = None,
        timeout_ms: int | None = None,
    ) -> HardwareAction:
        capability = self._capability_registry.get(capability_id)
        effective_timeout = timeout_ms or (capability.timeout_ms if capability else 1_000)
        now = self._clock()
        action = HardwareAction(
            action_id=self._action_id_factory(),
            action_kind=PHYSICAL_ACTION_KIND,
            device_id=device_id,
            capability_id=capability_id,
            parameters=parameters,
            requester=requester,
            status=ActionStatus.CREATED,
            idempotency_key=idempotency_key,
            timeout_ms=effective_timeout,
            correlation_id=correlation_id,
            context_ref=context_ref,
            expected_device_version=None,
            parameters_digest=self._parameters_digest(parameters),
            approval_expires_at=None,
            created_at=now,
            updated_at=now,
        )
        result = await self._executor.execute(action)
        stored = await self._repository.get_action(result.action_id)
        if stored is None:
            raise RuntimeError("Executor returned an action that was not persisted")
        return stored

    async def approve_action(self, action_id: str, approver: str) -> HardwareAction:
        action, device, capability = await self._approval_context(action_id)
        await self._approval_service.approve(
            action,
            device,
            capability,
            approver=approver,
        )
        await self._executor.resume_approved(
            action_id,
            approval_validator=self._approval_service,
        )
        return await self.get_action(action_id)

    async def reject_action(
        self,
        action_id: str,
        approver: str,
        reason: str,
    ) -> HardwareAction:
        action, device, capability = await self._approval_context(action_id)
        await self._approval_service.reject(
            action,
            device,
            capability,
            approver=approver,
            reason=reason,
        )
        await self._executor.resume_approved(
            action_id,
            approval_validator=self._approval_service,
        )
        return await self.get_action(action_id)

    async def cancel_action(self, action_id: str, requester: str) -> HardwareAction:
        await self._executor.cancel(action_id, requester=requester)
        return await self.get_action(action_id)

    async def get_action(self, action_id: str) -> HardwareAction:
        action = await self._repository.get_action(action_id)
        if action is None:
            raise KeyError(f"Action not found: {action_id}")
        return action

    async def get_action_record(self, action_id: str) -> Record:
        record = await self._repository.get_action_record(action_id)
        if record is None:
            raise KeyError(f"Action not found: {action_id}")
        return record

    async def _approval_context(
        self,
        action_id: str,
    ) -> tuple[HardwareAction, Device, Capability]:
        action = await self.get_action(action_id)
        device = await self._repository.get_device(action.device_id)
        capability = await self._repository.get_capability(action.capability_id)
        if device is None or capability is None:
            raise KeyError("Approval target no longer exists")
        return action, device, capability

    @staticmethod
    def _parameters_digest(parameters: Mapping[str, object]) -> str:
        canonical = json.dumps(
            dict(parameters),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


__all__ = ("HardwareFacade",)
