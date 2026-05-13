import json
from hashlib import sha256

from fastapi.testclient import TestClient

from dgentic.events import event_log
from dgentic.main import create_app
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings


def setup_function() -> None:
    get_settings.cache_clear()


def teardown_function() -> None:
    get_settings.cache_clear()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def configure_filesystem_approval_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        (
            "fs-token=filesystem;"
            "review-token=approvals;"
            "workflow-token=filesystem,approvals,hooks,logs"
        ),
    )
    get_settings.cache_clear()
    return TestClient(create_app()), root_dir


def test_filesystem_approval_lifecycle_claims_delete_once(tmp_path, monkeypatch) -> None:
    client, root_dir = configure_filesystem_approval_state(tmp_path, monkeypatch)
    actor_id = sha256(b"workflow-token").hexdigest()[:12]
    headers = bearer("workflow-token")
    target = root_dir / "delete-me.txt"
    target.write_text("remove", encoding="utf-8")

    boolean_response = client.post(
        "/filesystem/delete",
        headers=headers,
        json={"path": "delete-me.txt", "approved": True},
    )
    create_response = client.post(
        "/filesystem/approvals",
        headers=headers,
        json={"path": "delete-me.txt", "action": "delete", "requested_by": "spoofed"},
    )
    approval_id = create_response.json()["id"]
    review_response = client.get(
        f"/filesystem/approvals/{approval_id}/review",
        headers=headers,
    )
    approve_response = client.post(
        f"/filesystem/approvals/{approval_id}/approve",
        headers=headers,
        json={"decided_by": "spoofed-reviewer", "reason": "TOKEN=approval-secret"},
    )
    execute_response = client.post(
        "/filesystem/delete",
        headers=headers,
        json={"path": "delete-me.txt", "approval_id": approval_id},
    )
    reuse_response = client.post(
        "/filesystem/delete",
        headers=headers,
        json={"path": "delete-me.txt", "approval_id": approval_id},
    )
    approvals_response = client.get(
        "/filesystem/approvals?status=executed",
        headers=headers,
    )
    approval_events = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.approval)]
    )

    assert boolean_response.status_code == 403
    assert (
        "approved boolean bypass is only allowed in development/test mode" in boolean_response.text
    )
    assert create_response.status_code == 201
    assert create_response.json()["requested_by"] == actor_id
    assert create_response.json()["path_digest"].startswith("hmac-sha256:")
    assert create_response.json()["source_state_digest"].startswith("hmac-sha256:")
    assert review_response.status_code == 200
    assert review_response.json()["requires_bound_execution_request"] is True
    assert review_response.json()["direct_execute_available"] is False
    assert approve_response.status_code == 200
    assert approve_response.json()["decided_by"] == actor_id
    assert approve_response.json()["decision_reason"] == "TOKEN=[REDACTED]"
    assert execute_response.status_code == 200
    assert not target.exists()
    assert reuse_response.status_code == 403
    assert "not executable" in reuse_response.text
    assert approvals_response.status_code == 200
    assert approvals_response.json()[0]["status"] == "executed"
    assert "approval-secret" not in approval_events
    assert "TOKEN=[REDACTED]" in approval_events


def test_filesystem_approval_rejects_path_payload_and_state_drift(tmp_path, monkeypatch) -> None:
    client, root_dir = configure_filesystem_approval_state(tmp_path, monkeypatch)
    headers = bearer("workflow-token")
    source = root_dir / "copy-source.txt"
    source.write_text("original", encoding="utf-8")

    create_response = client.post(
        "/filesystem/approvals",
        headers=headers,
        json={"path": "copy-source.txt", "target_path": "copy-target.txt", "action": "copy"},
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/filesystem/approvals/{approval_id}/approve",
        headers=headers,
        json={"reason": "copy approved"},
    )
    changed_target_response = client.post(
        "/filesystem/copy",
        headers=headers,
        json={
            "path": "copy-source.txt",
            "target_path": "other-target.txt",
            "approval_id": approval_id,
        },
    )
    source.write_text("changed", encoding="utf-8")
    changed_source_response = client.post(
        "/filesystem/copy",
        headers=headers,
        json={
            "path": "copy-source.txt",
            "target_path": "copy-target.txt",
            "approval_id": approval_id,
        },
    )

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert changed_target_response.status_code == 403
    assert "not bound to this filesystem request" in changed_target_response.text
    assert changed_source_response.status_code == 403
    assert "not bound to this filesystem request" in changed_source_response.text
    assert not (root_dir / "copy-target.txt").exists()


def test_filesystem_hook_approval_is_enforced_for_write_payload(tmp_path, monkeypatch) -> None:
    client, root_dir = configure_filesystem_approval_state(tmp_path, monkeypatch)
    headers = bearer("workflow-token")

    hook_response = client.post(
        "/guardrails/hooks/rules",
        headers=headers,
        json={
            "name": "Review protected writes",
            "surface": "filesystem",
            "action": "write",
            "match_type": "prefix",
            "pattern": "protected/",
            "effect": "approval_required",
            "reason": "Review protected path.",
        },
    )
    denied_write_response = client.post(
        "/filesystem/write",
        headers=headers,
        json={"path": "protected/note.txt", "content": "approved content"},
    )
    create_response = client.post(
        "/filesystem/approvals",
        headers=headers,
        json={
            "path": "protected/note.txt",
            "action": "write",
            "content": "approved content",
        },
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/filesystem/approvals/{approval_id}/approve",
        headers=headers,
        json={"reason": "safe write"},
    )
    changed_payload_response = client.post(
        "/filesystem/write",
        headers=headers,
        json={
            "path": "protected/note.txt",
            "content": "different content",
            "approval_id": approval_id,
        },
    )
    second_create_response = client.post(
        "/filesystem/approvals",
        headers=headers,
        json={
            "path": "protected/note.txt",
            "action": "write",
            "content": "approved content",
        },
    )
    second_approval_id = second_create_response.json()["id"]
    client.post(
        f"/filesystem/approvals/{second_approval_id}/approve",
        headers=headers,
        json={"reason": "safe write"},
    )
    approved_write_response = client.post(
        "/filesystem/write",
        headers=headers,
        json={
            "path": "protected/note.txt",
            "content": "approved content",
            "approval_id": second_approval_id,
        },
    )

    assert hook_response.status_code == 201
    assert denied_write_response.status_code == 403
    assert "Review protected path." in denied_write_response.text
    assert create_response.status_code == 201
    assert create_response.json()["hook_policy"]["effect"] == "approval_required"
    assert create_response.json()["payload_digest"].startswith("hmac-sha256:")
    assert approve_response.status_code == 200
    assert changed_payload_response.status_code == 403
    assert "not bound to this filesystem request" in changed_payload_response.text
    assert second_create_response.status_code == 201
    assert approved_write_response.status_code == 200
    assert (root_dir / "protected" / "note.txt").read_text(encoding="utf-8") == ("approved content")


def test_filesystem_approval_capability_split(tmp_path, monkeypatch) -> None:
    client, root_dir = configure_filesystem_approval_state(tmp_path, monkeypatch)
    (root_dir / "delete-me.txt").write_text("remove", encoding="utf-8")

    fs_create_response = client.post(
        "/filesystem/approvals",
        headers=bearer("fs-token"),
        json={"path": "delete-me.txt", "action": "delete"},
    )
    approval_id = fs_create_response.json()["id"]
    fs_approve_response = client.post(
        f"/filesystem/approvals/{approval_id}/approve",
        headers=bearer("fs-token"),
        json={},
    )
    review_list_response = client.get(
        "/filesystem/approvals",
        headers=bearer("review-token"),
    )
    review_approve_response = client.post(
        f"/filesystem/approvals/{approval_id}/approve",
        headers=bearer("review-token"),
        json={"reason": "approved by reviewer"},
    )
    review_execute_response = client.post(
        "/filesystem/delete",
        headers=bearer("review-token"),
        json={"path": "delete-me.txt", "approval_id": approval_id},
    )
    fs_execute_response = client.post(
        "/filesystem/delete",
        headers=bearer("fs-token"),
        json={"path": "delete-me.txt", "approval_id": approval_id},
    )

    assert fs_create_response.status_code == 201
    assert fs_approve_response.status_code == 403
    assert review_list_response.status_code == 200
    assert review_approve_response.status_code == 200
    assert review_execute_response.status_code == 403
    assert fs_execute_response.status_code == 200
    assert not (root_dir / "delete-me.txt").exists()
