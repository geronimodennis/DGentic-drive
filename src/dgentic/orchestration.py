"""Backend orchestration control plane for autonomous sprint task graphs."""

from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

from dgentic.agents import get_agent, spawn_agent, update_agent_status
from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
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
    OrchestrationFollowUp,
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
TERMINAL_RUN_STATUSES = {PlanStatus.completed, PlanStatus.failed}
TASK_UPDATE_STATUSES = {StepStatus.completed, StepStatus.failed, StepStatus.blocked}
RECOVERABLE_TASK_BLOCKER_SEVERITIES = {"role_boundary", "retry_exhausted"}
RESOLVABLE_TASK_BLOCKER_SEVERITIES = {"blocked", "security"}
WRITE_FILE_ACTIONS = {
    "write",
    "binary_write",
    "delete",
    "move",
    "copy",
    "rename",
}


class OrchestrationError(ValueError):
    """Raised when an orchestration graph or transition is invalid."""


class OrchestrationService:
    """Validate, schedule, and track autonomous orchestration task graphs."""

    def __init__(self) -> None:
        self._runs = JsonCollection("orchestrations", OrchestrationRun)

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
            role_boundary_decisions=decisions,
            blockers=blockers,
            follow_ups=follow_ups,
            requested_by=actor or request.requested_by,
        )
        run = self._schedule_ready_tasks(run, actor=actor)
        self._runs.upsert(run)
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

    def advance_run(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        updated = self._schedule_ready_tasks(run, actor=actor)
        return self._persist(updated)

    def run_cycle(
        self,
        run_id: str,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
        task_updates = [
            (task.id, update)
            for task in run.tasks
            if task.status == StepStatus.running and task.agent_id
            for update in [_task_update_from_agent_status(task.agent_id)]
            if update is not None
        ]

        if not task_updates:
            updated = self._schedule_ready_tasks(run, actor=actor)
            return self._persist(updated)

        scheduled_task_ids: list[str] = []
        for task_id, update in task_updates:
            run = self.update_task(
                run.id,
                task_id,
                update,
                actor=actor,
                include_all=include_all,
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

    def update_task(
        self,
        run_id: str,
        task_id: str,
        update: OrchestrationTaskUpdate,
        *,
        actor: str | None = None,
        include_all: bool = True,
    ) -> OrchestrationRun:
        run = self._require_run(run_id, actor=actor, include_all=include_all)
        _ensure_run_open(run)
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
        if task.agent_id:
            _update_agent_for_task(task.agent_id, update.status, update.error)
        if updated_task.status in {StepStatus.completed, StepStatus.pending}:
            run = self._schedule_ready_tasks(run, actor=actor)
        return self._persist(run)

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
        run = self._schedule_ready_tasks(run, actor=actor)
        return self._persist(run)

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
        return self._persist(run)

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
        if not any([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=True,
                reason="No orchestration context was supplied.",
            )

        relevant_tasks = [
            (run, task)
            for run in self._runs.list()
            if run.status not in TERMINAL_RUN_STATUSES
            for task in run.tasks
            if task.status == StepStatus.running
            and ((agent_id is not None and task.agent_id == agent_id) or task.id == task_id)
        ]
        if not relevant_tasks:
            return OrchestrationActionDecision(
                allowed=True,
                reason="No active orchestration task matched supplied CLI context.",
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not all([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    "Orchestration-bound CLI actions require agent_id, agent_role, and task_id."
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
                    reason="CLI action is bound to a running orchestration task.",
                    run_id=run.id,
                    task_id=task.id,
                    agent_id=agent_id,
                    agent_role=agent_role,
                )

        return OrchestrationActionDecision(
            allowed=False,
            reason="Supplied CLI agent context does not match the running orchestration task.",
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
                    "Supplied tool agent context matches an orchestration task that is not running."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not relevant_tasks and has_active_tasks and not all([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    "Orchestration-bound tool actions require agent_id, agent_role, and task_id."
                ),
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not relevant_tasks:
            return OrchestrationActionDecision(
                allowed=True,
                reason="No active orchestration task matched supplied tool context.",
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )
        if not all([agent_id, agent_role, task_id]):
            return OrchestrationActionDecision(
                allowed=False,
                reason=(
                    "Orchestration-bound tool actions require agent_id, agent_role, and task_id."
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
                    reason="Tool action is bound to a running orchestration task.",
                    run_id=run.id,
                    task_id=task.id,
                    agent_id=agent_id,
                    agent_role=agent_role,
                )

        return OrchestrationActionDecision(
            allowed=False,
            reason="Supplied tool agent context does not match the running orchestration task.",
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

    def _persist(self, run: OrchestrationRun) -> OrchestrationRun:
        run = run.model_copy(update={"updated_at": datetime.now(UTC)})
        return self._runs.upsert(run)

    def _schedule_ready_tasks(
        self,
        run: OrchestrationRun,
        *,
        actor: str | None = None,
    ) -> OrchestrationRun:
        tasks_by_id = {task.id: task for task in run.tasks}
        scheduled_task_ids: list[str] = []
        updated_tasks: list[OrchestrationTask] = []

        for task in run.tasks:
            if len(scheduled_task_ids) >= MAX_READY_TASKS_PER_ADVANCE:
                updated_tasks.append(task)
                continue
            if task.status != StepStatus.pending:
                updated_tasks.append(task)
                continue
            if not all(
                tasks_by_id[dependency].status == StepStatus.completed
                for dependency in task.dependencies
            ):
                updated_tasks.append(task)
                continue

            agent = spawn_agent(
                AgentBrief(
                    role=task.role,
                    task=task.title,
                    task_id=task.id,
                    context=[run.objective],
                    constraints=[
                        f"Declared write paths: {task.declared_write_paths or ['read-only']}"
                    ],
                    required_data=task.dependencies,
                    expected_output=task.expected_output or task.validation,
                )
            )
            updated_tasks.append(
                task.model_copy(update={"status": StepStatus.running, "agent_id": agent.id})
            )
            scheduled_task_ids.append(task.id)

        if scheduled_task_ids:
            event_log.record(
                LogEventType.task,
                "Scheduled orchestration tasks.",
                actor=actor or "system",
                subject_id=run.id,
                metadata={"task_ids": scheduled_task_ids},
            )
        return run.model_copy(
            update={
                "tasks": updated_tasks,
                "scheduled_task_ids": scheduled_task_ids,
                "updated_at": datetime.now(UTC),
            }
        )

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
        expected_output=task.expected_output,
        validation=task.validation,
        retry_limit=task.retry_limit,
    )


def _ensure_run_open(run: OrchestrationRun) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        raise OrchestrationError(f"Cannot modify closed orchestration: {run.id}")


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
