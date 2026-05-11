from datetime import UTC, datetime
from uuid import uuid4

from dgentic.events import event_log
from dgentic.schemas import LogEventType, PlanStatus, StepResult, StepStatus, TaskPlan, TaskRun
from dgentic.storage import JsonCollection


class ExecutionEngine:
    def __init__(self) -> None:
        self._runs = JsonCollection("task-runs", TaskRun)

    def execute_plan(self, plan: TaskPlan, *, actor: str | None = None) -> TaskRun:
        results = [
            StepResult(
                step_id=step.id,
                status=StepStatus.completed,
                output={
                    "title": step.title,
                    "validation": step.validation,
                    "agent_role": step.agent_role,
                },
                completed_at=datetime.now(UTC),
            )
            for step in plan.steps
        ]
        run = TaskRun(
            id=f"run-{uuid4()}",
            plan_id=plan.id,
            status=PlanStatus.completed,
            results=results,
            completed_at=datetime.now(UTC),
        )
        self._runs.upsert(run)
        event_log.record(
            LogEventType.task,
            "Executed deterministic task plan.",
            actor=actor or "system",
            subject_id=plan.id,
            metadata={"run_id": run.id, "steps": len(results)},
        )
        return run

    def get_run(self, run_id: str) -> TaskRun | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[TaskRun]:
        return self._runs.list()


execution_engine = ExecutionEngine()
