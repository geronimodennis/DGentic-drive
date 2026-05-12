import hashlib
import io
import json
import signal
import subprocess
import time
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest

from dgentic.cli_runtime import (
    DEFAULT_MAX_OUTPUT_CHUNKS,
    REDACTED_LEGACY_DIGEST_MARKER,
    CliRuntimeService,
    CommandApproval,
    CommandApprovalStatus,
    CommandOutputChunk,
    CommandRun,
    CommandRunStatus,
    OrphanTerminationStatus,
    ProcessSnapshot,
    _command_args,
    command_approval_digest,
    command_environment_digest,
    sanitize_output,
)
from dgentic.command_policy import create_command_policy_rule
from dgentic.orchestration import OrchestrationService
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandPolicyMatchType,
    CommandPolicyRuleRequest,
    OrchestrationCreateRequest,
    OrchestrationTaskSpec,
    OrchestrationTaskUpdate,
    PermissionMode,
    StepStatus,
)
from dgentic.settings import get_settings


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    get_settings.cache_clear()

    yield CliRuntimeService(max_output_chars=48), root_dir, data_dir

    get_settings.cache_clear()


def test_create_approval_persists_pending_approval(runtime) -> None:
    service, root_dir, data_dir = runtime

    approval = service.create_approval(
        CommandExecutionRequest(command="python --version", timeout_seconds=5),
        requested_by="operator",
    )

    assert approval.status == CommandApprovalStatus.pending
    assert approval.permission_mode == PermissionMode.approval_required
    assert approval.cwd == root_dir.resolve()
    assert approval.requested_by == "operator"
    assert service.list_approvals(CommandApprovalStatus.pending)[0].id == approval.id
    assert (data_dir / "cli-approvals.json").exists()


def test_create_approval_includes_safe_policy_review_metadata(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Review Python version checks",
            match_type=CommandPolicyMatchType.executable,
            pattern="python",
            permission_mode=PermissionMode.approval_required,
            reason="Python execution requires reviewer approval.",
            agent_roles=["developer"],
            priority=5,
        )
    )

    approval = service.create_approval(
        CommandExecutionRequest(
            command="python --version",
            agent_role="developer",
            agent_id="agent-dev-1",
            task_id="sprint-9",
        ),
        requested_by="operator",
    )

    assert approval.policy_reason == "Python execution requires reviewer approval."
    assert approval.matched_rule_id == rule.id
    assert approval.matched_rule_name == "Review Python version checks"
    assert approval.agent_role == "developer"
    assert approval.agent_id == "agent-dev-1"
    assert approval.task_id == "sprint-9"


def test_cli_runtime_executes_legacy_agent_context_without_orchestration_match(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    result = service.execute_command(
        CommandExecutionRequest(
            command="cmd /c echo legacy-ok",
            agent_role="Developer",
            agent_id="legacy-agent",
            task_id="legacy-task",
        )
    )

    assert result.exit_code == 0
    assert "legacy-ok" in result.stdout
    assert result.permission_mode == PermissionMode.autopilot_safe


def test_cli_runtime_fails_closed_for_partial_active_orchestration_context(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    run = _create_running_orchestration_task_for_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        service.execute_command(
            CommandExecutionRequest(
                command="cmd /c echo should-not-run",
                agent_id=task.agent_id,
            )
        )


def test_cli_runtime_start_run_fails_closed_for_partial_active_orchestration_context(
    runtime,
) -> None:
    service, _root_dir, _data_dir = runtime
    run = _create_running_orchestration_task_for_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        service.start_command(
            CommandExecutionRequest(
                command="cmd /c echo should-not-start",
                task_id=task.id,
            )
        )

    assert service.list_command_runs() == []


def test_cli_runtime_create_approval_fails_closed_for_partial_active_orchestration_context(
    runtime,
) -> None:
    service, _root_dir, _data_dir = runtime
    run = _create_running_orchestration_task_for_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        service.create_approval(
            CommandExecutionRequest(
                command="python --version",
                agent_id=task.agent_id,
            )
        )

    assert service.list_approvals() == []


def test_cli_runtime_execute_approved_command_rechecks_active_orchestration_context(
    runtime,
) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(
        CommandExecutionRequest(
            command="python --version",
            task_id="qa-validation",
        )
    )
    service.approve_approval(approval.id, decided_by="reviewer")

    _create_running_orchestration_task_for_runtime()

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        service.execute_approved_command(approval.id)

    assert service.list_command_runs() == []
    assert service.list_approvals()[0].status == CommandApprovalStatus.approved


def test_cli_runtime_allows_matching_orchestration_context_under_normal_policy(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    run = _create_running_orchestration_task_for_runtime()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    result = service.execute_command(
        CommandExecutionRequest(
            command="cmd /c echo bound-ok",
            agent_role=task.role,
            agent_id=task.agent_id,
            task_id=task.id,
        )
    )

    assert result.exit_code == 0
    assert "bound-ok" in result.stdout
    assert result.permission_mode == PermissionMode.autopilot_safe


def test_cli_runtime_blocks_known_non_running_orchestration_context(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    orchestration = OrchestrationService()
    run = _create_running_orchestration_task_for_runtime(orchestration)
    task = next(task for task in run.tasks if task.id == "qa-validation")
    orchestration.update_task(
        run.id,
        task.id,
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    with pytest.raises(PermissionError, match="not running"):
        service.execute_command(
            CommandExecutionRequest(
                command="cmd /c echo stale-context",
                agent_role=task.role,
                agent_id=task.agent_id,
                task_id=task.id,
            )
        )

    assert service.list_command_runs() == []


def test_cli_runtime_blocks_executable_path_escape_before_launch(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    with pytest.raises(PermissionError, match="executable path resolves outside"):
        service.execute_command(CommandExecutionRequest(command="../outside-tool --version"))

    assert service.list_command_runs() == []


def test_create_approval_evaluates_policy_with_request_cwd(runtime) -> None:
    service, root_dir, _data_dir = runtime
    subdir = root_dir / "subdir"
    subdir.mkdir()
    readme = root_dir / "README.md"
    readme.write_text("inside root", encoding="utf-8")
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Review read-only cwd reads",
            match_type=CommandPolicyMatchType.executable,
            pattern="cat",
            permission_mode=PermissionMode.approval_required,
            reason="Review cwd-relative read command.",
            priority=5,
        )
    )

    approval = service.create_approval(
        CommandExecutionRequest(command="cat ../README.md", cwd=subdir),
        requested_by="operator",
    )

    assert approval.cwd == subdir.resolve()
    assert approval.policy_reason == "Review cwd-relative read command."
    assert approval.matched_rule_id == rule.id


def test_create_approval_includes_redacted_review_contract_metadata(runtime) -> None:
    service, _root_dir, data_dir = runtime
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Review Python secret command",
            match_type=CommandPolicyMatchType.executable,
            pattern="python",
            permission_mode=PermissionMode.approval_required,
            reason="Python commands require approval review.",
            priority=5,
        )
    )
    command = (
        'python -c "print(\'TOKEN="abc 123"\')" --token cli-secret --api-key="key with spaces"'
        " --github_token gh-secret --client_secret client-secret /password:win-secret "
        'PASSWORD="abc \\" tail secret" --secret "flag \\" tail secret" '
        r"--access-key escaped\ value API_KEY=escaped\ assignment "
        "--token=$(printf SUPER_SECRET; echo ok) SECRET=$(printf ASSIGNMENT_SECRET; echo ok) "
        "API_TOKEN=ps` assignment --refresh-token ps` value"
    )

    approval = service.create_approval(
        CommandExecutionRequest(
            command=command,
            timeout_seconds=11,
            requested_by="operator",
            agent_id="agent-dev-1",
            agent_role="developer",
            task_id="BL-003a",
            environment={"DGENTIC_TEST_FLAG": "should-not-persist"},
        )
    )

    assert approval.command == approval.review_command
    assert approval.review_command.startswith('python -c "print(')
    assert "abc 123" not in approval.command
    assert "cli-secret" not in approval.command
    assert "key with spaces" not in approval.command
    assert "gh-secret" not in approval.command
    assert "client-secret" not in approval.command
    assert "win-secret" not in approval.command
    assert "tail secret" not in approval.command
    assert "escaped\\ value" not in approval.command
    assert "escaped\\ assignment" not in approval.command
    assert "SUPER_SECRET" not in approval.command
    assert "ASSIGNMENT_SECRET" not in approval.command
    assert "ps` assignment" not in approval.command
    assert "ps` value" not in approval.command
    assert "echo ok)" not in approval.command
    assert "TOKEN=[REDACTED]" in approval.review_command
    assert "--token [REDACTED]" in approval.review_command
    assert "--api-key=[REDACTED]" in approval.review_command
    assert "--github_token [REDACTED]" in approval.review_command
    assert "--client_secret [REDACTED]" in approval.review_command
    assert "/password:[REDACTED]" in approval.review_command
    assert "PASSWORD=[REDACTED]" in approval.review_command
    assert "--secret [REDACTED]" in approval.review_command
    assert "--access-key [REDACTED]" in approval.review_command
    assert "API_KEY=[REDACTED]" in approval.review_command
    assert "--token=[REDACTED]" in approval.review_command
    assert "SECRET=[REDACTED]" in approval.review_command
    assert "API_TOKEN=[REDACTED]" in approval.review_command
    assert "--refresh-token [REDACTED]" in approval.review_command
    assert approval.environment_keys == ["DGENTIC_TEST_FLAG"]
    assert approval.matched_rule_id == rule.id
    assert approval.matched_rule_name == "Review Python secret command"
    assert approval.permission_mode == PermissionMode.approval_required
    assert approval.policy_reason == "Python commands require approval review."
    assert approval.command_digest.startswith("hmac-sha256:")
    assert approval.environment_digest.startswith("hmac-sha256:")
    assert len(approval.command_digest.removeprefix("hmac-sha256:")) == 64
    assert len(approval.environment_digest.removeprefix("hmac-sha256:")) == 64
    assert approval.expires_at > approval.created_at

    approval_storage = (data_dir / "cli-approvals.json").read_text(encoding="utf-8")
    assert "command" in approval_storage
    assert "review_command" in approval_storage
    assert "TOKEN=[REDACTED]" in approval_storage
    assert "abc 123" not in approval_storage
    assert "cli-secret" not in approval_storage
    assert "key with spaces" not in approval_storage
    assert "gh-secret" not in approval_storage
    assert "client-secret" not in approval_storage
    assert "win-secret" not in approval_storage
    assert "tail secret" not in approval_storage
    assert "escaped\\ value" not in approval_storage
    assert "escaped\\ assignment" not in approval_storage
    assert "SUPER_SECRET" not in approval_storage
    assert "ASSIGNMENT_SECRET" not in approval_storage
    assert "ps` assignment" not in approval_storage
    assert "ps` value" not in approval_storage
    assert "echo ok)" not in approval_storage
    assert "DGENTIC_TEST_FLAG" in approval_storage
    assert "environment_digest" in approval_storage
    assert "should-not-persist" not in approval_storage


def test_approval_review_contract_is_safe_for_ui_consumers(runtime) -> None:
    service, root_dir, _data_dir = runtime
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Review Python secret command",
            match_type=CommandPolicyMatchType.executable,
            pattern="python",
            permission_mode=PermissionMode.approval_required,
            reason="Python commands require approval review.",
            priority=5,
        )
    )
    approval = service.create_approval(
        CommandExecutionRequest(
            command="python deploy.py --token super-secret",
            environment={"DGENTIC_TEST_FLAG": "should-not-persist"},
            timeout_seconds=12,
            requested_by="operator",
            agent_role="developer",
            agent_id="agent-dev-1",
            task_id="BL-003b",
        )
    )

    review = service.get_approval_review(approval.id)

    assert review.id == approval.id
    assert review.status == CommandApprovalStatus.pending
    assert review.review_command == "python deploy.py --token [REDACTED]"
    assert review.cwd == root_dir.resolve()
    assert review.timeout_seconds == 12
    assert review.permission_mode == PermissionMode.approval_required
    assert review.policy_reason == "Python commands require approval review."
    assert review.requested_by == "operator"
    assert review.agent_role == "developer"
    assert review.agent_id == "agent-dev-1"
    assert review.task_id == "BL-003b"
    assert review.environment_keys == ["DGENTIC_TEST_FLAG"]
    assert review.command_digest.startswith("hmac-sha256:")
    assert review.environment_digest.startswith("hmac-sha256:")
    assert review.requires_bound_execution_request is True
    assert review.direct_execute_available is False
    assert any("redacted" in warning for warning in review.review_warnings)
    assert any("environment keys" in warning for warning in review.review_warnings)
    assert not any(
        "legacy or invalid binding digests" in warning for warning in review.review_warnings
    )
    assert "super-secret" not in review.model_dump_json()
    assert "should-not-persist" not in review.model_dump_json()


def test_approval_review_contract_marks_direct_execution_availability(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(CommandExecutionRequest(command="python --version"))
    review_before = service.get_approval_review(approval.id)

    service.approve_approval(
        approval.id,
        decided_by="reviewer",
        reason="Version check is acceptable.",
    )
    review_after = service.get_approval_review(approval.id)

    assert review_before.direct_execute_available is False
    assert review_after.status == CommandApprovalStatus.approved
    assert review_after.direct_execute_available is True
    assert review_after.requires_bound_execution_request is False
    assert review_after.decided_by == "reviewer"
    assert review_after.decision_reason == "Version check is acceptable."
    assert review_after.denial_reason is None


def test_approval_review_contract_blocks_direct_execution_for_legacy_digests(
    runtime,
) -> None:
    service, _root_dir, data_dir = runtime
    approval = service.create_approval(CommandExecutionRequest(command="python --version"))
    service.approve_approval(approval.id, decided_by="reviewer")
    storage_path = data_dir / "cli-approvals.json"
    raw_items = json.loads(storage_path.read_text(encoding="utf-8"))
    raw_items[0]["command_digest"] = "legacy-sha256:command"
    raw_items[0]["environment_digest"] = "legacy-sha256:environment"
    storage_path.write_text(json.dumps(raw_items, indent=2) + "\n", encoding="utf-8")

    review = service.get_approval_review(approval.id)

    assert review.status == CommandApprovalStatus.approved
    assert review.direct_execute_available is False
    assert any("legacy or invalid binding digests" in warning for warning in review.review_warnings)
    with pytest.raises(PermissionError, match="legacy or invalid binding digests"):
        service.execute_approved_command(approval.id)


def test_approval_decision_reasons_are_redacted_before_persistence(runtime) -> None:
    service, _root_dir, data_dir = runtime
    approved = service.create_approval(CommandExecutionRequest(command="python --version"))
    denied = service.create_approval(CommandExecutionRequest(command="python -V"))

    service.approve_approval(
        approved.id,
        decided_by="reviewer",
        reason="Approved with --token super-secret for local version check.",
    )
    service.deny_approval(
        denied.id,
        decided_by="reviewer",
        reason="Denied because PASSWORD=super-secret was pasted.",
    )

    approved_review = service.get_approval_review(approved.id)
    denied_review = service.get_approval_review(denied.id)
    approval_storage = (data_dir / "cli-approvals.json").read_text(encoding="utf-8")

    assert approved_review.decision_reason == (
        "Approved with --token [REDACTED] for local version check."
    )
    assert denied_review.decision_reason is not None
    assert "PASSWORD=[REDACTED]" in denied_review.decision_reason
    assert denied_review.denial_reason is not None
    assert "PASSWORD=[REDACTED]" in denied_review.denial_reason
    assert "super-secret" not in approved_review.model_dump_json()
    assert "super-secret" not in denied_review.model_dump_json()
    assert "super-secret" not in approval_storage


def test_legacy_persisted_approval_reasons_are_redacted_for_consumers(runtime) -> None:
    service, _root_dir, data_dir = runtime
    approval = service.create_approval(CommandExecutionRequest(command="python --version"))
    service.deny_approval(approval.id, decided_by="reviewer", reason="Not needed.")
    storage_path = data_dir / "cli-approvals.json"
    raw_items = json.loads(storage_path.read_text(encoding="utf-8"))
    raw_items[0]["decision_reason"] = "Approved with --token super-secret."
    raw_items[0]["denial_reason"] = "Denied because PASSWORD=super-secret was pasted."
    storage_path.write_text(json.dumps(raw_items, indent=2) + "\n", encoding="utf-8")

    listed = next(item for item in service.list_approvals() if item.id == approval.id)
    review = service.get_approval_review(approval.id)

    assert listed.decision_reason is not None
    assert "--token [REDACTED]" in listed.decision_reason
    assert listed.denial_reason is not None
    assert "PASSWORD=[REDACTED]" in listed.denial_reason
    assert review.decision_reason is not None
    assert "--token [REDACTED]" in review.decision_reason
    assert review.denial_reason is not None
    assert "PASSWORD=[REDACTED]" in review.denial_reason
    assert "super-secret" not in listed.model_dump_json()
    assert "super-secret" not in review.model_dump_json()


def test_approval_binding_digests_are_keyed(runtime) -> None:
    _service, root_dir, data_dir = runtime
    overrides = {"TOKEN": "short-secret"}

    environment_digest = command_environment_digest(overrides)
    raw_environment_payload = json.dumps(overrides, sort_keys=True, separators=(",", ":"))
    raw_environment_digest = hashlib.sha256(raw_environment_payload.encode("utf-8")).hexdigest()
    command_digest = command_approval_digest(
        command="python deploy.py --token short-secret",
        cwd=root_dir.resolve(),
        timeout_seconds=30,
        requested_by="operator",
        agent_id="agent-dev-1",
        agent_role="developer",
        task_id="BL-003a",
        environment_keys=["TOKEN"],
        environment_digest=environment_digest,
        permission_mode=PermissionMode.approval_required,
        matched_rule_id=None,
        matched_rule_name=None,
    )
    raw_command_payload = {
        "agent_id": "agent-dev-1",
        "agent_role": "developer",
        "command": "python deploy.py --token short-secret",
        "cwd": str(root_dir.resolve()),
        "environment_digest": environment_digest,
        "environment_keys": ["TOKEN"],
        "matched_rule_id": None,
        "matched_rule_name": None,
        "permission_mode": PermissionMode.approval_required,
        "requested_by": "operator",
        "task_id": "BL-003a",
        "timeout_seconds": 30,
    }
    raw_command_digest = hashlib.sha256(
        json.dumps(
            raw_command_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    assert environment_digest.startswith("hmac-sha256:")
    assert command_digest.startswith("hmac-sha256:")
    assert len(environment_digest.removeprefix("hmac-sha256:")) == 64
    assert len(command_digest.removeprefix("hmac-sha256:")) == 64
    assert environment_digest == command_environment_digest(overrides)
    assert environment_digest != raw_environment_digest
    assert command_digest != raw_command_digest
    assert (data_dir / "cli-approval-digest.key").exists()


def test_loaded_approval_and_run_models_resanitize_command_text(runtime) -> None:
    _service, root_dir, _data_dir = runtime

    approval = CommandApproval(
        id="approval-legacy",
        command="python deploy.py --token legacy-secret",
        review_command="python deploy.py --token legacy-secret",
        command_digest="a" * 64,
        environment_digest="b" * 64,
        cwd=root_dir,
        timeout_seconds=5,
        policy_reason="Legacy approval.",
    )
    run = CommandRun(
        id="cmdrun-legacy",
        command="python deploy.py --client_secret legacy-client",
        cwd=root_dir,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        started_at=datetime.now(UTC),
    )

    assert "legacy-secret" not in approval.command
    assert "legacy-secret" not in approval.review_command
    assert approval.command_digest == REDACTED_LEGACY_DIGEST_MARKER
    assert approval.environment_digest == REDACTED_LEGACY_DIGEST_MARKER
    assert "legacy-client" not in run.command


def test_redacted_approval_requires_bound_execution_request(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(
        CommandExecutionRequest(command="python -c \"print('TOKEN=abc123')\"")
    )
    service.approve_approval(approval.id, decided_by="reviewer")

    with pytest.raises(PermissionError, match="redacted"):
        service.execute_approved_command(approval.id)


def test_create_approval_rejects_safe_and_out_of_root_commands(runtime, tmp_path) -> None:
    service, _root_dir, _data_dir = runtime

    with pytest.raises(ValueError, match="Only approval-required"):
        service.create_approval(CommandExecutionRequest(command="cmd /c echo safe"))

    with pytest.raises(PermissionError, match="outside configured rootDir"):
        service.create_approval(
            CommandExecutionRequest(
                command="python --version",
                cwd=tmp_path / "outside",
            )
        )


def test_denied_approval_cannot_execute(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(CommandExecutionRequest(command="python --version"))

    denied = service.deny_approval(
        approval.id,
        decided_by="reviewer",
        reason="Not needed.",
    )

    assert denied.status == CommandApprovalStatus.denied
    assert denied.decision_reason == "Not needed."
    assert denied.denial_reason == "Not needed."
    review = service.get_approval_review(approval.id)
    assert review.status == CommandApprovalStatus.denied
    assert review.decision_reason == "Not needed."
    assert review.denial_reason == "Not needed."
    with pytest.raises(PermissionError, match="not executable"):
        service.execute_approved_command(approval.id)
    assert service.list_command_runs() == []


def test_approved_command_executes_once_and_records_sanitized_history(
    runtime,
    monkeypatch,
) -> None:
    service, root_dir, data_dir = runtime
    approval = service.create_approval(
        CommandExecutionRequest(command="python --version", timeout_seconds=5)
    )

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        assert cwd == root_dir.resolve()
        assert "PATH" in env
        assert capture_output is True
        assert text is True
        assert timeout == 5
        assert check is False
        return subprocess.CompletedProcess(
            args=args,
            returncode=7,
            stdout="TOKEN=abc123 " + ("x" * 80),
            stderr="PASSWORD=hunter2\nSECRET=rosebud",
        )

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    service.approve_approval(approval.id, decided_by="reviewer")
    result = service.execute_approved_command(approval.id)

    assert result.exit_code == 7
    assert result.permission_mode == PermissionMode.approval_required
    assert "TOKEN=[REDACTED]" in result.stdout
    assert "abc123" not in result.stdout
    assert result.stdout.endswith("[output truncated]")
    assert "PASSWORD=[REDACTED]" in result.stderr
    assert "SECRET=[REDACTED]" in result.stderr
    assert "hunter2" not in result.stderr

    runs = service.list_command_runs()
    assert len(runs) == 1
    assert runs[0].approval_id == approval.id
    assert runs[0].stdout_truncated is True
    assert runs[0].exit_code == 7
    assert runs[0].duration_ms >= 0
    assert (data_dir / "cli-command-runs.json").exists()

    updated_approval = service.list_approvals()[0]
    assert updated_approval.status == CommandApprovalStatus.executed
    assert updated_approval.run_id == runs[0].id
    with pytest.raises(PermissionError, match="not executable"):
        service.execute_approved_command(approval.id)


def test_safe_command_execution_is_persisted_with_root_boundary(
    runtime, tmp_path, monkeypatch
) -> None:
    service, root_dir, _data_dir = runtime

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        assert cwd == root_dir.resolve()
        assert "PATH" in env
        if subprocess.os.name != "nt":
            assert args == ["sh", "-c", "echo hello"]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="hello",
            stderr="",
        )

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    result = service.execute_command(CommandExecutionRequest(command="cmd /c echo hello"))

    assert result.exit_code == 0
    assert result.stdout == "hello"
    assert service.list_command_runs()[0].permission_mode == PermissionMode.autopilot_safe

    with pytest.raises(PermissionError, match="outside configured rootDir"):
        service.execute_command(
            CommandExecutionRequest(command="cmd /c echo hello", cwd=tmp_path / "outside")
        )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cmd /c echo hello", ["sh", "-c", "echo hello"]),
        ("cmd.exe /c echo hello", ["sh", "-c", "echo hello"]),
        ('cmd /c "echo hello world"', ["sh", "-c", "echo hello world"]),
        ("cmd /cecho compact", ["sh", "-c", "echo compact"]),
        ('cmd /d /s /c "echo hello"', ["sh", "-c", "echo hello"]),
    ],
)
def test_command_args_translates_cmd_wrappers_on_posix(command: str, expected: list[str]) -> None:
    if subprocess.os.name == "nt":
        args = _command_args(command)
        assert isinstance(args, list)
        assert args[0].lower().endswith("cmd") or args[0].lower().endswith("cmd.exe")
        assert "/d" in [argument.lower() for argument in args[1:]]
    else:
        assert _command_args(command) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            "powershell -Command echo hello",
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "echo", "hello"],
        ),
        (
            "powershell -NoProfile -Command echo hello",
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", "echo", "hello"],
        ),
        (
            "pwsh -NonInteractive -c 'echo hello'",
            ["pwsh", "-NoProfile", "-NonInteractive", "-c", "echo hello"],
        ),
    ],
)
def test_command_args_suppresses_powershell_profiles_and_interactivity(
    command: str,
    expected: list[str],
) -> None:
    assert _command_args(command) == expected


def test_power_shell_command_execution_uses_no_profile_noninteractive_args(
    runtime,
    monkeypatch,
) -> None:
    service, root_dir, _data_dir = runtime
    captured: dict[str, object] = {}

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        captured["args"] = args
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    result = service.execute_command(
        CommandExecutionRequest(command="powershell -Command echo hello")
    )

    assert captured["args"] == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "echo",
        "hello",
    ]
    assert captured["cwd"] == root_dir.resolve()
    assert result.exit_code == 0


def test_command_execution_requires_approval_for_state_file_reads(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    with pytest.raises(PermissionError, match="approved approval_id"):
        service.execute_command(
            CommandExecutionRequest(command="cmd /c type .dgentic\\cli-approval-digest.key")
        )


def test_read_only_command_path_escape_is_blocked_before_subprocess(
    runtime,
    monkeypatch,
) -> None:
    service, _root_dir, _data_dir = runtime

    def fake_run(*args, **kwargs):
        pytest.fail("Subprocess should not start for out-of-root read-only path arguments.")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    with pytest.raises(PermissionError, match="outside configured rootDir"):
        service.execute_command(CommandExecutionRequest(command="cat ../secret.txt"))


def test_command_execution_applies_controlled_environment_and_audit_context(
    runtime, monkeypatch
) -> None:
    service, root_dir, _data_dir = runtime

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        assert cwd == root_dir.resolve()
        assert env["DGENTIC_TEST_FLAG"] == "enabled"
        assert "PATH" in env
        assert "PYTHONPATH" not in env
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    result = service.execute_command(
        CommandExecutionRequest(
            command="cmd /c echo ok",
            requested_by="pm",
            agent_id="agent-dev-1",
            agent_role="developer",
            task_id="story-5.3",
            environment={"DGENTIC_TEST_FLAG": "enabled"},
        )
    )
    run = service.list_command_runs()[0]

    assert result.exit_code == 0
    assert result.requested_by == "pm"
    assert result.agent_id == "agent-dev-1"
    assert result.agent_role == "developer"
    assert result.task_id == "story-5.3"
    assert result.environment_keys == ["DGENTIC_TEST_FLAG"]
    assert run.environment_keys == ["DGENTIC_TEST_FLAG"]
    assert run.agent_role == "developer"


def test_command_environment_blocks_sensitive_runtime_overrides(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    with pytest.raises(ValueError, match="PATH"):
        service.execute_command(
            CommandExecutionRequest(
                command="cmd /c echo blocked",
                environment={"PATH": "C:\\unsafe"},
            )
        )


@pytest.mark.parametrize(
    "environment_key",
    [
        "BASH_ENV",
        "env",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "NODE_OPTIONS",
        "RUBYOPT",
        "PERL5LIB",
        "BASH_FUNC_MALICIOUS",
    ],
)
def test_command_environment_blocks_startup_hook_and_preload_overrides(
    runtime,
    environment_key: str,
) -> None:
    service, _root_dir, _data_dir = runtime

    with pytest.raises(ValueError, match="not allowed"):
        service.execute_command(
            CommandExecutionRequest(
                command="cmd /c echo blocked",
                environment={environment_key: "C:\\unsafe"},
            )
        )


def test_command_runs_and_results_redact_secret_bearing_commands(
    runtime,
    monkeypatch,
) -> None:
    service, _root_dir, _data_dir = runtime

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    result = service.execute_command(
        CommandExecutionRequest(
            command=(
                r"python deploy.py --client_secret result-secret --token escaped\ value "
                "--api-key=$(printf RUN_SECRET; echo ok)"
            ),
            approved=True,
        )
    )
    run = service.list_command_runs()[0]

    assert "result-secret" not in result.command
    assert "result-secret" not in run.command
    assert "escaped\\ value" not in result.command
    assert "escaped\\ value" not in run.command
    assert "RUN_SECRET" not in result.command
    assert "RUN_SECRET" not in run.command
    assert "echo ok)" not in result.command
    assert "echo ok)" not in run.command
    assert "--client_secret [REDACTED]" in result.command
    assert "--client_secret [REDACTED]" in run.command
    assert "--token [REDACTED]" in result.command
    assert "--token [REDACTED]" in run.command
    assert "--api-key=[REDACTED]" in result.command
    assert "--api-key=[REDACTED]" in run.command


def test_approval_queue_records_environment_keys_without_values(runtime) -> None:
    service, _root_dir, data_dir = runtime

    approval = service.create_approval(
        CommandExecutionRequest(
            command="python --version",
            environment={"DGENTIC_TEST_FLAG": "should-not-persist"},
        )
    )

    assert approval.environment_keys == ["DGENTIC_TEST_FLAG"]
    approval_storage = (data_dir / "cli-approvals.json").read_text(encoding="utf-8")
    assert "DGENTIC_TEST_FLAG" in approval_storage
    assert "should-not-persist" not in approval_storage


def test_production_approval_required_commands_need_bound_approval_id(
    tmp_path, monkeypatch
) -> None:
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    get_settings.cache_clear()
    service = CliRuntimeService(max_output_chars=48)

    with pytest.raises(PermissionError, match="approved approval_id"):
        service.execute_command(CommandExecutionRequest(command="python --version", approved=True))

    approval = service.create_approval(
        CommandExecutionRequest(
            command="python --version",
            timeout_seconds=5,
            requested_by="operator",
            agent_role="developer",
            task_id="sprint-9",
            environment={"DGENTIC_TEST_FLAG": "reviewed"},
        )
    )

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        assert cwd == root_dir.resolve()
        assert env["DGENTIC_TEST_FLAG"] == "reviewed"
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    service.approve_approval(approval.id, decided_by="reviewer")
    with pytest.raises(PermissionError, match="not bound"):
        service.execute_command(
            CommandExecutionRequest(
                command="python --version",
                timeout_seconds=5,
                approval_id=approval.id,
                requested_by="operator",
                agent_role="developer",
                task_id="sprint-9",
                environment={"DGENTIC_TEST_FLAG": "execute"},
            )
        )

    result = service.execute_command(
        CommandExecutionRequest(
            command="python --version",
            timeout_seconds=5,
            approval_id=approval.id,
            requested_by="operator",
            agent_role="developer",
            task_id="sprint-9",
            environment={"DGENTIC_TEST_FLAG": "reviewed"},
        )
    )

    run = service.list_command_runs()[0]
    executed = service.list_approvals()[0]
    assert result.exit_code == 0
    assert run.approval_id == approval.id
    assert executed.status == CommandApprovalStatus.executed
    assert executed.run_id == run.id

    with pytest.raises(PermissionError, match="not executable"):
        service.execute_command(
            CommandExecutionRequest(
                command="python --version",
                timeout_seconds=5,
                approval_id=approval.id,
                requested_by="operator",
                agent_role="developer",
                task_id="sprint-9",
                environment={"DGENTIC_TEST_FLAG": "reviewed"},
            )
        )
    get_settings.cache_clear()


def test_legacy_guarded_command_uses_runtime_approval_gate(tmp_path, monkeypatch) -> None:
    import dgentic.cli_runtime as cli_runtime_module
    from dgentic.guardrails import execute_guarded_command

    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    get_settings.cache_clear()
    service = CliRuntimeService(max_output_chars=48)
    monkeypatch.setattr(cli_runtime_module, "cli_runtime_service", service)

    with pytest.raises(PermissionError, match="approved approval_id"):
        execute_guarded_command(CommandExecutionRequest(command="python --version", approved=True))

    get_settings.cache_clear()


def test_bound_approval_rejects_mismatched_request(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(
        CommandExecutionRequest(
            command="python --version",
            requested_by="operator",
            environment={"DGENTIC_TEST_FLAG": "reviewed"},
        )
    )
    service.approve_approval(approval.id, decided_by="reviewer")

    with pytest.raises(PermissionError, match="not bound"):
        service.execute_command(
            CommandExecutionRequest(
                command="python --version",
                approval_id=approval.id,
                requested_by="operator",
            )
        )


def test_bound_approval_id_is_claimed_before_subprocess_starts(
    runtime,
    monkeypatch,
) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(
        CommandExecutionRequest(command="python --version", requested_by="operator")
    )
    service.approve_approval(approval.id, decided_by="reviewer")

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        claimed = service.list_approvals()[0]
        assert claimed.status == CommandApprovalStatus.executed
        assert claimed.run_id is None
        with pytest.raises(PermissionError, match="not executable"):
            service.execute_command(
                CommandExecutionRequest(
                    command="python --version",
                    approval_id=approval.id,
                    requested_by="operator",
                )
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    result = service.execute_command(
        CommandExecutionRequest(
            command="python --version",
            approval_id=approval.id,
            requested_by="operator",
        )
    )

    executed = service.list_approvals()[0]
    assert result.exit_code == 0
    assert executed.status == CommandApprovalStatus.executed
    assert executed.run_id is not None


def test_expired_approval_cannot_be_approved_or_executed(runtime) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(CommandExecutionRequest(command="python --version"))
    approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    service._approvals.upsert(approval)

    with pytest.raises(ValueError, match="expired"):
        service.approve_approval(approval.id, decided_by="reviewer")

    approved = service.create_approval(CommandExecutionRequest(command="python --version"))
    approved = service.approve_approval(approved.id, decided_by="reviewer")
    approved.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    service._approvals.upsert(approved)

    with pytest.raises(PermissionError, match="expired"):
        service.execute_approved_command(approved.id)


def test_sanitize_output_redacts_before_truncating() -> None:
    output, truncated = sanitize_output(
        "TOKEN=abc PASSWORD=hunter2 SECRET=rosebud trailing text",
        max_chars=36,
    )

    assert "abc" not in output
    assert "hunter2" not in output
    assert "rosebud" not in output
    assert "TOKEN=[REDACTED]" in output
    assert truncated is True


def test_async_command_run_can_be_polled_after_completion(runtime) -> None:
    service, _root_dir, data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command="python -c \"print('TOKEN=abc123')\"",
            approved=True,
            timeout_seconds=5,
        )
    )

    assert run.status == CommandRunStatus.running
    for _attempt in range(40):
        polled = service.get_command_run(run.id)
        assert polled is not None
        if polled.status == CommandRunStatus.completed:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Async command did not complete.")

    assert polled.exit_code == 0
    assert "TOKEN=[REDACTED]" in polled.stdout
    assert "abc123" not in polled.stdout
    assert polled.completed_at is not None
    assert (data_dir / "cli-command-runs.json").exists()


def test_start_command_uses_translated_cmd_wrapper_on_posix(runtime, monkeypatch) -> None:
    service, root_dir, _data_dir = runtime
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345
        stdout = io.StringIO("hello\n")
        stderr = io.StringIO("")

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        @property
        def returncode(self):
            return 0

    def fake_popen(args, env, cwd, stdout, stderr, text, **kwargs):
        captured["args"] = args
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.Popen", fake_popen)

    run = service.start_command(CommandExecutionRequest(command="cmd /c echo hello"))

    if subprocess.os.name != "nt":
        assert captured["args"] == ["sh", "-c", "echo hello"]
    else:
        assert captured["args"] == ["cmd", "/d", "/c", "echo", "hello"]
    assert captured["cwd"] == root_dir.resolve()
    assert run.status == CommandRunStatus.running


def test_start_command_records_supervision_metadata(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command="python -c \"print('supervised')\"",
            approved=True,
            timeout_seconds=5,
        )
    )

    assert run.status == CommandRunStatus.running
    assert run.supervisor_id == service.supervisor_id
    assert run.supervisor_pid is not None
    assert run.timeout_at is not None
    assert run.timeout_at > run.started_at
    assert run.last_heartbeat_at is not None
    assert run.status_reason == "Command process started."


def test_start_command_records_failed_launch_after_persisting_intent(
    runtime,
    monkeypatch,
) -> None:
    service, _root_dir, _data_dir = runtime

    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("missing executable")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.Popen", fake_popen)

    with pytest.raises(FileNotFoundError):
        service.start_command(
            CommandExecutionRequest(
                command="python --version",
                approved=True,
                timeout_seconds=5,
            )
        )

    runs = service.list_command_runs()
    assert len(runs) == 1
    failed = runs[0]
    assert failed.status == CommandRunStatus.failed
    assert failed.exit_code == -1
    assert failed.completed_at is not None
    assert failed.last_heartbeat_at is not None
    assert failed.supervisor_id == service.supervisor_id
    assert failed.status_reason is not None
    assert "Command launch failed" in failed.status_reason
    assert "missing executable" in failed.stderr


def test_start_command_launch_failure_binds_approval(runtime, monkeypatch) -> None:
    service, _root_dir, _data_dir = runtime
    approval = service.create_approval(
        CommandExecutionRequest(command="python --version", timeout_seconds=5),
        requested_by="operator",
    )
    service.approve_approval(approval.id, decided_by="reviewer")

    def fake_popen(*args, **kwargs):
        raise OSError("launch refused")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.Popen", fake_popen)

    with pytest.raises(OSError):
        service.start_command(
            CommandExecutionRequest(
                command="python --version",
                timeout_seconds=5,
                approval_id=approval.id,
                requested_by="operator",
            )
        )

    failed = next(run for run in service.list_command_runs() if run.approval_id == approval.id)
    stored_approval = next(
        item
        for item in service.list_approvals(CommandApprovalStatus.executed)
        if item.id == approval.id
    )
    assert failed.status == CommandRunStatus.failed
    assert stored_approval.status == CommandApprovalStatus.executed
    assert stored_approval.run_id == failed.id
    with pytest.raises(PermissionError, match="not executable"):
        service.start_command(
            CommandExecutionRequest(
                command="python --version",
                timeout_seconds=5,
                approval_id=approval.id,
                requested_by="operator",
            )
        )


def test_starting_command_cancellation_waits_for_process_registration(
    runtime,
    monkeypatch,
) -> None:
    service, _root_dir, _data_dir = runtime
    launch_started = Event()
    release_launch = Event()
    errors: list[BaseException] = []

    class FakeProcess:
        pid = 12345
        stdout = io.StringIO("")
        stderr = io.StringIO("")

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        @property
        def returncode(self):
            return 0

    def fake_popen(*args, **kwargs):
        launch_started.set()
        release_launch.wait(timeout=5)
        return FakeProcess()

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.Popen", fake_popen)

    def start_run() -> None:
        try:
            service.start_command(
                CommandExecutionRequest(
                    command="python --version",
                    approved=True,
                    timeout_seconds=5,
                )
            )
        except BaseException as exc:  # pragma: no cover - re-raised by assertion below.
            errors.append(exc)

    starter = Thread(target=start_run)
    starter.start()
    assert launch_started.wait(timeout=2)
    starting_run = service.list_command_runs()[0]

    with pytest.raises(ValueError, match="still starting"):
        service.cancel_command_run(starting_run.id)

    release_launch.set()
    starter.join(timeout=5)
    assert not starter.is_alive()
    assert not errors
    stored = service.get_command_run(starting_run.id)
    assert stored is not None
    assert stored.status in {CommandRunStatus.running, CommandRunStatus.completed}
    assert stored.stale_reason is None


def test_start_command_launch_failure_redacts_status_reason(
    runtime,
    monkeypatch,
) -> None:
    service, _root_dir, _data_dir = runtime

    def fake_popen(*args, **kwargs):
        raise OSError("TOKEN=supersecret")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.Popen", fake_popen)

    with pytest.raises(OSError):
        service.start_command(
            CommandExecutionRequest(
                command="python --version",
                approved=True,
                timeout_seconds=5,
            )
        )

    failed = service.list_command_runs()[0]
    assert failed.status == CommandRunStatus.failed
    assert failed.status_reason is not None
    assert "supersecret" not in failed.status_reason
    assert "TOKEN=[REDACTED]" in failed.status_reason
    assert "supersecret" not in failed.stderr


def test_async_command_run_streams_redacted_output_chunks(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command=(
                "python -c \"import time; print('TOKEN=abc123', flush=True); "
                "time.sleep(0.5); print('done', flush=True)\""
            ),
            approved=True,
            timeout_seconds=5,
        )
    )

    for _attempt in range(40):
        output = service.get_command_run_output(run.id)
        if output.chunks:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Async command did not stream output chunks.")

    assert output.run_id == run.id
    assert output.status in {CommandRunStatus.running, CommandRunStatus.completed}
    assert output.next_sequence >= 1
    assert any("TOKEN=[REDACTED]" in chunk.text for chunk in output.chunks)
    assert all("abc123" not in chunk.text for chunk in output.chunks)

    later_output = service.get_command_run_output(run.id, after_sequence=output.next_sequence)
    assert all(chunk.sequence > output.next_sequence for chunk in later_output.chunks)

    for _attempt in range(40):
        polled = service.get_command_run(run.id)
        assert polled is not None
        if polled.status == CommandRunStatus.completed:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Async streaming command did not complete.")

    assert "TOKEN=[REDACTED]" in polled.stdout
    assert "abc123" not in polled.stdout
    assert polled.last_output_at is not None


def test_async_command_run_can_be_cancelled(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command='python -c "import time; time.sleep(10)"',
            approved=True,
            timeout_seconds=30,
        )
    )
    cancelled = service.cancel_command_run(run.id)

    assert cancelled.status == CommandRunStatus.cancelled
    assert cancelled.cancelled_at is not None
    for _attempt in range(40):
        polled = service.get_command_run(run.id)
        assert polled is not None
        if polled.completed_at is not None:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Cancelled command did not finalize.")

    assert polled.status == CommandRunStatus.cancelled
    assert polled.exit_code is not None


def test_cancel_command_run_refreshes_registered_process_metadata(
    runtime,
    monkeypatch,
) -> None:
    service, root_dir, _data_dir = runtime

    class FakeProcess:
        pid = None
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            if self.returncode is None:
                self.returncode = -15
            return self.returncode

    registered_run = CommandRun(
        id="cmdrun-registered-cancel",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=12345,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id=service.supervisor_id,
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    stale_snapshot = registered_run.model_copy(
        update={
            "status": CommandRunStatus.starting,
            "process_id": None,
        }
    )
    service._runs.upsert(registered_run)
    service._active_processes[registered_run.id] = FakeProcess()
    monkeypatch.setattr(service, "_get_run_or_raise", lambda _run_id: stale_snapshot)

    cancelled = service.cancel_command_run(registered_run.id)
    stored = service.get_command_run(registered_run.id)

    assert cancelled.status == CommandRunStatus.cancelled
    assert cancelled.process_id == 12345
    assert stored is not None
    assert stored.process_id == 12345


def test_cancel_command_run_does_not_stale_refreshed_terminal_run(
    runtime,
    monkeypatch,
) -> None:
    service, root_dir, _data_dir = runtime
    started_at = datetime.now(UTC)
    stale_snapshot = CommandRun(
        id="cmdrun-finalizing-cancel",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=12345,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id=service.supervisor_id,
        supervisor_pid=12345,
        started_at=started_at,
    )
    completed_run = stale_snapshot.model_copy(
        update={
            "status": CommandRunStatus.completed,
            "exit_code": 0,
            "duration_ms": 10,
            "completed_at": started_at + timedelta(milliseconds=10),
            "status_reason": "Command process completed.",
        }
    )
    service._runs.upsert(completed_run)
    monkeypatch.setattr(service, "_get_run_or_raise", lambda _run_id: stale_snapshot)

    with pytest.raises(ValueError, match="current status is completed"):
        service.cancel_command_run(stale_snapshot.id)

    stored = service.get_command_run(stale_snapshot.id)
    assert stored is not None
    assert stored.status == CommandRunStatus.completed
    assert stored.stale_reason is None


def test_async_command_cancel_kills_sigterm_ignoring_process_on_posix(runtime) -> None:
    if subprocess.os.name == "nt":
        pytest.skip("POSIX process-group signal escalation is not used on Windows.")
    service, _root_dir, _data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command=(
                'python -c "import signal, time; '
                'signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"'
            ),
            approved=True,
            timeout_seconds=30,
        )
    )
    cancelled = service.cancel_command_run(run.id)

    assert cancelled.status == CommandRunStatus.cancelled
    assert cancelled.exit_code is not None
    for _attempt in range(40):
        polled = service.get_command_run(run.id)
        assert polled is not None
        if polled.completed_at is not None:
            break
        time.sleep(0.1)
    else:
        pytest.fail("SIGTERM-ignoring command did not finalize after cancellation.")
    assert polled.status == CommandRunStatus.cancelled


def test_async_command_run_times_out_with_auditable_state(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command='python -c "import time; time.sleep(5)"',
            approved=True,
            timeout_seconds=1,
        )
    )

    for _attempt in range(60):
        polled = service.get_command_run(run.id)
        assert polled is not None
        if polled.status == CommandRunStatus.timed_out:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Async command did not time out.")

    output = service.get_command_run_output(run.id)
    assert polled.exit_code is not None
    assert polled.timeout_at is not None
    assert polled.completed_at is not None
    assert polled.last_heartbeat_at is not None
    assert polled.status_reason == "Command process timed out."
    assert "timed out" in polled.stderr
    assert any("timed out" in chunk.text for chunk in output.chunks)


def test_async_nonzero_exit_records_failed_status(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    run = service.start_command(
        CommandExecutionRequest(
            command="python -c \"import sys; print('nope'); sys.exit(7)\"",
            approved=True,
            timeout_seconds=5,
        )
    )

    for _attempt in range(40):
        polled = service.get_command_run(run.id)
        assert polled is not None
        if polled.status == CommandRunStatus.failed:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Async command did not record failed status.")

    assert polled.exit_code == 7
    assert polled.status_reason == "Command process failed."
    assert "nope" in polled.stdout
    output = service.get_command_run_output(run.id)
    assert any("nope" in chunk.text for chunk in output.chunks)


def test_cancel_orphaned_running_run_marks_stale(runtime) -> None:
    service, root_dir, _data_dir = runtime
    orphaned_run = CommandRun(
        id="cmdrun-orphaned",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=999999,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        status_reason="Command process started.",
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(orphaned_run)

    reconciled = service.cancel_command_run(orphaned_run.id)

    assert reconciled.status == CommandRunStatus.stale
    assert reconciled.exit_code == -1
    assert reconciled.completed_at is not None
    assert reconciled.last_heartbeat_at is not None
    assert reconciled.stale_reason is not None
    assert "Cancellation requested" in reconciled.stale_reason
    assert "previous backend supervisor" in reconciled.stale_reason
    assert reconciled.termination_status == OrphanTerminationStatus.skipped
    assert reconciled.termination_reason == (
        "Termination skipped because process identity was not persisted."
    )
    assert reconciled.termination_attempted_at is not None
    assert reconciled.termination_completed_at is not None
    assert reconciled.terminated_by_supervisor_id == service.supervisor_id


def test_reconcile_stale_command_runs_marks_orphaned_running_records(runtime) -> None:
    service, root_dir, _data_dir = runtime
    stale_run = CommandRun(
        id="cmdrun-stale",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=999999,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        requested_by="operator",
        agent_role="developer",
        task_id="sprint-9",
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(stale_run)

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(stale_run.id)

    assert [run.id for run in reconciled] == [stale_run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.exit_code == -1
    assert stored.completed_at is not None
    assert "marked stale" in stored.stderr
    assert stored.stale_reason is not None
    assert "no persisted supervisor metadata" in stored.stale_reason
    assert stored.termination_status == OrphanTerminationStatus.skipped
    assert stored.termination_reason == (
        "Termination skipped because process identity was not persisted."
    )


def test_reconcile_stale_command_runs_records_launch_interruption_reason(runtime) -> None:
    service, root_dir, _data_dir = runtime
    starting_run = CommandRun(
        id="cmdrun-starting",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.starting,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id=service.supervisor_id,
        supervisor_pid=12345,
        status_reason="Command launch requested.",
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(starting_run)

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(starting_run.id)

    assert [run.id for run in reconciled] == [starting_run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.stale_reason is not None
    assert "launch did not complete" in stored.stale_reason
    assert stored.termination_status == OrphanTerminationStatus.skipped
    assert stored.termination_reason == "Termination skipped because the run is not running."


def test_reconcile_stale_command_runs_records_previous_supervisor_reason(runtime) -> None:
    service, root_dir, _data_dir = runtime
    previous_supervisor_run = CommandRun(
        id="cmdrun-previous-supervisor",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=999999,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        status_reason="Command process started.",
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(previous_supervisor_run)

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(previous_supervisor_run.id)

    assert [run.id for run in reconciled] == [previous_supervisor_run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.stale_reason is not None
    assert "previous backend supervisor" in stored.stale_reason
    assert stored.termination_status == OrphanTerminationStatus.skipped
    assert stored.termination_reason == (
        "Termination skipped because process identity was not persisted."
    )


def test_reconcile_previous_supervisor_skips_termination_on_identity_mismatch(
    runtime,
    monkeypatch,
) -> None:
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-mismatch",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=4242,
        process_group_id=4242,
        process_identity="posix-proc-start:old",
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        status_reason="Command process started.",
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(run)
    monkeypatch.setattr(
        "dgentic.cli_runtime._process_snapshot",
        lambda pid: ProcessSnapshot(pid=pid, identity="posix-proc-start:new"),
    )

    def fail_termination(_run: CommandRun) -> None:
        pytest.fail("Mismatched process identity must not be terminated.")

    monkeypatch.setattr(service, "_terminate_orphaned_process", fail_termination)

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(run.id)

    assert [item.id for item in reconciled] == [run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.termination_status == OrphanTerminationStatus.skipped
    assert (
        stored.termination_reason == "Termination skipped because process identity did not match."
    )


def test_reconcile_previous_supervisor_terminates_matching_orphan_and_marks_stale(
    runtime,
    monkeypatch,
) -> None:
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-matching-orphan",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=4242,
        process_group_id=4242,
        process_identity="posix-proc-start:match",
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        status_reason="Command process started.",
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(run)
    terminated: list[str] = []
    monkeypatch.setattr(
        "dgentic.cli_runtime._process_snapshot",
        lambda pid: ProcessSnapshot(pid=pid, identity="posix-proc-start:match"),
    )
    monkeypatch.setattr(
        service,
        "_terminate_orphaned_process",
        lambda orphaned_run: terminated.append(orphaned_run.id),
    )

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(run.id)

    assert [item.id for item in reconciled] == [run.id]
    assert terminated == [run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.termination_status == OrphanTerminationStatus.terminated
    assert stored.termination_reason is not None
    assert "termination was requested" in stored.termination_reason
    assert stored.terminated_by_supervisor_id == service.supervisor_id
    assert stored.termination_attempted_at is not None
    assert stored.termination_completed_at is not None


def test_terminate_orphaned_process_uses_posix_process_group(runtime, monkeypatch) -> None:
    if subprocess.os.name == "nt":
        pytest.skip("POSIX process groups are not used on Windows.")
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-posix-orphan",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=4242,
        process_group_id=4242,
        process_identity="posix-proc-start:match",
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    signals: list[tuple[int, int]] = []
    snapshots = iter(
        [
            ProcessSnapshot(pid=4242, identity="posix-proc-start:match"),
            None,
        ]
    )
    monkeypatch.setattr(
        "dgentic.cli_runtime.os.killpg", lambda pgid, sig: signals.append((pgid, sig))
    )
    monkeypatch.setattr("dgentic.cli_runtime.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("dgentic.cli_runtime._process_snapshot", lambda _pid: next(snapshots))

    service._terminate_orphaned_process(run)

    assert signals == [(4242, signal.SIGTERM)]


def test_terminate_orphaned_process_uses_windows_taskkill(runtime, monkeypatch) -> None:
    if subprocess.os.name != "nt":
        pytest.skip("Windows taskkill is not used on POSIX.")
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-windows-orphan",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=4242,
        process_identity="windows-created:match",
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    service._terminate_orphaned_process(run)

    assert calls == [["taskkill", "/PID", "4242", "/T", "/F"]]


def test_reconcile_windows_taskkill_timeout_marks_orphan_stale_with_failure(
    runtime,
    monkeypatch,
) -> None:
    if subprocess.os.name != "nt":
        pytest.skip("Windows taskkill is not used on POSIX.")
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-windows-timeout",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=4242,
        process_identity="windows-created:match",
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(run)
    monkeypatch.setattr(
        "dgentic.cli_runtime._process_snapshot",
        lambda pid: ProcessSnapshot(pid=pid, identity="windows-created:match"),
    )

    def fake_run(args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=5)

    monkeypatch.setattr("dgentic.cli_runtime.subprocess.run", fake_run)

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(run.id)

    assert [item.id for item in reconciled] == [run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.termination_status == OrphanTerminationStatus.failed
    assert stored.termination_reason is not None
    assert stored.termination_reason.startswith("Orphan process termination")
    assert stored.stale_reason is not None
    assert "previous backend supervisor" in stored.stale_reason


def test_output_chunk_sequence_remains_monotonic_after_retention_trim(runtime) -> None:
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-output-retention",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=12345,
        permission_mode=PermissionMode.autopilot_safe,
        duration_ms=0,
        supervisor_id=service.supervisor_id,
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(run)

    for index in range(DEFAULT_MAX_OUTPUT_CHUNKS + 2):
        service._append_output_chunk(run.id, "stdout", f"chunk-{index}\n")

    stored = service.get_command_run(run.id)

    assert stored is not None
    assert len(stored.output_chunks) == DEFAULT_MAX_OUTPUT_CHUNKS
    assert stored.output_chunks[-1].sequence == DEFAULT_MAX_OUTPUT_CHUNKS + 2
    assert stored.output_chunks[-1].text == f"chunk-{DEFAULT_MAX_OUTPUT_CHUNKS + 1}\n"
    cursor_output = service.get_command_run_output(
        run.id,
        after_sequence=DEFAULT_MAX_OUTPUT_CHUNKS + 1,
    )
    assert [chunk.sequence for chunk in cursor_output.chunks] == [DEFAULT_MAX_OUTPUT_CHUNKS + 2]


def test_stale_reconciliation_preserves_output_cursor_and_approval_id(runtime) -> None:
    service, root_dir, _data_dir = runtime
    run = CommandRun(
        id="cmdrun-stale-output",
        approval_id="approval-used",
        command="python --version TOKEN=secret-value",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=999999,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        stdout="TOKEN=[REDACTED]\n",
        output_chunks=[
            CommandOutputChunk(
                sequence=1,
                stream="stdout",
                text="TOKEN=[REDACTED]\n",
            )
        ],
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    service._runs.upsert(run)

    reconciled = service.reconcile_stale_command_runs()
    stored = service.get_command_run(run.id)
    output = service.get_command_run_output(run.id, after_sequence=0)

    assert [item.id for item in reconciled] == [run.id]
    assert stored is not None
    assert stored.status == CommandRunStatus.stale
    assert stored.approval_id == "approval-used"
    assert "secret-value" not in stored.command
    assert "TOKEN=[REDACTED]" in stored.stdout
    assert [chunk.sequence for chunk in output.chunks] == [1]
    assert "TOKEN=[REDACTED]" in output.chunks[0].text


def _create_running_orchestration_task_for_runtime(
    service: OrchestrationService | None = None,
):
    return (service or OrchestrationService()).create_run(
        OrchestrationCreateRequest(
            objective="Bind CLI runtime execution to a running QA task.",
            tasks=[
                OrchestrationTaskSpec(
                    id="qa-validation",
                    title="QA validation",
                    description="Validate orchestration-bound CLI runtime behavior.",
                    role="QA",
                    declared_write_paths=["tests/test_cli_runtime.py"],
                    expected_output="Focused runtime regressions.",
                    validation="pytest tests/test_cli_runtime.py passes.",
                )
            ],
        )
    )
