"""Authoritative Device-to-Capability relationship registry."""

from __future__ import annotations

from ..domain.capability import Capability
from .device_registry import DeviceRegistry


class CapabilityRegistry:
    def __init__(self, *, device_registry: DeviceRegistry) -> None:
        self._device_registry = device_registry
        self._capabilities: dict[str, Capability] = {}
        self._capability_ids_by_device: dict[str, list[str]] = {}

    def register(self, capability: Capability) -> None:
        if capability.id in self._capabilities:
            raise ValueError(f"capability already registered: {capability.id}")
        if self._device_registry.get(capability.device_id) is None:
            raise KeyError(f"device not registered: {capability.device_id}")

        self._capabilities[capability.id] = capability
        device_capabilities = self._capability_ids_by_device.setdefault(
            capability.device_id,
            [],
        )
        device_capabilities.append(capability.id)
        self._device_registry._replace_capability_snapshot(
            capability.device_id,
            tuple(device_capabilities),
        )

    def get(self, capability_id: str) -> Capability | None:
        return self._capabilities.get(capability_id)

    def list(self, *, device_id: str | None = None) -> list[Capability]:
        if device_id is None:
            return list(self._capabilities.values())
        capability_ids = self._capability_ids_by_device.get(device_id, ())
        return [self._capabilities[capability_id] for capability_id in capability_ids]

    def is_action_eligible(self, capability_id: str) -> bool:
        capability = self._require(capability_id)
        return capability.enabled and self._device_registry.is_action_eligible(
            capability.device_id
        )

    def _require(self, capability_id: str) -> Capability:
        capability = self.get(capability_id)
        if capability is None:
            raise KeyError(f"capability not registered: {capability_id}")
        return capability


__all__ = ("CapabilityRegistry",)
