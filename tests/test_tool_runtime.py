import importlib.util
import json
import signal
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import dgentic.tool_runtime as tool_runtime
from dgentic.database import get_db_session, reset_database_state
from dgentic.events import event_log
from dgentic.memory.schemas import ToolRegistryCreateRequest
from dgentic.orchestration import OrchestrationService
from dgentic.redaction import REDACTED_SECRET_MARKER
from dgentic.schemas import (
    LogEventType,
    OrchestrationCreateRequest,
    OrchestrationTaskSpec,
    OrchestrationTaskUpdate,
    PermissionMode,
    StepStatus,
    ToolExecutionRequest,
    ToolManifest,
    ToolStatus,
)
from dgentic.settings import get_settings
from dgentic.tool_runtime import (
    TIMEOUT_EXIT_CODE,
    ToolApprovalStatus,
    approve_tool_approval,
    create_tool_approval,
    deny_tool_approval,
    execute_tool,
    get_tool_approval_review,
    list_tool_approvals,
)
from dgentic.tools import get_tool, register_tool
from dgentic.tools.registry_service import ToolRegistryService


@pytest.fixture()
def local_tool_state(tmp_path, monkeypatch) -> tuple[Path, Path]:
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    (root_dir / "localmcp").mkdir(parents=True)
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    reset_database_state()
    yield root_dir, data_dir
    reset_database_state()
    get_settings.cache_clear()


def test_execute_tool_prefers_wrapper_and_tracks_success(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "adder",
        tool_source=(
            "def run(payload):\n"
            "    return {'total': payload['a'] + payload['b'], 'source': 'tool'}\n"
        ),
        wrapper_source=(
            "from tool import run\n\n"
            "def invoke(payload):\n"
            "    print('wrapper-log')\n"
            "    result = run(payload)\n"
            "    result['source'] = 'wrapper'\n"
            "    return result\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="adder",
            description="Add two numbers.",
            entrypoint="localmcp/adder/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("adder", {"a": 2, "b": 3})
    stored = get_tool("adder")

    assert result.exit_code == 0
    assert result.cwd == tool_dir.resolve()
    assert result.entrypoint == (tool_dir / "wrapper.py").resolve()
    assert result.parsed_output == {"total": 5, "source": "wrapper"}
    assert "wrapper-log" in result.stderr
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.success_count == 1
    assert stored.failure_count == 0
    assert stored.reliability_score == 1.0
    assert stored.last_used_at is not None
    assert (data_dir / "tools.json").exists()


def test_approval_required_tool_must_be_approved(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(root_dir, "reviewer", tool_source="def run(payload):\n    return {'ok': True}\n")
    register_tool(
        ToolManifest(
            name="reviewer",
            description="Requires a human approval gate.",
            entrypoint="tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )

    with pytest.raises(PermissionError, match="approved approval_id"):
        execute_tool("reviewer", {"approved": False})

    denied_manifest = get_tool("reviewer")
    result = execute_tool("reviewer", {"approved": True}, approved=True)
    approved_manifest = get_tool("reviewer")

    assert denied_manifest is not None
    assert denied_manifest.usage_count == 0
    assert result.exit_code == 0
    assert approved_manifest is not None
    assert approved_manifest.usage_count == 1
    assert approved_manifest.success_count == 1


def test_execute_tool_keeps_legacy_agent_context_without_orchestration_match(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "legacy-context-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="legacy-context-tool",
            description="Legacy context should remain audit-compatible.",
            entrypoint="localmcp/legacy-context-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool(
        "legacy-context-tool",
        {},
        agent_id="legacy-agent",
        agent_role="Developer",
        task_id="legacy-task",
    )
    latest_event = event_log.list(LogEventType.tool)[-1]

    assert result.exit_code == 0
    assert result.orchestration is not None
    assert result.orchestration.allowed is True
    assert (
        result.orchestration.reason == "No active orchestration task matched supplied tool context."
    )
    assert latest_event.metadata["orchestration"] == result.orchestration.model_dump(mode="json")


def test_execute_tool_fails_closed_for_partial_active_orchestration_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "active-bound-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="active-bound-tool",
            description="Active context must be complete.",
            entrypoint="localmcp/active-bound-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    run = _create_running_orchestration_task_for_tool_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        execute_tool("active-bound-tool", {}, agent_id=task.agent_id)

    stored = get_tool("active-bound-tool")
    assert stored is not None
    assert stored.usage_count == 0


def test_execute_tool_fails_closed_for_role_only_active_orchestration_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "role-only-active-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="role-only-active-tool",
            description="Role-only active context must be complete.",
            entrypoint="localmcp/role-only-active-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _create_running_orchestration_task_for_tool_runtime()

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        execute_tool("role-only-active-tool", {}, agent_role="QA")

    stored = get_tool("role-only-active-tool")
    assert stored is not None
    assert stored.usage_count == 0


def test_execute_tool_fails_closed_for_completed_orchestration_task_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "completed-context-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="completed-context-tool",
            description="Completed task context cannot run tools.",
            entrypoint="localmcp/completed-context-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    service = OrchestrationService()
    run = _create_running_orchestration_task_for_tool_runtime(service)
    task = next(task for task in run.tasks if task.id == "qa-validation")
    service.update_task(
        run.id,
        task.id,
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    with pytest.raises(PermissionError, match="not running"):
        execute_tool(
            "completed-context-tool",
            {},
            agent_id=task.agent_id,
            agent_role=task.role,
            task_id=task.id,
        )

    stored = get_tool("completed-context-tool")
    assert stored is not None
    assert stored.usage_count == 0


def test_execute_tool_fails_closed_for_pending_orchestration_task_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "pending-context-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="pending-context-tool",
            description="Pending task context cannot run tools.",
            entrypoint="localmcp/pending-context-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _create_pending_orchestration_task_for_tool_runtime()

    with pytest.raises(PermissionError, match="not running"):
        execute_tool(
            "pending-context-tool",
            {},
            agent_role="QA",
            task_id="qa-validation",
        )

    stored = get_tool("pending-context-tool")
    assert stored is not None
    assert stored.usage_count == 0


def test_execute_tool_redacts_orchestration_denial_reason(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "redacted-denial-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="redacted-denial-tool",
            description="Redact orchestration denial context.",
            entrypoint="localmcp/redacted-denial-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    run = _create_running_orchestration_task_for_tool_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    with pytest.raises(PermissionError) as exc:
        execute_tool(
            "redacted-denial-tool",
            {},
            agent_id=task.agent_id,
            agent_role="Developer SECRET=role-leak",
            task_id=task.id,
        )

    assert "role-leak" not in str(exc.value)
    assert "SECRET=[REDACTED]" in str(exc.value)


def test_create_tool_approval_fails_closed_for_partial_active_orchestration_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "active-approval-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="active-approval-tool",
            description="Active approval context must be complete.",
            entrypoint="localmcp/active-approval-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )
    run = _create_running_orchestration_task_for_tool_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        create_tool_approval(
            "active-approval-tool",
            ToolExecutionRequest(payload={}, task_id=task.id),
        )

    assert list_tool_approvals() == []


def test_approved_tool_execution_rechecks_active_orchestration_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "approval-recheck-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="approval-recheck-tool",
            description="Approved execution must recheck active context.",
            entrypoint="localmcp/approval-recheck-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )
    approval = create_tool_approval(
        "approval-recheck-tool",
        ToolExecutionRequest(payload={}, task_id="qa-validation"),
    )
    approve_tool_approval(approval.id, decided_by="reviewer")

    _create_running_orchestration_task_for_tool_runtime()

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        execute_tool(
            "approval-recheck-tool",
            {},
            approval_id=approval.id,
            task_id="qa-validation",
        )

    assert list_tool_approvals()[0].status == ToolApprovalStatus.approved
    stored = get_tool("approval-recheck-tool")
    assert stored is not None
    assert stored.usage_count == 0


def test_approved_tool_execution_blocks_completed_orchestration_context_before_claim(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "approved-completed-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="approved-completed-tool",
            description="Approved execution must require a running task.",
            entrypoint="localmcp/approved-completed-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )
    service = OrchestrationService()
    run = _create_running_orchestration_task_for_tool_runtime(service)
    task = next(task for task in run.tasks if task.id == "qa-validation")
    approval = create_tool_approval(
        "approved-completed-tool",
        ToolExecutionRequest(
            payload={},
            timeout_seconds=5,
            agent_id=task.agent_id,
            agent_role=task.role,
            task_id=task.id,
        ),
    )
    approve_tool_approval(approval.id, decided_by="reviewer")
    service.update_task(
        run.id,
        task.id,
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    with pytest.raises(PermissionError, match="not running"):
        execute_tool(
            "approved-completed-tool",
            {},
            approval_id=approval.id,
            timeout_seconds=5,
            agent_id=task.agent_id,
            agent_role=task.role,
            task_id=task.id,
        )

    assert list_tool_approvals()[0].status == ToolApprovalStatus.approved
    stored = get_tool("approved-completed-tool")
    assert stored is not None
    assert stored.usage_count == 0


def test_tool_approval_and_execution_serialize_matching_orchestration_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "serialized-context-tool",
        tool_source="def run(payload):\n    return {'ok': True, 'value': payload.get('value')}\n",
    )
    register_tool(
        ToolManifest(
            name="serialized-context-tool",
            description="Serialize matching orchestration context.",
            entrypoint="localmcp/serialized-context-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )
    run = _create_running_orchestration_task_for_tool_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    approval = create_tool_approval(
        "serialized-context-tool",
        ToolExecutionRequest(
            payload={"value": "ok"},
            timeout_seconds=5,
            agent_id=task.agent_id,
            agent_role=task.role,
            task_id=task.id,
        ),
    )
    review = get_tool_approval_review(approval.id)
    approval_event = event_log.list(LogEventType.approval)[-1]
    approve_tool_approval(approval.id, decided_by="reviewer")
    result = execute_tool(
        "serialized-context-tool",
        {"value": "ok"},
        approval_id=approval.id,
        timeout_seconds=5,
        agent_id=task.agent_id,
        agent_role=task.role,
        task_id=task.id,
    )
    latest_event = event_log.list(LogEventType.tool)[-1]

    expected_orchestration = {
        "allowed": True,
        "reason": "Tool action is bound to a running orchestration task.",
        "run_id": run.id,
        "task_id": task.id,
        "agent_id": task.agent_id,
        "agent_role": task.role,
        "violating_paths": [],
    }
    assert approval.orchestration is not None
    assert approval.orchestration.model_dump(mode="json") == expected_orchestration
    assert approval_event.metadata["orchestration"] == expected_orchestration
    assert review.orchestration is not None
    assert review.orchestration.model_dump(mode="json") == expected_orchestration
    assert result.exit_code == 0
    assert result.orchestration is not None
    assert result.orchestration.model_dump(mode="json") == expected_orchestration
    assert latest_event.metadata["orchestration"] == expected_orchestration


def test_tool_approval_event_redacts_legacy_orchestration_context(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "redacted-approval-context-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="redacted-approval-context-tool",
            description="Redact legacy orchestration context metadata.",
            entrypoint="localmcp/redacted-approval-context-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )

    approval = create_tool_approval(
        "redacted-approval-context-tool",
        ToolExecutionRequest(
            payload={},
            agent_id="agent PASSWORD=agent-leak",
            agent_role="Developer SECRET=role-leak",
            task_id="task API_KEY=task-leak",
        ),
    )
    latest_event = event_log.list(LogEventType.approval)[-1]
    serialized_event = json.dumps(latest_event.metadata, sort_keys=True)

    assert approval.orchestration is not None
    assert approval.orchestration.allowed is True
    assert "agent-leak" not in serialized_event
    assert "role-leak" not in serialized_event
    assert "task-leak" not in serialized_event
    assert "PASSWORD=[REDACTED]" in serialized_event
    assert "SECRET=[REDACTED]" in serialized_event
    assert "API_KEY=[REDACTED]" in serialized_event


def test_production_approval_required_tool_requires_bound_approval(
    local_tool_state: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir, data_dir = local_tool_state
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "reviewer-bound",
        tool_source=("def run(payload):\n    return {'ok': True, 'value': payload.get('value')}\n"),
    )
    register_tool(
        ToolManifest(
            name="reviewer-bound",
            description="Requires a bound tool approval.",
            entrypoint="localmcp/reviewer-bound/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )

    with pytest.raises(PermissionError, match="approved approval_id"):
        execute_tool("reviewer-bound", {"value": "safe"}, approved=True)

    approval = create_tool_approval(
        "reviewer-bound",
        ToolExecutionRequest(
            payload={"value": "TOKEN=payload-secret"},
            timeout_seconds=5,
            requested_by="operator TOKEN=requester-secret",
            agent_id="agent PASSWORD=agent-secret",
            agent_role="developer SECRET=role-secret",
            task_id="sprint-11 API_KEY=task-secret",
        ),
    )
    assert approval.status == ToolApprovalStatus.pending
    assert approval.review_payload["value"] == "TOKEN=[REDACTED]"
    assert approval.requested_by == "operator TOKEN=[REDACTED]"
    assert approval.agent_id == "agent PASSWORD=[REDACTED]"
    assert approval.agent_role == "developer SECRET=[REDACTED]"
    assert approval.task_id == "sprint-11 API_KEY=[REDACTED]"
    approval_storage = (data_dir / "tool-approvals.json").read_text(encoding="utf-8")
    assert "payload-secret" not in approval_storage
    assert "requester-secret" not in approval_storage
    assert "agent-secret" not in approval_storage
    assert "role-secret" not in approval_storage
    assert "task-secret" not in approval_storage

    approved = approve_tool_approval(
        approval.id,
        decided_by="reviewer TOKEN=reviewer-secret",
        reason="Approved after checking --token reason-secret.",
    )
    review = get_tool_approval_review(approval.id)
    assert approved.status == ToolApprovalStatus.approved
    assert approved.decided_by == "reviewer TOKEN=[REDACTED]"
    assert "--token [REDACTED]" in approved.decision_reason
    assert review.review_payload["value"] == "TOKEN=[REDACTED]"
    assert review.direct_execute_available is False
    approval_storage = (data_dir / "tool-approvals.json").read_text(encoding="utf-8")
    assert "reviewer-secret" not in approval_storage

    with pytest.raises(PermissionError, match="not bound"):
        execute_tool(
            "reviewer-bound",
            {"value": "different"},
            approval_id=approval.id,
            timeout_seconds=5,
            requested_by="operator TOKEN=requester-secret",
            agent_id="agent PASSWORD=agent-secret",
            agent_role="developer SECRET=role-secret",
            task_id="sprint-11 API_KEY=task-secret",
        )

    result = execute_tool(
        "reviewer-bound",
        {"value": "TOKEN=payload-secret"},
        approval_id=approval.id,
        timeout_seconds=5,
        requested_by="operator TOKEN=requester-secret",
        agent_id="agent PASSWORD=agent-secret",
        agent_role="developer SECRET=role-secret",
        task_id="sprint-11 API_KEY=task-secret",
    )

    executed = list_tool_approvals()[0]
    assert result.exit_code == 0
    assert result.approval_id == approval.id
    assert result.parsed_output["value"] == "TOKEN=[REDACTED]"
    assert executed.status == ToolApprovalStatus.executed

    with pytest.raises(PermissionError, match="not executable"):
        execute_tool(
            "reviewer-bound",
            {"value": "TOKEN=payload-secret"},
            approval_id=approval.id,
            timeout_seconds=5,
            requested_by="operator TOKEN=requester-secret",
            agent_id="agent PASSWORD=agent-secret",
            agent_role="developer SECRET=role-secret",
            task_id="sprint-11 API_KEY=task-secret",
        )


def test_bound_tool_approval_rejects_artifact_drift(
    local_tool_state: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    get_settings.cache_clear()
    tool_dir = _write_tool(
        root_dir,
        "artifact-bound-tool",
        tool_source=(
            "from helper import approved_value\n\n"
            "def run(payload):\n"
            "    return {'value': approved_value()}\n"
        ),
    )
    (tool_dir / "helper.py").write_text(
        "def approved_value():\n    return 'approved'\n",
        encoding="utf-8",
    )
    register_tool(
        ToolManifest(
            name="artifact-bound-tool",
            description="Approval should bind to generated tool artifacts.",
            entrypoint="localmcp/artifact-bound-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )
    approval = create_tool_approval(
        "artifact-bound-tool",
        ToolExecutionRequest(payload={}, timeout_seconds=5),
    )
    approve_tool_approval(approval.id, decided_by="reviewer")
    (tool_dir / "helper.py").write_text(
        "def approved_value():\n    return 'changed'\n",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="not bound"):
        execute_tool(
            "artifact-bound-tool",
            {},
            approval_id=approval.id,
            timeout_seconds=5,
        )


def test_bound_tool_approval_rejects_denied_and_expired_records(
    local_tool_state: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir, data_dir = local_tool_state
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "approval-lifecycle-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="approval-lifecycle-tool",
            description="Exercises non-executable approval states.",
            entrypoint="localmcp/approval-lifecycle-tool/tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )

    denied = create_tool_approval(
        "approval-lifecycle-tool",
        ToolExecutionRequest(payload={"case": "denied"}, timeout_seconds=5),
    )
    deny_tool_approval(denied.id, decided_by="reviewer", reason="Denied after review.")

    with pytest.raises(PermissionError, match="not executable"):
        execute_tool(
            "approval-lifecycle-tool",
            {"case": "denied"},
            approval_id=denied.id,
            timeout_seconds=5,
        )

    expired = create_tool_approval(
        "approval-lifecycle-tool",
        ToolExecutionRequest(payload={"case": "expired"}, timeout_seconds=5),
    )
    approve_tool_approval(expired.id, decided_by="reviewer")
    approval_path = data_dir / "tool-approvals.json"
    approvals = json.loads(approval_path.read_text(encoding="utf-8"))
    for approval in approvals:
        if approval["id"] == expired.id:
            approval["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    approval_path.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(PermissionError, match="expired"):
        execute_tool(
            "approval-lifecycle-tool",
            {"case": "expired"},
            approval_id=expired.id,
            timeout_seconds=5,
        )


@pytest.mark.parametrize(
    ("permission_mode", "status"),
    [
        (PermissionMode.blocked, ToolStatus.active),
        (PermissionMode.autopilot_safe, ToolStatus.disabled),
        (PermissionMode.autopilot_safe, ToolStatus.deprecated),
    ],
)
def test_blocked_disabled_and_deprecated_tools_do_not_run(
    local_tool_state: tuple[Path, Path],
    permission_mode: PermissionMode,
    status: ToolStatus,
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        f"guarded-{status.value}-{permission_mode.value}",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    name = tool_dir.name
    register_tool(
        ToolManifest(
            name=name,
            description="Should not execute.",
            entrypoint=f"localmcp/{name}/tool.py",
            permission_mode=permission_mode,
            status=status,
            deprecated_reason="Replaced." if status == ToolStatus.deprecated else None,
        )
    )

    with pytest.raises(PermissionError):
        execute_tool(name, {})

    stored = get_tool(name)
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def test_failed_tool_execution_tracks_failure_and_captured_output(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    raw_secrets = [
        "failure-printed-token-secret",
        "failure-json-token-secret",
        "failure-json-password-secret",
        "failure-auth-header-secret",
        "failure-exception-secret",
    ]
    _write_tool(
        root_dir,
        "broken",
        tool_source=(
            "import sys\n\n"
            "def run(payload):\n"
            "    print('TOKEN=failure-printed-token-secret')\n"
            "    sys.stderr.write("
            '\'{"token":"failure-json-token-secret",'
            '"nested":{"password":"failure-json-password-secret"}}\\n\')\n'
            "    sys.stderr.write('Authorization: Bearer failure-auth-header-secret\\n')\n"
            "    raise RuntimeError('SECRET=failure-exception-secret')\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="broken",
            description="Raises an error.",
            entrypoint="localmcp/broken/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    events_before = event_log.list(LogEventType.tool)

    result = execute_tool("broken", {"value": 1})
    stored = get_tool("broken")
    events_after = event_log.list(LogEventType.tool)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "TOKEN=[REDACTED]" in result.stderr
    assert "Authorization: Bearer [REDACTED]" in result.stderr
    assert "RuntimeError: SECRET=[REDACTED]" in result.stderr
    assert result.stderr.count(REDACTED_SECRET_MARKER) >= 5
    serialized_result = result.model_dump_json()
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_result
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.success_count == 0
    assert stored.failure_count == 1
    assert stored.reliability_score == 0.0
    new_events = events_after[len(events_before) :]
    execution_events = [event for event in new_events if event.subject_id == "broken"]
    assert execution_events
    assert execution_events[-1].metadata["exit_code"] == 1
    serialized_event = json.dumps(execution_events[-1].model_dump(mode="json"), sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_event


def test_reliability_policy_warns_without_disabling_low_score_tool(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "flaky-warning",
        tool_source=(
            "def run(payload):\n"
            "    if payload.get('fail'):\n"
            "        raise RuntimeError('expected failure')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="flaky-warning",
            description="Warns after low reliability but remains active.",
            entrypoint="localmcp/flaky-warning/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    events_before = event_log.list(LogEventType.tool)

    for should_fail in [False, False, False, True, True]:
        execute_tool("flaky-warning", {"fail": should_fail})

    stored = get_tool("flaky-warning")
    events_after = event_log.list(LogEventType.tool)
    policy_events = [
        event
        for event in events_after[len(events_before) :]
        if event.message == "Applied generated tool reliability policy."
    ]
    assert stored is not None
    assert stored.status == ToolStatus.active
    assert stored.usage_count == 5
    assert stored.success_count == 3
    assert stored.failure_count == 2
    assert stored.reliability_score == pytest.approx(0.6)
    assert policy_events[-1].metadata["policy"] == "warn"


def test_reliability_policy_deprecates_consistently_weak_tool(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "mostly-failing",
        tool_source=(
            "def run(payload):\n"
            "    if payload.get('fail'):\n"
            "        raise RuntimeError('expected failure')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="mostly-failing",
            description="Should be deprecated after enough weak results.",
            entrypoint="localmcp/mostly-failing/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
            usage_count=9,
            failure_count=9,
            reliability_score=0.0,
        )
    )

    execute_tool("mostly-failing", {"fail": True})

    stored = get_tool("mostly-failing")
    assert stored is not None
    assert stored.status == ToolStatus.deprecated
    assert stored.usage_count == 10
    assert stored.failure_count == 10
    assert stored.reliability_score == 0.0
    assert stored.deprecated_reason == "Auto-deprecated: reliability score 0.00 after 10 runs."

    with pytest.raises(PermissionError, match="deprecated"):
        execute_tool("mostly-failing", {"fail": False})


def test_reliability_policy_disables_repeatedly_failing_tool(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "always-failing",
        tool_source="def run(payload):\n    raise RuntimeError('expected failure')\n",
    )
    register_tool(
        ToolManifest(
            name="always-failing",
            description="Should be disabled after repeated failures.",
            entrypoint="localmcp/always-failing/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    for _ in range(5):
        execute_tool("always-failing", {})

    stored = get_tool("always-failing")
    assert stored is not None
    assert stored.status == ToolStatus.disabled
    assert stored.usage_count == 5
    assert stored.success_count == 0
    assert stored.failure_count == 5
    assert stored.reliability_score == 0.0
    assert stored.deprecated_reason == "Auto-disabled: reliability score 0.00 after 5 runs."

    with pytest.raises(PermissionError, match="disabled"):
        execute_tool("always-failing", {})


def test_execute_tool_syncs_sql_registry_usage_and_deprecation(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "sql-reliability-tool",
        tool_source=(
            "def run(payload):\n"
            "    if payload.get('fail'):\n"
            "        raise RuntimeError('expected failure')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="sql-reliability-tool",
            description="Syncs runtime usage into the SQL registry.",
            entrypoint="localmcp/sql-reliability-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _register_sql_registry_tool(
        "sql-reliability-tool",
        permission_level="autopilot_safe",
    )

    execute_tool("sql-reliability-tool", {"fail": False})

    sql_tool = _get_sql_registry_tool("sql-reliability-tool")
    assert sql_tool is not None
    assert sql_tool.usage_count == 1
    assert sql_tool.success_count == 1
    assert sql_tool.failure_count == 0
    assert sql_tool.reliability_score == 1.0
    assert sql_tool.deprecated is False

    stored_before_deprecation = get_tool("sql-reliability-tool")
    assert stored_before_deprecation is not None
    register_tool(
        stored_before_deprecation.model_copy(
            update={
                "usage_count": 9,
                "success_count": 0,
                "failure_count": 9,
                "reliability_score": 0.0,
            }
        )
    )

    execute_tool("sql-reliability-tool", {"fail": True})

    stored = get_tool("sql-reliability-tool")
    deprecated_sql_tool = _get_sql_registry_tool("sql-reliability-tool")
    assert stored is not None
    assert stored.status == ToolStatus.deprecated
    assert deprecated_sql_tool is not None
    assert deprecated_sql_tool.usage_count == 2
    assert deprecated_sql_tool.success_count == 1
    assert deprecated_sql_tool.failure_count == 1
    assert deprecated_sql_tool.deprecated is True


def test_execute_tool_redacts_secret_outputs_and_records_audit_event(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    raw_secrets = [
        "printed-token-secret",
        "stderr-password-secret",
        "json-stderr-token-secret",
        "json-stderr-password-secret",
        "colon-api-secret",
        "auth-header-secret",
        "basic-auth-header-secret",
        "token-auth-header-secret",
        "proxy-auth-header-secret",
        "returned-token-secret",
        "returned-secret",
        "returned-api-secret",
        "returned-password-secret",
    ]
    _write_tool(
        root_dir,
        "redacting-tool",
        tool_source=(
            "import sys\n\n"
            "def run(payload):\n"
            "    print('TOKEN=printed-token-secret')\n"
            "    sys.stderr.write('PASSWORD=stderr-password-secret\\n')\n"
            '    sys.stderr.write(\'{"token":"json-stderr-token-secret",'
            '"nested":{"password":"json-stderr-password-secret"}}\\n\')\n'
            "    sys.stderr.write('api_key: colon-api-secret\\n')\n"
            "    sys.stderr.write('Authorization: Bearer auth-header-secret\\n')\n"
            "    sys.stderr.write('Authorization: Basic basic-auth-header-secret\\n')\n"
            "    sys.stderr.write('authorization: token token-auth-header-secret\\n')\n"
            "    sys.stderr.write('Proxy-Authorization: ApiKey proxy-auth-header-secret\\n')\n"
            "    return {\n"
            "        'token': 'returned-token-secret',\n"
            "        'payload': 'SECRET=returned-secret --api-key returned-api-secret',\n"
            "        'nested': {'password': 'returned-password-secret'},\n"
            "        'safe': 'visible',\n"
            "    }\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="redacting-tool",
            description="Emits and returns secret-shaped values.",
            entrypoint="localmcp/redacting-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    events_before = event_log.list(LogEventType.tool)

    result = execute_tool("redacting-tool", {})
    events_after = event_log.list(LogEventType.tool)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["token"] == REDACTED_SECRET_MARKER
    assert "TOKEN=[REDACTED]" in result.stderr
    assert "Authorization: Bearer [REDACTED]" in result.stderr
    assert "Authorization: Basic [REDACTED]" in result.stderr
    assert "authorization: token [REDACTED]" in result.stderr
    assert "Proxy-Authorization: ApiKey [REDACTED]" in result.stderr
    assert result.stderr.count(REDACTED_SECRET_MARKER) >= 9
    assert result.parsed_output["token"] == REDACTED_SECRET_MARKER
    assert result.parsed_output["nested"]["password"] == REDACTED_SECRET_MARKER
    assert result.parsed_output["safe"] == "visible"
    assert REDACTED_SECRET_MARKER in result.parsed_output["payload"]
    serialized_result = result.model_dump_json()
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_result

    new_events = events_after[len(events_before) :]
    execution_events = [event for event in new_events if event.subject_id == "redacting-tool"]
    assert execution_events
    execution_event = execution_events[-1]
    assert execution_event.event_type == LogEventType.tool
    assert execution_event.metadata["exit_code"] == 0
    serialized_event = json.dumps(execution_event.model_dump(mode="json"), sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_event


def test_timed_out_tool_redacts_partial_output_and_records_audit_event(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    raw_secrets = [
        "timeout-json-token-secret",
        "timeout-json-password-secret",
        "timeout-auth-header-secret",
    ]
    _write_tool(
        root_dir,
        "slow-redacting-tool",
        tool_source=(
            "import sys\n"
            "import time\n\n"
            "def run(payload):\n"
            '    sys.stderr.write(\'{"token":"timeout-json-token-secret",'
            '"nested":{"password":"timeout-json-password-secret"}}\\n\')\n'
            "    sys.stderr.write('Authorization: Bearer timeout-auth-header-secret\\n')\n"
            "    sys.stderr.flush()\n"
            "    time.sleep(5)\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="slow-redacting-tool",
            description="Times out after emitting secret-shaped logs.",
            entrypoint="localmcp/slow-redacting-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    events_before = event_log.list(LogEventType.tool)

    result = execute_tool("slow-redacting-tool", {}, timeout_seconds=1)
    events_after = event_log.list(LogEventType.tool)

    assert result.exit_code == TIMEOUT_EXIT_CODE
    assert result.parsed_output is None
    assert "Authorization: Bearer [REDACTED]" in result.stderr
    assert "Tool timed out after 1 seconds." in result.stderr
    serialized_result = result.model_dump_json()
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_result

    new_events = events_after[len(events_before) :]
    execution_events = [event for event in new_events if event.subject_id == "slow-redacting-tool"]
    assert execution_events
    assert execution_events[-1].metadata["exit_code"] == TIMEOUT_EXIT_CODE
    serialized_event = json.dumps(execution_events[-1].model_dump(mode="json"), sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_event


def test_execute_tool_cannot_import_application_runtime_dependency(
    local_tool_state: tuple[Path, Path],
) -> None:
    assert importlib.util.find_spec("fastapi") is not None
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "app-dependency-leak",
        tool_source=(
            "import fastapi\n\n"
            "def run(payload):\n"
            "    return {'fastapi_version': fastapi.__version__}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="app-dependency-leak",
            description="Should not inherit app runtime dependencies.",
            entrypoint="localmcp/app-dependency-leak/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("app-dependency-leak", {})
    stored = get_tool("app-dependency-leak")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "No module named 'fastapi'" in result.stderr
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.success_count == 0
    assert stored.failure_count == 1


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("deny", "blocked by DGentic network policy"),
        ("approval_required", "requires DGentic network approval"),
    ],
)
def test_execute_tool_enforces_network_domain_policy_in_subprocess(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
    mode: str,
    message: str,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": mode,
                        "reason": "policy token=network-policy-secret",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        f"network-{mode}-tool",
        tool_source=(
            "import socket\n\n"
            "def run(payload):\n"
            "    socket.create_connection(('blocked.example.test', 443), timeout=1)\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name=f"network-{mode}-tool",
            description="Network policy should stop outbound sockets.",
            entrypoint=f"localmcp/network-{mode}-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool(f"network-{mode}-tool", {})
    stored = get_tool(f"network-{mode}-tool")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert message in result.stderr
    assert "network-policy-secret" not in result.model_dump_json()
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.success_count == 0
    assert stored.failure_count == 1


def test_execute_tool_enforces_network_domain_policy_for_raw_socket_connect(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": "deny",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "raw-socket-network-deny-tool",
        tool_source=(
            "import socket\n\n"
            "def run(payload):\n"
            "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    try:\n"
            "        sock.connect(('blocked.example.test', 443))\n"
            "    finally:\n"
            "        sock.close()\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="raw-socket-network-deny-tool",
            description="Network policy should stop raw socket connect.",
            entrypoint="localmcp/raw-socket-network-deny-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("raw-socket-network-deny-tool", {})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "blocked by DGentic network policy" in result.stderr


def test_execute_tool_enforces_network_domain_policy_before_tool_import(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": "deny",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "import-time-network-deny-tool",
        tool_source=(
            "import socket\n\n"
            "socket.create_connection(('blocked.example.test', 443), timeout=1)\n\n"
            "def run(payload):\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="import-time-network-deny-tool",
            description="Network policy should stop import-time sockets.",
            entrypoint="localmcp/import-time-network-deny-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("import-time-network-deny-tool", {})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "blocked by DGentic network policy" in result.stderr


def test_execute_tool_enforces_network_domain_policy_for_connect_ex(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": "deny",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "connect-ex-network-deny-tool",
        tool_source=(
            "import socket\n\n"
            "def run(payload):\n"
            "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    try:\n"
            "        return {'code': sock.connect_ex(('blocked.example.test', 443))}\n"
            "    finally:\n"
            "        sock.close()\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="connect-ex-network-deny-tool",
            description="Network policy should stop connect_ex sockets.",
            entrypoint="localmcp/connect-ex-network-deny-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("connect-ex-network-deny-tool", {})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "blocked by DGentic network policy" in result.stderr


@pytest.mark.parametrize(
    ("name", "tool_source"),
    [
        (
            "byte-host-connect-network-deny-tool",
            "import socket\n\n"
            "def run(payload):\n"
            "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    try:\n"
            "        sock.connect((b'127.0.0.1', 443))\n"
            "    finally:\n"
            "        sock.close()\n"
            "    return {'ok': True}\n",
        ),
        (
            "byte-host-connect-ex-network-deny-tool",
            "import socket\n\n"
            "def run(payload):\n"
            "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    try:\n"
            "        return {'code': sock.connect_ex((b'127.0.0.1', 443))}\n"
            "    finally:\n"
            "        sock.close()\n",
        ),
        (
            "byte-host-getaddrinfo-network-deny-tool",
            "import socket\n\n"
            "def run(payload):\n"
            "    return {'addresses': socket.getaddrinfo(b'127.0.0.1', 443)}\n",
        ),
    ],
)
def test_execute_tool_normalizes_byte_hosts_for_network_policy(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
    name: str,
    tool_source: str,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "127.0.0.1",
                        "mode": "deny",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(root_dir, name, tool_source=tool_source)
    register_tool(
        ToolManifest(
            name=name,
            description="Network policy should stop byte-string socket hosts.",
            entrypoint=f"localmcp/{name}/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool(name, {})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "blocked by DGentic network policy" in result.stderr


def test_execute_tool_blocks_denied_hostname_resolution_before_ip_connect(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "default_mode": "allow",
                "rules": [
                    {
                        "domain": "localhost",
                        "mode": "deny",
                    }
                ],
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "resolver-network-deny-tool",
        tool_source=(
            "import socket\n\n"
            "ip_address = socket.gethostbyname('localhost')\n\n"
            "def run(payload):\n"
            "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    try:\n"
            "        return {'code': sock.connect_ex((ip_address, 9))}\n"
            "    finally:\n"
            "        sock.close()\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="resolver-network-deny-tool",
            description="Network policy should stop denied hostname resolution.",
            entrypoint="localmcp/resolver-network-deny-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("resolver-network-deny-tool", {})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "blocked by DGentic network policy" in result.stderr


def test_execute_tool_allows_resolved_address_for_allowed_hostname(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    _host, port = listener.getsockname()
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "default_mode": "deny",
                "rules": [
                    {
                        "domain": "localhost",
                        "mode": "allow",
                    }
                ],
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "resolver-network-allow-tool",
        tool_source=(
            "import socket\n\n"
            "def run(payload):\n"
            "    ip_address = socket.gethostbyname('localhost')\n"
            f"    with socket.create_connection((ip_address, {port}), timeout=2):\n"
            "        return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="resolver-network-allow-tool",
            description="Network policy should allow resolved approved host addresses.",
            entrypoint="localmcp/resolver-network-allow-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    try:
        result = execute_tool("resolver-network-allow-tool", {})
    finally:
        listener.close()

    assert result.exit_code == 0
    assert result.parsed_output == {"ok": True}


def test_execute_tool_network_policy_survives_main_original_restore_attempt(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": "deny",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "main-restore-network-deny-tool",
        tool_source=(
            "import __main__\n"
            "import socket\n\n"
            "def run(payload):\n"
            "    original_connect = getattr(__main__, '_ORIGINAL_SOCKET_CONNECT', None)\n"
            "    original_create = getattr(__main__, '_ORIGINAL_CREATE_CONNECTION', None)\n"
            "    if original_connect is not None:\n"
            "        socket.socket.connect = original_connect\n"
            "    if original_create is not None:\n"
            "        socket.create_connection = original_create\n"
            "    socket.create_connection(('blocked.example.test', 443), timeout=1)\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="main-restore-network-deny-tool",
            description="Network policy should survive trivial restore attempts.",
            entrypoint="localmcp/main-restore-network-deny-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("main-restore-network-deny-tool", {})

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "blocked by DGentic network policy" in result.stderr


@pytest.mark.parametrize("mode", ["allow", "audit"])
def test_execute_tool_preserves_network_policy_allow_and_audit_modes(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
    mode: str,
) -> None:
    root_dir, _data_dir = local_tool_state
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "default_mode": "deny",
                "rules": [
                    {
                        "domain": host,
                        "mode": mode,
                    }
                ],
            }
        ),
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        f"network-{mode}-tool",
        tool_source=(
            "import socket\n\n"
            "def run(payload):\n"
            f"    with socket.create_connection(({host!r}, {port}), timeout=2):\n"
            "        return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name=f"network-{mode}-tool",
            description=f"Network policy {mode} mode should permit sockets.",
            entrypoint=f"localmcp/network-{mode}-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    try:
        result = execute_tool(f"network-{mode}-tool", {})
    finally:
        listener.close()

    assert result.exit_code == 0
    assert result.parsed_output == {"ok": True}


def test_execute_tool_does_not_expose_network_policy_handoff_to_tool(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "allowed.example.test",
                        "mode": "allow",
                        "reason": "policy token=network-policy-secret",
                    }
                ]
            }
        ),
    )
    monkeypatch.setenv(
        "DGENTIC_TOOL_NETWORK_DOMAIN_POLICY",
        '{"default_mode":"deny","reason":"hostile inherited policy secret"}',
    )
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "network-policy-env-tool",
        tool_source=(
            "import os\n\n"
            "def run(payload):\n"
            "    return {'tool_policy': os.environ.get('DGENTIC_TOOL_NETWORK_DOMAIN_POLICY')}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="network-policy-env-tool",
            description="Tool should not see runner network policy handoff.",
            entrypoint="localmcp/network-policy-env-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("network-policy-env-tool", {})

    assert result.exit_code == 0
    assert result.parsed_output == {"tool_policy": None}
    serialized = result.model_dump_json()
    assert "network-policy-secret" not in serialized
    assert "hostile inherited policy secret" not in serialized


def test_execute_tool_rejects_invalid_network_policy_before_subprocess_usage(
    local_tool_state: tuple[Path, Path],
    monkeypatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    monkeypatch.setenv("DGENTIC_NETWORK_DOMAIN_POLICY", '{"rules":"not-a-list"}')
    get_settings.cache_clear()
    _write_tool(
        root_dir,
        "invalid-network-policy-tool",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="invalid-network-policy-tool",
            description="Invalid policy should block before execution.",
            entrypoint="localmcp/invalid-network-policy-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    with pytest.raises(PermissionError, match="Network domain policy is invalid"):
        execute_tool("invalid-network-policy-tool", {})

    stored = get_tool("invalid-network-policy-tool")
    assert stored is not None
    assert stored.usage_count == 0


@pytest.mark.parametrize(
    ("name", "dependency_dir", "manifest_dependency_paths"),
    [
        ("manifest-local-dependency", "deps", ["deps"]),
        ("standard-vendor-dependency", "vendor", []),
    ],
)
def test_execute_tool_imports_local_dependency_path(
    local_tool_state: tuple[Path, Path],
    name: str,
    dependency_dir: str,
    manifest_dependency_paths: list[str],
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        name,
        tool_source=(
            "from local_tool_dependency import value\n\n"
            "def run(payload):\n"
            "    return {'value': value(), 'payload': payload['value']}\n"
        ),
    )
    package_dir = tool_dir / dependency_dir / "local_tool_dependency"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text(
        "def value():\n    return 'loaded from local dependency'\n",
        encoding="utf-8",
    )
    register_tool(
        ToolManifest(
            name=name,
            description="Imports a dependency from the tool's local dependency path.",
            entrypoint=f"localmcp/{name}/tool.py",
            dependency_paths=manifest_dependency_paths,
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool(name, {"value": "payload visible"})

    assert result.exit_code == 0
    assert result.parsed_output == {
        "value": "loaded from local dependency",
        "payload": "payload visible",
    }
    assert (tool_dir / dependency_dir).resolve() in result.dependency_paths


def test_execute_tool_blocks_dependency_path_symlink_escape_before_usage(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "dependency-symlink-escape",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    external_dependency_dir = root_dir / "external-dependency"
    external_dependency_dir.mkdir()
    (tool_dir / "vendor-link").symlink_to(external_dependency_dir, target_is_directory=True)
    register_tool(
        ToolManifest(
            name="dependency-symlink-escape",
            description="Has a dependency path symlink that escapes the tool directory.",
            entrypoint="localmcp/dependency-symlink-escape/tool.py",
            dependency_paths=["vendor-link"],
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    with pytest.raises(PermissionError, match="symlinks"):
        execute_tool("dependency-symlink-escape", {})

    stored = get_tool("dependency-symlink-escape")
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def test_execute_tool_blocks_missing_explicit_dependency_path_before_usage(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "missing-dependency-path",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="missing-dependency-path",
            description="Declares a missing local dependency directory.",
            entrypoint="localmcp/missing-dependency-path/tool.py",
            dependency_paths=["deps"],
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    with pytest.raises(FileNotFoundError, match="dependency path"):
        execute_tool("missing-dependency-path", {})

    stored = get_tool("missing-dependency-path")
    assert stored is not None
    assert stored.usage_count == 0


def test_tool_subprocess_does_not_inherit_host_python_environment(
    local_tool_state: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    host_python_vars = {
        "PYTHONPATH": "C:\\fake-host-pythonpath",
        "VIRTUAL_ENV": "C:\\fake-host-venv",
        "PYTHONHOME": "C:\\fake-host-pythonhome",
        "CONDA_PREFIX": "C:\\fake-host-conda",
        "LD_LIBRARY_PATH": "/fake-host-ld",
        "DYLD_LIBRARY_PATH": "/fake-host-dyld",
    }
    for key, value in host_python_vars.items():
        monkeypatch.setenv(key, value)
    _write_tool(
        root_dir,
        "subprocess-env-isolation",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="subprocess-env-isolation",
            description="Verifies isolated subprocess launch configuration.",
            entrypoint="localmcp/subprocess-env-isolation/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    call: dict[str, object] = {}

    class FakeProcess:
        pid = 4242
        returncode = 0

        def communicate(self, input, timeout):
            call["input"] = input
            call["timeout"] = timeout
            return '{"ok": true}\n', ""

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    def fake_popen(args, **kwargs):
        call["args"] = args
        call["env"] = kwargs["env"]
        call["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(tool_runtime.subprocess, "Popen", fake_popen)

    result = execute_tool("subprocess-env-isolation", {})

    assert result.exit_code == 0
    assert result.parsed_output == {"ok": True}
    args = call["args"]
    env = call["env"]
    assert isinstance(args, list)
    assert "-I" in args
    assert "-S" in args
    assert "-X" in args
    assert "utf8" in args
    assert isinstance(env, dict)
    assert call["input"] == "{}"
    assert call["timeout"] == 30
    for key, value in host_python_vars.items():
        assert key not in env
        assert value not in env.values()
    assert env["DGENTIC_TOOL_DEPENDENCY_MODE"] == "local-only"
    kwargs = call["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["cwd"] == (root_dir / "localmcp" / "subprocess-env-isolation").resolve()
    assert kwargs["stdin"] == subprocess.PIPE
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.PIPE
    if tool_runtime.os.name == "nt" and hasattr(
        tool_runtime.subprocess, "CREATE_NEW_PROCESS_GROUP"
    ):
        assert kwargs["creationflags"] == tool_runtime.subprocess.CREATE_NEW_PROCESS_GROUP
    elif tool_runtime.os.name != "nt":
        assert kwargs["start_new_session"] is True


def test_timed_out_tool_terminates_process_tree(
    local_tool_state: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "timeout-process-tree",
        tool_source="def run(payload):\n    return {'ok': True}\n",
    )
    register_tool(
        ToolManifest(
            name="timeout-process-tree",
            description="Verifies timeout cleanup is invoked.",
            entrypoint="localmcp/timeout-process-tree/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    terminated: list[object] = []

    class TimeoutProcess:
        pid = 4242
        returncode = None

        def communicate(self, input=None, timeout=None):
            raise subprocess.TimeoutExpired(
                cmd="timeout-process-tree",
                timeout=timeout,
                output="partial stdout",
                stderr="partial stderr",
            )

        def poll(self):
            return None

    process = TimeoutProcess()

    def fake_popen(args, **kwargs):
        return process

    monkeypatch.setattr(tool_runtime.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        tool_runtime,
        "_terminate_tool_process_tree",
        lambda process: terminated.append(process),
    )

    result = execute_tool("timeout-process-tree", {}, timeout_seconds=1)
    stored = get_tool("timeout-process-tree")

    assert result.exit_code == TIMEOUT_EXIT_CODE
    assert result.stdout == "partial stdout"
    assert "partial stderr" in result.stderr
    assert "Tool timed out after 1 seconds." in result.stderr
    assert terminated == [process]
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.failure_count == 1


def test_terminate_tool_process_tree_uses_host_tree_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 4242

        def __init__(self) -> None:
            self.poll_calls = 0
            self.terminated = False
            self.killed = False
            self.waits: list[int | None] = []

        def poll(self):
            self.poll_calls += 1
            if tool_runtime.os.name == "nt":
                return None if self.poll_calls == 1 else 0
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            self.waits.append(timeout)
            if tool_runtime.os.name != "nt" and len(self.waits) == 1:
                raise subprocess.TimeoutExpired(cmd="tool", timeout=timeout)
            return 0

    process = FakeProcess()
    if tool_runtime.os.name == "nt":
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(tool_runtime.subprocess, "run", fake_run)

        tool_runtime._terminate_tool_process_tree(process)

        assert process.terminated is True
        assert calls == [["taskkill", "/PID", "4242", "/T", "/F"]]
        assert process.killed is False
    else:
        signals: list[tuple[int, signal.Signals]] = []
        monkeypatch.setattr(
            tool_runtime.os,
            "killpg",
            lambda pgid, sig: signals.append((pgid, sig)),
        )

        tool_runtime._terminate_tool_process_tree(process)

        assert signals == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]
        assert process.waits == [1, 5]
        assert process.terminated is False
        assert process.killed is False


def test_windows_taskkill_failure_falls_back_to_process_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if tool_runtime.os.name != "nt":
        pytest.skip("Windows taskkill fallback is only used on Windows.")

    class FakeProcess:
        pid = 4242

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])

    process = FakeProcess()
    monkeypatch.setattr(tool_runtime.subprocess, "run", fake_run)

    tool_runtime._terminate_tool_process_tree(process)

    assert process.terminated is True
    assert process.killed is True


def test_manifest_entrypoint_must_stay_under_named_localmcp_tool_dir(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(root_dir, "safe-name", tool_source="def run(payload):\n    return {'ok': True}\n")
    register_tool(
        ToolManifest(
            name="safe-name",
            description="Has an unsafe manifest entrypoint.",
            entrypoint="localmcp/other-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    with pytest.raises(PermissionError, match=r"rootDir/localmcp/\[tool_name\]"):
        execute_tool("safe-name", {})

    stored = get_tool("safe-name")
    assert stored is not None
    assert stored.usage_count == 0


def test_sql_registry_deprecated_tool_does_not_run(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "sql-deprecated",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="sql-deprecated",
            description="Local manifest is active, but SQL registry is deprecated.",
            entrypoint="localmcp/sql-deprecated/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _register_sql_registry_tool(
        "sql-deprecated",
        permission_level="autopilot_safe",
        deprecated=True,
    )

    with pytest.raises(PermissionError):
        execute_tool("sql-deprecated", {})

    stored = get_tool("sql-deprecated")
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def test_sql_registry_permission_conflict_fails_closed(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "sql-permission-conflict",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="sql-permission-conflict",
            description="SQL registry permission conflicts with local manifest.",
            entrypoint="localmcp/sql-permission-conflict/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _register_sql_registry_tool(
        "sql-permission-conflict",
        permission_level="approval_required",
    )

    with pytest.raises(PermissionError):
        execute_tool("sql-permission-conflict", {})

    stored = get_tool("sql-permission-conflict")
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def _register_sql_registry_tool(
    name: str,
    *,
    permission_level: str,
    deprecated: bool = False,
) -> None:
    session = get_db_session()
    try:
        service = ToolRegistryService(session)
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name=name,
                version="1.0.0",
                source_path=f"localmcp/{name}/tool.py",
                interface_signature=f"sha256:{name}",
                permission_level=permission_level,
            )
        )
        if deprecated:
            service.deprecate_tool(tool.id)
    finally:
        session.close()


def _get_sql_registry_tool(name: str):
    session = get_db_session()
    try:
        service = ToolRegistryService(session)
        tool = service.get_tool_by_name(name)
        if tool is not None:
            session.expunge(tool)
        return tool
    finally:
        session.close()


def _write_tool(
    root_dir: Path,
    name: str,
    *,
    tool_source: str,
    wrapper_source: str | None = None,
) -> Path:
    tool_dir = root_dir / "localmcp" / name
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(tool_source, encoding="utf-8")
    if wrapper_source is not None:
        (tool_dir / "wrapper.py").write_text(wrapper_source, encoding="utf-8")
    return tool_dir


def _create_running_orchestration_task_for_tool_runtime(
    service: OrchestrationService | None = None,
):
    service = service or OrchestrationService()
    return service.create_run(
        OrchestrationCreateRequest(
            objective="Bind generated tool runtime to a running QA task.",
            tasks=[
                OrchestrationTaskSpec(
                    id="qa-validation",
                    title="QA validation",
                    description="Validate orchestration-bound tool runtime behavior.",
                    role="QA",
                    declared_write_paths=["tests/test_tool_runtime.py"],
                    expected_output="Focused tool runtime regressions.",
                    validation="pytest tests/test_tool_runtime.py passes.",
                )
            ],
        )
    )


def _create_pending_orchestration_task_for_tool_runtime():
    return OrchestrationService().create_run(
        OrchestrationCreateRequest(
            objective="Keep QA pending behind developer implementation.",
            tasks=[
                OrchestrationTaskSpec(
                    id="dev-implementation",
                    title="Developer implementation",
                    description="Implement source changes.",
                    role="Developer",
                    declared_write_paths=["src/dgentic/tool_runtime.py"],
                    expected_output="Source changes.",
                    validation="Developer smoke passes.",
                ),
                OrchestrationTaskSpec(
                    id="qa-validation",
                    title="QA validation",
                    description="Validate generated-tool runtime behavior.",
                    role="QA",
                    dependencies=["dev-implementation"],
                    declared_write_paths=["tests/test_tool_runtime.py"],
                    expected_output="Focused tool runtime regressions.",
                    validation="pytest tests/test_tool_runtime.py passes.",
                ),
            ],
        )
    )
