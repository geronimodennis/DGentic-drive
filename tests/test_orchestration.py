import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from dgentic.agents import get_agent, update_agent_status
from dgentic.database import get_db_session, reset_database_state
from dgentic.events import event_log
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.schemas import MetadataCreateRequest
from dgentic.orchestration import OrchestrationError, OrchestrationService
from dgentic.schemas import (
    AgentStatus,
    AgentStatusUpdate,
    LogEventType,
    OrchestrationBlocker,
    OrchestrationBlockerResolutionRequest,
    OrchestrationCloseRequest,
    OrchestrationCreateRequest,
    OrchestrationExecution,
    OrchestrationExecutionStatus,
    OrchestrationLoopRequest,
    OrchestrationLoopResult,
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
    reset_database_state()
    yield data_dir
    reset_database_state()
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


def test_orchestration_schedules_dependency_agent_with_redacted_shared_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Coordinate PASSWORD=objective-secret context handoff.",
            tasks=[
                OrchestrationTaskSpec(
                    id="dev-implementation",
                    title="Implement API_KEY=title-secret source",
                    description="Implement source changes.",
                    role="Developer",
                    declared_write_paths=["src/dgentic/tools.py"],
                    expected_output="Source changes are ready.",
                    validation="Developer work complete.",
                ),
                _task(
                    "qa-validation",
                    role="QA",
                    dependencies=["dev-implementation"],
                    paths=["tests/test_orchestration.py"],
                    expected_output="",
                    title="Validate TOKEN=qa-title-secret source",
                    validation="QA receives PASSWORD=validation-secret context.",
                ),
            ],
        )
    )

    updated = service.update_task(
        run.id,
        "dev-implementation",
        OrchestrationTaskUpdate(
            status=StepStatus.completed,
            output={"summary": "plain-secret-value", "credential": "API_KEY=implementation-secret"},
        ),
    )
    qa_task = _task_by_id(updated, "qa-validation")
    assert qa_task.agent_id
    qa_agent = get_agent(qa_task.agent_id)
    assert qa_agent is not None

    serialized_context = "\n".join(qa_agent.context)
    serialized_agent = qa_agent.model_dump_json()
    assert qa_agent.context[0] == "Coordinate PASSWORD=[REDACTED] context handoff."
    assert qa_agent.task == "Validate TOKEN=[REDACTED] source"
    assert qa_agent.expected_output == "QA receives PASSWORD=[REDACTED] context."
    assert "Dependency dev-implementation (Developer) completed" in serialized_context
    assert "Implement API_KEY=[REDACTED] source" in serialized_context
    assert '"summary": "[REDACTED]"' in serialized_context
    assert '"credential": "[REDACTED]"' in serialized_context
    assert "qa-title-secret" not in serialized_agent
    assert "validation-secret" not in serialized_agent
    assert "objective-secret" not in serialized_context
    assert "title-secret" not in serialized_context
    assert "implementation-secret" not in serialized_context
    assert "plain-secret-value" not in serialized_context
    assert qa_agent.required_data == ["dev-implementation"]


def test_orchestration_shared_memory_publishes_and_reuses_tagged_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    producer = service.create_run(
        OrchestrationCreateRequest(
            objective="Produce tagged QA memory.",
            shared_memory_tags=["QA Context"],
            tasks=[
                _task(
                    "qa-producer",
                    role="QA",
                    title="QA producer",
                    paths=["tests/test_orchestration.py"],
                )
            ],
        )
    )
    completed = service.update_task(
        producer.id,
        "qa-producer",
        OrchestrationTaskUpdate(
            status=StepStatus.completed,
            output={"summary": "Use regression smoke checks.", "secret": "TOKEN=memory-secret"},
        ),
    )
    service._publish_completed_task_memory(
        completed,
        _task_by_id(completed, "qa-producer"),
        actor="qa-owner",
    )
    session = get_db_session()
    try:
        items, total = MetadataService(session).list_by_filters(
            entity_type="memory",
            category="orchestration_context",
            tags=["qa-context"],
        )
    finally:
        session.close()

    consumer = service.create_run(
        OrchestrationCreateRequest(
            objective="Consume tagged QA memory.",
            shared_memory_tags=["qa-context"],
            tasks=[
                _task(
                    "qa-consumer",
                    role="QA",
                    title="QA consumer",
                    paths=["tests/test_orchestration.py"],
                )
            ],
        )
    )
    agent_id = _task_by_id(consumer, "qa-consumer").agent_id
    assert agent_id is not None
    agent = get_agent(agent_id)
    assert agent is not None
    rendered_context = "\n".join(agent.context)

    assert total == 1
    assert len(items) == 1
    assert items[0].entity_id == f"orchestration:{producer.id}:qa-producer"
    assert items[0].owner_agent == "system"
    assert '"secret": "[REDACTED]"' in (items[0].description or "")
    assert "memory-secret" not in (items[0].description or "")
    assert "Shared memory" in rendered_context
    assert "qa-context" in rendered_context
    assert '"secret": "[REDACTED]"' in rendered_context
    assert "memory-secret" not in rendered_context


def test_orchestration_shared_memory_ignores_untagged_and_inactive_records(
    orchestration_state,
) -> None:
    orchestration = OrchestrationService()
    active_source = orchestration.create_run(
        OrchestrationCreateRequest(
            objective="Produce active shared memory.",
            shared_memory_tags=["qa-context"],
            tasks=[_task("qa-active", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    archived_source = orchestration.create_run(
        OrchestrationCreateRequest(
            objective="Produce archived shared memory.",
            shared_memory_tags=["qa-context"],
            tasks=[_task("qa-archived", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    orchestration.update_task(
        active_source.id,
        "qa-active",
        OrchestrationTaskUpdate(
            status=StepStatus.completed, output={"summary": "Active QA memory."}
        ),
    )
    orchestration.update_task(
        archived_source.id,
        "qa-archived",
        OrchestrationTaskUpdate(
            status=StepStatus.completed,
            output={"summary": "Archived QA memory."},
        ),
    )
    archived_entity_id = f"orchestration:{archived_source.id}:qa-archived"
    session = get_db_session()
    try:
        items, _total = MetadataService(session).list_by_filters(
            entity_type="memory",
            category="orchestration_context",
            tags=["qa-context"],
        )
        archived = next(item for item in items if item.entity_id == archived_entity_id)
        MetadataService(session).update(archived.id, lifecycle_state="archived")
    finally:
        session.close()

    untagged = orchestration.create_run(
        OrchestrationCreateRequest(
            objective="No shared memory tags.",
            tasks=[_task("qa-untagged", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    tagged = orchestration.create_run(
        OrchestrationCreateRequest(
            objective="Use shared memory tags.",
            tasks=[
                _task(
                    "qa-tagged",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    shared_memory_tags=["qa-context"],
                )
            ],
        )
    )
    untagged_agent = get_agent(_task_by_id(untagged, "qa-untagged").agent_id or "")
    tagged_agent = get_agent(_task_by_id(tagged, "qa-tagged").agent_id or "")
    assert untagged_agent is not None
    assert tagged_agent is not None
    untagged_context = "\n".join(untagged_agent.context)
    tagged_context = "\n".join(tagged_agent.context)

    assert f"orchestration:{active_source.id}:qa-active" not in untagged_context
    assert f"Shared memory orchestration:{active_source.id}:qa-active" in tagged_context
    assert archived_entity_id not in tagged_context


def test_orchestration_shared_memory_requires_all_tags_and_valid_provenance(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    producer = service.create_run(
        OrchestrationCreateRequest(
            objective="Produce scoped QA memory.",
            shared_memory_tags=["qa-context"],
            tasks=[
                _task(
                    "qa-producer",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    shared_memory_tags=["smoke"],
                )
            ],
        )
    )
    completed = service.update_task(
        producer.id,
        "qa-producer",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"summary": "Use smoke."}),
    )
    session = get_db_session()
    try:
        MetadataService(session).create(
            MetadataCreateRequest(
                entity_type="memory",
                entity_id="orchestration:missing-run:qa-producer",
                tags=["qa-context", "smoke"],
                category="orchestration_context",
                description="Spoofed orchestration memory.",
                owner_agent="system",
            )
        )
        MetadataService(session).create(
            MetadataCreateRequest(
                entity_type="memory",
                entity_id="broad-tag-memory",
                tags=["qa-context"],
                category="orchestration_context",
                description="Broad tag should not match all tags.",
                owner_agent="system",
            )
        )
    finally:
        session.close()

    matching = service.create_run(
        OrchestrationCreateRequest(
            objective="Consume scoped QA memory.",
            shared_memory_tags=["qa-context"],
            tasks=[
                _task(
                    "qa-matching",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    shared_memory_tags=["smoke"],
                )
            ],
        )
    )
    broad_only = service.create_run(
        OrchestrationCreateRequest(
            objective="Consume broad QA memory.",
            shared_memory_tags=["qa-context"],
            tasks=[_task("qa-broad", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    matching_context = "\n".join(
        get_agent(_task_by_id(matching, "qa-matching").agent_id or "").context
    )
    broad_context = "\n".join(get_agent(_task_by_id(broad_only, "qa-broad").agent_id or "").context)

    assert completed.id in matching_context
    assert "Shared memory" in matching_context
    assert "Spoofed orchestration memory" not in matching_context
    assert "Broad tag should not match all tags" not in matching_context
    assert completed.id not in broad_context


def test_orchestration_shared_memory_owner_scope_blocks_cross_actor_context(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    alpha = service.create_run(
        OrchestrationCreateRequest(
            objective="Alpha produces memory.",
            shared_memory_tags=["qa-context"],
            requested_by="alpha-owner",
            tasks=[_task("qa-alpha", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    service.update_task(
        alpha.id,
        "qa-alpha",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"summary": "Alpha only."}),
    )

    beta = service.create_run(
        OrchestrationCreateRequest(
            objective="Beta tries same tag.",
            shared_memory_tags=["qa-context"],
            requested_by="beta-owner",
            tasks=[_task("qa-beta", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    alpha_consumer = service.create_run(
        OrchestrationCreateRequest(
            objective="Alpha consumes same tag.",
            shared_memory_tags=["qa-context"],
            requested_by="alpha-owner",
            tasks=[_task("qa-alpha-consumer", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    beta_context = "\n".join(get_agent(_task_by_id(beta, "qa-beta").agent_id or "").context)
    alpha_context = "\n".join(
        get_agent(_task_by_id(alpha_consumer, "qa-alpha-consumer").agent_id or "").context
    )

    assert "Alpha only" not in beta_context
    assert f"orchestration:{alpha.id}:qa-alpha" not in beta_context
    assert "Shared memory" in alpha_context
    assert f"orchestration:{alpha.id}:qa-alpha" in alpha_context


def test_orchestration_shared_memory_retrieval_failure_is_fail_soft_and_redacted(
    orchestration_state,
    monkeypatch,
) -> None:
    def fail_session():
        raise RuntimeError("TOKEN=retrieval-secret")

    monkeypatch.setattr("dgentic.orchestration.get_db_session", fail_session)
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Retrieve memory with failing SQL.",
            shared_memory_tags=["qa-context"],
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    task = _task_by_id(run, "qa-validation")
    agent = get_agent(task.agent_id or "")
    event = next(
        event
        for event in reversed(event_log.list(LogEventType.memory))
        if event.subject_id == run.id
        and event.message == "Failed to retrieve orchestration shared memory."
    )
    serialized_event = json.dumps(event.model_dump(), default=str)

    assert task.status == StepStatus.running
    assert agent is not None
    assert agent.context == ["Retrieve memory with failing SQL."]
    assert "retrieval-secret" not in serialized_event
    assert "TOKEN=[REDACTED]" in serialized_event


def test_orchestration_shared_memory_publish_failure_is_fail_soft_and_redacted(
    orchestration_state,
    monkeypatch,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Publish memory with failing SQL.",
            shared_memory_tags=["qa-context"],
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    def fail_session():
        raise RuntimeError("TOKEN=publish-secret")

    monkeypatch.setattr("dgentic.orchestration.get_db_session", fail_session)
    updated = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"summary": "Done."}),
    )
    event = next(
        event
        for event in reversed(event_log.list(LogEventType.memory))
        if event.subject_id == run.id
        and event.message == "Failed to publish orchestration shared memory."
    )
    serialized_event = json.dumps(event.model_dump(), default=str)

    assert _task_by_id(updated, "qa-validation").status == StepStatus.completed
    assert "publish-secret" not in serialized_event
    assert "TOKEN=[REDACTED]" in serialized_event


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


def test_orchestration_loop_reconciles_until_waiting_for_agents(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Loop completed agent work.",
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
    update_agent_status(dev_task.agent_id, AgentStatusUpdate(status=AgentStatus.completed))

    result = service.run_loop(run.id, OrchestrationLoopRequest(max_iterations=5))

    assert result.iterations == 2
    assert result.made_progress is True
    assert result.stopped_reason == "waiting_for_agents"
    assert result.running_task_ids == ["qa-validation"]
    assert result.pending_task_ids == []
    assert result.unresolved_blocker_ids == []
    assert _task_by_id(result.run, "dev-implementation").status == StepStatus.completed
    assert _task_by_id(result.run, "qa-validation").status == StepStatus.running


def test_background_execution_lifecycle_persists_and_completes_with_result_polling(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Run detached orchestration until it waits for agents.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    execution = service.start_background_execution(
        run.id,
        OrchestrationLoopRequest(max_iterations=3),
        actor="qa-owner",
    )
    completed = _poll_execution(service, run.id, execution.id)

    assert execution.status == OrchestrationExecutionStatus.starting
    assert execution.request.max_iterations == 3
    assert execution.requested_by == "qa-owner"
    assert completed.status == OrchestrationExecutionStatus.completed
    assert completed.result is not None
    assert completed.result.stopped_reason == "waiting_for_agents"
    assert completed.result.running_task_ids == ["qa-validation"]
    assert completed.completed_at is not None
    assert service.list_background_executions(run.id) == [completed]


def test_orchestration_operations_summary_counts_visible_runtime_state(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    active_run = service.create_run(
        OrchestrationCreateRequest(
            objective="Summarize active orchestration state.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    blocked_run = service.create_run(
        OrchestrationCreateRequest(
            objective="Summarize blocked orchestration state.",
            tasks=[
                _task(
                    "qa-source-edit",
                    role="QA",
                    paths=["src/dgentic/orchestration.py"],
                )
            ],
        )
    )
    now = datetime.now(UTC)
    service._executions.upsert(
        OrchestrationExecution(
            id="orchexec-active-summary",
            run_id=active_run.id,
            status=OrchestrationExecutionStatus.running,
            request=OrchestrationLoopRequest(max_iterations=1),
            supervisor_id=service.supervisor_id,
            started_at=now,
            last_heartbeat_at=now,
        )
    )
    service._executions.upsert(
        OrchestrationExecution(
            id="orchexec-stale-summary",
            run_id=blocked_run.id,
            status=OrchestrationExecutionStatus.running,
            request=OrchestrationLoopRequest(max_iterations=1),
            supervisor_id="old-supervisor",
            started_at=now - timedelta(seconds=301),
            last_heartbeat_at=now - timedelta(seconds=301),
        )
    )

    summary = service.get_operations_summary()
    persisted_stale_candidate = service._executions.get("orchexec-stale-summary")

    assert summary.total_runs == 2
    assert summary.run_status_counts == {"running": 2}
    assert summary.task_status_counts["running"] == 1
    assert summary.task_status_counts["blocked"] == 1
    assert summary.execution_status_counts["running"] == 1
    assert summary.execution_status_counts["stale"] == 1
    assert summary.active_execution_count == 1
    assert summary.active_execution_ids == ["orchexec-active-summary"]
    assert summary.stale_execution_count == 1
    assert summary.stale_execution_ids == ["orchexec-stale-summary"]
    assert summary.unresolved_blocker_count == 1
    assert summary.open_follow_up_count == 1
    assert summary.blocked_run_ids == [blocked_run.id]
    assert persisted_stale_candidate is not None
    assert persisted_stale_candidate.status == OrchestrationExecutionStatus.running


def test_orchestration_operations_summary_does_not_mutate_hidden_executions(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    alpha_run = service.create_run(
        OrchestrationCreateRequest(
            objective="Hidden alpha operations state.",
            requested_by="alpha-owner",
            tasks=[_task("qa-alpha", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    beta_run = service.create_run(
        OrchestrationCreateRequest(
            objective="Visible beta operations state.",
            requested_by="beta-owner",
            tasks=[_task("qa-beta", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    old_at = datetime.now(UTC) - timedelta(seconds=301)
    service._executions.upsert(
        OrchestrationExecution(
            id="orchexec-hidden-alpha",
            run_id=alpha_run.id,
            status=OrchestrationExecutionStatus.running,
            request=OrchestrationLoopRequest(max_iterations=1),
            supervisor_id="old-supervisor",
            started_at=old_at,
            last_heartbeat_at=old_at,
        )
    )

    summary = service.get_operations_summary(actor="beta-owner", include_all=False)
    hidden_execution = service._executions.get("orchexec-hidden-alpha")

    assert summary.total_runs == 1
    assert summary.active_execution_count == 0
    assert summary.stale_execution_count == 0
    assert beta_run.id not in summary.blocked_run_ids
    assert hidden_execution is not None
    assert hidden_execution.status == OrchestrationExecutionStatus.running
    assert hidden_execution.completed_at is None


def test_background_execution_rejects_duplicate_active_execution_across_service_instances(
    orchestration_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    service1 = OrchestrationService()
    run = service1.create_run(
        OrchestrationCreateRequest(
            objective="Keep the first detached execution active.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    first = service1.start_background_execution(run.id, OrchestrationLoopRequest(max_iterations=1))

    service2 = OrchestrationService()

    with pytest.raises(OrchestrationError, match=first.id):
        service2.start_background_execution(run.id, OrchestrationLoopRequest(max_iterations=1))

    persisted = service2.get_background_execution(run.id, first.id)
    assert persisted.status == OrchestrationExecutionStatus.starting
    assert persisted.supervisor_id == service1.supervisor_id


def test_background_execution_blocks_foreground_loop_while_active(
    orchestration_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject foreground loops during active detached execution.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    execution = service.start_background_execution(
        run.id,
        OrchestrationLoopRequest(max_iterations=1),
    )

    with pytest.raises(OrchestrationError, match=execution.id):
        service.run_loop(run.id, OrchestrationLoopRequest(max_iterations=1))


def test_background_execution_reconciles_prior_supervisor_active_records(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reconcile abandoned detached executions.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    fresh_at = datetime.now(UTC)
    old_at = fresh_at - timedelta(seconds=301)
    stale_starting = OrchestrationExecution(
        id="orchexec-old-starting",
        run_id=run.id,
        status=OrchestrationExecutionStatus.starting,
        request=OrchestrationLoopRequest(max_iterations=1),
        supervisor_id="previous-supervisor",
        started_at=old_at,
        last_heartbeat_at=None,
    )
    stale_running = stale_starting.model_copy(
        update={
            "id": "orchexec-old-running",
            "status": OrchestrationExecutionStatus.running,
            "last_heartbeat_at": old_at,
        }
    )
    fresh_running = stale_starting.model_copy(
        update={
            "id": "orchexec-fresh-running",
            "status": OrchestrationExecutionStatus.running,
            "started_at": fresh_at,
            "last_heartbeat_at": fresh_at,
        }
    )
    current_running = stale_starting.model_copy(
        update={
            "id": "orchexec-current-running",
            "status": OrchestrationExecutionStatus.running,
            "supervisor_id": service.supervisor_id,
            "last_heartbeat_at": old_at,
        }
    )
    service._executions.upsert(stale_starting)
    service._executions.upsert(stale_running)
    service._executions.upsert(fresh_running)
    service._executions.upsert(current_running)

    service.reconcile_stale_background_executions()

    assert (
        service.get_background_execution(run.id, "orchexec-old-starting").status
        == OrchestrationExecutionStatus.stale
    )
    assert (
        service.get_background_execution(run.id, "orchexec-old-running").status
        == OrchestrationExecutionStatus.stale
    )
    fresh = service.get_background_execution(run.id, "orchexec-fresh-running")
    assert fresh.status == OrchestrationExecutionStatus.running
    assert fresh.completed_at is None
    current = service.get_background_execution(run.id, "orchexec-current-running")
    assert current.status == OrchestrationExecutionStatus.running


def test_background_execution_polling_reconciles_expired_foreign_records(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Poll stale detached executions.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    old_at = datetime.now(UTC) - timedelta(seconds=301)
    service._executions.upsert(
        OrchestrationExecution(
            id="orchexec-poll-stale",
            run_id=run.id,
            status=OrchestrationExecutionStatus.running,
            request=OrchestrationLoopRequest(max_iterations=1),
            supervisor_id="previous-supervisor",
            started_at=old_at,
            last_heartbeat_at=old_at,
        )
    )

    fetched = service.get_background_execution(run.id, "orchexec-poll-stale")
    listed = service.list_background_executions(run.id)

    assert fetched.status == OrchestrationExecutionStatus.stale
    assert fetched.completed_at is not None
    assert [execution.status for execution in listed] == [OrchestrationExecutionStatus.stale]


def test_background_execution_heartbeat_keeps_foreign_running_record_fresh(
    orchestration_state,
) -> None:
    service1 = OrchestrationService()
    run = service1.create_run(
        OrchestrationCreateRequest(
            objective="Keep long detached executions fresh with heartbeat renewal.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    old_at = datetime.now(UTC) - timedelta(seconds=301)
    service1._executions.upsert(
        OrchestrationExecution(
            id="orchexec-heartbeat-running",
            run_id=run.id,
            status=OrchestrationExecutionStatus.running,
            request=OrchestrationLoopRequest(max_iterations=1),
            supervisor_id=service1.supervisor_id,
            started_at=old_at,
            last_heartbeat_at=old_at,
        )
    )

    renewed = service1._renew_background_execution_heartbeat("orchexec-heartbeat-running")
    service2 = OrchestrationService()
    fetched = service2.get_background_execution(run.id, "orchexec-heartbeat-running")

    assert renewed is not None
    assert renewed.last_heartbeat_at is not None
    assert renewed.last_heartbeat_at > old_at
    assert fetched.status == OrchestrationExecutionStatus.running
    assert fetched.completed_at is None


def test_background_execution_cancel_starting_record_allows_retry(
    orchestration_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Cancel queued detached execution.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    execution = service.start_background_execution(
        run.id,
        OrchestrationLoopRequest(max_iterations=1),
        actor="qa-owner",
    )

    cancelled = service.cancel_background_execution(
        run.id,
        execution.id,
        actor="qa-owner",
    )
    retry = service.start_background_execution(
        run.id,
        OrchestrationLoopRequest(max_iterations=1),
        actor="qa-owner",
    )

    assert cancelled.status == OrchestrationExecutionStatus.cancelled
    assert cancelled.completed_at is not None
    assert cancelled.status_reason == "Orchestration background execution cancelled before start."
    assert retry.status == OrchestrationExecutionStatus.starting
    assert retry.id != execution.id


def test_background_execution_cancel_running_record_blocks_duplicate_until_finalized(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Cancel running detached execution.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    now = datetime.now(UTC)
    execution = OrchestrationExecution(
        id="orchexec-running-cancel",
        run_id=run.id,
        status=OrchestrationExecutionStatus.running,
        request=OrchestrationLoopRequest(max_iterations=1),
        supervisor_id=service.supervisor_id,
        started_at=now,
        last_heartbeat_at=now,
    )
    service._executions.upsert(execution)

    cancelling = service.cancel_background_execution(run.id, execution.id, actor="qa-owner")
    assert cancelling.status == OrchestrationExecutionStatus.cancelling
    assert cancelling.completed_at is None
    with pytest.raises(OrchestrationError, match=execution.id):
        service.start_background_execution(run.id, OrchestrationLoopRequest(max_iterations=1))
    result = service.run_loop(
        run.id,
        OrchestrationLoopRequest(max_iterations=1),
        actor="qa-owner",
        background_execution_id=execution.id,
    )
    cancelled = service._finalize_background_execution(
        execution.id,
        status=OrchestrationExecutionStatus.cancelled,
        status_reason="Orchestration background execution cancelled.",
        result=result,
        actor="qa-owner",
    )
    assert result.stopped_reason == "cancelled"
    assert result.iterations == 0
    assert _task_by_id(result.run, "qa-validation").status == StepStatus.running
    assert cancelled is not None
    assert cancelled.status == OrchestrationExecutionStatus.cancelled
    assert cancelled.result is not None
    assert cancelled.result.stopped_reason == "cancelled"


def test_background_execution_cancel_rejects_terminal_execution(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject terminal detached cancellation.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    completed = OrchestrationExecution(
        id="orchexec-completed-cancel",
        run_id=run.id,
        status=OrchestrationExecutionStatus.completed,
        request=OrchestrationLoopRequest(max_iterations=1),
        supervisor_id=service.supervisor_id,
        status_reason="Already completed.",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        last_heartbeat_at=datetime.now(UTC),
    )
    service._executions.upsert(completed)

    with pytest.raises(OrchestrationError, match="not active"):
        service.cancel_background_execution(run.id, completed.id, actor="qa-owner")


def test_background_execution_cancel_wins_finalize_race(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Preserve cancellation over stale finalize status.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    now = datetime.now(UTC)
    execution = OrchestrationExecution(
        id="orchexec-cancel-finalize-race",
        run_id=run.id,
        status=OrchestrationExecutionStatus.cancelling,
        request=OrchestrationLoopRequest(max_iterations=1),
        supervisor_id=service.supervisor_id,
        status_reason="Cancellation requested.",
        started_at=now,
        last_heartbeat_at=now,
    )
    result = OrchestrationLoopResult(
        run=run,
        iterations=1,
        made_progress=True,
        stopped_reason="waiting_for_agents",
    )
    service._executions.upsert(execution)

    finalized = service._finalize_background_execution(
        execution.id,
        status=OrchestrationExecutionStatus.completed,
        status_reason="Attempted stale completion.",
        result=result,
        actor="qa-owner",
    )

    assert finalized is not None
    assert finalized.status == OrchestrationExecutionStatus.cancelled
    assert finalized.status_reason == "Orchestration background execution cancelled."
    assert finalized.result == result
    event = next(
        event
        for event in reversed(event_log.list(LogEventType.task))
        if event.subject_id == execution.id
    )
    assert event.message == "Cancelled orchestration background execution."


def test_background_execution_cancel_losing_finalize_race_reports_conflict(
    orchestration_state,
    monkeypatch,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Report terminal cancel race as conflict.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    def losing_cancel(_execution_id):  # noqa: ANN001
        return None, OrchestrationExecutionStatus.completed

    monkeypatch.setattr(service, "_request_background_execution_cancellation", losing_cancel)
    service._executions.upsert(
        OrchestrationExecution(
            id="orchexec-cancel-lost-race",
            run_id=run.id,
            status=OrchestrationExecutionStatus.running,
            request=OrchestrationLoopRequest(max_iterations=1),
            supervisor_id=service.supervisor_id,
            started_at=datetime.now(UTC),
            last_heartbeat_at=datetime.now(UTC),
        )
    )

    with pytest.raises(OrchestrationError, match="not active"):
        service.cancel_background_execution(run.id, "orchexec-cancel-lost-race", actor="qa-owner")


def test_background_execution_finalize_preserves_stale_or_foreign_records(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Avoid overwriting detached executions no longer owned by this supervisor.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    now = datetime.now(UTC)
    stale_execution = OrchestrationExecution(
        id="orchexec-stale-before-finalize",
        run_id=run.id,
        status=OrchestrationExecutionStatus.stale,
        request=OrchestrationLoopRequest(max_iterations=1),
        supervisor_id=service.supervisor_id,
        status_reason="Existing stale reason.",
        error="preserved stale error",
        started_at=now,
        completed_at=now,
        last_heartbeat_at=now,
    )
    foreign_execution = stale_execution.model_copy(
        update={
            "id": "orchexec-foreign-before-finalize",
            "status": OrchestrationExecutionStatus.running,
            "supervisor_id": "other-supervisor",
            "status_reason": "Existing foreign reason.",
            "error": "preserved foreign error",
            "completed_at": None,
        }
    )
    attempted_result = OrchestrationLoopResult(
        run=run,
        iterations=0,
        made_progress=False,
        stopped_reason="quiescent",
    )
    service._executions.upsert(stale_execution)
    service._executions.upsert(foreign_execution)

    stale_finalized = service._finalize_background_execution(
        stale_execution.id,
        status=OrchestrationExecutionStatus.completed,
        status_reason="Attempted stale overwrite.",
        result=attempted_result,
        actor="qa-owner",
    )
    foreign_finalized = service._finalize_background_execution(
        foreign_execution.id,
        status=OrchestrationExecutionStatus.completed,
        status_reason="Attempted foreign overwrite.",
        result=attempted_result,
        actor="qa-owner",
    )

    assert stale_finalized is None
    assert foreign_finalized is None
    persisted_stale = service.get_background_execution(run.id, stale_execution.id)
    persisted_foreign = service.get_background_execution(run.id, foreign_execution.id)
    assert persisted_stale.status == OrchestrationExecutionStatus.stale
    assert persisted_stale.status_reason == "Existing stale reason."
    assert persisted_stale.error == "preserved stale error"
    assert persisted_stale.result is None
    assert persisted_foreign.status == OrchestrationExecutionStatus.running
    assert persisted_foreign.status_reason == "Existing foreign reason."
    assert persisted_foreign.error == "preserved foreign error"
    assert persisted_foreign.result is None


def test_background_execution_launch_failure_finalizes_and_allows_retry(
    orchestration_state,
    monkeypatch,
) -> None:
    class RaisingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            raise RuntimeError("SECRET=thread-secret")

    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", RaisingThread)
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Finalize failed detached execution launch.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    with pytest.raises(OrchestrationError, match="SECRET=\\[REDACTED\\]"):
        service.start_background_execution(run.id, OrchestrationLoopRequest(max_iterations=1))

    failed = service.list_background_executions(run.id)[0]
    assert failed.status == OrchestrationExecutionStatus.failed
    assert failed.error == "RuntimeError: SECRET=[REDACTED]"
    assert "thread-secret" not in failed.model_dump_json()

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    retry = service.start_background_execution(run.id, OrchestrationLoopRequest(max_iterations=1))
    assert retry.status == OrchestrationExecutionStatus.starting


def test_background_execution_pre_run_failure_finalizes_record(
    orchestration_state,
    monkeypatch,
) -> None:
    class ImmediateThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            self.target(*self.args)

    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Finalize detached execution pre-run failure.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    def fail_mark_running(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("TOKEN=pre-run-secret")

    monkeypatch.setattr("dgentic.orchestration.Thread", ImmediateThread)
    monkeypatch.setattr(service, "_mark_background_execution_running", fail_mark_running)

    execution = service.start_background_execution(
        run.id,
        OrchestrationLoopRequest(max_iterations=1),
    )
    persisted = service.get_background_execution(run.id, execution.id)

    assert persisted.status == OrchestrationExecutionStatus.failed
    assert persisted.error == "RuntimeError: TOKEN=[REDACTED]"
    assert "pre-run-secret" not in persisted.model_dump_json()


def test_background_execution_failure_redacts_error(
    orchestration_state,
    monkeypatch,
) -> None:
    class ImmediateThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            self.target(*self.args)

    def fail_loop(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("SECRET=background-secret")

    monkeypatch.setattr("dgentic.orchestration.Thread", ImmediateThread)
    monkeypatch.setattr(OrchestrationService, "run_loop", fail_loop)
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Redact detached execution failures.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    execution = service.start_background_execution(
        run.id,
        OrchestrationLoopRequest(max_iterations=1),
    )
    persisted = service.get_background_execution(run.id, execution.id)

    assert persisted.status == OrchestrationExecutionStatus.failed
    assert persisted.error == "RuntimeError: SECRET=[REDACTED]"
    assert "background-secret" not in persisted.model_dump_json()


def test_orchestration_loop_honors_max_iterations_after_progress(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Bound autonomous loop iterations.",
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
    update_agent_status(dev_task.agent_id, AgentStatusUpdate(status=AgentStatus.completed))

    result = service.run_loop(run.id, OrchestrationLoopRequest(max_iterations=1))

    assert result.iterations == 1
    assert result.made_progress is True
    assert result.stopped_reason == "max_iterations"
    assert result.running_task_ids == ["qa-validation"]


def test_orchestration_loop_stops_on_unresolved_blocker(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Stop loop on blocker.",
            tasks=[
                _task("qa-validation", role="QA", paths=["tests/test_orchestration.py"]),
            ],
        )
    )
    task = _task_by_id(run, "qa-validation")
    assert task.agent_id
    update_agent_status(task.agent_id, AgentStatusUpdate(status=AgentStatus.failed))

    result = service.run_loop(run.id, OrchestrationLoopRequest(max_iterations=5))

    assert result.iterations == 1
    assert result.made_progress is True
    assert result.stopped_reason == "blocked"
    assert result.running_task_ids == []
    assert result.pending_task_ids == []
    assert len(result.unresolved_blocker_ids) == 1
    assert _task_by_id(result.run, "qa-validation").status == StepStatus.blocked


def test_orchestration_loop_stops_before_scheduling_when_blockers_already_exist(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Do not schedule while already blocked.",
            tasks=[
                _task("blocked-qa", role="QA", paths=["tests/test_orchestration.py"]),
                _task("ready-dev", role="Developer", paths=["src/dgentic/orchestration.py"]),
            ],
        )
    )
    blocked_task = _task_by_id(run, "blocked-qa")
    ready_task = _task_by_id(run, "ready-dev")
    assert blocked_task.agent_id
    assert ready_task.agent_id
    blocked = service.update_task(
        run.id,
        "blocked-qa",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Manual review needed."),
    )
    ready_pending = ready_task.model_copy(update={"status": StepStatus.pending, "agent_id": None})
    blocked = blocked.model_copy(
        update={
            "tasks": [ready_pending if task.id == "ready-dev" else task for task in blocked.tasks],
            "scheduled_task_ids": [],
        }
    )
    service._runs.upsert(blocked)

    result = service.run_loop(blocked.id, OrchestrationLoopRequest(max_iterations=5))

    assert result.iterations == 0
    assert result.made_progress is False
    assert result.stopped_reason == "blocked"
    assert result.pending_task_ids == ["ready-dev"]
    assert _task_by_id(result.run, "ready-dev").status == StepStatus.pending
    assert _task_by_id(result.run, "ready-dev").agent_id is None


def test_orchestration_loop_schedules_ready_pending_task(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Schedule pending recovered work.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Needs review."),
    )
    resolved = service.resolve_blocker(
        blocked.id,
        blocked.blockers[0].id,
        OrchestrationBlockerResolutionRequest(resolution="Reviewed without immediate schedule."),
    )

    result = service.run_loop(resolved.id, OrchestrationLoopRequest(max_iterations=5))

    assert result.iterations == 2
    assert result.made_progress is True
    assert result.stopped_reason == "waiting_for_agents"
    assert result.running_task_ids == ["qa-validation"]
    assert result.pending_task_ids == []
    assert _task_by_id(result.run, "qa-validation").status == StepStatus.running


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


def test_orchestration_create_run_syncs_generated_project_documents(
    orchestration_state,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Publish generated orchestration documents.",
            tasks=[
                _task(
                    "qa-document-check",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    title="Validate generated project documents",
                ),
            ],
        )
    )

    progress_document, backlog_document = _generated_orchestration_documents()
    assert "# DGentic Orchestration Run Status" in progress_document
    assert "# DGentic Orchestration Follow-Up Backlog" in backlog_document
    assert run.id in progress_document
    assert "Publish generated orchestration documents." in progress_document
    assert "`running` `qa-document-check` (QA): Validate generated project documents" in (
        progress_document
    )
    assert "- None." in backlog_document


def test_orchestration_generated_documents_list_active_follow_ups_and_blockers(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Track active blocker documents.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(
            status=StepStatus.blocked,
            error="Need PM review before continuing.",
        ),
    )

    progress_document, backlog_document = _generated_orchestration_documents()
    assert blocked.status == PlanStatus.running
    assert "`blocked` `qa-validation`" in progress_document
    assert "`blocked`" in progress_document
    assert "Need PM review before continuing." in progress_document
    assert f"`{blocked.id}` / `qa-validation` -> QA: Need PM review before continuing." in (
        backlog_document
    )
    assert f"`{blocked.id}` / `qa-validation` `blocked`: Need PM review before continuing." in (
        backlog_document
    )


def test_orchestration_generated_documents_drop_resolved_and_completed_open_items(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Clear resolved blocker documents.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
            required_dod_evidence=["tests"],
        )
    )
    blocked = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.blocked, error="Manual review needed."),
    )

    resolved = service.resolve_blocker(
        blocked.id,
        blocked.blockers[0].id,
        OrchestrationBlockerResolutionRequest(
            resolution="Manual review accepted.",
            reschedule=True,
        ),
    )
    progress_document, backlog_document = _generated_orchestration_documents()
    assert resolved.blockers[0].status == "resolved"
    assert resolved.follow_ups == []
    assert "Manual review needed." not in backlog_document
    assert "Manual review needed." not in progress_document
    assert progress_document.count("- None.") >= 1
    assert backlog_document.count("- None.") == 2

    completed = service.update_task(
        resolved.id,
        "qa-validation",
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )
    closed = service.close_run(
        completed.id,
        OrchestrationCloseRequest(evidence={"tests": "pytest passed"}),
    )

    _progress_document, backlog_document = _generated_orchestration_documents()
    assert closed.status == PlanStatus.completed
    assert closed.id not in backlog_document
    assert "Manual review needed." not in backlog_document
    assert backlog_document.count("- None.") == 2


def test_orchestration_generated_documents_redact_secret_shaped_text(
    orchestration_state,
) -> None:
    service = OrchestrationService()

    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Coordinate TOKEN=objective-secret document sync.",
            tasks=[
                _task(
                    "qa-redaction",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    title="Validate API_KEY=title-secret generated docs",
                ),
            ],
        )
    )
    service.update_task(
        run.id,
        "qa-redaction",
        OrchestrationTaskUpdate(
            status=StepStatus.blocked,
            error="Blocked by PASSWORD=blocker-secret and --token flag-secret.",
        ),
    )

    progress_document, backlog_document = _generated_orchestration_documents()
    documents = "\n".join([progress_document, backlog_document])
    assert "TOKEN=[REDACTED]" in documents
    assert "API_KEY=[REDACTED]" in documents
    assert "PASSWORD=[REDACTED]" in documents
    assert "--token [REDACTED]" in documents
    assert "objective-secret" not in documents
    assert "title-secret" not in documents
    assert "blocker-secret" not in documents
    assert "flag-secret" not in documents


@pytest.mark.parametrize("symlink_case", ["parent", "target"])
def test_orchestration_generated_document_symlink_failures_are_audited_and_non_fatal(
    orchestration_state,
    symlink_case: str,
) -> None:
    root_dir = get_settings().root_dir
    outside_dir = root_dir.parent / f"outside-{symlink_case}"
    outside_dir.mkdir()
    docs_dir = root_dir / "docs"
    progress_dir = docs_dir / "progress"
    outside_progress = outside_dir / "progress"

    docs_dir.mkdir()
    if symlink_case == "parent":
        outside_progress.mkdir()
        try:
            progress_dir.symlink_to(outside_progress, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"Symlink creation is unavailable on this platform: {exc}")
        outside_file = outside_progress / "orchestration-runs.md"
    else:
        progress_dir.mkdir()
        outside_file = outside_dir / "orchestration-runs.md"
        outside_file.write_text("outside sentinel", encoding="utf-8")
        try:
            (progress_dir / "orchestration-runs.md").symlink_to(outside_file)
        except OSError as exc:
            pytest.skip(f"Symlink creation is unavailable on this platform: {exc}")

    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective=f"Persist state despite {symlink_case} document sync failure.",
            tasks=[_task("qa-validation", role="QA", paths=["tests/test_orchestration.py"])],
        )
    )

    persisted = OrchestrationService().get_run(run.id)
    failure_event = _latest_task_event(
        run.id,
        "Failed to sync orchestration project documents.",
    )

    assert persisted is not None
    assert persisted.id == run.id
    assert failure_event.metadata["error_type"] == "ValueError"
    assert "must not contain symlinks" in failure_event.metadata["error"]
    if symlink_case == "parent":
        assert not outside_file.exists()
    else:
        assert outside_file.read_text(encoding="utf-8") == "outside sentinel"


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


def test_orchestration_task_update_records_redacted_audit_metadata(
    orchestration_state,
) -> None:
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Audit direct orchestration task updates.",
            tasks=[
                _task(
                    "qa-validation",
                    role="QA",
                    paths=["tests/test_orchestration.py"],
                    retry_limit=1,
                ),
                _task(
                    "pm-follow-up",
                    role="PM",
                    dependencies=["qa-validation"],
                    paths=["docs/progress/project-progress-log.md"],
                ),
            ],
        )
    )

    retried = service.update_task(
        run.id,
        "qa-validation",
        OrchestrationTaskUpdate(
            status=StepStatus.failed,
            error="First attempt failed with TOKEN=retry-secret.",
            output={"API_KEY=output-secret": "value"},
        ),
        actor="qa-reviewer",
    )
    retry_event = _latest_task_event(retried.id, "Updated orchestration task status.")

    assert retry_event.actor == "qa-reviewer"
    assert retry_event.metadata["task_id"] == "qa-validation"
    assert retry_event.metadata["previous_status"] == StepStatus.running
    assert retry_event.metadata["requested_status"] == StepStatus.failed
    assert retry_event.metadata["transition_status"] == StepStatus.pending
    assert retry_event.metadata["status"] == StepStatus.running
    assert retry_event.metadata["previous_retry_count"] == 0
    assert retry_event.metadata["retry_count"] == 1
    assert retry_event.metadata["new_blocker_ids"] == []
    assert retry_event.metadata["new_follow_up_ids"] == []
    assert retry_event.metadata["scheduled_task_ids"] == ["qa-validation"]
    assert retry_event.metadata["error"] == "First attempt failed with TOKEN=[REDACTED]"
    assert "retry-secret" not in retry_event.metadata["error"]
    assert retry_event.metadata["output_keys"] == ["API_KEY=[REDACTED]"]

    blocked = service.update_task(
        retried.id,
        "qa-validation",
        OrchestrationTaskUpdate(
            status=StepStatus.failed,
            error="Still failing with PASSWORD=blocker-secret.",
        ),
        actor="qa-reviewer",
    )
    blocked_event = _latest_task_event(blocked.id, "Updated orchestration task status.")

    assert blocked_event.actor == "qa-reviewer"
    assert blocked_event.metadata["previous_status"] == StepStatus.running
    assert blocked_event.metadata["requested_status"] == StepStatus.failed
    assert blocked_event.metadata["transition_status"] == StepStatus.blocked
    assert blocked_event.metadata["status"] == StepStatus.blocked
    assert blocked_event.metadata["previous_retry_count"] == 1
    assert blocked_event.metadata["retry_count"] == 2
    assert blocked_event.metadata["new_blocker_ids"] == [blocked.blockers[0].id]
    assert blocked_event.metadata["new_follow_up_ids"] == [blocked.follow_ups[0].id]
    assert blocked_event.metadata["scheduled_task_ids"] == []
    assert blocked_event.metadata["error"] == "Still failing with PASSWORD=[REDACTED]"
    assert "blocker-secret" not in blocked_event.metadata["error"]


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
    expected_output: str | None = None,
    title: str | None = None,
    validation: str | None = None,
    shared_memory_tags: list[str] | None = None,
) -> OrchestrationTaskSpec:
    return OrchestrationTaskSpec(
        id=task_id,
        title=title or f"{task_id} title",
        description=f"{task_id} description",
        role=role,
        dependencies=dependencies or [],
        declared_write_paths=paths or [],
        shared_memory_tags=shared_memory_tags or [],
        expected_output=expected_output if expected_output is not None else f"{task_id} output",
        validation=validation or f"{task_id} validation",
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


def _poll_execution(
    service: OrchestrationService,
    run_id: str,
    execution_id: str,
    *,
    attempts: int = 50,
) -> OrchestrationExecution:
    for _ in range(attempts):
        execution = service.get_background_execution(run_id, execution_id)
        if execution.status not in {
            OrchestrationExecutionStatus.starting,
            OrchestrationExecutionStatus.running,
        }:
            return execution
        time.sleep(0.01)
    pytest.fail(f"Background execution did not finish: {execution_id}")


def _status_by_id(run) -> dict[str, StepStatus]:
    return {task.id: task.status for task in run.tasks}


def _generated_orchestration_documents() -> tuple[str, str]:
    root_dir = get_settings().root_dir
    progress_path = root_dir / "docs" / "progress" / "orchestration-runs.md"
    backlog_path = root_dir / "docs" / "planning" / "orchestration-follow-ups.md"
    assert progress_path.is_file()
    assert backlog_path.is_file()
    return (
        progress_path.read_text(encoding="utf-8"),
        backlog_path.read_text(encoding="utf-8"),
    )


def _latest_task_event(run_id: str, message: str):
    return next(
        event
        for event in reversed(event_log.list(LogEventType.task))
        if event.subject_id == run_id and event.message == message
    )
