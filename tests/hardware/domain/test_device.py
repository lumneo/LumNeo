from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone

import pytest

from lumneo.hardware.domain.device import Device
from lumneo.hardware.domain.enums import DeviceStatus


EXPECTED_FIELDS = (
    "id",
    "type",
    "name",
    "status",
    "capability_ids",
    "driver_id",
    "metadata",
    "last_seen_at",
    "version",
)


def _device(**changes: object) -> Device:
    values: dict[str, object] = {
        "id": "device-light-01",
        "type": "light",
        "name": "Desk light",
        "status": DeviceStatus.ONLINE,
        "capability_ids": (
            "device-light-01.turn_on",
            "device-light-01.set_brightness",
        ),
        "driver_id": "simulated-light",
        "metadata": {"room": "office", "labels": ["phase0", "test"]},
        "last_seen_at": datetime(2026, 8, 23, 5, 30, tzinfo=timezone.utc),
        "version": 3,
    }
    values.update(changes)
    return Device(**values)  # type: ignore[arg-type]


def test_device_has_exact_contract_fields() -> None:
    assert tuple(field.name for field in fields(Device)) == EXPECTED_FIELDS


def test_device_constructs_and_serializes_to_json_compatible_values() -> None:
    device = _device()

    serialized = device.to_dict()

    assert serialized == {
        "id": "device-light-01",
        "type": "light",
        "name": "Desk light",
        "status": "online",
        "capability_ids": [
            "device-light-01.turn_on",
            "device-light-01.set_brightness",
        ],
        "driver_id": "simulated-light",
        "metadata": {"room": "office", "labels": ["phase0", "test"]},
        "last_seen_at": "2026-08-23T05:30:00+00:00",
        "version": 3,
    }
    assert json.loads(json.dumps(serialized)) == serialized


def test_none_last_seen_at_serializes_as_null() -> None:
    device = _device(last_seen_at=None)

    assert device.to_dict()["last_seen_at"] is None


def test_capability_ids_is_a_read_only_tuple_snapshot() -> None:
    device = _device()

    assert isinstance(device.capability_ids, tuple)
    with pytest.raises(FrozenInstanceError):
        device.capability_ids = ()  # type: ignore[misc]


def test_mutating_constructor_metadata_does_not_change_device() -> None:
    metadata: dict[str, object] = {"room": "office"}
    device = _device(metadata=metadata)

    metadata["room"] = "lab"

    assert device.metadata == {"room": "office"}


def test_reconnect_state_replacement_preserves_identity_and_has_no_transport_fields() -> None:
    original = _device(status=DeviceStatus.OFFLINE, version=8)
    connecting = replace(
        original,
        status=DeviceStatus.CONNECTING,
        version=original.version + 1,
    )
    reconnected = replace(
        connecting,
        status=DeviceStatus.ONLINE,
        version=connecting.version + 1,
    )

    assert reconnected.id == original.id
    assert reconnected.driver_id == original.driver_id
    assert reconnected.version == 10
    assert {"port", "transport", "endpoint", "connection"}.isdisjoint(
        EXPECTED_FIELDS
    )


@pytest.mark.parametrize("field_name", ["id", "type", "name", "driver_id"])
def test_required_string_fields_reject_blank_values(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        _device(**{field_name: "  "})


@pytest.mark.parametrize("device_type", ["Light", " light", "light "])
def test_type_rejects_non_stable_lowercase_values(device_type: str) -> None:
    with pytest.raises(ValueError, match="lowercase"):
        _device(type=device_type)


def test_status_requires_frozen_device_status_enum() -> None:
    with pytest.raises(TypeError, match="DeviceStatus"):
        _device(status="online")


def test_capability_snapshot_rejects_mutable_list() -> None:
    with pytest.raises(TypeError, match="read-only tuple"):
        _device(capability_ids=["device-light-01.turn_on"])


def test_capability_snapshot_rejects_blank_ids() -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        _device(capability_ids=("device-light-01.turn_on", ""))


@pytest.mark.parametrize("version", [-1, 1.5, True])
def test_version_requires_non_negative_integer(version: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        _device(version=version)


def test_last_seen_at_rejects_non_datetime() -> None:
    with pytest.raises(TypeError, match="datetime or None"):
        _device(last_seen_at="2026-08-23T05:30:00Z")


def test_metadata_rejects_non_serializable_value() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        _device(metadata={"callback": object()})


@pytest.mark.parametrize("sensitive_key", ["password", "secret", "token", "api_key", "credential"])
def test_metadata_rejects_sensitive_keys_at_any_depth(sensitive_key: str) -> None:
    with pytest.raises(ValueError, match=sensitive_key):
        _device(metadata={"nested": [{sensitive_key: "must-not-be-stored"}]})


def test_serialized_metadata_is_detached_from_domain_state() -> None:
    device = _device()
    serialized = device.to_dict()
    serialized_metadata = serialized["metadata"]
    assert isinstance(serialized_metadata, dict)

    serialized_metadata["room"] = "lab"

    assert device.metadata["room"] == "office"
