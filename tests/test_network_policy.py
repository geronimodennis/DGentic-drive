import pytest

from dgentic.network_policy import (
    NetworkDomainPolicyError,
    evaluate_network_domain_policy,
    network_domain_policy,
)
from dgentic.settings import Settings


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
