import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

MAX_PROVIDER_ROLE_ROUTING_CHARS = 16_384
MAX_PROVIDER_ROLE_ROUTING_ENTRIES = 64
MAX_PROVIDER_ROLE_ROUTING_KEY_CHARS = 128
MAX_PROVIDER_ROLE_ROUTING_VALUE_CHARS = 256
PROVIDER_ROLE_ROUTE_KEYS = {"provider_id", "model"}


class ProviderRoutingConfigurationError(ValueError):
    """Raised when provider role-routing configuration is invalid."""


@dataclass(frozen=True)
class ProviderRoleRoute:
    role: str
    provider_id: str
    model: str


def validate_provider_role_routing(settings: Any) -> None:
    provider_role_routing(settings)


def provider_role_routing(settings: Any) -> dict[str, ProviderRoleRoute]:
    raw_routing = str(getattr(settings, "provider_role_routing", "") or "").strip()
    return dict(_parse_provider_role_routing(raw_routing))


def provider_role_route_for(settings: Any, role: str) -> ProviderRoleRoute | None:
    normalized_role = _normalized_role(role)
    if not normalized_role:
        return None
    return provider_role_routing(settings).get(normalized_role)


@lru_cache(maxsize=16)
def _parse_provider_role_routing(raw_routing: str) -> tuple[tuple[str, ProviderRoleRoute], ...]:
    if not raw_routing:
        return ()
    if len(raw_routing) > MAX_PROVIDER_ROLE_ROUTING_CHARS:
        raise ProviderRoutingConfigurationError("Provider role routing is too large.")

    try:
        decoded = json.loads(raw_routing)
    except json.JSONDecodeError as exc:
        raise ProviderRoutingConfigurationError("Provider role routing must be JSON.") from exc
    if not isinstance(decoded, dict):
        raise ProviderRoutingConfigurationError("Provider role routing must be a JSON object.")
    if len(decoded) > MAX_PROVIDER_ROLE_ROUTING_ENTRIES:
        raise ProviderRoutingConfigurationError("Provider role routing has too many entries.")

    entries: list[tuple[str, ProviderRoleRoute]] = []
    for raw_role, raw_route in decoded.items():
        role = _validated_role(raw_role)
        if any(existing_role == role for existing_role, _ in entries):
            raise ProviderRoutingConfigurationError(
                "Provider role routing contains duplicate role entries."
            )
        route = _provider_role_route(role, raw_route)
        entries.append((role, route))
    return tuple(entries)


def _provider_role_route(role: str, raw_route: Any) -> ProviderRoleRoute:
    if not isinstance(raw_route, dict):
        raise ProviderRoutingConfigurationError("Provider role routing entries must be objects.")
    unknown_keys = set(raw_route) - PROVIDER_ROLE_ROUTE_KEYS
    if unknown_keys:
        raise ProviderRoutingConfigurationError(
            "Provider role routing contains unsupported entry keys."
        )
    return ProviderRoleRoute(
        role=role,
        provider_id=_validated_route_value(raw_route.get("provider_id"), "provider_id"),
        model=_validated_route_value(raw_route.get("model"), "model"),
    )


def _validated_role(value: Any) -> str:
    if not isinstance(value, str):
        raise ProviderRoutingConfigurationError("Provider role routing roles must be strings.")
    normalized = _normalized_role(value)
    if not normalized:
        raise ProviderRoutingConfigurationError("Provider role routing roles must not be blank.")
    if len(normalized) > MAX_PROVIDER_ROLE_ROUTING_KEY_CHARS:
        raise ProviderRoutingConfigurationError("Provider role routing roles are too long.")
    return normalized


def _validated_route_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ProviderRoutingConfigurationError(
            f"Provider role routing {field_name} must be a string."
        )
    normalized = value.strip()
    if not normalized:
        raise ProviderRoutingConfigurationError(
            f"Provider role routing {field_name} must not be blank."
        )
    if len(normalized) > MAX_PROVIDER_ROLE_ROUTING_VALUE_CHARS:
        raise ProviderRoutingConfigurationError(f"Provider role routing {field_name} is too long.")
    return normalized


def _normalized_role(role: str) -> str:
    return str(role or "").strip().lower()
