import subprocess
import time
from datetime import UTC, datetime

import pytest

from dgentic.cli_runtime import (
    CliRuntimeService,
    CommandApprovalStatus,
    CommandRun,
    CommandRunStatus,
    sanitize_output,
)
from dgentic.command_policy import create_command_policy_rule
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandPolicyMatchType,
    CommandPolicyRuleRequest,
    PermissionMode,
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
    assert denied.denial_reason == "Not needed."
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


def test_approval_queue_rejects_environment_values(runtime) -> None:
    service, _root_dir, _data_dir = runtime

    with pytest.raises(ValueError, match="does not persist environment values"):
        service.create_approval(
            CommandExecutionRequest(
                command="python --version",
                environment={"DGENTIC_TEST_FLAG": "enabled"},
            )
        )


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
