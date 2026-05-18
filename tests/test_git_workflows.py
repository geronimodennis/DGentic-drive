import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgentic.events import event_log
from dgentic.git_workflows import (
    MAX_DIFF_REVIEW_SECTION_BYTES,
    GitChangeReviewArtifactRequest,
    GitChangeReviewDecision,
    GitRawDiffReviewRequest,
    GitWorkflowCheckpointRequest,
    create_git_change_review_artifact,
    create_git_raw_diff_review,
    create_git_workflow_checkpoint,
)
from dgentic.main import create_app
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings


@pytest.fixture
def git_workspace(tmp_path, monkeypatch) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DGENTIC_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("DGENTIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("DGENTIC_AUTH_TOKENS", raising=False)
    get_settings.cache_clear()

    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# Checkpoint\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")

    yield root_dir

    get_settings.cache_clear()


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _checkpoint(
    action: str,
    cwd: Path | None = None,
    *,
    evidence: list[str] | None = None,
):
    return create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action=action,
            cwd=cwd,
            test_evidence=evidence or ["python -m pytest tests/test_git_workflows.py -q"],
            requested_by="qa-agent",
        )
    )


def _push_ready_workspace(git_workspace: Path, *, ahead: bool = True) -> Path:
    remote_dir = git_workspace.parent / "remote.git"
    current_branch = _git(git_workspace, "branch", "--show-current").stdout.strip()
    _git(git_workspace.parent, "init", "--bare", str(remote_dir))
    _git(git_workspace, "remote", "add", "origin", str(remote_dir))
    _git(git_workspace, "push", "-u", "origin", current_branch)
    _git(git_workspace, "checkout", "-b", "feature/push-approval")
    _git(git_workspace, "push", "-u", "origin", "feature/push-approval")
    if ahead:
        git_workspace.joinpath("README.md").write_text(
            "# Checkpoint\n\nPush-ready.\n",
            encoding="utf-8",
        )
        _git(git_workspace, "add", "README.md")
        _git(git_workspace, "commit", "-m", "Add push-ready change")
    return remote_dir


def _bare_remote_head(remote_dir: Path, branch: str) -> str:
    return _git(remote_dir, "rev-parse", f"refs/heads/{branch}").stdout.strip()


def _install_fake_gh(
    bin_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    record_path: Path,
    stdout: str = "https://github.com/example/repo/pull/42\n",
    returncode: int = 0,
    token: str | None = "fake-gh-token",
) -> Path:
    bin_dir.mkdir()
    fake_script = bin_dir / "fake-gh.py"
    record_literal = json.dumps(str(record_path))
    stdout_literal = json.dumps(stdout)
    fake_script.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                f"Path({record_literal}).write_text(",
                "    json.dumps({",
                "        'argv': sys.argv[1:],",
                "        'cwd': os.getcwd(),",
                "        'env': {",
                "            key: os.environ.get(key)",
                "            for key in (",
                "                'GH_CONFIG_DIR',",
                "                'GH_PROMPT_DISABLED',",
                "                'GH_TOKEN',",
                "                'GITHUB_TOKEN',",
                "                'GH_ENTERPRISE_TOKEN',",
                "                'GHE_TOKEN',",
                "                'HOME',",
                "                'NO_COLOR',",
                "            )",
                "        },",
                "    }),",
                "    encoding='utf-8',",
                ")",
                f"sys.stdout.write({stdout_literal})",
                f"sys.exit({returncode})",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if os.name == "nt":
        launcher = bin_dir / "gh.cmd"
        launcher.write_text(
            f'@echo off\n"{sys.executable}" "{fake_script}" %*\n',
            encoding="utf-8",
        )
    else:
        launcher = bin_dir / "gh"
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{fake_script}" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)

    if token is not None:
        monkeypatch.setenv("GH_TOKEN", token)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return launcher


def test_git_checkpoint_rejects_cwd_outside_root(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    outside_dir = tmp_path / "outside"
    root_dir.mkdir()
    outside_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()

    with pytest.raises(PermissionError, match="outside configured rootDir"):
        _checkpoint("commit", outside_dir)

    get_settings.cache_clear()


def test_git_checkpoint_rejects_repo_root_outside_root(tmp_path, monkeypatch) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    outer_repo = tmp_path / "outer"
    root_dir = outer_repo / "workspace"
    root_dir.mkdir(parents=True)
    _git(outer_repo, "init")
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()

    with pytest.raises(PermissionError, match="repository root resolves outside"):
        _checkpoint("commit", root_dir)

    get_settings.cache_clear()


def test_commit_checkpoint_requires_staged_changes_and_evidence(git_workspace) -> None:
    clean = _checkpoint("commit", git_workspace)

    git_workspace.joinpath("README.md").write_text("# Checkpoint\n\nUpdated.\n", encoding="utf-8")
    _git(git_workspace, "add", "README.md")
    ready = _checkpoint("commit", git_workspace)
    missing_evidence = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(action="commit", cwd=git_workspace, test_evidence=[])
    )

    assert clean.ready is False
    assert "Commit preparation requires staged changes." in clean.blockers
    assert ready.ready is True
    assert ready.staged_count == 1
    assert ready.diff_stat.files_changed == 1
    assert missing_evidence.ready is False
    assert "Git workflow preparation requires test evidence." in missing_evidence.blockers


def test_commit_checkpoint_blocks_protected_and_secret_shaped_staged_files(
    git_workspace,
) -> None:
    git_workspace.joinpath(".env").write_text("API_KEY=env-file-secret\n", encoding="utf-8")
    _git(git_workspace, "add", ".env")
    protected = _checkpoint("commit", git_workspace)
    _git(git_workspace, "reset", "--", ".env")
    git_workspace.joinpath(".env").unlink()

    raw_secret = "super-secret-checkpoint-token"
    git_workspace.joinpath("notes.txt").write_text(
        f"ACCESS_TOKEN={raw_secret}\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "notes.txt")
    secret_shaped = _checkpoint("commit", git_workspace)
    serialized = json.dumps(secret_shaped.model_dump(mode="json"))
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )

    assert protected.ready is False
    assert (
        "Staged protected files require manual review outside git checkpoint." in protected.blockers
    )
    assert secret_shaped.ready is False
    assert "Staged diff contains secret-shaped additions." in secret_shaped.blockers
    assert raw_secret not in serialized
    assert raw_secret not in serialized_logs


def test_git_raw_diff_review_redacts_and_bounds_staged_and_unstaged_sections(
    git_workspace,
) -> None:
    staged_secret = "staged-diff-secret"
    unstaged_secret = "unstaged-diff-secret"
    git_workspace.joinpath("README.md").write_text(
        f"# Checkpoint\n\nACCESS_TOKEN={staged_secret}\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    git_workspace.joinpath("README.md").write_text(
        f"# Checkpoint\n\nACCESS_TOKEN={staged_secret}\nPASSWORD={unstaged_secret}\n",
        encoding="utf-8",
    )
    checkpoint = _checkpoint("commit", git_workspace)

    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    serialized = review.model_dump_json()
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )
    staged = next(section for section in review.sections if section.scope == "staged")
    unstaged = next(section for section in review.sections if section.scope == "unstaged")

    assert review.checkpoint_digest == checkpoint.checkpoint_digest
    assert staged.redacted is True
    assert unstaged.redacted is True
    assert "ACCESS_TOKEN=[REDACTED]" in staged.patch
    assert "PASSWORD=[REDACTED]" in unstaged.patch
    assert staged_secret not in serialized
    assert unstaged_secret not in serialized
    assert staged_secret not in serialized_logs
    assert unstaged_secret not in serialized_logs
    assert "Secret-shaped patch content was redacted before returning this review." in (
        review.warnings
    )


def test_git_raw_diff_review_rejects_stale_checkpoint_digest(git_workspace) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nFirst change.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)

    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nSecond change.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")

    with pytest.raises(ValueError, match="fresh matching checkpoint digest"):
        create_git_raw_diff_review(
            GitRawDiffReviewRequest(
                action="commit",
                cwd=git_workspace,
                checkpoint_digest=checkpoint.checkpoint_digest,
                test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
            )
        )


def test_git_raw_diff_review_omits_protected_path_patch_content(git_workspace) -> None:
    git_workspace.joinpath(".env").write_text(
        "API_KEY=protected-file-secret\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", ".env")
    checkpoint = _checkpoint("commit", git_workspace)

    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    staged = next(section for section in review.sections if section.scope == "staged")

    assert staged.patch == ""
    assert ".env" in staged.omitted_protected_paths
    assert "protected-file-secret" not in review.model_dump_json()
    assert "Protected or secret-shaped paths were omitted from patch content." in review.warnings


def test_git_raw_diff_review_truncates_large_patch_sections(git_workspace) -> None:
    omitted_tail = "TAIL_MARKER_SHOULD_BE_OMITTED"
    git_workspace.joinpath("README.md").write_text(
        f"# Checkpoint\n\n{'A' * (MAX_DIFF_REVIEW_SECTION_BYTES + 4096)}{omitted_tail}\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)

    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            include_unstaged=False,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    staged = next(section for section in review.sections if section.scope == "staged")

    assert staged.truncated is True
    assert "... [diff review truncated]" in staged.patch
    assert omitted_tail not in staged.patch
    assert staged.returned_byte_count <= MAX_DIFF_REVIEW_SECTION_BYTES
    assert staged.byte_count > staged.returned_byte_count
    assert "Large patch content was truncated for bounded review output." in review.warnings


def test_git_raw_diff_review_api_returns_checkpoint_bound_sections(git_workspace) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nAPI diff review.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/diff-reviews",
        json={
            "action": "commit",
            "cwd": str(git_workspace),
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["uv run pytest tests/test_git_workflows.py -q"],
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert [section["scope"] for section in body["sections"]] == ["staged", "unstaged"]
    assert "API diff review." in body["sections"][0]["patch"]


def test_git_change_review_artifact_persists_metadata_only(git_workspace) -> None:
    raw_secret = "artifact-diff-secret"
    git_workspace.joinpath("README.md").write_text(
        f"# Checkpoint\n\nACCESS_TOKEN={raw_secret}\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    staged = next(section for section in review.sections if section.scope == "staged")

    artifact = create_git_change_review_artifact(
        GitChangeReviewArtifactRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
            decisions=[
                GitChangeReviewDecision(
                    scope="staged",
                    decision="accepted",
                    patch_digest=staged.patch_digest,
                    reason=f"Reviewer saw API_KEY={raw_secret} and accepts the staged section.",
                    paths=["spoofed TOKEN=path-secret"],
                    redacted=False,
                )
            ],
            requested_by="qa-reviewer",
        )
    )
    serialized = artifact.model_dump_json()
    state_payload = git_workspace.parent.joinpath(
        "state",
        "git-change-review-artifacts.json",
    ).read_text(encoding="utf-8")

    assert artifact.checkpoint_digest == checkpoint.checkpoint_digest
    assert artifact.decisions[0].decision == "accepted"
    assert "Reviewer saw API_KEY=[REDACTED]" in artifact.decisions[0].reason
    assert artifact.decisions[0].paths == ["README.md"]
    assert artifact.decisions[0].redacted is True
    assert raw_secret not in serialized
    assert "ACCESS_TOKEN=[REDACTED]" not in serialized
    assert "diff --git" not in serialized
    assert raw_secret not in state_payload
    assert "ACCESS_TOKEN=[REDACTED]" not in state_payload
    assert "diff --git" not in state_payload


def test_git_change_review_artifact_api_lists_and_retrieves_saved_artifacts(
    git_workspace,
) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nAPI artifact.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    staged = next(section for section in review.sections if section.scope == "staged")
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/git/change-review-artifacts",
        json={
            "action": "commit",
            "cwd": str(git_workspace),
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["uv run pytest tests/test_git_workflows.py -q"],
            "decisions": [
                {
                    "scope": "staged",
                    "decision": "rejected",
                    "patch_digest": staged.patch_digest,
                    "reason": "Missing rollback evidence.",
                    "paths": ["README.md"],
                    "redacted": staged.redacted,
                    "truncated": staged.truncated,
                    "omitted_protected_paths": staged.omitted_protected_paths,
                }
            ],
        },
    )
    artifact = create_response.json()
    list_response = client.get(
        "/cli/git/change-review-artifacts",
        params={"action": "commit", "checkpoint_digest": checkpoint.checkpoint_digest},
    )
    get_response = client.get(f"/cli/git/change-review-artifacts/{artifact['id']}")

    assert create_response.status_code == 201
    assert artifact["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert artifact["decisions"][0]["decision"] == "rejected"
    assert artifact["decisions"][0]["reason"] == "Missing rollback evidence."
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [artifact["id"]]
    assert get_response.status_code == 200
    assert get_response.json()["id"] == artifact["id"]
    assert get_response.json()["decisions"][0]["reason"] == "Missing rollback evidence."


def test_git_change_review_artifact_bounds_and_redacts_reviewer_reason(
    git_workspace,
) -> None:
    raw_secret = "review-reason-secret-token"
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nReviewer reason.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    staged = next(section for section in review.sections if section.scope == "staged")

    artifact = create_git_change_review_artifact(
        GitChangeReviewArtifactRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
            decisions=[
                GitChangeReviewDecision(
                    scope="staged",
                    decision="rejected",
                    patch_digest=staged.patch_digest,
                    reason=f"Reject because API_KEY={raw_secret}. {'x' * 900}",
                )
            ],
        )
    )
    stored_reason = artifact.decisions[0].reason
    serialized = artifact.model_dump_json()

    assert artifact.decisions[0].decision == "rejected"
    assert len(stored_reason) <= 500
    assert "Reject because API_KEY=[REDACTED]" in stored_reason
    assert raw_secret not in stored_reason
    assert raw_secret not in serialized
    assert "diff --git" not in serialized


def test_git_change_review_artifact_rejects_stale_checkpoint_digest(
    git_workspace,
) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nFirst artifact change.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    review = create_git_raw_diff_review(
        GitRawDiffReviewRequest(
            action="commit",
            cwd=git_workspace,
            checkpoint_digest=checkpoint.checkpoint_digest,
            test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
        )
    )
    staged = next(section for section in review.sections if section.scope == "staged")
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nSecond artifact change.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")

    with pytest.raises(ValueError, match="fresh matching checkpoint digest"):
        create_git_change_review_artifact(
            GitChangeReviewArtifactRequest(
                action="commit",
                cwd=git_workspace,
                checkpoint_digest=checkpoint.checkpoint_digest,
                test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
                decisions=[
                    GitChangeReviewDecision(
                        scope="staged",
                        decision="accepted",
                        patch_digest=staged.patch_digest,
                    )
                ],
            )
        )


def test_git_change_review_artifact_rejects_mismatched_section_digest(
    git_workspace,
) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nMismatched artifact change.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)

    with pytest.raises(ValueError, match="does not match the current diff review"):
        create_git_change_review_artifact(
            GitChangeReviewArtifactRequest(
                action="commit",
                cwd=git_workspace,
                checkpoint_digest=checkpoint.checkpoint_digest,
                test_evidence=["uv run pytest tests/test_git_workflows.py -q"],
                decisions=[
                    GitChangeReviewDecision(
                        scope="staged",
                        decision="accepted",
                        patch_digest=f"sha256:{'0' * 64}",
                    )
                ],
            )
        )


def test_push_and_pr_checkpoints_block_unsafe_starting_states(git_workspace) -> None:
    protected_push = _checkpoint("push", git_workspace)

    _git(git_workspace, "checkout", "-b", "feature/checkpoint")
    git_workspace.joinpath("README.md").write_text("# Checkpoint\n\nDirty.\n", encoding="utf-8")
    dirty_push = _checkpoint("push", git_workspace)
    _git(git_workspace, "checkout", "--", "README.md")
    pr_checkpoint = _checkpoint("pr", git_workspace)

    assert protected_push.ready is False
    assert "Push and PR preparation from protected branches is blocked." in protected_push.blockers
    assert dirty_push.ready is False
    assert "Push and PR preparation requires a clean local worktree." in dirty_push.blockers
    assert pr_checkpoint.ready is True
    assert "PR checkpoint produces readiness metadata only; no network call is made." in (
        pr_checkpoint.warnings
    )


def test_git_checkpoint_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# API checkpoint\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")

    cli_token = "git-checkpoint-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/checkpoints",
        headers={"Authorization": "Bearer task-token"},
        json={"action": "commit", "test_evidence": ["pytest -q"]},
    )
    allowed = client.post(
        "/cli/git/checkpoints",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "action": "commit",
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )
    logs = event_log.list(LogEventType.cli)

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["requested_by"] == expected_actor
    assert logs[-1].actor == expected_actor
    get_settings.cache_clear()


def test_git_commit_approval_api_creates_pending_approval_without_executing_commit(
    git_workspace,
) -> None:
    head_before = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nApproval-ready.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace, evidence=["python -m pytest -q"])
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add checkpoint approval",
            "test_evidence": ["python -m pytest -q"],
            "requested_by": "qa-agent",
        },
    )
    head_after = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    staged_paths = _git(git_workspace, "diff", "--cached", "--name-only").stdout.splitlines()

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["permission_mode"] == "approval_required"
    assert response.json()["command"] == 'git commit -m "Add checkpoint approval"'
    assert Path(response.json()["cwd"]) == git_workspace.resolve()
    assert response.json()["requested_by"] == "qa-agent"
    assert head_after == head_before
    assert staged_paths == ["README.md"]


def test_git_commit_approval_rejects_mismatched_checkpoint_digest(git_workspace) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nFirst staged body.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nDifferent staged body.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Reject stale digest",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approvals = client.get("/cli/approvals").json()

    assert response.status_code == 400
    assert "fresh matching checkpoint digest" in response.json()["detail"]
    assert approvals == []


def test_git_commit_approval_rejects_non_ready_checkpoint(git_workspace) -> None:
    checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Reject clean checkpoint",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approvals = client.get("/cli/approvals").json()

    assert checkpoint.ready is False
    assert response.status_code == 400
    assert "ready commit checkpoint" in response.json()["detail"]
    assert approvals == []


def test_git_commit_approval_rejects_secret_shaped_commit_message(git_workspace) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nSecret message rejection.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    raw_secret = "commit-message-secret-token"
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": f"API_KEY={raw_secret}",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approvals = client.get("/cli/approvals").json()

    assert response.status_code == 400
    assert "secret-shaped text" in response.json()["detail"]
    assert raw_secret not in response.text
    assert approvals == []


def test_git_commit_approval_revalidates_workflow_state_before_execution(
    git_workspace,
) -> None:
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nApproved staged state.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())
    create_response = client.post(
        "/cli/git/commit-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add workflow-bound commit",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer", "reason": "Commit checkpoint reviewed."},
    )
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nDifferent staged state.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")

    execute_response = client.post(f"/cli/approvals/{approval_id}/execute")
    review_response = client.get(f"/cli/approvals/{approval_id}/review")

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert execute_response.status_code == 403
    assert "no longer matches current repository state" in execute_response.json()["detail"]
    assert review_response.json()["status"] == "approved"


def test_git_commit_approval_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# Commit approval\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")
    root_dir.joinpath("README.md").write_text(
        "# Commit approval\n\nAuthenticated.\n",
        encoding="utf-8",
    )
    _git(root_dir, "add", "README.md")

    cli_token = "git-commit-approval-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="commit",
            cwd=root_dir,
            test_evidence=["pytest -q"],
            requested_by="spoofed-checkpoint-actor",
        )
    )
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/commit-approvals",
        headers={"Authorization": "Bearer task-token"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add authenticated approval",
            "test_evidence": ["pytest -q"],
        },
    )
    allowed = client.post(
        "/cli/git/commit-approvals",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add authenticated approval",
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["requested_by"] == expected_actor
    get_settings.cache_clear()


def test_git_commit_run_api_commits_locally_without_creating_approval(git_workspace) -> None:
    head_before = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nDirect runner.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace, evidence=["python -m pytest -q"])
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add direct commit runner",
            "test_evidence": ["python -m pytest -q"],
            "requested_by": "qa-agent",
        },
    )
    head_after = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    staged_paths = _git(git_workspace, "diff", "--cached", "--name-only").stdout.splitlines()
    approvals = client.get("/cli/approvals").json()
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )

    assert response.status_code == 201
    assert response.json()["action"] == "commit"
    assert response.json()["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert response.json()["commit_message_digest"].startswith("sha256:")
    assert response.json()["head_before"] == head_before
    assert response.json()["head_after"] == head_after
    assert response.json()["requested_by"] == "qa-agent"
    assert head_after != head_before
    assert staged_paths == []
    assert approvals == []
    assert "Add direct commit runner" not in serialized_logs


def test_git_commit_run_rejects_mismatched_checkpoint_digest_without_commit(
    git_workspace,
) -> None:
    head_before = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nFirst direct runner body.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nDifferent direct runner body.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Reject stale direct commit",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    head_after = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()

    assert response.status_code == 400
    assert "fresh matching checkpoint digest" in response.json()["detail"]
    assert head_after == head_before


def test_git_commit_run_rejects_non_ready_checkpoint_without_commit(git_workspace) -> None:
    head_before = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Reject clean direct commit",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    head_after = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()

    assert checkpoint.ready is False
    assert response.status_code == 400
    assert "ready commit checkpoint" in response.json()["detail"]
    assert head_after == head_before


def test_git_commit_run_blocks_protected_and_secret_staged_additions(
    git_workspace,
) -> None:
    head_before = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    git_workspace.joinpath(".env").write_text("API_KEY=direct-runner-secret\n", encoding="utf-8")
    _git(git_workspace, "add", ".env")
    protected_checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())

    protected_response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": protected_checkpoint.checkpoint_digest,
            "commit_message": "Reject protected direct commit",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    _git(git_workspace, "reset", "--", ".env")
    git_workspace.joinpath(".env").unlink()
    raw_secret = "direct-runner-token-secret"
    git_workspace.joinpath("notes.txt").write_text(
        f"ACCESS_TOKEN={raw_secret}\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "notes.txt")
    secret_checkpoint = _checkpoint("commit", git_workspace)
    secret_response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": secret_checkpoint.checkpoint_digest,
            "commit_message": "Reject secret direct commit",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    head_after = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )

    assert protected_response.status_code == 400
    assert secret_response.status_code == 400
    assert "ready commit checkpoint" in protected_response.json()["detail"]
    assert "ready commit checkpoint" in secret_response.json()["detail"]
    assert head_after == head_before
    assert raw_secret not in secret_response.text
    assert raw_secret not in serialized_logs


def test_git_commit_run_rejects_secret_and_multiline_commit_messages_without_commit(
    git_workspace,
) -> None:
    head_before = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nInvalid direct runner message.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())
    raw_secret = "direct-message-secret"

    secret_response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": f"API_KEY={raw_secret}",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    multiline_response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Reject direct commit\nwith body",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    head_after = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )

    assert secret_response.status_code == 400
    assert "secret-shaped text" in secret_response.json()["detail"]
    assert multiline_response.status_code == 400
    assert "single printable line" in multiline_response.json()["detail"]
    assert head_after == head_before
    assert raw_secret not in secret_response.text
    assert raw_secret not in serialized_logs


def test_git_commit_run_uses_empty_hooks_path(git_workspace) -> None:
    hook_marker = git_workspace / "hook-ran.txt"
    hook_path = git_workspace / ".git" / "hooks" / "pre-commit"
    hook_path.write_text(
        f"#!/bin/sh\necho hook-ran > {hook_marker.as_posix()!r}\nexit 1\n",
        encoding="utf-8",
    )
    hook_path.chmod(0o755)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nHook bypassed.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    checkpoint = _checkpoint("commit", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/commit-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add hook isolated commit",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert response.status_code == 201
    assert not hook_marker.exists()


def test_git_commit_run_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# Direct commit auth\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")
    root_dir.joinpath("README.md").write_text(
        "# Direct commit auth\n\nAuthenticated.\n",
        encoding="utf-8",
    )
    _git(root_dir, "add", "README.md")

    cli_token = "git-commit-run-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    checkpoint = create_git_workflow_checkpoint(
        GitWorkflowCheckpointRequest(
            action="commit",
            cwd=root_dir,
            test_evidence=["pytest -q"],
            requested_by="spoofed-checkpoint-actor",
        )
    )
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/commit-runs",
        headers={"Authorization": "Bearer task-token"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add authenticated direct commit",
            "test_evidence": ["pytest -q"],
        },
    )
    allowed = client.post(
        "/cli/git/commit-runs",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "commit_message": "Add authenticated direct commit",
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["requested_by"] == expected_actor
    get_settings.cache_clear()


def test_git_push_approval_api_creates_pending_approval_without_pushing(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace)
    local_head = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    remote_head_before = _git(
        git_workspace,
        "rev-parse",
        "origin/feature/push-approval",
    ).stdout.strip()
    checkpoint = _checkpoint("push", git_workspace, evidence=["python -m pytest -q"])
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest -q"],
            "requested_by": "qa-agent",
        },
    )
    remote_head_after = _git(
        git_workspace,
        "rev-parse",
        "origin/feature/push-approval",
    ).stdout.strip()

    assert checkpoint.ready is True
    assert checkpoint.ahead == 1
    assert checkpoint.upstream == "origin/feature/push-approval"
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["permission_mode"] == "approval_required"
    assert response.json()["command"] == "git push"
    assert response.json()["workflow_binding"]["action"] == "push"
    assert response.json()["workflow_binding"]["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert Path(response.json()["cwd"]) == git_workspace.resolve()
    assert remote_head_before != local_head
    assert remote_head_after == remote_head_before


def test_git_push_approval_rejects_stale_checkpoint_digest(git_workspace) -> None:
    _push_ready_workspace(git_workspace)
    checkpoint = _checkpoint("push", git_workspace)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nAnother local commit.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    _git(git_workspace, "commit", "-m", "Add stale push change")
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approvals = client.get("/cli/approvals").json()

    assert response.status_code == 400
    assert "fresh matching checkpoint digest" in response.json()["detail"]
    assert approvals == []


def test_git_push_approval_rejects_no_upstream_and_no_ahead(git_workspace) -> None:
    _git(git_workspace, "checkout", "-b", "feature/no-upstream")
    no_upstream = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    missing_upstream_response = client.post(
        "/cli/git/push-approvals",
        json={
            "checkpoint_digest": no_upstream.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    remote_dir = git_workspace.parent / "remote.git"
    _git(git_workspace.parent, "init", "--bare", str(remote_dir))
    _git(git_workspace, "remote", "add", "origin", str(remote_dir))
    _git(git_workspace, "push", "-u", "origin", "feature/no-upstream")
    no_ahead = _checkpoint("push", git_workspace)

    no_ahead_response = client.post(
        "/cli/git/push-approvals",
        json={
            "checkpoint_digest": no_ahead.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert no_upstream.ready is True
    assert missing_upstream_response.status_code == 400
    assert "configured upstream" in missing_upstream_response.json()["detail"]
    assert no_ahead.ready is True
    assert no_ahead_response.status_code == 400
    assert "local commits ahead" in no_ahead_response.json()["detail"]


def test_git_push_approval_revalidates_workflow_state_before_execution(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace)
    checkpoint = _checkpoint("push", git_workspace)
    client = TestClient(create_app())
    create_response = client.post(
        "/cli/git/push-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer", "reason": "Push checkpoint reviewed."},
    )
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nChanged after approval.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    _git(git_workspace, "commit", "-m", "Change after approval")

    execute_response = client.post(f"/cli/approvals/{approval_id}/execute")
    review_response = client.get(f"/cli/approvals/{approval_id}/review")

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert execute_response.status_code == 403
    assert "no longer matches current repository state" in execute_response.json()["detail"]
    assert review_response.json()["status"] == "approved"


def test_git_push_approval_rejects_arbitrary_remote_branch_and_flags_payload(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace)
    checkpoint = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
            "remote": "origin",
            "branch": "feature/push-approval",
            "flags": ["--force"],
        },
    )

    assert response.status_code == 422


def test_git_push_approval_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DGENTIC_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("DGENTIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("DGENTIC_AUTH_TOKENS", raising=False)
    get_settings.cache_clear()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# Push auth\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")
    _push_ready_workspace(root_dir)
    checkpoint = _checkpoint("push", root_dir, evidence=["pytest -q"])

    cli_token = "git-push-approval-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/push-approvals",
        headers={"Authorization": "Bearer task-token"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["pytest -q"],
        },
    )
    allowed = client.post(
        "/cli/git/push-approvals",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["requested_by"] == expected_actor
    get_settings.cache_clear()


def test_git_push_run_api_pushes_to_configured_upstream_without_creating_approval(
    git_workspace,
) -> None:
    remote_dir = _push_ready_workspace(git_workspace)
    local_head = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    remote_head_before = _bare_remote_head(remote_dir, "feature/push-approval")
    checkpoint = _checkpoint("push", git_workspace, evidence=["python -m pytest -q"])
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest -q"],
            "requested_by": "qa-agent",
        },
    )
    remote_head_after = _bare_remote_head(remote_dir, "feature/push-approval")
    approvals = client.get("/cli/approvals").json()
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )

    assert checkpoint.ready is True
    assert checkpoint.ahead == 1
    assert response.status_code == 201
    assert response.json()["action"] == "push"
    assert response.json()["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert response.json()["head_sha"] == local_head
    assert response.json()["ahead_before"] == 1
    assert response.json()["behind_before"] == 0
    assert response.json()["ahead_after"] == 0
    assert response.json()["behind_after"] == 0
    assert response.json()["requested_by"] == "qa-agent"
    assert remote_head_before != local_head
    assert remote_head_after == local_head
    assert approvals == []
    assert str(remote_dir) not in response.text
    assert str(remote_dir) not in serialized_logs


def test_git_push_run_rejects_stale_checkpoint_digest_without_push(git_workspace) -> None:
    remote_dir = _push_ready_workspace(git_workspace)
    remote_head_before = _bare_remote_head(remote_dir, "feature/push-approval")
    checkpoint = _checkpoint("push", git_workspace)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nAnother direct push change.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    _git(git_workspace, "commit", "-m", "Add stale direct push change")
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    remote_head_after = _bare_remote_head(remote_dir, "feature/push-approval")

    assert response.status_code == 400
    assert "fresh matching checkpoint digest" in response.json()["detail"]
    assert remote_head_after == remote_head_before


def test_git_push_run_rejects_dirty_worktree_without_push(git_workspace) -> None:
    remote_dir = _push_ready_workspace(git_workspace)
    remote_head_before = _bare_remote_head(remote_dir, "feature/push-approval")
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nDirty direct push worktree.\n",
        encoding="utf-8",
    )
    checkpoint = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    remote_head_after = _bare_remote_head(remote_dir, "feature/push-approval")

    assert checkpoint.ready is False
    assert response.status_code == 400
    assert "ready push checkpoint" in response.json()["detail"]
    assert remote_head_after == remote_head_before


def test_git_push_run_rejects_no_upstream_and_no_ahead(git_workspace) -> None:
    _git(git_workspace, "checkout", "-b", "feature/direct-no-upstream")
    no_upstream = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    missing_upstream_response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": no_upstream.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    remote_dir = git_workspace.parent / "direct-remote.git"
    _git(git_workspace.parent, "init", "--bare", str(remote_dir))
    _git(git_workspace, "remote", "add", "origin", str(remote_dir))
    _git(git_workspace, "push", "-u", "origin", "feature/direct-no-upstream")
    no_ahead = _checkpoint("push", git_workspace)

    no_ahead_response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": no_ahead.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    remote_head_after = _bare_remote_head(remote_dir, "feature/direct-no-upstream")

    assert no_upstream.ready is True
    assert missing_upstream_response.status_code == 400
    assert "configured upstream" in missing_upstream_response.json()["detail"]
    assert no_ahead.ready is True
    assert no_ahead_response.status_code == 400
    assert "local commits ahead" in no_ahead_response.json()["detail"]
    assert remote_head_after == _git(git_workspace, "rev-parse", "HEAD").stdout.strip()


def test_git_push_run_rejects_arbitrary_remote_branch_and_flags_payload(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace)
    checkpoint = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
            "remote": "origin",
            "branch": "feature/push-approval",
            "flags": ["--force"],
        },
    )

    assert response.status_code == 422


def test_git_push_run_does_not_expose_secret_shaped_remote_url(git_workspace) -> None:
    remote_dir = _push_ready_workspace(git_workspace)
    raw_secret = "remote-url-push-secret-token"
    secret_remote_dir = remote_dir.with_name(f"{raw_secret}.git")
    remote_dir.rename(secret_remote_dir)
    _git(git_workspace, "remote", "set-url", "origin", str(secret_remote_dir))
    checkpoint = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    serialized_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)]
    )

    assert response.status_code == 201
    assert response.json()["remote_url_digest"].startswith("sha256:")
    assert raw_secret not in response.text
    assert raw_secret not in serialized_logs


def test_git_push_run_uses_empty_hooks_path(git_workspace) -> None:
    remote_dir = _push_ready_workspace(git_workspace)
    local_head = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    hook_marker = git_workspace / "pre-push-ran.txt"
    hook_path = git_workspace / ".git" / "hooks" / "pre-push"
    hook_path.write_text(
        f"#!/bin/sh\necho pre-push-ran > {hook_marker.as_posix()!r}\nexit 1\n",
        encoding="utf-8",
    )
    hook_path.chmod(0o755)
    checkpoint = _checkpoint("push", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/push-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    remote_head_after = _bare_remote_head(remote_dir, "feature/push-approval")

    assert response.status_code == 201
    assert remote_head_after == local_head
    assert not hook_marker.exists()


def test_git_push_run_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DGENTIC_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("DGENTIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("DGENTIC_AUTH_TOKENS", raising=False)
    get_settings.cache_clear()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# Push run auth\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")
    _push_ready_workspace(root_dir)
    checkpoint = _checkpoint("push", root_dir, evidence=["pytest -q"])

    cli_token = "git-push-run-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/push-runs",
        headers={"Authorization": "Bearer task-token"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["pytest -q"],
        },
    )
    allowed = client.post(
        "/cli/git/push-runs",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["requested_by"] == expected_actor
    get_settings.cache_clear()


def test_git_pr_approval_api_creates_pending_approval_without_creating_pr(
    git_workspace,
) -> None:
    base_branch = _git(git_workspace, "branch", "--show-current").stdout.strip()
    _push_ready_workspace(git_workspace, ahead=False)
    raw_remote_secret = "remote-url-pr-secret-token"
    _git(
        git_workspace,
        "remote",
        "set-url",
        "origin",
        f"https://user:{raw_remote_secret}@example.test/org/repo.git",
    )
    checkpoint = _checkpoint("pr", git_workspace, evidence=["python -m pytest -q"])
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open guarded PR",
            "body": "Focused Sprint 15 PR approval.",
            "base_branch": base_branch,
            "draft": True,
            "test_evidence": ["python -m pytest -q"],
            "requested_by": "qa-agent",
        },
    )
    runs = client.get("/cli/runs").json()
    logs = json.dumps([event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)])
    approval = response.json()

    assert checkpoint.ready is True
    assert checkpoint.ahead == 0
    assert checkpoint.behind == 0
    assert checkpoint.remote_url_digest.startswith("sha256:")
    assert response.status_code == 201
    assert approval["status"] == "pending"
    assert approval["permission_mode"] == "approval_required"
    assert approval["command"] == (
        'gh pr create --title "Open guarded PR" '
        '--body "Focused Sprint 15 PR approval." '
        '--head "feature/push-approval" '
        f'--base "{base_branch}" --draft'
    )
    assert approval["run_id"] is None
    assert approval["workflow_binding"]["action"] == "pr"
    assert approval["workflow_binding"]["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert approval["workflow_binding"]["remote_url_digest"] == checkpoint.remote_url_digest
    assert approval["workflow_binding"]["pr_intent"]["title_digest"].startswith("sha256:")
    assert approval["workflow_binding"]["pr_intent"]["body_digest"].startswith("sha256:")
    assert approval["workflow_binding"]["pr_intent"]["base_branch"] == base_branch
    assert approval["workflow_binding"]["pr_intent"]["head_branch"] == "feature/push-approval"
    assert approval["workflow_binding"]["pr_intent"]["draft"] is True
    assert "Open guarded PR" not in json.dumps(approval["workflow_binding"]["pr_intent"])
    assert "Focused Sprint 15 PR approval." not in json.dumps(
        approval["workflow_binding"]["pr_intent"]
    )
    assert Path(approval["cwd"]) == git_workspace.resolve()
    assert approval["requested_by"] == "qa-agent"
    assert runs == []
    assert raw_remote_secret not in response.text
    assert raw_remote_secret not in logs


def test_git_pr_approval_rejects_stale_checkpoint_digest(git_workspace) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nAnother PR commit.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    _git(git_workspace, "commit", "-m", "Add stale PR change")
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject stale PR digest",
            "body": "State changed after checkpoint.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approvals = client.get("/cli/approvals").json()

    assert response.status_code == 400
    assert "fresh matching checkpoint digest" in response.json()["detail"]
    assert approvals == []


def test_git_pr_approval_rejects_unpushed_or_missing_upstream_branch(git_workspace) -> None:
    _git(git_workspace, "checkout", "-b", "feature/pr-no-upstream")
    no_upstream = _checkpoint("pr", git_workspace)
    client = TestClient(create_app())

    missing_upstream_response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": no_upstream.checkpoint_digest,
            "title": "Reject missing upstream",
            "body": "No upstream branch is configured.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    _git(git_workspace, "checkout", "-")
    _push_ready_workspace(git_workspace, ahead=True)
    unpushed = _checkpoint("pr", git_workspace)
    unpushed_response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": unpushed.checkpoint_digest,
            "title": "Reject unpushed branch",
            "body": "Branch still has local commits ahead.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert no_upstream.ready is True
    assert missing_upstream_response.status_code == 400
    assert "configured upstream" in missing_upstream_response.json()["detail"]
    assert unpushed.ready is True
    assert unpushed.ahead == 1
    assert unpushed_response.status_code == 400
    assert "branch to be pushed" in unpushed_response.json()["detail"]


def test_git_pr_approval_rejects_behind_upstream_branch(git_workspace) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    tree_sha = _git(git_workspace, "rev-parse", "HEAD^{tree}").stdout.strip()
    head_sha = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    remote_only_commit = subprocess.run(
        ["git", "commit-tree", tree_sha, "-p", head_sha, "-m", "Remote-only PR change"],
        cwd=git_workspace,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git(
        git_workspace, "update-ref", "refs/remotes/origin/feature/push-approval", remote_only_commit
    )
    behind = _checkpoint("pr", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": behind.checkpoint_digest,
            "title": "Reject stale upstream",
            "body": "Remote tracking branch is ahead.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert behind.ready is True
    assert behind.behind == 1
    assert response.status_code == 400
    assert "current with upstream" in response.json()["detail"]


def test_git_pr_approval_rejects_arbitrary_command_remote_and_flags_payload(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject arbitrary payload",
            "body": "Only structured PR fields are allowed.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
            "command": "gh pr create --web",
            "remote": "origin",
            "flags": ["--web"],
        },
    )

    assert response.status_code == 422


def test_git_pr_approval_rejects_secret_shaped_title_and_body(git_workspace) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    raw_secret = "pr-body-secret-token"
    client = TestClient(create_app())

    title_response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": f"API_KEY={raw_secret}",
            "body": "Rejected title secret.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    body_response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject PR body secret",
            "body": f"ACCESS_TOKEN={raw_secret}",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approvals = client.get("/cli/approvals").json()

    assert title_response.status_code == 400
    assert body_response.status_code == 400
    assert "secret-shaped text" in title_response.json()["detail"]
    assert "secret-shaped text" in body_response.json()["detail"]
    assert raw_secret not in title_response.text
    assert raw_secret not in body_response.text
    assert approvals == []


def test_git_pr_approval_revalidates_workflow_state_before_execution(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    client = TestClient(create_app())
    create_response = client.post(
        "/cli/git/pr-approvals",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open workflow-bound PR",
            "body": "PR state will be revalidated.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer", "reason": "PR checkpoint reviewed."},
    )
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nChanged after PR approval.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    _git(git_workspace, "commit", "-m", "Change after PR approval")

    execute_response = client.post(f"/cli/approvals/{approval_id}/execute")
    review_response = client.get(f"/cli/approvals/{approval_id}/review")

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert execute_response.status_code == 403
    assert "no longer matches current repository state" in execute_response.json()["detail"]
    assert review_response.json()["status"] == "approved"
    assert (
        "Approval is workflow-bound and revalidates workflow state before execution."
        in review_response.json()["review_warnings"]
    )


def test_git_pr_approval_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DGENTIC_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("DGENTIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("DGENTIC_AUTH_TOKENS", raising=False)
    get_settings.cache_clear()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# PR auth\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")
    _push_ready_workspace(root_dir, ahead=False)
    checkpoint = _checkpoint("pr", root_dir, evidence=["pytest -q"])

    cli_token = "git-pr-approval-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/pr-approvals",
        headers={"Authorization": "Bearer task-token"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open authenticated PR",
            "body": "Wrong capability is rejected.",
            "test_evidence": ["pytest -q"],
        },
    )
    allowed = client.post(
        "/cli/git/pr-approvals",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open authenticated PR",
            "body": "Authenticated principal is bound.",
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["requested_by"] == expected_actor
    get_settings.cache_clear()


def test_git_pr_run_api_invokes_fake_gh_outside_root_with_exact_argv(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    base_branch = _git(git_workspace, "branch", "--show-current").stdout.strip()
    _push_ready_workspace(git_workspace, ahead=False)
    _git(git_workspace, "remote", "set-url", "origin", "https://github.com/example/repo.git")
    checkpoint = _checkpoint("pr", git_workspace, evidence=["python -m pytest -q"])
    record_path = tmp_path / "gh-record.json"
    ambient_home = tmp_path / "ambient-gh-home"
    raw_gh_secret = "gh-output-secret-token"
    safe_pr_url = "https://github.com/example/repo/pull/42"
    monkeypatch.setenv("HOME", str(ambient_home))
    fake_gh = _install_fake_gh(
        tmp_path / "bin",
        monkeypatch,
        record_path=record_path,
        stdout=f"https://user:{raw_gh_secret}@github.com/example/repo/pull/1\n{safe_pr_url}\n",
    )
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open direct PR",
            "body": "Focused direct PR.",
            "base_branch": base_branch,
            "draft": True,
            "test_evidence": ["python -m pytest -q"],
            "requested_by": "qa-agent",
        },
    )
    assert response.status_code == 201, response.text
    record = json.loads(record_path.read_text(encoding="utf-8"))
    approvals = client.get("/cli/approvals").json()
    logs = json.dumps([event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)])

    assert fake_gh.resolve() != git_workspace.resolve()
    assert git_workspace.resolve() not in fake_gh.resolve().parents
    assert response.json()["action"] == "pr"
    assert response.json()["checkpoint_digest"] == checkpoint.checkpoint_digest
    assert response.json()["title_digest"].startswith("sha256:")
    assert response.json()["body_digest"].startswith("sha256:")
    assert response.json()["head_branch"] == "feature/push-approval"
    assert response.json()["base_branch"] == base_branch
    assert response.json()["draft"] is True
    assert response.json()["pr_url"] == safe_pr_url
    assert response.json()["requested_by"] == "qa-agent"
    assert record["cwd"] == str(git_workspace.resolve())
    gh_config_dir = Path(record["env"]["GH_CONFIG_DIR"])
    assert record["env"]["HOME"] is None
    assert record["env"]["GH_TOKEN"] == "fake-gh-token"
    assert record["env"]["GH_PROMPT_DISABLED"] == "1"
    assert record["env"]["NO_COLOR"] == "1"
    assert gh_config_dir.name.startswith("dgentic-gh-config-")
    assert git_workspace.resolve() not in gh_config_dir.resolve().parents
    assert gh_config_dir.resolve() != ambient_home.resolve()
    assert not gh_config_dir.exists()
    assert record["argv"] == [
        "pr",
        "create",
        "--title",
        "Open direct PR",
        "--body",
        "Focused direct PR.",
        "--head",
        "feature/push-approval",
        "--base",
        base_branch,
        "--draft",
    ]
    assert approvals == []
    assert raw_gh_secret not in response.text
    assert raw_gh_secret not in logs


def test_git_pr_run_ignores_pr_url_from_unmatched_remote_host(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    _git(git_workspace, "remote", "set-url", "origin", "https://github.com/example/repo.git")
    checkpoint = _checkpoint("pr", git_workspace, evidence=["python -m pytest -q"])
    record_path = tmp_path / "gh-record.json"
    _install_fake_gh(
        tmp_path / "bin",
        monkeypatch,
        record_path=record_path,
        stdout="https://evil.example.test/example/repo/pull/42\n",
    )
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open direct PR",
            "body": "Focused direct PR.",
            "test_evidence": ["python -m pytest -q"],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["pr_url"] == ""


def test_git_pr_run_requires_explicit_token_without_invoking_gh(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    _git(git_workspace, "remote", "set-url", "origin", "https://github.com/example/repo.git")
    checkpoint = _checkpoint("pr", git_workspace)
    record_path = tmp_path / "gh-record.json"
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GHE_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    _install_fake_gh(tmp_path / "bin", monkeypatch, record_path=record_path, token=None)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject missing token",
            "body": "Token environment is required.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert response.status_code == 400
    assert "explicit GitHub CLI token environment" in response.json()["detail"]
    assert not record_path.exists()


def test_git_pr_run_rejects_stale_checkpoint_digest_without_invoking_gh(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nAnother direct PR commit.\n",
        encoding="utf-8",
    )
    _git(git_workspace, "add", "README.md")
    _git(git_workspace, "commit", "-m", "Add stale direct PR change")
    record_path = tmp_path / "gh-record.json"
    _install_fake_gh(tmp_path / "bin", monkeypatch, record_path=record_path)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject stale direct PR digest",
            "body": "State changed after checkpoint.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert response.status_code == 400
    assert "fresh matching checkpoint digest" in response.json()["detail"]
    assert not record_path.exists()


def test_git_pr_run_rejects_dirty_worktree_without_invoking_gh(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    git_workspace.joinpath("README.md").write_text(
        "# Checkpoint\n\nDirty direct PR worktree.\n",
        encoding="utf-8",
    )
    checkpoint = _checkpoint("pr", git_workspace)
    record_path = tmp_path / "gh-record.json"
    _install_fake_gh(tmp_path / "bin", monkeypatch, record_path=record_path)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject dirty direct PR",
            "body": "Worktree is not clean.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert checkpoint.ready is False
    assert response.status_code == 400
    assert "ready PR checkpoint" in response.json()["detail"]
    assert not record_path.exists()


def test_git_pr_run_rejects_missing_unpushed_and_behind_upstream_without_invoking_gh(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    record_path = tmp_path / "gh-record.json"
    _install_fake_gh(tmp_path / "bin", monkeypatch, record_path=record_path)
    client = TestClient(create_app())

    _git(git_workspace, "checkout", "-b", "feature/direct-pr-no-upstream")
    no_upstream = _checkpoint("pr", git_workspace)
    missing_upstream_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": no_upstream.checkpoint_digest,
            "title": "Reject missing upstream",
            "body": "No upstream branch is configured.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    _git(git_workspace, "checkout", "-")
    _push_ready_workspace(git_workspace, ahead=True)
    unpushed = _checkpoint("pr", git_workspace)
    unpushed_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": unpushed.checkpoint_digest,
            "title": "Reject unpushed branch",
            "body": "Branch still has local commits ahead.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    _git(git_workspace, "reset", "--hard", "origin/feature/push-approval")
    tree_sha = _git(git_workspace, "rev-parse", "HEAD^{tree}").stdout.strip()
    head_sha = _git(git_workspace, "rev-parse", "HEAD").stdout.strip()
    remote_only_commit = subprocess.run(
        ["git", "commit-tree", tree_sha, "-p", head_sha, "-m", "Remote-only direct PR change"],
        cwd=git_workspace,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git(
        git_workspace, "update-ref", "refs/remotes/origin/feature/push-approval", remote_only_commit
    )
    behind = _checkpoint("pr", git_workspace)
    behind_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": behind.checkpoint_digest,
            "title": "Reject stale upstream",
            "body": "Remote tracking branch is ahead.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )

    assert no_upstream.ready is True
    assert missing_upstream_response.status_code == 400
    assert "configured upstream" in missing_upstream_response.json()["detail"]
    assert unpushed.ready is True
    assert unpushed.ahead == 1
    assert unpushed_response.status_code == 400
    assert "branch to be pushed" in unpushed_response.json()["detail"]
    assert behind.ready is True
    assert behind.behind == 1
    assert behind_response.status_code == 400
    assert "current with upstream" in behind_response.json()["detail"]
    assert not record_path.exists()


def test_git_pr_run_rejects_arbitrary_command_remote_and_flags_payload(
    git_workspace,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    client = TestClient(create_app())

    response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject arbitrary payload",
            "body": "Only structured PR fields are allowed.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
            "command": "gh pr create --web",
            "remote": "origin",
            "flags": ["--web"],
        },
    )

    assert response.status_code == 422


def test_git_pr_run_rejects_secret_and_multiline_title_body_without_leakage(
    git_workspace,
    tmp_path,
    monkeypatch,
) -> None:
    _push_ready_workspace(git_workspace, ahead=False)
    checkpoint = _checkpoint("pr", git_workspace)
    raw_secret = "direct-pr-secret-token"
    record_path = tmp_path / "gh-record.json"
    _install_fake_gh(tmp_path / "bin", monkeypatch, record_path=record_path)
    client = TestClient(create_app())

    title_secret_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": f"API_KEY={raw_secret}",
            "body": "Rejected title secret.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    title_multiline_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject direct PR\nwith title newline",
            "body": "Rejected multiline title.",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    body_secret_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject PR body secret",
            "body": f"ACCESS_TOKEN={raw_secret}",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    body_multiline_response = client.post(
        "/cli/git/pr-runs",
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Reject multiline body",
            "body": "Rejected direct PR\nwith body newline",
            "test_evidence": ["python -m pytest tests/test_git_workflows.py -q"],
        },
    )
    logs = json.dumps([event.model_dump(mode="json") for event in event_log.list(LogEventType.cli)])

    assert title_secret_response.status_code == 400
    assert body_secret_response.status_code == 400
    assert "secret-shaped text" in title_secret_response.json()["detail"]
    assert "secret-shaped text" in body_secret_response.json()["detail"]
    assert title_multiline_response.status_code == 400
    assert body_multiline_response.status_code == 400
    assert "single printable line" in title_multiline_response.json()["detail"]
    assert "single printable line" in body_multiline_response.json()["detail"]
    assert raw_secret not in title_secret_response.text
    assert raw_secret not in body_secret_response.text
    assert raw_secret not in logs
    assert not record_path.exists()


def test_git_pr_run_api_uses_cli_capability_and_authenticated_principal(
    tmp_path,
    monkeypatch,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DGENTIC_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("DGENTIC_ENVIRONMENT", raising=False)
    monkeypatch.delenv("DGENTIC_AUTH_TOKENS", raising=False)
    get_settings.cache_clear()
    _git(root_dir, "init")
    _git(root_dir, "config", "user.email", "qa@example.test")
    _git(root_dir, "config", "user.name", "QA Agent")
    root_dir.joinpath("README.md").write_text("# PR run auth\n", encoding="utf-8")
    _git(root_dir, "add", "README.md")
    _git(root_dir, "commit", "-m", "Initial commit")
    _push_ready_workspace(root_dir, ahead=False)
    _git(root_dir, "remote", "set-url", "origin", "https://github.com/example/repo.git")
    checkpoint = _checkpoint("pr", root_dir, evidence=["pytest -q"])
    record_path = tmp_path / "gh-record.json"
    _install_fake_gh(tmp_path / "bin", monkeypatch, record_path=record_path)

    cli_token = "git-pr-run-cli-token"
    expected_actor = sha256(cli_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{cli_token}=cli;task-token=tasks")
    get_settings.cache_clear()
    client = TestClient(create_app())

    wrong_capability = client.post(
        "/cli/git/pr-runs",
        headers={"Authorization": "Bearer task-token"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open authenticated PR",
            "body": "Wrong capability is rejected.",
            "test_evidence": ["pytest -q"],
        },
    )
    allowed = client.post(
        "/cli/git/pr-runs",
        headers={"Authorization": f"Bearer {cli_token}"},
        json={
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "title": "Open authenticated PR",
            "body": "Authenticated principal is bound.",
            "test_evidence": ["pytest -q"],
            "requested_by": "spoofed-body-actor",
        },
    )

    assert wrong_capability.status_code == 403
    assert allowed.status_code == 201
    assert allowed.json()["requested_by"] == expected_actor
    get_settings.cache_clear()
