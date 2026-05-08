from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dgentic.settings import get_settings

CAPABILITY_ADMIN = "admin"
CAPABILITY_AGENTS = "agents"
CAPABILITY_CLI = "cli"
CAPABILITY_FILESYSTEM = "filesystem"
CAPABILITY_LOGS = "logs"
CAPABILITY_MEMORY = "memory"
CAPABILITY_PROVIDERS = "providers"
CAPABILITY_SESSIONS = "sessions"
CAPABILITY_TASKS = "tasks"
CAPABILITY_TOOLS = "tools"
CAPABILITY_ALL = "*"

PUBLIC_PATHS = frozenset(
    {
        "/",
        "/health",
        "/docs",
        "/docs/oauth2-redirect",
        "/openapi.json",
        "/redoc",
    }
)

CAPABILITY_PATHS: tuple[tuple[str, str], ...] = (
    ("/tasks", CAPABILITY_TASKS),
    ("/guardrails/filesystem", CAPABILITY_FILESYSTEM),
    ("/filesystem", CAPABILITY_FILESYSTEM),
    ("/guardrails/commands", CAPABILITY_CLI),
    ("/cli", CAPABILITY_CLI),
    ("/providers", CAPABILITY_PROVIDERS),
    ("/routing", CAPABILITY_PROVIDERS),
    ("/agents", CAPABILITY_AGENTS),
    ("/memory", CAPABILITY_MEMORY),
    ("/api/v1/memory", CAPABILITY_MEMORY),
    ("/tools", CAPABILITY_TOOLS),
    ("/api/v1/tools", CAPABILITY_TOOLS),
    ("/sessions", CAPABILITY_SESSIONS),
    ("/logs", CAPABILITY_LOGS),
)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    token_id: str
    capabilities: frozenset[str]


def parse_token_map(raw_config: str) -> dict[str, frozenset[str]]:
    token_map: dict[str, frozenset[str]] = {}
    for entry in raw_config.replace("\n", ";").split(";"):
        token, separator, raw_capabilities = entry.strip().partition("=")
        if not separator:
            continue
        token = token.strip()
        capabilities = frozenset(
            capability.strip() for capability in raw_capabilities.split(",") if capability.strip()
        )
        if token and capabilities:
            token_map[token] = capabilities
    return token_map


def capability_for_path(path: str) -> str | None:
    if path in PUBLIC_PATHS:
        return None
    for prefix, capability in CAPABILITY_PATHS:
        if path == prefix or path.startswith(f"{prefix}/"):
            return capability
    return CAPABILITY_ADMIN


def has_capability(principal: Principal, capability: str) -> bool:
    return bool(principal.capabilities & frozenset({capability, CAPABILITY_ADMIN, CAPABILITY_ALL}))


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_route_capability(request: Request) -> Principal | None:
    settings = get_settings()
    if not settings.effective_auth_enabled:
        return None

    required_capability = capability_for_path(request.url.path)
    if required_capability is None:
        return None

    credentials: HTTPAuthorizationCredentials | None = await bearer_scheme(request)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    configured_tokens = parse_token_map(settings.auth_tokens)
    for configured_token, capabilities in configured_tokens.items():
        if compare_digest(credentials.credentials, configured_token):
            principal = Principal(
                token_id=sha256(configured_token.encode("utf-8")).hexdigest()[:12],
                capabilities=capabilities,
            )
            if not has_capability(principal, required_capability):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bearer token lacks the required capability.",
                )
            request.state.principal = principal
            return principal

    raise _unauthorized()
