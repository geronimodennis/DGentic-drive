import importlib.util
import json
import signal
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import dgentic.tool_runtime as tool_runtime
from dgentic.database import get_db_session, reset_database_state
from dgentic.events import event_log
from dgentic.memory.schemas import ToolRegistryCreateRequest
from dgentic.redaction import REDACTED_SECRET_MARKER
from dgentic.schemas import (
    LogEventType,
    PermissionMode,
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
