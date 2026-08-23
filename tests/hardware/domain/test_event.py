from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from lumneo.hardware.domain.event import (
    HardwareDomainEvent,
    HardwareEvent,
    HardwareSignalEvent,
    new_domain_event,
    new_signal_event,
)


NOW = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)

EXPECTED_DOMAIN_FIELDS = (
    "event_id",
    "event_type",
    "device_id",
    "action_id",
    "timestamp",
    "payload",
    "runtime_sequence",
    "source_sequence",
    "correlation_id",
    "source",
)

EXPECTED_SIGNAL_FIELDS = (
    "signal_id",
    "signal_type",
    "device_id",
    "timestamp",
    "payload",
    "source_sequence",
    "source",
)


def _domain_event(**changes: object) -> HardwareDomainEvent:
    values: dict[str, object] = {
        "event_id": "event-01",
        "event_type": "hardware.action.succeeded",
        "device_id": "device-light-01",
        "action_id": "action-01",
        "timestamp": NOW,
        "payload": {"brightness": 75},
        "runtime_sequence": 8,
        "source_sequence": 22,
        "correlation_id": "conversation-7",
        "source": "simulated-light",
    }
    values.update(changes)
    return HardwareDomainEvent(**values)  # type: ignore[arg-type]


def _signal_event(**changes: object) -> HardwareSignalEvent:
    values: dict[str, object] = {
        "signal_id": "signal-01",
        "signal_type": "gpio_change",
        "device_id": "device-board-01",
        "timestamp": NOW,
        "payload": {"pin": 13, "value": 1},
        "source_sequence": 40,
        "source": "virtual-mcu",
    }
    values.update(changes)
    return HardwareSignalEvent(**values)  # type: ignore[arg-type]


def test_domain_event_has_exact_accepted_contract_fields() -> None:
    assert tuple(field.name for field in fields(HardwareDomainEvent)) == EXPECTED_DOMAIN_FIELDS


def test_hardware_event_is_only_a_compatibility_alias() -> None:
    assert HardwareEvent is HardwareDomainEvent


def test_domain_event_serializes_to_json_compatible_values() -> None:
    serialized = _domain_event().to_dict()

    assert tuple(serialized) == EXPECTED_DOMAIN_FIELDS
    assert serialized["timestamp"] == "2026-08-23T09:00:00+00:00"
    assert serialized["event_type"] == "hardware.action.succeeded"
    assert json.loads(json.dumps(serialized)) == serialized


def test_domain_event_allows_device_or_action_id_to_be_absent() -> None:
    event = _domain_event(device_id=None, action_id=None)

    assert event.device_id is None
    assert event.action_id is None


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 8, 23, 9, 0),
        datetime(2026, 8, 23, 17, 0, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_domain_event_rejects_non_utc_timestamp(timestamp: datetime) -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _domain_event(timestamp=timestamp)


def test_domain_event_requires_datetime_timestamp() -> None:
    with pytest.raises(TypeError, match="datetime"):
        _domain_event(timestamp="2026-08-23T09:00:00Z")


@pytest.mark.parametrize(
    "event_type",
    ["action.succeeded", "device.status_changed", "gpio_change", "serial_output"],
)
def test_domain_event_requires_canonical_hardware_namespace(event_type: str) -> None:
    with pytest.raises(ValueError, match="hardware"):
        _domain_event(event_type=event_type)


def test_domain_event_factory_generates_unique_ids_and_utc_time() -> None:
    events = [
        new_domain_event(
            event_type="hardware.device.connected",
            device_id=f"device-{index}",
            payload={},
            runtime_sequence=0,
            source="discovery",
        )
        for index in range(100)
    ]

    assert len({event.event_id for event in events}) == 100
    assert all(event.timestamp.utcoffset() == timedelta(0) for event in events)


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("runtime_sequence", -1),
        ("runtime_sequence", 1.5),
        ("runtime_sequence", True),
        ("source_sequence", -1),
        ("source_sequence", "1"),
    ],
)
def test_domain_event_validates_sequences(field_name: str, value: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        _domain_event(**{field_name: value})


def test_payload_is_detached_and_serialization_returns_another_copy() -> None:
    payload: dict[str, object] = {"state": {"online": True}}
    event = _domain_event(payload=payload)
    payload["state"] = {"online": False}
    serialized = event.to_dict()
    serialized_payload = serialized["payload"]
    assert isinstance(serialized_payload, dict)
    serialized_payload["state"] = {"online": False}

    assert event.payload == {"state": {"online": True}}


def test_payload_rejects_binary_or_non_serializable_data() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        _domain_event(payload={"firmware": b"binary"})


@pytest.mark.parametrize("key", ["password", "secret", "token", "api_key", "credential"])
def test_payload_rejects_sensitive_keys_at_any_depth(key: str) -> None:
    with pytest.raises(ValueError, match=key):
        _domain_event(payload={"nested": [{key: "private"}]})


def test_signal_event_has_distinct_fields_type_and_serialization() -> None:
    signal = _signal_event()

    assert tuple(field.name for field in fields(HardwareSignalEvent)) == EXPECTED_SIGNAL_FIELDS
    assert not isinstance(signal, HardwareDomainEvent)
    assert signal.to_dict()["signal_type"] == "gpio_change"
    assert "event_type" not in signal.to_dict()


def test_signal_event_cannot_use_domain_event_namespace() -> None:
    with pytest.raises(ValueError, match="domain-event namespace"):
        _signal_event(signal_type="hardware.action.succeeded")


def test_signal_factory_generates_unique_signal_ids() -> None:
    first = new_signal_event(
        signal_type="analog_change",
        device_id="device-board-01",
        payload={"channel": 0, "value": 0.5},
        source="virtual-mcu",
    )
    second = new_signal_event(
        signal_type="analog_change",
        device_id="device-board-01",
        payload={"channel": 0, "value": 0.6},
        source="virtual-mcu",
    )

    assert first.signal_id != second.signal_id
    assert first.timestamp.utcoffset() == timedelta(0)
