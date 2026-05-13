import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dgentic.events import event_log
from dgentic.orchestration import authorize_cli_action
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import CommandExecutionRequest, LogEventType
from dgentic.settings import get_settings

GitWorkflowAction = Literal["commit", "push", "pr"]

GIT_CHECKPOINT_TIMEOUT_SECONDS = 10
MAX_CHANGED_PATHS = 50
MAX_CHANGED_PATH_CHARS = 240
MAX_COMMIT_MESSAGE_CHARS = 240
MAX_PR_TITLE_CHARS = 200
MAX_PR_BODY_CHARS = 2_000
MAX_PR_BRANCH_CHARS = 120
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


class GitDiffStat(BaseModel):
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    summary: str = ""


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


class _GitStatus(BaseModel):
    branch: str
    staged_paths: list[str]
    unstaged_paths: list[str]
    untracked_paths: list[str]
    changed_paths: list[str]
    changed_paths_truncated: bool


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
    error_type: type[Exception] = ValueError,
) -> None:
    if not checkpoint.upstream:
        raise error_type("Git push approval requires a configured upstream branch.")
    if not checkpoint.remote_name or not checkpoint.remote_url_digest:
        raise error_type("Git push approval requires a bound upstream remote URL.")
    if checkpoint.ahead <= 0:
        raise error_type("Git push approval requires local commits ahead of upstream.")
    if checkpoint.behind > 0:
        raise error_type("Git push approval requires the branch to be current with upstream.")


def _require_pr_checkpoint_for_approval(
    checkpoint: GitWorkflowCheckpoint,
    *,
    error_type: type[Exception] = ValueError,
) -> None:
    if not checkpoint.upstream:
        raise error_type("Git PR approval requires a configured upstream branch.")
    if not checkpoint.remote_name or not checkpoint.remote_url_digest:
        raise error_type("Git PR approval requires a bound upstream remote URL.")
    if checkpoint.ahead > 0:
        raise error_type("Git PR approval requires the branch to be pushed before PR creation.")
    if checkpoint.behind > 0:
        raise error_type("Git PR approval requires the branch to be current with upstream.")


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
