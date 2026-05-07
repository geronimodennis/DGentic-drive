import os
import re
import shlex
import signal
import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from pydantic import BaseModel, Field

from dgentic.events import event_log
from dgentic.guardrails import evaluate_command_policy
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandPolicyDecision,
    CommandPolicyRequest,
    LogEventType,
    PermissionMode,
)
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

DEFAULT_MAX_OUTPUT_CHARS = 10_000
TRUNCATION_MARKER = "\n[output truncated]"
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>TOKEN|PASSWORD|SECRET)\s*=\s*(?P<value>[^\s;&|]+)",
    re.IGNORECASE,
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BLOCKED_ENV_OVERRIDES = {
    "COMSPEC",
    "HOME",
    "PATH",
    "PATHEXT",
    "PYTHONHOME",
    "PYTHONPATH",
    "SYSTEMROOT",
    "VIRTUAL_ENV",
}
_INHERITED_ENV_KEYS = {
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
}


class CommandApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    executed = "executed"


class CommandRunStatus(StrEnum):
    running = "running"
    completed = "completed"
    timed_out = "timed_out"
    cancelled = "cancelled"


class CommandApproval(BaseModel):
    id: str
    command: str
    cwd: Path
    timeout_seconds: int
    permission_mode: PermissionMode = PermissionMode.approval_required
    policy_reason: str
    status: CommandApprovalStatus = CommandApprovalStatus.pending
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    environment_keys: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    denial_reason: str | None = None
    run_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    executed_at: datetime | None = None


class CommandRun(BaseModel):
    id: str
    approval_id: str | None = None
    command: str
    cwd: Path
    status: CommandRunStatus = CommandRunStatus.completed
    process_id: int | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    permission_mode: PermissionMode
    duration_ms: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    environment_keys: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


def redact_sensitive_values(text: str) -> str:
    """Redact basic KEY=value secret assignments from command output."""

    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}=[REDACTED]",
        text,
    )


def truncate_output(text: str, max_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1.")
    if len(text) <= max_chars:
        return text, False
    if max_chars <= len(TRUNCATION_MARKER):
        return text[:max_chars], True
    return text[: max_chars - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER, True


def sanitize_output(text: str, max_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    return truncate_output(redact_sensitive_values(text), max_chars=max_chars)


def resolve_command_cwd(cwd: Path | None = None) -> Path:
    root_dir = get_settings().root_dir.resolve()
    candidate = cwd or root_dir
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    resolved = candidate.resolve()
    if resolved != root_dir and root_dir not in resolved.parents:
        raise PermissionError(f"Command cwd resolves outside configured rootDir: {root_dir}")
    return resolved


def _command_args(command: str) -> str | list[str]:
    if os.name == "nt":
        return command
    return shlex.split(command)


def _popen_kwargs(cwd: Path) -> dict:
    kwargs = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    elif os.name != "nt":
        kwargs["start_new_session"] = True
    return kwargs


def _base_command_environment() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _INHERITED_ENV_KEYS:
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def build_command_environment(overrides: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    env = _base_command_environment()
    applied_keys: list[str] = []
    for key, value in overrides.items():
        normalized_key = key.strip()
        if not _ENV_NAME_RE.fullmatch(normalized_key):
            raise ValueError(f"Invalid environment variable name: {key}")
        upper_key = normalized_key.upper()
        if upper_key in _BLOCKED_ENV_OVERRIDES:
            raise ValueError(f"Environment variable override is not allowed: {normalized_key}")
        if len(value) > 4096:
            raise ValueError(f"Environment variable value is too long: {normalized_key}")
        env[normalized_key] = value
        applied_keys.append(normalized_key)
    return env, sorted(applied_keys)


def validate_command_environment(overrides: dict[str, str]) -> list[str]:
    _env, environment_keys = build_command_environment(overrides)
    return environment_keys


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
        if process.pid is not None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        if process.poll() is None:
            process.kill()
        return

    if process.pid is not None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()
    else:
        process.terminate()


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class CliRuntimeService:
    def __init__(self, max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> None:
        self.max_output_chars = max_output_chars
        self._approvals = JsonCollection("cli-approvals", CommandApproval)
        self._runs = JsonCollection("cli-command-runs", CommandRun)
        self._active_processes: dict[str, subprocess.Popen] = {}
        self._cancelled_run_ids: set[str] = set()
        self._active_lock = Lock()

    def create_approval(
        self,
        request: CommandExecutionRequest,
        *,
        requested_by: str | None = None,
    ) -> CommandApproval:
        decision = evaluate_command_policy(
            CommandPolicyRequest(
                command=request.command,
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
        )
        if decision.permission_mode == PermissionMode.blocked:
            raise PermissionError(decision.reason)
        if decision.permission_mode != PermissionMode.approval_required:
            raise ValueError("Only approval-required commands can be queued for approval.")
        if request.environment:
            raise ValueError(
                "Approval queue does not persist environment values; execute with approval "
                "after reviewing the environment keys."
            )
        environment_keys = validate_command_environment(request.environment)

        approval = CommandApproval(
            id=f"approval-{uuid4()}",
            command=decision.command,
            cwd=resolve_command_cwd(request.cwd),
            timeout_seconds=request.timeout_seconds,
            permission_mode=decision.permission_mode,
            policy_reason=decision.reason,
            requested_by=requested_by or request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
        )
        self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Created CLI command approval request.",
            subject_id=approval.id,
            metadata={
                "command": redact_sensitive_values(approval.command),
                "cwd": str(approval.cwd),
                "permission_mode": approval.permission_mode,
                "requested_by": approval.requested_by,
                "agent_id": approval.agent_id,
                "agent_role": approval.agent_role,
                "task_id": approval.task_id,
                "environment_keys": approval.environment_keys,
            },
        )
        return approval

    def approve_approval(
        self,
        approval_id: str,
        *,
        decided_by: str | None = None,
    ) -> CommandApproval:
        approval = self._get_approval_or_raise(approval_id)
        if approval.status != CommandApprovalStatus.pending:
            raise ValueError(
                f"Only pending approvals can be approved; current status is {approval.status}."
            )

        now = datetime.now(UTC)
        approval.status = CommandApprovalStatus.approved
        approval.decided_by = decided_by
        approval.decided_at = now
        approval.updated_at = now
        self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Approved CLI command request.",
            subject_id=approval.id,
            actor=decided_by or "system",
        )
        return approval

    def deny_approval(
        self,
        approval_id: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> CommandApproval:
        approval = self._get_approval_or_raise(approval_id)
        if approval.status != CommandApprovalStatus.pending:
            raise ValueError(
                f"Only pending approvals can be denied; current status is {approval.status}."
            )

        now = datetime.now(UTC)
        approval.status = CommandApprovalStatus.denied
        approval.decided_by = decided_by
        approval.denial_reason = reason
        approval.decided_at = now
        approval.updated_at = now
        self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Denied CLI command request.",
            subject_id=approval.id,
            actor=decided_by or "system",
            metadata={"reason": reason} if reason else {},
        )
        return approval

    def execute_approved_command(self, approval_id: str) -> CommandExecutionResult:
        approval = self._get_approval_or_raise(approval_id)
        if approval.status != CommandApprovalStatus.approved:
            raise PermissionError(
                f"Approval {approval_id} is not executable; current status is {approval.status}."
            )

        request = CommandExecutionRequest(
            command=approval.command,
            cwd=approval.cwd,
            timeout_seconds=approval.timeout_seconds,
            approved=True,
            requested_by=approval.requested_by,
            agent_id=approval.agent_id,
            agent_role=approval.agent_role,
            task_id=approval.task_id,
        )
        result, run = self._execute_request(request, approval_id=approval.id)

        now = datetime.now(UTC)
        approval.status = CommandApprovalStatus.executed
        approval.run_id = run.id
        approval.executed_at = now
        approval.updated_at = now
        self._approvals.upsert(approval)
        return result

    def execute_command(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        result, _run = self._execute_request(request, approval_id=None)
        return result

    def start_command(self, request: CommandExecutionRequest) -> CommandRun:
        decision, cwd = self._authorize_request(request)
        env, environment_keys = build_command_environment(request.environment)
        started_at = datetime.now(UTC)
        process = subprocess.Popen(
            _command_args(decision.command),
            env=env,
            **_popen_kwargs(cwd),
        )
        run = CommandRun(
            id=f"cmdrun-{uuid4()}",
            command=decision.command,
            cwd=cwd,
            status=CommandRunStatus.running,
            process_id=process.pid,
            permission_mode=decision.permission_mode,
            duration_ms=0,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
            started_at=started_at,
        )
        self._runs.upsert(run)
        with self._active_lock:
            self._active_processes[run.id] = process

        event_log.record(
            LogEventType.cli,
            "Started asynchronous CLI command run.",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "process_id": run.process_id,
                "permission_mode": run.permission_mode,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
                "environment_keys": run.environment_keys,
            },
        )
        Thread(
            target=self._wait_for_process,
            args=(run.id, process, request.timeout_seconds, started_at),
            daemon=True,
        ).start()
        return run

    def get_command_run(self, run_id: str) -> CommandRun | None:
        return self._runs.get(run_id)

    def cancel_command_run(self, run_id: str) -> CommandRun:
        run = self._get_run_or_raise(run_id)
        if run.status != CommandRunStatus.running:
            raise ValueError(
                f"Only running commands can be cancelled; current status is {run.status}."
            )

        with self._active_lock:
            process = self._active_processes.get(run_id)
            self._cancelled_run_ids.add(run_id)

        if process is None:
            with self._active_lock:
                self._cancelled_run_ids.discard(run_id)
            raise ValueError(
                "Command run is marked running but is not cancellable in this process."
            )

        _terminate_process_tree(process)
        now = datetime.now(UTC)
        run.status = CommandRunStatus.cancelled
        run.exit_code = process.returncode if process.returncode is not None else -1
        run.stderr = "Command cancellation requested."
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
        run.cancelled_at = now
        run.completed_at = now
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Cancellation requested for CLI command run.",
            subject_id=run.id,
            metadata={
                "process_id": run.process_id,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
            },
        )
        return run

    def list_approvals(
        self,
        status: CommandApprovalStatus | str | None = None,
    ) -> list[CommandApproval]:
        approvals = self._approvals.list()
        if status is None:
            return approvals
        requested_status = CommandApprovalStatus(status)
        return [approval for approval in approvals if approval.status == requested_status]

    def list_command_runs(self) -> list[CommandRun]:
        return self._runs.list()

    def _authorize_request(
        self,
        request: CommandExecutionRequest,
    ) -> tuple[CommandPolicyDecision, Path]:
        decision = evaluate_command_policy(
            CommandPolicyRequest(
                command=request.command,
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
        )
        if decision.permission_mode == PermissionMode.blocked:
            raise PermissionError(decision.reason)
        if decision.permission_mode == PermissionMode.approval_required and not request.approved:
            raise PermissionError("Command requires explicit approval before execution.")
        return decision, resolve_command_cwd(request.cwd)

    def _execute_request(
        self,
        request: CommandExecutionRequest,
        *,
        approval_id: str | None,
    ) -> tuple[CommandExecutionResult, CommandRun]:
        decision, cwd = self._authorize_request(request)
        env, environment_keys = build_command_environment(request.environment)
        started_at = datetime.now(UTC)
        try:
            completed = subprocess.run(
                _command_args(decision.command),
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
            stderr = _text_output(exc.stderr)
            timeout_message = f"Command timed out after {request.timeout_seconds} seconds."
            stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
            self._record_run(
                command=decision.command,
                cwd=cwd,
                approval_id=approval_id,
                exit_code=-1,
                stdout=_text_output(exc.stdout),
                stderr=stderr,
                permission_mode=decision.permission_mode,
                duration_ms=duration_ms,
                started_at=started_at,
                status=CommandRunStatus.timed_out,
                requested_by=request.requested_by,
                agent_id=request.agent_id,
                agent_role=request.agent_role,
                task_id=request.task_id,
                environment_keys=environment_keys,
            )
            raise

        duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        return self._record_run(
            command=decision.command,
            cwd=cwd,
            approval_id=approval_id,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            permission_mode=decision.permission_mode,
            duration_ms=duration_ms,
            started_at=started_at,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
        )

    def _record_run(
        self,
        *,
        command: str,
        cwd: Path,
        approval_id: str | None,
        exit_code: int,
        stdout: str,
        stderr: str,
        permission_mode: PermissionMode,
        duration_ms: int,
        started_at: datetime,
        status: CommandRunStatus = CommandRunStatus.completed,
        requested_by: str | None = None,
        agent_id: str | None = None,
        agent_role: str | None = None,
        task_id: str | None = None,
        environment_keys: list[str] | None = None,
    ) -> tuple[CommandExecutionResult, CommandRun]:
        environment_keys = environment_keys or []
        sanitized_stdout, stdout_truncated = sanitize_output(
            stdout,
            max_chars=self.max_output_chars,
        )
        sanitized_stderr, stderr_truncated = sanitize_output(
            stderr,
            max_chars=self.max_output_chars,
        )
        completed_at = datetime.now(UTC)
        run = CommandRun(
            id=f"cmdrun-{uuid4()}",
            approval_id=approval_id,
            command=command,
            cwd=cwd,
            status=status,
            exit_code=exit_code,
            stdout=sanitized_stdout,
            stderr=sanitized_stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            permission_mode=permission_mode,
            duration_ms=duration_ms,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
            environment_keys=environment_keys,
            started_at=started_at,
            completed_at=completed_at,
        )
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Recorded CLI command run.",
            subject_id=run.id,
            metadata={
                "approval_id": approval_id,
                "command": redact_sensitive_values(command),
                "cwd": str(cwd),
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "permission_mode": permission_mode,
                "requested_by": requested_by,
                "agent_id": agent_id,
                "agent_role": agent_role,
                "task_id": task_id,
                "environment_keys": environment_keys,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )
        result = CommandExecutionResult(
            command=command,
            cwd=cwd,
            exit_code=exit_code,
            stdout=sanitized_stdout,
            stderr=sanitized_stderr,
            permission_mode=permission_mode,
            duration_ms=duration_ms,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
            environment_keys=environment_keys,
        )
        return result, run

    def _wait_for_process(
        self,
        run_id: str,
        process: subprocess.Popen,
        timeout_seconds: int,
        started_at: datetime,
    ) -> None:
        status = CommandRunStatus.completed
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stdout = _text_output(exc.stdout)
            stderr = _text_output(exc.stderr)
            with self._active_lock:
                was_cancelled = run_id in self._cancelled_run_ids
            if was_cancelled:
                status = CommandRunStatus.cancelled
            else:
                status = CommandRunStatus.timed_out
            if process.poll() is None:
                process.kill()
            timeout_stdout, timeout_stderr = process.communicate()
            stdout = f"{stdout}{_text_output(timeout_stdout)}"
            stderr = f"{stderr}{_text_output(timeout_stderr)}"
            if was_cancelled:
                cancel_message = "Command was cancelled."
                stderr = f"{stderr}\n{cancel_message}" if stderr else cancel_message
            else:
                timeout_message = f"Command timed out after {timeout_seconds} seconds."
                stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
        else:
            with self._active_lock:
                was_cancelled = run_id in self._cancelled_run_ids
            if was_cancelled:
                status = CommandRunStatus.cancelled

        with self._active_lock:
            self._active_processes.pop(run_id, None)
            self._cancelled_run_ids.discard(run_id)

        exit_code = process.returncode
        if exit_code is None:
            exit_code = -1
        duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        self._finalize_async_run(
            run_id=run_id,
            exit_code=exit_code,
            stdout=_text_output(stdout),
            stderr=_text_output(stderr),
            status=status,
            duration_ms=duration_ms,
        )

    def _finalize_async_run(
        self,
        *,
        run_id: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        status: CommandRunStatus,
        duration_ms: int,
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return

        sanitized_stdout, stdout_truncated = sanitize_output(
            stdout,
            max_chars=self.max_output_chars,
        )
        sanitized_stderr, stderr_truncated = sanitize_output(
            stderr,
            max_chars=self.max_output_chars,
        )
        completed_at = datetime.now(UTC)
        run.status = status
        run.exit_code = exit_code
        run.stdout = sanitized_stdout
        run.stderr = sanitized_stderr
        run.stdout_truncated = stdout_truncated
        run.stderr_truncated = stderr_truncated
        run.duration_ms = duration_ms
        run.completed_at = completed_at
        if status == CommandRunStatus.cancelled and run.cancelled_at is None:
            run.cancelled_at = completed_at
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Finalized asynchronous CLI command run.",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "permission_mode": run.permission_mode,
                "status": run.status,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
                "environment_keys": run.environment_keys,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )

    def _get_approval_or_raise(self, approval_id: str) -> CommandApproval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"Command approval not found: {approval_id}")
        return approval

    def _get_run_or_raise(self, run_id: str) -> CommandRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"Command run not found: {run_id}")
        return run


cli_runtime_service = CliRuntimeService()
