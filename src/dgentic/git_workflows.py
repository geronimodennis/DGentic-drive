import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from dgentic.events import event_log
from dgentic.orchestration import authorize_cli_action
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings

GitWorkflowAction = Literal["commit", "push", "pr"]

GIT_CHECKPOINT_TIMEOUT_SECONDS = 10
MAX_CHANGED_PATHS = 50
MAX_CHANGED_PATH_CHARS = 240
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
        evidence: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if normalized:
                evidence.append(normalized[:500])
        return evidence


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
    ahead, behind = _ahead_behind(git_executable, repo_root, upstream)
    diff_stat = _combined_diff_stat(git_executable, repo_root)
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
            "ahead": ahead,
            "behind": behind,
            "staged_paths": status.staged_paths,
            "unstaged_paths": status.unstaged_paths,
            "untracked_paths": status.untracked_paths,
            "diff_stat": diff_stat.model_dump(),
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
