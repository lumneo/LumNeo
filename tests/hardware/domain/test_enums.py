from __future__ import annotations

import json
from enum import Enum

import pytest

from lumneo.hardware.domain import (
    ActionStatus,
    DeviceStatus,
    IdempotencyMode,
    RiskLevel,
)
from lumneo.hardware.domain.enums import (
    ActionStatus as DirectActionStatus,
)
from lumneo.hardware.domain.enums import (
    DeviceStatus as DirectDeviceStatus,
)
from lumneo.hardware.domain.enums import (
    IdempotencyMode as DirectIdempotencyMode,
)
from lumneo.hardware.domain.enums import RiskLevel as DirectRiskLevel


EXPECTED_MEMBERS = {
    DeviceStatus: (
        ("UNKNOWN", "unknown"),
        ("OFFLINE", "offline"),
        ("CONNECTING", "connecting"),
        ("ONLINE", "online"),
        ("DEGRADED", "degraded"),
        ("ERROR", "error"),
        ("DISABLED", "disabled"),
    ),
    RiskLevel: (
        ("READ_ONLY", "read_only"),
        ("LOW", "low"),
        ("MEDIUM", "medium"),
        ("HIGH", "high"),
        ("CRITICAL", "critical"),
    ),
    IdempotencyMode: (
        ("IDEMPOTENT", "idempotent"),
        ("KEY_REQUIRED", "key_required"),
        ("NON_IDEMPOTENT", "non_idempotent"),
    ),
    ActionStatus: (
        ("CREATED", "created"),
        ("VALIDATING", "validating"),
        ("AWAITING_APPROVAL", "awaiting_approval"),
        ("APPROVED", "approved"),
        ("RUNNING", "running"),
        ("SUCCEEDED", "succeeded"),
        ("FAILED", "failed"),
        ("REJECTED", "rejected"),
        ("TIMED_OUT", "timed_out"),
        ("CANCELLED", "cancelled"),
        ("RECONCILIATION_REQUIRED", "reconciliation_required"),
    ),
}


@pytest.mark.parametrize("enum_type", EXPECTED_MEMBERS)
def test_enum_members_and_values_match_contract_exactly(
    enum_type: type[Enum],
) -> None:
    actual = tuple((member.name, member.value) for member in enum_type)

    assert actual == EXPECTED_MEMBERS[enum_type]
    assert tuple(enum_type.__members__) == tuple(
        name for name, _ in EXPECTED_MEMBERS[enum_type]
    )


@pytest.mark.parametrize("enum_type", EXPECTED_MEMBERS)
def test_enum_is_a_string_enum(enum_type: type[Enum]) -> None:
    assert issubclass(enum_type, str)
    assert issubclass(enum_type, Enum)
    assert all(isinstance(member, str) for member in enum_type)


@pytest.mark.parametrize(
    "enum_type, expected_members",
    EXPECTED_MEMBERS.items(),
)
def test_every_member_serializes_to_its_exact_contract_string(
    enum_type: type[Enum],
    expected_members: tuple[tuple[str, str], ...],
) -> None:
    for name, value in expected_members:
        member = enum_type[name]

        assert json.dumps(member) == json.dumps(value)
        assert json.loads(json.dumps(member)) == value
        assert enum_type(value) is member


@pytest.mark.parametrize("enum_type", EXPECTED_MEMBERS)
def test_unknown_value_is_rejected(enum_type: type[Enum]) -> None:
    with pytest.raises(ValueError):
        enum_type("not-a-contract-value")


def test_domain_package_reexports_the_canonical_enum_types() -> None:
    assert DeviceStatus is DirectDeviceStatus
    assert RiskLevel is DirectRiskLevel
    assert IdempotencyMode is DirectIdempotencyMode
    assert ActionStatus is DirectActionStatus
