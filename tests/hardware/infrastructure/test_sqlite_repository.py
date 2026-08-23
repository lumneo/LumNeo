from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumneo.hardware.domain.action import ActionResult
from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.ports.repository import HardwareRepository
from lumneo.infrastructure.database.sqlite import SQLiteConnectionFactory
from lumneo.infrastructure.hardware.persistence.unit_of_work import SQLiteHardwareUnitOfWork
from lumneo.persistence.models.hardware import HARDWARE_TABLES, SCHEMA_VERSION

from tests.hardware.execution.test_executor import NOW, _action, _composition


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def sqlite_database_path():
    with tempfile.TemporaryDirectory(prefix=".t32-", dir=PROJECT_ROOT) as directory:
        yield Path(directory) / "hardware.sqlite3"


def test_migration_creates_all_hardware_tables(sqlite_database_path: Path) -> None:
    factory = SQLiteConnectionFactory(sqlite_database_path)
    factory.initialize()
    connection = factory.connect()
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert SCHEMA_VERSION == 1
    assert set(HARDWARE_TABLES) <= tables


def test_repository_round_trips_every_contract_record(sqlite_database_path: Path) -> None:
    async def scenario():
        _, _, driver, _, capability = await _composition()
        device = (await driver.discover())[0]
        action = _action(capability.id, {"brightness": 45})
        result = ActionResult(
            action.action_id,
            ActionStatus.SUCCEEDED,
            {"brightness": 45, "on": False},
            None,
            NOW,
            NOW,
            True,
        )
        event = HardwareDomainEvent(
            "event-1",
            "hardware.action.succeeded",
            device.id,
            action.action_id,
            NOW,
            {"status": "succeeded"},
            1,
            None,
            None,
            "test",
        )
        factory = SQLiteConnectionFactory(sqlite_database_path)
        factory.initialize()
        async with SQLiteHardwareUnitOfWork(factory) as uow:
            repository = uow.repository
            assert isinstance(repository, HardwareRepository)
            await repository.save_device(device)
            await repository.save_capability(capability)
            await repository.save_action(action)
            await repository.save_result(result)
            await repository.save_approval({"action_id": action.action_id, "decision": "approved"})
            await repository.append_transition({"action_id": action.action_id, "to_status": "running"})
            await repository.append_transition({"action_id": action.action_id, "to_status": "succeeded"})
            await repository.append_event(event)
            await repository.append_reconciliation({"action_id": action.action_id, "evidence": "ref-1"})
            await repository.append_audit({"action_id": action.action_id, "decision": "succeeded"})
            reserved = await repository.reserve_idempotency_key(
                requester=action.requester,
                device_id=action.device_id,
                capability_id=action.capability_id,
                idempotency_key="key-1",
                parameters_digest=action.parameters_digest,
                action_id=action.action_id,
            )
            duplicate = await repository.reserve_idempotency_key(
                requester=action.requester,
                device_id=action.device_id,
                capability_id=action.capability_id,
                idempotency_key="key-1",
                parameters_digest=action.parameters_digest,
                action_id="other-action",
            )
        async with SQLiteHardwareUnitOfWork(factory) as uow:
            repository = uow.repository
            record = await repository.get_action_record(action.action_id)
            return (
                await repository.get_device(device.id),
                await repository.list_devices(),
                await repository.get_capability(capability.id),
                await repository.list_capabilities(device.id),
                await repository.get_action(action.action_id),
                await repository.get_result(action.action_id),
                await repository.get_action_by_idempotency_key(
                    requester=action.requester,
                    device_id=action.device_id,
                    capability_id=action.capability_id,
                    idempotency_key="key-1",
                ),
                record,
                reserved,
                duplicate,
            )

    device, devices, capability, capabilities, action, result, keyed, record, reserved, duplicate = asyncio.run(scenario())
    assert devices == [device]
    assert capabilities == [capability]
    assert keyed == action
    assert result is not None and result.status is ActionStatus.SUCCEEDED
    assert reserved is True and duplicate is False
    assert record is not None
    assert len(record["approvals"]) == 1
    assert len(record["transitions"]) == 2
    assert len(record["events"]) == 1
    assert len(record["reconciliations"]) == 1
    assert len(record["audits"]) == 1


def test_unit_of_work_commits_success_and_rolls_back_failure(sqlite_database_path: Path) -> None:
    async def scenario():
        factory = SQLiteConnectionFactory(sqlite_database_path)
        factory.initialize()
        committed = _action("capability-1", {}, action_id="committed")
        rolled_back = _action("capability-1", {}, action_id="rolled-back")
        async with SQLiteHardwareUnitOfWork(factory) as uow:
            await uow.repository.save_action(committed)
        with pytest.raises(RuntimeError, match="force rollback"):
            async with SQLiteHardwareUnitOfWork(factory) as uow:
                await uow.repository.save_action(rolled_back)
                raise RuntimeError("force rollback")
        async with SQLiteHardwareUnitOfWork(factory) as uow:
            return (
                await uow.repository.get_action("committed"),
                await uow.repository.get_action("rolled-back"),
            )

    committed, rolled_back = asyncio.run(scenario())
    assert committed is not None
    assert rolled_back is None
