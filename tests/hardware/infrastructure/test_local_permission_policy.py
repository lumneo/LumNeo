from __future__ import annotations

import asyncio
from dataclasses import replace

from lumneo.hardware.domain.enums import ActionStatus, RiskLevel
from lumneo.hardware.ports.permission_gate import PermissionDecision
from lumneo.infrastructure.hardware.permission.local_policy import (
    LocalPermissionGate,
    LocalPermissionPolicyConfig,
)

from tests.hardware.execution.test_executor import _action, _composition


def _evaluate(risk: RiskLevel, *, low_auto_approve: bool = False):
    async def scenario():
        _, _, _, _, capability = await _composition()
        capability = replace(capability, risk_level=risk)
        gate = LocalPermissionGate(
            LocalPermissionPolicyConfig(low_auto_approve=low_auto_approve)
        )
        return await gate.evaluate(
            _action(capability.id, {"brightness": 10}),
            capability,
        )

    return asyncio.run(scenario())


def test_phase_0_risk_matrix_is_exact_and_effective_risk_is_not_lowered() -> None:
    expected = {
        RiskLevel.READ_ONLY: PermissionDecision.APPROVED,
        RiskLevel.LOW: PermissionDecision.APPROVAL_REQUIRED,
        RiskLevel.MEDIUM: PermissionDecision.APPROVAL_REQUIRED,
        RiskLevel.HIGH: PermissionDecision.APPROVAL_REQUIRED,
        RiskLevel.CRITICAL: PermissionDecision.REJECTED,
    }
    for risk, decision in expected.items():
        evaluation = _evaluate(risk)
        assert evaluation.decision is decision
        assert evaluation.effective_risk is risk


def test_low_auto_approval_requires_explicit_configuration() -> None:
    default = _evaluate(RiskLevel.LOW)
    enabled = _evaluate(RiskLevel.LOW, low_auto_approve=True)
    assert default.decision is PermissionDecision.APPROVAL_REQUIRED
    assert enabled.decision is PermissionDecision.APPROVED
    assert enabled.reason_code == "low_auto_approved"


def test_high_can_never_be_silently_or_model_self_approved() -> None:
    evaluation = _evaluate(RiskLevel.HIGH, low_auto_approve=True)
    assert evaluation.decision is PermissionDecision.APPROVAL_REQUIRED
    assert evaluation.reason_code == "high_explicit_confirmation_required"
    assert "non-model" in (evaluation.reason_detail or "")


def test_critical_is_always_rejected_even_when_low_auto_approval_is_enabled() -> None:
    evaluation = _evaluate(RiskLevel.CRITICAL, low_auto_approve=True)
    assert evaluation.decision is PermissionDecision.REJECTED
    assert evaluation.reason_code == "critical_rejected_phase_0"


def test_executor_validates_parameters_before_local_permission_and_driver() -> None:
    class CountingGate(LocalPermissionGate):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def evaluate(self, action, capability):
            self.calls += 1
            return await super().evaluate(action, capability)

    async def scenario():
        executor, repository, driver, _, capability = await _composition()
        gate = CountingGate()
        executor._permission_gate = gate
        invalid = await executor.execute(
            _action(capability.id, {"brightness": 101})
        )
        return invalid, gate.calls, driver.execute_calls, await repository.get_action("action-1")

    result, permission_calls, driver_calls, stored = asyncio.run(scenario())
    assert result.status is ActionStatus.FAILED
    assert result.error is not None and result.error.code == "INVALID_PARAMETERS"
    assert permission_calls == 0
    assert driver_calls == 0
    assert stored is not None and stored.status is ActionStatus.FAILED


def test_critical_rejection_occurs_before_driver_invocation() -> None:
    async def scenario():
        executor, repository, driver, _, capability = await _composition()
        capability = replace(capability, risk_level=RiskLevel.CRITICAL)
        await repository.save_capability(capability)
        executor._permission_gate = LocalPermissionGate()
        result = await executor.execute(_action(capability.id, {"brightness": 10}))
        return result, driver.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.REJECTED
    assert result.error is not None and result.error.code == "ACTION_REJECTED"
    assert calls == 0
