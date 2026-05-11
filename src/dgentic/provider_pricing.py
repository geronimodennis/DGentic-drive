import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

MAX_PROVIDER_PRICING_CATALOG_CHARS = 65_536
MAX_PROVIDER_PRICING_ENTRIES = 128
MAX_PROVIDER_PRICING_KEY_CHARS = 256
MAX_PROVIDER_TOKEN_RATE_USD = 1_000.0
MAX_PROVIDER_REQUEST_ESTIMATE_USD = 1_000.0
PROVIDER_PRICING_RATE_KEYS = {
    "prompt_usd_per_1k_tokens",
    "completion_usd_per_1k_tokens",
    "request_estimate_usd",
}


class ProviderPricingConfigurationError(ValueError):
    """Raised when provider pricing catalog configuration is invalid."""


@dataclass(frozen=True)
class ProviderPricingEntry:
    provider_id: str
    model: str
    prompt_usd_per_1k_tokens: float | None = None
    completion_usd_per_1k_tokens: float | None = None
    request_estimate_usd: float | None = None


def validate_provider_pricing_catalog(settings: Any) -> None:
    provider_pricing_catalog(settings)


def provider_pricing_catalog(settings: Any) -> dict[tuple[str, str], ProviderPricingEntry]:
    raw_catalog = str(getattr(settings, "provider_pricing_catalog", "") or "").strip()
    return dict(_parse_provider_pricing_catalog(raw_catalog))


def provider_model_pricing(
    settings: Any,
    *,
    provider_id: str,
    model: str,
) -> ProviderPricingEntry | None:
    return provider_pricing_catalog(settings).get((provider_id, model))


def provider_request_estimate_usd(
    settings: Any,
    *,
    provider_id: str,
    model: str,
) -> float | None:
    entry = provider_model_pricing(settings, provider_id=provider_id, model=model)
    return None if entry is None else entry.request_estimate_usd


def estimate_provider_usage_cost_usd(
    settings: Any,
    *,
    provider_id: str,
    model: str,
    usage_metadata: dict[str, int | float],
) -> float | None:
    entry = provider_model_pricing(settings, provider_id=provider_id, model=model)
    if entry is None:
        return None

    prompt_tokens = _safe_usage_token_count(usage_metadata.get("prompt_tokens"))
    completion_tokens = _safe_usage_token_count(usage_metadata.get("completion_tokens"))
    if (
        prompt_tokens is not None
        and completion_tokens is not None
        and entry.prompt_usd_per_1k_tokens is not None
        and entry.completion_usd_per_1k_tokens is not None
    ):
        prompt_cost = (prompt_tokens / 1000.0) * entry.prompt_usd_per_1k_tokens
        completion_cost = (completion_tokens / 1000.0) * entry.completion_usd_per_1k_tokens
        return round(prompt_cost + completion_cost, 12)

    return entry.request_estimate_usd


@lru_cache(maxsize=16)
def _parse_provider_pricing_catalog(
    raw_catalog: str,
) -> tuple[tuple[tuple[str, str], ProviderPricingEntry], ...]:
    if not raw_catalog:
        return ()
    if len(raw_catalog) > MAX_PROVIDER_PRICING_CATALOG_CHARS:
        raise ProviderPricingConfigurationError("Provider pricing catalog is too large.")

    try:
        decoded = json.loads(raw_catalog)
    except json.JSONDecodeError as exc:
        raise ProviderPricingConfigurationError("Provider pricing catalog must be JSON.") from exc
    if not isinstance(decoded, dict):
        raise ProviderPricingConfigurationError("Provider pricing catalog must be a JSON object.")

    entries: list[tuple[tuple[str, str], ProviderPricingEntry]] = []
    for raw_provider_id, raw_models in decoded.items():
        provider_id = _validated_pricing_key(raw_provider_id, "provider id")
        if not isinstance(raw_models, dict):
            raise ProviderPricingConfigurationError(
                "Provider pricing catalog values must be model objects."
            )
        for raw_model, raw_entry in raw_models.items():
            if len(entries) >= MAX_PROVIDER_PRICING_ENTRIES:
                raise ProviderPricingConfigurationError(
                    "Provider pricing catalog has too many entries."
                )
            model = _validated_pricing_key(raw_model, "model")
            entry = _provider_pricing_entry(provider_id, model, raw_entry)
            key = (provider_id, model)
            if any(existing_key == key for existing_key, _ in entries):
                raise ProviderPricingConfigurationError(
                    "Provider pricing catalog contains duplicate entries."
                )
            entries.append((key, entry))
    return tuple(entries)


def _provider_pricing_entry(
    provider_id: str,
    model: str,
    raw_entry: Any,
) -> ProviderPricingEntry:
    if not isinstance(raw_entry, dict):
        raise ProviderPricingConfigurationError("Provider pricing catalog entries must be objects.")
    unknown_keys = set(raw_entry) - PROVIDER_PRICING_RATE_KEYS
    if unknown_keys:
        raise ProviderPricingConfigurationError(
            "Provider pricing catalog contains unsupported entry keys."
        )

    prompt_rate = _optional_non_negative_price(
        raw_entry.get("prompt_usd_per_1k_tokens"),
        max_value=MAX_PROVIDER_TOKEN_RATE_USD,
    )
    completion_rate = _optional_non_negative_price(
        raw_entry.get("completion_usd_per_1k_tokens"),
        max_value=MAX_PROVIDER_TOKEN_RATE_USD,
    )
    request_estimate = _optional_non_negative_price(
        raw_entry.get("request_estimate_usd"),
        max_value=MAX_PROVIDER_REQUEST_ESTIMATE_USD,
    )

    if (prompt_rate is None) != (completion_rate is None):
        raise ProviderPricingConfigurationError(
            "Provider pricing catalog token rates must include prompt and completion rates."
        )
    if prompt_rate is None and request_estimate is None:
        raise ProviderPricingConfigurationError(
            "Provider pricing catalog entries must include token rates or a request estimate."
        )

    return ProviderPricingEntry(
        provider_id=provider_id,
        model=model,
        prompt_usd_per_1k_tokens=prompt_rate,
        completion_usd_per_1k_tokens=completion_rate,
        request_estimate_usd=request_estimate,
    )


def _validated_pricing_key(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ProviderPricingConfigurationError(
            f"Provider pricing catalog {field_name} must be a string."
        )
    normalized = value.strip()
    if not normalized:
        raise ProviderPricingConfigurationError(
            f"Provider pricing catalog {field_name} must not be blank."
        )
    if len(normalized) > MAX_PROVIDER_PRICING_KEY_CHARS:
        raise ProviderPricingConfigurationError(
            f"Provider pricing catalog {field_name} is too long."
        )
    return normalized


def _optional_non_negative_price(value: Any, *, max_value: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProviderPricingConfigurationError(
            "Provider pricing catalog prices must be finite numbers."
        )
    price = float(value)
    if not math.isfinite(price) or price < 0 or price > max_value:
        raise ProviderPricingConfigurationError(
            "Provider pricing catalog prices must be finite non-negative numbers."
        )
    return price


def _safe_usage_token_count(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    token_count = float(value)
    if not math.isfinite(token_count) or token_count < 0:
        return None
    return token_count
