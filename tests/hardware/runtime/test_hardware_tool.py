from __future__ import annotations

import asyncio
from itertools import count

import pytest

from lumneo.hardware.bootstrap import build_simulated_hardware_facade
from lumneo.runtime.tools.hardware import (
    HARDWARE_EXECUTE_TOOL_NAME,
    HardwareExecuteTool,
    register_hardware_tool,
)

from tests.hardware.execution.test_executor import NOW


def _ids():
    sequence = count(1)
    return lambda: f"tool-action-{next(sequence)}"


class FakeToolRegistry:
    def __init__(self) -> None:
        self.registrations = {}

    def register(self, name, handler, *, input_schema) -> None:
        self.registrations[name] = (handler, input_schema)


def test_hardware_execute_registers_single_thin_tool() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        registry = FakeToolRegistry()
        tool = register_hardware_tool(registry, facade)
        return tool, registry

    tool, registry = asyncio.run(scenario())
    assert tool.name == HARDWARE_EXECUTE_TOOL_NAME == "hardware.execute"
    assert set(registry.registrations) == {"hardware.execute"}
    assert "action_kind" not in tool.input_schema["properties"]
    assert "operation" not in tool.input_schema["properties"]


def test_tool_success_returns_traceable_action_result_event_and_audit() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        return await HardwareExecuteTool(facade).invoke(
            {
                "device_id": "simulated-light-01",
                "capability_id": "simulated-light-01.set_brightness",
                "parameters": {"brightness": 42},
                "requester": "agent-1",
                "correlation_id": "turn-1",
            }
        )

    output = asyncio.run(scenario())
    assert output["action"]["status"] == "succeeded"
    assert output["result"]["output"] == {"on": False, "brightness": 42}
    assert len(output["events"]) == 1
    assert len(output["audits"]) == 1


def test_capability_invalid_parameters_surface_without_second_validation_policy() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        return await HardwareExecuteTool(facade).invoke(
            {
                "device_id": "simulated-light-01",
                "capability_id": "simulated-light-01.set_brightness",
                "parameters": {"brightness": 101},
                "requester": "agent-1",
            }
        )

    output = asyncio.run(scenario())
    assert output["action"]["status"] == "failed"
    assert output["result"]["error"]["code"] == "INVALID_PARAMETERS"


def test_approval_required_is_returned_without_driver_execution() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            low_auto_approve=False,
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        return await HardwareExecuteTool(facade).invoke(
            {
                "device_id": "simulated-light-01",
                "capability_id": "simulated-light-01.turn_on",
                "parameters": {},
                "requester": "agent-1",
            }
        )

    output = asyncio.run(scenario())
    assert output["action"]["status"] == "awaiting_approval"
    assert output["result"]["error"]["code"] == "APPROVAL_REQUIRED"
    assert all(item["to_status"] != "running" for item in output["transitions"])


def test_tool_envelope_rejects_compile_build_simulate_and_unknown_fields() -> None:
    async def scenario():
        facade = await build_simulated_hardware_facade(
            clock=lambda: NOW,
            action_id_factory=_ids(),
        )
        tool = HardwareExecuteTool(facade)
        with pytest.raises(ValueError, match="Unknown"):
            await tool.invoke(
                {
                    "device_id": "simulated-light-01",
                    "capability_id": "simulated-light-01.turn_on",
                    "parameters": {},
                    "requester": "agent-1",
                    "operation": "compile",
                }
            )

    asyncio.run(scenario())
