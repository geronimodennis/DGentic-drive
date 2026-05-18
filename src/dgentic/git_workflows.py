import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dgentic.events import event_log
from dgentic.orchestration import authorize_cli_action
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import CommandExecutionRequest, LogEventType
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

GitWorkflowAction = Literal["commit", "push", "pr"]
GitChangeReviewDecisionValue = Literal["accepted", "rejected", "pending"]

GIT_CHECKPOINT_TIMEOUT_SECONDS = 10
MAX_CHANGED_PATHS = 50
MAX_CHANGED_PATH_CHARS = 240
MAX_DIFF_REVIEW_SECTION_BYTES = 32 * 1024
MAX_COMMIT_MESSAGE_CHARS = 240
MAX_PR_TITLE_CHARS = 200
MAX_PR_BODY_CHARS = 2_000
MAX_PR_BRANCH_CHARS = 120
MAX_CHANGE_REVIEW_REASON_CHARS = 500
GH_TOKEN_ENV_KEYS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GHE_TOKEN")
PROTECTED_BRANCHES = frozenset({"main", "master", "production", "release"})
PROTECTED_FILE_SUFFIXES = frozenset({".key", ".pem", ".pfx", ".p12"})
PROTECTED_FILE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
)


class GitWorkflowCheckpointRequest(BaseModel):
    action: GitWorkflowAction
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitRawDiffReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    action: GitWorkflowAction
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    include_staged: bool = True
    include_unstaged: bool = True
    context_lines: int = Field(default=3, ge=0, le=20)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitCommitApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    commit_message: str = Field(min_length=1, max_length=MAX_COMMIT_MESSAGE_CHARS)
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitPushApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitPushRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitPrApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=MAX_PR_TITLE_CHARS)
    body: str = Field(default="", max_length=MAX_PR_BODY_CHARS)
    base_branch: str | None = Field(default=None, max_length=MAX_PR_BRANCH_CHARS)
    draft: bool = False
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitPrRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=MAX_PR_TITLE_CHARS)
    body: str = Field(default="", max_length=MAX_PR_BODY_CHARS)
    base_branch: str | None = Field(default=None, max_length=MAX_PR_BRANCH_CHARS)
    draft: bool = False
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitCommitRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    commit_message: str = Field(min_length=1, max_length=MAX_COMMIT_MESSAGE_CHARS)
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitDiffStat(BaseModel):
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    summary: str = ""


class GitRawDiffSection(BaseModel):
    scope: Literal["staged", "unstaged"]
    patch: str = ""
    patch_digest: str = ""
    redacted: bool = False
    truncated: bool = False
    omitted_protected_paths: list[str] = Field(default_factory=list)
    byte_count: int = 0
    returned_byte_count: int = 0


class GitRawDiffReview(BaseModel):
    action: GitWorkflowAction
    repo_root: Path
    cwd: Path
    branch: str
    head_sha: str = ""
    checkpoint_digest: str
    diff_stat: GitDiffStat = Field(default_factory=GitDiffStat)
    changed_paths: list[str] = Field(default_factory=list)
    changed_paths_truncated: bool = False
    sections: list[GitRawDiffSection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitChangeReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["staged", "unstaged"]
    decision: GitChangeReviewDecisionValue = "pending"
    patch_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=MAX_CHANGE_REVIEW_REASON_CHARS)
    paths: list[str] = Field(default_factory=list, max_length=100)
    redacted: bool = False
    truncated: bool = False
    omitted_protected_paths: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_must_be_safe_metadata(cls, value: object) -> str:
        return _normalize_change_review_reason(value)

    @field_validator("paths", "omitted_protected_paths")
    @classmethod
    def paths_must_be_safe_metadata(cls, value: list[str]) -> list[str]:
        return _normalize_review_paths(value)


class GitChangeReviewArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_digest: str = Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")
    action: GitWorkflowAction
    cwd: Path | None = None
    test_evidence: list[str] = Field(default_factory=list, max_length=20)
    context_lines: int = Field(default=3, ge=0, le=20)
    decisions: list[GitChangeReviewDecision] = Field(default_factory=list, max_length=20)
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("test_evidence")
    @classmethod
    def evidence_must_be_bounded(cls, value: list[str]) -> list[str]:
        return _normalize_test_evidence(value)


class GitChangeReviewArtifact(BaseModel):
    id: str
    action: GitWorkflowAction
    repo_root: Path
    cwd: Path
    branch: str
    head_sha: str = ""
    checkpoint_digest: str
    diff_stat: GitDiffStat = Field(default_factory=GitDiffStat)
    changed_paths: list[str] = Field(default_factory=list)
    changed_paths_truncated: bool = False
    decisions: list[GitChangeReviewDecision] = Field(default_factory=list)
    test_evidence_count: int = 0
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitWorkflowCheckpoint(BaseModel):
    action: GitWorkflowAction
    ready: bool
    repo_root: Path
    cwd: Path
    branch: str
    head_sha: str = ""
    upstream: str = ""
    remote_name: str = ""
    remote_url_digest: str = ""
    ahead: int = 0
    behind: int = 0
    staged_count: int = 0
    unstaged_count: int = 0
    untracked_count: int = 0
    changed_paths: list[str] = Field(default_factory=list)
    changed_paths_truncated: bool = False
    diff_stat: GitDiffStat = Field(default_factory=GitDiffStat)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checkpoint_digest: str
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitCommitRunResult(BaseModel):
    action: Literal["commit"] = "commit"
    repo_root: Path
    cwd: Path
    branch: str
    head_before: str
    head_after: str
    checkpoint_digest: str
    commit_message_digest: str
    exit_code: int
    duration_ms: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitPushRunResult(BaseModel):
    action: Literal["push"] = "push"
    repo_root: Path
    cwd: Path
    branch: str
    upstream: str
    remote_name: str
    remote_url_digest: str
    head_sha: str
    checkpoint_digest: str
    exit_code: int
    duration_ms: int
    ahead_before: int
    behind_before: int
    ahead_after: int
    behind_after: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitPrRunResult(BaseModel):
    action: Literal["pr"] = "pr"
    repo_root: Path
    cwd: Path
    branch: str
    upstream: str
    remote_name: str
    remote_url_digest: str
    head_sha: str
    checkpoint_digest: str
    title_digest: str
    body_digest: str
    base_branch: str = ""
    head_branch: str
    draft: bool
    pr_url: str = ""
    exit_code: int
    duration_ms: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class _GitStatus(BaseModel):
    branch: str
    staged_paths: list[str]
    unstaged_paths: list[str]
    untracked_paths: list[str]
    changed_paths: list[str]
    changed_paths_truncated: bool


_git_change_review_artifacts = JsonCollection(
    "git-change-review-artifacts",
    GitChangeReviewArtifact,
)


def create_git_workflow_checkpoint(
    request: GitWorkflowCheckpointRequest,
    *,
    actor: str | None = None,
) -> GitWorkflowCheckpoint:
    orchestration_decision = authorize_cli_action(
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    if not orchestration_decision.allowed:
        raise PermissionError(orchestration_decision.reason)

    cwd = _resolve_checkpoint_cwd(request.cwd)
    git_executable = _resolve_git_executable()
    repo_root = _resolve_repo_root(git_executable, cwd)
    status = _git_status(git_executable, repo_root)
    head_sha = _git_optional_output(git_executable, repo_root, ["rev-parse", "--verify", "HEAD"])
    upstream = _git_optional_output(
        git_executable,
        repo_root,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
    )
    remote_name = _branch_remote(git_executable, repo_root, status.branch)
    remote_url_digest = _remote_url_digest(git_executable, repo_root, remote_name)
    ahead, behind = _ahead_behind(git_executable, repo_root, upstream)
    diff_stat = _combined_diff_stat(git_executable, repo_root)
    staged_diff_digest = _git_diff_digest(git_executable, repo_root, cached=True)
    unstaged_diff_digest = _git_diff_digest(git_executable, repo_root, cached=False)
    evidence_count = len(request.test_evidence)
    blockers, warnings = _readiness_findings(
        action=request.action,
        branch=status.branch,
        staged_paths=status.staged_paths,
        unstaged_paths=status.unstaged_paths,
        untracked_paths=status.untracked_paths,
        evidence_count=evidence_count,
        secret_shaped_staged_additions=_staged_diff_has_secret(git_executable, repo_root),
        upstream=upstream,
        ahead=ahead,
    )
    checkpoint_digest = _checkpoint_digest(
        {
            "action": request.action,
            "repo_root": str(repo_root),
            "branch": status.branch,
            "head_sha": head_sha,
            "upstream": upstream,
            "remote_name": remote_name,
            "remote_url_digest": remote_url_digest,
            "ahead": ahead,
            "behind": behind,
            "staged_paths": status.staged_paths,
            "unstaged_paths": status.unstaged_paths,
            "untracked_paths": status.untracked_paths,
            "diff_stat": diff_stat.model_dump(),
            "staged_diff_digest": staged_diff_digest,
            "unstaged_diff_digest": unstaged_diff_digest,
            "blockers": blockers,
            "warnings": warnings,
            "test_evidence_count": evidence_count,
        }
    )
    checkpoint = GitWorkflowCheckpoint(
        action=request.action,
        ready=not blockers,
        repo_root=repo_root,
        cwd=cwd,
        branch=status.branch,
        head_sha=head_sha,
        upstream=upstream,
        remote_name=remote_name,
        remote_url_digest=remote_url_digest,
        ahead=ahead,
        behind=behind,
        staged_count=len(status.staged_paths),
        unstaged_count=len(status.unstaged_paths),
        untracked_count=len(status.untracked_paths),
        changed_paths=[_redact_path(path) for path in status.changed_paths],
        changed_paths_truncated=status.changed_paths_truncated,
        diff_stat=diff_stat,
        blockers=blockers,
        warnings=warnings,
        checkpoint_digest=checkpoint_digest,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _record_checkpoint_event(
        checkpoint,
        actor=actor or request.requested_by,
        test_evidence_count=evidence_count,
    )
    return checkpoint


def create_git_raw_diff_review(
    request: GitRawDiffReviewRequest,
    *,
    actor: str | None = None,
) -> GitRawDiffReview:
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action=request.action,
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git diff review requires a fresh matching checkpoint digest.")

    git_executable = _resolve_git_executable()
    sections: list[GitRawDiffSection] = []
    if request.include_staged:
        sections.append(
            _git_diff_review_section(
                git_executable,
                checkpoint.repo_root,
                scope="staged",
                cached=True,
                context_lines=request.context_lines,
            )
        )
    if request.include_unstaged:
        sections.append(
            _git_diff_review_section(
                git_executable,
                checkpoint.repo_root,
                scope="unstaged",
                cached=False,
                context_lines=request.context_lines,
            )
        )
    warnings = _diff_review_warnings(checkpoint, sections)
    review = GitRawDiffReview(
        action=checkpoint.action,
        repo_root=checkpoint.repo_root,
        cwd=checkpoint.cwd,
        branch=checkpoint.branch,
        head_sha=checkpoint.head_sha,
        checkpoint_digest=checkpoint.checkpoint_digest,
        diff_stat=checkpoint.diff_stat,
        changed_paths=checkpoint.changed_paths,
        changed_paths_truncated=checkpoint.changed_paths_truncated,
        sections=sections,
        warnings=warnings,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _record_diff_review_event(
        review,
        actor=actor or request.requested_by,
        test_evidence_count=len(request.test_evidence),
    )
    return review


def create_git_change_review_artifact(
    request: GitChangeReviewArtifactRequest,
    *,
    actor: str | None = None,
) -> GitChangeReviewArtifact:
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action=request.action,
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git change review artifact requires a fresh matching checkpoint digest.")

    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            checkpoint_digest=request.checkpoint_digest,
            action=request.action,
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            include_staged=True,
            include_unstaged=True,
            context_lines=request.context_lines,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    normalized_decisions = _normalize_change_review_decisions(request.decisions, review.sections)
    artifact = GitChangeReviewArtifact(
        id=f"gcr_{uuid4().hex}",
        action=checkpoint.action,
        repo_root=checkpoint.repo_root,
        cwd=checkpoint.cwd,
        branch=checkpoint.branch,
        head_sha=checkpoint.head_sha,
        checkpoint_digest=checkpoint.checkpoint_digest,
        diff_stat=checkpoint.diff_stat,
        changed_paths=checkpoint.changed_paths,
        changed_paths_truncated=checkpoint.changed_paths_truncated,
        decisions=normalized_decisions,
        test_evidence_count=len(request.test_evidence),
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        created_by=actor or request.requested_by or "system",
    )
    saved = _git_change_review_artifacts.upsert(artifact)
    _record_change_review_artifact_event(saved)
    return saved


def list_git_change_review_artifacts(
    *,
    action: GitWorkflowAction | None = None,
    checkpoint_digest: str | None = None,
    limit: int = 20,
) -> list[GitChangeReviewArtifact]:
    bounded_limit = min(max(limit, 1), 100)
    artifacts = _git_change_review_artifacts.list()
    if action:
        artifacts = [artifact for artifact in artifacts if artifact.action == action]
    if checkpoint_digest:
        artifacts = [
            artifact for artifact in artifacts if artifact.checkpoint_digest == checkpoint_digest
        ]
    return sorted(artifacts, key=lambda artifact: artifact.created_at, reverse=True)[:bounded_limit]


def get_git_change_review_artifact(artifact_id: str) -> GitChangeReviewArtifact:
    artifact = _git_change_review_artifacts.get(artifact_id)
    if artifact is None:
        raise KeyError(f"Git change review artifact not found: {artifact_id}")
    return artifact


def build_git_commit_approval_request(
    request: GitCommitApprovalRequest,
    *,
    actor: str | None = None,
) -> CommandExecutionRequest:
    commit_message = _validate_commit_message(request.commit_message)
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="commit",
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if not checkpoint.ready:
        raise ValueError("Git commit approval requires a ready commit checkpoint.")
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git commit approval requires a fresh matching checkpoint digest.")
    return CommandExecutionRequest(
        command=_git_commit_command(commit_message),
        cwd=checkpoint.repo_root,
        timeout_seconds=request.timeout_seconds,
        approved=False,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        workflow_binding=_git_workflow_binding(
            action="commit",
            checkpoint=checkpoint,
            command=_git_commit_command(commit_message),
            test_evidence_count=len(request.test_evidence),
        ),
    )


def run_git_commit_workflow(
    request: GitCommitRunRequest,
    *,
    actor: str | None = None,
) -> GitCommitRunResult:
    commit_message = _validate_commit_message(request.commit_message)
    commit_message_digest = _commit_message_digest(commit_message)
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="commit",
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if not checkpoint.ready:
        raise ValueError("Git commit runner requires a ready commit checkpoint.")
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git commit runner requires a fresh matching checkpoint digest.")
    git_executable = _resolve_git_executable()
    started = monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="dgentic-git-hooks-") as hooks_path:
            completed = subprocess.run(
                [
                    git_executable,
                    "--no-optional-locks",
                    "-c",
                    f"core.hooksPath={hooks_path}",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-m",
                    commit_message,
                ],
                cwd=checkpoint.repo_root,
                env=_git_environment(),
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        _record_commit_run_event(
            checkpoint=checkpoint,
            actor=actor or request.requested_by,
            exit_code=None,
            duration_ms=int((monotonic() - started) * 1000),
            status="timed_out",
            commit_message_digest=commit_message_digest,
            test_evidence_count=len(request.test_evidence),
        )
        raise TimeoutError("Git commit runner timed out.") from exc

    duration_ms = int((monotonic() - started) * 1000)
    if completed.returncode != 0:
        _record_commit_run_event(
            checkpoint=checkpoint,
            actor=actor or request.requested_by,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            status="failed",
            commit_message_digest=commit_message_digest,
            test_evidence_count=len(request.test_evidence),
        )
        raise ValueError("Git commit runner failed.")

    head_after = _git_optional_output(git_executable, checkpoint.repo_root, ["rev-parse", "HEAD"])
    result = GitCommitRunResult(
        repo_root=checkpoint.repo_root,
        cwd=checkpoint.cwd,
        branch=checkpoint.branch,
        head_before=checkpoint.head_sha,
        head_after=head_after,
        checkpoint_digest=checkpoint.checkpoint_digest,
        commit_message_digest=commit_message_digest,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _record_commit_run_event(
        checkpoint=checkpoint,
        actor=actor or request.requested_by,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        status="completed",
        commit_message_digest=commit_message_digest,
        test_evidence_count=len(request.test_evidence),
        head_after=head_after,
    )
    return result


def run_git_push_workflow(
    request: GitPushRunRequest,
    *,
    actor: str | None = None,
) -> GitPushRunResult:
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="push",
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if not checkpoint.ready:
        raise ValueError("Git push runner requires a ready push checkpoint.")
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git push runner requires a fresh matching checkpoint digest.")
    _require_push_checkpoint_for_approval(checkpoint, workflow_name="Git push runner")
    remote_name, upstream_branch = _push_target_for_checkpoint(checkpoint)
    git_executable = _resolve_git_executable()
    started = monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="dgentic-git-hooks-") as hooks_path:
            completed = subprocess.run(
                [
                    git_executable,
                    "--no-optional-locks",
                    "-c",
                    f"core.hooksPath={hooks_path}",
                    "-c",
                    "push.gpgSign=false",
                    "push",
                    "--porcelain",
                    remote_name,
                    f"HEAD:refs/heads/{upstream_branch}",
                ],
                cwd=checkpoint.repo_root,
                env=_git_environment(),
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        _record_push_run_event(
            checkpoint=checkpoint,
            actor=actor or request.requested_by,
            exit_code=None,
            duration_ms=int((monotonic() - started) * 1000),
            status="timed_out",
            test_evidence_count=len(request.test_evidence),
        )
        raise TimeoutError("Git push runner timed out.") from exc

    duration_ms = int((monotonic() - started) * 1000)
    if completed.returncode != 0:
        _record_push_run_event(
            checkpoint=checkpoint,
            actor=actor or request.requested_by,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            status="failed",
            test_evidence_count=len(request.test_evidence),
        )
        raise ValueError("Git push runner failed.")

    ahead_after, behind_after = _ahead_behind(
        git_executable, checkpoint.repo_root, checkpoint.upstream
    )
    result = GitPushRunResult(
        repo_root=checkpoint.repo_root,
        cwd=checkpoint.cwd,
        branch=checkpoint.branch,
        upstream=checkpoint.upstream,
        remote_name=checkpoint.remote_name,
        remote_url_digest=checkpoint.remote_url_digest,
        head_sha=checkpoint.head_sha,
        checkpoint_digest=checkpoint.checkpoint_digest,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        ahead_before=checkpoint.ahead,
        behind_before=checkpoint.behind,
        ahead_after=ahead_after,
        behind_after=behind_after,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _record_push_run_event(
        checkpoint=checkpoint,
        actor=actor or request.requested_by,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        status="completed",
        test_evidence_count=len(request.test_evidence),
        ahead_after=ahead_after,
        behind_after=behind_after,
    )
    return result


def run_git_pr_workflow(
    request: GitPrRunRequest,
    *,
    actor: str | None = None,
) -> GitPrRunResult:
    title = _validate_pr_text(
        request.title,
        field_name="Git PR title",
        max_chars=MAX_PR_TITLE_CHARS,
        allow_empty=False,
    )
    body = _validate_pr_text(
        request.body,
        field_name="Git PR body",
        max_chars=MAX_PR_BODY_CHARS,
        allow_empty=True,
    )
    base_branch = _validate_optional_pr_branch(request.base_branch, field_name="Git PR base branch")
    title_digest = _text_digest(title)
    body_digest = _text_digest(body)
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="pr",
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if not checkpoint.ready:
        raise ValueError("Git PR runner requires a ready PR checkpoint.")
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git PR runner requires a fresh matching checkpoint digest.")
    _require_pr_checkpoint_for_approval(checkpoint, workflow_name="Git PR runner")
    head_branch = _validate_pr_branch(checkpoint.branch, field_name="Git PR head branch")
    git_executable = _resolve_git_executable()
    gh_executable = _resolve_gh_executable()
    remote_host = _remote_url_host(git_executable, checkpoint.repo_root, checkpoint.remote_name)
    if not remote_host:
        raise ValueError("Git PR runner requires an upstream remote host.")
    gh_config_dir = tempfile.TemporaryDirectory(prefix="dgentic-gh-config-")
    started = monotonic()
    try:
        with gh_config_dir as isolated_config_dir:
            completed = subprocess.run(
                [
                    gh_executable,
                    *_gh_pr_create_args(
                        title=title,
                        body=body,
                        base_branch=base_branch,
                        head_branch=head_branch,
                        draft=request.draft,
                    ),
                ],
                cwd=checkpoint.repo_root,
                env=_gh_environment(Path(isolated_config_dir)),
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        _record_pr_run_event(
            checkpoint=checkpoint,
            actor=actor or request.requested_by,
            exit_code=None,
            duration_ms=int((monotonic() - started) * 1000),
            status="timed_out",
            title_digest=title_digest,
            body_digest=body_digest,
            base_branch=base_branch or "",
            head_branch=head_branch,
            draft=request.draft,
            test_evidence_count=len(request.test_evidence),
        )
        raise TimeoutError("Git PR runner timed out.") from exc

    duration_ms = int((monotonic() - started) * 1000)
    if completed.returncode != 0:
        _record_pr_run_event(
            checkpoint=checkpoint,
            actor=actor or request.requested_by,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            status="failed",
            title_digest=title_digest,
            body_digest=body_digest,
            base_branch=base_branch or "",
            head_branch=head_branch,
            draft=request.draft,
            test_evidence_count=len(request.test_evidence),
        )
        raise ValueError("Git PR runner failed.")

    pr_url = _extract_pr_url(completed.stdout, allowed_host=remote_host)
    result = GitPrRunResult(
        repo_root=checkpoint.repo_root,
        cwd=checkpoint.cwd,
        branch=checkpoint.branch,
        upstream=checkpoint.upstream,
        remote_name=checkpoint.remote_name,
        remote_url_digest=checkpoint.remote_url_digest,
        head_sha=checkpoint.head_sha,
        checkpoint_digest=checkpoint.checkpoint_digest,
        title_digest=title_digest,
        body_digest=body_digest,
        base_branch=base_branch or "",
        head_branch=head_branch,
        draft=request.draft,
        pr_url=pr_url,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _record_pr_run_event(
        checkpoint=checkpoint,
        actor=actor or request.requested_by,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        status="completed",
        title_digest=title_digest,
        body_digest=body_digest,
        base_branch=base_branch or "",
        head_branch=head_branch,
        draft=request.draft,
        test_evidence_count=len(request.test_evidence),
        pr_url=pr_url,
    )
    return result


def build_git_push_approval_request(
    request: GitPushApprovalRequest,
    *,
    actor: str | None = None,
) -> CommandExecutionRequest:
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="push",
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if not checkpoint.ready:
        raise ValueError("Git push approval requires a ready push checkpoint.")
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git push approval requires a fresh matching checkpoint digest.")
    _require_push_checkpoint_for_approval(checkpoint)
    return CommandExecutionRequest(
        command="git push",
        cwd=checkpoint.repo_root,
        timeout_seconds=request.timeout_seconds,
        approved=False,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        workflow_binding=_git_workflow_binding(
            action="push",
            checkpoint=checkpoint,
            command="git push",
            test_evidence_count=len(request.test_evidence),
        ),
    )


def build_git_pr_approval_request(
    request: GitPrApprovalRequest,
    *,
    actor: str | None = None,
) -> CommandExecutionRequest:
    title = _validate_pr_text(
        request.title,
        field_name="Git PR title",
        max_chars=MAX_PR_TITLE_CHARS,
        allow_empty=False,
    )
    body = _validate_pr_text(
        request.body,
        field_name="Git PR body",
        max_chars=MAX_PR_BODY_CHARS,
        allow_empty=True,
    )
    base_branch = _validate_optional_pr_branch(request.base_branch, field_name="Git PR base branch")
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="pr",
            cwd=request.cwd,
            test_evidence=request.test_evidence,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=actor,
    )
    if not checkpoint.ready:
        raise ValueError("Git PR approval requires a ready PR checkpoint.")
    if checkpoint.checkpoint_digest != request.checkpoint_digest:
        raise ValueError("Git PR approval requires a fresh matching checkpoint digest.")
    _require_pr_checkpoint_for_approval(checkpoint)
    head_branch = _validate_pr_branch(checkpoint.branch, field_name="Git PR head branch")
    command = _gh_pr_create_command(
        title=title,
        body=body,
        base_branch=base_branch,
        head_branch=head_branch,
        draft=request.draft,
    )
    return CommandExecutionRequest(
        command=command,
        cwd=checkpoint.repo_root,
        timeout_seconds=request.timeout_seconds,
        approved=False,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        workflow_binding=_git_workflow_binding(
            action="pr",
            checkpoint=checkpoint,
            command=command,
            test_evidence_count=len(request.test_evidence),
            pr_intent=_git_pr_intent_binding(
                title=title,
                body=body,
                base_branch=base_branch,
                head_branch=head_branch,
                draft=request.draft,
            ),
        ),
    )


def validate_git_workflow_approval_binding(
    binding: dict[str, object],
    *,
    request: CommandExecutionRequest,
    command: str,
    cwd: Path,
) -> None:
    action = str(binding.get("action") or "")
    expected_command = str(binding.get("command") or "")
    checkpoint_digest = str(binding.get("checkpoint_digest") or "")
    evidence_count = _binding_evidence_count(binding.get("test_evidence_count"))

    if action not in {"commit", "push", "pr"}:
        raise PermissionError("Git workflow approval action is not supported.")
    if command != expected_command:
        raise PermissionError("Git workflow approval command does not match the bound workflow.")
    if action == "commit" and not expected_command.startswith('git commit -m "'):
        raise PermissionError("Git commit workflow approval command is not supported.")
    if action == "push" and expected_command != "git push":
        raise PermissionError("Git push workflow approval command is not supported.")
    if action == "pr" and not expected_command.startswith('gh pr create --title "'):
        raise PermissionError("Git PR workflow approval command is not supported.")

    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action=action,
            cwd=cwd,
            test_evidence=["approval-bound workflow evidence"] * evidence_count,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        ),
        actor=request.requested_by,
    )
    if not checkpoint.ready:
        raise PermissionError("Git workflow approval requires a ready current checkpoint.")
    if checkpoint.checkpoint_digest != checkpoint_digest:
        raise PermissionError("Git workflow approval no longer matches current repository state.")
    for field in ("branch", "head_sha", "upstream", "remote_name", "remote_url_digest"):
        if str(binding.get(field) or "") != str(getattr(checkpoint, field)):
            raise PermissionError("Git workflow approval metadata no longer matches.")
    if action == "push":
        _require_push_checkpoint_for_approval(checkpoint, error_type=PermissionError)
    if action == "pr":
        _require_pr_checkpoint_for_approval(checkpoint, error_type=PermissionError)


def _git_workflow_binding(
    *,
    action: GitWorkflowAction,
    checkpoint: GitWorkflowCheckpoint,
    command: str,
    test_evidence_count: int,
    pr_intent: dict[str, object] | None = None,
) -> dict[str, object]:
    binding: dict[str, object] = {
        "type": "git_workflow",
        "action": action,
        "checkpoint_digest": checkpoint.checkpoint_digest,
        "command": command,
        "branch": checkpoint.branch,
        "head_sha": checkpoint.head_sha,
        "upstream": checkpoint.upstream,
        "remote_name": checkpoint.remote_name,
        "remote_url_digest": checkpoint.remote_url_digest,
        "ahead": checkpoint.ahead,
        "behind": checkpoint.behind,
        "staged_count": checkpoint.staged_count,
        "unstaged_count": checkpoint.unstaged_count,
        "untracked_count": checkpoint.untracked_count,
        "test_evidence_count": test_evidence_count,
    }
    if pr_intent is not None:
        binding["pr_intent"] = pr_intent
    return binding


def _git_pr_intent_binding(
    *,
    title: str,
    body: str,
    base_branch: str | None,
    head_branch: str,
    draft: bool,
) -> dict[str, object]:
    return {
        "title_digest": f"sha256:{sha256(title.encode('utf-8')).hexdigest()}",
        "body_digest": f"sha256:{sha256(body.encode('utf-8')).hexdigest()}",
        "base_branch": base_branch or "",
        "head_branch": head_branch,
        "draft": draft,
    }


def _binding_evidence_count(value: object) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise PermissionError("Git workflow approval has invalid evidence binding.") from exc
    if count < 1 or count > 20:
        raise PermissionError("Git workflow approval has invalid evidence binding.")
    return count


def _require_push_checkpoint_for_approval(
    checkpoint: GitWorkflowCheckpoint,
    *,
    workflow_name: str = "Git push approval",
    error_type: type[Exception] = ValueError,
) -> None:
    if not checkpoint.upstream:
        raise error_type(f"{workflow_name} requires a configured upstream branch.")
    if not checkpoint.remote_name or not checkpoint.remote_url_digest:
        raise error_type(f"{workflow_name} requires a bound upstream remote URL.")
    if checkpoint.ahead <= 0:
        raise error_type(f"{workflow_name} requires local commits ahead of upstream.")
    if checkpoint.behind > 0:
        raise error_type(f"{workflow_name} requires the branch to be current with upstream.")


def _push_target_for_checkpoint(checkpoint: GitWorkflowCheckpoint) -> tuple[str, str]:
    remote_name = checkpoint.remote_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote_name):
        raise ValueError("Git push runner has an unsupported upstream remote name.")
    upstream_prefix = f"{remote_name}/"
    if not checkpoint.upstream.startswith(upstream_prefix):
        raise ValueError("Git push runner upstream does not match the configured remote.")
    upstream_branch = _validate_pr_branch(
        checkpoint.upstream[len(upstream_prefix) :],
        field_name="Git push upstream branch",
    )
    if upstream_branch.lower() in PROTECTED_BRANCHES:
        raise ValueError("Git push runner to protected upstream branch is blocked.")
    return remote_name, upstream_branch


def _require_pr_checkpoint_for_approval(
    checkpoint: GitWorkflowCheckpoint,
    *,
    workflow_name: str = "Git PR approval",
    error_type: type[Exception] = ValueError,
) -> None:
    if not checkpoint.upstream:
        raise error_type(f"{workflow_name} requires a configured upstream branch.")
    if not checkpoint.remote_name or not checkpoint.remote_url_digest:
        raise error_type(f"{workflow_name} requires a bound upstream remote URL.")
    if checkpoint.ahead > 0:
        raise error_type(f"{workflow_name} requires the branch to be pushed before PR creation.")
    if checkpoint.behind > 0:
        raise error_type(f"{workflow_name} requires the branch to be current with upstream.")


def _normalize_test_evidence(value: list[str]) -> list[str]:
    evidence: list[str] = []
    for item in value:
        normalized = str(item).strip()
        if normalized:
            evidence.append(normalized[:500])
    return evidence


def _validate_commit_message(message: str) -> str:
    normalized = message.strip()
    if not normalized:
        raise ValueError("Git commit message must not be empty.")
    if len(normalized) > MAX_COMMIT_MESSAGE_CHARS:
        raise ValueError("Git commit message is too long.")
    if redact_sensitive_values(normalized) != normalized:
        raise ValueError("Git commit message contains secret-shaped text.")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError("Git commit message must be a single printable line.")
    if '"' in normalized:
        raise ValueError("Git commit message must not contain double quotes.")
    return normalized


def _validate_pr_text(
    value: str,
    *,
    field_name: str,
    max_chars: int,
    allow_empty: bool,
) -> str:
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty.")
    if len(normalized) > max_chars:
        raise ValueError(f"{field_name} is too long.")
    if redact_sensitive_values(normalized) != normalized:
        raise ValueError(f"{field_name} contains secret-shaped text.")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError(f"{field_name} must be a single printable line.")
    if '"' in normalized:
        raise ValueError(f"{field_name} must not contain double quotes.")
    return normalized


def _validate_optional_pr_branch(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return _validate_pr_branch(normalized, field_name=field_name)


def _validate_pr_branch(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    if len(normalized) > MAX_PR_BRANCH_CHARS:
        raise ValueError(f"{field_name} is too long.")
    if redact_sensitive_values(normalized) != normalized:
        raise ValueError(f"{field_name} contains secret-shaped text.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", normalized):
        raise ValueError(f"{field_name} contains unsupported characters.")
    if (
        ".." in normalized
        or "//" in normalized
        or normalized.endswith("/")
        or normalized.endswith(".")
        or normalized.endswith(".lock")
    ):
        raise ValueError(f"{field_name} contains unsupported ref syntax.")
    return normalized


def _git_commit_command(commit_message: str) -> str:
    return f'git commit -m "{commit_message}"'


def _commit_message_digest(commit_message: str) -> str:
    return _text_digest(commit_message)


def _text_digest(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _gh_pr_create_command(
    *,
    title: str,
    body: str,
    base_branch: str | None,
    head_branch: str,
    draft: bool,
) -> str:
    parts = [
        "gh pr create",
        f'--title "{title}"',
        f'--body "{body}"',
        f'--head "{head_branch}"',
    ]
    if base_branch:
        parts.append(f'--base "{base_branch}"')
    if draft:
        parts.append("--draft")
    return " ".join(parts)


def _gh_pr_create_args(
    *,
    title: str,
    body: str,
    base_branch: str | None,
    head_branch: str,
    draft: bool,
) -> list[str]:
    args = [
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--head",
        head_branch,
    ]
    if base_branch:
        args.extend(["--base", base_branch])
    if draft:
        args.append("--draft")
    return args


def _resolve_checkpoint_cwd(cwd: Path | None) -> Path:
    root_dir = get_settings().root_dir.resolve()
    candidate = cwd or root_dir
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Git checkpoint cwd does not exist.") from exc
    if not resolved.is_dir():
        raise ValueError("Git checkpoint cwd must be a directory.")
    if resolved != root_dir and root_dir not in resolved.parents:
        raise PermissionError("Git checkpoint cwd resolves outside configured rootDir.")
    return resolved


def _resolve_git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git executable is not available.")
    git_path = Path(executable)
    root_dir = get_settings().root_dir.resolve()
    try:
        resolved = git_path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("Git executable is not available.") from exc
    if resolved == root_dir or root_dir in resolved.parents:
        raise PermissionError("Git executable resolves inside configured rootDir.")
    return str(resolved)


def _resolve_gh_executable() -> str:
    executable = shutil.which("gh")
    if executable is None:
        raise RuntimeError("GitHub CLI executable is not available.")
    gh_path = Path(executable)
    root_dir = get_settings().root_dir.resolve()
    try:
        resolved = gh_path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("GitHub CLI executable is not available.") from exc
    if resolved == root_dir or root_dir in resolved.parents:
        raise PermissionError("GitHub CLI executable resolves inside configured rootDir.")
    return str(resolved)


def _resolve_repo_root(git_executable: str, cwd: Path) -> Path:
    repo_root_text = _run_git(git_executable, cwd, ["rev-parse", "--show-toplevel"]).strip()
    if not repo_root_text:
        raise ValueError("Git repository root could not be determined.")
    try:
        repo_root = Path(repo_root_text).resolve(strict=True)
    except OSError as exc:
        raise ValueError("Git repository root could not be determined.") from exc
    root_dir = get_settings().root_dir.resolve()
    if repo_root != root_dir and root_dir not in repo_root.parents:
        raise PermissionError("Git repository root resolves outside configured rootDir.")
    return repo_root


def _run_git(git_executable: str, cwd: Path, args: list[str]) -> str:
    completed = subprocess.run(
        [git_executable, "--no-optional-locks", *args],
        cwd=cwd,
        env=_git_environment(),
        capture_output=True,
        text=True,
        timeout=GIT_CHECKPOINT_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        detail = redact_sensitive_values((completed.stderr or completed.stdout).strip())
        message = "Git checkpoint inspection failed."
        if detail:
            message = f"{message} {detail[:300]}"
        raise ValueError(message)
    return completed.stdout


def _git_optional_output(git_executable: str, cwd: Path, args: list[str]) -> str:
    try:
        return _run_git(git_executable, cwd, args).strip()
    except ValueError:
        return ""


def _git_environment() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in (
        "COMSPEC",
        "HOME",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    ):
        if key in os.environ:
            env[key] = os.environ[key]
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_PAGER"] = "cat"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _gh_environment(config_dir: Path) -> dict[str, str]:
    env = _git_environment()
    env.pop("HOME", None)
    token_found = False
    for key in GH_TOKEN_ENV_KEYS:
        token_value = os.environ.get(key)
        if token_value:
            env[key] = token_value
            token_found = True
    if not token_found:
        raise ValueError("Git PR runner requires an explicit GitHub CLI token environment.")
    env["GH_CONFIG_DIR"] = str(config_dir)
    env["GH_PROMPT_DISABLED"] = "1"
    env["NO_COLOR"] = "1"
    return env


def _extract_pr_url(output: str, *, allowed_host: str) -> str:
    candidates: list[str] = []
    for token in output.split():
        candidate = token.strip().strip("\"'<>()[]{},.;")
        if _is_safe_pr_url(candidate, allowed_host=allowed_host):
            candidates.append(candidate)
    unique_candidates = list(dict.fromkeys(candidates))
    if len(unique_candidates) == 1:
        return unique_candidates[0]
    return ""


def _is_safe_pr_url(candidate: str, *, allowed_host: str) -> bool:
    if not candidate.startswith("https://"):
        return False
    if len(candidate) > 500 or redact_sensitive_values(candidate) != candidate:
        return False
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname != allowed_host.lower()
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return False
    if not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", parsed.netloc):
        return False
    raw_path_parts = parsed.path.split("/")
    if len(raw_path_parts) != 5 or raw_path_parts[0] != "":
        return False
    path_parts = raw_path_parts[1:]
    if len(path_parts) != 4 or path_parts[2] != "pull" or not path_parts[3].isdigit():
        return False
    owner, repo = path_parts[0], path_parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return False
    for part in path_parts:
        if redact_sensitive_values(part) != part:
            return False
    return True


def _git_status(git_executable: str, repo_root: Path) -> _GitStatus:
    output = _run_git(
        git_executable,
        repo_root,
        ["status", "--porcelain=v1", "--branch", "--untracked-files=normal"],
    )
    branch = ""
    staged_paths: list[str] = []
    unstaged_paths: list[str] = []
    untracked_paths: list[str] = []
    changed_paths: list[str] = []
    for line in output.splitlines():
        if line.startswith("## "):
            branch = _parse_status_branch(line[3:])
            continue
        if len(line) < 4:
            continue
        status = line[:2]
        path = _normalize_status_path(line[3:])
        if not path:
            continue
        if status == "??":
            untracked_paths.append(path)
        else:
            if status[0] != " ":
                staged_paths.append(path)
            if status[1] != " ":
                unstaged_paths.append(path)
        if path not in changed_paths:
            changed_paths.append(path)
    return _GitStatus(
        branch=branch or "DETACHED",
        staged_paths=staged_paths,
        unstaged_paths=unstaged_paths,
        untracked_paths=untracked_paths,
        changed_paths=changed_paths[:MAX_CHANGED_PATHS],
        changed_paths_truncated=len(changed_paths) > MAX_CHANGED_PATHS,
    )


def _parse_status_branch(raw_branch: str) -> str:
    branch = raw_branch.strip()
    if branch.startswith("No commits yet on "):
        branch = branch.removeprefix("No commits yet on ").strip()
    if "..." in branch:
        branch = branch.split("...", 1)[0].strip()
    if " [" in branch:
        branch = branch.split(" [", 1)[0].strip()
    return redact_sensitive_values(branch)[:120] or "DETACHED"


def _normalize_status_path(path: str) -> str:
    normalized = path.strip()
    if " -> " in normalized:
        normalized = normalized.rsplit(" -> ", 1)[-1]
    return _redact_path(normalized)


def _ahead_behind(git_executable: str, repo_root: Path, upstream: str) -> tuple[int, int]:
    if not upstream:
        return 0, 0
    output = _git_optional_output(
        git_executable,
        repo_root,
        ["rev-list", "--left-right", "--count", "HEAD...@{u}"],
    )
    parts = output.split()
    if len(parts) != 2:
        return 0, 0
    try:
        return max(0, int(parts[0])), max(0, int(parts[1]))
    except ValueError:
        return 0, 0


def _branch_remote(git_executable: str, repo_root: Path, branch: str) -> str:
    if not branch or branch == "DETACHED":
        return ""
    remote = _git_optional_output(
        git_executable,
        repo_root,
        ["config", "--get", f"branch.{branch}.remote"],
    )
    return redact_sensitive_values(remote)[:120]


def _remote_url_digest(git_executable: str, repo_root: Path, remote_name: str) -> str:
    if not remote_name:
        return ""
    remote_url = _git_optional_output(git_executable, repo_root, ["remote", "get-url", remote_name])
    if not remote_url:
        return ""
    return f"sha256:{sha256(remote_url.encode('utf-8')).hexdigest()}"


def _remote_url_host(git_executable: str, repo_root: Path, remote_name: str) -> str:
    if not remote_name:
        return ""
    remote_url = _git_optional_output(git_executable, repo_root, ["remote", "get-url", remote_name])
    return _parse_remote_url_host(remote_url)


def _parse_remote_url_host(remote_url: str) -> str:
    normalized = remote_url.strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.hostname:
        return parsed.hostname.lower()
    if re.match(r"^[A-Za-z]:[\\/]", normalized):
        return ""
    match = re.match(r"(?:[^@/\s]+@)?(?P<host>[A-Za-z0-9.-]+):", normalized)
    if match:
        return match.group("host").lower()
    return ""


def _combined_diff_stat(git_executable: str, repo_root: Path) -> GitDiffStat:
    staged = _parse_shortstat(
        _git_optional_output(
            git_executable,
            repo_root,
            ["diff", "--cached", "--no-ext-diff", "--shortstat"],
        )
    )
    unstaged = _parse_shortstat(
        _git_optional_output(
            git_executable,
            repo_root,
            ["diff", "--no-ext-diff", "--shortstat"],
        )
    )
    stat = GitDiffStat(
        files_changed=staged.files_changed + unstaged.files_changed,
        insertions=staged.insertions + unstaged.insertions,
        deletions=staged.deletions + unstaged.deletions,
    )
    parts = [f"{stat.files_changed} files changed"]
    if stat.insertions:
        parts.append(f"{stat.insertions} insertions")
    if stat.deletions:
        parts.append(f"{stat.deletions} deletions")
    stat.summary = ", ".join(parts) if stat.files_changed else "No tracked diff changes."
    return stat


def _git_diff_digest(git_executable: str, repo_root: Path, *, cached: bool) -> str:
    args = ["diff", "--no-ext-diff"]
    if cached:
        args.append("--cached")
    output = _git_optional_output(git_executable, repo_root, args)
    return f"sha256:{sha256(output.encode('utf-8')).hexdigest()}"


def _git_diff_review_section(
    git_executable: str,
    repo_root: Path,
    *,
    scope: Literal["staged", "unstaged"],
    cached: bool,
    context_lines: int,
) -> GitRawDiffSection:
    paths = _git_diff_name_only(git_executable, repo_root, cached=cached)
    allowed_paths: list[str] = []
    omitted_paths: list[str] = []
    for path in paths:
        if _is_protected_path(path) or redact_sensitive_values(path) != path:
            omitted_paths.append(_redact_path(path))
        else:
            allowed_paths.append(path)

    raw_patch = ""
    if allowed_paths:
        args = [
            "diff",
            "--no-ext-diff",
            "--no-color",
            f"--unified={context_lines}",
        ]
        if cached:
            args.append("--cached")
        args.extend(["--", *allowed_paths])
        raw_patch = _run_git(git_executable, repo_root, args)

    redacted_patch = redact_sensitive_values(raw_patch)
    patch, truncated = _truncate_diff_review_patch(redacted_patch)
    return GitRawDiffSection(
        scope=scope,
        patch=patch,
        patch_digest=_text_digest(redacted_patch),
        redacted=redacted_patch != raw_patch,
        truncated=truncated,
        omitted_protected_paths=omitted_paths,
        byte_count=len(redacted_patch.encode("utf-8")),
        returned_byte_count=len(patch.encode("utf-8")),
    )


def _git_diff_name_only(git_executable: str, repo_root: Path, *, cached: bool) -> list[str]:
    args = ["diff", "--no-ext-diff", "--name-only", "-z"]
    if cached:
        args.append("--cached")
    output = _git_optional_output(git_executable, repo_root, args)
    return [path for path in output.split("\0") if path]


def _truncate_diff_review_patch(patch: str) -> tuple[str, bool]:
    encoded = patch.encode("utf-8")
    if len(encoded) <= MAX_DIFF_REVIEW_SECTION_BYTES:
        return patch, False
    marker = "\n... [diff review truncated]\n"
    budget = max(0, MAX_DIFF_REVIEW_SECTION_BYTES - len(marker.encode("utf-8")))
    truncated = encoded[:budget].decode("utf-8", errors="ignore").rstrip()
    return f"{truncated}{marker}", True


def _diff_review_warnings(
    checkpoint: GitWorkflowCheckpoint,
    sections: list[GitRawDiffSection],
) -> list[str]:
    warnings: list[str] = []
    if checkpoint.untracked_count:
        warnings.append("Untracked file contents are not included in raw diff review.")
    if checkpoint.blockers:
        warnings.append("Checkpoint blockers are still present; review readiness before approval.")
    if any(section.redacted for section in sections):
        warnings.append("Secret-shaped patch content was redacted before returning this review.")
    if any(section.truncated for section in sections):
        warnings.append("Large patch content was truncated for bounded review output.")
    if any(section.omitted_protected_paths for section in sections):
        warnings.append("Protected or secret-shaped paths were omitted from patch content.")
    if not sections:
        warnings.append("No diff sections were requested.")
    elif not any(section.patch for section in sections):
        warnings.append("No tracked staged or unstaged patch content is available.")
    return warnings


def _parse_shortstat(output: str) -> GitDiffStat:
    if not output.strip():
        return GitDiffStat()
    files_changed = _first_int(r"(\d+)\s+files?\s+changed", output)
    insertions = _first_int(r"(\d+)\s+insertions?", output)
    deletions = _first_int(r"(\d+)\s+deletions?", output)
    return GitDiffStat(files_changed=files_changed, insertions=insertions, deletions=deletions)


def _first_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _staged_diff_has_secret(git_executable: str, repo_root: Path) -> bool:
    output = _git_optional_output(
        git_executable,
        repo_root,
        ["diff", "--cached", "--no-ext-diff", "--unified=0"],
    )
    for line in output.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if redact_sensitive_values(line) != line:
            return True
    return False


def _readiness_findings(
    *,
    action: GitWorkflowAction,
    branch: str,
    staged_paths: list[str],
    unstaged_paths: list[str],
    untracked_paths: list[str],
    evidence_count: int,
    secret_shaped_staged_additions: bool,
    upstream: str,
    ahead: int,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    protected_paths = [path for path in staged_paths if _is_protected_path(path)]

    if action == "commit" and not staged_paths:
        blockers.append("Commit preparation requires staged changes.")
    if action in {"commit", "push", "pr"} and evidence_count == 0:
        blockers.append("Git workflow preparation requires test evidence.")
    if protected_paths:
        blockers.append("Staged protected files require manual review outside git checkpoint.")
    if secret_shaped_staged_additions:
        blockers.append("Staged diff contains secret-shaped additions.")

    if action in {"push", "pr"}:
        if branch.lower() in PROTECTED_BRANCHES:
            blockers.append("Push and PR preparation from protected branches is blocked.")
        if staged_paths or unstaged_paths or untracked_paths:
            blockers.append("Push and PR preparation requires a clean local worktree.")
        if not upstream:
            warnings.append("No upstream branch is configured.")
        elif ahead == 0:
            warnings.append("Current branch has no local commits ahead of upstream.")
        if action == "pr":
            warnings.append(
                "PR checkpoint produces readiness metadata only; no network call is made."
            )

    if action == "commit" and (unstaged_paths or untracked_paths):
        warnings.append("Unstaged or untracked changes are present outside the staged commit set.")
    return blockers, warnings


def _is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return False
    posix_path = PurePosixPath(normalized)
    parts = [part.lower() for part in posix_path.parts]
    name = parts[-1]
    if ".dgentic" in parts or name in PROTECTED_FILE_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in PROTECTED_FILE_SUFFIXES)


def _redact_path(path: str) -> str:
    return redact_sensitive_values(path.strip())[:MAX_CHANGED_PATH_CHARS]


def _normalize_review_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for path in paths:
        redacted = _redact_path(str(path))
        if redacted and redacted not in seen:
            seen.add(redacted)
            normalized.append(redacted)
    return normalized


def _normalize_change_review_reason(value: object) -> str:
    normalized = " ".join(str(value or "").split())
    return redact_sensitive_values(normalized)[:MAX_CHANGE_REVIEW_REASON_CHARS]


def _diff_section_paths(section: GitRawDiffSection) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+)$", section.patch or "", re.MULTILINE):
        path = _redact_path(match.group(2) or match.group(1))
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _normalize_change_review_decisions(
    decisions: list[GitChangeReviewDecision],
    sections: list[GitRawDiffSection],
) -> list[GitChangeReviewDecision]:
    section_by_key = {(section.scope, section.patch_digest): section for section in sections}
    normalized: list[GitChangeReviewDecision] = []
    seen: set[tuple[str, str]] = set()
    for decision in decisions:
        key = (decision.scope, decision.patch_digest)
        if key in seen:
            raise ValueError("Git change review decisions must not contain duplicates.")
        section = section_by_key.get(key)
        if section is None:
            raise ValueError("Git change review decision does not match the current diff review.")
        seen.add(key)
        normalized.append(
            GitChangeReviewDecision(
                scope=decision.scope,
                decision=decision.decision,
                patch_digest=section.patch_digest,
                reason=decision.reason,
                paths=_diff_section_paths(section),
                redacted=section.redacted,
                truncated=section.truncated,
                omitted_protected_paths=section.omitted_protected_paths,
            )
        )
    return normalized


def _checkpoint_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def _record_checkpoint_event(
    checkpoint: GitWorkflowCheckpoint,
    *,
    actor: str | None,
    test_evidence_count: int,
) -> None:
    event_log.record(
        LogEventType.cli,
        "Created git workflow checkpoint.",
        actor=actor or "system",
        subject_id=checkpoint.checkpoint_digest,
        metadata={
            "action": checkpoint.action,
            "ready": checkpoint.ready,
            "repo_root": str(checkpoint.repo_root),
            "branch": checkpoint.branch,
            "head_sha": checkpoint.head_sha,
            "upstream": checkpoint.upstream,
            "remote_name": checkpoint.remote_name,
            "remote_url_digest": checkpoint.remote_url_digest,
            "ahead": checkpoint.ahead,
            "behind": checkpoint.behind,
            "staged_count": checkpoint.staged_count,
            "unstaged_count": checkpoint.unstaged_count,
            "untracked_count": checkpoint.untracked_count,
            "changed_paths_truncated": checkpoint.changed_paths_truncated,
            "diff_stat": checkpoint.diff_stat.model_dump(),
            "blocker_count": len(checkpoint.blockers),
            "warning_count": len(checkpoint.warnings),
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence_count": test_evidence_count,
            "requested_by": checkpoint.requested_by,
            "agent_id": checkpoint.agent_id,
            "agent_role": checkpoint.agent_role,
            "task_id": checkpoint.task_id,
        },
    )


def _record_diff_review_event(
    review: GitRawDiffReview,
    *,
    actor: str | None,
    test_evidence_count: int,
) -> None:
    event_log.record(
        LogEventType.cli,
        "Created git raw diff review.",
        actor=actor or "system",
        subject_id=review.checkpoint_digest,
        metadata={
            "action": review.action,
            "repo_root": str(review.repo_root),
            "branch": review.branch,
            "head_sha": review.head_sha,
            "checkpoint_digest": review.checkpoint_digest,
            "section_count": len(review.sections),
            "redacted_sections": sum(1 for section in review.sections if section.redacted),
            "truncated_sections": sum(1 for section in review.sections if section.truncated),
            "omitted_protected_path_count": sum(
                len(section.omitted_protected_paths) for section in review.sections
            ),
            "returned_byte_count": sum(section.returned_byte_count for section in review.sections),
            "warning_count": len(review.warnings),
            "test_evidence_count": test_evidence_count,
            "requested_by": review.requested_by,
            "agent_id": review.agent_id,
            "agent_role": review.agent_role,
            "task_id": review.task_id,
        },
    )


def _record_change_review_artifact_event(artifact: GitChangeReviewArtifact) -> None:
    counts = {
        "accepted": sum(1 for decision in artifact.decisions if decision.decision == "accepted"),
        "rejected": sum(1 for decision in artifact.decisions if decision.decision == "rejected"),
        "pending": sum(1 for decision in artifact.decisions if decision.decision == "pending"),
    }
    event_log.record(
        LogEventType.cli,
        "Saved git change review artifact.",
        actor=artifact.created_by,
        subject_id=artifact.id,
        metadata={
            "action": artifact.action,
            "repo_root": str(artifact.repo_root),
            "branch": artifact.branch,
            "head_sha": artifact.head_sha,
            "checkpoint_digest": artifact.checkpoint_digest,
            "decision_counts": counts,
            "section_count": len(artifact.decisions),
            "redacted_sections": sum(1 for decision in artifact.decisions if decision.redacted),
            "truncated_sections": sum(1 for decision in artifact.decisions if decision.truncated),
            "omitted_protected_path_count": sum(
                len(decision.omitted_protected_paths) for decision in artifact.decisions
            ),
            "test_evidence_count": artifact.test_evidence_count,
            "requested_by": artifact.requested_by,
            "agent_id": artifact.agent_id,
            "agent_role": artifact.agent_role,
            "task_id": artifact.task_id,
        },
    )


def _record_commit_run_event(
    *,
    checkpoint: GitWorkflowCheckpoint,
    actor: str | None,
    exit_code: int | None,
    duration_ms: int,
    status: str,
    commit_message_digest: str,
    test_evidence_count: int,
    head_after: str = "",
) -> None:
    event_log.record(
        LogEventType.cli,
        "Ran direct git commit workflow.",
        actor=actor or "system",
        subject_id=checkpoint.checkpoint_digest,
        metadata={
            "action": "commit",
            "status": status,
            "repo_root": str(checkpoint.repo_root),
            "branch": checkpoint.branch,
            "head_before": checkpoint.head_sha,
            "head_after": head_after,
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message_digest": commit_message_digest,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "staged_count": checkpoint.staged_count,
            "diff_stat": checkpoint.diff_stat.model_dump(),
            "test_evidence_count": test_evidence_count,
            "requested_by": checkpoint.requested_by,
            "agent_id": checkpoint.agent_id,
            "agent_role": checkpoint.agent_role,
            "task_id": checkpoint.task_id,
        },
    )


def _record_push_run_event(
    *,
    checkpoint: GitWorkflowCheckpoint,
    actor: str | None,
    exit_code: int | None,
    duration_ms: int,
    status: str,
    test_evidence_count: int,
    ahead_after: int | None = None,
    behind_after: int | None = None,
) -> None:
    event_log.record(
        LogEventType.cli,
        "Ran direct git push workflow.",
        actor=actor or "system",
        subject_id=checkpoint.checkpoint_digest,
        metadata={
            "action": "push",
            "status": status,
            "repo_root": str(checkpoint.repo_root),
            "branch": checkpoint.branch,
            "upstream": checkpoint.upstream,
            "remote_name": checkpoint.remote_name,
            "remote_url_digest": checkpoint.remote_url_digest,
            "head_sha": checkpoint.head_sha,
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "ahead_before": checkpoint.ahead,
            "behind_before": checkpoint.behind,
            "ahead_after": ahead_after,
            "behind_after": behind_after,
            "test_evidence_count": test_evidence_count,
            "requested_by": checkpoint.requested_by,
            "agent_id": checkpoint.agent_id,
            "agent_role": checkpoint.agent_role,
            "task_id": checkpoint.task_id,
        },
    )


def _record_pr_run_event(
    *,
    checkpoint: GitWorkflowCheckpoint,
    actor: str | None,
    exit_code: int | None,
    duration_ms: int,
    status: str,
    title_digest: str,
    body_digest: str,
    base_branch: str,
    head_branch: str,
    draft: bool,
    test_evidence_count: int,
    pr_url: str = "",
) -> None:
    event_log.record(
        LogEventType.cli,
        "Ran direct git PR workflow.",
        actor=actor or "system",
        subject_id=checkpoint.checkpoint_digest,
        metadata={
            "action": "pr",
            "status": status,
            "repo_root": str(checkpoint.repo_root),
            "branch": checkpoint.branch,
            "upstream": checkpoint.upstream,
            "remote_name": checkpoint.remote_name,
            "remote_url_digest": checkpoint.remote_url_digest,
            "head_sha": checkpoint.head_sha,
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title_digest": title_digest,
            "body_digest": body_digest,
            "base_branch": base_branch,
            "head_branch": head_branch,
            "draft": draft,
            "pr_url_digest": _text_digest(pr_url) if pr_url else "",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "test_evidence_count": test_evidence_count,
            "requested_by": checkpoint.requested_by,
            "agent_id": checkpoint.agent_id,
            "agent_role": checkpoint.agent_role,
            "task_id": checkpoint.task_id,
        },
    )
