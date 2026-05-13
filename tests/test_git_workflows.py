import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgentic.events import event_log
from dgentic.git_workflows import (
    GitWorkflowCheckpointRequest,
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
