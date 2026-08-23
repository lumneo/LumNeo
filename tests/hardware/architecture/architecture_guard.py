"""Static import guards for the Hardware OS architecture.

The guard intentionally uses only the Python standard library so it can run before
the production package or its optional adapters exist. It examines syntactic import
edges; dynamic imports are reported as a documented limitation by the T01 review.
"""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


ModulePredicate = Callable[[str], bool]


def _under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _under_any(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(_under(module, prefix) for prefix in prefixes)


HARDWARE_DOMAIN = ("lumneo.hardware.domain",)
HARDWARE_SERVICE = ("lumneo.hardware.service",)
HARDWARE_EXECUTION = ("lumneo.hardware.execution",)
HARDWARE = ("lumneo.hardware",)
RUNTIME = ("lumneo.runtime",)
API = ("lumneo.api",)
EXTERNAL_CALLERS = ("lumneo.api", "lumneo.conversation", "lumneo.runtime")
KERNEL = ("lumneo.kernel",)
PERSISTENCE_MODELS = (
    "lumneo.persistence.models",
    "lumneo.infrastructure.hardware.persistence.models",
)
DRIVER_MODULES = (
    "lumneo.hardware.ports.driver",
    "lumneo.infrastructure.hardware.drivers",
)

# Physical client roots must be extended when a new vendor SDK is approved. The
# internal vendor-driver prefix catches bypasses even before a concrete SDK is known.
PHYSICAL_SDK_ROOTS = (
    "serial",
    "pyserial",
    "usb",
    "usb1",
    "pyusb",
    "hid",
    "hidapi",
    "pyvisa",
    "vendor_sdk",
    "lumneo.infrastructure.hardware.drivers.serial",
    "lumneo.infrastructure.hardware.drivers.usb",
    "lumneo.infrastructure.hardware.drivers.vendor",
)

AGENT_PLANNER_ROOTS = (
    "lumneo.agent.planner",
    "lumneo.agents.planner",
    "lumneo.runtime.agent_planner",
    "lumneo.runtime.planner",
)

HARDWARE_DRIVER_ROOTS = (
    "lumneo.hardware.ports.driver",
    "lumneo.infrastructure.hardware.drivers",
)


@dataclass(frozen=True, slots=True)
class ArchitectureRule:
    rule_id: str
    description: str
    source_matches: ModulePredicate
    target_matches: ModulePredicate


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source_module: str
    target_module: str
    source_path: Path
    line: int


@dataclass(frozen=True, slots=True)
class ArchitectureViolation:
    rule_id: str
    description: str
    source_module: str
    target_module: str
    source_path: Path
    line: int

    def render(self) -> str:
        return (
            f"{self.source_path}:{self.line}: [{self.rule_id}] "
            f"{self.source_module} -> {self.target_module}: {self.description}"
        )


def _source(prefixes: tuple[str, ...]) -> ModulePredicate:
    return lambda module: _under_any(module, prefixes)


def _target(prefixes: tuple[str, ...]) -> ModulePredicate:
    return lambda module: _under_any(module, prefixes)


RULES: tuple[ArchitectureRule, ...] = (
    ArchitectureRule(
        "HW_DOMAIN_INFRASTRUCTURE",
        "Hardware Domain must not import infrastructure adapters.",
        _source(HARDWARE_DOMAIN),
        _target(("lumneo.infrastructure",)),
    ),
    ArchitectureRule(
        "HW_DOMAIN_PERSISTENCE",
        "Hardware Domain must not import concrete persistence.",
        _source(HARDWARE_DOMAIN),
        _target(("lumneo.persistence",)),
    ),
    ArchitectureRule(
        "HW_DOMAIN_FASTAPI",
        "Hardware Domain must not import FastAPI.",
        _source(HARDWARE_DOMAIN),
        _target(("fastapi",)),
    ),
    ArchitectureRule(
        "HW_DOMAIN_DATABASE",
        "Hardware Domain must not import sqlite3 or SQLAlchemy.",
        _source(HARDWARE_DOMAIN),
        _target(("sqlite3", "sqlalchemy")),
    ),
    ArchitectureRule(
        "HW_DOMAIN_PHYSICAL_SDK",
        "Hardware Domain must not import Serial, USB, or vendor SDK clients.",
        _source(HARDWARE_DOMAIN),
        _target(PHYSICAL_SDK_ROOTS),
    ),
    ArchitectureRule(
        "HW_DOMAIN_RUNTIME",
        "Hardware Domain must not import Runtime implementation.",
        _source(HARDWARE_DOMAIN),
        _target(RUNTIME),
    ),
    ArchitectureRule(
        "HW_SERVICE_DATABASE",
        "Hardware services must not own SQLAlchemy/sqlite database access.",
        _source(HARDWARE_SERVICE),
        _target(("sqlite3", "sqlalchemy")),
    ),
    ArchitectureRule(
        "HW_EXECUTION_RUNTIME",
        "Hardware execution is not lumneo.runtime and must not import it.",
        _source(HARDWARE_EXECUTION),
        _target(RUNTIME),
    ),
    ArchitectureRule(
        "API_HARDWARE_DRIVER",
        "API may use HardwareFacade but must not import a Hardware Driver.",
        _source(API),
        _target(HARDWARE_DRIVER_ROOTS),
    ),
    ArchitectureRule(
        "EXTERNAL_HARDWARE_INTERNAL",
        "API, Conversation, and Runtime may access Hardware only through its Facade.",
        _source(EXTERNAL_CALLERS),
        lambda module: _under(module, "lumneo.hardware")
        and not _under(module, "lumneo.hardware.facade"),
    ),
    ArchitectureRule(
        "RUNTIME_PHYSICAL_SDK",
        "Runtime must not directly import Serial, USB, vendor SDK, or physical drivers.",
        _source(RUNTIME),
        _target(PHYSICAL_SDK_ROOTS),
    ),
    ArchitectureRule(
        "DRIVER_AGENT_PLANNER",
        "A Hardware Driver must not depend on Agent Planner.",
        _source(DRIVER_MODULES),
        _target(AGENT_PLANNER_ROOTS),
    ),
    ArchitectureRule(
        "HARDWARE_CONVERSATION",
        "Hardware must not depend on Conversation or form a cross-domain cycle.",
        _source(HARDWARE),
        _target(("lumneo.conversation",)),
    ),
    ArchitectureRule(
        "PERSISTENCE_MODEL_DOMAIN",
        "Persistence models must not import Hardware Domain models.",
        _source(PERSISTENCE_MODELS),
        _target(HARDWARE_DOMAIN),
    ),
    ArchitectureRule(
        "KERNEL_HARDWARE",
        "Kernel must not depend on Hardware OS business contracts.",
        _source(KERNEL),
        _target(HARDWARE),
    ),
)


def module_name(source_path: Path, source_root: Path) -> str:
    """Return the dotted module name for a Python path below ``source_root``."""

    relative = source_path.relative_to(source_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_from_import(node: ast.ImportFrom, source_package: str) -> str:
    if node.level == 0:
        return node.module or ""

    relative_name = f"{'.' * node.level}{node.module or ''}"
    try:
        return importlib.util.resolve_name(relative_name, source_package)
    except (ImportError, ValueError):
        # Invalid relative imports are a Python/import correctness issue. Retaining
        # their visible suffix lets architecture checks still catch obvious roots.
        return node.module or ""


def import_edges(source_path: Path, source_root: Path) -> tuple[ImportEdge, ...]:
    """Parse all static import targets from one Python source file."""

    source_module = module_name(source_path, source_root)
    source_package = (
        source_module
        if source_path.name == "__init__.py"
        else source_module.rpartition(".")[0]
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    edges: list[ImportEdge] = []

    for node in ast.walk(tree):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_import(node, source_package)
            if base:
                targets.append(base)
            for alias in node.names:
                if alias.name != "*":
                    targets.append(f"{base}.{alias.name}" if base else alias.name)
        else:
            continue

        for target in dict.fromkeys(targets):
            edges.append(
                ImportEdge(
                    source_module=source_module,
                    target_module=target,
                    source_path=source_path,
                    line=node.lineno,
                )
            )

    return tuple(edges)


def scan_architecture(
    source_root: Path,
    *,
    rules: Iterable[ArchitectureRule] = RULES,
) -> tuple[ArchitectureViolation, ...]:
    """Return every forbidden static import below a ``src``-style root."""

    if not source_root.exists():
        return ()

    active_rules = tuple(rules)
    violations: list[ArchitectureViolation] = []
    for source_path in sorted(source_root.rglob("*.py")):
        for edge in import_edges(source_path, source_root):
            for rule in active_rules:
                if rule.source_matches(edge.source_module) and rule.target_matches(
                    edge.target_module
                ):
                    violations.append(
                        ArchitectureViolation(
                            rule_id=rule.rule_id,
                            description=rule.description,
                            source_module=edge.source_module,
                            target_module=edge.target_module,
                            source_path=edge.source_path,
                            line=edge.line,
                        )
                    )

    return tuple(violations)


def render_violations(violations: Iterable[ArchitectureViolation]) -> str:
    rendered = [violation.render() for violation in violations]
    return "\n".join(rendered) if rendered else "No architecture violations."
