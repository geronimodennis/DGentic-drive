import subprocess

import pytest

from dgentic.cli_runtime import CliRuntimeService, CommandApprovalStatus, sanitize_output
from dgentic.schemas import CommandExecutionRequest, PermissionMode
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

    def fake_run(args, cwd, capture_output, text, timeout, check):
        assert cwd == root_dir.resolve()
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

    def fake_run(args, cwd, capture_output, text, timeout, check):
        assert cwd == root_dir.resolve()
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
