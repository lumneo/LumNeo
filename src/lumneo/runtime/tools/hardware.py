"""Thin Runtime mapping for the single Phase 0 ``hardware.execute`` tool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from lumneo.hardware.facade import HardwareFacade


HARDWARE_EXECUTE_TOOL_NAME = "hardware.execute"
HARDWARE_EXECUTE_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "device_id": {"type": "string", "minLength": 1},
        "capability_id": {"type": "string", "minLength": 1},
        "parameters": {"type": "object"},
        "requester": {"type": "string", "minLength": 1},
        "idempotency_key": {"type": ["string", "null"]},
        "correlation_id": {"type": ["string", "null"]},
        "context_ref": {"type": ["object", "null"]},
        "timeout_ms": {"type": ["integer", "null"], "minimum": 1},
    },
    "required": ["device_id", "capability_id", "parameters", "requester"],
    "additionalProperties": False,
}


ToolHandler = Callable[[Mapping[str, object]], Awaitable[dict[str, object]]]


class RuntimeToolRegistry(Protocol):
    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        input_schema: Mapping[str, object],
    ) -> None: ...


class HardwareExecuteTool:
    name = HARDWARE_EXECUTE_TOOL_NAME
    input_schema = HARDWARE_EXECUTE_INPUT_SCHEMA

    def __init__(self, facade: HardwareFacade) -> None:
        self._facade = facade

    async def invoke(self, payload: Mapping[str, object]) -> dict[str, object]:
        values = self._validate_envelope(payload)
        action = await self._facade.submit_action(**values)
        record = await self._facade.get_action_record(action.action_id)
        return _serialize_record(record)

    @staticmethod
    def _validate_envelope(payload: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(payload, Mapping):
            raise TypeError("hardware.execute input must be an object")
        allowed = set(HARDWARE_EXECUTE_INPUT_SCHEMA["properties"])
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unknown hardware.execute fields: {sorted(unknown)}")
        required = {"device_id", "capability_id", "parameters", "requester"}
        missing = required - set(payload)
        if missing:
            raise ValueError(f"Missing hardware.execute fields: {sorted(missing)}")
        for field in ("device_id", "capability_id", "requester"):
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        parameters = payload["parameters"]
        if not isinstance(parameters, dict):
            raise TypeError("parameters must be an object")
        return dict(payload)


def register_hardware_tool(
    registry: RuntimeToolRegistry,
    facade: HardwareFacade,
) -> HardwareExecuteTool:
    tool = HardwareExecuteTool(facade)
    registry.register(tool.name, tool.invoke, input_schema=tool.input_schema)
    return tool


def _serialize(value: object) -> object:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _serialize(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _serialize(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _serialize_record(record: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _serialize(value) for key, value in record.items()}


__all__ = (
    "HARDWARE_EXECUTE_INPUT_SCHEMA",
    "HARDWARE_EXECUTE_TOOL_NAME",
    "HardwareExecuteTool",
    "RuntimeToolRegistry",
    "register_hardware_tool",
)
