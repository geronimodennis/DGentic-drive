from typing import Any

from dgentic.network_policy import (
    NetworkApproval,
    NetworkApprovalRequiredError,
    NetworkDomainPolicyDecision,
    claim_network_approval,
    create_network_approval,
    evaluate_network_domain_policy,
)

WEB_RETRIEVAL_NETWORK_SURFACE = "web_retrieval"
WEB_RETRIEVAL_FETCH_ACTION = "fetch"


def evaluate_web_retrieval_network_policy(
    url: str,
    *,
    actor: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkDomainPolicyDecision:
    return evaluate_network_domain_policy(
        url,
        settings=settings,
        actor=actor,
        action=WEB_RETRIEVAL_FETCH_ACTION,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def create_web_retrieval_network_approval(
    url: str,
    *,
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkApproval:
    return create_network_approval(
        url,
        surface=WEB_RETRIEVAL_NETWORK_SURFACE,
        action=WEB_RETRIEVAL_FETCH_ACTION,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        settings=settings,
    )


def authorize_web_retrieval_network_request(
    url: str,
    *,
    approval_id: str | None = None,
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkDomainPolicyDecision:
    decision = evaluate_web_retrieval_network_policy(
        url,
        actor=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        settings=settings,
    )
    if decision.mode == "deny":
        raise PermissionError(decision.reason)
    if decision.mode == "approval_required":
        if not approval_id:
            raise NetworkApprovalRequiredError(
                "Web retrieval requires a bound network approval before fetch."
            )
        claim_network_approval(
            approval_id,
            url=url,
            surface=WEB_RETRIEVAL_NETWORK_SURFACE,
            action=WEB_RETRIEVAL_FETCH_ACTION,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
            settings=settings,
        )
    return decision
