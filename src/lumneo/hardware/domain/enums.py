"""Frozen Hardware OS domain enum definitions.

Values in this module are part of the v1.1.2 Hardware OS Contract. Adding,
removing, or changing a member is a contract change rather than an implementation
convenience.
"""

from enum import Enum, unique


@unique
class DeviceStatus(str, Enum):
    UNKNOWN = "unknown"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ONLINE = "online"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLED = "disabled"


@unique
class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@unique
class IdempotencyMode(str, Enum):
    IDEMPOTENT = "idempotent"
    KEY_REQUIRED = "key_required"
    NON_IDEMPOTENT = "non_idempotent"


@unique
class ActionStatus(str, Enum):
    CREATED = "created"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    RECONCILIATION_REQUIRED = "reconciliation_required"


__all__ = (
    "ActionStatus",
    "DeviceStatus",
    "IdempotencyMode",
    "RiskLevel",
)
