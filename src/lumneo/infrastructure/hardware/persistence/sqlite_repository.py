"""SQLite HardwareRepository mapping adapter; transaction-neutral by design."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime

from lumneo.hardware.domain.action import ActionResult, HardwareAction
from lumneo.hardware.domain.capability import Capability
from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus, IdempotencyMode, RiskLevel
from lumneo.hardware.domain.errors import HardwareError
from lumneo.hardware.domain.event import HardwareDomainEvent
from lumneo.hardware.ports.repository import Record


def _dump(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), separators=(",", ":"), sort_keys=True, allow_nan=False)


def _load(payload: str) -> dict[str, object]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("stored payload must be an object")
    return value


class SQLiteHardwareRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def save_device(self, device: Device) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO hardware_devices(id,payload) VALUES (?,?)",
            (device.id, _dump(device.to_dict())),
        )

    async def get_device(self, device_id: str) -> Device | None:
        row = self._connection.execute(
            "SELECT payload FROM hardware_devices WHERE id=?", (device_id,)
        ).fetchone()
        return self._device(_load(row["payload"])) if row else None

    async def list_devices(self) -> list[Device]:
        rows = self._connection.execute(
            "SELECT payload FROM hardware_devices ORDER BY id"
        ).fetchall()
        return [self._device(_load(row["payload"])) for row in rows]

    async def save_capability(self, capability: Capability) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO hardware_capabilities(id,device_id,payload) VALUES (?,?,?)",
            (capability.id, capability.device_id, _dump(capability.to_dict())),
        )

    async def get_capability(self, capability_id: str) -> Capability | None:
        row = self._connection.execute(
            "SELECT payload FROM hardware_capabilities WHERE id=?", (capability_id,)
        ).fetchone()
        return self._capability(_load(row["payload"])) if row else None

    async def list_capabilities(self, device_id: str) -> list[Capability]:
        rows = self._connection.execute(
            "SELECT payload FROM hardware_capabilities WHERE device_id=? ORDER BY id",
            (device_id,),
        ).fetchall()
        return [self._capability(_load(row["payload"])) for row in rows]

    async def save_action(self, action: HardwareAction) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO hardware_actions(action_id,payload) VALUES (?,?)",
            (action.action_id, _dump(action.to_dict())),
        )

    async def get_action(self, action_id: str) -> HardwareAction | None:
        row = self._connection.execute(
            "SELECT payload FROM hardware_actions WHERE action_id=?", (action_id,)
        ).fetchone()
        return self._action(_load(row["payload"])) if row else None

    async def save_result(self, result: ActionResult) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO hardware_action_results(action_id,payload) VALUES (?,?)",
            (result.action_id, _dump(result.to_dict())),
        )

    async def get_result(self, action_id: str) -> ActionResult | None:
        row = self._connection.execute(
            "SELECT payload FROM hardware_action_results WHERE action_id=?", (action_id,)
        ).fetchone()
        return self._result(_load(row["payload"])) if row else None

    async def save_approval(self, approval: Record) -> None:
        self._append_record("hardware_approvals", approval)

    async def list_approvals(self, action_id: str) -> list[Record]:
        return self._records("hardware_approvals", action_id)

    async def append_transition(self, transition: Record) -> None:
        self._append_record("hardware_action_transitions", transition)

    async def append_event(self, event: HardwareDomainEvent) -> None:
        self._connection.execute(
            "INSERT INTO hardware_events(event_id,action_id,payload) VALUES (?,?,?)",
            (event.event_id, event.action_id, _dump(event.to_dict())),
        )

    async def append_reconciliation(self, reconciliation: Record) -> None:
        self._append_record("hardware_reconciliations", reconciliation)

    async def append_audit(self, audit: Record) -> None:
        self._append_record("hardware_audits", audit)

    async def list_audits(self, action_id: str) -> list[Record]:
        return self._records("hardware_audits", action_id)

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
        try:
            self._connection.execute(
                "INSERT INTO hardware_idempotency_keys VALUES (?,?,?,?,?,?)",
                (
                    requester,
                    device_id,
                    capability_id,
                    idempotency_key,
                    parameters_digest,
                    action_id,
                ),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    async def get_action_by_idempotency_key(
        self,
        *,
        requester: str,
        device_id: str,
        capability_id: str,
        idempotency_key: str,
    ) -> HardwareAction | None:
        row = self._connection.execute(
            "SELECT action_id FROM hardware_idempotency_keys "
            "WHERE requester=? AND device_id=? AND capability_id=? AND idempotency_key=?",
            (requester, device_id, capability_id, idempotency_key),
        ).fetchone()
        return await self.get_action(row["action_id"]) if row else None

    async def get_action_record(self, action_id: str) -> Record | None:
        action = await self.get_action(action_id)
        if action is None:
            return None
        event_rows = self._connection.execute(
            "SELECT payload FROM hardware_events WHERE action_id=? ORDER BY sequence",
            (action_id,),
        ).fetchall()
        return {
            "action": action,
            "result": await self.get_result(action_id),
            "approvals": self._records("hardware_approvals", action_id),
            "transitions": self._records("hardware_action_transitions", action_id),
            "events": [self._event(_load(row["payload"])) for row in event_rows],
            "reconciliations": self._records("hardware_reconciliations", action_id),
            "audits": self._records("hardware_audits", action_id),
        }

    def _append_record(self, table: str, record: Record) -> None:
        if table not in {
            "hardware_approvals",
            "hardware_action_transitions",
            "hardware_reconciliations",
            "hardware_audits",
        }:
            raise ValueError("unsupported append-only table")
        action_id = record.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            raise ValueError("append-only record requires action_id")
        self._connection.execute(
            f"INSERT INTO {table}(action_id,payload) VALUES (?,?)",
            (action_id, _dump(record)),
        )

    def _records(self, table: str, action_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            f"SELECT payload FROM {table} WHERE action_id=? ORDER BY sequence",
            (action_id,),
        ).fetchall()
        return [_load(row["payload"]) for row in rows]

    @staticmethod
    def _device(value: dict[str, object]) -> Device:
        return Device(
            str(value["id"]), str(value["type"]), str(value["name"]),
            DeviceStatus(str(value["status"])), tuple(value["capability_ids"]),
            str(value["driver_id"]), dict(value["metadata"]),
            datetime.fromisoformat(str(value["last_seen_at"])) if value["last_seen_at"] else None,
            int(value["version"]),
        )

    @staticmethod
    def _capability(value: dict[str, object]) -> Capability:
        return Capability(
            str(value["id"]), str(value["device_id"]), str(value["operation"]),
            str(value["description"]), dict(value["input_schema"]),
            dict(value["output_schema"]), str(value["schema_version"]),
            int(value["revision"]), RiskLevel(str(value["risk_level"])),
            IdempotencyMode(str(value["idempotency"])), int(value["timeout_ms"]),
            bool(value["enabled"]),
        )

    @staticmethod
    def _action(value: dict[str, object]) -> HardwareAction:
        return HardwareAction(
            str(value["action_id"]), str(value["action_kind"]), str(value["device_id"]),
            str(value["capability_id"]), dict(value["parameters"]), str(value["requester"]),
            ActionStatus(str(value["status"])), value["idempotency_key"], int(value["timeout_ms"]),
            value["correlation_id"], value["context_ref"], value["expected_device_version"],
            str(value["parameters_digest"]),
            datetime.fromisoformat(str(value["approval_expires_at"])) if value["approval_expires_at"] else None,
            datetime.fromisoformat(str(value["created_at"])),
            datetime.fromisoformat(str(value["updated_at"])),
        )

    @staticmethod
    def _result(value: dict[str, object]) -> ActionResult:
        error_value = value["error"]
        error = None if error_value is None else HardwareError(
            str(error_value["code"]), str(error_value["message"]),
            bool(error_value["retryable"]), dict(error_value["details"]),
        )
        return ActionResult(
            str(value["action_id"]), ActionStatus(str(value["status"])),
            dict(value["output"]) if value["output"] is not None else None, error,
            datetime.fromisoformat(str(value["started_at"])) if value["started_at"] else None,
            datetime.fromisoformat(str(value["finished_at"])) if value["finished_at"] else None,
            bool(value["device_acknowledged"]),
        )

    @staticmethod
    def _event(value: dict[str, object]) -> HardwareDomainEvent:
        return HardwareDomainEvent(
            str(value["event_id"]), str(value["event_type"]), value["device_id"],
            value["action_id"], datetime.fromisoformat(str(value["timestamp"])),
            dict(value["payload"]), int(value["runtime_sequence"]),
            value["source_sequence"], value["correlation_id"], str(value["source"]),
        )


__all__ = ("SQLiteHardwareRepository",)
