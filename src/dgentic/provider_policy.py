from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dgentic.network_policy import (
    NetworkApprovalRequiredError,
    NetworkDomainPolicyError,
    claim_network_approval,
    evaluate_network_domain_policy,
    validate_bound_network_approval,
)
from dgentic.settings import get_settings


class ProviderEgressPolicyError(PermissionError):
    """Raised when a provider request targets a URL outside configured policy."""


class _NoProviderRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        raise ProviderEgressPolicyError("Provider redirects are blocked by egress policy.")


_PROVIDER_OPENER = build_opener(_NoProviderRedirectHandler)


def validate_provider_base_url(
    *,
    provider_id: str,
    base_url: str,
    settings: Any | None = None,
    network_approval_id: str | None = None,
    network_surface: str = "provider",
    network_action: str = "request",
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    require_network_approval: bool = True,
    claim_network_approval_record: bool = False,
) -> str:
    active_settings = settings if settings is not None else get_settings()
    normalized = normalize_provider_base_url(base_url)
    try:
        network_decision = evaluate_network_domain_policy(
            normalized,
            settings=active_settings,
            actor=requested_by,
            action=network_action,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )
    except NetworkDomainPolicyError as exc:
        raise ProviderEgressPolicyError("Network domain policy is invalid.") from exc
    if network_decision.mode == "deny":
        raise ProviderEgressPolicyError("Provider domain is denied by network policy.")
    allowed = allowed_provider_base_urls_for_provider(provider_id, active_settings)
    if normalized not in allowed:
        raise ProviderEgressPolicyError(
            f"Provider base_url for {provider_id} is not allowed by egress policy."
        )
    if network_decision.mode == "approval_required" and require_network_approval:
        if not network_approval_id:
            raise ProviderEgressPolicyError(
                "Provider domain requires network approval via an approved "
                "network_approval_id before transport."
            )
        try:
            if claim_network_approval_record:
                claim_network_approval(
                    network_approval_id,
                    url=normalized,
                    surface=network_surface,
                    action=network_action,
                    requested_by=requested_by,
                    agent_id=agent_id,
                    agent_role=agent_role,
                    task_id=task_id,
                    settings=active_settings,
                )
            else:
                validate_bound_network_approval(
                    network_approval_id,
                    url=normalized,
                    surface=network_surface,
                    action=network_action,
                    requested_by=requested_by,
                    agent_id=agent_id,
                    agent_role=agent_role,
                    task_id=task_id,
                    settings=active_settings,
                )
        except (NetworkApprovalRequiredError, NetworkDomainPolicyError, ValueError) as exc:
            raise ProviderEgressPolicyError(str(exc)) from exc
    elif network_approval_id:
        raise ProviderEgressPolicyError(
            "network_approval_id is only valid when provider domain policy requires approval."
        )
    return normalized


def allowed_provider_base_urls(settings: Any) -> set[str]:
    configured_urls = [
        settings.ollama_base_url,
        settings.lm_studio_base_url,
        *(item.strip() for item in settings.provider_allowed_base_urls.split(",") if item.strip()),
    ]
    return {normalize_provider_base_url(item) for item in configured_urls if item.strip()}


def allowed_provider_base_urls_for_provider(provider_id: str, settings: Any) -> set[str]:
    base_urls = []
    if provider_id == "ollama":
        base_urls.append(settings.ollama_base_url)
        base_urls.extend(
            item.strip() for item in settings.provider_allowed_base_urls.split(",") if item.strip()
        )
    elif provider_id == "lm-studio":
        base_urls.append(settings.lm_studio_base_url)
        base_urls.extend(
            item.strip() for item in settings.provider_allowed_base_urls.split(",") if item.strip()
        )
    elif provider_id == "external-openai-compatible":
        base_urls.append(settings.external_openai_compatible_base_url)
    else:
        return set()
    return {normalize_provider_base_url(item) for item in base_urls if item.strip()}


def normalize_provider_base_url(base_url: str) -> str:
    try:
        parts = urlsplit(base_url.strip())
        port = parts.port
    except ValueError as exc:
        raise ProviderEgressPolicyError("Provider base_url is not valid.") from exc

    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ProviderEgressPolicyError("Provider base_url must use http or https with a host.")
    if parts.username or parts.password:
        raise ProviderEgressPolicyError("Provider base_url must not include credentials.")
    if parts.query or parts.fragment:
        raise ProviderEgressPolicyError("Provider base_url must not include query or fragment.")

    netloc = parts.hostname.lower()
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), "", ""))


def open_provider_request(request: Request, *, timeout_seconds: float) -> Any:
    return _PROVIDER_OPENER.open(request, timeout=timeout_seconds)
