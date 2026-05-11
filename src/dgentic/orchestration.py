"""Backend orchestration control plane for autonomous sprint task graphs."""

import json
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import PurePosixPath
from threading import RLock, Thread
from typing import Any, ParamSpec, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from dgentic.agents import get_agent, spawn_agent, update_agent_status
from dgentic.database import get_db_session
from dgentic.events import event_log
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import MemoryMetadata
from dgentic.memory.schemas import MetadataCreateRequest
from dgentic.orchestration_documents import sync_orchestration_documents
from dgentic.redaction import REDACTED_SECRET_MARKER, redact_sensitive_values
from dgentic.schemas import (
    AgentBrief,
    AgentStatus,
    AgentStatusUpdate,
    LogEventType,
    OrchestrationActionDecision,
    OrchestrationBlocker,
    OrchestrationBlockerResolutionRequest,
    OrchestrationCloseRequest,
    OrchestrationCreateRequest,
    OrchestrationExecution,
    OrchestrationExecutionStatus,
    OrchestrationFollowUp,
    OrchestrationLoopRequest,
    OrchestrationLoopResult,
    OrchestrationOperationsSummary,
    OrchestrationRun,
    OrchestrationTask,
    OrchestrationTaskRecoveryRequest,
    OrchestrationTaskSpec,
    OrchestrationTaskUpdate,
    PlanStatus,
    RoleBoundaryDecision,
    StepStatus,
)
from dgentic.storage import JsonCollection

MAX_READY_TASKS_PER_ADVANCE = 20
MAX_DEPENDENCY_CONTEXT_CHARS = 1200
MAX_CONTEXT_FIELD_CHARS = 1200
MAX_CONTEXT_OUTPUT_ITEMS = 20
MAX_CONTEXT_OUTPUT_DEPTH = 4
MAX_MEMORY_CONTEXT_RESULTS = 3
MAX_MEMORY_CONTEXT_CHARS = 800
MAX_SHARED_MEMORY_TAGS = 20
ORCHESTRATION_MEMORY_CATEGORY = "orchestration_context"
ORCHESTRATION_MEMORY_ENTITY_PREFIX = "orchestration:"
SHARED_MEMORY_SYSTEM_OWNER = "system"
TERMINAL_RUN_STATUSES = {PlanStatus.completed, PlanStatus.failed}
TASK_UPDATE_STATUSES = {StepStatus.completed, StepStatus.failed, StepStatus.blocked}
RECOVERABLE_TASK_BLOCKER_SEVERITIES = {"role_boundary", "retry_exhausted"}
RESOLVABLE_TASK_BLOCKER_SEVERITIES = {"blocked", "security"}
ACTIVE_EXECUTION_STATUSES = {
    OrchestrationExecutionStatus.starting,
    OrchestrationExecutionStatus.running,
    OrchestrationExecutionStatus.cancelling,
}
BACKGROUND_EXECUTION_STALE_AFTER_SECONDS = 300
BACKGROUND_EXECUTION_HEARTBEAT_INTERVAL_SECONDS = 30
SCHEDULER_LEASE_SECONDS = 300
WRITE_FILE_ACTIONS = {
    "write",
    "binary_write",
    "delete",
    "move",
    "copy",
    "rename",
}


class _SchedulerLease(BaseModel):
    id: str
    run_id: str
    supervisor_id: str
    lease_token: str
    execution_id: str | None = None
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class _ScheduleClaim:
    task_id: str
    agent_id: str


class OrchestrationError(ValueError):
    """Raised when an orchestration graph or transition is invalid."""


class OrchestrationContextAuthorizationError(PermissionError):
    """Raised when caller-supplied orchestration agent context is not authorized."""


ParamT = ParamSpec("ParamT")
ReturnT = TypeVar("ReturnT")


def _locked_mutation(
    method: Callable[ParamT, ReturnT],
) -> Callable[ParamT, ReturnT]:
    @wraps(method)
    def wrapped(self, *args: ParamT.args, **kwargs: ParamT.kwargs) -> ReturnT:
        with self._mutation_lock:
            return method(self, *args, **kwargs)

    return wrapped


def _should_mark_background_execution_stale(
    execution: OrchestrationExecution,
    *,
    supervisor_id: str,
    now: datetime,
) -> bool:
    if execution.status not in ACTIVE_EXECUTION_STATUSES:
        return False
    if execution.supervisor_id == supervisor_id:
        return False
    heartbeat_at = execution.last_heartbeat_at or execution.started_at
    stale_before = now - timedelta(seconds=BACKGROUND_EXECUTION_STALE_AFTER_SECONDS)
    return heartbeat_at <= stale_before


class OrchestrationService:
    """Validate, schedule, and track autonomous orchestration task graphs."""

    def __init__(self) -> None:
        self._runs = JsonCollection("orchestrations", OrchestrationRun)
        self._executions = JsonCollection("orchestration-executions", OrchestrationExecution)
        self._scheduler_leases = JsonCollection(
            "orchestration-scheduler-leases",
            _SchedulerLease,
            key_field="run_id",
        )
        self._mutation_lock = RLock()
        self.supervisor_id = f"orchestration-supervisor-{uuid4()}"
        self.resume_stale_background_executions()

    @_locked_mutation
    def create_run(
        self,
        request: OrchestrationCreateRequest,
        *,
        actor: str | None = None,
    ) -> OrchestrationRun:
        tasks = [_task_from_spec(task) for task in request.tasks]
        self._validate_graph(tasks)
        decisions = [_role_boundary_decision(task) for task in tasks]
        tasks_by_id = {task.id: task for task in tasks}
        blockers: list[OrchestrationBlocker] = []
        follow_ups: list[OrchestrationFollowUp] = []

        for decision in decisions:
            if decision.allowed:
                continue
            task = tasks_by_id[decision.task_id]
            tasks_by_id[task.id] = task.model_copy(
                update={
                    "status": StepStatus.blocked,
                    "error": decision.reason,
                }
            )
            blockers.append(_blocker(task.id, decision.reason, severity="role_boundary"))
            follow_ups.append(
                _follow_up(
                    task.id,
                    decision.suggested_owner_role or "PM",
                    f"Reassign out-of-bound work for task {task.id}: {decision.reason}",
                )
            )

        run = OrchestrationRun(
            id=f"orch-{uuid4()}",
            objective=request.objective,
            tasks=list(tasks_by_id.values()),
            required_dod_evidence=request.required_dod_evidence,
            shared_memory_tags=_normalize_shared_memory_tags(request.shared_memory_tags),
            shared_memory_policy=request.shared_memory_policy,
            role_boundary_decisions=decisions,
            blockers=blockers,
            follow_ups=follow_ups,
            requested_by=actor or request.requested_by,
        )
        run = self._persist(run)
        run = self._schedule_ready_tasks(run, actor=actor)
        event_log.record(
            LogEventType.task,
            "Created orchestration run.",
            actor=actor or "system",
            subject_id=run.id,
            metadata={
                "tasks": len(run.tasks),
                "scheduled": run.scheduled_task_ids,
                "blockers": len(run.blockers),
            },
        )
        return run

    def list_runs(
        self,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> list[OrchestrationRun]:
        runs = self._runs.list()
        if actor is None or include_all:
            return runs
        return [run for run in runs if run.requested_by == actor]

    def get_operations_summary(
        self,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationOperationsSummary:
        runs = self.list_runs(actor=actor, include_all=include_all)
        visible_run_ids = {run.id for run in runs}
        now = datetime.now(UTC)
        executions = [
            execution
            for execution in self._executions.list()
            if execution.run_id in visible_run_ids
        ]
        execution_statuses = [
            (
                execution,
                _operations_execution_status(
                    execution,
                    supervisor_id=self.supervisor_id,
                    now=now,
                ),
            )
            for execution in executions
        ]
        active_executions = [
            execution
            for execution, status in execution_statuses
            if status in ACTIVE_EXECUTION_STATUSES
        ]
        stale_executions = [
            execution
            for execution, status in execution_statuses
            if status == OrchestrationExecutionStatus.stale
        ]
        unresolved_blockers = [
            blocker for run in runs for blocker in run.blockers if _is_unresolved_blocker(blocker)
        ]
        blocked_run_ids = [
            run.id
            for run in runs
            if run.status == PlanStatus.failed
            or any(_is_unresolved_blocker(blocker) for blocker in run.blockers)
        ]
        return OrchestrationOperationsSummary(
            total_runs=len(runs),
            run_status_counts=_value_counts(run.status.value for run in runs),
            task_status_counts=_value_counts(
                task.status.value for run in runs for task in run.tasks
            ),
            execution_status_counts=_value_counts(
                status.value for _execution, status in execution_statuses
            ),
            active_execution_count=len(active_executions),
            stale_execution_count=len(stale_executions),
            unresolved_blocker_count=len(unresolved_blockers),
            open_follow_up_count=sum(len(run.follow_ups) for run in runs),
            blocked_run_ids=blocked_run_ids,
            active_execution_ids=[execution.id for execution in active_executions],
            stale_execution_ids=[execution.id for execution in stale_executions],
        )

    def get_run(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun | None:
        run = self._runs.get(run_id)
        if run is None or actor is None or include_all or run.requested_by == actor:
            return run
        return None

    def orchestration_agent_visibility(
        self,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> tuple[set[str], set[str]]:
        visible_agent_ids: set[str] = set()
        orchestration_agent_ids: set[str] = set()
        for run in self._runs.list():
            run_agent_ids = {task.agent_id for task in run.tasks if task.agent_id}
            orchestration_agent_ids.update(run_agent_ids)
            if actor is None or include_all or run.requested_by == actor:
                visible_agent_ids.update(run_agent_ids)
        return visible_agent_ids, orchestration_agent_ids

    @_locked_mutation
    def advance_run(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        return self._schedule_ready_tasks(run, actor=actor)

    @_locked_mutation
    def run_cycle(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
        background_execution_id: str | None = None,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        scheduler_lease_token: str | None = None
        if background_execution_id is not None:
            scheduler_lease_token = self._scheduler_lease_token_for_execution(
                background_execution_id
            )
            self._require_scheduler_lease(run.id, scheduler_lease_token)
        self.reconcile_stale_background_executions()
        active_execution = self._active_background_execution_for_run(run.id)
        if active_execution is not None and active_execution.id != background_execution_id:
            raise OrchestrationError(
                f"Orchestration already has active background execution: {active_execution.id}"
            )
        task_updates = [
            (task.id, update)
            for task in run.tasks
            if task.status == StepStatus.running and task.agent_id
            for update in [_task_update_from_agent_status(task.agent_id)]
            if update is not None
        ]

        if not task_updates:
            return self._schedule_ready_tasks(
                run,
                actor=actor,
                background_execution_id=background_execution_id,
            )

        scheduled_task_ids: list[str] = []
        for task_id, update in task_updates:
            run = self.update_task(
                run.id,
                task_id,
                update,
                actor=actor,
                include_all=include_all,
                background_execution_id=background_execution_id,
                scheduler_lease_token=scheduler_lease_token,
            )
            scheduled_task_ids.extend(
                task_id for task_id in run.scheduled_task_ids if task_id not in scheduled_task_ids
            )
        if scheduled_task_ids != run.scheduled_task_ids:
            run = run.model_copy(update={"scheduled_task_ids": scheduled_task_ids})
        event_log.record(
            LogEventType.task,
            "Ran orchestration execution cycle.",
            actor=actor or "system",
            subject_id=run.id,
            metadata={
                "reconciled_task_ids": [task_id for task_id, _update in task_updates],
                "scheduled": scheduled_task_ids,
            },
        )
        return run

    @_locked_mutation
    def run_loop(
        self,
        run_id: str,
        request: OrchestrationLoopRequest,
        *,
        actor: str | None = None,
        include_all: bool = True,
        background_execution_id: str | None = None,
    ) -> OrchestrationLoopResult:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        self.reconcile_stale_background_executions()
        active_execution = self._active_background_execution_for_run(run.id)
        if active_execution is not None and active_execution.id != background_execution_id:
            raise OrchestrationError(
                f"Orchestration already has active background execution: {active_execution.id}"
            )
        iterations = 0
        made_progress = False
        stopped_reason = _loop_stop_reason(run, stop_on_blocked=request.stop_on_blocked)
        if stopped_reason is None:
            stopped_reason = self._background_execution_cancel_stop_reason(background_execution_id)

        while stopped_reason is None and iterations < request.max_iterations:
            before = _progress_signature(run)
            run = self.run_cycle(
                run.id,
                actor=actor,
                include_all=include_all,
                background_execution_id=background_execution_id,
            )
            iterations += 1
            progressed = _progress_signature(run) != before
            made_progress = made_progress or progressed
            stopped_reason = self._background_execution_cancel_stop_reason(background_execution_id)
            if stopped_reason is None:
                stopped_reason = _loop_stop_reason(run, stop_on_blocked=request.stop_on_blocked)
            if stopped_reason is not None:
                break
            if not progressed:
                stopped_reason = "waiting_for_agents" if _running_task_ids(run) else "quiescent"
                break

        if stopped_reason is None:
            stopped_reason = "max_iterations"

        event_log.record(
            LogEventType.task,
            "Ran orchestration autonomous loop.",
            actor=actor or "system",
            subject_id=run.id,
            metadata={
                "iterations": iterations,
                "made_progress": made_progress,
                "stopped_reason": stopped_reason,
                "running_task_ids": _running_task_ids(run),
                "pending_task_ids": _pending_task_ids(run),
                "unresolved_blocker_ids": [
                    blocker.id for blocker in _unresolved_blockers(run.blockers)
                ],
            },
        )
        return _loop_result(
            run,
            iterations=iterations,
            made_progress=made_progress,
            stopped_reason=stopped_reason,
        )

    @_locked_mutation
    def start_background_execution(
        self,
        run_id: str,
        request: OrchestrationLoopRequest,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationExecution:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        self.reconcile_stale_background_executions()

        now = datetime.now(UTC)
        execution = OrchestrationExecution(
            id=f"orchexec-{uuid4()}",
            run_id=run.id,
            status=OrchestrationExecutionStatus.starting,
            request=request,
            requested_by=actor or run.requested_by,
            supervisor_id=self.supervisor_id,
            status_reason="Orchestration background execution queued.",
            started_at=now,
            last_heartbeat_at=now,
        )
        lease = self._acquire_scheduler_lease(
            run.id,
            execution_id=execution.id,
            actor=actor,
        )
        execution = execution.model_copy(update={"scheduler_lease_id": lease.id})
        try:
            saved = self._claim_background_execution(execution)
        except Exception:
            self._release_scheduler_lease(run.id, lease.lease_token)
            raise
        event_log.record(
            LogEventType.task,
            "Recorded orchestration background execution launch intent.",
            actor=actor or "system",
            subject_id=saved.id,
            metadata={
                "run_id": saved.run_id,
                "supervisor_id": saved.supervisor_id,
                "scheduler_lease_id": lease.id,
                "max_iterations": request.max_iterations,
                "stop_on_blocked": request.stop_on_blocked,
            },
        )
        try:
            self._start_background_worker(saved.id, actor=actor, include_all=include_all)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._finalize_background_execution(
                saved.id,
                status=OrchestrationExecutionStatus.failed,
                status_reason="Orchestration background execution failed to start.",
                error=error,
                actor=actor,
            )
            safe_error = redact_sensitive_values(error)
            raise OrchestrationError(
                f"Failed to start orchestration background execution: {safe_error}"
            ) from exc
        return saved

    def list_background_executions(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> list[OrchestrationExecution]:
        self._require_run(run_id, actor=actor, include_all=include_all)
        self.reconcile_stale_background_executions()
        return [execution for execution in self._executions.list() if execution.run_id == run_id]

    def get_background_execution(
        self,
        run_id: str,
        execution_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationExecution:
        self._require_run(run_id, actor=actor, include_all=include_all)
        self.reconcile_stale_background_executions()
        execution = self._executions.get(execution_id)
        if execution is None or execution.run_id != run_id:
            raise OrchestrationError(
                f"Orchestration background execution not found: {execution_id}"
            )
        return execution

    def cancel_background_execution(
        self,
        run_id: str,
        execution_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationExecution:
        self._require_run(run_id, actor=actor, include_all=include_all)
        self.reconcile_stale_background_executions()
        execution = self._executions.get(execution_id)
        if execution is None or execution.run_id != run_id:
            raise OrchestrationError(
                f"Orchestration background execution not found: {execution_id}"
            )
        if execution.status == OrchestrationExecutionStatus.cancelled:
            return execution
        if execution.status not in ACTIVE_EXECUTION_STATUSES:
            raise OrchestrationError(
                f"Orchestration background execution is not active: {execution_id}"
            )

        saved, previous_status = self._request_background_execution_cancellation(execution_id)
        if saved is None:
            if previous_status is not None:
                raise OrchestrationError(
                    f"Orchestration background execution is not active: {execution_id}"
                )
            raise OrchestrationError(
                f"Orchestration background execution not found: {execution_id}"
            )
        if execution.scheduler_lease_id and saved.status == OrchestrationExecutionStatus.cancelled:
            self._release_scheduler_lease_by_id(run_id, execution.scheduler_lease_id)
        event_log.record(
            LogEventType.task,
            (
                "Cancelled orchestration background execution."
                if saved.status == OrchestrationExecutionStatus.cancelled
                else "Requested orchestration background execution cancellation."
            ),
            actor=actor or "system",
            subject_id=saved.id,
            metadata={
                "run_id": saved.run_id,
                "previous_status": previous_status,
                "status": saved.status,
                "supervisor_id": saved.supervisor_id,
            },
        )
        return saved

    def reconcile_stale_background_executions(self) -> None:
        now = datetime.now(UTC)
        stale_executions = self._executions.transact(
            lambda items: self._mark_stale_background_executions(items, now=now)
        )
        for stale_execution in stale_executions:
            event_log.record(
                LogEventType.task,
                "Marked stale orchestration background execution.",
                subject_id=stale_execution.id,
                metadata={
                    "run_id": stale_execution.run_id,
                    "previous_supervisor_id": stale_execution.supervisor_id,
                    "current_supervisor_id": self.supervisor_id,
                },
            )

    def resume_stale_background_executions(self) -> None:
        now = datetime.now(UTC)
        resumable_run_ids = {
            run.id for run in self._runs.list() if run.status not in TERMINAL_RUN_STATUSES
        }
        adopted_executions, cancelled_executions, stale_executions = self._executions.transact(
            lambda items: self._adopt_stale_background_executions(
                items,
                now=now,
                resumable_run_ids=resumable_run_ids,
            )
        )
        for stale_execution in stale_executions:
            event_log.record(
                LogEventType.task,
                "Marked duplicate stale orchestration background execution during adoption.",
                subject_id=stale_execution.id,
                metadata={
                    "run_id": stale_execution.run_id,
                    "previous_supervisor_id": stale_execution.supervisor_id,
                    "current_supervisor_id": self.supervisor_id,
                },
            )
        for cancelled_execution in cancelled_executions:
            event_log.record(
                LogEventType.task,
                "Cancelled stale orchestration background execution during adoption.",
                subject_id=cancelled_execution.id,
                metadata={
                    "run_id": cancelled_execution.run_id,
                    "previous_supervisor_id": cancelled_execution.supervisor_id,
                    "current_supervisor_id": self.supervisor_id,
                },
            )
        for adopted_execution in adopted_executions:
            event_log.record(
                LogEventType.task,
                "Adopted stale orchestration background execution.",
                actor=adopted_execution.requested_by or "system",
                subject_id=adopted_execution.id,
                metadata={
                    "run_id": adopted_execution.run_id,
                    "supervisor_id": adopted_execution.supervisor_id,
                    "max_iterations": adopted_execution.request.max_iterations,
                    "stop_on_blocked": adopted_execution.request.stop_on_blocked,
                },
            )
            try:
                self._start_background_worker(
                    adopted_execution.id,
                    actor=adopted_execution.requested_by,
                    include_all=True,
                )
            except Exception as exc:
                self._finalize_background_execution(
                    adopted_execution.id,
                    status=OrchestrationExecutionStatus.failed,
                    status_reason="Adopted orchestration background execution failed to start.",
                    error=f"{type(exc).__name__}: {exc}",
                    actor=adopted_execution.requested_by,
                )

    @_locked_mutation
    def update_task(
        self,
        run_id: str,
        task_id: str,
        update: OrchestrationTaskUpdate,
        *,
        actor: str | None = None,
        include_all: bool = True,
        background_execution_id: str | None = None,
        scheduler_lease_token: str | None = None,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        if background_execution_id is not None:
            scheduler_lease_token = (
                scheduler_lease_token
                or self._scheduler_lease_token_for_execution(background_execution_id)
            )
            self._require_scheduler_lease(run.id, scheduler_lease_token)
        base_signature = _progress_signature(run)
        task = _task_by_id(run, task_id)
        _validate_task_update(task, update)
        now = datetime.now(UTC)
        patch = {
            "status": update.status,
            "output": update.output,
            "error": update.error,
            "completed_at": now if update.status == StepStatus.completed else None,
        }
        blockers = list(run.blockers)
        follow_ups = list(run.follow_ups)
        previous_blocker_ids = {blocker.id for blocker in blockers}
        previous_follow_up_ids = {follow_up.id for follow_up in follow_ups}

        if update.status == StepStatus.failed:
            retry_count = task.retry_count + 1
            patch["retry_count"] = retry_count
            if retry_count <= task.retry_limit:
                patch["status"] = StepStatus.pending
                patch["agent_id"] = None
                patch["completed_at"] = None
            else:
                patch["status"] = StepStatus.blocked
                reason = update.error or f"Task {task_id} exceeded retry limit."
                patch["error"] = reason
                blockers.append(_blocker(task_id, reason, severity="retry_exhausted"))
                follow_ups.append(_follow_up(task_id, task.role, reason))
        elif update.status == StepStatus.blocked:
            reason = update.error or f"Task {task_id} was blocked."
            patch["error"] = reason
            blockers.append(_blocker(task_id, reason, severity="blocked"))
            follow_ups.append(_follow_up(task_id, task.role, reason))

        updated_task = task.model_copy(update=patch)
        tasks = [updated_task if existing.id == task_id else existing for existing in run.tasks]
        run = run.model_copy(
            update={
                "tasks": tasks,
                "blockers": blockers,
                "follow_ups": follow_ups,
                "scheduled_task_ids": [],
                "updated_at": now,
            }
        )
        run = self._persist_if_run_unchanged(
            run,
            expected_signature=base_signature,
            scheduler_lease_token=scheduler_lease_token,
        )
        if task.agent_id:
            _update_agent_for_task(task.agent_id, update.status, update.error)
        if updated_task.status == StepStatus.completed:
            self._publish_completed_task_memory(run, _task_by_id(run, updated_task.id), actor=actor)
        if updated_task.status in {StepStatus.completed, StepStatus.pending}:
            run = self._schedule_ready_tasks(
                run,
                actor=actor,
                background_execution_id=background_execution_id,
                skip_foreground_conflict=True,
            )
        _record_task_update_event(
            run,
            task,
            updated_task,
            update,
            previous_blocker_ids=previous_blocker_ids,
            previous_follow_up_ids=previous_follow_up_ids,
            actor=actor,
        )
        return run

    @_locked_mutation
    def recover_task(
        self,
        run_id: str,
        task_id: str,
        request: OrchestrationTaskRecoveryRequest,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        base_signature = _progress_signature(run)
        task = _task_by_id(run, task_id)
        if task.status != StepStatus.blocked:
            raise OrchestrationError(
                f"Cannot recover task {task_id} from {task.status}; "
                "only blocked tasks can be recovered."
            )
        task_blockers = [
            blocker
            for blocker in run.blockers
            if blocker.task_id == task_id and _is_unresolved_blocker(blocker)
        ]
        if not task_blockers:
            raise OrchestrationError(
                f"Cannot recover task {task_id}; no recoverable blockers are recorded."
            )
        unsupported_blockers = [
            blocker
            for blocker in task_blockers
            if blocker.severity not in RECOVERABLE_TASK_BLOCKER_SEVERITIES
        ]
        if unsupported_blockers:
            severities = ", ".join(sorted({blocker.severity for blocker in unsupported_blockers}))
            raise OrchestrationError(
                f"Cannot recover task {task_id}; unresolved blocker severity requires "
                f"separate review: {severities}"
            )

        candidate = task.model_copy(
            update={
                "role": request.role or task.role,
                "declared_write_paths": (
                    list(request.declared_write_paths)
                    if request.declared_write_paths is not None
                    else list(task.declared_write_paths)
                ),
            }
        )
        decision = _role_boundary_decision(candidate)
        if not decision.allowed:
            raise OrchestrationError(
                f"Cannot recover task {task_id}; role-boundary validation still fails."
            )

        patch = {
            "role": candidate.role,
            "declared_write_paths": candidate.declared_write_paths,
            "status": StepStatus.pending,
            "agent_id": None,
            "output": {},
            "error": None,
            "completed_at": None,
        }
        if request.reset_retry_count:
            patch["retry_count"] = 0

        recovered_task = task.model_copy(update=patch)
        tasks = [recovered_task if existing.id == task_id else existing for existing in run.tasks]
        blockers = [
            blocker
            for blocker in run.blockers
            if not (
                blocker.task_id == task_id
                and blocker.severity in RECOVERABLE_TASK_BLOCKER_SEVERITIES
            )
        ]
        follow_ups = [follow_up for follow_up in run.follow_ups if follow_up.task_id != task_id]
        decisions = _replace_role_boundary_decision(run.role_boundary_decisions, decision)
        run = run.model_copy(
            update={
                "tasks": tasks,
                "blockers": blockers,
                "follow_ups": follow_ups,
                "role_boundary_decisions": decisions,
                "updated_at": datetime.now(UTC),
            }
        )
        event_log.record(
            LogEventType.task,
            "Recovered blocked orchestration task.",
            actor=actor or "system",
            subject_id=run.id,
            metadata={
                "task_id": task_id,
                "resolution": redact_sensitive_values(request.resolution),
                "reset_retry_count": request.reset_retry_count,
                "previous_role": _redact_metadata_value(task.role),
                "recovered_role": _redact_metadata_value(recovered_task.role),
                "previous_declared_write_paths": _redact_metadata_values(task.declared_write_paths),
                "recovered_declared_write_paths": _redact_metadata_values(
                    recovered_task.declared_write_paths
                ),
                "role_changed": recovered_task.role != task.role,
                "declared_write_paths_changed": (
                    recovered_task.declared_write_paths != task.declared_write_paths
                ),
            },
        )
        run = self._persist_if_run_unchanged(run, expected_signature=base_signature)
        run = self._schedule_ready_tasks(run, actor=actor)
        return run

    @_locked_mutation
    def resolve_blocker(
        self,
        run_id: str,
        blocker_id: str,
        request: OrchestrationBlockerResolutionRequest,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        base_signature = _progress_signature(run)
        blocker = _blocker_by_id(run, blocker_id)
        if not _is_unresolved_blocker(blocker):
            raise OrchestrationError(f"Blocker is already resolved: {blocker_id}")
        if blocker.severity not in RESOLVABLE_TASK_BLOCKER_SEVERITIES:
            raise OrchestrationError(
                f"Cannot resolve {blocker.severity} blocker through manual review."
            )

        now = datetime.now(UTC)
        resolved_blocker = blocker.model_copy(
            update={
                "status": "resolved",
                "resolved_at": now,
                "resolved_by": actor or "system",
                "resolution": redact_sensitive_values(request.resolution),
            }
        )
        blockers = [
            resolved_blocker if existing.id == blocker_id else existing for existing in run.blockers
        ]
        task = _task_by_id(run, blocker.task_id)
        should_unblock_task = task.status == StepStatus.blocked and not _unresolved_blockers(
            blockers, task_id=task.id
        )
        should_reschedule = request.reschedule and should_unblock_task
        tasks = list(run.tasks)
        follow_ups = list(run.follow_ups)
        if should_unblock_task:
            unblocked_task = task.model_copy(
                update={
                    "status": StepStatus.pending,
                    "agent_id": None,
                    "output": {},
                    "error": None,
                    "completed_at": None,
                }
            )
            tasks = [unblocked_task if existing.id == task.id else existing for existing in tasks]
            follow_ups = [follow_up for follow_up in follow_ups if follow_up.task_id != task.id]

        run = run.model_copy(
            update={
                "tasks": tasks,
                "blockers": blockers,
                "follow_ups": follow_ups,
                "scheduled_task_ids": [],
                "updated_at": now,
            }
        )
        run = self._persist_if_run_unchanged(run, expected_signature=base_signature)
        if should_reschedule:
            run = self._schedule_ready_tasks(run, actor=actor)
        was_rescheduled = blocker.task_id in run.scheduled_task_ids
        event_log.record(
            LogEventType.task,
            "Resolved orchestration blocker.",
            actor=actor or "system",
            subject_id=run.id,
            metadata={
                "blocker_id": blocker_id,
                "task_id": blocker.task_id,
                "severity": blocker.severity,
                "resolution": redact_sensitive_values(request.resolution),
                "reschedule_requested": request.reschedule,
                "task_unblocked": should_unblock_task,
                "rescheduled": was_rescheduled,
            },
        )
        return run

    @_locked_mutation
    def close_run(
        self,
        run_id: str,
        request: OrchestrationCloseRequest,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        evidence = {**run.dod_evidence, **request.evidence}
        incomplete = [task.id for task in run.tasks if task.status != StepStatus.completed]
        if incomplete:
            raise OrchestrationError(
                "Cannot close orchestration with incomplete tasks: " + ", ".join(incomplete)
            )
        if _unresolved_blockers(run.blockers):
            raise OrchestrationError("Cannot close orchestration with unresolved blockers.")
        missing_evidence = [
            gate for gate in run.required_dod_evidence if not str(evidence.get(gate, "")).strip()
        ]
        if missing_evidence:
            raise OrchestrationError(
                "Cannot close orchestration without DoD evidence: " + ", ".join(missing_evidence)
            )

        closed = run.model_copy(
            update={
                "status": PlanStatus.completed,
                "dod_evidence": evidence,
                "updated_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            }
        )
        event_log.record(
            LogEventType.task,
            "Closed orchestration run.",
            actor=actor or "system",
            subject_id=closed.id,
            metadata={"dod_evidence": sorted(evidence)},
        )
        return self._persist(closed)

    def authorize_filesystem_action(
        self,
        *,
        agent_id: str | None,
        agent_role: str | None,
        task_id: str | None,
        action: str,
        paths: list[str],
    ) -> OrchestrationActionDecision:
        if not any([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=True,
                reason="No orchestration context was supplied.",
            )
        if not all([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    "Orchestration-bound filesystem actions require "
                    "agent_id, agent_role, and task_id."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )

        for run in self._runs.list():
            if run.status in TERMINAL_RUN_STATUSES:
                continue
            for task in run.tasks:
                if task.id != task_id or task.agent_id != agent_id:
                    continue
                return _authorize_task_filesystem_action(
                    run,
                    task,
                    agent_role=agent_role or "",
                    action=action,
                    paths=paths,
                )

        return OrchestrationActionDecision(
            allowed=False,
            reason="No running orchestration task matches the supplied agent context.",
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )

    def authorize_cli_action(
        self,
        *,
        agent_id: str | None,
        agent_role: str | None,
        task_id: str | None,
    ) -> OrchestrationActionDecision:
        return self._authorize_task_context_action(
            action_label="CLI",
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )

    def authorize_tool_action(
        self,
        *,
        agent_id: str | None,
        agent_role: str | None,
        task_id: str | None,
    ) -> OrchestrationActionDecision:
        return self._authorize_task_context_action(
            action_label="Tool",
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )

    def authorize_provider_action(
        self,
        *,
        agent_id: str | None,
        agent_role: str | None,
        task_id: str | None,
    ) -> OrchestrationActionDecision:
        return self._authorize_task_context_action(
            action_label="Provider",
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )

    def authorize_network_action(
        self,
        *,
        agent_id: str | None,
        agent_role: str | None,
        task_id: str | None,
    ) -> OrchestrationActionDecision:
        return self._authorize_task_context_action(
            action_label="Network",
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )

    def _authorize_task_context_action(
        self,
        *,
        action_label: str,
        agent_id: str | None,
        agent_role: str | None,
        task_id: str | None,
    ) -> OrchestrationActionDecision:
        context_label = action_label if action_label.isupper() else action_label.lower()
        if not any([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=True,
                reason="No orchestration context was supplied.",
            )

        all_runs = self._runs.list()
        open_runs = [run for run in all_runs if run.status not in TERMINAL_RUN_STATUSES]
        known_context_tasks = [
            (run, task)
            for run in all_runs
            for task in run.tasks
            if (agent_id is not None and task.agent_id == agent_id) or task.id == task_id
        ]
        relevant_tasks = [
            (run, task)
            for run in open_runs
            for task in run.tasks
            if task.status == StepStatus.running
            and ((agent_id is not None and task.agent_id == agent_id) or task.id == task_id)
        ]
        has_active_tasks = any(
            task.status == StepStatus.running for run in open_runs for task in run.tasks
        )
        if known_context_tasks and not relevant_tasks:
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    f"Supplied {context_label} agent context matches an orchestration "
                    "task that is not running."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not relevant_tasks and has_active_tasks and not all([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    f"Orchestration-bound {action_label} actions require "
                    "agent_id, agent_role, and task_id."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not relevant_tasks and has_active_tasks:
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    f"Supplied {action_label} agent context does not match any "
                    "running orchestration task."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not relevant_tasks:
            return OrchestrationActionDecision(
                allowed=True,
                reason=f"No active orchestration task matched supplied {context_label} context.",
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not all([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    f"Orchestration-bound {action_label} actions require "
                    "agent_id, agent_role, and task_id."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )

        for run, task in relevant_tasks:
            if task.id == task_id and task.agent_id == agent_id:
                if _normalize_role(task.role) != _normalize_role(agent_role or ""):
                    return OrchestrationActionDecision(
                        allowed=False,
                        reason=(
                            f"Agent role {agent_role} does not match orchestration "
                            f"task role {task.role}."
                        ),
                        run_id=run.id,
                        task_id=task.id,
                        agent_id=agent_id,
                        agent_role=agent_role,
                    )
                return OrchestrationActionDecision(
                    allowed=True,
                    reason=f"{action_label} action is bound to a running orchestration task.",
                    run_id=run.id,
                    task_id=task.id,
                    agent_id=agent_id,
                    agent_role=agent_role,
                )

        return OrchestrationActionDecision(
            allowed=False,
            reason=(
                f"Supplied {action_label} agent context does not match the "
                "running orchestration task."
            ),
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )

    def _require_run(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self.get_run(run_id, actor=actor, include_all=include_all)
        if run is None:
            raise OrchestrationError(f"Orchestration not found: {run_id}")
        return run

    def _claim_background_execution(
        self,
        execution: OrchestrationExecution,
    ) -> OrchestrationExecution:
        def claim(
            items: list[OrchestrationExecution],
        ) -> tuple[list[OrchestrationExecution], OrchestrationExecution]:
            active_execution = next(
                (
                    item
                    for item in items
                    if item.run_id == execution.run_id and item.status in ACTIVE_EXECUTION_STATUSES
                ),
                None,
            )
            if active_execution is not None:
                raise OrchestrationError(
                    f"Orchestration already has active background execution: {active_execution.id}"
                )
            return [*items, execution], execution

        return self._executions.transact(claim)

    def _active_background_execution_for_run(
        self,
        run_id: str,
    ) -> OrchestrationExecution | None:
        return next(
            (
                execution
                for execution in self._executions.list()
                if execution.run_id == run_id and execution.status in ACTIVE_EXECUTION_STATUSES
            ),
            None,
        )

    def _mark_stale_background_executions(
        self,
        executions: list[OrchestrationExecution],
        *,
        now: datetime,
    ) -> tuple[list[OrchestrationExecution], list[OrchestrationExecution]]:
        stale_executions: list[OrchestrationExecution] = []
        updated_executions: list[OrchestrationExecution] = []
        for execution in executions:
            if not _should_mark_background_execution_stale(
                execution,
                supervisor_id=self.supervisor_id,
                now=now,
            ) and not self._background_execution_lost_scheduler_lease(execution, now=now):
                updated_executions.append(execution)
                continue
            stale_execution = execution.model_copy(
                update={
                    "status": OrchestrationExecutionStatus.stale,
                    "status_reason": ("Background execution supervisor heartbeat expired."),
                    "scheduler_lease_id": None,
                    "completed_at": now,
                    "last_heartbeat_at": now,
                }
            )
            stale_executions.append(stale_execution)
            updated_executions.append(stale_execution)
        return updated_executions, stale_executions

    def _background_execution_lost_scheduler_lease(
        self,
        execution: OrchestrationExecution,
        *,
        now: datetime,
    ) -> bool:
        if (
            execution.status not in ACTIVE_EXECUTION_STATUSES
            or execution.supervisor_id != self.supervisor_id
            or not execution.scheduler_lease_id
        ):
            return False
        lease = self._scheduler_leases.get(execution.run_id)
        return (
            lease is None
            or lease.id != execution.scheduler_lease_id
            or lease.execution_id != execution.id
            or lease.supervisor_id != self.supervisor_id
            or lease.expires_at <= now
        )

    def _adopt_stale_background_executions(
        self,
        executions: list[OrchestrationExecution],
        *,
        now: datetime,
        resumable_run_ids: set[str],
    ) -> tuple[
        list[OrchestrationExecution],
        tuple[
            list[OrchestrationExecution],
            list[OrchestrationExecution],
            list[OrchestrationExecution],
        ],
    ]:
        adopted_executions: list[OrchestrationExecution] = []
        cancelled_executions: list[OrchestrationExecution] = []
        stale_executions: list[OrchestrationExecution] = []
        adopted_run_ids: set[str] = set()
        updated_executions: list[OrchestrationExecution] = []
        for execution in executions:
            if not _should_mark_background_execution_stale(
                execution,
                supervisor_id=self.supervisor_id,
                now=now,
            ):
                updated_executions.append(execution)
                continue
            if execution.status == OrchestrationExecutionStatus.cancelling:
                cancelled_execution = execution.model_copy(
                    update={
                        "status": OrchestrationExecutionStatus.cancelled,
                        "status_reason": (
                            "Orchestration background execution cancelled after restart."
                        ),
                        "error": None,
                        "scheduler_lease_id": None,
                        "completed_at": now,
                        "last_heartbeat_at": now,
                    }
                )
                cancelled_executions.append(cancelled_execution)
                updated_executions.append(cancelled_execution)
                continue
            if execution.run_id not in resumable_run_ids:
                stale_execution = execution.model_copy(
                    update={
                        "status": OrchestrationExecutionStatus.stale,
                        "status_reason": (
                            "Stale background execution skipped because the run is not resumable."
                        ),
                        "scheduler_lease_id": None,
                        "completed_at": now,
                        "last_heartbeat_at": now,
                    }
                )
                stale_executions.append(stale_execution)
                updated_executions.append(stale_execution)
                continue
            if execution.run_id in adopted_run_ids:
                stale_execution = execution.model_copy(
                    update={
                        "status": OrchestrationExecutionStatus.stale,
                        "status_reason": (
                            "Duplicate stale background execution skipped during adoption."
                        ),
                        "scheduler_lease_id": None,
                        "completed_at": now,
                        "last_heartbeat_at": now,
                    }
                )
                stale_executions.append(stale_execution)
                updated_executions.append(stale_execution)
                continue
            adopted_execution = execution.model_copy(
                update={
                    "status": OrchestrationExecutionStatus.starting,
                    "supervisor_id": self.supervisor_id,
                    "status_reason": ("Orchestration background execution adopted after restart."),
                    "error": None,
                    "scheduler_lease_id": None,
                    "completed_at": None,
                    "last_heartbeat_at": now,
                }
            )
            adopted_run_ids.add(execution.run_id)
            adopted_executions.append(adopted_execution)
            updated_executions.append(adopted_execution)
        return updated_executions, (adopted_executions, cancelled_executions, stale_executions)

    def _start_background_worker(
        self,
        execution_id: str,
        *,
        actor: str | None,
        include_all: bool,
    ) -> None:
        worker = Thread(
            target=self._run_background_execution,
            args=(execution_id, actor, include_all),
            daemon=True,
        )
        worker.start()

    def _run_background_execution(
        self,
        execution_id: str,
        actor: str | None,
        include_all: bool,
    ) -> None:
        try:
            execution = self._mark_background_execution_running(execution_id, actor=actor)
        except Exception as exc:
            self._finalize_background_execution(
                execution_id,
                status=OrchestrationExecutionStatus.failed,
                status_reason="Orchestration background execution failed before starting.",
                error=f"{type(exc).__name__}: {exc}",
                actor=actor,
            )
            return
        if execution is None:
            return
        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_background_execution,
            args=(execution.id, stop_heartbeat),
            daemon=True,
        )
        try:
            heartbeat_thread.start()
        except Exception as exc:
            self._finalize_background_execution(
                execution_id,
                status=OrchestrationExecutionStatus.failed,
                status_reason="Orchestration background execution heartbeat failed to start.",
                error=f"{type(exc).__name__}: {exc}",
                actor=actor,
            )
            return
        try:
            result = self.run_loop(
                execution.run_id,
                execution.request,
                actor=actor,
                include_all=include_all,
                background_execution_id=execution.id,
            )
        except OrchestrationError as exc:
            self._finalize_background_execution(
                execution_id,
                status=OrchestrationExecutionStatus.failed,
                status_reason="Orchestration background execution failed.",
                error=str(exc),
                actor=actor,
            )
        except Exception as exc:
            self._finalize_background_execution(
                execution_id,
                status=OrchestrationExecutionStatus.failed,
                status_reason="Orchestration background execution failed unexpectedly.",
                error=f"{type(exc).__name__}: {exc}",
                actor=actor,
            )
        else:
            final_status = (
                OrchestrationExecutionStatus.cancelled
                if result.stopped_reason == "cancelled"
                or self._background_execution_cancel_requested(execution_id)
                else OrchestrationExecutionStatus.completed
            )
            self._finalize_background_execution(
                execution_id,
                status=final_status,
                status_reason=(
                    "Orchestration background execution cancelled."
                    if final_status == OrchestrationExecutionStatus.cancelled
                    else f"Orchestration background execution stopped: {result.stopped_reason}."
                ),
                result=result,
                actor=actor,
            )
        finally:
            stop_heartbeat.set()

    def _heartbeat_background_execution(
        self,
        execution_id: str,
        stop_heartbeat: threading.Event,
    ) -> None:
        while not stop_heartbeat.wait(BACKGROUND_EXECUTION_HEARTBEAT_INTERVAL_SECONDS):
            if self._renew_background_execution_heartbeat(execution_id) is None:
                return

    def _renew_background_execution_heartbeat(
        self,
        execution_id: str,
    ) -> OrchestrationExecution | None:
        current_execution = self._executions.get(execution_id)
        if (
            current_execution is None
            or current_execution.status not in ACTIVE_EXECUTION_STATUSES
            or current_execution.supervisor_id != self.supervisor_id
        ):
            return None
        if (
            current_execution.scheduler_lease_id
            and self._renew_scheduler_lease_for_execution(current_execution) is None
        ):
            return None

        def heartbeat(
            items: list[OrchestrationExecution],
        ) -> tuple[list[OrchestrationExecution], OrchestrationExecution | None]:
            now = datetime.now(UTC)
            updated_items: list[OrchestrationExecution] = []
            saved: OrchestrationExecution | None = None
            for execution in items:
                if execution.id != execution_id:
                    updated_items.append(execution)
                    continue
                if (
                    execution.status not in ACTIVE_EXECUTION_STATUSES
                    or execution.supervisor_id != self.supervisor_id
                ):
                    updated_items.append(execution)
                    continue
                saved = execution.model_copy(update={"last_heartbeat_at": now})
                updated_items.append(saved)
            return updated_items, saved

        return self._executions.transact(heartbeat)

    def _background_execution_cancel_stop_reason(
        self,
        execution_id: str | None,
    ) -> str | None:
        if execution_id is None:
            return None
        return "cancelled" if self._background_execution_cancel_requested(execution_id) else None

    def _background_execution_cancel_requested(
        self,
        execution_id: str,
    ) -> bool:
        execution = self._executions.get(execution_id)
        return execution is not None and execution.status in {
            OrchestrationExecutionStatus.cancelling,
            OrchestrationExecutionStatus.cancelled,
        }

    def _request_background_execution_cancellation(
        self,
        execution_id: str,
    ) -> tuple[OrchestrationExecution | None, OrchestrationExecutionStatus | None]:
        def cancel(
            items: list[OrchestrationExecution],
        ) -> tuple[
            list[OrchestrationExecution],
            tuple[OrchestrationExecution | None, OrchestrationExecutionStatus | None],
        ]:
            now = datetime.now(UTC)
            updated_items: list[OrchestrationExecution] = []
            saved: OrchestrationExecution | None = None
            previous_status: OrchestrationExecutionStatus | None = None
            for execution in items:
                if execution.id != execution_id:
                    updated_items.append(execution)
                    continue
                previous_status = execution.status
                if execution.status == OrchestrationExecutionStatus.starting:
                    saved = execution.model_copy(
                        update={
                            "status": OrchestrationExecutionStatus.cancelled,
                            "status_reason": (
                                "Orchestration background execution cancelled before start."
                            ),
                            "error": None,
                            "scheduler_lease_id": None,
                            "completed_at": now,
                            "last_heartbeat_at": now,
                        }
                    )
                elif execution.status == OrchestrationExecutionStatus.running:
                    saved = execution.model_copy(
                        update={
                            "status": OrchestrationExecutionStatus.cancelling,
                            "status_reason": (
                                "Orchestration background execution cancellation requested."
                            ),
                            "error": None,
                            "last_heartbeat_at": now,
                        }
                    )
                elif execution.status == OrchestrationExecutionStatus.cancelling:
                    saved = execution
                else:
                    saved = None
                updated_items.append(saved or execution)
            return updated_items, (saved, previous_status)

        return self._executions.transact(cancel)

    def _mark_background_execution_running(
        self,
        execution_id: str,
        *,
        actor: str | None,
    ) -> OrchestrationExecution | None:
        current_execution = self._executions.get(execution_id)
        if (
            current_execution is None
            or current_execution.status != OrchestrationExecutionStatus.starting
            or current_execution.supervisor_id != self.supervisor_id
        ):
            return None
        lease = self._scheduler_lease_for_execution(current_execution)
        if lease is None:
            lease = self._acquire_scheduler_lease(
                current_execution.run_id,
                execution_id=execution_id,
                actor=actor,
            )

        def mark_running(
            items: list[OrchestrationExecution],
        ) -> tuple[list[OrchestrationExecution], OrchestrationExecution | None]:
            now = datetime.now(UTC)
            updated_items: list[OrchestrationExecution] = []
            saved: OrchestrationExecution | None = None
            for execution in items:
                if execution.id != execution_id:
                    updated_items.append(execution)
                    continue
                if (
                    execution.status != OrchestrationExecutionStatus.starting
                    or execution.supervisor_id != self.supervisor_id
                ):
                    updated_items.append(execution)
                    continue
                saved = execution.model_copy(
                    update={
                        "status": OrchestrationExecutionStatus.running,
                        "status_reason": "Orchestration background execution is running.",
                        "scheduler_lease_id": lease.id,
                        "last_heartbeat_at": now,
                    }
                )
                updated_items.append(saved)
            return updated_items, saved

        saved = self._executions.transact(mark_running)
        if saved is None:
            self._release_scheduler_lease(current_execution.run_id, lease.lease_token)
            return None
        event_log.record(
            LogEventType.task,
            "Started orchestration background execution.",
            actor=actor or "system",
            subject_id=saved.id,
            metadata={
                "run_id": saved.run_id,
                "supervisor_id": saved.supervisor_id,
                "scheduler_lease_id": lease.id,
            },
        )
        return saved

    def _finalize_background_execution(
        self,
        execution_id: str,
        *,
        status: OrchestrationExecutionStatus,
        status_reason: str,
        actor: str | None,
        result: OrchestrationLoopResult | None = None,
        error: str | None = None,
    ) -> OrchestrationExecution | None:
        def finalize(
            items: list[OrchestrationExecution],
        ) -> tuple[list[OrchestrationExecution], OrchestrationExecution | None]:
            now = datetime.now(UTC)
            updated_items: list[OrchestrationExecution] = []
            saved: OrchestrationExecution | None = None
            for execution in items:
                if execution.id != execution_id:
                    updated_items.append(execution)
                    continue
                if (
                    execution.status not in ACTIVE_EXECUTION_STATUSES
                    or execution.supervisor_id != self.supervisor_id
                ):
                    updated_items.append(execution)
                    continue
                if execution.scheduler_lease_id and not self._scheduler_lease_matches(
                    execution.run_id,
                    execution.scheduler_lease_id,
                ):
                    saved = execution.model_copy(
                        update={
                            "status": OrchestrationExecutionStatus.stale,
                            "result": None,
                            "status_reason": (
                                "Background execution lost its scheduler lease before finalizing."
                            ),
                            "error": None,
                            "scheduler_lease_id": None,
                            "completed_at": now,
                            "last_heartbeat_at": now,
                        }
                    )
                    updated_items.append(saved)
                    continue
                resolved_status = (
                    OrchestrationExecutionStatus.cancelled
                    if execution.status == OrchestrationExecutionStatus.cancelling
                    else status
                )
                resolved_reason = (
                    "Orchestration background execution cancelled."
                    if resolved_status == OrchestrationExecutionStatus.cancelled
                    else status_reason
                )
                saved = execution.model_copy(
                    update={
                        "status": resolved_status,
                        "result": result,
                        "status_reason": resolved_reason,
                        "error": redact_sensitive_values(error) if error else None,
                        "completed_at": now,
                        "last_heartbeat_at": now,
                    }
                )
                updated_items.append(saved)
            return updated_items, saved

        saved = self._executions.transact(finalize)
        if saved is None:
            return None
        if saved.scheduler_lease_id:
            self._release_scheduler_lease_by_id(saved.run_id, saved.scheduler_lease_id)
        event_log.record(
            LogEventType.task,
            (
                "Failed orchestration background execution."
                if saved.status == OrchestrationExecutionStatus.failed
                else "Cancelled orchestration background execution."
                if saved.status == OrchestrationExecutionStatus.cancelled
                else "Completed orchestration background execution."
            ),
            actor=actor or "system",
            subject_id=saved.id,
            metadata={
                "run_id": saved.run_id,
                "status": saved.status,
                "status_reason": saved.status_reason,
                "error": saved.error,
                "iterations": result.iterations if result else None,
                "stopped_reason": result.stopped_reason if result else None,
            },
        )
        return saved

    def _publish_completed_task_memory(
        self,
        run: OrchestrationRun,
        task: OrchestrationTask,
        *,
        actor: str | None,
    ) -> None:
        tags = _shared_memory_tags(run, task)
        if not tags:
            return

        session = None
        try:
            session = get_db_session()
            metadata = MetadataService(session).upsert_by_entity(
                MetadataCreateRequest(
                    entity_type="memory",
                    entity_id=_task_memory_entity_id(run, task),
                    tags=tags,
                    category=ORCHESTRATION_MEMORY_CATEGORY,
                    description=_completed_task_memory_description(run, task),
                    relevance_score=0.75,
                    retention_policy="automatic",
                    owner_agent=_shared_memory_owner(run),
                )
            )
        except Exception as exc:
            if session is not None:
                session.rollback()
            event_log.record(
                LogEventType.memory,
                "Failed to publish orchestration shared memory.",
                actor=actor or "system",
                subject_id=run.id,
                metadata={
                    "task_id": _redact_metadata_value(task.id),
                    "tags": _redact_metadata_values(tags),
                    "error_type": type(exc).__name__,
                    "error": redact_sensitive_values(str(exc)),
                },
            )
        else:
            event_log.record(
                LogEventType.memory,
                "Published orchestration shared memory.",
                actor=actor or "system",
                subject_id=str(metadata.id),
                metadata={
                    "run_id": run.id,
                    "task_id": _redact_metadata_value(task.id),
                    "entity_id": metadata.entity_id,
                    "owner_agent": _redact_metadata_value(metadata.owner_agent or ""),
                    "tags": _redact_metadata_values(tags),
                },
            )
        finally:
            if session is not None:
                session.close()

    def _acquire_scheduler_lease(
        self,
        run_id: str,
        *,
        execution_id: str | None = None,
        actor: str | None = None,
    ) -> _SchedulerLease:
        now = datetime.now(UTC)
        if execution_id is None:
            self.reconcile_stale_background_executions()
            active_execution = self._active_background_execution_for_run(run_id)
            if active_execution is not None:
                raise OrchestrationError(
                    f"Orchestration already has active background execution: {active_execution.id}"
                )
        lease = _SchedulerLease(
            id=f"orchlease-{uuid4()}",
            run_id=run_id,
            supervisor_id=self.supervisor_id,
            execution_id=execution_id,
            lease_token=f"orchlease-token-{uuid4()}",
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=SCHEDULER_LEASE_SECONDS),
        )

        def claim(
            items: list[_SchedulerLease],
        ) -> tuple[list[_SchedulerLease], _SchedulerLease]:
            updated_items: list[_SchedulerLease] = []
            replaced = False
            for existing in items:
                if existing.run_id != run_id:
                    updated_items.append(existing)
                    continue
                if existing.expires_at > now:
                    holder = existing.execution_id or existing.supervisor_id
                    raise OrchestrationError(
                        f"Orchestration scheduler lease is active for run {run_id}: {holder}"
                    )
                updated_items.append(lease)
                replaced = True
            if not replaced:
                updated_items.append(lease)
            return updated_items, lease

        saved = self._scheduler_leases.transact(claim)
        event_log.record(
            LogEventType.task,
            "Acquired orchestration scheduler lease.",
            actor=actor or "system",
            subject_id=run_id,
            metadata={
                "lease_id": saved.id,
                "supervisor_id": saved.supervisor_id,
                "execution_id": saved.execution_id,
                "expires_at": saved.expires_at.isoformat(),
            },
        )
        return saved

    def _require_scheduler_lease(
        self,
        run_id: str,
        lease_token: str | None,
    ) -> _SchedulerLease:
        if lease_token is None:
            raise OrchestrationError(f"Orchestration scheduler lease is missing for run {run_id}.")
        lease = self._scheduler_leases.get(run_id)
        now = datetime.now(UTC)
        if lease is None or lease.lease_token != lease_token or lease.expires_at <= now:
            raise OrchestrationError(
                f"Orchestration scheduler lease is no longer active for run {run_id}."
            )
        return lease

    def _release_scheduler_lease(
        self,
        run_id: str,
        lease_token: str,
    ) -> None:
        def release(
            items: list[_SchedulerLease],
        ) -> tuple[list[_SchedulerLease], _SchedulerLease | None]:
            released: _SchedulerLease | None = None
            updated_items: list[_SchedulerLease] = []
            for lease in items:
                if lease.run_id == run_id and lease.lease_token == lease_token:
                    released = lease
                    continue
                updated_items.append(lease)
            return updated_items, released

        released = self._scheduler_leases.transact(release)
        if released is None:
            return
        event_log.record(
            LogEventType.task,
            "Released orchestration scheduler lease.",
            subject_id=run_id,
            metadata={
                "lease_id": released.id,
                "supervisor_id": released.supervisor_id,
                "execution_id": released.execution_id,
            },
        )

    def _release_scheduler_lease_by_id(
        self,
        run_id: str,
        lease_id: str,
    ) -> None:
        lease = self._scheduler_leases.get(run_id)
        if lease is None or lease.id != lease_id:
            return
        self._release_scheduler_lease(run_id, lease.lease_token)

    def _renew_scheduler_lease(
        self,
        run_id: str,
        lease_token: str,
    ) -> _SchedulerLease | None:
        def renew(
            items: list[_SchedulerLease],
        ) -> tuple[list[_SchedulerLease], _SchedulerLease | None]:
            now = datetime.now(UTC)
            updated_items: list[_SchedulerLease] = []
            saved: _SchedulerLease | None = None
            for lease in items:
                if lease.run_id != run_id or lease.lease_token != lease_token:
                    updated_items.append(lease)
                    continue
                if lease.expires_at <= now or lease.supervisor_id != self.supervisor_id:
                    updated_items.append(lease)
                    continue
                saved = lease.model_copy(
                    update={
                        "heartbeat_at": now,
                        "expires_at": now + timedelta(seconds=SCHEDULER_LEASE_SECONDS),
                    }
                )
                updated_items.append(saved)
            return updated_items, saved

        return self._scheduler_leases.transact(renew)

    def _renew_scheduler_lease_for_execution(
        self,
        execution: OrchestrationExecution,
    ) -> _SchedulerLease | None:
        lease = self._scheduler_lease_for_execution(execution)
        if lease is None:
            return None
        return self._renew_scheduler_lease(execution.run_id, lease.lease_token)

    def _scheduler_lease_for_execution(
        self,
        execution: OrchestrationExecution,
    ) -> _SchedulerLease | None:
        lease = self._scheduler_leases.get(execution.run_id)
        if (
            lease is None
            or lease.id != execution.scheduler_lease_id
            or lease.execution_id != execution.id
            or lease.supervisor_id != self.supervisor_id
            or lease.expires_at <= datetime.now(UTC)
        ):
            return None
        return lease

    def _scheduler_lease_matches(
        self,
        run_id: str,
        lease_id: str,
    ) -> bool:
        lease = self._scheduler_leases.get(run_id)
        return (
            lease is not None
            and lease.id == lease_id
            and lease.supervisor_id == self.supervisor_id
            and lease.expires_at > datetime.now(UTC)
        )

    def _scheduler_lease_token_for_execution(self, execution_id: str | None) -> str:
        if execution_id is None:
            raise OrchestrationError("Background scheduler execution id is missing.")
        execution = self._executions.get(execution_id)
        if (
            execution is None
            or execution.status not in ACTIVE_EXECUTION_STATUSES
            or execution.supervisor_id != self.supervisor_id
            or not execution.scheduler_lease_id
        ):
            raise OrchestrationError(
                f"Background execution does not hold the scheduler lease: {execution_id}"
            )
        lease = self._scheduler_leases.get(execution.run_id)
        if (
            lease is None
            or lease.id != execution.scheduler_lease_id
            or lease.execution_id != execution.id
            or lease.supervisor_id != self.supervisor_id
            or lease.expires_at <= datetime.now(UTC)
        ):
            raise OrchestrationError(
                f"Background execution does not hold the scheduler lease: {execution_id}"
            )
        return lease.lease_token

    def _claim_ready_tasks_for_schedule(
        self,
        run_id: str,
        lease_token: str,
    ) -> tuple[OrchestrationRun, list[_ScheduleClaim], list[str]]:
        self._require_scheduler_lease(run_id, lease_token)

        def claim(
            items: list[OrchestrationRun],
        ) -> tuple[
            list[OrchestrationRun],
            tuple[OrchestrationRun, list[_ScheduleClaim], list[str]],
        ]:
            self._require_scheduler_lease(run_id, lease_token)
            now = datetime.now(UTC)
            updated_items: list[OrchestrationRun] = []
            saved: OrchestrationRun | None = None
            claims: list[_ScheduleClaim] = []
            scheduled_task_ids: list[str] = []
            for candidate in items:
                if candidate.id != run_id:
                    updated_items.append(candidate)
                    continue
                _ensure_run_open(candidate)
                tasks_by_id = {task.id: task for task in candidate.tasks}
                updated_tasks: list[OrchestrationTask] = []
                for task in candidate.tasks:
                    if (
                        len(scheduled_task_ids) < MAX_READY_TASKS_PER_ADVANCE
                        and task.status == StepStatus.pending
                        and all(
                            tasks_by_id[dependency].status == StepStatus.completed
                            for dependency in task.dependencies
                        )
                    ):
                        agent_id = task.agent_id or f"agent-{uuid4()}"
                        updated_tasks.append(
                            task.model_copy(
                                update={"status": StepStatus.running, "agent_id": agent_id}
                            )
                        )
                        claims.append(_ScheduleClaim(task_id=task.id, agent_id=agent_id))
                        scheduled_task_ids.append(task.id)
                        continue
                    if (
                        task.status == StepStatus.running
                        and task.agent_id
                        and get_agent(task.agent_id) is None
                    ):
                        claims.append(_ScheduleClaim(task_id=task.id, agent_id=task.agent_id))
                    updated_tasks.append(task)
                saved = candidate.model_copy(
                    update={
                        "tasks": updated_tasks,
                        "scheduled_task_ids": scheduled_task_ids,
                        "updated_at": now,
                    }
                )
                updated_items.append(saved)
            if saved is None:
                raise OrchestrationError(f"Orchestration not found: {run_id}")
            return updated_items, (saved, claims, scheduled_task_ids)

        return self._runs.transact(claim)

    def _rollback_unspawned_schedule_claims(
        self,
        run_id: str,
        claims: list[_ScheduleClaim],
        *,
        spawned_agent_ids: set[str],
    ) -> OrchestrationRun:
        unspawned_agent_ids = {
            claim.agent_id for claim in claims if claim.agent_id not in spawned_agent_ids
        }
        if not unspawned_agent_ids:
            current = self._runs.get(run_id)
            if current is None:
                raise OrchestrationError(f"Orchestration not found: {run_id}")
            return current

        def rollback(
            items: list[OrchestrationRun],
        ) -> tuple[list[OrchestrationRun], OrchestrationRun]:
            updated_items: list[OrchestrationRun] = []
            saved: OrchestrationRun | None = None
            for candidate in items:
                if candidate.id != run_id:
                    updated_items.append(candidate)
                    continue
                tasks: list[OrchestrationTask] = []
                for task in candidate.tasks:
                    if task.status == StepStatus.running and task.agent_id in unspawned_agent_ids:
                        tasks.append(
                            task.model_copy(update={"status": StepStatus.pending, "agent_id": None})
                        )
                    else:
                        tasks.append(task)
                saved = candidate.model_copy(
                    update={
                        "tasks": tasks,
                        "scheduled_task_ids": [
                            task_id
                            for task_id in candidate.scheduled_task_ids
                            if _task_by_id(candidate, task_id).agent_id not in unspawned_agent_ids
                        ],
                        "updated_at": datetime.now(UTC),
                    }
                )
                updated_items.append(saved)
            if saved is None:
                raise OrchestrationError(f"Orchestration not found: {run_id}")
            return updated_items, saved

        return self._runs.transact(rollback)

    def _persist(self, run: OrchestrationRun) -> OrchestrationRun:
        run = run.model_copy(update={"updated_at": datetime.now(UTC)})
        saved = self._runs.upsert(run)
        self._sync_project_documents(saved)
        return saved

    def _persist_if_run_unchanged(
        self,
        run: OrchestrationRun,
        *,
        expected_signature: str,
        scheduler_lease_token: str | None = None,
    ) -> OrchestrationRun:
        run = run.model_copy(update={"updated_at": datetime.now(UTC)})

        def save(
            items: list[OrchestrationRun],
        ) -> tuple[list[OrchestrationRun], OrchestrationRun]:
            if scheduler_lease_token is not None:
                self._require_scheduler_lease(run.id, scheduler_lease_token)
            updated_items: list[OrchestrationRun] = []
            saved: OrchestrationRun | None = None
            for candidate in items:
                if candidate.id != run.id:
                    updated_items.append(candidate)
                    continue
                if _progress_signature(candidate) != expected_signature:
                    raise OrchestrationError(
                        f"Orchestration changed during update; retry run {run.id}."
                    )
                saved = run
                updated_items.append(saved)
            if saved is None:
                raise OrchestrationError(f"Orchestration not found: {run.id}")
            return updated_items, saved

        saved = self._runs.transact(save)
        self._sync_project_documents(saved)
        return saved

    def _sync_project_documents(self, saved: OrchestrationRun) -> None:
        try:
            sync_result = sync_orchestration_documents(self._runs.list)
        except (OSError, ValueError) as exc:
            event_log.record(
                LogEventType.task,
                "Failed to sync orchestration project documents.",
                subject_id=saved.id,
                metadata={
                    "error_type": type(exc).__name__,
                    "error": redact_sensitive_values(str(exc)),
                },
            )
        else:
            event_log.record(
                LogEventType.task,
                "Synced orchestration project documents.",
                subject_id=saved.id,
                metadata=sync_result.model_dump(),
            )

    def _schedule_ready_tasks(
        self,
        run: OrchestrationRun,
        *,
        actor: str | None = None,
        background_execution_id: str | None = None,
        skip_foreground_conflict: bool = False,
    ) -> OrchestrationRun:
        foreground_lease = background_execution_id is None
        lease_token: str | None = None
        if foreground_lease:
            try:
                lease = self._acquire_scheduler_lease(run.id, actor=actor)
            except OrchestrationError:
                if skip_foreground_conflict:
                    current = self._runs.get(run.id)
                    return current or run
                raise
            lease_token = lease.lease_token
        else:
            lease_token = self._scheduler_lease_token_for_execution(background_execution_id)
            self._require_scheduler_lease(run.id, lease_token)

        spawned_agent_ids: set[str] = set()
        try:
            saved, claims, scheduled_task_ids = self._claim_ready_tasks_for_schedule(
                run.id,
                lease_token,
            )
            if not claims:
                self._sync_project_documents(saved)
                return saved

            try:
                for claim in claims:
                    task = _task_by_id(saved, claim.task_id)
                    if get_agent(claim.agent_id) is not None:
                        spawned_agent_ids.add(claim.agent_id)
                        continue
                    tasks_by_id = {candidate.id: candidate for candidate in saved.tasks}
                    brief = _agent_brief_for_task(
                        saved,
                        task,
                        tasks_by_id,
                        memory_context=self._memory_context_for_task(saved, task),
                    ).model_copy(update={"id": claim.agent_id})
                    agent = spawn_agent(brief)
                    spawned_agent_ids.add(agent.id)
            except Exception as exc:
                rolled_back = self._rollback_unspawned_schedule_claims(
                    saved.id,
                    claims,
                    spawned_agent_ids=spawned_agent_ids,
                )
                self._sync_project_documents(rolled_back)
                safe_error = redact_sensitive_values(f"{type(exc).__name__}: {exc}")
                raise OrchestrationError(
                    f"Failed to spawn scheduled orchestration agent: {safe_error}"
                ) from exc

            if scheduled_task_ids:
                event_log.record(
                    LogEventType.task,
                    "Scheduled orchestration tasks.",
                    actor=actor or "system",
                    subject_id=saved.id,
                    metadata={"task_ids": scheduled_task_ids},
                )
            self._sync_project_documents(saved)
            return saved
        finally:
            if foreground_lease and lease_token is not None:
                self._release_scheduler_lease(run.id, lease_token)

    def _validate_graph(self, tasks: list[OrchestrationTask]) -> None:
        task_ids = [task.id for task in tasks]
        duplicate_ids = {task_id for task_id in task_ids if task_ids.count(task_id) > 1}
        if duplicate_ids:
            raise OrchestrationError(
                "Orchestration task ids must be unique: " + ", ".join(sorted(duplicate_ids))
            )

        task_id_set = set(task_ids)
        for task in tasks:
            unknown = sorted(set(task.dependencies) - task_id_set)
            if unknown:
                raise OrchestrationError(
                    f"Task {task.id} has unknown dependencies: " + ", ".join(unknown)
                )
            if task.id in task.dependencies:
                raise OrchestrationError(f"Task {task.id} cannot depend on itself.")

        _raise_on_cycle(tasks)

    def _memory_context_for_task(
        self,
        run: OrchestrationRun,
        task: OrchestrationTask,
    ) -> list[str]:
        tags = _shared_memory_tags(run, task)
        if not tags:
            return []

        session = None
        try:
            session = get_db_session()
            items, _total = MetadataService(session).list_by_filters(
                entity_type="memory",
                category=ORCHESTRATION_MEMORY_CATEGORY,
                tags=tags,
                match_all_tags=True,
                lifecycle_state="active",
                owner_agent=_shared_memory_owner(run),
                limit=100,
            )
            valid_items = [item for item in items if self._is_valid_shared_memory_source(run, item)]
            return [_memory_context(item) for item in valid_items[:MAX_MEMORY_CONTEXT_RESULTS]]
        except Exception as exc:
            if session is not None:
                session.rollback()
            event_log.record(
                LogEventType.memory,
                "Failed to retrieve orchestration shared memory.",
                subject_id=run.id,
                metadata={
                    "task_id": _redact_metadata_value(task.id),
                    "owner_agent": _redact_metadata_value(_shared_memory_owner(run)),
                    "tags": _redact_metadata_values(tags),
                    "error_type": type(exc).__name__,
                    "error": redact_sensitive_values(str(exc)),
                },
            )
            return []
        finally:
            if session is not None:
                session.close()

    def _is_valid_shared_memory_source(
        self,
        consumer_run: OrchestrationRun,
        metadata: MemoryMetadata,
    ) -> bool:
        source_ids = _parse_task_memory_entity_id(metadata.entity_id)
        if source_ids is None:
            return False
        source_run_id, source_task_id = source_ids
        source_run = (
            consumer_run if source_run_id == consumer_run.id else self._runs.get(source_run_id)
        )
        if source_run is None:
            return False
        if not _shared_memory_policy_allows_source(consumer_run, source_run):
            return False
        if metadata.owner_agent != _shared_memory_owner(source_run):
            return False
        try:
            source_task = _task_by_id(source_run, source_task_id)
        except OrchestrationError:
            return False
        metadata_tags = set(_normalize_shared_memory_tags(metadata.tags or []))
        source_tags = set(_shared_memory_tags(source_run, source_task))
        return (
            source_task.status == StepStatus.completed
            and metadata.entity_id == _task_memory_entity_id(source_run, source_task)
            and bool(metadata_tags)
            and metadata_tags.issubset(source_tags)
            and metadata.description == _completed_task_memory_description(source_run, source_task)
        )


def _raise_on_cycle(tasks: list[OrchestrationTask]) -> None:
    task_map = {task.id: task for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise OrchestrationError("Orchestration task graph must be acyclic.")
        visiting.add(task_id)
        for dependency in task_map[task_id].dependencies:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in tasks:
        visit(task.id)


def _task_from_spec(task: OrchestrationTaskSpec) -> OrchestrationTask:
    return OrchestrationTask(
        id=task.id,
        title=task.title,
        description=task.description,
        role=task.role,
        dependencies=list(task.dependencies),
        declared_write_paths=list(task.declared_write_paths),
        shared_memory_tags=_normalize_shared_memory_tags(task.shared_memory_tags),
        expected_output=task.expected_output,
        validation=task.validation,
        retry_limit=task.retry_limit,
    )


def _agent_context_for_task(
    run: OrchestrationRun,
    task: OrchestrationTask,
    tasks_by_id: dict[str, OrchestrationTask],
    memory_context: list[str],
) -> list[str]:
    context = [_redacted_context_text(run.objective)]
    for dependency_id in task.dependencies:
        dependency = tasks_by_id[dependency_id]
        context.append(_dependency_context(dependency))
    context.extend(memory_context)
    return context


def _agent_brief_for_task(
    run: OrchestrationRun,
    task: OrchestrationTask,
    tasks_by_id: dict[str, OrchestrationTask],
    memory_context: list[str],
) -> AgentBrief:
    return AgentBrief(
        role=_redacted_context_text(task.role),
        task=_redacted_context_text(task.title),
        task_id=_redacted_context_text(task.id),
        context=_agent_context_for_task(run, task, tasks_by_id, memory_context),
        constraints=[
            _redacted_context_text(
                f"Declared write paths: {task.declared_write_paths or ['read-only']}"
            )
        ],
        required_data=[_redacted_context_text(dependency) for dependency in task.dependencies],
        expected_output=_redacted_context_text(task.expected_output or task.validation),
    )


def _dependency_context(task: OrchestrationTask) -> str:
    output = _redacted_json(task.output)
    return _redacted_context_text(
        f"Dependency {task.id} ({task.role}) completed: {task.title}. Output: {output}"
    )


def _shared_memory_tags(
    run: OrchestrationRun,
    task: OrchestrationTask,
) -> list[str]:
    return _normalize_shared_memory_tags([*run.shared_memory_tags, *task.shared_memory_tags])


def _normalize_shared_memory_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        tag = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
        if not tag or tag in tags:
            continue
        tags.append(tag[:80])
        if len(tags) >= MAX_SHARED_MEMORY_TAGS:
            break
    return tags


def _completed_task_memory_description(run: OrchestrationRun, task: OrchestrationTask) -> str:
    return _redacted_context_text(
        (
            f"Orchestration task {task.id} ({task.role}) from run {run.id} completed: "
            f"{task.title}. Output: {_redacted_json(task.output)}"
        ),
        max_chars=MAX_DEPENDENCY_CONTEXT_CHARS,
    )


def _task_memory_entity_id(run: OrchestrationRun, task: OrchestrationTask) -> str:
    return f"{ORCHESTRATION_MEMORY_ENTITY_PREFIX}{run.id}:{task.id}"


def _parse_task_memory_entity_id(entity_id: str) -> tuple[str, str] | None:
    if not entity_id.startswith(ORCHESTRATION_MEMORY_ENTITY_PREFIX):
        return None
    remainder = entity_id[len(ORCHESTRATION_MEMORY_ENTITY_PREFIX) :]
    run_id, separator, task_id = remainder.partition(":")
    if not separator or not run_id or not task_id:
        return None
    return run_id, task_id


def _shared_memory_owner(run: OrchestrationRun) -> str:
    return _redacted_context_text(
        run.requested_by or SHARED_MEMORY_SYSTEM_OWNER,
        max_chars=100,
    )


def _shared_memory_policy_allows_source(
    consumer_run: OrchestrationRun,
    source_run: OrchestrationRun,
) -> bool:
    if _shared_memory_owner(source_run) != _shared_memory_owner(consumer_run):
        return False
    if source_run.shared_memory_policy == "run" or consumer_run.shared_memory_policy == "run":
        return source_run.id == consumer_run.id
    return True


def _memory_context(metadata: MemoryMetadata) -> str:
    tags = [
        _redacted_context_text(tag, max_chars=80)
        for tag in (metadata.tags or [])[:MAX_CONTEXT_OUTPUT_ITEMS]
    ]
    description = _redacted_context_text(
        metadata.description or "",
        max_chars=MAX_MEMORY_CONTEXT_CHARS,
    )
    return _redacted_context_text(
        f"Shared memory {metadata.entity_id}. Tags: {tags}. Summary: {description}",
        max_chars=MAX_DEPENDENCY_CONTEXT_CHARS,
    )


def _redacted_json(value: dict[str, Any]) -> str:
    rendered = json.dumps(_context_value_summary(value), sort_keys=True, default=str)
    redacted = redact_sensitive_values(rendered)
    if len(redacted) <= MAX_DEPENDENCY_CONTEXT_CHARS:
        return redacted
    return redacted[: MAX_DEPENDENCY_CONTEXT_CHARS - 3] + "..."


def _context_value_summary(value: Any, *, depth: int = 0) -> Any:
    if depth >= MAX_CONTEXT_OUTPUT_DEPTH:
        return "<truncated>"
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_CONTEXT_OUTPUT_ITEMS:
                summary["_truncated_items"] = len(value) - MAX_CONTEXT_OUTPUT_ITEMS
                break
            summary[_redacted_context_text(str(key), max_chars=120)] = _context_value_summary(
                item,
                depth=depth + 1,
            )
        return summary
    if isinstance(value, list):
        summary = [
            _context_value_summary(item, depth=depth + 1)
            for item in value[:MAX_CONTEXT_OUTPUT_ITEMS]
        ]
        if len(value) > MAX_CONTEXT_OUTPUT_ITEMS:
            summary.append({"_truncated_items": len(value) - MAX_CONTEXT_OUTPUT_ITEMS})
        return summary
    if isinstance(value, str):
        return REDACTED_SECRET_MARKER
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, int | float):
        return "<number>"
    if value is None:
        return None
    return f"<{type(value).__name__}>"


def _redacted_context_text(
    value: str,
    *,
    max_chars: int = MAX_CONTEXT_FIELD_CHARS,
) -> str:
    redacted = redact_sensitive_values(value)
    if len(redacted) <= max_chars:
        return redacted
    return redacted[: max_chars - 3] + "..."


def _ensure_run_open(run: OrchestrationRun) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        raise OrchestrationError(f"Cannot modify closed orchestration: {run.id}")


def _progress_signature(run: OrchestrationRun) -> str:
    return json.dumps(
        {
            "tasks": [
                {
                    "id": task.id,
                    "status": task.status,
                    "agent_id": task.agent_id,
                    "retry_count": task.retry_count,
                    "output": task.output,
                    "error": task.error,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                }
                for task in run.tasks
            ],
            "blockers": [
                {
                    "id": blocker.id,
                    "task_id": blocker.task_id,
                    "severity": blocker.severity,
                    "status": blocker.status,
                }
                for blocker in run.blockers
            ],
            "follow_ups": [
                {
                    "id": follow_up.id,
                    "task_id": follow_up.task_id,
                    "assigned_role": follow_up.assigned_role,
                }
                for follow_up in run.follow_ups
            ],
        },
        sort_keys=True,
        default=str,
    )


def _loop_stop_reason(
    run: OrchestrationRun,
    *,
    stop_on_blocked: bool,
) -> str | None:
    if stop_on_blocked and _unresolved_blockers(run.blockers):
        return "blocked"
    if all(task.status == StepStatus.completed for task in run.tasks):
        return "all_tasks_completed"
    if _pending_task_ids(run):
        return None
    if _running_task_ids(run):
        return None
    return "quiescent"


def _loop_result(
    run: OrchestrationRun,
    *,
    iterations: int,
    made_progress: bool,
    stopped_reason: str,
) -> OrchestrationLoopResult:
    return OrchestrationLoopResult(
        run=run,
        iterations=iterations,
        made_progress=made_progress,
        stopped_reason=stopped_reason,
        running_task_ids=_running_task_ids(run),
        pending_task_ids=_pending_task_ids(run),
        unresolved_blocker_ids=[blocker.id for blocker in _unresolved_blockers(run.blockers)],
    )


def _operations_execution_status(
    execution: OrchestrationExecution,
    *,
    supervisor_id: str,
    now: datetime,
) -> OrchestrationExecutionStatus:
    if _should_mark_background_execution_stale(execution, supervisor_id=supervisor_id, now=now):
        return OrchestrationExecutionStatus.stale
    return execution.status


def _value_counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _record_task_update_event(
    run: OrchestrationRun,
    previous_task: OrchestrationTask,
    transition_task: OrchestrationTask,
    update: OrchestrationTaskUpdate,
    *,
    previous_blocker_ids: set[str],
    previous_follow_up_ids: set[str],
    actor: str | None,
) -> None:
    persisted_task = _task_by_id(run, previous_task.id)
    event_log.record(
        LogEventType.task,
        "Updated orchestration task status.",
        actor=actor or "system",
        subject_id=run.id,
        metadata={
            "task_id": _redact_metadata_value(previous_task.id),
            "requested_status": update.status,
            "previous_status": previous_task.status,
            "transition_status": transition_task.status,
            "status": persisted_task.status,
            "previous_retry_count": previous_task.retry_count,
            "retry_count": persisted_task.retry_count,
            "new_blocker_ids": [
                _redact_metadata_value(blocker.id)
                for blocker in run.blockers
                if blocker.id not in previous_blocker_ids
            ],
            "new_follow_up_ids": [
                _redact_metadata_value(follow_up.id)
                for follow_up in run.follow_ups
                if follow_up.id not in previous_follow_up_ids
            ],
            "scheduled_task_ids": _redact_metadata_values(run.scheduled_task_ids),
            "error": redact_sensitive_values(update.error) if update.error else None,
            "output_keys": _redact_metadata_values(sorted(str(key) for key in update.output)),
        },
    )


def _running_task_ids(run: OrchestrationRun) -> list[str]:
    return [task.id for task in run.tasks if task.status == StepStatus.running]


def _pending_task_ids(run: OrchestrationRun) -> list[str]:
    return [task.id for task in run.tasks if task.status == StepStatus.pending]


def _validate_task_update(
    task: OrchestrationTask,
    update: OrchestrationTaskUpdate,
) -> None:
    if update.status not in TASK_UPDATE_STATUSES:
        raise OrchestrationError(
            "Orchestration task updates may only mark tasks completed, failed, or blocked."
        )
    if task.status != StepStatus.running:
        raise OrchestrationError(
            f"Cannot update task {task.id} from {task.status}; only running tasks can be updated."
        )


def _task_update_from_agent_status(agent_id: str) -> OrchestrationTaskUpdate | None:
    agent = get_agent(agent_id)
    if agent is None:
        return None
    if agent.status == AgentStatus.completed:
        return OrchestrationTaskUpdate(
            status=StepStatus.completed,
            output={"agent_id": agent_id, "agent_status": agent.status},
        )
    if agent.status == AgentStatus.failed:
        return OrchestrationTaskUpdate(
            status=StepStatus.failed,
            error=f"Agent {agent_id} reported failed status.",
        )
    if agent.status == AgentStatus.cancelled:
        return OrchestrationTaskUpdate(
            status=StepStatus.blocked,
            error=f"Agent {agent_id} was cancelled.",
        )
    return None


def _authorize_task_filesystem_action(
    run: OrchestrationRun,
    task: OrchestrationTask,
    *,
    agent_role: str,
    action: str,
    paths: list[str],
) -> OrchestrationActionDecision:
    if task.status != StepStatus.running:
        return OrchestrationActionDecision(
            allowed=False,
            reason=f"Task {task.id} is not running.",
            run_id=run.id,
            task_id=task.id,
            agent_id=task.agent_id,
            agent_role=task.role,
        )
    if _normalize_role(task.role) != _normalize_role(agent_role):
        return OrchestrationActionDecision(
            allowed=False,
            reason=f"Agent role {agent_role} does not match orchestration task role {task.role}.",
            run_id=run.id,
            task_id=task.id,
            agent_id=task.agent_id,
            agent_role=agent_role,
        )

    normalized_paths: list[str] = []
    invalid_paths: list[str] = []
    for path in paths:
        try:
            normalized_paths.append(_normalize_path(path))
        except ValueError:
            invalid_paths.append(path)
    if invalid_paths:
        return OrchestrationActionDecision(
            allowed=False,
            reason="Filesystem action paths must be relative repository paths without traversal.",
            run_id=run.id,
            task_id=task.id,
            agent_id=task.agent_id,
            agent_role=task.role,
            violating_paths=invalid_paths,
        )

    if action not in WRITE_FILE_ACTIONS:
        return OrchestrationActionDecision(
            allowed=True,
            reason="Read-only filesystem action is bound to a running orchestration task.",
            run_id=run.id,
            task_id=task.id,
            agent_id=task.agent_id,
            agent_role=task.role,
        )

    declared_paths = [_normalize_path(path) for path in task.declared_write_paths]
    if not declared_paths:
        return OrchestrationActionDecision(
            allowed=False,
            reason=f"Task {task.id} declares no write paths for filesystem action {action}.",
            run_id=run.id,
            task_id=task.id,
            agent_id=task.agent_id,
            agent_role=task.role,
            violating_paths=normalized_paths,
        )

    violations = [
        path
        for path in normalized_paths
        if not any(_path_matches(path, declared_path) for declared_path in declared_paths)
    ]
    if violations:
        return OrchestrationActionDecision(
            allowed=False,
            reason="Filesystem action path is outside the orchestration task declared write paths.",
            run_id=run.id,
            task_id=task.id,
            agent_id=task.agent_id,
            agent_role=task.role,
            violating_paths=violations,
        )

    return OrchestrationActionDecision(
        allowed=True,
        reason="Filesystem write action is within the orchestration task declared write paths.",
        run_id=run.id,
        task_id=task.id,
        agent_id=task.agent_id,
        agent_role=task.role,
    )


def _role_boundary_decision(task: OrchestrationTask) -> RoleBoundaryDecision:
    normalized_role = _normalize_role(task.role)
    if normalized_role not in ROLE_POLICIES:
        return RoleBoundaryDecision(
            task_id=task.id,
            role=task.role,
            allowed=False,
            reason=f"Unsupported orchestration role: {task.role}",
            violating_paths=list(task.declared_write_paths),
            suggested_owner_role="PM",
        )

    paths: list[str] = []
    invalid_paths: list[str] = []
    for path in task.declared_write_paths:
        try:
            paths.append(_normalize_path(path))
        except ValueError:
            invalid_paths.append(path)
    if invalid_paths:
        return RoleBoundaryDecision(
            task_id=task.id,
            role=task.role,
            allowed=False,
            reason=(
                "Declared write paths must be relative repository paths without traversal: "
                + ", ".join(sorted(invalid_paths))
            ),
            violating_paths=invalid_paths,
            suggested_owner_role="PM",
        )

    policy = ROLE_POLICIES[normalized_role]
    if not paths:
        return RoleBoundaryDecision(
            task_id=task.id,
            role=task.role,
            allowed=True,
            reason="Task declares no write paths.",
        )
    if policy is None:
        return RoleBoundaryDecision(
            task_id=task.id,
            role=task.role,
            allowed=False,
            reason=f"{task.role} is read-only in role-boundary policy.",
            violating_paths=paths,
            suggested_owner_role=_suggest_owner_role(paths[0]),
        )

    violations = [
        path for path in paths if not any(_path_matches(path, prefix) for prefix in policy)
    ]
    if violations:
        return RoleBoundaryDecision(
            task_id=task.id,
            role=task.role,
            allowed=False,
            reason=(
                f"{task.role} may not modify declared path(s): " + ", ".join(sorted(violations))
            ),
            violating_paths=violations,
            suggested_owner_role=_suggest_owner_role(violations[0]),
        )
    return RoleBoundaryDecision(
        task_id=task.id,
        role=task.role,
        allowed=True,
        reason=f"{task.role} declared write paths are within role policy.",
    )


ROLE_POLICIES: dict[str, tuple[str, ...] | None] = {
    "developer": (
        "src/",
        "pyproject.toml",
        "docs/architecture/",
        "docs/how-to/",
        "docs/agentic-workflows/",
    ),
    "dev": (
        "src/",
        "pyproject.toml",
        "docs/architecture/",
        "docs/how-to/",
        "docs/agentic-workflows/",
    ),
    "qa": ("tests/",),
    "reviewer": None,
    "security": None,
    "pm": ("README.md", "docs/planning/", "docs/progress/", "docs/agentic-workflows/"),
    "project manager": (
        "README.md",
        "docs/planning/",
        "docs/progress/",
        "docs/agentic-workflows/",
    ),
    "release manager": ("README.md", "docs/releases/"),
    "releasemanager": ("README.md", "docs/releases/"),
}


def _normalize_role(role: str) -> str:
    return " ".join(role.strip().lower().replace("_", " ").replace("-", " ").split())


def _normalize_path(path: str) -> str:
    raw_path = path.strip().replace("\\", "/")
    if not raw_path or raw_path.startswith(("/", "~")):
        raise ValueError("Declared write path must be relative.")
    if ":" in PurePosixPath(raw_path).parts[0]:
        raise ValueError("Declared write path must not include a drive or URI scheme.")

    parts: list[str] = []
    for part in raw_path.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("Declared write path must not contain traversal.")
        parts.append(part)
    if not parts:
        raise ValueError("Declared write path must not be empty.")
    return "/".join(parts)


def _path_matches(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix


def _suggest_owner_role(path: str) -> str:
    if path.startswith("tests/"):
        return "QA"
    if path.startswith("src/") or path == "pyproject.toml":
        return "Developer"
    if (
        path.startswith("docs/planning/")
        or path.startswith("docs/progress/")
        or path == "README.md"
    ):
        return "PM"
    if path.startswith("docs/releases/"):
        return "ReleaseManager"
    return "PM"


def _task_by_id(run: OrchestrationRun, task_id: str) -> OrchestrationTask:
    for task in run.tasks:
        if task.id == task_id:
            return task
    raise OrchestrationError(f"Task not found in orchestration: {task_id}")


def _blocker_by_id(run: OrchestrationRun, blocker_id: str) -> OrchestrationBlocker:
    for blocker in run.blockers:
        if blocker.id == blocker_id:
            return blocker
    raise OrchestrationError(f"Blocker not found in orchestration: {blocker_id}")


def _is_unresolved_blocker(blocker: OrchestrationBlocker) -> bool:
    return blocker.status != "resolved"


def _unresolved_blockers(
    blockers: list[OrchestrationBlocker],
    *,
    task_id: str | None = None,
) -> list[OrchestrationBlocker]:
    return [
        blocker
        for blocker in blockers
        if _is_unresolved_blocker(blocker) and (task_id is None or blocker.task_id == task_id)
    ]


def _replace_role_boundary_decision(
    decisions: list[RoleBoundaryDecision],
    replacement: RoleBoundaryDecision,
) -> list[RoleBoundaryDecision]:
    replaced = False
    updated: list[RoleBoundaryDecision] = []
    for decision in decisions:
        if decision.task_id == replacement.task_id:
            if not replaced:
                updated.append(replacement)
                replaced = True
            continue
        updated.append(decision)
    if not replaced:
        updated.append(replacement)
    return updated


def _redact_metadata_value(value: str) -> str:
    return redact_sensitive_values(value)


def _redact_metadata_values(values: list[str]) -> list[str]:
    return [_redact_metadata_value(value) for value in values]


def _blocker(task_id: str, reason: str, *, severity: str) -> OrchestrationBlocker:
    return OrchestrationBlocker(
        id=f"blocker-{uuid4()}",
        task_id=task_id,
        reason=reason,
        severity=severity,
    )


def _follow_up(task_id: str, assigned_role: str, description: str) -> OrchestrationFollowUp:
    return OrchestrationFollowUp(
        id=f"followup-{uuid4()}",
        task_id=task_id,
        assigned_role=assigned_role,
        description=description,
    )


def _update_agent_for_task(agent_id: str, status: StepStatus, error: str | None) -> None:
    agent = get_agent(agent_id)
    if agent is not None and agent.status in {
        AgentStatus.completed,
        AgentStatus.failed,
        AgentStatus.cancelled,
    }:
        return
    if status == StepStatus.completed:
        update_agent_status(agent_id, AgentStatusUpdate(status=AgentStatus.completed))
    elif status in {StepStatus.failed, StepStatus.blocked}:
        update_agent_status(agent_id, AgentStatusUpdate(status=AgentStatus.failed, note=error))


orchestration_service = OrchestrationService()


def authorize_filesystem_action(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    action: str,
    paths: list[str],
) -> OrchestrationActionDecision:
    return orchestration_service.authorize_filesystem_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        action=action,
        paths=paths,
    )


def authorize_cli_action(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> OrchestrationActionDecision:
    return orchestration_service.authorize_cli_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def authorize_tool_action(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> OrchestrationActionDecision:
    return orchestration_service.authorize_tool_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def authorize_provider_action(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> OrchestrationActionDecision:
    return orchestration_service.authorize_provider_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def authorize_network_action(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> OrchestrationActionDecision:
    return orchestration_service.authorize_network_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
