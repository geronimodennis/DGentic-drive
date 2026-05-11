import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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
