import os
import re
import shlex
import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from dgentic.events import event_log
from dgentic.guardrails import evaluate_command_policy
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandExecutionResult,
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


class CommandApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    executed = "executed"


class CommandApproval(BaseModel):
    id: str
    command: str
    cwd: Path
    timeout_seconds: int
    permission_mode: PermissionMode = PermissionMode.approval_required
    policy_reason: str
    status: CommandApprovalStatus = CommandApprovalStatus.pending
    requested_by: str | None = None
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
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    permission_mode: PermissionMode
    duration_ms: int
    started_at: datetime
    completed_at: datetime


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

    def create_approval(
        self,
        request: CommandExecutionRequest,
        *,
        requested_by: str | None = None,
    ) -> CommandApproval:
        decision = evaluate_command_policy(CommandPolicyRequest(command=request.command))
        if decision.permission_mode == PermissionMode.blocked:
            raise PermissionError(decision.reason)
        if decision.permission_mode != PermissionMode.approval_required:
            raise ValueError("Only approval-required commands can be queued for approval.")

        approval = CommandApproval(
            id=f"approval-{uuid4()}",
            command=decision.command,
            cwd=resolve_command_cwd(request.cwd),
            timeout_seconds=request.timeout_seconds,
            permission_mode=decision.permission_mode,
            policy_reason=decision.reason,
            requested_by=requested_by,
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

    def _execute_request(
        self,
        request: CommandExecutionRequest,
        *,
        approval_id: str | None,
    ) -> tuple[CommandExecutionResult, CommandRun]:
        decision = evaluate_command_policy(CommandPolicyRequest(command=request.command))
        if decision.permission_mode == PermissionMode.blocked:
            raise PermissionError(decision.reason)
        if decision.permission_mode == PermissionMode.approval_required and not request.approved:
            raise PermissionError("Command requires explicit approval before execution.")

        cwd = resolve_command_cwd(request.cwd)
        started_at = datetime.now(UTC)
        try:
            completed = subprocess.run(
                _command_args(decision.command),
                cwd=cwd,
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
    ) -> tuple[CommandExecutionResult, CommandRun]:
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
            exit_code=exit_code,
            stdout=sanitized_stdout,
            stderr=sanitized_stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            permission_mode=permission_mode,
            duration_ms=duration_ms,
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
        )
        return result, run

    def _get_approval_or_raise(self, approval_id: str) -> CommandApproval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"Command approval not found: {approval_id}")
        return approval


cli_runtime_service = CliRuntimeService()
