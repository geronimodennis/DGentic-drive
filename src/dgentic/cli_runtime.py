import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Lock, Thread
from typing import Literal
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
DEFAULT_MAX_OUTPUT_CHUNKS = 200
DEFAULT_APPROVAL_TTL_MINUTES = 30
TRUNCATION_MARKER = "\n[output truncated]"
REDACTED_SECRET_MARKER = "[REDACTED]"
APPROVAL_DIGEST_PREFIX = "hmac-sha256:"
REDACTED_LEGACY_DIGEST_MARKER = "[LEGACY_DIGEST_REDACTED]"
_APPROVAL_DIGEST_KEY_FILE = "cli-approval-digest.key"
_DIGEST_KEY_LOCK = Lock()
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)"
    r"|TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)\s*=\s*"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\$\([^;&|]*?\)|`(?:\\.|[^`\\])*`|(?:\\.|[^\s;&|'\"\)])+)",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_RE = re.compile(
    r"(?P<prefix>(?:--?|/)[A-Za-z0-9_-]*"
    r"(?:api[-_]?key|access[-_]?key|token|password|secret)[A-Za-z0-9_-]*"
    r"(?:\s+|=|:))"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\$\([^;&|]*?\)|`(?:\\.|[^`\\])*`|(?:\\.|[^\s;&|'\"\)])+)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PREFIX_RE = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)"
    r"|TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)\s*=\s*",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_PREFIX_RE = re.compile(
    r"(?P<prefix>(?:--?|/)[A-Za-z0-9_-]*"
    r"(?:api[-_]?key|access[-_]?key|token|password|secret)[A-Za-z0-9_-]*"
    r"(?:\s+|=|:))",
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
    stale = "stale"


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
        self.command_digest = _sanitize_approval_digest(self.command_digest)
        self.environment_digest = _sanitize_approval_digest(self.environment_digest)


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
    started_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        self.command = redact_sensitive_values(self.command)


class CommandRunOutput(BaseModel):
    run_id: str
    status: CommandRunStatus
    chunks: list[CommandOutputChunk] = Field(default_factory=list)
    next_sequence: int


def redact_sensitive_values(text: str) -> str:
    """Redact basic KEY=value secret assignments from command output."""

    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}={REDACTED_SECRET_MARKER}",
        _SENSITIVE_FLAG_RE.sub(
            lambda match: f"{match.group('prefix')}{REDACTED_SECRET_MARKER}",
            _redact_substitution_secret_values(text),
        ),
    )


def _redact_substitution_secret_values(text: str) -> str:
    result = text
    for match in list(_SENSITIVE_ASSIGNMENT_PREFIX_RE.finditer(result))[::-1]:
        result = _redact_balanced_substitution_value(result, match.end(), "")
    for match in list(_SENSITIVE_FLAG_PREFIX_RE.finditer(result))[::-1]:
        result = _redact_balanced_substitution_value(result, match.end(), match.group("prefix"))
    return result


def _redact_balanced_substitution_value(text: str, value_start: int, prefix: str) -> str:
    if not text.startswith("$(", value_start):
        return text
    end_index = _find_balanced_substitution_end(text, value_start + 2)
    if end_index == -1:
        return text
    redacted = f"{prefix}{REDACTED_SECRET_MARKER}"
    return text[: value_start - len(prefix)] + redacted + text[end_index:]


def _find_balanced_substitution_end(text: str, start_index: int) -> int:
    depth = 1
    quote: str | None = None
    escaped = False
    index = start_index
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if text.startswith("$(", index):
            depth += 1
            index += 2
            continue
        if char == ")":
            depth -= 1
            index += 1
            if depth == 0:
                return index
            continue
        index += 1
    return -1


def _regex_redact_sensitive_values(text: str) -> str:
    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}={REDACTED_SECRET_MARKER}",
        _SENSITIVE_FLAG_RE.sub(
            lambda match: f"{match.group('prefix')}{REDACTED_SECRET_MARKER}",
            text,
        ),
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
        self.reconcile_stale_command_runs()

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
        environment_keys = validate_command_environment(request.environment)
        environment_digest = command_environment_digest(request.environment)
        cwd = resolve_command_cwd(request.cwd)
        requested_by_value = requested_by or request.requested_by
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
    ) -> CommandApproval:
        approval = self._get_approval_or_raise(approval_id)
        if approval.status != CommandApprovalStatus.pending:
            raise ValueError(
                f"Only pending approvals can be approved; current status is {approval.status}."
            )
        if self._approval_is_expired(approval):
            raise ValueError(f"Approval {approval_id} has expired and cannot be approved.")

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
        return self.execute_command(request)

    def execute_command(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        result, run = self._execute_request(request)
        if run.approval_id is not None:
            self._mark_approval_executed(run.approval_id, run.id)
        return result

    def start_command(self, request: CommandExecutionRequest) -> CommandRun:
        decision, cwd, env, environment_keys, approval_id = self._prepare_request(request)
        started_at = datetime.now(UTC)
        process = subprocess.Popen(
            _command_args(decision.command),
            env=env,
            **_popen_kwargs(cwd),
        )
        run = CommandRun(
            id=f"cmdrun-{uuid4()}",
            approval_id=approval_id,
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
        if approval_id is not None:
            self._mark_approval_executed(approval_id, run.id)
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

    def reconcile_stale_command_runs(self) -> list[CommandRun]:
        now = datetime.now(UTC)
        reconciled: list[CommandRun] = []
        for run in self._runs.list():
            if run.status != CommandRunStatus.running:
                continue
            with self._active_lock:
                is_active = run.id in self._active_processes
            if is_active:
                continue

            message = (
                "Command run was marked stale because no active process is registered "
                "in this backend process."
            )
            stderr = f"{run.stderr}\n{message}" if run.stderr else message
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
            self._runs.upsert(run)
            event_log.record(
                LogEventType.cli,
                "Reconciled stale CLI command run.",
                subject_id=run.id,
                metadata={
                    "command": redact_sensitive_values(run.command),
                    "cwd": str(run.cwd),
                    "process_id": run.process_id,
                    "status": run.status,
                    "requested_by": run.requested_by,
                    "agent_id": run.agent_id,
                    "agent_role": run.agent_role,
                    "task_id": run.task_id,
                },
            )
            reconciled.append(run)
        return reconciled

    def _prepare_request(
        self,
        request: CommandExecutionRequest,
    ) -> tuple[CommandPolicyDecision, Path, dict[str, str], list[str], str | None]:
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
        cwd = resolve_command_cwd(request.cwd)
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
            )
            if run.approval_id is not None:
                self._mark_approval_executed(run.approval_id, run.id)
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
            chunk = CommandOutputChunk(
                sequence=len(run.output_chunks) + 1,
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
            subject_id=approval.id,
        )

    def _approval_is_expired(self, approval: CommandApproval) -> bool:
        return approval.expires_at <= datetime.now(UTC)

    def _mark_approval_executed(self, approval_id: str, run_id: str) -> None:
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
