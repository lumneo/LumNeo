"""Core ordered HardwareAction execution pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Protocol

from jsonschema.exceptions import ValidationError

from ..domain.action import ActionResult, HardwareAction
from ..domain.capability import Capability
from ..domain.device import Device
from ..domain.enums import ActionStatus, DeviceStatus, IdempotencyMode
from ..domain.errors import HardwareError
from ..domain.event import HardwareDomainEvent
from ..ports.event_bus import EventBus
from ..ports.driver import DeviceDriver
from ..ports.permission_gate import PermissionDecision, PermissionGate
from ..ports.repository import HardwareRepository
from .dispatcher import ActionDispatcher, DispatchError
from .lifecycle import ActionLifecycle
from .reliability import ConfirmedNotExecutedTimeout


ExecutionObserver = Callable[[str], None]
EventBuilder = Callable[[HardwareAction], Awaitable[HardwareDomainEvent]]


class ApprovalCheck(Protocol):
    valid: bool
    reason_code: str
    reason_detail: str


class ApprovalValidator(Protocol):
    async def validate(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
    ) -> ApprovalCheck: ...


class AuditWriter(Protocol):
    async def record(self, action: HardwareAction, result: ActionResult) -> None: ...


class ActionExecutor:
    def __init__(
        self,
        *,
        repository: HardwareRepository,
        permission_gate: PermissionGate,
        event_bus: EventBus,
        event_builder: EventBuilder,
        dispatcher: ActionDispatcher,
        lifecycle: ActionLifecycle,
        audit_writer: AuditWriter | None = None,
        observer: ExecutionObserver | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._permission_gate = permission_gate
        self._event_bus = event_bus
        self._event_builder = event_builder
        self._dispatcher = dispatcher
        self._lifecycle = lifecycle
        self._audit_writer = audit_writer
        self._observer = observer
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._device_write_locks: dict[str, asyncio.Lock] = {}
        self._terminal_locks: dict[str, asyncio.Lock] = {}
        self._active_drivers: dict[str, DeviceDriver] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def execute(self, action: HardwareAction) -> ActionResult:
        if action.status is not ActionStatus.CREATED:
            raise ValueError("ActionExecutor requires a CREATED action")

        self._mark("1.create")
        await self._repository.save_action(action)
        action = await self._move(
            action,
            ActionStatus.VALIDATING,
            reason_code="validation_started",
        )

        self._mark("2.lookup")
        device = await self._repository.get_device(action.device_id)
        if device is None:
            return await self._fail_validation(
                action,
                HardwareError("DEVICE_NOT_FOUND", "Device not found", False, {}),
            )
        capability = await self._repository.get_capability(action.capability_id)
        if capability is None or capability.device_id != device.id:
            return await self._fail_validation(
                action,
                HardwareError("CAPABILITY_NOT_FOUND", "Capability not found", False, {}),
            )

        self._mark("3.state_validate")
        state_error = self._validate_state(action, device, capability)
        if state_error is not None:
            return await self._fail_validation(action, state_error)

        self._mark("4.schema_validate")
        try:
            capability.validate_input(action.parameters)
        except ValidationError as error:
            return await self._fail_validation(
                action,
                HardwareError(
                    "INVALID_PARAMETERS",
                    error.message,
                    False,
                    {"path": list(error.absolute_path)},
                ),
            )

        self._mark("5.idempotency")
        existing = await self._apply_idempotency(action, capability)
        if isinstance(existing, ActionResult):
            await self._audit(action, existing)
            self._mark("13.return")
            return existing
        if isinstance(existing, HardwareError):
            return await self._fail_validation(action, existing)

        self._mark("6.permission")
        permission = await self._permission_gate.evaluate(action, capability)

        self._mark("7.persist_state")
        if permission.decision is PermissionDecision.REJECTED:
            action = await self._move(
                action,
                ActionStatus.AWAITING_APPROVAL,
                reason_code="permission_evaluated",
            )
            action = await self._move(
                action,
                ActionStatus.REJECTED,
                reason_code=permission.reason_code,
                reason_detail=permission.reason_detail,
            )
            return await self._finish(
                action,
                ActionResult(
                    action.action_id,
                    ActionStatus.REJECTED,
                    None,
                    HardwareError(
                        "ACTION_REJECTED",
                        permission.reason_detail or "Action rejected by permission policy",
                        False,
                        {"effective_risk": permission.effective_risk.value},
                    ),
                    None,
                    self._clock(),
                    False,
                ),
            )
        if permission.decision is PermissionDecision.APPROVAL_REQUIRED:
            action = await self._move(
                action,
                ActionStatus.AWAITING_APPROVAL,
                reason_code=permission.reason_code,
                reason_detail=permission.reason_detail,
            )
            result = ActionResult(
                action.action_id,
                ActionStatus.AWAITING_APPROVAL,
                None,
                HardwareError(
                    "APPROVAL_REQUIRED",
                    permission.reason_detail or "Approval is required",
                    False,
                    {"effective_risk": permission.effective_risk.value},
                ),
                None,
                None,
                False,
            )
            await self._repository.save_result(result)
            await self._audit(action, result)
            self._mark("13.return")
            return result

        return await self._run_approved(
            action,
            device,
            capability,
            reason_code=permission.reason_code,
            reason_detail=permission.reason_detail,
        )

    async def resume_approved(
        self,
        action_id: str,
        *,
        approval_validator: ApprovalValidator,
    ) -> ActionResult:
        """Revalidate an exact approval binding immediately before execution."""
        action = await self._repository.get_action(action_id)
        if action is None:
            return self._operation_error(
                action_id,
                ActionStatus.FAILED,
                "CONFLICT",
                "Action not found",
            )
        if action.status is not ActionStatus.AWAITING_APPROVAL:
            return self._operation_error(
                action_id,
                action.status,
                "CONFLICT",
                "Action is not awaiting approval",
            )
        device = await self._repository.get_device(action.device_id)
        capability = await self._repository.get_capability(action.capability_id)
        if device is None or capability is None or capability.device_id != action.device_id:
            return await self._reject_invalid_approval(
                action,
                "approval_target_missing",
                "Approval target no longer exists",
            )
        check = await approval_validator.validate(action, device, capability)
        if not check.valid:
            return await self._reject_invalid_approval(
                action,
                check.reason_code,
                check.reason_detail,
            )
        return await self._run_approved(
            action,
            device,
            capability,
            reason_code=check.reason_code,
            reason_detail=check.reason_detail,
        )

    async def _reject_invalid_approval(
        self,
        action: HardwareAction,
        reason_code: str,
        reason_detail: str,
    ) -> ActionResult:
        return await self._accept_terminal(
            action,
            ActionResult(
                action.action_id,
                ActionStatus.REJECTED,
                None,
                HardwareError(
                    "ACTION_REJECTED",
                    reason_detail,
                    False,
                    {"approval_reason": reason_code},
                ),
                None,
                self._clock(),
                False,
            ),
            reason_code=reason_code,
        )

    async def _run_approved(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
        *,
        reason_code: str,
        reason_detail: str | None,
    ) -> ActionResult:
        action = await self._move(
            action,
            ActionStatus.APPROVED,
            reason_code=reason_code,
            reason_detail=reason_detail,
        )
        action = await self._move(
            action,
            ActionStatus.RUNNING,
            reason_code="execution_started",
        )

        self._mark("8.driver")
        try:
            driver = await self._dispatcher.resolve(action, device, capability)
        except DispatchError as error:
            return await self._fail_running(action, error.error)

        self._mark("9.outcome")
        try:
            lock = self._device_write_locks.setdefault(device.id, asyncio.Lock())
            if capability.risk_level.value == "read_only":
                driver_result = await self._execute_with_retries(action, driver, capability)
            else:
                async with lock:
                    driver_result = await self._execute_with_retries(action, driver, capability)
        except ConfirmedNotExecutedTimeout:
            return await self._accept_terminal(
                action,
                ActionResult(
                    action.action_id,
                    ActionStatus.TIMED_OUT,
                    None,
                    HardwareError(
                        "ACTION_TIMEOUT",
                        "Adapter confirmed the action did not execute",
                        False,
                        {"outcome_certainty": "confirmed_not_executed"},
                    ),
                    None,
                    self._clock(),
                    False,
                ),
                reason_code="execution_timeout_confirmed_not_executed",
            )
        except TimeoutError:
            return await self._accept_terminal(
                action,
                ActionResult(
                    action.action_id,
                    ActionStatus.RECONCILIATION_REQUIRED,
                    None,
                    HardwareError(
                        "ACTION_TIMEOUT",
                        "The deadline expired after dispatch; physical outcome is unknown",
                        False,
                        {"automatic_retry": False},
                    ),
                    None,
                    self._clock(),
                    False,
                ),
                reason_code="execution_outcome_unknown",
            )

        self._mark("10.output_validate")
        if driver_result.status is ActionStatus.SUCCEEDED:
            try:
                capability.validate_output(driver_result.output)  # type: ignore[arg-type]
            except ValidationError as error:
                return await self._fail_running(
                    action,
                    HardwareError(
                        "OUTPUT_VALIDATION_FAILED",
                        error.message,
                        False,
                        {"path": list(error.absolute_path)},
                    ),
                    started_at=driver_result.started_at,
                )
            if not driver_result.device_acknowledged:
                return await self._fail_running(
                    action,
                    HardwareError(
                        "DRIVER_ERROR",
                        "Successful physical action lacks device acknowledgement",
                        False,
                        {},
                    ),
                    started_at=driver_result.started_at,
                )
            result = ActionResult(
                action.action_id,
                ActionStatus.SUCCEEDED,
                driver_result.output,
                None,
                driver_result.started_at,
                driver_result.finished_at,
                True,
            )
            return await self._accept_terminal(
                action,
                result,
                reason_code="driver_succeeded",
            )

        target = (
            driver_result.status
            if driver_result.status
            in {
                ActionStatus.FAILED,
                ActionStatus.CANCELLED,
                ActionStatus.TIMED_OUT,
                ActionStatus.RECONCILIATION_REQUIRED,
            }
            else ActionStatus.FAILED
        )
        result = ActionResult(
            action.action_id,
            target,
            driver_result.output,
            driver_result.error
            or HardwareError("DRIVER_ERROR", "Driver returned failure", False, {}),
            driver_result.started_at,
            driver_result.finished_at,
            driver_result.device_acknowledged,
        )
        return await self._accept_terminal(
            action,
            result,
            reason_code="driver_result",
        )

    async def cancel(self, action_id: str, *, requester: str) -> ActionResult:
        """Request cancellation; only confirmation can create CANCELLED while running."""
        action = await self._repository.get_action(action_id)
        if action is None:
            return self._operation_error(
                action_id,
                ActionStatus.FAILED,
                "DEVICE_NOT_FOUND",
                "Action not found",
            )
        if requester != action.requester:
            return self._operation_error(
                action_id,
                action.status,
                "ACTION_REJECTED",
                "Requester is not authorized to cancel this action",
            )
        if action.status in {
            ActionStatus.SUCCEEDED,
            ActionStatus.FAILED,
            ActionStatus.REJECTED,
            ActionStatus.TIMED_OUT,
            ActionStatus.CANCELLED,
            ActionStatus.RECONCILIATION_REQUIRED,
        }:
            return self._operation_error(
                action_id,
                action.status,
                "CONFLICT",
                "A terminal action cannot be cancelled",
            )

        if action.status is not ActionStatus.RUNNING:
            return await self._accept_terminal(
                action,
                ActionResult(
                    action_id,
                    ActionStatus.CANCELLED,
                    None,
                    None,
                    None,
                    self._clock(),
                    False,
                ),
                reason_code="cancelled_before_dispatch",
                actor=requester,
            )

        driver = self._active_drivers.get(action_id)
        if driver is None or not await driver.cancel(action_id):
            return self._operation_error(
                action_id,
                ActionStatus.RUNNING,
                "CONFLICT",
                "Cancellation was requested but not confirmed",
            )
        return await self._accept_terminal(
            action,
            ActionResult(
                action_id,
                ActionStatus.CANCELLED,
                None,
                None,
                None,
                self._clock(),
                True,
            ),
            reason_code="driver_cancel_confirmed",
            actor=requester,
        )

    async def _execute_with_deadline(
        self,
        action: HardwareAction,
        driver: DeviceDriver,
    ) -> ActionResult:
        task = asyncio.create_task(driver.execute(action))
        self._active_drivers[action.action_id] = driver
        done, _ = await asyncio.wait(
            {task},
            timeout=action.timeout_ms / 1_000,
        )
        if task not in done:
            watcher = asyncio.create_task(self._record_late_task(action.action_id, task))
            self._background_tasks.add(watcher)
            watcher.add_done_callback(self._background_tasks.discard)
            raise TimeoutError("local execution deadline expired")
        self._active_drivers.pop(action.action_id, None)
        return task.result()

    async def _execute_with_retries(
        self,
        action: HardwareAction,
        driver: DeviceDriver,
        capability: Capability,
    ) -> ActionResult:
        maximum_retries = 2 if capability.idempotency is IdempotencyMode.IDEMPOTENT else 0
        for attempt in range(maximum_retries + 1):
            result = await self._execute_with_deadline(action, driver)
            retryable_failure = (
                result.status is ActionStatus.FAILED
                and result.error is not None
                and result.error.retryable
            )
            if not retryable_failure or attempt == maximum_retries:
                return result
        raise AssertionError("retry loop must return an ActionResult")

    async def _record_late_task(
        self,
        action_id: str,
        task: asyncio.Task[ActionResult],
    ) -> None:
        try:
            result = await task
        except asyncio.CancelledError:
            return
        except Exception as error:
            await self._repository.append_reconciliation(
                {
                    "record_kind": "late_driver_error",
                    "action_id": action_id,
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "observed_at": self._clock().isoformat(),
                }
            )
        else:
            stored = await self._repository.get_action(action_id)
            await self._record_late_result(
                result,
                accepted_status=stored.status if stored is not None else None,
            )
        finally:
            self._active_drivers.pop(action_id, None)

    async def _accept_terminal(
        self,
        action: HardwareAction,
        result: ActionResult,
        *,
        reason_code: str,
        actor: str = "action_executor",
    ) -> ActionResult:
        lock = self._terminal_locks.setdefault(action.action_id, asyncio.Lock())
        async with lock:
            stored = await self._repository.get_action(action.action_id)
            current = stored or action
            if current.status in {
                ActionStatus.SUCCEEDED,
                ActionStatus.FAILED,
                ActionStatus.REJECTED,
                ActionStatus.TIMED_OUT,
                ActionStatus.CANCELLED,
                ActionStatus.RECONCILIATION_REQUIRED,
            }:
                await self._record_late_result(result, accepted_status=current.status)
                winner = await self._repository.get_result(action.action_id)
                return winner or self._operation_error(
                    action.action_id,
                    current.status,
                    "CONFLICT",
                    "Terminal result was already accepted",
                )

            updated = await self._lifecycle.transition(
                current,
                result.status,
                reason_code=reason_code,
                actor=actor,
            )
            await self._repository.save_action(updated)
            if result.status is ActionStatus.RECONCILIATION_REQUIRED:
                await self._repository.append_reconciliation(
                    {
                        "record_kind": "outcome_unknown",
                        "action_id": action.action_id,
                        "automatic_retry": False,
                        "observed_at": self._clock().isoformat(),
                    }
                )
            return await self._finish(updated, result)

    async def _record_late_result(
        self,
        result: ActionResult,
        *,
        accepted_status: ActionStatus | None,
    ) -> None:
        await self._repository.append_reconciliation(
            {
                "record_kind": "late_result",
                "action_id": result.action_id,
                "accepted_status": (
                    accepted_status.value if accepted_status is not None else None
                ),
                "late_result": result.to_dict(),
                "observed_at": self._clock().isoformat(),
            }
        )

    def _operation_error(
        self,
        action_id: str,
        status: ActionStatus,
        code: str,
        message: str,
    ) -> ActionResult:
        return ActionResult(
            action_id,
            status,
            None,
            HardwareError(code, message, False, {}),
            None,
            self._clock(),
            False,
        )

    def _validate_state(
        self,
        action: HardwareAction,
        device: Device,
        capability: Capability,
    ) -> HardwareError | None:
        if device.status is DeviceStatus.DISABLED:
            return HardwareError("DEVICE_DISABLED", "Device is disabled", False, {})
        if device.status not in {DeviceStatus.ONLINE, DeviceStatus.DEGRADED}:
            return HardwareError("DEVICE_OFFLINE", "Device is not online", True, {})
        if not capability.enabled:
            return HardwareError("CAPABILITY_DISABLED", "Capability is disabled", False, {})
        if action.timeout_ms > capability.timeout_ms:
            return HardwareError(
                "INVALID_PARAMETERS",
                "Action timeout exceeds Capability timeout",
                False,
                {},
            )
        if (
            action.expected_device_version is not None
            and action.expected_device_version != device.version
        ):
            return HardwareError("CONFLICT", "Device version does not match", False, {})
        return None

    async def _apply_idempotency(
        self,
        action: HardwareAction,
        capability: Capability,
    ) -> ActionResult | HardwareError | None:
        if capability.idempotency is not IdempotencyMode.KEY_REQUIRED:
            return None
        if action.idempotency_key is None:
            return HardwareError(
                "INVALID_PARAMETERS",
                "idempotency_key is required for this Capability",
                False,
                {},
            )
        scope = {
            "requester": action.requester,
            "device_id": action.device_id,
            "capability_id": action.capability_id,
            "idempotency_key": action.idempotency_key,
        }
        original = await self._repository.get_action_by_idempotency_key(**scope)
        if original is not None:
            if original.parameters_digest != action.parameters_digest:
                return HardwareError(
                    "CONFLICT",
                    "Idempotency key was reused with different parameters",
                    False,
                    {},
                )
            original_result = await self._repository.get_result(original.action_id)
            return original_result or ActionResult(
                original.action_id,
                original.status,
                None,
                None,
                None,
                None,
                False,
            )
        reserved = await self._repository.reserve_idempotency_key(
            **scope,
            parameters_digest=action.parameters_digest,
            action_id=action.action_id,
        )
        if not reserved:
            original = await self._repository.get_action_by_idempotency_key(**scope)
            if original is not None:
                original_result = await self._repository.get_result(original.action_id)
                return original_result or ActionResult(
                    original.action_id,
                    original.status,
                    None,
                    None,
                    None,
                    None,
                    False,
                )
            return HardwareError("CONFLICT", "Idempotency reservation conflict", False, {})
        return None

    async def _fail_validation(
        self,
        action: HardwareAction,
        error: HardwareError,
    ) -> ActionResult:
        action = await self._move(
            action,
            ActionStatus.FAILED,
            reason_code=error.code,
            reason_detail=error.message,
        )
        return await self._finish(
            action,
            ActionResult(
                action.action_id,
                ActionStatus.FAILED,
                None,
                error,
                None,
                self._clock(),
                False,
            ),
        )

    async def _fail_running(
        self,
        action: HardwareAction,
        error: HardwareError,
        *,
        started_at: datetime | None = None,
    ) -> ActionResult:
        return await self._accept_terminal(
            action,
            ActionResult(
                action.action_id,
                ActionStatus.FAILED,
                None,
                error,
                started_at,
                self._clock(),
                False,
            ),
            reason_code=error.code,
        )

    async def _move(
        self,
        action: HardwareAction,
        status: ActionStatus,
        *,
        reason_code: str,
        reason_detail: str | None = None,
    ) -> HardwareAction:
        updated = await self._lifecycle.transition(
            action,
            status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            actor="action_executor",
        )
        await self._repository.save_action(updated)
        return updated

    async def _finish(self, action: HardwareAction, result: ActionResult) -> ActionResult:
        self._mark("11.terminal_persist")
        await self._repository.save_action(action)
        await self._repository.save_result(result)
        await self._audit(action, result)
        self._mark("12.event")
        event = await self._event_builder(action)
        await self._repository.append_event(event)
        await self._event_bus.publish(event)
        self._mark("13.return")
        return result

    async def _audit(self, action: HardwareAction, result: ActionResult) -> None:
        if self._audit_writer is not None:
            await self._audit_writer.record(action, result)

    def _mark(self, step: str) -> None:
        if self._observer is not None:
            self._observer(step)


__all__ = (
    "ActionExecutor",
    "ApprovalCheck",
    "ApprovalValidator",
    "AuditWriter",
    "EventBuilder",
    "ExecutionObserver",
)
