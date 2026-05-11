import json
from datetime import UTC, datetime, timedelta

import pytest

from dgentic.network_policy import (
    NetworkApprovalRequiredError,
    NetworkApprovalStatus,
    NetworkDomainPolicyError,
    approve_network_approval,
    claim_network_approval,
    create_network_approval,
    deny_network_approval,
    evaluate_network_domain_policy,
    get_network_approval_review,
    list_network_approvals,
    network_domain_policy,
)
from dgentic.orchestration import OrchestrationService
from dgentic.schemas import OrchestrationCreateRequest, OrchestrationTaskSpec
from dgentic.settings import Settings, get_settings


@pytest.fixture()
def network_approval_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DGENTIC_APPROVAL_DIGEST_KEY", "network-test-key")
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "provider.example.test",
                        "mode": "approval_required",
                        "reason": "Review outbound provider token=policy-secret.",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    yield data_dir
    get_settings.cache_clear()


def _running_orchestration_task():
    run = OrchestrationService().create_run(
        OrchestrationCreateRequest(
            objective="Bind network approval context to the active orchestration task.",
            tasks=[
                OrchestrationTaskSpec(
                    id="qa-validation",
                    title="QA validation",
                    description="Validate network approval context binding.",
                    role="QA",
                    declared_write_paths=["tests/test_network_policy.py"],
                    validation="Network approval context is verified.",
                )
            ],
        )
    )
    return run.tasks[0]


def test_network_domain_policy_allows_by_default() -> None:
    decision = evaluate_network_domain_policy(
        "https://api.example.test/v1",
        settings=Settings(),
    )

    assert decision.allowed is True
    assert decision.mode == "allow"
    assert decision.host == "api.example.test"
    assert decision.matched_domain is None


def test_network_domain_policy_matches_exact_and_wildcard_rules() -> None:
    settings = Settings(
        network_domain_policy=(
            '{"default_mode":"deny","rules":['
            '{"domain":"api.example.test","mode":"allow","reason":"trusted"},'
            '{"domain":"*.audit.example.test","mode":"audit"}'
            "]}"
        )
    )

    exact = evaluate_network_domain_policy("https://api.example.test/v1", settings=settings)
    wildcard = evaluate_network_domain_policy(
        "https://child.audit.example.test/v1",
        settings=settings,
    )
    default = evaluate_network_domain_policy("https://other.example.test/v1", settings=settings)

    assert exact.allowed is True
    assert exact.mode == "allow"
    assert exact.reason == "trusted"
    assert wildcard.allowed is True
    assert wildcard.mode == "audit"
    assert wildcard.matched_domain == "*.audit.example.test"
    assert default.allowed is False
    assert default.mode == "deny"


def test_network_domain_policy_supports_approval_required_mode() -> None:
    decision = evaluate_network_domain_policy(
        "https://needs-review.example.test/v1",
        settings=Settings(
            network_domain_policy=(
                '{"rules":[{"domain":"needs-review.example.test","mode":"approval-required"}]}'
            )
        ),
    )

    assert decision.allowed is False
    assert decision.mode == "approval_required"


def test_network_domain_policy_rejects_malformed_configuration() -> None:
    with pytest.raises(NetworkDomainPolicyError):
        network_domain_policy(Settings(network_domain_policy='{"rules":[{"domain":"bad/path"}]}'))

    with pytest.raises(NetworkDomainPolicyError):
        evaluate_network_domain_policy("file:///tmp/secret.txt", settings=Settings())


def test_network_approval_lifecycle_redacts_and_claims_bound_request(
    network_approval_state,
) -> None:
    url = "https://provider.example.test/v1?api_key=url-secret#token=fragment-secret"

    approval = create_network_approval(
        url,
        surface="provider",
        action="generate",
        requested_by="operator TOKEN=requester-secret",
        agent_id="agent SECRET=agent-secret",
        agent_role="developer PASSWORD=role-secret",
        task_id="sprint API_KEY=task-secret",
    )

    assert approval.status == NetworkApprovalStatus.pending
    assert approval.url == "https://provider.example.test/v1"
    assert approval.requested_by == "operator TOKEN=[REDACTED]"
    assert approval.policy_reason == "Review outbound provider token=[REDACTED]"
    assert list_network_approvals(NetworkApprovalStatus.pending)[0].id == approval.id

    stored = (network_approval_state / "network-approvals.json").read_text(encoding="utf-8")
    assert "url-secret" not in stored
    assert "fragment-secret" not in stored
    assert "policy-secret" not in stored
    assert "requester-secret" not in stored
    assert "agent-secret" not in stored
    assert "role-secret" not in stored
    assert "task-secret" not in stored

    approved = approve_network_approval(
        approval.id,
        decided_by="reviewer TOKEN=reviewer-secret",
        reason="Looks safe PASSWORD=reason-secret.",
    )
    review = get_network_approval_review(approval.id)

    assert approved.status == NetworkApprovalStatus.approved
    assert review.direct_execute_available is False
    assert review.requires_bound_execution_request is True
    assert review.decided_by == "reviewer TOKEN=[REDACTED]"

    stored = (network_approval_state / "network-approvals.json").read_text(encoding="utf-8")
    assert "reviewer-secret" not in stored
    assert "reason-secret" not in stored

    executed = claim_network_approval(
        approval.id,
        url=url,
        surface="provider",
        action="generate",
        requested_by="operator TOKEN=requester-secret",
        agent_id="agent SECRET=agent-secret",
        agent_role="developer PASSWORD=role-secret",
        task_id="sprint API_KEY=task-secret",
    )

    assert executed.status == NetworkApprovalStatus.executed
    with pytest.raises(NetworkApprovalRequiredError, match="not executable"):
        claim_network_approval(
            approval.id,
            url=url,
            surface="provider",
            action="generate",
            requested_by="operator TOKEN=requester-secret",
            agent_id="agent SECRET=agent-secret",
            agent_role="developer PASSWORD=role-secret",
            task_id="sprint API_KEY=task-secret",
        )


def test_network_approval_rejects_partial_and_unmatched_active_orchestration_context(
    network_approval_state,
) -> None:
    task = _running_orchestration_task()

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        create_network_approval(
            "https://provider.example.test/v1",
            surface="provider",
            action="generate",
            requested_by="operator",
            agent_id=task.agent_id,
        )

    with pytest.raises(PermissionError, match="does not match"):
        create_network_approval(
            "https://provider.example.test/v1",
            surface="provider",
            action="generate",
            requested_by="operator",
            agent_id="wrong-agent",
            agent_role=task.role,
            task_id=task.id,
        )

    assert list_network_approvals() == []


def test_network_approval_claim_rechecks_active_orchestration_context(
    network_approval_state,
) -> None:
    approval = create_network_approval(
        "https://provider.example.test/v1",
        surface="provider",
        action="generate",
        requested_by="operator",
    )
    approve_network_approval(approval.id, decided_by="reviewer")
    task = _running_orchestration_task()

    with pytest.raises(PermissionError, match="require agent_id, agent_role, and task_id"):
        claim_network_approval(
            approval.id,
            url="https://provider.example.test/v1",
            surface="provider",
            action="generate",
            requested_by="operator",
            agent_id=task.agent_id,
        )

    assert list_network_approvals()[0].status == NetworkApprovalStatus.approved


def test_bound_network_approval_rejects_drift_denied_and_expired(
    network_approval_state,
) -> None:
    approved = create_network_approval(
        "https://provider.example.test/v1",
        surface="provider",
        action="generate",
        requested_by="operator",
    )
    approve_network_approval(approved.id, decided_by="reviewer")

    with pytest.raises(NetworkApprovalRequiredError, match="not bound"):
        claim_network_approval(
            approved.id,
            url="https://provider.example.test/v2",
            surface="provider",
            action="generate",
            requested_by="operator",
        )

    denied = create_network_approval(
        "https://provider.example.test/v1",
        surface="provider",
        action="stream",
        requested_by="operator",
    )
    deny_network_approval(denied.id, decided_by="reviewer")
    with pytest.raises(NetworkApprovalRequiredError, match="not executable"):
        claim_network_approval(
            denied.id,
            url="https://provider.example.test/v1",
            surface="provider",
            action="stream",
            requested_by="operator",
        )

    expired = create_network_approval(
        "https://provider.example.test/v1",
        surface="provider",
        action="request",
        requested_by="operator",
    )
    approve_network_approval(expired.id, decided_by="reviewer")
    approval_path = network_approval_state / "network-approvals.json"
    approvals = json.loads(approval_path.read_text(encoding="utf-8"))
    for item in approvals:
        if item["id"] == expired.id:
            item["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    approval_path.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(NetworkApprovalRequiredError, match="expired"):
        claim_network_approval(
            expired.id,
            url="https://provider.example.test/v1",
            surface="provider",
            action="request",
            requested_by="operator",
        )
