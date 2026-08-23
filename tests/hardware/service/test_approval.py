from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest

from lumneo.hardware.domain.enums import ActionStatus, DeviceStatus, RiskLevel
from lumneo.hardware.service.approval import ApprovalError, ApprovalService
from lumneo.hardware.ports.permission_gate import PermissionDecision

from tests.hardware.execution.test_executor import NOW, _action, _composition


async def _awaiting_composition():
    executor, repository, driver, _, capability = await _composition(
        decision=PermissionDecision.APPROVAL_REQUIRED
    )
    initial = await executor.execute(_action(capability.id, {"brightness": 30}))
    assert initial.status is ActionStatus.AWAITING_APPROVAL
    action = await repository.get_action("action-1")
    device = await repository.get_device("simulated-light-01")
    assert action is not None and device is not None
    return executor, repository, driver, capability, action, device


def test_approved_binding_resumes_and_executes_exactly_once() -> None:
    async def scenario():
        executor, repository, driver, capability, action, device = (
            await _awaiting_composition()
        )
        service = ApprovalService(repository, clock=lambda: NOW)
        approval = await service.approve(
            action,
            device,
            capability,
            approver="human-1",
        )
        result = await executor.resume_approved(
            action.action_id,
            approval_validator=service,
        )
        return approval, result, driver.execute_calls, await repository.list_approvals(action.action_id)

    approval, result, calls, records = asyncio.run(scenario())
    assert approval.expires_at == NOW + timedelta(minutes=5)
    assert result.status is ActionStatus.SUCCEEDED
    assert calls == 1
    assert "parameters" not in records[0]
    assert records[0]["parameters_digest"] == "sha256:test"


def test_rejection_cannot_execute_driver() -> None:
    async def scenario():
        executor, repository, driver, capability, action, device = (
            await _awaiting_composition()
        )
        service = ApprovalService(repository, clock=lambda: NOW)
        await service.reject(action, device, capability, approver="human-1")
        result = await executor.resume_approved(
            action.action_id,
            approval_validator=service,
        )
        return result, driver.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.REJECTED
    assert result.error is not None
    assert result.error.details["approval_reason"] == "approval_rejected"
    assert calls == 0


def test_default_expiry_and_thirty_minute_maximum_are_enforced() -> None:
    async def scenario():
        _, repository, _, capability, action, device = await _awaiting_composition()
        service = ApprovalService(repository, clock=lambda: NOW)
        default = await service.approve(action, device, capability, approver="human-1")
        maximum = await service.approve(
            action,
            device,
            capability,
            approver="human-1",
            ttl=timedelta(minutes=30),
        )
        with pytest.raises(ValueError, match="30 minutes"):
            await service.approve(
                action,
                device,
                capability,
                approver="human-1",
                ttl=timedelta(minutes=30, seconds=1),
            )
        return default, maximum

    default, maximum = asyncio.run(scenario())
    assert default.expires_at == NOW + timedelta(minutes=5)
    assert maximum.expires_at == NOW + timedelta(minutes=30)


def test_expired_approval_is_rejected_before_driver() -> None:
    async def scenario():
        now = [NOW]
        executor, repository, driver, capability, action, device = (
            await _awaiting_composition()
        )
        service = ApprovalService(repository, clock=lambda: now[0])
        await service.approve(action, device, capability, approver="human-1")
        now[0] = NOW + timedelta(minutes=5)
        result = await executor.resume_approved(action.action_id, approval_validator=service)
        return result, driver.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.REJECTED
    assert result.error is not None
    assert result.error.details["approval_reason"] == "approval_expired"
    assert calls == 0


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("digest", "approval_digest_changed"),
        ("device_version", "approval_device_changed"),
        ("device_status", "approval_device_unavailable"),
        ("capability_revision", "approval_capability_changed"),
    ],
)
def test_changed_binding_context_invalidates_approval(
    mutation: str,
    expected_reason: str,
) -> None:
    async def scenario():
        executor, repository, driver, capability, action, device = (
            await _awaiting_composition()
        )
        service = ApprovalService(repository, clock=lambda: NOW)
        await service.approve(action, device, capability, approver="human-1")
        if mutation == "digest":
            await repository.save_action(
                replace(
                    action,
                    parameters={"brightness": 31},
                    parameters_digest="sha256:changed",
                )
            )
        elif mutation == "device_version":
            await repository.save_device(replace(device, version=device.version + 1))
        elif mutation == "device_status":
            await repository.save_device(replace(device, status=DeviceStatus.OFFLINE))
        else:
            await repository.save_capability(
                replace(capability, revision=capability.revision + 1)
            )
        result = await executor.resume_approved(action.action_id, approval_validator=service)
        return result, driver.execute_calls

    result, calls = asyncio.run(scenario())
    assert result.status is ActionStatus.REJECTED
    assert result.error is not None
    assert result.error.details["approval_reason"] == expected_reason
    assert calls == 0


def test_model_cannot_approve_high_risk_action() -> None:
    async def scenario():
        _, repository, _, capability, action, device = await _awaiting_composition()
        service = ApprovalService(repository, clock=lambda: NOW)
        high = replace(capability, risk_level=RiskLevel.HIGH)
        with pytest.raises(ApprovalError) as caught:
            await service.approve(
                action,
                device,
                high,
                approver="model-agent",
                approver_kind="model",
            )
        return caught.value, await repository.list_approvals(action.action_id)

    error, records = asyncio.run(scenario())
    assert error.code == "ACTION_REJECTED"
    assert records == []
