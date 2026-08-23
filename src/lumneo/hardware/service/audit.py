"""Append-only Hardware action audit with recursive sensitive-data redaction."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from ..domain.action import ActionResult, HardwareAction
from ..ports.repository import HardwareRepository


REDACTED = "[REDACTED]"
FALLBACK_SENSITIVE_NAMES = frozenset(
    {"password", "secret", "token", "api_key", "credential", "latitude", "longitude"}
)


class SensitiveRedactor:
    def redact(
        self,
        value: object,
        schema: dict[str, object] | None = None,
    ) -> object:
        if schema is not None and schema.get("x-sensitive") is True:
            return REDACTED
        if isinstance(value, (bytes, bytearray, memoryview)):
            content = bytes(value)
            digest = hashlib.sha256(content).hexdigest()
            return {
                "content_ref": f"sha256:{digest}",
                "checksum": f"sha256:{digest}",
                "size": len(content),
            }
        if isinstance(value, dict):
            properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
            if not isinstance(properties, dict):
                properties = {}
            redacted: dict[str, object] = {}
            for key, nested in value.items():
                normalized = key.casefold()
                if normalized in FALLBACK_SENSITIVE_NAMES:
                    redacted[key] = REDACTED
                    continue
                nested_schema = properties.get(key)
                redacted[key] = self.redact(
                    nested,
                    nested_schema if isinstance(nested_schema, dict) else None,
                )
            return redacted
        if isinstance(value, (list, tuple)):
            items = schema.get("items") if isinstance(schema, dict) else None
            item_schema = items if isinstance(items, dict) else None
            return [self.redact(item, item_schema) for item in value]
        return value


class AuditService:
    def __init__(
        self,
        repository: HardwareRepository,
        *,
        redactor: SensitiveRedactor | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._redactor = redactor or SensitiveRedactor()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def record(self, action: HardwareAction, result: ActionResult) -> None:
        capability = await self._repository.get_capability(action.capability_id)
        input_schema = capability.input_schema if capability is not None else None
        output_schema = capability.output_schema if capability is not None else None
        await self._repository.append_audit(
            {
                "audit_id": self._id_factory(),
                "action_id": action.action_id,
                "requester": action.requester,
                "device_id": action.device_id,
                "capability_id": action.capability_id,
                "effective_risk": capability.risk_level.value if capability else None,
                "decision": result.status.value,
                "parameters": self._redactor.redact(action.parameters, input_schema),
                "output": self._redactor.redact(result.output, output_schema),
                "error": (
                    {
                        "code": result.error.code,
                        "retryable": result.error.retryable,
                        "details": self._redactor.redact(result.error.details),
                    }
                    if result.error is not None
                    else None
                ),
                "timestamp": self._clock().isoformat(),
            }
        )


__all__ = ("AuditService", "FALLBACK_SENSITIVE_NAMES", "REDACTED", "SensitiveRedactor")
