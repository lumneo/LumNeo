from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from lumneo.hardware.domain.action import ActionResult
from lumneo.hardware.domain.enums import ActionStatus
from lumneo.hardware.domain.errors import HardwareError
from lumneo.hardware.service.audit import AuditService, REDACTED, SensitiveRedactor
from lumneo.infrastructure.hardware.persistence.in_memory_repository import InMemoryHardwareRepository

from tests.hardware.execution.test_executor import NOW, _action, _composition


def test_schema_and_fallback_sensitive_fields_are_recursively_redacted() -> None:
    async def scenario():
        repository = InMemoryHardwareRepository()
        _, _, _, _, base = await _composition()
        capability = replace(
            base,
            input_schema={
                "type": "object",
                "properties": {
                    "private_note": {"type": "string", "x-sensitive": True},
                    "nested": {
                        "type": "object",
                        "properties": {"safe": {"type": "string"}},
                    },
                },
            },
        )
        await repository.save_capability(capability)
        action = _action(
            capability.id,
            {
                "private_note": "schema-secret",
                "password": "fallback-secret",
                "nested": {"token": "nested-secret", "safe": "visible"},
                "latitude": 31.2,
                "longitude": 121.5,
            },
        )
        result = ActionResult(
            action.action_id,
            ActionStatus.FAILED,
            None,
            HardwareError(
                "DRIVER_ERROR",
                "free-form message contains schema-secret",
                False,
                {"token": "error-secret", "safe": "visible"},
            ),
            None,
            NOW,
            False,
        )
        service = AuditService(
            repository,
            clock=lambda: NOW,
            id_factory=lambda: "audit-1",
        )
        await service.record(action, result)
        return (await repository.list_audits(action.action_id))[0]

    audit = asyncio.run(scenario())
    parameters = audit["parameters"]
    assert parameters["private_note"] == REDACTED
    assert parameters["password"] == REDACTED
    assert parameters["nested"]["token"] == REDACTED
    assert parameters["nested"]["safe"] == "visible"
    assert parameters["latitude"] == parameters["longitude"] == REDACTED
    serialized = json.dumps(audit)
    assert audit["error"]["details"] == {"token": REDACTED, "safe": "visible"}
    assert "message" not in audit["error"]
    for secret in (
        "schema-secret",
        "fallback-secret",
        "nested-secret",
        "error-secret",
    ):
        assert secret not in serialized


def test_binary_content_becomes_reference_checksum_and_size() -> None:
    redacted = SensitiveRedactor().redact({"firmware": b"binary-secret-content"})
    binary = redacted["firmware"]
    assert binary["content_ref"].startswith("sha256:")
    assert binary["checksum"] == binary["content_ref"]
    assert binary["size"] == len(b"binary-secret-content")
    assert b"binary-secret-content" not in repr(redacted).encode()


def test_audit_and_transition_histories_are_append_only_and_detached() -> None:
    async def scenario():
        repository = InMemoryHardwareRepository()
        await repository.save_action(_action("capability-1", {}))
        first = {"action_id": "action-1", "decision": "created"}
        await repository.append_audit(first)
        first["decision"] = "tampered"
        await repository.append_audit({"action_id": "action-1", "decision": "failed"})
        await repository.append_transition({"action_id": "action-1", "to_status": "validating"})
        await repository.append_transition({"action_id": "action-1", "to_status": "failed"})
        audits = await repository.list_audits("action-1")
        audits[0]["decision"] = "caller-mutated"
        return await repository.list_audits("action-1"), await repository.get_action_record("action-1")

    audits, record = asyncio.run(scenario())
    assert [item["decision"] for item in audits] == ["created", "failed"]
    assert record is not None
    assert [item["to_status"] for item in record["transitions"]] == [
        "validating",
        "failed",
    ]


def test_executor_writes_one_audit_for_success_and_validation_failure() -> None:
    async def execute(parameters: dict[str, object]):
        executor, repository, _, _, capability = await _composition()
        executor._audit_writer = AuditService(
            repository,
            clock=lambda: NOW,
            id_factory=lambda: "audit-1",
        )
        result = await executor.execute(_action(capability.id, parameters))
        return result, await repository.list_audits("action-1")

    succeeded, success_audits = asyncio.run(execute({"brightness": 20}))
    failed, failure_audits = asyncio.run(execute({"brightness": 101}))
    assert succeeded.status is ActionStatus.SUCCEEDED
    assert failed.status is ActionStatus.FAILED
    assert len(success_audits) == len(failure_audits) == 1
    assert success_audits[0]["decision"] == "succeeded"
    assert failure_audits[0]["decision"] == "failed"
