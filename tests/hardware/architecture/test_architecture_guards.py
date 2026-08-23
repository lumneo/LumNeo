from __future__ import annotations

from pathlib import Path
import tempfile
from collections.abc import Iterator

import pytest

from tests.hardware.architecture.architecture_guard import (
    RULES,
    import_edges,
    render_violations,
    scan_architecture,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_RULE_IDS = {
    "HW_DOMAIN_INFRASTRUCTURE",
    "HW_DOMAIN_PERSISTENCE",
    "HW_DOMAIN_FASTAPI",
    "HW_DOMAIN_DATABASE",
    "HW_DOMAIN_PHYSICAL_SDK",
    "HW_DOMAIN_RUNTIME",
    "HW_SERVICE_DATABASE",
    "HW_EXECUTION_RUNTIME",
    "API_HARDWARE_DRIVER",
    "EXTERNAL_HARDWARE_INTERNAL",
    "RUNTIME_PHYSICAL_SDK",
    "DRIVER_AGENT_PLANNER",
    "HARDWARE_CONVERSATION",
    "PERSISTENCE_MODEL_DOMAIN",
    "KERNEL_HARDWARE",
}


@pytest.fixture
def architecture_tmp_path() -> Iterator[Path]:
    """Use the writable workspace instead of the restricted system temp root."""

    with tempfile.TemporaryDirectory(prefix=".t01-", dir=PROJECT_ROOT) as directory:
        yield Path(directory)


def _write_module(source_root: Path, module: str, source: str) -> Path:
    module_path = source_root.joinpath(*module.split(".")).with_suffix(".py")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return module_path


def test_current_source_tree_obeys_hardware_architecture() -> None:
    violations = scan_architecture(PROJECT_ROOT / "src")
    assert not violations, render_violations(violations)


def test_frozen_rule_set_is_complete_and_unique() -> None:
    rule_ids = [rule.rule_id for rule in RULES]

    assert len(rule_ids) == len(set(rule_ids))
    assert set(rule_ids) == EXPECTED_RULE_IDS


def test_compliant_layering_passes(architecture_tmp_path: Path) -> None:
    source_root = architecture_tmp_path / "src"
    _write_module(
        source_root,
        "lumneo.hardware.domain.device",
        "from dataclasses import dataclass\nfrom lumneo.kernel.clock import Clock\n",
    )
    _write_module(
        source_root,
        "lumneo.hardware.ports.driver",
        "from lumneo.hardware.domain.device import Device\n",
    )
    _write_module(
        source_root,
        "lumneo.infrastructure.hardware.drivers.serial.light",
        "from lumneo.hardware.ports.driver import DeviceDriver\nimport serial\n",
    )
    _write_module(
        source_root,
        "lumneo.runtime.tools.hardware",
        "from lumneo.hardware.facade.hardware_facade import HardwareFacade\n",
    )
    _write_module(
        source_root,
        "lumneo.api.hardware",
        "from lumneo.hardware.facade.hardware_facade import HardwareFacade\n",
    )
    _write_module(
        source_root,
        "lumneo.conversation.hardware",
        "from lumneo.hardware.facade.hardware_facade import HardwareFacade\n",
    )

    violations = scan_architecture(source_root)

    assert not violations, render_violations(violations)


@pytest.mark.parametrize(
    ("source_module", "statement", "expected_rule"),
    [
        (
            "lumneo.hardware.domain.device",
            "from lumneo.infrastructure.hardware import drivers",
            "HW_DOMAIN_INFRASTRUCTURE",
        ),
        (
            "lumneo.hardware.domain.device",
            "from lumneo.persistence.models import HardwareDeviceRow",
            "HW_DOMAIN_PERSISTENCE",
        ),
        ("lumneo.hardware.domain.device", "import fastapi", "HW_DOMAIN_FASTAPI"),
        ("lumneo.hardware.domain.device", "import sqlite3", "HW_DOMAIN_DATABASE"),
        (
            "lumneo.hardware.domain.device",
            "from sqlalchemy.orm import Session",
            "HW_DOMAIN_DATABASE",
        ),
        (
            "lumneo.hardware.domain.device",
            "import serial",
            "HW_DOMAIN_PHYSICAL_SDK",
        ),
        (
            "lumneo.hardware.domain.device",
            "from lumneo.runtime.execution import RuntimeLoop",
            "HW_DOMAIN_RUNTIME",
        ),
        (
            "lumneo.hardware.service.hardware_service",
            "from sqlalchemy.orm import Session",
            "HW_SERVICE_DATABASE",
        ),
        (
            "lumneo.hardware.execution.executor",
            "from lumneo.runtime.execution import RuntimeLoop",
            "HW_EXECUTION_RUNTIME",
        ),
        (
            "lumneo.api.hardware",
            "from lumneo.hardware.ports import driver",
            "API_HARDWARE_DRIVER",
        ),
        (
            "lumneo.api.hardware",
            "from lumneo.infrastructure.hardware.drivers.usb import UsbDriver",
            "API_HARDWARE_DRIVER",
        ),
        (
            "lumneo.conversation.hardware",
            "from lumneo.hardware.domain.action import HardwareAction",
            "EXTERNAL_HARDWARE_INTERNAL",
        ),
        (
            "lumneo.runtime.tools.hardware",
            "import usb.core",
            "RUNTIME_PHYSICAL_SDK",
        ),
        (
            "lumneo.runtime.tools.hardware",
            "from lumneo.infrastructure.hardware.drivers.vendor import VendorDriver",
            "RUNTIME_PHYSICAL_SDK",
        ),
        (
            "lumneo.infrastructure.hardware.drivers.serial.light",
            "from lumneo.agent.planner import Planner",
            "DRIVER_AGENT_PLANNER",
        ),
        (
            "lumneo.hardware.service.hardware_service",
            "from lumneo.conversation.service import ConversationService",
            "HARDWARE_CONVERSATION",
        ),
        (
            "lumneo.persistence.models.hardware",
            "from lumneo.hardware.domain.action import HardwareAction",
            "PERSISTENCE_MODEL_DOMAIN",
        ),
        (
            "lumneo.kernel.events",
            "from lumneo.hardware.domain.event import HardwareDomainEvent",
            "KERNEL_HARDWARE",
        ),
    ],
)
def test_representative_forbidden_import_is_detected(
    architecture_tmp_path: Path,
    source_module: str,
    statement: str,
    expected_rule: str,
) -> None:
    source_root = architecture_tmp_path / "src"
    _write_module(source_root, source_module, f"{statement}\n")

    violations = scan_architecture(source_root)

    assert expected_rule in {violation.rule_id for violation in violations}, (
        f"Expected {expected_rule} for {source_module}: {statement}\n"
        f"{render_violations(violations)}"
    )


def test_relative_imports_are_resolved_before_rules_are_applied(
    architecture_tmp_path: Path,
) -> None:
    source_root = architecture_tmp_path / "src"
    path = _write_module(
        source_root,
        "lumneo.hardware.execution.executor",
        "from ...runtime.execution import RuntimeLoop\n",
    )

    edges = import_edges(path, source_root)
    violations = scan_architecture(source_root)

    assert "lumneo.runtime.execution" in {edge.target_module for edge in edges}
    assert "HW_EXECUTION_RUNTIME" in {
        violation.rule_id for violation in violations
    }


def test_package_init_relative_import_uses_package_as_resolution_base(
    architecture_tmp_path: Path,
) -> None:
    source_root = architecture_tmp_path / "src"
    path = _write_module(
        source_root,
        "lumneo.hardware.execution.__init__",
        "from ...runtime import execution\n",
    )

    edges = import_edges(path, source_root)
    violations = scan_architecture(source_root)

    assert "lumneo.runtime" in {edge.target_module for edge in edges}
    assert "HW_EXECUTION_RUNTIME" in {
        violation.rule_id for violation in violations
    }


def test_violation_output_contains_rule_path_line_and_edge(
    architecture_tmp_path: Path,
) -> None:
    source_root = architecture_tmp_path / "src"
    source_path = _write_module(
        source_root,
        "lumneo.hardware.domain.device",
        "\nimport fastapi\n",
    )

    rendered = render_violations(scan_architecture(source_root))

    assert "[HW_DOMAIN_FASTAPI]" in rendered
    assert f"{source_path}:2" in rendered
    assert "lumneo.hardware.domain.device -> fastapi" in rendered
