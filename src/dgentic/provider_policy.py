from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
) -> str:
    active_settings = settings if settings is not None else get_settings()
    normalized = normalize_provider_base_url(base_url)
    allowed = allowed_provider_base_urls(active_settings)
    if normalized not in allowed:
        raise ProviderEgressPolicyError(
            f"Provider base_url for {provider_id} is not allowed by egress policy."
        )
    return normalized


def allowed_provider_base_urls(settings: Any) -> set[str]:
    configured_urls = [
        settings.ollama_base_url,
        settings.lm_studio_base_url,
        *(item.strip() for item in settings.provider_allowed_base_urls.split(",") if item.strip()),
    ]
    return {normalize_provider_base_url(item) for item in configured_urls}


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
