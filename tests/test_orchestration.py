import pytest

from dgentic.orchestration import OrchestrationError, OrchestrationService
from dgentic.schemas import (
    OrchestrationCloseRequest,
    OrchestrationCreateRequest,
    OrchestrationTask,
    OrchestrationTaskSpec,
    OrchestrationTaskUpdate,
    PlanStatus,
    StepStatus,
)
from dgentic.settings import get_settings


@pytest.fixture
def orchestration_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    yield data_dir
    get_settings.cache_clear()


def test_orchestration_schedules_parallel_ready_tasks_and_unblocks_dependencies(
    orchestration_state,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Coordinate Sprint 14 delivery.",
            tasks=[
                _task("dev-impl", role="Developer", paths=["src/dgentic/orchestration.py"]),
                _task("qa-tests", role="QA", paths=["tests/test_orchestration.py"]),
                _task(
                    "pm-closeout",
                    role="PM",
                    dependencies=["dev-impl", "qa-tests"],
                    paths=["docs/progress/project-progress-log.md"],
                ),
            ],
        )
    )

    assert set(run.scheduled_task_ids) == {"dev-impl", "qa-tests"}
    assert _status_by_id(run) == {
        "dev-impl": StepStatus.running,
        "qa-tests": StepStatus.running,
        "pm-closeout": StepStatus.pending,
    }
    assert all(_task_by_id(run, task_id).agent_id for task_id in ["dev-impl", "qa-tests"])

    run = service.update_task(
        run.id,
        "dev-impl",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"done": True}),
    )

    assert run.scheduled_task_ids == []
    assert _task_by_id(run, "pm-closeout").status == StepStatus.pending

    run = service.update_task(
        run.id,
        "qa-tests",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    assert run.scheduled_task_ids == ["pm-closeout"]
    assert _task_by_id(run, "pm-closeout").status == StepStatus.running
    assert _task_by_id(run, "pm-closeout").agent_id


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate", "unique"),
        ("unknown", "unknown dependencies"),
        ("self", "cannot depend on itself"),
        ("cycle", "acyclic"),
    ],
)
def test_orchestration_rejects_invalid_dependency_graphs(
    orchestration_state,
    case: str,
    message: str,
) -> None:
    service = OrchestrationService()

    with pytest.raises(OrchestrationError, match=message):
        service.create_run(
            OrchestrationCreateRequest(
                objective="Reject invalid orchestration graphs.",
                tasks=_invalid_graph_tasks(case),
            )
        )


def test_orchestration_blocks_role_boundary_violations_with_follow_up_suggestions(
    orchestration_state,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Keep QA inside the test ownership boundary.",
            tasks=[
                _task(
                    "qa-source-edit",
                    role="QA",
                    paths=["src/dgentic/orchestration.py"],
                ),
                _task("qa-allowed", role="QA", paths=["tests/test_orchestration.py"]),
            ],
        )
    )

    blocked_task = _task_by_id(run, "qa-source-edit")
    decision = next(
        decision for decision in run.role_boundary_decisions if decision.task_id == blocked_task.id
    )

    assert blocked_task.status == StepStatus.blocked
    assert blocked_task.error == decision.reason
    assert decision.allowed is False
    assert decision.violating_paths == ["src/dgentic/orchestration.py"]
    assert decision.suggested_owner_role == "Developer"
    assert [(blocker.task_id, blocker.severity) for blocker in run.blockers] == [
        ("qa-source-edit", "role_boundary")
    ]
    assert [(follow_up.task_id, follow_up.assigned_role) for follow_up in run.follow_ups] == [
        ("qa-source-edit", "Developer")
    ]
    assert run.scheduled_task_ids == ["qa-allowed"]


@pytest.mark.parametrize(
    ("task_id", "role", "paths", "violating_path"),
    [
        ("qa-traversal", "QA", ["tests/../src/dgentic/orchestration.py"], None),
        ("pm-readme-prefix", "PM", ["README.md.bak"], "README.md.bak"),
        ("dev-absolute", "Developer", ["/src/dgentic/orchestration.py"], None),
    ],
)
def test_orchestration_role_boundaries_reject_non_canonical_paths(
    orchestration_state,
    task_id: str,
    role: str,
    paths: list[str],
    violating_path: str | None,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject non-canonical role-boundary paths.",
            tasks=[_task(task_id, role=role, paths=paths)],
        )
    )

    assert run.tasks[0].status == StepStatus.blocked
    assert run.role_boundary_decisions[0].allowed is False
    if violating_path is not None:
        assert run.role_boundary_decisions[0].violating_paths == [violating_path]


def test_orchestration_rejects_unknown_roles_even_when_read_only(
    orchestration_state,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject unknown roles.",
            tasks=[_task("unknown-role", role="Wizard")],
        )
    )

    assert run.tasks[0].status == StepStatus.blocked
    assert run.role_boundary_decisions[0].allowed is False
    assert "Unsupported orchestration role" in run.role_boundary_decisions[0].reason


def test_orchestration_filesystem_context_is_optional_and_bounds_declared_writes(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Authorize filesystem writes for the assigned QA task only.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")

    no_context = service.authorize_filesystem_action(
        agent_id=None,
        agent_role=None,
        task_id=None,
        action="write",
        paths=["src/dgentic/orchestration.py"],
    )
    declared_write = service.authorize_filesystem_action(
        agent_id=task.agent_id,
        agent_role=task.role,
        task_id=task.id,
        action="write",
        paths=["tests/test_orchestration.py"],
    )
    outside_write = service.authorize_filesystem_action(
        agent_id=task.agent_id,
        agent_role=task.role,
        task_id=task.id,
        action="write",
        paths=["tests/test_api.py"],
    )

    assert no_context.allowed is True
    assert no_context.reason == "No orchestration context was supplied."
    assert declared_write.allowed is True
    assert declared_write.run_id == run.id
    assert declared_write.agent_id == task.agent_id
    assert outside_write.allowed is False
    assert outside_write.violating_paths == ["tests/test_api.py"]
    assert "outside the orchestration task declared write paths" in outside_write.reason


@pytest.mark.parametrize(
    ("agent_id", "agent_role", "task_id", "reason"),
    [
        ("agent-only", None, None, "require agent_id, agent_role, and task_id"),
        (None, "QA", None, "require agent_id, agent_role, and task_id"),
        (None, None, "qa-validation", "require agent_id, agent_role, and task_id"),
        ("wrong-agent", "QA", "qa-validation", "No running orchestration task matches"),
        ("agent-from-task", "Developer", "qa-validation", "does not match orchestration task role"),
        ("agent-from-task", "QA", "wrong-task", "No running orchestration task matches"),
    ],
)
def test_orchestration_filesystem_binding_blocks_partial_or_mismatched_context(
    orchestration_state,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    reason: str,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject incomplete or mismatched filesystem ownership context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")
    bound_agent_id = task.agent_id if agent_id == "agent-from-task" else agent_id

    decision = service.authorize_filesystem_action(
        agent_id=bound_agent_id,
        agent_role=agent_role,
        task_id=task_id,
        action="write",
        paths=["tests/test_orchestration.py"],
    )

    assert decision.allowed is False
    assert reason in decision.reason


def test_orchestration_filesystem_allows_read_only_action_for_running_bound_task(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Allow read-only filesystem access for a running reviewer task.",
            tasks=[_task("review-readonly", role="Reviewer")],
        )
    )
    task = _task_by_id(run, "review-readonly")

    decision = service.authorize_filesystem_action(
        agent_id=task.agent_id,
        agent_role=task.role,
        task_id=task.id,
        action="read",
        paths=["src/dgentic/orchestration.py"],
    )

    assert decision.allowed is True
    assert decision.run_id == run.id
    assert (
        decision.reason == "Read-only filesystem action is bound to a running orchestration task."
    )


def test_orchestration_cli_context_is_backward_compatible_without_active_task_match(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    service.create_run(
        OrchestrationCreateRequest(
            objective="Keep legacy CLI context behavior when no task matches.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    decision = service.authorize_cli_action(
        agent_id="legacy-agent",
        agent_role="Developer",
        task_id="legacy-task",
    )

    assert decision.allowed is True
    assert decision.reason == "No active orchestration task matched supplied CLI context."
    assert decision.agent_id == "legacy-agent"
    assert decision.agent_role == "Developer"
    assert decision.task_id == "legacy-task"


@pytest.mark.parametrize(
    ("agent_id", "agent_role", "task_id", "reason"),
    [
        ("agent-from-task", None, None, "require agent_id, agent_role, and task_id"),
        (None, "QA", "qa-validation", "require agent_id, agent_role, and task_id"),
        ("wrong-agent", "QA", "qa-validation", "does not match the running orchestration task"),
        ("agent-from-task", "Developer", "qa-validation", "does not match orchestration task role"),
        ("agent-from-task", "QA", "wrong-task", "does not match the running orchestration task"),
    ],
)
def test_orchestration_cli_binding_blocks_partial_or_mismatched_active_context(
    orchestration_state,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    reason: str,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject incomplete or mismatched CLI ownership context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")
    bound_agent_id = task.agent_id if agent_id == "agent-from-task" else agent_id

    decision = service.authorize_cli_action(
        agent_id=bound_agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )

    assert decision.allowed is False
    assert reason in decision.reason


def test_orchestration_cli_allows_matching_running_task_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Allow exact running task CLI context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")

    decision = service.authorize_cli_action(
        agent_id=task.agent_id,
        agent_role="qa",
        task_id=task.id,
    )

    assert decision.allowed is True
    assert decision.reason == "CLI action is bound to a running orchestration task."
    assert decision.run_id == run.id
    assert decision.agent_id == task.agent_id
    assert decision.agent_role == "qa"
    assert decision.task_id == task.id


def test_orchestration_tool_context_is_backward_compatible_without_active_task_match(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    service.create_run(
        OrchestrationCreateRequest(
            objective="Keep legacy tool context behavior when no task matches.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    decision = service.authorize_tool_action(
        agent_id="legacy-agent",
        agent_role="Developer",
        task_id="legacy-task",
    )

    assert decision.allowed is True
    assert decision.reason == "No active orchestration task matched supplied tool context."
    assert decision.agent_id == "legacy-agent"
    assert decision.agent_role == "Developer"
    assert decision.task_id == "legacy-task"


@pytest.mark.parametrize(
    ("agent_id", "agent_role", "task_id", "reason"),
    [
        ("agent-from-task", None, None, "require agent_id, agent_role, and task_id"),
        (None, "QA", "qa-validation", "require agent_id, agent_role, and task_id"),
        ("wrong-agent", "QA", "qa-validation", "does not match the running orchestration task"),
        ("agent-from-task", "Developer", "qa-validation", "does not match orchestration task role"),
        ("agent-from-task", "QA", "wrong-task", "does not match the running orchestration task"),
    ],
)
def test_orchestration_tool_binding_blocks_partial_or_mismatched_active_context(
    orchestration_state,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    reason: str,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject incomplete or mismatched tool ownership context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")
    bound_agent_id = task.agent_id if agent_id == "agent-from-task" else agent_id

    decision = service.authorize_tool_action(
        agent_id=bound_agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )

    assert decision.allowed is False
    assert reason in decision.reason


def test_orchestration_tool_binding_blocks_known_non_running_task_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject stale tool ownership context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")
    run = service.update_task(
        run.id,
        task.id,
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    decision = service.authorize_tool_action(
        agent_id=task.agent_id,
        agent_role=task.role,
        task_id=task.id,
    )

    assert _task_by_id(run, "qa-validation").status == StepStatus.completed
    assert decision.allowed is False
    assert "not running" in decision.reason


def test_orchestration_tool_binding_blocks_known_terminal_run_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject terminal-run tool ownership context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")
    run = service.update_task(
        run.id,
        task.id,
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )
    closed = service.close_run(
        run.id,
        OrchestrationCloseRequest(
            evidence={
                "tests": "pytest passed",
                "docs": "docs updated",
                "review": "review completed",
            }
        ),
    )

    decision = service.authorize_tool_action(
        agent_id=task.agent_id,
        agent_role=task.role,
        task_id=task.id,
    )

    assert closed.status == PlanStatus.completed
    assert decision.allowed is False
    assert "not running" in decision.reason


def test_orchestration_tool_binding_blocks_pending_known_task_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject pending tool ownership context.",
            tasks=[
                _task("dev-implementation", role="Developer", paths=["src/dgentic/tools.py"]),
                _task(
                    "qa-validation",
                    role="QA",
                    dependencies=["dev-implementation"],
                    paths=["tests/test_orchestration.py"],
                ),
            ],
        )
    )

    decision = service.authorize_tool_action(
        agent_id=None,
        agent_role="QA",
        task_id="qa-validation",
    )

    assert _task_by_id(run, "qa-validation").status == StepStatus.pending
    assert decision.allowed is False
    assert "not running" in decision.reason


def test_orchestration_tool_allows_matching_running_task_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Allow exact running task tool context.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")

    decision = service.authorize_tool_action(
        agent_id=task.agent_id,
        agent_role="qa",
        task_id=task.id,
    )

    assert decision.allowed is True
    assert decision.reason == "Tool action is bound to a running orchestration task."
    assert decision.run_id == run.id
    assert decision.agent_id == task.agent_id
    assert decision.agent_role == "qa"
    assert decision.task_id == task.id


def test_orchestration_retry_exhaustion_creates_blocker_and_follow_up(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Escalate repeatedly failing QA validation.",
            tasks=[
                _task(
                    "qa-validation",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    retry_limit=1,
                )
            ],
        )
    )

    run = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.failed, error="First test pass failed."),
    )

    task = _task_by_id(run, "qa-validation")
    assert task.status == StepStatus.running
    assert task.retry_count == 1
    assert task.agent_id
    assert run.scheduled_task_ids == ["qa-validation"]
    assert run.blockers == []
    assert run.follow_ups == []

    run = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.failed, error="Still failing after retry."),
    )

    task = _task_by_id(run, "qa-validation")
    assert task.status == StepStatus.blocked
    assert task.retry_count == 2
    assert task.error == "Still failing after retry."
    assert [(blocker.task_id, blocker.severity, blocker.reason) for blocker in run.blockers] == [
        ("qa-validation", "retry_exhausted", "Still failing after retry.")
    ]
    assert [(follow_up.task_id, follow_up.assigned_role) for follow_up in run.follow_ups] == [
        ("qa-validation", "QA")
    ]


def test_orchestration_close_requires_completed_tasks_and_dod_evidence(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Gate closeout on validation evidence.",
            required_dod_evidence=["tests", "review"],
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    with pytest.raises(OrchestrationError, match="incomplete tasks"):
        service.close_run(
            run.id,
            OrchestrationCloseRequest(
                evidence={"tests": "pytest tests/test_orchestration.py passed"}
            ),
        )

    run = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    with pytest.raises(OrchestrationError, match="review"):
        service.close_run(
            run.id,
            OrchestrationCloseRequest(
                evidence={"tests": "pytest tests/test_orchestration.py passed"}
            ),
        )

    closed = service.close_run(
        run.id,
        OrchestrationCloseRequest(
            evidence={
                "tests": "pytest tests/test_orchestration.py passed",
                "review": "Reviewer reported no blockers.",
            }
        ),
    )

    assert closed.status == PlanStatus.completed
    assert closed.completed_at is not None
    assert closed.dod_evidence == {
        "tests": "pytest tests/test_orchestration.py passed",
        "review": "Reviewer reported no blockers.",
    }


def test_orchestration_rejects_updates_after_close(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Prevent closed run mutation.",
            required_dod_evidence=["tests"],
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    run = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )
    closed = service.close_run(
        run.id,
        OrchestrationCloseRequest(evidence={"tests": "pytest passed"}),
    )

    with pytest.raises(OrchestrationError, match="closed orchestration"):
        service.advance_run(closed.id)
    with pytest.raises(OrchestrationError, match="closed orchestration"):
        service.update_task(
            closed.id,
            "qa-validation",
            OrchestrationTaskUpdate(status=StepStatus.failed, error="late failure"),
        )


def test_orchestration_rejects_invalid_task_status_transitions(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Prevent duplicate scheduling.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    with pytest.raises(OrchestrationError, match="completed, failed, or blocked"):
        service.update_task(
            run.id,
            "qa-validation",
            OrchestrationTaskUpdate(status=StepStatus.pending),
        )


def test_orchestration_bounds_ready_task_scheduling_per_pass(
    orchestration_state,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Bound ready task fan-out.",
            tasks=[
                _task(
                    f"qa-validation-{index}",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                )
                for index in range(25)
            ],
        )
    )

    running_tasks = [task for task in run.tasks if task.status == StepStatus.running]
    pending_tasks = [task for task in run.tasks if task.status == StepStatus.pending]
    assert len(run.scheduled_task_ids) == 20
    assert len(running_tasks) == 20
    assert len(pending_tasks) == 5


def _task(
    task_id: str,
    *,
    role: str,
    dependencies: list[str] | None = None,
    paths: list[str] | None = None,
    retry_limit: int = 0,
) -> OrchestrationTaskSpec:
    return OrchestrationTaskSpec(
        id=task_id,
        title=f"{task_id} title",
        description=f"{task_id} description",
        role=role,
        dependencies=dependencies or [],
        declared_write_paths=paths or [],
        expected_output=f"{task_id} output",
        validation=f"{task_id} validation",
        retry_limit=retry_limit,
    )


def _invalid_graph_tasks(case: str) -> list[OrchestrationTask]:
    if case == "duplicate":
        return [_task("qa-tests", role="QA"), _task("qa-tests", role="QA")]
    if case == "unknown":
        return [_task("qa-tests", role="QA", dependencies=["missing"])]
    if case == "self":
        return [_task("qa-tests", role="QA", dependencies=["qa-tests"])]
    if case == "cycle":
        return [
            _task("dev-impl", role="Developer", dependencies=["qa-tests"]),
            _task("qa-tests", role="QA", dependencies=["dev-impl"]),
        ]
    raise AssertionError(f"Unexpected invalid graph case: {case}")


def _task_by_id(run, task_id: str) -> OrchestrationTask:
    return next(task for task in run.tasks if task.id == task_id)


def _status_by_id(run) -> dict[str, StepStatus]:
    return {task.id: task.status for task in run.tasks}
