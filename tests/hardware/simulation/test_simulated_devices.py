from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumneo.hardware.domain.action import PHYSICAL_ACTION_KIND, HardwareAction
from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus
from lumneo.hardware.ports.driver import DeviceDriver
from lumneo.hardware.simulation.faults import FaultProfile
from lumneo.hardware.simulation.light import SimulatedLightDriver
from lumneo.hardware.simulation.temperature_sensor import (
    SimulatedTemperatureSensorDriver,
)


FIXED_TIME = datetime(2026, 8, 23, 11, 0, tzinfo=timezone.utc)


def _action(driver: DeviceDriver, capability_id: str, parameters: dict[str, object]) -> HardwareAction:
    return HardwareAction(
        action_id=f"action-{capability_id.rsplit('.', 1)[-1]}",
        action_kind=PHYSICAL_ACTION_KIND,
        device_id=capability_id.rsplit(".", 1)[0],
        capability_id=capability_id,
        parameters=parameters,
        requester="test",
        status=ActionStatus.RUNNING,
        idempotency_key=None,
        timeout_ms=1_000,
        correlation_id=None,
        context_ref=None,
        expected_device_version=None,
        parameters_digest="sha256:test",
        approval_expires_at=None,
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )


async def _ready(driver: DeviceDriver, device_id: str) -> None:
    await driver.initialize()
    await driver.connect(device_id)


def test_both_simulated_devices_satisfy_same_driver_port() -> None:
    assert isinstance(SimulatedLightDriver(), DeviceDriver)
    assert isinstance(SimulatedTemperatureSensorDriver(), DeviceDriver)


def test_simulated_light_discovery_health_and_lifecycle() -> None:
    async def scenario() -> tuple[bool, DeviceStatus, DeviceStatus]:
        driver = SimulatedLightDriver()
        await driver.initialize()
        health = await driver.health_check()
        discovered = await driver.discover()
        await driver.connect(discovered[0].id)
        online = await driver.get_status(discovered[0].id)
        await driver.disconnect(discovered[0].id)
        offline = await driver.get_status(discovered[0].id)
        return health.available, online, offline

    assert asyncio.run(scenario()) == (True, DeviceStatus.ONLINE, DeviceStatus.OFFLINE)


def test_light_all_happy_paths_and_state_are_deterministic() -> None:
    async def scenario() -> list[dict[str, object] | None]:
        driver = SimulatedLightDriver()
        device_id = "simulated-light-01"
        await _ready(driver, device_id)
        outputs = []
        for operation, parameters in (
            ("get_state", {}),
            ("turn_on", {}),
            ("set_brightness", {"brightness": 75}),
            ("turn_off", {}),
            ("get_state", {}),
        ):
            result = await driver.execute(
                _action(driver, f"{device_id}.{operation}", parameters)
            )
            assert result.status is ActionStatus.SUCCEEDED
            outputs.append(result.output)
        return outputs

    assert asyncio.run(scenario()) == [
        {"on": False, "brightness": 0},
        {"on": True, "brightness": 0},
        {"on": True, "brightness": 75},
        {"on": False, "brightness": 75},
        {"on": False, "brightness": 75},
    ]


@pytest.mark.parametrize("brightness", [0, 100])
def test_light_brightness_accepts_contract_boundaries(brightness: int) -> None:
    async def scenario() -> object:
        driver = SimulatedLightDriver()
        await _ready(driver, "simulated-light-01")
        result = await driver.execute(
            _action(
                driver,
                "simulated-light-01.set_brightness",
                {"brightness": brightness},
            )
        )
        return result.output

    assert asyncio.run(scenario()) == {"on": False, "brightness": brightness}


@pytest.mark.parametrize("brightness", [-1, 101, 1.5, True])
def test_light_rejects_invalid_brightness_even_when_called_directly(brightness: object) -> None:
    async def scenario():
        driver = SimulatedLightDriver()
        await _ready(driver, "simulated-light-01")
        return await driver.execute(
            _action(
                driver,
                "simulated-light-01.set_brightness",
                {"brightness": brightness},
            )
        )

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert result.error is not None
    assert result.error.code == "INVALID_PARAMETERS"


def test_temperature_read_has_exact_deterministic_output() -> None:
    async def scenario():
        driver = SimulatedTemperatureSensorDriver(
            temperature_celsius=23.75,
            clock=lambda: FIXED_TIME,
        )
        await _ready(driver, "simulated-temperature-01")
        return await driver.execute(
            _action(
                driver,
                "simulated-temperature-01.read_temperature",
                {},
            )
        )

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.SUCCEEDED
    assert result.output == {
        "value": 23.75,
        "unit": "celsius",
        "measured_at": "2026-08-23T11:00:00+00:00",
    }


def test_offline_fault_returns_device_offline_without_execution() -> None:
    async def scenario():
        driver = SimulatedLightDriver(fault_profile=FaultProfile(offline=True))
        await driver.initialize()
        return await driver.execute(
            _action(driver, "simulated-light-01.turn_on", {})
        )

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert result.error is not None and result.error.code == "DEVICE_OFFLINE"
    assert result.device_acknowledged is False


def test_delay_fault_is_deterministic() -> None:
    async def scenario() -> float:
        driver = SimulatedLightDriver(fault_profile=FaultProfile(delay_ms=15))
        await _ready(driver, "simulated-light-01")
        started = time.perf_counter()
        await driver.execute(_action(driver, "simulated-light-01.turn_on", {}))
        return time.perf_counter() - started

    assert asyncio.run(scenario()) >= 0.010


def test_timeout_fault_raises_timeout_for_executor_to_classify() -> None:
    async def scenario() -> None:
        driver = SimulatedLightDriver(fault_profile=FaultProfile(timeout=True))
        await _ready(driver, "simulated-light-01")
        with pytest.raises(TimeoutError, match="deterministic"):
            await driver.execute(_action(driver, "simulated-light-01.turn_on", {}))

    asyncio.run(scenario())


def test_driver_error_fault_returns_explicit_error() -> None:
    async def scenario():
        driver = SimulatedLightDriver(
            fault_profile=FaultProfile(driver_error="injected driver error")
        )
        await _ready(driver, "simulated-light-01")
        return await driver.execute(_action(driver, "simulated-light-01.turn_on", {}))

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert result.error is not None
    assert result.error.code == "DRIVER_ERROR"
    assert result.error.message == "injected driver error"


def test_invalid_output_fault_returns_deterministic_schema_violation() -> None:
    async def scenario():
        driver = SimulatedLightDriver(fault_profile=FaultProfile(invalid_output=True))
        await _ready(driver, "simulated-light-01")
        return await driver.execute(_action(driver, "simulated-light-01.turn_on", {}))

    result = asyncio.run(scenario())
    assert result.status is ActionStatus.SUCCEEDED
    assert result.output == {"invalid_output": True}


def test_fail_next_n_fails_exact_count_then_recovers() -> None:
    async def scenario() -> list[ActionStatus]:
        profile = FaultProfile(fail_next_n=2)
        driver = SimulatedLightDriver(fault_profile=profile)
        await _ready(driver, "simulated-light-01")
        statuses = []
        for _ in range(3):
            result = await driver.execute(
                _action(driver, "simulated-light-01.turn_on", {})
            )
            statuses.append(result.status)
        assert profile.fail_next_n == 0
        return statuses

    assert asyncio.run(scenario()) == [
        ActionStatus.FAILED,
        ActionStatus.FAILED,
        ActionStatus.SUCCEEDED,
    ]


@pytest.mark.parametrize(
    "changes,error_type",
    [
        ({"delay_ms": -1}, ValueError),
        ({"delay_ms": True}, ValueError),
        ({"fail_next_n": -1}, ValueError),
        ({"offline": 1}, TypeError),
        ({"driver_error": 1}, TypeError),
    ],
)
def test_fault_profile_rejects_invalid_configuration(
    changes: dict[str, object],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        FaultProfile(**changes)  # type: ignore[arg-type]


def test_simulation_has_no_random_or_virtual_mcu_dependency() -> None:
    import lumneo.hardware.simulation.base as base_module
    import lumneo.hardware.simulation.faults as faults_module

    source = "\n".join(
        [
            Path(base_module.__file__).read_text(encoding="utf-8"),
            Path(faults_module.__file__).read_text(encoding="utf-8"),
        ]
    )
    assert "import random" not in source
    assert all(name not in source for name in ("simavr", "qemu", "renode"))
