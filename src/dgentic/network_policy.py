import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from dgentic.settings import get_settings

NetworkPolicyMode = Literal["allow", "deny", "approval_required", "audit"]
DEFAULT_NETWORK_POLICY_MODE: NetworkPolicyMode = "allow"
DOMAIN_PATTERN = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


class NetworkDomainPolicyError(ValueError):
    """Raised when network domain policy configuration is malformed."""


@dataclass(frozen=True)
class NetworkDomainPolicyDecision:
    url: str
    host: str
    mode: NetworkPolicyMode
    matched_domain: str | None = None
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.mode in {"allow", "audit"}


@dataclass(frozen=True)
class NetworkDomainRule:
    domain: str
    mode: NetworkPolicyMode
    reason: str = ""


@dataclass(frozen=True)
class NetworkDomainPolicy:
    default_mode: NetworkPolicyMode = DEFAULT_NETWORK_POLICY_MODE
    rules: tuple[NetworkDomainRule, ...] = ()


def evaluate_network_domain_policy(
    url: str,
    *,
    settings: Any | None = None,
) -> NetworkDomainPolicyDecision:
    active_settings = settings if settings is not None else get_settings()
    host = _host_for_url(url)
    policy = network_domain_policy(active_settings)

    for rule in policy.rules:
        if _domain_matches(host, rule.domain):
            return NetworkDomainPolicyDecision(
                url=url,
                host=host,
                mode=rule.mode,
                matched_domain=rule.domain,
                reason=rule.reason or f"Matched network domain policy rule for {rule.domain}.",
            )

    return NetworkDomainPolicyDecision(
        url=url,
        host=host,
        mode=policy.default_mode,
        reason=f"Used default network domain policy mode: {policy.default_mode}.",
    )


def network_domain_policy(settings: Any | None = None) -> NetworkDomainPolicy:
    active_settings = settings if settings is not None else get_settings()
    raw_config = active_settings.network_domain_policy.strip()
    if not raw_config:
        return NetworkDomainPolicy()
    try:
        payload = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise NetworkDomainPolicyError("Network domain policy must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise NetworkDomainPolicyError("Network domain policy must be a JSON object.")

    default_mode = _normalize_mode(payload.get("default_mode", DEFAULT_NETWORK_POLICY_MODE))
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, list):
        raise NetworkDomainPolicyError("Network domain policy rules must be a list.")

    rules = tuple(_parse_rule(rule) for rule in raw_rules)
    return NetworkDomainPolicy(default_mode=default_mode, rules=rules)


def _parse_rule(raw_rule: Any) -> NetworkDomainRule:
    if not isinstance(raw_rule, dict):
        raise NetworkDomainPolicyError("Network domain policy rule must be an object.")
    domain = _normalize_domain(raw_rule.get("domain"))
    mode = _normalize_mode(raw_rule.get("mode"))
    reason = raw_rule.get("reason", "")
    if reason is None:
        reason = ""
    if not isinstance(reason, str):
        raise NetworkDomainPolicyError("Network domain policy rule reason must be a string.")
    return NetworkDomainRule(domain=domain, mode=mode, reason=reason.strip())


def _normalize_mode(value: Any) -> NetworkPolicyMode:
    if not isinstance(value, str):
        raise NetworkDomainPolicyError("Network domain policy mode must be a string.")
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"allow", "deny", "approval_required", "audit"}:
        raise NetworkDomainPolicyError("Network domain policy mode is not supported.")
    return normalized  # type: ignore[return-value]


def _normalize_domain(value: Any) -> str:
    if not isinstance(value, str):
        raise NetworkDomainPolicyError("Network domain policy rule domain must be a string.")
    domain = value.strip().lower().rstrip(".")
    if not domain or "/" in domain or ":" in domain or not DOMAIN_PATTERN.fullmatch(domain):
        raise NetworkDomainPolicyError("Network domain policy rule domain is not valid.")
    if ".." in domain:
        raise NetworkDomainPolicyError("Network domain policy rule domain is not valid.")
    return domain


def _host_for_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise NetworkDomainPolicyError("Network policy URL is not valid.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise NetworkDomainPolicyError("Network policy URL must use http or https with a host.")
    return parts.hostname.lower().rstrip(".")


def _domain_matches(host: str, domain: str) -> bool:
    if domain.startswith("*."):
        suffix = domain[2:]
        return host.endswith(f".{suffix}") and host != suffix
    return host == domain
