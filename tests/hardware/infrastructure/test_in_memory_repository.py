from __future__ import annotations

import asyncio
import ast
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from lumneo.hardware.domain.action import (
    PHYSICAL_ACTION_KIND,
    ActionResult,
    HardwareAction,
)
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import (
    ActionStatus,
    DeviceStatus,
    IdempotencyMode,
    RiskLevel,
)
from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.ports.repository import HardwareRepository
from lumneo.infrastructure.hardware.persistence.in_memory_repository import (
    InMemoryHardwareRepository,
)


NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
IMPLEMENTATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "lumneo"
    / "infrastructure"
    / "hardware"
    / "persistence"
    / "in_memory_repository.py"
)


def _device(**changes: object) -> Device:
    values: dict[str, object] = {
        "id": "device-1",
        "type": "light",
        "name": "Light",
        "status": DeviceStatus.ONLINE,
        "capability_ids": (),
        "driver_id": "simulated",
        "metadata": {"room": "office"},
        "last_seen_at": NOW,
        "version": 0,
    }
    values.update(changes)
    return Device(**values)  # type: ignore[arg-type]


def _capability() -> Capability:
    return Capability(
        id="device-1.turn_on",
        device_id="device-1",
        operation="turn_on",
        description="Turn on",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        schema_version="1.0.0",
        revision=0,
        risk_level=RiskLevel.LOW,
        idempotency=IdempotencyMode.IDEMPOTENT,
        timeout_ms=1_000,
        enabled=True,
    )


def _action(**changes: object) -> HardwareAction:
    values: dict[str, object] = {
        "action_id": "action-1",
        "action_kind": PHYSICAL_ACTION_KIND,
        "device_id": "device-1",
        "capability_id": "device-1.turn_on",
        "parameters": {},
        "requester": "test",
        "status": ActionStatus.CREATED,
        "idempotency_key": None,
        "timeout_ms": 1_000,
        "correlation_id": None,
        "context_ref": None,
        "expected_device_version": None,
        "parameters_digest": "sha256:empty",
        "approval_expires_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return HardwareAction(**values)  # type: ignore[arg-type]


def test_adapter_structurally_conforms_to_hardware_repository() -> None:
    assert isinstance(InMemoryHardwareRepository(), HardwareRepository)


def test_device_save_get_update_and_list_are_deterministic() -> None:
    repository = InMemoryHardwareRepository()
    original = _device()
    asyncio.run(repository.save_device(original))

    assert asyncio.run(repository.get_device(original.id)) == original
    assert asyncio.run(repository.list_devices()) == [original]

    updated = replace(original, status=DeviceStatus.DEGRADED, version=1)
    asyncio.run(repository.save_device(updated))
    assert asyncio.run(repository.get_device(original.id)) == updated
    assert asyncio.run(repository.list_devices()) == [updated]


def test_action_save_get_and_update() -> None:
    repository = InMemoryHardwareRepository()
    action = _action()
    asyncio.run(repository.save_action(action))
    assert asyncio.run(repository.get_action(action.action_id)) == action

    running = replace(action, status=ActionStatus.RUNNING)
    asyncio.run(repository.save_action(running))
    assert asyncio.run(repository.get_action(action.action_id)) == running


def test_missing_objects_return_none_and_empty_lists() -> None:
    repository = InMemoryHardwareRepository()

    assert asyncio.run(repository.get_device("missing")) is None
    assert asyncio.run(repository.get_capability("missing")) is None
    assert asyncio.run(repository.get_action("missing")) is None
    assert asyncio.run(repository.get_result("missing")) is None
    assert asyncio.run(repository.get_action_record("missing")) is None
    assert asyncio.run(repository.list_devices()) == []
    assert asyncio.run(repository.list_capabilities("missing")) == []


def test_repository_detaches_saved_and_returned_domain_objects() -> None:
    repository = InMemoryHardwareRepository()
    device = _device()
    asyncio.run(repository.save_device(device))

    device.metadata["room"] = "lab"
    first_read = asyncio.run(repository.get_device(device.id))
    assert first_read is not None
    first_read.metadata["room"] = "garage"
    second_read = asyncio.run(repository.get_device(device.id))

    assert second_read is not None
    assert second_read.metadata == {"room": "office"}


def test_repository_instances_are_isolated() -> None:
    first = InMemoryHardwareRepository()
    second = InMemoryHardwareRepository()
    asyncio.run(first.save_device(_device()))

    assert asyncio.run(first.get_device("device-1")) is not None
    assert asyncio.run(second.get_device("device-1")) is None


def test_capability_and_result_round_trip() -> None:
    repository = InMemoryHardwareRepository()
    capability = _capability()
    result = ActionResult(
        "action-1",
        ActionStatus.SUCCEEDED,
        {"on": True},
        None,
        NOW,
        NOW,
        True,
    )
    asyncio.run(repository.save_capability(capability))
    asyncio.run(repository.save_result(result))

    assert asyncio.run(repository.get_capability(capability.id)) == capability
    assert asyncio.run(repository.list_capabilities("device-1")) == [capability]
    assert asyncio.run(repository.get_result("action-1")) == result


def test_append_records_are_available_in_complete_action_record() -> None:
    repository = InMemoryHardwareRepository()
    action = _action(status=ActionStatus.FAILED)
    asyncio.run(repository.save_action(action))
    asyncio.run(repository.save_approval({"action_id": "action-1", "decision": "approved"}))
    asyncio.run(repository.append_transition({"action_id": "action-1", "to_status": "failed"}))
    asyncio.run(
        repository.append_event(
            HardwareDomainEvent(
                "event-1",
                "hardware.action.failed",
                "device-1",
                "action-1",
                NOW,
                {},
                1,
                None,
                None,
                "test",
            )
        )
    )
    asyncio.run(repository.append_reconciliation({"action_id": "action-1", "outcome": "failed"}))

    record = asyncio.run(repository.get_action_record("action-1"))

    assert record is not None
    assert record["action"] == action
    assert len(record["approvals"]) == 1  # type: ignore[arg-type]
    assert len(record["transitions"]) == 1  # type: ignore[arg-type]
    assert len(record["events"]) == 1  # type: ignore[arg-type]
    assert len(record["reconciliations"]) == 1  # type: ignore[arg-type]


def test_idempotency_reservation_is_scoped_and_returns_original_action() -> None:
    repository = InMemoryHardwareRepository()
    action = _action(idempotency_key="key-1")
    asyncio.run(repository.save_action(action))
    scope = {
        "requester": action.requester,
        "device_id": action.device_id,
        "capability_id": action.capability_id,
        "idempotency_key": "key-1",
    }

    first = asyncio.run(
        repository.reserve_idempotency_key(
            **scope,
            parameters_digest=action.parameters_digest,
            action_id=action.action_id,
        )
    )
    second = asyncio.run(
        repository.reserve_idempotency_key(
            **scope,
            parameters_digest=action.parameters_digest,
            action_id="action-2",
        )
    )

    assert first is True
    assert second is False
    assert asyncio.run(repository.get_action_by_idempotency_key(**scope)) == action


def test_adapter_has_no_sqlite_or_orm_imports() -> None:
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

    assert not any(name == "sqlite3" or name.startswith("sqlalchemy") for name in imported)
