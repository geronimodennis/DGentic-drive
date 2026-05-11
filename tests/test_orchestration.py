import pytest

from dgentic.agents import get_agent, update_agent_status
from dgentic.events import event_log
from dgentic.orchestration import OrchestrationError, OrchestrationService
from dgentic.schemas import (
    AgentStatus,
    AgentStatusUpdate,
    LogEventType,
    OrchestrationBlocker,
    OrchestrationBlockerResolutionRequest,
    OrchestrationCloseRequest,
    OrchestrationCreateRequest,
    OrchestrationTask,
    OrchestrationTaskRecoveryRequest,
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


def test_orchestration_cycle_reconciles_completed_agent_and_schedules_dependency(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reconcile completed agent work.",
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
    dev_task = _task_by_id(run, "dev-implementation")
    assert dev_task.agent_id
    update_agent_status(
        dev_task.agent_id,
        AgentStatusUpdate(status=AgentStatus.completed, note="Implementation done."),
    )
    completed_agent = get_agent(dev_task.agent_id)
    assert completed_agent is not None
    completed_at = completed_agent.completed_at

    cycled = service.run_cycle(run.id)

    completed_task = _task_by_id(cycled, "dev-implementation")
    qa_task = _task_by_id(cycled, "qa-validation")
    assert completed_task.status == StepStatus.completed
    assert completed_task.output == {
        "agent_id": dev_task.agent_id,
        "agent_status": AgentStatus.completed,
    }
    assert cycled.scheduled_task_ids == ["qa-validation"]
    assert qa_task.status == StepStatus.running
    assert qa_task.agent_id
    agent_after_cycle = get_agent(dev_task.agent_id)
    assert agent_after_cycle is not None
    assert agent_after_cycle.status == AgentStatus.completed
    assert agent_after_cycle.completed_at == completed_at


def test_orchestration_cycle_reconciles_multiple_completed_agents_before_scheduling(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reconcile parallel completed agent work.",
            tasks=[
                _task("dev-implementation", role="Developer", paths=["src/dgentic/tools.py"]),
                _task("qa-validation", role="QA", paths=["tests/test_orchestration.py"]),
                _task(
                    "pm-closeout",
                    role="PM",
                    dependencies=["dev-implementation", "qa-validation"],
                    paths=["docs/progress/project-progress-log.md"],
                ),
            ],
        )
    )
    for task_id in ["dev-implementation", "qa-validation"]:
        agent_id = _task_by_id(run, task_id).agent_id
        assert agent_id
        update_agent_status(agent_id, AgentStatusUpdate(status=AgentStatus.completed))

    cycled = service.run_cycle(run.id)

    assert _task_by_id(cycled, "dev-implementation").status == StepStatus.completed
    assert _task_by_id(cycled, "qa-validation").status == StepStatus.completed
    assert cycled.scheduled_task_ids == ["pm-closeout"]
    assert _task_by_id(cycled, "pm-closeout").status == StepStatus.running


def test_orchestration_cycle_reports_all_independent_tasks_scheduled_in_one_cycle(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Report all downstream schedules from one cycle.",
            tasks=[
                _task("root-a", role="Developer", paths=["src/dgentic/tools.py"]),
                _task("root-b", role="QA", paths=["tests/test_orchestration.py"]),
                _task(
                    "after-a",
                    role="PM",
                    dependencies=["root-a"],
                    paths=["docs/progress/project-progress-log.md"],
                ),
                _task(
                    "after-b",
                    role="PM",
                    dependencies=["root-b"],
                    paths=["docs/planning/backlog-needs-to-be-done.md"],
                ),
            ],
        )
    )
    for task_id in ["root-a", "root-b"]:
        agent_id = _task_by_id(run, task_id).agent_id
        assert agent_id
        update_agent_status(agent_id, AgentStatusUpdate(status=AgentStatus.completed))

    cycled = service.run_cycle(run.id)

    assert set(cycled.scheduled_task_ids) == {"after-a", "after-b"}
    assert _task_by_id(cycled, "after-a").status == StepStatus.running
    assert _task_by_id(cycled, "after-b").status == StepStatus.running


def test_orchestration_cycle_retries_then_blocks_failed_agent_work(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Retry failed agent work through cycle.",
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
    first_agent_id = _task_by_id(run, "qa-validation").agent_id
    assert first_agent_id
    update_agent_status(first_agent_id, AgentStatusUpdate(status=AgentStatus.failed))
    failed_agent = get_agent(first_agent_id)
    assert failed_agent is not None
    failed_at = failed_agent.completed_at

    retried = service.run_cycle(run.id)
    retried_task = _task_by_id(retried, "qa-validation")

    assert retried_task.status == StepStatus.running
    assert retried_task.retry_count == 1
    assert retried_task.agent_id
    assert retried_task.agent_id != first_agent_id
    assert retried.blockers == []
    first_agent_after_cycle = get_agent(first_agent_id)
    assert first_agent_after_cycle is not None
    assert first_agent_after_cycle.status == AgentStatus.failed
    assert first_agent_after_cycle.completed_at == failed_at

    update_agent_status(retried_task.agent_id, AgentStatusUpdate(status=AgentStatus.failed))
    blocked = service.run_cycle(retried.id)
    blocked_task = _task_by_id(blocked, "qa-validation")

    assert blocked_task.status == StepStatus.blocked
    assert blocked_task.retry_count == 2
    assert "reported failed status" in (blocked_task.error or "")
    assert [(blocker.task_id, blocker.severity) for blocker in blocked.blockers] == [
        ("qa-validation", "retry_exhausted")
    ]


def test_orchestration_cycle_blocks_cancelled_agent_without_overwriting_agent_status(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Block cancelled agent work through cycle.",
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
    task = _task_by_id(run, "dev-implementation")
    assert task.agent_id
    update_agent_status(task.agent_id, AgentStatusUpdate(status=AgentStatus.cancelled))

    cycled = service.run_cycle(run.id)

    assert _task_by_id(cycled, "dev-implementation").status == StepStatus.blocked
    assert _task_by_id(cycled, "qa-validation").status == StepStatus.pending
    assert cycled.scheduled_task_ids == []
    assert [(blocker.task_id, blocker.severity) for blocker in cycled.blockers] == [
        ("dev-implementation", "blocked")
    ]
    agent = get_agent(task.agent_id)
    assert agent is not None
    assert agent.status == AgentStatus.cancelled


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


def test_orchestration_recovers_blocked_task_after_safe_reassignment(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Recover out-of-bound task assignment.",
            tasks=[
                _task(
                    "qa-source-edit",
                    role="QA",
                    paths=["src/dgentic/orchestration.py"],
                )
            ],
        )
    )

    recovered = service.recover_task(
        run.id,
        "qa-source-edit",
        OrchestrationTaskRecoveryRequest(
            resolution="Reassigned source work to Developer.",
            role="Developer",
            declared_write_paths=["src/dgentic/orchestration.py"],
        ),
    )
    task = _task_by_id(recovered, "qa-source-edit")

    assert recovered.blockers == []
    assert recovered.follow_ups == []
    assert recovered.scheduled_task_ids == ["qa-source-edit"]
    assert task.status == StepStatus.running
    assert task.role == "Developer"
    assert task.declared_write_paths == ["src/dgentic/orchestration.py"]
    assert task.error is None
    assert task.agent_id
    assert recovered.role_boundary_decisions[0].allowed is True


def test_orchestration_recovery_waits_for_dependencies_before_rescheduling(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Recover blocked dependent work.",
            tasks=[
                _task("dev-implementation", role="Developer", paths=["src/dgentic/tools.py"]),
                _task(
                    "qa-validation",
                    role="QA",
                    dependencies=["dev-implementation"],
                    paths=["src/dgentic/orchestration.py"],
                ),
            ],
        )
    )

    recovered = service.recover_task(
        run.id,
        "qa-validation",
        OrchestrationTaskRecoveryRequest(
            resolution="Corrected QA write scope.",
            declared_write_paths=["tests/test_orchestration.py"],
        ),
    )
    waiting_task = _task_by_id(recovered, "qa-validation")

    assert waiting_task.status == StepStatus.pending
    assert waiting_task.agent_id is None
    assert recovered.scheduled_task_ids == []
    assert recovered.blockers == []
    assert recovered.follow_ups == []

    advanced = service.update_task(
        recovered.id,
        "dev-implementation",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"source": "done"}),
    )

    assert advanced.scheduled_task_ids == ["qa-validation"]
    assert _task_by_id(advanced, "qa-validation").status == StepStatus.running


def test_orchestration_recovery_rejects_still_invalid_or_non_blocked_tasks(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject unsafe blocked-task recovery.",
            tasks=[
                _task(
                    "qa-source-edit",
                    role="QA",
                    paths=["src/dgentic/orchestration.py"],
                ),
                _task("qa-running", role="QA", paths=["tests/test_orchestration.py"]),
            ],
        )
    )

    with pytest.raises(OrchestrationError, match="role-boundary validation still fails"):
        service.recover_task(
            run.id,
            "qa-source-edit",
            OrchestrationTaskRecoveryRequest(resolution="Try without correcting scope."),
        )
    with pytest.raises(OrchestrationError, match="only blocked tasks can be recovered"):
        service.recover_task(
            run.id,
            "qa-running",
            OrchestrationTaskRecoveryRequest(resolution="Already running."),
        )

    unchanged = service.get_run(run.id)
    assert unchanged is not None
    assert _task_by_id(unchanged, "qa-source-edit").status == StepStatus.blocked
    assert unchanged.blockers


def test_orchestration_recovery_requires_meaningful_resolution(
    orchestration_state,
) -> None:
    with pytest.raises(ValueError, match="resolution must not be blank"):
        OrchestrationTaskRecoveryRequest(resolution="   ")


def test_orchestration_recovery_preserves_manual_blockers(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Preserve manual blocker review.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Needs security review."),
    )

    with pytest.raises(OrchestrationError, match="requires separate review"):
        service.recover_task(
            blocked.id,
            "qa-validation",
            OrchestrationTaskRecoveryRequest(resolution="Security reviewed."),
        )

    unchanged = service.get_run(blocked.id)
    assert unchanged is not None
    assert _task_by_id(unchanged, "qa-validation").status == StepStatus.blocked
    assert [(blocker.task_id, blocker.severity) for blocker in unchanged.blockers] == [
        ("qa-validation", "blocked")
    ]
    assert [(follow_up.task_id, follow_up.assigned_role) for follow_up in unchanged.follow_ups] == [
        ("qa-validation", "QA")
    ]


def test_orchestration_resolves_manual_blocker_and_preserves_audit_history(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Resolve a manually blocked task.",
            required_dod_evidence=["tests"],
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Needs security review."),
    )
    blocker_id = blocked.blockers[0].id

    resolved = service.resolve_blocker(
        blocked.id,
        blocker_id,
        OrchestrationBlockerResolutionRequest(
            resolution="TOKEN=secret-value mitigation accepted.",
            reschedule=True,
        ),
        actor="admin-actor",
    )
    task = _task_by_id(resolved, "qa-validation")

    assert task.status == StepStatus.running
    assert task.error is None
    assert task.agent_id
    assert resolved.follow_ups == []
    assert resolved.scheduled_task_ids == ["qa-validation"]
    assert len(resolved.blockers) == 1
    blocker = resolved.blockers[0]
    assert blocker.id == blocker_id
    assert blocker.status == "resolved"
    assert blocker.resolved_by == "admin-actor"
    assert blocker.resolution == "TOKEN=[REDACTED] mitigation accepted."
    assert blocker.resolved_at is not None

    done = service.update_task(
        resolved.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )
    closed = service.close_run(
        done.id,
        OrchestrationCloseRequest(evidence={"tests": "pytest passed"}),
    )

    assert closed.status == PlanStatus.completed
    assert closed.blockers[0].status == "resolved"


def test_orchestration_resolving_final_blocker_without_reschedule_leaves_task_pending(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Resolve without immediate scheduling.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(
            status=StepStatus.blocked,
            output={"partial": "stale"},
            error="Needs review.",
        ),
    )

    resolved = service.resolve_blocker(
        blocked.id,
        blocked.blockers[0].id,
        OrchestrationBlockerResolutionRequest(resolution="Reviewed without immediate schedule."),
    )
    task = _task_by_id(resolved, "qa-validation")

    assert task.status == StepStatus.pending
    assert task.agent_id is None
    assert task.output == {}
    assert task.error is None
    assert resolved.scheduled_task_ids == []
    assert resolved.blockers[0].status == "resolved"
    assert resolved.follow_ups == []

    advanced = service.advance_run(resolved.id)

    assert advanced.scheduled_task_ids == ["qa-validation"]
    assert _task_by_id(advanced, "qa-validation").status == StepStatus.running


def test_orchestration_blocker_resolution_reports_actual_reschedule(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Do not overreport scheduling.",
            tasks=[
                _task("dev-impl", role="Developer", paths=["src/dgentic/orchestration.py"]),
                _task(
                    "qa-validation",
                    role="QA",
                    dependencies=["dev-impl"],
                    paths=["tests/test_orchestration.py"],
                ),
            ],
        )
    )
    blocker = OrchestrationBlocker(
        id="blocker-dependent-qa",
        task_id="qa-validation",
        reason="Manual review before dependency is done.",
    )
    blocked_tasks = [
        task.model_copy(
            update={
                "status": StepStatus.blocked,
                "error": blocker.reason,
            }
        )
        if task.id == "qa-validation"
        else task.model_copy(update={"status": StepStatus.pending, "agent_id": None})
        for task in run.tasks
    ]
    blocked = run.model_copy(
        update={
            "tasks": blocked_tasks,
            "blockers": [blocker],
            "scheduled_task_ids": [],
        }
    )
    service._runs.upsert(blocked)

    resolved = service.resolve_blocker(
        blocked.id,
        blocker.id,
        OrchestrationBlockerResolutionRequest(
            resolution="Reviewed, but dependency remains incomplete.",
            reschedule=True,
        ),
    )

    assert _task_by_id(resolved, "qa-validation").status == StepStatus.pending
    assert resolved.scheduled_task_ids == ["dev-impl"]
    resolution_event = next(
        event
        for event in reversed(event_log.list(LogEventType.task))
        if event.subject_id == resolved.id and event.message == "Resolved orchestration blocker."
    )
    assert resolution_event.metadata["reschedule_requested"] is True
    assert resolution_event.metadata["rescheduled"] is False


def test_orchestration_resolves_security_blocker(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Resolve security blocker.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Needs security review."),
    )
    security_blocker = blocked.blockers[0].model_copy(update={"severity": "security"})
    blocked = blocked.model_copy(update={"blockers": [security_blocker]})
    service._runs.upsert(blocked)

    resolved = service.resolve_blocker(
        blocked.id,
        security_blocker.id,
        OrchestrationBlockerResolutionRequest(
            resolution="Security accepted mitigation.",
            reschedule=True,
        ),
        actor="security-admin",
    )

    assert resolved.blockers[0].severity == "security"
    assert resolved.blockers[0].status == "resolved"
    assert resolved.blockers[0].resolved_by == "security-admin"
    assert _task_by_id(resolved, "qa-validation").status == StepStatus.running


def test_orchestration_resolve_blocker_rejects_system_blockers_and_repeats(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Keep system blockers on the recovery path.",
            tasks=[
                _task(
                    "qa-source-edit",
                    role="QA",
                    paths=["src/dgentic/orchestration.py"],
                )
            ],
        )
    )
    blocker_id = run.blockers[0].id

    with pytest.raises(OrchestrationError, match="role_boundary blocker"):
        service.resolve_blocker(
            run.id,
            blocker_id,
            OrchestrationBlockerResolutionRequest(resolution="Manual override."),
        )

    unchanged = service.get_run(run.id)
    assert unchanged is not None
    assert unchanged.blockers[0].status == "open"

    recovered = service.recover_task(
        run.id,
        "qa-source-edit",
        OrchestrationTaskRecoveryRequest(
            resolution="Reassigned to Developer.",
            role="Developer",
            declared_write_paths=["src/dgentic/orchestration.py"],
        ),
    )
    blocked = service.update_task(
        recovered.id,
        "qa-source-edit",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Needs manual review."),
    )
    manual_blocker_id = blocked.blockers[0].id
    resolved = service.resolve_blocker(
        blocked.id,
        manual_blocker_id,
        OrchestrationBlockerResolutionRequest(resolution="Reviewed."),
    )

    with pytest.raises(OrchestrationError, match="already resolved"):
        service.resolve_blocker(
            resolved.id,
            manual_blocker_id,
            OrchestrationBlockerResolutionRequest(resolution="Reviewed again."),
        )


def test_orchestration_blocker_resolution_requires_meaningful_resolution(
    orchestration_state,
) -> None:
    with pytest.raises(ValueError, match="resolution must not be blank"):
        OrchestrationBlockerResolutionRequest(resolution="   ")


def test_orchestration_recovery_can_reset_retry_count(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Recover retry-exhausted work.",
            tasks=[
                _task(
                    "qa-validation",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    retry_limit=0,
                )
            ],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.failed, error="Validation failed."),
    )
    assert _task_by_id(blocked, "qa-validation").retry_count == 1
    assert _task_by_id(blocked, "qa-validation").status == StepStatus.blocked

    recovered = service.recover_task(
        blocked.id,
        "qa-validation",
        OrchestrationTaskRecoveryRequest(
            resolution="Fixed fixture setup.",
            reset_retry_count=True,
        ),
    )
    task = _task_by_id(recovered, "qa-validation")

    assert task.status == StepStatus.running
    assert task.retry_count == 0
    assert recovered.blockers == []
    assert recovered.follow_ups == []


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
    with pytest.raises(OrchestrationError, match="closed orchestration"):
        service.recover_task(
            closed.id,
            "qa-validation",
            OrchestrationTaskRecoveryRequest(resolution="late recovery"),
        )
    with pytest.raises(OrchestrationError, match="closed orchestration"):
        service.run_cycle(closed.id)


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
