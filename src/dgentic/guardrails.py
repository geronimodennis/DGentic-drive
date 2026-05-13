import base64
import binascii
import hashlib
import hmac
import json
import secrets
import shutil
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from dgentic.command_policy import evaluate_command_policy as evaluate_configured_command_policy
from dgentic.events import event_log
from dgentic.hook_policy import evaluate_hook_policy
from dgentic.orchestration import authorize_filesystem_action
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandPolicyDecision,
    CommandPolicyRequest,
    FileAccessDecision,
    FileAccessRequest,
    FileAction,
    FileApprovalRequest,
    FileBinaryReadRequest,
    FileBinaryReadResponse,
    FileBinaryWriteRequest,
    FileCopyRequest,
    FileCopyResponse,
    FileDeleteRequest,
    FileDeleteResponse,
    FileListEntry,
    FileListRequest,
    FileListResponse,
    FileMetadataRequest,
    FileMetadataResponse,
    FileMoveRequest,
    FileMoveResponse,
    FileReadRequest,
    FileReadResponse,
    FileRenameRequest,
    FileRenameResponse,
    FileWriteRequest,
    FileWriteResponse,
    HookPolicyDecision,
    HookPolicySurface,
    LogEventType,
    OrchestrationActionDecision,
    PermissionMode,
)
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

_APPROVAL_REQUIRED_ACTIONS = frozenset({"delete", "move", "copy", "rename"})
_TARGET_ACTIONS = frozenset({"move", "copy", "rename"})
FILESYSTEM_APPROVAL_DIGEST_PREFIX = "hmac-sha256:"
REDACTED_LEGACY_DIGEST_MARKER = "[LEGACY_DIGEST_REDACTED]"
DEFAULT_FILESYSTEM_APPROVAL_TTL_MINUTES = 30
MAX_FILESYSTEM_APPROVAL_CONTEXT_CHARS = 256
_FILESYSTEM_APPROVAL_DIGEST_KEY_FILE = "filesystem-approval-digest.key"
_FILESYSTEM_APPROVAL_DIGEST_LOCK = Lock()
_filesystem_approval_lock = Lock()


class FileApprovalRequiredError(PermissionError):
    """Raised when a filesystem operation needs a bound approval record."""


class FileApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    executed = "executed"


class FileApproval(BaseModel):
    id: str
    action: FileAction
    path: str
    target_path: str | None = None
    recursive: bool = False
    overwrite: bool = False
    create_parent_dirs: bool = True
    permission_mode: PermissionMode = PermissionMode.approval_required
    policy_reason: str = ""
    path_digest: str = ""
    target_path_digest: str = ""
    payload_digest: str = ""
    source_state_digest: str = ""
    target_state_digest: str = ""
    resolved_path_digest: str = ""
    resolved_target_path_digest: str = ""
    options_digest: str = ""
    policy_digest: str = ""
    approval_digest: str = ""
    hook_policy: HookPolicyDecision | None = None
    orchestration: OrchestrationActionDecision | None = None
    status: FileApprovalStatus = FileApprovalStatus.pending
    requested_by: str | None = Field(default=None, max_length=MAX_FILESYSTEM_APPROVAL_CONTEXT_CHARS)
    agent_id: str | None = Field(default=None, max_length=MAX_FILESYSTEM_APPROVAL_CONTEXT_CHARS)
    agent_role: str | None = Field(default=None, max_length=MAX_FILESYSTEM_APPROVAL_CONTEXT_CHARS)
    task_id: str | None = Field(default=None, max_length=MAX_FILESYSTEM_APPROVAL_CONTEXT_CHARS)
    decided_by: str | None = Field(default=None, max_length=MAX_FILESYSTEM_APPROVAL_CONTEXT_CHARS)
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: (
            datetime.now(UTC) + timedelta(minutes=DEFAULT_FILESYSTEM_APPROVAL_TTL_MINUTES)
        )
    )
    decided_at: datetime | None = None
    executed_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        self.path = redact_sensitive_values(self.path)
        if self.target_path is not None:
            self.target_path = redact_sensitive_values(self.target_path)
        self.policy_reason = redact_sensitive_values(self.policy_reason)
        self.requested_by = _redact_optional_sensitive_text(self.requested_by)
        self.agent_id = _redact_optional_sensitive_text(self.agent_id)
        self.agent_role = _redact_optional_sensitive_text(self.agent_role)
        self.task_id = _redact_optional_sensitive_text(self.task_id)
        self.decided_by = _redact_optional_sensitive_text(self.decided_by)
        self.decision_reason = _redact_optional_sensitive_text(self.decision_reason)
        self.denial_reason = _redact_optional_sensitive_text(self.denial_reason)
        self.path_digest = _sanitize_filesystem_approval_digest(self.path_digest)
        self.target_path_digest = _sanitize_filesystem_approval_digest(self.target_path_digest)
        self.payload_digest = _sanitize_filesystem_approval_digest(self.payload_digest)
        self.source_state_digest = _sanitize_filesystem_approval_digest(self.source_state_digest)
        self.target_state_digest = _sanitize_filesystem_approval_digest(self.target_state_digest)
        self.resolved_path_digest = _sanitize_filesystem_approval_digest(self.resolved_path_digest)
        self.resolved_target_path_digest = _sanitize_filesystem_approval_digest(
            self.resolved_target_path_digest
        )
        self.options_digest = _sanitize_filesystem_approval_digest(self.options_digest)
        self.policy_digest = _sanitize_filesystem_approval_digest(self.policy_digest)
        self.approval_digest = _sanitize_filesystem_approval_digest(self.approval_digest)


class FileApprovalReview(BaseModel):
    id: str
    status: FileApprovalStatus
    action: FileAction
    path: str
    target_path: str | None = None
    recursive: bool = False
    overwrite: bool = False
    create_parent_dirs: bool = True
    permission_mode: PermissionMode
    policy_reason: str
    path_digest: str = ""
    target_path_digest: str = ""
    payload_digest: str = ""
    source_state_digest: str = ""
    target_state_digest: str = ""
    resolved_path_digest: str = ""
    resolved_target_path_digest: str = ""
    options_digest: str = ""
    policy_digest: str = ""
    approval_digest: str = ""
    hook_policy: HookPolicyDecision | None = None
    orchestration: OrchestrationActionDecision | None = None
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    requires_bound_execution_request: bool = True
    direct_execute_available: bool = False
    review_warnings: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    executed_at: datetime | None = None


_filesystem_approvals = JsonCollection("filesystem-approvals", FileApproval)


def _root_and_data_dirs() -> tuple[Path, Path]:
    settings = get_settings()
    root_dir = settings.root_dir.resolve()
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = root_dir / data_dir
    return root_dir, data_dir.resolve()


def create_file_approval(
    request: FileApprovalRequest,
    *,
    requested_by: str | None = None,
) -> FileApproval:
    decision = evaluate_file_access(
        _file_access_request(request, request.action, request.target_path),
        actor=requested_by,
    )
    if decision.permission_mode != PermissionMode.approval_required:
        raise ValueError("Only approval-required filesystem operations can be queued.")

    requester = requested_by or request.requested_by
    options = _file_approval_options(
        recursive=request.recursive,
        overwrite=request.overwrite,
        create_parent_dirs=request.create_parent_dirs,
    )
    path_digest = filesystem_path_digest(request.path)
    target_path_digest = filesystem_optional_path_digest(request.target_path)
    payload_digest = filesystem_payload_digest(
        action=request.action,
        content=request.content,
        content_base64=request.content_base64,
    )
    source_state_digest = filesystem_path_state_digest(decision.resolved_path)
    target_state_digest = filesystem_optional_path_state_digest(decision.resolved_target_path)
    resolved_path_digest = filesystem_resolved_path_digest(decision.resolved_path)
    resolved_target_path_digest = filesystem_optional_resolved_path_digest(
        decision.resolved_target_path
    )
    options_digest = filesystem_options_digest(options)
    policy_digest = filesystem_policy_decision_digest(
        decision,
        action=request.action,
        path_digest=path_digest,
        target_path_digest=target_path_digest,
        payload_digest=payload_digest,
        source_state_digest=source_state_digest,
        target_state_digest=target_state_digest,
        resolved_path_digest=resolved_path_digest,
        resolved_target_path_digest=resolved_target_path_digest,
    )
    approval_digest = filesystem_approval_digest(
        action=request.action,
        path_digest=path_digest,
        target_path_digest=target_path_digest,
        payload_digest=payload_digest,
        source_state_digest=source_state_digest,
        target_state_digest=target_state_digest,
        resolved_path_digest=resolved_path_digest,
        resolved_target_path_digest=resolved_target_path_digest,
        options_digest=options_digest,
        policy_digest=policy_digest,
        permission_mode=decision.permission_mode,
        requested_by=requester,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    approval = FileApproval(
        id=f"filesystem-approval-{uuid4()}",
        action=request.action,
        path=_safe_path_for_review(request.path),
        target_path=_safe_optional_path_for_review(request.target_path),
        recursive=request.recursive,
        overwrite=request.overwrite,
        create_parent_dirs=request.create_parent_dirs,
        permission_mode=decision.permission_mode,
        policy_reason=decision.reason,
        path_digest=path_digest,
        target_path_digest=target_path_digest,
        payload_digest=payload_digest,
        source_state_digest=source_state_digest,
        target_state_digest=target_state_digest,
        resolved_path_digest=resolved_path_digest,
        resolved_target_path_digest=resolved_target_path_digest,
        options_digest=options_digest,
        policy_digest=policy_digest,
        approval_digest=approval_digest,
        hook_policy=decision.hook_policy,
        orchestration=decision.orchestration,
        requested_by=requester,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _filesystem_approvals.upsert(approval)
    event_log.record(
        LogEventType.approval,
        "Created filesystem approval request.",
        actor=approval.requested_by or "system",
        subject_id=approval.id,
        metadata=_filesystem_approval_event_metadata(approval),
    )
    return approval


def list_file_approvals(
    status: FileApprovalStatus | str | None = None,
) -> list[FileApproval]:
    approvals = _filesystem_approvals.list()
    if status is None:
        return approvals
    requested_status = FileApprovalStatus(status)
    return [approval for approval in approvals if approval.status == requested_status]


def get_file_approval_review(approval_id: str) -> FileApprovalReview:
    approval = _get_file_approval_or_raise(approval_id)
    warnings = [
        "Filesystem approval stores redacted path previews and request digests; execute with "
        "a bound request for the same action, path, target, options, policy, and actor context."
    ]
    if _file_approval_is_expired(approval):
        warnings.append("Approval is expired.")
    return FileApprovalReview(
        id=approval.id,
        status=approval.status,
        action=approval.action,
        path=approval.path,
        target_path=approval.target_path,
        recursive=approval.recursive,
        overwrite=approval.overwrite,
        create_parent_dirs=approval.create_parent_dirs,
        permission_mode=approval.permission_mode,
        policy_reason=approval.policy_reason,
        path_digest=approval.path_digest,
        target_path_digest=approval.target_path_digest,
        payload_digest=approval.payload_digest,
        source_state_digest=approval.source_state_digest,
        target_state_digest=approval.target_state_digest,
        resolved_path_digest=approval.resolved_path_digest,
        resolved_target_path_digest=approval.resolved_target_path_digest,
        options_digest=approval.options_digest,
        policy_digest=approval.policy_digest,
        approval_digest=approval.approval_digest,
        hook_policy=approval.hook_policy,
        orchestration=approval.orchestration,
        requested_by=approval.requested_by,
        agent_id=approval.agent_id,
        agent_role=approval.agent_role,
        task_id=approval.task_id,
        review_warnings=warnings,
        decided_by=approval.decided_by,
        decision_reason=_redact_optional_sensitive_text(approval.decision_reason),
        denial_reason=_redact_optional_sensitive_text(approval.denial_reason),
        created_at=approval.created_at,
        updated_at=approval.updated_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        executed_at=approval.executed_at,
    )


def approve_file_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> FileApproval:
    redacted_reason = _redact_optional_sensitive_text(reason)

    def approve(current: FileApproval) -> FileApproval:
        if current.status != FileApprovalStatus.pending:
            raise ValueError(
                "Only pending filesystem approvals can be approved; "
                f"current status is {current.status}."
            )
        if _file_approval_is_expired(current):
            raise ValueError(
                f"Filesystem approval {approval_id} has expired and cannot be approved."
            )
        now = datetime.now(UTC)
        current.status = FileApprovalStatus.approved
        current.decided_by = _redact_optional_sensitive_text(decided_by)
        current.decision_reason = redacted_reason
        current.decided_at = now
        current.updated_at = now
        return current

    approval = _filesystem_approvals.update(approval_id, approve)
    event_log.record(
        LogEventType.approval,
        "Approved filesystem request.",
        actor=approval.decided_by or "system",
        subject_id=approval.id,
        metadata={
            **_filesystem_approval_event_metadata(approval),
            **({"reason": redacted_reason} if redacted_reason else {}),
        },
    )
    return approval


def deny_file_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> FileApproval:
    redacted_reason = _redact_optional_sensitive_text(reason)

    def deny(current: FileApproval) -> FileApproval:
        if current.status != FileApprovalStatus.pending:
            raise ValueError(
                "Only pending filesystem approvals can be denied; "
                f"current status is {current.status}."
            )
        now = datetime.now(UTC)
        current.status = FileApprovalStatus.denied
        current.decided_by = _redact_optional_sensitive_text(decided_by)
        current.decision_reason = redacted_reason
        current.denial_reason = redacted_reason
        current.decided_at = now
        current.updated_at = now
        return current

    approval = _filesystem_approvals.update(approval_id, deny)
    event_log.record(
        LogEventType.approval,
        "Denied filesystem request.",
        actor=approval.decided_by or "system",
        subject_id=approval.id,
        metadata={
            **_filesystem_approval_event_metadata(approval),
            **({"reason": redacted_reason} if redacted_reason else {}),
        },
    )
    return approval


def filesystem_path_digest(path: Path) -> str:
    return _filesystem_hmac_digest(_canonical_json({"path": path.as_posix()}))


def filesystem_optional_path_digest(path: Path | None) -> str:
    if path is None:
        return ""
    return filesystem_path_digest(path)


def filesystem_payload_digest(
    *,
    action: FileAction,
    content: str | None = None,
    content_base64: str | None = None,
) -> str:
    if action == "write":
        if content is None:
            raise ValueError("write approval requests must include content.")
        _ensure_payload_size(len(content.encode("utf-8")))
        return _filesystem_hmac_digest(
            _canonical_json({"kind": "text", "bytes": content.encode("utf-8").hex()})
        )
    if action == "binary_write":
        if content_base64 is None:
            raise ValueError("binary_write approval requests must include content_base64.")
        try:
            content_bytes = base64.b64decode(content_base64.encode("ascii"), validate=True)
        except (binascii.Error, UnicodeEncodeError) as exc:
            raise ValueError("content_base64 must be valid base64.") from exc
        _ensure_payload_size(len(content_bytes))
        return _filesystem_hmac_digest(
            _canonical_json({"kind": "binary", "bytes": content_bytes.hex()})
        )
    if content is not None or content_base64 is not None:
        raise ValueError("Filesystem approval content is only valid for write operations.")
    return ""


def filesystem_payload_digest_for_request(action: FileAction, request: Any) -> str:
    return filesystem_payload_digest(
        action=action,
        content=getattr(request, "content", None),
        content_base64=getattr(request, "content_base64", None),
    )


def filesystem_path_state_digest(path: Path) -> str:
    return _filesystem_hmac_digest(_canonical_json(_path_state_payload(path)))


def filesystem_optional_path_state_digest(path: Path | None) -> str:
    if path is None:
        return ""
    return filesystem_path_state_digest(path)


def filesystem_resolved_path_digest(path: Path) -> str:
    return _filesystem_hmac_digest(_canonical_json({"resolved_path": str(path)}))


def filesystem_optional_resolved_path_digest(path: Path | None) -> str:
    if path is None:
        return ""
    return filesystem_resolved_path_digest(path)


def filesystem_options_digest(options: dict[str, bool]) -> str:
    return _filesystem_hmac_digest(_canonical_json(options))


def filesystem_policy_decision_digest(
    decision: FileAccessDecision,
    *,
    action: FileAction,
    path_digest: str,
    target_path_digest: str,
    payload_digest: str,
    source_state_digest: str,
    target_state_digest: str,
    resolved_path_digest: str,
    resolved_target_path_digest: str,
) -> str:
    payload = {
        "action": action,
        "allowed": decision.allowed,
        "permission_mode": decision.permission_mode,
        "reason": decision.reason,
        "path_digest": path_digest,
        "target_path_digest": target_path_digest,
        "payload_digest": payload_digest,
        "source_state_digest": source_state_digest,
        "target_state_digest": target_state_digest,
        "resolved_path_digest": resolved_path_digest,
        "resolved_target_path_digest": resolved_target_path_digest,
        "hook_policy": _model_dump_or_value(decision.hook_policy),
        "orchestration": _model_dump_or_value(decision.orchestration),
    }
    return _filesystem_hmac_digest(_canonical_json(payload))


def filesystem_approval_digest(
    *,
    action: FileAction,
    path_digest: str,
    target_path_digest: str,
    payload_digest: str,
    source_state_digest: str,
    target_state_digest: str,
    resolved_path_digest: str,
    resolved_target_path_digest: str,
    options_digest: str,
    policy_digest: str,
    permission_mode: PermissionMode,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> str:
    payload = {
        "action": action,
        "path_digest": path_digest,
        "target_path_digest": target_path_digest,
        "payload_digest": payload_digest,
        "source_state_digest": source_state_digest,
        "target_state_digest": target_state_digest,
        "resolved_path_digest": resolved_path_digest,
        "resolved_target_path_digest": resolved_target_path_digest,
        "options_digest": options_digest,
        "policy_digest": policy_digest,
        "permission_mode": permission_mode,
        "requested_by": requested_by,
        "agent_id": agent_id,
        "agent_role": agent_role,
        "task_id": task_id,
    }
    return _filesystem_hmac_digest(_canonical_json(payload))


def _filesystem_approval_event_metadata(approval: FileApproval) -> dict[str, Any]:
    return {
        "action": approval.action,
        "path": approval.path,
        "target_path": approval.target_path,
        "recursive": approval.recursive,
        "overwrite": approval.overwrite,
        "create_parent_dirs": approval.create_parent_dirs,
        "permission_mode": approval.permission_mode,
        "requested_by": approval.requested_by,
        "agent_id": approval.agent_id,
        "agent_role": approval.agent_role,
        "task_id": approval.task_id,
        "path_digest": approval.path_digest,
        "target_path_digest": approval.target_path_digest,
        "payload_digest": approval.payload_digest,
        "source_state_digest": approval.source_state_digest,
        "target_state_digest": approval.target_state_digest,
        "resolved_path_digest": approval.resolved_path_digest,
        "resolved_target_path_digest": approval.resolved_target_path_digest,
        "options_digest": approval.options_digest,
        "policy_digest": approval.policy_digest,
        "approval_digest": approval.approval_digest,
        "expires_at": approval.expires_at.isoformat(),
    }


def _safe_path_for_review(path: Path) -> str:
    return redact_sensitive_values(path.as_posix())


def _safe_optional_path_for_review(path: Path | None) -> str | None:
    if path is None:
        return None
    return _safe_path_for_review(path)


def _redact_optional_sensitive_text(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_sensitive_values(value)


def _file_approval_options(
    *,
    recursive: bool = False,
    overwrite: bool = False,
    create_parent_dirs: bool = True,
) -> dict[str, bool]:
    return {
        "recursive": recursive,
        "overwrite": overwrite,
        "create_parent_dirs": create_parent_dirs,
    }


def _options_for_file_request(request: Any) -> dict[str, bool]:
    return _file_approval_options(
        recursive=bool(getattr(request, "recursive", False)),
        overwrite=bool(getattr(request, "overwrite", False)),
        create_parent_dirs=bool(getattr(request, "create_parent_dirs", True)),
    )


def _approval_boolean_bypass_allowed() -> bool:
    return get_settings().environment.strip().lower() in {"development", "test", "testing"}


def _filesystem_approval_digest_key() -> bytes:
    settings = get_settings()
    configured_key = settings.approval_digest_key.strip()
    if configured_key:
        return configured_key.encode("utf-8")

    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = settings.root_dir / data_dir
    key_path = data_dir / _FILESYSTEM_APPROVAL_DIGEST_KEY_FILE
    with _FILESYSTEM_APPROVAL_DIGEST_LOCK:
        if key_path.exists():
            stored_key = key_path.read_text(encoding="utf-8").strip()
            if stored_key:
                return stored_key.encode("utf-8")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        generated_key = secrets.token_hex(32)
        key_path.write_text(generated_key + "\n", encoding="utf-8")
        return generated_key.encode("utf-8")


def _filesystem_hmac_digest(encoded_payload: str) -> str:
    digest = hmac.new(
        _filesystem_approval_digest_key(),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{FILESYSTEM_APPROVAL_DIGEST_PREFIX}{digest}"


def _sanitize_filesystem_approval_digest(digest: str) -> str:
    if not digest:
        return ""
    if digest.startswith(FILESYSTEM_APPROVAL_DIGEST_PREFIX):
        return digest
    return REDACTED_LEGACY_DIGEST_MARKER


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _model_dump_or_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _path_state_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    stat_result = path.stat()
    return {
        "exists": True,
        "type": _file_type(path),
        "size_bytes": stat_result.st_size if path.is_file() else None,
        "modified_ns": stat_result.st_mtime_ns,
    }


def _file_approval_is_expired(approval: FileApproval) -> bool:
    return approval.expires_at <= datetime.now(UTC)


def _get_file_approval_or_raise(approval_id: str) -> FileApproval:
    approval = _filesystem_approvals.get(approval_id)
    if approval is None:
        raise KeyError(f"Filesystem approval not found: {approval_id}")
    return approval


def _claim_bound_file_approval(
    approval_id: str,
    *,
    decision: FileAccessDecision,
    action: FileAction,
    request: Any,
    actor: str | None,
) -> FileApproval:
    def claim(current: FileApproval) -> FileApproval:
        _validate_bound_file_approval(
            current,
            decision=decision,
            action=action,
            request=request,
            requested_by=actor,
        )
        now = datetime.now(UTC)
        current.status = FileApprovalStatus.executed
        current.executed_at = now
        current.updated_at = now
        return current

    with _filesystem_approval_lock:
        try:
            approval = _filesystem_approvals.update(approval_id, claim)
        except KeyError as exc:
            raise FileApprovalRequiredError(str(exc)) from exc
    event_log.record(
        LogEventType.approval,
        "Claimed filesystem approval for execution.",
        actor=actor or approval.requested_by or "system",
        subject_id=approval.id,
        metadata={
            "action": approval.action,
            "path": approval.path,
            "target_path": approval.target_path,
            "requested_by": _redact_optional_sensitive_text(actor),
        },
    )
    return approval


def _validate_bound_file_approval(
    approval: FileApproval,
    *,
    decision: FileAccessDecision,
    action: FileAction,
    request: Any,
    requested_by: str | None,
) -> None:
    if approval.status != FileApprovalStatus.approved:
        raise FileApprovalRequiredError(
            f"Filesystem approval {approval.id} is not executable; "
            f"current status is {approval.status}."
        )
    if _file_approval_is_expired(approval):
        raise FileApprovalRequiredError(
            f"Filesystem approval {approval.id} has expired and cannot be executed."
        )
    if decision.permission_mode != PermissionMode.approval_required:
        raise FileApprovalRequiredError(
            f"Filesystem approval {approval.id} is not required by the current filesystem policy."
        )

    path = request.path
    target_path = getattr(request, "target_path", None)
    if action == "rename":
        target_path = path.parent / request.new_name
    path_digest = filesystem_path_digest(path)
    target_path_digest = filesystem_optional_path_digest(target_path)
    payload_digest = filesystem_payload_digest_for_request(action, request)
    source_state_digest = filesystem_path_state_digest(decision.resolved_path)
    target_state_digest = filesystem_optional_path_state_digest(decision.resolved_target_path)
    resolved_path_digest = filesystem_resolved_path_digest(decision.resolved_path)
    resolved_target_path_digest = filesystem_optional_resolved_path_digest(
        decision.resolved_target_path
    )
    options = _options_for_file_request(request)
    options_digest = filesystem_options_digest(options)
    policy_digest = filesystem_policy_decision_digest(
        decision,
        action=action,
        path_digest=path_digest,
        target_path_digest=target_path_digest,
        payload_digest=payload_digest,
        source_state_digest=source_state_digest,
        target_state_digest=target_state_digest,
        resolved_path_digest=resolved_path_digest,
        resolved_target_path_digest=resolved_target_path_digest,
    )
    expected_approval_digest = filesystem_approval_digest(
        action=action,
        path_digest=path_digest,
        target_path_digest=target_path_digest,
        payload_digest=payload_digest,
        source_state_digest=source_state_digest,
        target_state_digest=target_state_digest,
        resolved_path_digest=resolved_path_digest,
        resolved_target_path_digest=resolved_target_path_digest,
        options_digest=options_digest,
        policy_digest=policy_digest,
        permission_mode=decision.permission_mode,
        requested_by=requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    checks = [
        approval.action == action,
        approval.path == _safe_path_for_review(path),
        approval.target_path == _safe_optional_path_for_review(target_path),
        approval.recursive == options["recursive"],
        approval.overwrite == options["overwrite"],
        approval.create_parent_dirs == options["create_parent_dirs"],
        approval.permission_mode == decision.permission_mode,
        approval.policy_reason == redact_sensitive_values(decision.reason),
        approval.path_digest == path_digest,
        approval.target_path_digest == target_path_digest,
        approval.payload_digest == payload_digest,
        approval.source_state_digest == source_state_digest,
        approval.target_state_digest == target_state_digest,
        approval.resolved_path_digest == resolved_path_digest,
        approval.resolved_target_path_digest == resolved_target_path_digest,
        approval.options_digest == options_digest,
        approval.policy_digest == policy_digest,
        approval.approval_digest == expected_approval_digest,
        approval.requested_by == _redact_optional_sensitive_text(requested_by),
        approval.agent_id == _redact_optional_sensitive_text(request.agent_id),
        approval.agent_role == _redact_optional_sensitive_text(request.agent_role),
        approval.task_id == _redact_optional_sensitive_text(request.task_id),
    ]
    if not all(checks):
        raise FileApprovalRequiredError(
            f"Filesystem approval {approval.id} is not bound to this filesystem request."
        )


def _candidate_path(path: Path, root_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return root_dir / path


def _resolve_guarded_path(path: Path, root_dir: Path) -> Path:
    return _candidate_path(path, root_dir).resolve()


def _is_inside(path: Path, root_dir: Path) -> bool:
    return path == root_dir or root_dir in path.parents


def _is_protected(path: Path, protected_data_dir: Path) -> bool:
    return path == protected_data_dir or protected_data_dir in path.parents


def _blocked_decision(
    request: FileAccessRequest,
    resolved_path: Path,
    reason: str,
    *,
    resolved_target_path: Path | None = None,
) -> FileAccessDecision:
    return FileAccessDecision(
        path=request.path,
        resolved_path=resolved_path,
        target_path=request.target_path,
        resolved_target_path=resolved_target_path,
        allowed=False,
        permission_mode=PermissionMode.blocked,
        reason=reason,
    )


def evaluate_file_access(
    request: FileAccessRequest, *, actor: str | None = None
) -> FileAccessDecision:
    root_dir, protected_data_dir = _root_and_data_dirs()
    resolved = _resolve_guarded_path(request.path, root_dir)
    target_resolved: Path | None = None

    if not _is_inside(resolved, root_dir):
        decision = _blocked_decision(
            request,
            resolved,
            f"Path resolves outside configured rootDir: {root_dir}",
        )
    elif _is_protected(resolved, protected_data_dir):
        decision = _blocked_decision(
            request,
            resolved,
            "DGentic state files are protected from guarded filesystem access.",
        )
    elif request.action in _TARGET_ACTIONS and request.target_path is None:
        decision = _blocked_decision(
            request,
            resolved,
            f"{request.action} operations require a target_path.",
        )
    else:
        if request.target_path is not None:
            target_resolved = _resolve_guarded_path(request.target_path, root_dir)
            if not _is_inside(target_resolved, root_dir):
                decision = _blocked_decision(
                    request,
                    resolved,
                    f"Target path resolves outside configured rootDir: {root_dir}",
                    resolved_target_path=target_resolved,
                )
            elif _is_protected(target_resolved, protected_data_dir):
                decision = _blocked_decision(
                    request,
                    resolved,
                    "DGentic state files are protected from guarded filesystem access.",
                    resolved_target_path=target_resolved,
                )
            else:
                decision = _allowed_file_decision(request, resolved, target_resolved)
        else:
            decision = _allowed_file_decision(request, resolved, None)

    decision = _apply_orchestration_filesystem_binding(request, decision, root_dir)
    decision = _apply_hook_policy_to_file_decision(request, decision, actor=actor)
    event_log.record(
        LogEventType.filesystem,
        "Evaluated filesystem access policy.",
        actor=actor or "system",
        metadata=decision.model_dump(mode="json"),
    )
    return decision


def _apply_hook_policy_to_file_decision(
    request: FileAccessRequest,
    decision: FileAccessDecision,
    *,
    actor: str | None,
) -> FileAccessDecision:
    hook_decision = evaluate_hook_policy(
        surface=HookPolicySurface.filesystem,
        action=request.action,
        subject=_filesystem_hook_subject(request),
        current_permission_mode=decision.permission_mode,
        agent_role=request.agent_role,
        agent_id=request.agent_id,
        task_id=request.task_id,
        actor=actor,
    )
    if hook_decision is None:
        return decision
    updates = {"hook_policy": hook_decision}
    if decision.permission_mode != PermissionMode.blocked:
        if hook_decision.permission_mode == PermissionMode.blocked:
            updates.update(
                {
                    "allowed": False,
                    "permission_mode": PermissionMode.blocked,
                    "reason": hook_decision.reason,
                }
            )
        elif (
            hook_decision.permission_mode == PermissionMode.approval_required
            and decision.permission_mode == PermissionMode.autopilot_safe
        ):
            updates.update(
                {
                    "allowed": False,
                    "permission_mode": PermissionMode.approval_required,
                    "reason": hook_decision.reason,
                }
            )
    return decision.model_copy(update=updates)


def _filesystem_hook_subject(request: FileAccessRequest) -> str:
    path = request.path.as_posix()
    if request.target_path is None:
        return path
    return f"{path} -> {request.target_path.as_posix()}"


def _apply_orchestration_filesystem_binding(
    request: FileAccessRequest,
    decision: FileAccessDecision,
    root_dir: Path,
) -> FileAccessDecision:
    if decision.permission_mode == PermissionMode.blocked or not _has_orchestration_context(
        request
    ):
        return decision

    orchestration_decision = authorize_filesystem_action(
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        action=request.action,
        paths=_orchestration_write_paths(request, decision, root_dir),
    )
    if orchestration_decision.allowed:
        return decision.model_copy(update={"orchestration": orchestration_decision})

    return decision.model_copy(
        update={
            "allowed": False,
            "permission_mode": PermissionMode.blocked,
            "reason": orchestration_decision.reason,
            "orchestration": orchestration_decision,
        }
    )


def _has_orchestration_context(request: FileAccessRequest) -> bool:
    return any([request.agent_id, request.agent_role, request.task_id])


def _file_access_request(
    request,
    action: str,
    target_path: Path | None = None,
) -> FileAccessRequest:
    return FileAccessRequest(
        agent_id=getattr(request, "agent_id", None),
        agent_role=getattr(request, "agent_role", None),
        task_id=getattr(request, "task_id", None),
        path=request.path,
        action=action,
        target_path=target_path,
    )


def _orchestration_write_paths(
    request: FileAccessRequest,
    decision: FileAccessDecision,
    root_dir: Path,
) -> list[str]:
    if request.action in {"read", "binary_read", "metadata", "list"}:
        return []
    if request.action == "copy" and decision.resolved_target_path is not None:
        return [_relative_repo_path(decision.resolved_target_path, root_dir)]
    paths = [_relative_repo_path(decision.resolved_path, root_dir)]
    if request.action in {"move", "rename"} and decision.resolved_target_path is not None:
        paths.append(_relative_repo_path(decision.resolved_target_path, root_dir))
    return paths


def _relative_repo_path(path: Path, root_dir: Path) -> str:
    return path.relative_to(root_dir).as_posix()


def _allowed_file_decision(
    request: FileAccessRequest,
    resolved: Path,
    target_resolved: Path | None,
) -> FileAccessDecision:
    if request.action in _APPROVAL_REQUIRED_ACTIONS:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            target_path=request.target_path,
            resolved_target_path=target_resolved,
            allowed=False,
            permission_mode=PermissionMode.approval_required,
            reason=f"{request.action.title()} operations require explicit approval.",
        )
    else:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            target_path=request.target_path,
            resolved_target_path=target_resolved,
            allowed=True,
            permission_mode=PermissionMode.autopilot_safe,
            reason="Path is inside rootDir and action is allowed.",
        )
    return decision


def _require_file_permission(
    decision: FileAccessDecision,
    *,
    request: Any,
    action: FileAction,
    actor: str | None,
    approved: bool = False,
    approval_id: str | None = None,
) -> None:
    if decision.permission_mode == PermissionMode.blocked:
        raise PermissionError(decision.reason)
    if decision.permission_mode == PermissionMode.approval_required:
        if approval_id is not None:
            _claim_bound_file_approval(
                approval_id,
                decision=decision,
                action=action,
                request=request,
                actor=actor,
            )
            return
        if approved and _approval_boolean_bypass_allowed():
            return
        if approved:
            raise FileApprovalRequiredError(
                "Filesystem operation requires an approved approval_id before execution; "
                "the approved boolean bypass is only allowed in development/test mode."
            )
        raise FileApprovalRequiredError(f"{decision.reason} Approval is required before execution.")
    if approval_id is not None:
        raise ValueError("approval_id is only valid for approval-required filesystem operations.")


def _ensure_payload_size(size_bytes: int) -> None:
    max_bytes = get_settings().max_filesystem_bytes
    if size_bytes > max_bytes:
        raise ValueError(
            f"Filesystem payload exceeds maximum filesystem payload size of {max_bytes} bytes."
        )


def _ensure_parent(path: Path, *, create_parent_dirs: bool) -> None:
    if create_parent_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.exists():
        raise FileNotFoundError(str(path.parent))


def _file_type(path: Path) -> str:
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    return "other"


def _metadata_response(path: Path, logical_path: Path) -> FileMetadataResponse:
    stat_result = path.stat()
    return FileMetadataResponse(
        path=logical_path,
        type=_file_type(path),
        size_bytes=stat_result.st_size if path.is_file() else None,
        modified_at=datetime.fromtimestamp(stat_result.st_mtime, UTC),
        is_symlink=path.is_symlink(),
    )


def _copy_path(source: Path, target: Path, *, overwrite: bool, recursive: bool) -> int | None:
    if target.exists():
        if not overwrite:
            raise FileExistsError(str(target))
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    if source.is_dir():
        if not recursive:
            raise IsADirectoryError(str(source))
        shutil.copytree(source, target)
        return None

    _ensure_payload_size(source.stat().st_size)
    shutil.copy2(source, target)
    return target.stat().st_size


def read_guarded_text_file(
    request: FileReadRequest, *, actor: str | None = None
) -> FileReadResponse:
    action: FileAction = "read"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approval_id=request.approval_id,
    )
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_file():
        raise IsADirectoryError(str(decision.path))
    _ensure_payload_size(decision.resolved_path.stat().st_size)

    content = decision.resolved_path.read_text(encoding="utf-8")
    response = FileReadResponse(
        path=decision.path,
        content=content,
        bytes_read=len(content.encode("utf-8")),
    )
    event_log.record(
        LogEventType.filesystem,
        "Read guarded text file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_read": response.bytes_read},
    )
    return response


def write_guarded_text_file(
    request: FileWriteRequest, *, actor: str | None = None
) -> FileWriteResponse:
    action: FileAction = "write"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approval_id=request.approval_id,
    )
    content_bytes = request.content.encode("utf-8")
    _ensure_payload_size(len(content_bytes))

    _ensure_parent(decision.resolved_path, create_parent_dirs=request.create_parent_dirs)

    decision.resolved_path.write_text(request.content, encoding="utf-8")
    response = FileWriteResponse(
        path=decision.path,
        bytes_written=len(content_bytes),
    )
    event_log.record(
        LogEventType.filesystem,
        "Wrote guarded text file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_written": response.bytes_written},
    )
    return response


def read_guarded_binary_file(
    request: FileBinaryReadRequest, *, actor: str | None = None
) -> FileBinaryReadResponse:
    action: FileAction = "binary_read"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approval_id=request.approval_id,
    )
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_file():
        raise IsADirectoryError(str(decision.path))
    _ensure_payload_size(decision.resolved_path.stat().st_size)

    content = decision.resolved_path.read_bytes()
    response = FileBinaryReadResponse(
        path=decision.path,
        content_base64=base64.b64encode(content).decode("ascii"),
        bytes_read=len(content),
    )
    event_log.record(
        LogEventType.filesystem,
        "Read guarded binary file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_read": response.bytes_read},
    )
    return response


def write_guarded_binary_file(
    request: FileBinaryWriteRequest, *, actor: str | None = None
) -> FileWriteResponse:
    action: FileAction = "binary_write"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approval_id=request.approval_id,
    )
    try:
        content = base64.b64decode(request.content_base64.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ValueError("content_base64 must be valid base64.") from exc
    _ensure_payload_size(len(content))
    _ensure_parent(decision.resolved_path, create_parent_dirs=request.create_parent_dirs)

    decision.resolved_path.write_bytes(content)
    response = FileWriteResponse(path=decision.path, bytes_written=len(content))
    event_log.record(
        LogEventType.filesystem,
        "Wrote guarded binary file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_written": response.bytes_written},
    )
    return response


def delete_guarded_path(
    request: FileDeleteRequest, *, actor: str | None = None
) -> FileDeleteResponse:
    action: FileAction = "delete"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approved=request.approved,
        approval_id=request.approval_id,
    )
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if decision.resolved_path.is_dir():
        if request.recursive:
            shutil.rmtree(decision.resolved_path)
        else:
            decision.resolved_path.rmdir()
    else:
        decision.resolved_path.unlink()
    response = FileDeleteResponse(path=decision.path, deleted=True)
    event_log.record(
        LogEventType.filesystem,
        "Deleted guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "recursive": request.recursive,
            "approved": request.approved,
            "approval_id": request.approval_id,
        },
    )
    return response


def move_guarded_path(request: FileMoveRequest, *, actor: str | None = None) -> FileMoveResponse:
    action: FileAction = "move"
    decision = evaluate_file_access(
        _file_access_request(request, action, request.target_path), actor=actor
    )
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approved=request.approved,
        approval_id=request.approval_id,
    )
    if decision.resolved_target_path is None:
        raise PermissionError("Move operation requires a target path.")
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    _ensure_parent(decision.resolved_target_path, create_parent_dirs=True)
    if decision.resolved_target_path.exists():
        if not request.overwrite:
            raise FileExistsError(str(decision.target_path))
        if decision.resolved_target_path.is_dir():
            shutil.rmtree(decision.resolved_target_path)
        else:
            decision.resolved_target_path.unlink()

    shutil.move(str(decision.resolved_path), str(decision.resolved_target_path))
    response = FileMoveResponse(path=decision.path, target_path=request.target_path, moved=True)
    event_log.record(
        LogEventType.filesystem,
        "Moved guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "target_path": str(request.target_path),
            "overwrite": request.overwrite,
            "approved": request.approved,
            "approval_id": request.approval_id,
        },
    )
    return response


def copy_guarded_path(request: FileCopyRequest, *, actor: str | None = None) -> FileCopyResponse:
    action: FileAction = "copy"
    decision = evaluate_file_access(
        _file_access_request(request, action, request.target_path), actor=actor
    )
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approved=request.approved,
        approval_id=request.approval_id,
    )
    if decision.resolved_target_path is None:
        raise PermissionError("Copy operation requires a target path.")
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    _ensure_parent(decision.resolved_target_path, create_parent_dirs=True)
    bytes_copied = _copy_path(
        decision.resolved_path,
        decision.resolved_target_path,
        overwrite=request.overwrite,
        recursive=request.recursive,
    )
    response = FileCopyResponse(
        path=decision.path,
        target_path=request.target_path,
        copied=True,
        bytes_copied=bytes_copied,
    )
    event_log.record(
        LogEventType.filesystem,
        "Copied guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "target_path": str(request.target_path),
            "overwrite": request.overwrite,
            "recursive": request.recursive,
            "bytes_copied": bytes_copied,
            "approved": request.approved,
            "approval_id": request.approval_id,
        },
    )
    return response


def rename_guarded_path(
    request: FileRenameRequest, *, actor: str | None = None
) -> FileRenameResponse:
    target_logical_path = request.path.parent / request.new_name
    action: FileAction = "rename"
    decision = evaluate_file_access(
        _file_access_request(request, action, target_logical_path), actor=actor
    )
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approved=request.approved,
        approval_id=request.approval_id,
    )
    if decision.resolved_target_path is None:
        raise PermissionError("Rename operation requires a target path.")
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if decision.resolved_target_path.exists():
        if not request.overwrite:
            raise FileExistsError(str(target_logical_path))
        if decision.resolved_target_path.is_dir():
            shutil.rmtree(decision.resolved_target_path)
        else:
            decision.resolved_target_path.unlink()

    decision.resolved_path.rename(decision.resolved_target_path)
    response = FileRenameResponse(
        path=decision.path,
        target_path=target_logical_path,
        renamed=True,
    )
    event_log.record(
        LogEventType.filesystem,
        "Renamed guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "target_path": str(target_logical_path),
            "overwrite": request.overwrite,
            "approval_id": request.approval_id,
        },
    )
    return response


def get_guarded_path_metadata(
    request: FileMetadataRequest, *, actor: str | None = None
) -> FileMetadataResponse:
    action: FileAction = "metadata"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approval_id=request.approval_id,
    )
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    response = _metadata_response(decision.resolved_path, decision.path)
    event_log.record(
        LogEventType.filesystem,
        "Read guarded filesystem metadata.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "type": response.type},
    )
    return response


def list_guarded_directory(
    request: FileListRequest, *, actor: str | None = None
) -> FileListResponse:
    action: FileAction = "list"
    decision = evaluate_file_access(_file_access_request(request, action), actor=actor)
    _require_file_permission(
        decision,
        request=request,
        action=action,
        actor=actor,
        approval_id=request.approval_id,
    )
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_dir():
        raise NotADirectoryError(str(decision.path))

    root_dir, protected_data_dir = _root_and_data_dirs()
    entries: list[FileListEntry] = []
    for child in sorted(decision.resolved_path.iterdir(), key=lambda entry: entry.name.lower()):
        child_resolved = child.resolve()
        if not _is_inside(child_resolved, root_dir) or _is_protected(
            child_resolved, protected_data_dir
        ):
            continue
        logical_path = request.path / child.name if request.path != Path(".") else Path(child.name)
        metadata = _metadata_response(child_resolved, logical_path)
        entries.append(FileListEntry(name=child.name, **metadata.model_dump()))

    response = FileListResponse(path=decision.path, entries=entries)
    event_log.record(
        LogEventType.filesystem,
        "Listed guarded filesystem directory.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "entry_count": len(entries)},
    )
    return response


def evaluate_command_policy(
    request: CommandPolicyRequest,
    *,
    actor: str | None = None,
) -> CommandPolicyDecision:
    return evaluate_configured_command_policy(request, actor=actor)


def execute_guarded_command(request: CommandExecutionRequest) -> CommandExecutionResult:
    from dgentic.cli_runtime import cli_runtime_service

    return cli_runtime_service.execute_command(request)
