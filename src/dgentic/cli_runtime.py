import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Lock, Thread
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from dgentic.command_policy import parse_command, parse_inner_shell_command
from dgentic.events import event_log
from dgentic.guardrails import evaluate_command_policy
from dgentic.redaction import REDACTED_SECRET_MARKER, redact_sensitive_values
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
DEFAULT_MAX_OUTPUT_CHUNKS = 200
DEFAULT_APPROVAL_TTL_MINUTES = 30
TRUNCATION_MARKER = "\n[output truncated]"
APPROVAL_DIGEST_PREFIX = "hmac-sha256:"
REDACTED_LEGACY_DIGEST_MARKER = "[LEGACY_DIGEST_REDACTED]"
_APPROVAL_DIGEST_KEY_FILE = "cli-approval-digest.key"
_DIGEST_KEY_LOCK = Lock()
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
    starting = "starting"
    running = "running"
    completed = "completed"
    failed = "failed"
    timed_out = "timed_out"
    cancelled = "cancelled"
    stale = "stale"


class OrphanTerminationStatus(StrEnum):
    skipped = "skipped"
    terminated = "terminated"
    not_found = "not_found"
    failed = "failed"


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    identity: str


class CommandOutputChunk(BaseModel):
    sequence: int
    stream: Literal["stdout", "stderr"]
    text: str
    truncated: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommandApproval(BaseModel):
    id: str
    command: str
    review_command: str = ""
    command_digest: str = ""
    environment_digest: str = ""
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
    matched_rule_id: str | None = None
    matched_rule_name: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    run_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=DEFAULT_APPROVAL_TTL_MINUTES)
    )
    decided_at: datetime | None = None
    executed_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        redacted_command = redact_sensitive_values(self.command)
        self.command = redacted_command
        self.review_command = redact_sensitive_values(self.review_command or redacted_command)
        self.decision_reason = _redact_optional_sensitive_text(self.decision_reason)
        self.denial_reason = _redact_optional_sensitive_text(self.denial_reason)
        self.command_digest = _sanitize_approval_digest(self.command_digest)
        self.environment_digest = _sanitize_approval_digest(self.environment_digest)


class CommandApprovalReview(BaseModel):
    id: str
    status: CommandApprovalStatus
    review_command: str
    cwd: Path
    timeout_seconds: int
    permission_mode: PermissionMode
    policy_reason: str
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    environment_keys: list[str] = Field(default_factory=list)
    matched_rule_id: str | None = None
    matched_rule_name: str | None = None
    command_digest: str = ""
    environment_digest: str = ""
    requires_bound_execution_request: bool = False
    direct_execute_available: bool = False
    review_warnings: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    run_id: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
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
    output_chunks: list[CommandOutputChunk] = Field(default_factory=list)
    last_output_at: datetime | None = None
    permission_mode: PermissionMode
    duration_ms: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    environment_keys: list[str] = Field(default_factory=list)
    supervisor_id: str | None = None
    supervisor_pid: int | None = None
    process_group_id: int | None = None
    process_identity: str | None = None
    process_started_at: datetime | None = None
    timeout_at: datetime | None = None
    status_reason: str | None = None
    stale_reason: str | None = None
    termination_attempted_at: datetime | None = None
    termination_completed_at: datetime | None = None
    termination_status: OrphanTerminationStatus | None = None
    termination_reason: str | None = None
    terminated_by_supervisor_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    last_heartbeat_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        self.command = redact_sensitive_values(self.command)


class CommandRunOutput(BaseModel):
    run_id: str
    status: CommandRunStatus
    chunks: list[CommandOutputChunk] = Field(default_factory=list)
    next_sequence: int


def _redact_optional_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    return redact_sensitive_values(text)


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
    parsed = parse_command(command)
    if parsed.executable in {"cmd", "cmd.exe"}:
        inner_command = parse_inner_shell_command(command)
        if inner_command is not None:
            return ["sh", "-c", inner_command]
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


def normalize_command_environment_overrides(overrides: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in overrides.items():
        normalized_key = key.strip()
        if not _ENV_NAME_RE.fullmatch(normalized_key):
            raise ValueError(f"Invalid environment variable name: {key}")
        upper_key = normalized_key.upper()
        if upper_key in _BLOCKED_ENV_OVERRIDES:
            raise ValueError(f"Environment variable override is not allowed: {normalized_key}")
        if len(value) > 4096:
            raise ValueError(f"Environment variable value is too long: {normalized_key}")
        normalized[normalized_key] = value
    return normalized


def build_command_environment(overrides: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    env = _base_command_environment()
    normalized_overrides = normalize_command_environment_overrides(overrides)
    env.update(normalized_overrides)
    return env, sorted(normalized_overrides)


def validate_command_environment(overrides: dict[str, str]) -> list[str]:
    _env, environment_keys = build_command_environment(overrides)
    return environment_keys


def _approval_digest_key() -> bytes:
    settings = get_settings()
    configured_key = settings.approval_digest_key.strip()
    if configured_key:
        return configured_key.encode("utf-8")

    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = settings.root_dir / data_dir
    key_path = data_dir / _APPROVAL_DIGEST_KEY_FILE
    with _DIGEST_KEY_LOCK:
        if key_path.exists():
            stored_key = key_path.read_text(encoding="utf-8").strip()
            if stored_key:
                return stored_key.encode("utf-8")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        generated_key = secrets.token_hex(32)
        key_path.write_text(generated_key + "\n", encoding="utf-8")
        return generated_key.encode("utf-8")


def _approval_hmac_digest(encoded_payload: str) -> str:
    digest = hmac.new(
        _approval_digest_key(),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{APPROVAL_DIGEST_PREFIX}{digest}"


def _sanitize_approval_digest(digest: str) -> str:
    if not digest:
        return ""
    if digest.startswith(APPROVAL_DIGEST_PREFIX):
        return digest
    return REDACTED_LEGACY_DIGEST_MARKER


def command_environment_digest(overrides: dict[str, str]) -> str:
    normalized_overrides = normalize_command_environment_overrides(overrides)
    encoded = json.dumps(normalized_overrides, sort_keys=True, separators=(",", ":"))
    return _approval_hmac_digest(encoded)


def approval_boolean_bypass_allowed() -> bool:
    return get_settings().environment.strip().lower() in {"development", "test", "testing"}


def _approval_binding_payload(
    *,
    command: str,
    cwd: Path,
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    environment_keys: list[str],
    environment_digest: str,
    permission_mode: PermissionMode,
    matched_rule_id: str | None,
    matched_rule_name: str | None,
) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "agent_role": agent_role,
        "command": command.strip(),
        "cwd": str(cwd),
        "environment_digest": environment_digest,
        "environment_keys": sorted(environment_keys),
        "matched_rule_id": matched_rule_id,
        "matched_rule_name": matched_rule_name,
        "permission_mode": permission_mode,
        "requested_by": requested_by,
        "task_id": task_id,
        "timeout_seconds": timeout_seconds,
    }


def command_approval_digest(
    *,
    command: str,
    cwd: Path,
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    environment_keys: list[str],
    environment_digest: str,
    permission_mode: PermissionMode,
    matched_rule_id: str | None,
    matched_rule_name: str | None,
) -> str:
    payload = _approval_binding_payload(
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        environment_keys=environment_keys,
        environment_digest=environment_digest,
        permission_mode=permission_mode,
        matched_rule_id=matched_rule_id,
        matched_rule_name=matched_rule_name,
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return _approval_hmac_digest(encoded)


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
    try:
        process.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass

    if process.pid is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _process_snapshot(pid: int | None) -> ProcessSnapshot | None:
    if pid is None or pid <= 0:
        return None
    if os.name == "nt":
        return _windows_process_snapshot(pid)
    return _posix_process_snapshot(pid)


def _posix_process_snapshot(pid: int) -> ProcessSnapshot | None:
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        stat_text = stat_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        _prefix, fields_text = stat_text.rsplit(") ", 1)
        fields = fields_text.split()
        start_ticks = fields[19]
    except (IndexError, ValueError):
        return None
    return ProcessSnapshot(pid=pid, identity=f"posix-proc-start:{start_ticks}")


def _windows_process_snapshot(pid: int) -> ProcessSnapshot | None:
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, AttributeError):
        return None

    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return None
    try:
        creation_time = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        ok = ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation_time),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        if not ok:
            return None
        created_at = (creation_time.dwHighDateTime << 32) + creation_time.dwLowDateTime
        return ProcessSnapshot(pid=pid, identity=f"windows-created:{created_at}")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _status_reason_for_terminal_async_run(status: CommandRunStatus) -> str:
    if status == CommandRunStatus.completed:
        return "Command process completed."
    if status == CommandRunStatus.cancelled:
        return "Command process was cancelled."
    if status == CommandRunStatus.timed_out:
        return "Command process timed out."
    if status == CommandRunStatus.failed:
        return "Command process failed."
    if status == CommandRunStatus.stale:
        return "Command process supervision was lost."
    return f"Command process reached status {status}."


class CliRuntimeService:
    def __init__(self, max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> None:
        self.max_output_chars = max_output_chars
        self.supervisor_id = f"cli-supervisor-{uuid4()}"
        self._approvals = JsonCollection("cli-approvals", CommandApproval)
        self._runs = JsonCollection("cli-command-runs", CommandRun)
        self._active_processes: dict[str, subprocess.Popen] = {}
        self._cancelled_run_ids: set[str] = set()
        self._active_lock = Lock()
        self.reconcile_stale_command_runs()

    def create_approval(
        self,
        request: CommandExecutionRequest,
        *,
        requested_by: str | None = None,
    ) -> CommandApproval:
        cwd = resolve_command_cwd(request.cwd)
        requested_by_value = requested_by or request.requested_by
        decision = evaluate_command_policy(
            CommandPolicyRequest(
                command=request.command,
                cwd=cwd,
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            ),
            actor=requested_by_value,
        )
        if decision.permission_mode == PermissionMode.blocked:
            raise PermissionError(decision.reason)
        if decision.permission_mode != PermissionMode.approval_required:
            raise ValueError("Only approval-required commands can be queued for approval.")
        environment_keys = validate_command_environment(request.environment)
        environment_digest = command_environment_digest(request.environment)
        command_digest = command_approval_digest(
            command=decision.command,
            cwd=cwd,
            timeout_seconds=request.timeout_seconds,
            requested_by=requested_by_value,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
            environment_digest=environment_digest,
            permission_mode=decision.permission_mode,
            matched_rule_id=decision.matched_rule_id,
            matched_rule_name=decision.matched_rule_name,
        )
        review_command = redact_sensitive_values(decision.command)

        approval = CommandApproval(
            id=f"approval-{uuid4()}",
            command=review_command,
            review_command=review_command,
            command_digest=command_digest,
            environment_digest=environment_digest,
            cwd=cwd,
            timeout_seconds=request.timeout_seconds,
            permission_mode=decision.permission_mode,
            policy_reason=decision.reason,
            requested_by=requested_by_value,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
            matched_rule_id=decision.matched_rule_id,
            matched_rule_name=decision.matched_rule_name,
        )
        self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Created CLI command approval request.",
            actor=approval.requested_by or "system",
            subject_id=approval.id,
            metadata={
                "command": redact_sensitive_values(approval.command),
                "review_command": approval.review_command,
                "cwd": str(approval.cwd),
                "permission_mode": approval.permission_mode,
                "requested_by": approval.requested_by,
                "agent_id": approval.agent_id,
                "agent_role": approval.agent_role,
                "task_id": approval.task_id,
                "environment_keys": approval.environment_keys,
                "environment_digest": approval.environment_digest,
                "matched_rule_id": approval.matched_rule_id,
                "matched_rule_name": approval.matched_rule_name,
                "command_digest": approval.command_digest,
                "expires_at": approval.expires_at.isoformat(),
            },
        )
        return approval

    def approve_approval(
        self,
        approval_id: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> CommandApproval:
        approval = self._get_approval_or_raise(approval_id)
        if approval.status != CommandApprovalStatus.pending:
            raise ValueError(
                f"Only pending approvals can be approved; current status is {approval.status}."
            )
        if self._approval_is_expired(approval):
            raise ValueError(f"Approval {approval_id} has expired and cannot be approved.")

        redacted_reason = _redact_optional_sensitive_text(reason)
        now = datetime.now(UTC)
        approval.status = CommandApprovalStatus.approved
        approval.decided_by = decided_by
        approval.decision_reason = redacted_reason
        approval.decided_at = now
        approval.updated_at = now
        self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Approved CLI command request.",
            subject_id=approval.id,
            actor=decided_by or "system",
            metadata={"reason": redacted_reason} if redacted_reason else {},
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

        redacted_reason = _redact_optional_sensitive_text(reason)
        now = datetime.now(UTC)
        approval.status = CommandApprovalStatus.denied
        approval.decided_by = decided_by
        approval.decision_reason = redacted_reason
        approval.denial_reason = redacted_reason
        approval.decided_at = now
        approval.updated_at = now
        self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Denied CLI command request.",
            subject_id=approval.id,
            actor=decided_by or "system",
            metadata={"reason": redacted_reason} if redacted_reason else {},
        )
        return approval

    def get_approval_review(self, approval_id: str) -> CommandApprovalReview:
        approval = self._get_approval_or_raise(approval_id)
        warnings: list[str] = []
        requires_bound_execution_request = False
        if REDACTED_SECRET_MARKER in approval.command:
            requires_bound_execution_request = True
            warnings.append(
                "Approval command is redacted; execute with a bound request that resubmits "
                "the original command."
            )
        if approval.environment_keys:
            requires_bound_execution_request = True
            warnings.append(
                "Approval has environment keys; execute with a bound request that supplies "
                "the same environment keys."
            )
        has_current_binding_digests = True
        if not requires_bound_execution_request:
            has_current_binding_digests = self._approval_has_current_binding_digests(approval)
        if not has_current_binding_digests:
            warnings.append(
                "Approval has legacy or invalid binding digests; direct execution is unavailable."
            )
        direct_execute_available = (
            approval.status == CommandApprovalStatus.approved
            and not requires_bound_execution_request
            and has_current_binding_digests
            and not self._approval_is_expired(approval)
        )
        if self._approval_is_expired(approval):
            warnings.append("Approval is expired.")
        return CommandApprovalReview(
            id=approval.id,
            status=approval.status,
            review_command=approval.review_command,
            cwd=approval.cwd,
            timeout_seconds=approval.timeout_seconds,
            permission_mode=approval.permission_mode,
            policy_reason=approval.policy_reason,
            requested_by=approval.requested_by,
            agent_id=approval.agent_id,
            agent_role=approval.agent_role,
            task_id=approval.task_id,
            environment_keys=approval.environment_keys,
            matched_rule_id=approval.matched_rule_id,
            matched_rule_name=approval.matched_rule_name,
            command_digest=approval.command_digest,
            environment_digest=approval.environment_digest,
            requires_bound_execution_request=requires_bound_execution_request,
            direct_execute_available=direct_execute_available,
            review_warnings=warnings,
            decided_by=approval.decided_by,
            decision_reason=_redact_optional_sensitive_text(approval.decision_reason),
            denial_reason=_redact_optional_sensitive_text(approval.denial_reason),
            run_id=approval.run_id,
            created_at=approval.created_at,
            updated_at=approval.updated_at,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
            executed_at=approval.executed_at,
        )

    def _approval_has_current_binding_digests(self, approval: CommandApproval) -> bool:
        if not approval.command_digest.startswith(APPROVAL_DIGEST_PREFIX):
            return False
        if not approval.environment_digest.startswith(APPROVAL_DIGEST_PREFIX):
            return False
        expected_environment_digest = command_environment_digest({})
        if (
            not approval.environment_keys
            and approval.environment_digest != expected_environment_digest
        ):
            return False
        expected_command_digest = command_approval_digest(
            command=approval.command,
            cwd=approval.cwd,
            timeout_seconds=approval.timeout_seconds,
            requested_by=approval.requested_by,
            agent_id=approval.agent_id,
            agent_role=approval.agent_role,
            task_id=approval.task_id,
            environment_keys=approval.environment_keys,
            environment_digest=approval.environment_digest,
            permission_mode=approval.permission_mode,
            matched_rule_id=approval.matched_rule_id,
            matched_rule_name=approval.matched_rule_name,
        )
        return approval.command_digest == expected_command_digest

    def execute_approved_command(
        self,
        approval_id: str,
        *,
        actor: str | None = None,
        allow_cross_actor: bool = False,
    ) -> CommandExecutionResult:
        approval = self._get_approval_or_raise(approval_id)
        if (
            actor is not None
            and approval.requested_by is not None
            and actor != approval.requested_by
            and not allow_cross_actor
        ):
            raise PermissionError(f"Approval {approval_id} is bound to a different requester.")
        if approval.status != CommandApprovalStatus.approved:
            raise PermissionError(
                f"Approval {approval_id} is not executable; current status is {approval.status}."
            )
        if self._approval_is_expired(approval):
            raise PermissionError(f"Approval {approval_id} has expired and cannot be executed.")
        if REDACTED_SECRET_MARKER in approval.command:
            raise PermissionError(
                "Approval command is redacted; execute with approval_id and matching command "
                "through /cli/execute or /cli/runs."
            )
        if approval.environment_keys:
            raise PermissionError(
                "Approval includes environment keys; execute with approval_id and matching "
                "environment keys through /cli/execute or /cli/runs."
            )
        if not self._approval_has_current_binding_digests(approval):
            raise PermissionError(
                f"Approval {approval_id} has legacy or invalid binding digests and cannot "
                "be directly executed."
            )

        request = CommandExecutionRequest(
            command=approval.command,
            cwd=approval.cwd,
            timeout_seconds=approval.timeout_seconds,
            approval_id=approval.id,
            requested_by=approval.requested_by,
            agent_id=approval.agent_id,
            agent_role=approval.agent_role,
            task_id=approval.task_id,
        )
        return self.execute_command(request, actor=actor or approval.requested_by)

    def execute_command(
        self,
        request: CommandExecutionRequest,
        *,
        actor: str | None = None,
    ) -> CommandExecutionResult:
        result, run = self._execute_request(request, actor=actor)
        if run.approval_id is not None:
            self._mark_approval_executed(
                run.approval_id,
                run.id,
                actor=actor or request.requested_by,
            )
        return result

    def start_command(self, request: CommandExecutionRequest) -> CommandRun:
        decision, cwd, env, environment_keys, approval_id = self._prepare_request(request)
        started_at = datetime.now(UTC)
        run = CommandRun(
            id=f"cmdrun-{uuid4()}",
            approval_id=approval_id,
            command=decision.command,
            cwd=cwd,
            status=CommandRunStatus.starting,
            permission_mode=decision.permission_mode,
            duration_ms=0,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
            supervisor_id=self.supervisor_id,
            supervisor_pid=os.getpid(),
            timeout_at=started_at + timedelta(seconds=request.timeout_seconds),
            status_reason="Command launch requested.",
            started_at=started_at,
            last_heartbeat_at=started_at,
        )
        self._runs.upsert(run)
        if approval_id is not None:
            self._mark_approval_executed(approval_id, run.id, actor=run.requested_by)

        event_log.record(
            LogEventType.cli,
            "Recorded asynchronous CLI command launch intent.",
            actor=run.requested_by or "system",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "supervisor_id": run.supervisor_id,
                "supervisor_pid": run.supervisor_pid,
                "timeout_at": run.timeout_at.isoformat() if run.timeout_at else None,
                "permission_mode": run.permission_mode,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
                "environment_keys": run.environment_keys,
            },
        )

        try:
            process = subprocess.Popen(
                _command_args(decision.command),
                env=env,
                **_popen_kwargs(cwd),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._mark_run_failed(run, reason=f"Command launch failed: {exc}")
            raise

        with self._active_lock:
            self._active_processes[run.id] = process
            current_run = self._runs.get(run.id)
            if current_run is None or current_run.status != CommandRunStatus.starting:
                self._active_processes.pop(run.id, None)
                _terminate_process_tree(process)
                if current_run is not None:
                    return current_run
                return self._mark_run_stale(
                    run,
                    reason="Command launch completed, but persisted launch intent was missing.",
                )

            now = datetime.now(UTC)
            process_snapshot = _process_snapshot(process.pid)
            current_run.status = CommandRunStatus.running
            current_run.process_id = process.pid
            current_run.process_group_id = process.pid if os.name != "nt" else None
            current_run.process_identity = (
                process_snapshot.identity if process_snapshot is not None else None
            )
            current_run.process_started_at = now
            current_run.status_reason = "Command process started."
            current_run.last_heartbeat_at = now
            self._runs.upsert(current_run)
            run = current_run

        event_log.record(
            LogEventType.cli,
            "Started asynchronous CLI command run.",
            actor=run.requested_by or "system",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "process_id": run.process_id,
                "process_group_id": run.process_group_id,
                "process_identity": run.process_identity,
                "process_started_at": (
                    run.process_started_at.isoformat() if run.process_started_at else None
                ),
                "supervisor_id": run.supervisor_id,
                "supervisor_pid": run.supervisor_pid,
                "timeout_at": run.timeout_at.isoformat() if run.timeout_at else None,
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

    def get_command_run_output(self, run_id: str, after_sequence: int = 0) -> CommandRunOutput:
        if after_sequence < 0:
            raise ValueError("after_sequence must be greater than or equal to 0.")

        run = self._get_run_or_raise(run_id)
        chunks = [chunk for chunk in run.output_chunks if chunk.sequence > after_sequence]
        next_sequence = chunks[-1].sequence if chunks else after_sequence
        return CommandRunOutput(
            run_id=run.id,
            status=run.status,
            chunks=chunks,
            next_sequence=next_sequence,
        )

    def cancel_command_run(self, run_id: str, *, actor: str | None = None) -> CommandRun:
        run = self._get_run_or_raise(run_id)
        if run.status not in {CommandRunStatus.starting, CommandRunStatus.running}:
            raise ValueError(
                "Only starting or running commands can be cancelled; "
                f"current status is {run.status}."
            )

        with self._active_lock:
            process = self._active_processes.get(run_id)
            self._cancelled_run_ids.add(run_id)
            current_run = self._runs.get(run_id)
            if current_run is None:
                self._cancelled_run_ids.discard(run_id)
                raise KeyError(f"Command run not found: {run_id}")
            if current_run.status not in {
                CommandRunStatus.starting,
                CommandRunStatus.running,
            }:
                self._cancelled_run_ids.discard(run_id)
                raise ValueError(
                    "Only starting or running commands can be cancelled; "
                    f"current status is {current_run.status}."
                )
            run = current_run

        if process is None:
            with self._active_lock:
                self._cancelled_run_ids.discard(run_id)
            if run.status == CommandRunStatus.starting and run.supervisor_id == self.supervisor_id:
                raise ValueError(
                    "Command launch is still starting and cannot be cancelled until "
                    "process registration completes."
                )
            if run.supervisor_id == self.supervisor_id:
                raise ValueError(
                    "Command run is not currently cancellable in this backend process; "
                    "it may be starting or finalizing."
                )
            return self._reconcile_orphaned_run(
                run,
                reason=f"Cancellation requested, but {self._orphaned_run_reason(run)}",
            )

        _terminate_process_tree(process)
        now = datetime.now(UTC)
        run.status = CommandRunStatus.cancelled
        run.exit_code = process.returncode if process.returncode is not None else -1
        run.stderr = "Command cancellation requested."
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
        run.cancelled_at = now
        run.completed_at = now
        run.last_heartbeat_at = now
        run.status_reason = "Command cancellation requested."
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Cancellation requested for CLI command run.",
            actor=actor or run.requested_by or "system",
            subject_id=run.id,
            metadata={
                "process_id": run.process_id,
                "supervisor_id": run.supervisor_id,
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

    def reconcile_stale_command_runs(self) -> list[CommandRun]:
        reconciled: list[CommandRun] = []
        for run in self._runs.list():
            if run.status not in {CommandRunStatus.starting, CommandRunStatus.running}:
                continue
            with self._active_lock:
                is_active = run.id in self._active_processes
            if is_active:
                continue

            reconciled.append(
                self._reconcile_orphaned_run(
                    run,
                    reason=f"Command run was marked stale because {self._orphaned_run_reason(run)}",
                )
            )
        return reconciled

    def _orphaned_run_reason(self, run: CommandRun) -> str:
        if run.status == CommandRunStatus.starting:
            return "launch did not complete before backend supervision was interrupted."
        if not run.supervisor_id:
            return "it has no persisted supervisor metadata from an older backend version."
        if run.supervisor_id != self.supervisor_id:
            return (
                "it belongs to a previous backend supervisor and cannot be adopted by the "
                "current process."
            )
        return "no active process is registered in this backend process."

    def _reconcile_orphaned_run(self, run: CommandRun, *, reason: str) -> CommandRun:
        self._record_orphan_termination_attempt(run)
        return self._mark_run_stale(run, reason=reason)

    def _record_orphan_termination_attempt(self, run: CommandRun) -> None:
        now = datetime.now(UTC)
        run.termination_attempted_at = now
        run.terminated_by_supervisor_id = self.supervisor_id

        if run.status != CommandRunStatus.running:
            run.termination_status = OrphanTerminationStatus.skipped
            run.termination_reason = "Termination skipped because the run is not running."
            run.termination_completed_at = datetime.now(UTC)
            return
        if run.process_id is None:
            run.termination_status = OrphanTerminationStatus.skipped
            run.termination_reason = "Termination skipped because no process id was persisted."
            run.termination_completed_at = datetime.now(UTC)
            return
        if not run.process_identity:
            run.termination_status = OrphanTerminationStatus.skipped
            run.termination_reason = (
                "Termination skipped because process identity was not persisted."
            )
            run.termination_completed_at = datetime.now(UTC)
            return

        snapshot = _process_snapshot(run.process_id)
        if snapshot is None:
            run.termination_status = OrphanTerminationStatus.not_found
            run.termination_reason = (
                "Orphan process was not found or process identity could not be inspected."
            )
            run.termination_completed_at = datetime.now(UTC)
            return
        if snapshot.identity != run.process_identity:
            run.termination_status = OrphanTerminationStatus.skipped
            run.termination_reason = "Termination skipped because process identity did not match."
            run.termination_completed_at = datetime.now(UTC)
            return

        try:
            self._terminate_orphaned_process(run)
        except (OSError, subprocess.SubprocessError) as exc:
            sanitized_reason, _truncated = sanitize_output(
                f"Orphan process termination failed: {exc}",
                max_chars=self.max_output_chars,
            )
            run.termination_status = OrphanTerminationStatus.failed
            run.termination_reason = sanitized_reason
        else:
            run.termination_status = OrphanTerminationStatus.terminated
            run.termination_reason = (
                "Matching orphan process termination was requested before marking stale."
            )
        run.termination_completed_at = datetime.now(UTC)

    def _terminate_orphaned_process(self, run: CommandRun) -> None:
        if run.process_id is None:
            return
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(run.process_id), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if completed.returncode != 0:
                message = completed.stderr.strip() or completed.stdout.strip()
                raise OSError(message or f"taskkill failed with exit code {completed.returncode}.")
            return

        process_group_id = run.process_group_id or run.process_id
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            return
        time.sleep(0.2)
        snapshot = _process_snapshot(run.process_id)
        if snapshot is None or snapshot.identity != run.process_identity:
            return
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            return

    def _mark_run_stale(self, run: CommandRun, *, reason: str) -> CommandRun:
        now = datetime.now(UTC)
        stderr = f"{run.stderr}\n{reason}" if run.stderr else reason
        sanitized_stderr, stderr_truncated = sanitize_output(
            stderr,
            max_chars=self.max_output_chars,
        )
        run.status = CommandRunStatus.stale
        run.exit_code = -1
        run.stderr = sanitized_stderr
        run.stderr_truncated = run.stderr_truncated or stderr_truncated
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
        run.completed_at = now
        run.last_heartbeat_at = now
        run.status_reason = reason
        run.stale_reason = reason
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Reconciled stale CLI command run.",
            actor=run.requested_by or "system",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "process_id": run.process_id,
                "supervisor_id": run.supervisor_id,
                "supervisor_pid": run.supervisor_pid,
                "status": run.status,
                "status_reason": run.status_reason,
                "stale_reason": run.stale_reason,
                "termination_status": run.termination_status,
                "termination_reason": run.termination_reason,
                "termination_attempted_at": (
                    run.termination_attempted_at.isoformat()
                    if run.termination_attempted_at
                    else None
                ),
                "termination_completed_at": (
                    run.termination_completed_at.isoformat()
                    if run.termination_completed_at
                    else None
                ),
                "terminated_by_supervisor_id": run.terminated_by_supervisor_id,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
            },
        )
        return run

    def _mark_run_failed(self, run: CommandRun, *, reason: str) -> CommandRun:
        now = datetime.now(UTC)
        sanitized_reason, stderr_truncated = sanitize_output(
            reason,
            max_chars=self.max_output_chars,
        )
        run.status = CommandRunStatus.failed
        run.exit_code = -1
        run.stderr = sanitized_reason
        run.stderr_truncated = run.stderr_truncated or stderr_truncated
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
        run.completed_at = now
        run.last_heartbeat_at = now
        run.status_reason = sanitized_reason
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Failed asynchronous CLI command launch.",
            actor=run.requested_by or "system",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "supervisor_id": run.supervisor_id,
                "supervisor_pid": run.supervisor_pid,
                "status": run.status,
                "status_reason": run.status_reason,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
            },
        )
        return run

    def _prepare_request(
        self,
        request: CommandExecutionRequest,
    ) -> tuple[CommandPolicyDecision, Path, dict[str, str], list[str], str | None]:
        cwd = resolve_command_cwd(request.cwd)
        decision = evaluate_command_policy(
            CommandPolicyRequest(
                command=request.command,
                cwd=cwd,
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            ),
            actor=request.requested_by,
        )
        if decision.permission_mode == PermissionMode.blocked:
            raise PermissionError(decision.reason)
        env, environment_keys = build_command_environment(request.environment)
        environment_digest = command_environment_digest(request.environment)
        approval_id: str | None = None
        if decision.permission_mode == PermissionMode.approval_required:
            approval_id = self._authorize_approval_required_request(
                request,
                decision=decision,
                cwd=cwd,
                environment_keys=environment_keys,
                environment_digest=environment_digest,
            )
        elif request.approval_id:
            raise ValueError("approval_id is only valid for approval-required commands.")
        return decision, cwd, env, environment_keys, approval_id

    def _authorize_approval_required_request(
        self,
        request: CommandExecutionRequest,
        *,
        decision: CommandPolicyDecision,
        cwd: Path,
        environment_keys: list[str],
        environment_digest: str,
    ) -> str | None:
        if request.approval_id is not None:
            approval = self._get_approval_or_raise(request.approval_id)
            self._claim_bound_approval(
                approval,
                request=request,
                decision=decision,
                cwd=cwd,
                environment_keys=environment_keys,
                environment_digest=environment_digest,
            )
            return approval.id

        if request.approved and approval_boolean_bypass_allowed():
            return None
        if request.approved:
            raise PermissionError(
                "Command requires an approved approval_id before execution; "
                "the approved boolean bypass is only allowed in development/test mode."
            )
        raise PermissionError("Command requires an approved approval_id before execution.")

    def _execute_request(
        self,
        request: CommandExecutionRequest,
        *,
        actor: str | None = None,
    ) -> tuple[CommandExecutionResult, CommandRun]:
        decision, cwd, env, environment_keys, approval_id = self._prepare_request(request)
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
            _result, run = self._record_run(
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
                actor=actor,
            )
            if run.approval_id is not None:
                self._mark_approval_executed(
                    run.approval_id,
                    run.id,
                    actor=actor or request.requested_by,
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
            actor=actor,
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
        actor: str | None = None,
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
            status_reason=_status_reason_for_terminal_async_run(status),
            started_at=started_at,
            completed_at=completed_at,
            last_heartbeat_at=completed_at,
        )
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Recorded CLI command run.",
            actor=actor or requested_by or "system",
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
            command=redact_sensitive_values(command),
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
        stdout_thread = Thread(
            target=self._read_output_pipe,
            args=(run_id, "stdout", process.stdout),
            daemon=True,
        )
        stderr_thread = Thread(
            target=self._read_output_pipe,
            args=(run_id, "stderr", process.stderr),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            with self._active_lock:
                was_cancelled = run_id in self._cancelled_run_ids
            if was_cancelled:
                status = CommandRunStatus.cancelled
            else:
                status = CommandRunStatus.timed_out
            if process.poll() is None:
                _terminate_process_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if was_cancelled:
                self._append_output_chunk(run_id, "stderr", "Command was cancelled.")
            else:
                self._append_output_chunk(
                    run_id,
                    "stderr",
                    f"Command timed out after {timeout_seconds} seconds.",
                )
        else:
            with self._active_lock:
                was_cancelled = run_id in self._cancelled_run_ids
            if was_cancelled:
                status = CommandRunStatus.cancelled

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        with self._active_lock:
            self._active_processes.pop(run_id, None)
            self._cancelled_run_ids.discard(run_id)

        exit_code = process.returncode
        if exit_code is None:
            exit_code = -1
        if status == CommandRunStatus.completed and exit_code != 0:
            status = CommandRunStatus.failed
        duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        self._finalize_async_run(
            run_id=run_id,
            exit_code=exit_code,
            status=status,
            duration_ms=duration_ms,
        )

    def _read_output_pipe(
        self,
        run_id: str,
        stream: Literal["stdout", "stderr"],
        pipe,
    ) -> None:
        if pipe is None:
            return
        for chunk in iter(pipe.readline, ""):
            self._append_output_chunk(run_id, stream, _text_output(chunk))
        tail = pipe.read()
        if tail:
            self._append_output_chunk(run_id, stream, _text_output(tail))

    def _append_output_chunk(
        self,
        run_id: str,
        stream: Literal["stdout", "stderr"],
        text: str,
    ) -> None:
        if not text:
            return

        sanitized_text, chunk_truncated = sanitize_output(
            text,
            max_chars=self.max_output_chars,
        )
        if not sanitized_text:
            return

        with self._active_lock:
            run = self._runs.get(run_id)
            if run is None:
                return

            now = datetime.now(UTC)
            next_sequence = max((chunk.sequence for chunk in run.output_chunks), default=0) + 1
            chunk = CommandOutputChunk(
                sequence=next_sequence,
                stream=stream,
                text=sanitized_text,
                truncated=chunk_truncated,
                created_at=now,
            )
            if stream == "stdout":
                combined = f"{run.stdout}{sanitized_text}"
                run.stdout, stdout_truncated = sanitize_output(
                    combined,
                    max_chars=self.max_output_chars,
                )
                run.stdout_truncated = run.stdout_truncated or stdout_truncated or chunk_truncated
            else:
                combined = f"{run.stderr}{sanitized_text}"
                run.stderr, stderr_truncated = sanitize_output(
                    combined,
                    max_chars=self.max_output_chars,
                )
                run.stderr_truncated = run.stderr_truncated or stderr_truncated or chunk_truncated

            run.output_chunks = [*run.output_chunks, chunk][-DEFAULT_MAX_OUTPUT_CHUNKS:]
            run.last_output_at = now
            run.last_heartbeat_at = now
            self._runs.upsert(run)

    def _finalize_async_run(
        self,
        *,
        run_id: str,
        exit_code: int,
        status: CommandRunStatus,
        duration_ms: int,
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return

        sanitized_stdout, stdout_truncated = sanitize_output(
            run.stdout,
            max_chars=self.max_output_chars,
        )
        sanitized_stderr, stderr_truncated = sanitize_output(
            run.stderr,
            max_chars=self.max_output_chars,
        )
        completed_at = datetime.now(UTC)
        run.status = status
        run.exit_code = exit_code
        run.stdout = sanitized_stdout
        run.stderr = sanitized_stderr
        run.stdout_truncated = run.stdout_truncated or stdout_truncated
        run.stderr_truncated = run.stderr_truncated or stderr_truncated
        run.duration_ms = duration_ms
        run.completed_at = completed_at
        run.last_heartbeat_at = completed_at
        run.status_reason = _status_reason_for_terminal_async_run(status)
        if status == CommandRunStatus.cancelled and run.cancelled_at is None:
            run.cancelled_at = completed_at
        self._runs.upsert(run)
        event_log.record(
            LogEventType.cli,
            "Finalized asynchronous CLI command run.",
            actor=run.requested_by or "system",
            subject_id=run.id,
            metadata={
                "command": redact_sensitive_values(run.command),
                "cwd": str(run.cwd),
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "permission_mode": run.permission_mode,
                "status": run.status,
                "status_reason": run.status_reason,
                "supervisor_id": run.supervisor_id,
                "supervisor_pid": run.supervisor_pid,
                "requested_by": run.requested_by,
                "agent_id": run.agent_id,
                "agent_role": run.agent_role,
                "task_id": run.task_id,
                "environment_keys": run.environment_keys,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )

    def _validate_bound_approval(
        self,
        approval: CommandApproval,
        *,
        request: CommandExecutionRequest,
        decision: CommandPolicyDecision,
        cwd: Path,
        environment_keys: list[str],
        environment_digest: str,
    ) -> None:
        if approval.status != CommandApprovalStatus.approved:
            raise PermissionError(
                f"Approval {approval.id} is not executable; current status is {approval.status}."
            )
        if self._approval_is_expired(approval):
            raise PermissionError(f"Approval {approval.id} has expired and cannot be executed.")

        expected_digest = command_approval_digest(
            command=decision.command,
            cwd=cwd,
            timeout_seconds=request.timeout_seconds,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
            environment_keys=environment_keys,
            environment_digest=environment_digest,
            permission_mode=decision.permission_mode,
            matched_rule_id=decision.matched_rule_id,
            matched_rule_name=decision.matched_rule_name,
        )
        review_command = redact_sensitive_values(decision.command)
        checks = [
            approval.command == review_command,
            approval.review_command == review_command,
            approval.cwd == cwd,
            approval.timeout_seconds == request.timeout_seconds,
            approval.requested_by == request.requested_by,
            approval.agent_id == request.agent_id,
            approval.agent_role == request.agent_role,
            approval.task_id == request.task_id,
            sorted(approval.environment_keys) == environment_keys,
            approval.environment_digest == environment_digest,
            approval.permission_mode == decision.permission_mode,
            approval.matched_rule_id == decision.matched_rule_id,
            approval.matched_rule_name == decision.matched_rule_name,
            approval.command_digest == expected_digest,
        ]
        if not all(checks):
            raise PermissionError(f"Approval {approval.id} is not bound to this command request.")

    def _claim_bound_approval(
        self,
        approval: CommandApproval,
        *,
        request: CommandExecutionRequest,
        decision: CommandPolicyDecision,
        cwd: Path,
        environment_keys: list[str],
        environment_digest: str,
    ) -> None:
        with self._active_lock:
            current = self._get_approval_or_raise(approval.id)
            self._validate_bound_approval(
                current,
                request=request,
                decision=decision,
                cwd=cwd,
                environment_keys=environment_keys,
                environment_digest=environment_digest,
            )
            now = datetime.now(UTC)
            current.status = CommandApprovalStatus.executed
            current.executed_at = now
            current.updated_at = now
            self._approvals.upsert(current)
        event_log.record(
            LogEventType.approval,
            "Claimed CLI command approval for execution.",
            actor=request.requested_by or approval.requested_by or "system",
            subject_id=approval.id,
        )

    def _approval_is_expired(self, approval: CommandApproval) -> bool:
        return approval.expires_at <= datetime.now(UTC)

    def _mark_approval_executed(
        self,
        approval_id: str,
        run_id: str,
        *,
        actor: str | None = None,
    ) -> None:
        with self._active_lock:
            approval = self._get_approval_or_raise(approval_id)
            if approval.run_id is not None:
                return
            now = datetime.now(UTC)
            approval.status = CommandApprovalStatus.executed
            approval.run_id = run_id
            if approval.executed_at is None:
                approval.executed_at = now
            approval.updated_at = now
            self._approvals.upsert(approval)
        event_log.record(
            LogEventType.approval,
            "Executed CLI command approval.",
            actor=actor or approval.requested_by or "system",
            subject_id=approval.id,
            metadata={"run_id": run_id},
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
