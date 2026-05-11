import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from dgentic.events import event_log
from dgentic.schemas import LogEventType
from dgentic.settings import Settings, get_settings
from dgentic.storage import JsonCollection

CAPABILITY_ADMIN = "admin"
CAPABILITY_AGENTS = "agents"
CAPABILITY_APPROVALS = "approvals"
CAPABILITY_CLI = "cli"
CAPABILITY_CREDENTIALS = "credentials"
CAPABILITY_FILESYSTEM = "filesystem"
CAPABILITY_LOGS = "logs"
CAPABILITY_MEMORY = "memory"
CAPABILITY_PROVIDERS = "providers"
CAPABILITY_SESSIONS = "sessions"
CAPABILITY_TASKS = "tasks"
CAPABILITY_TOOLS = "tools"
CAPABILITY_AUTH = "auth"
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
    ("/auth", CAPABILITY_AUTH),
    ("/credentials", CAPABILITY_CREDENTIALS),
    ("/guardrails/filesystem", CAPABILITY_FILESYSTEM),
    ("/filesystem", CAPABILITY_FILESYSTEM),
    ("/guardrails/commands", CAPABILITY_CLI),
    ("/cli", CAPABILITY_CLI),
    ("/providers/approvals", CAPABILITY_APPROVALS),
    ("/providers", CAPABILITY_PROVIDERS),
    ("/routing", CAPABILITY_PROVIDERS),
    ("/agents", CAPABILITY_AGENTS),
    ("/memory", CAPABILITY_MEMORY),
    ("/api/v1/memory", CAPABILITY_MEMORY),
    ("/tools/approvals", CAPABILITY_APPROVALS),
    ("/tools", CAPABILITY_TOOLS),
    ("/api/v1/tools", CAPABILITY_TOOLS),
    ("/sessions", CAPABILITY_SESSIONS),
    ("/logs", CAPABILITY_LOGS),
)

bearer_scheme = HTTPBearer(auto_error=False)
TOKEN_HASH_ITERATIONS = 120_000


@dataclass(frozen=True)
class Principal:
    token_id: str
    capabilities: frozenset[str]
    operator_id: str | None = None

    @property
    def actor_id(self) -> str:
        return self.operator_id or self.token_id


class AuthConfigurationError(RuntimeError):
    """Raised when authentication is enabled without usable credentials."""


class AuthTokenRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=120)
    capabilities: list[str] = Field(min_length=1, max_length=50)
    expires_at: datetime | None = None

    @field_validator("operator_id")
    @classmethod
    def operator_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("operator_id must not be blank.")
        return stripped

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str]) -> list[str]:
        capabilities = _normalize_capabilities(value)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)


class AuthTokenRotateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    capabilities: list[str] | None = Field(default=None, max_length=50)
    expires_at: datetime | None = None

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        capabilities = _normalize_capabilities(value)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)


class AuthTokenRecord(BaseModel):
    id: str
    operator_id: str
    label: str = ""
    token_hash: str
    capabilities: list[str] = Field(default_factory=list)
    status: Literal["active", "revoked", "expired"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    rotated_from_token_id: str | None = None
    rotated_to_token_id: str | None = None
    last_used_at: datetime | None = None

    @field_validator("operator_id")
    @classmethod
    def operator_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("operator_id must not be blank.")
        return stripped

    @field_validator("created_at", "updated_at", "expires_at", "revoked_at", "last_used_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)


class AuthTokenView(BaseModel):
    id: str
    operator_id: str
    label: str = ""
    capabilities: list[str] = Field(default_factory=list)
    status: Literal["active", "revoked", "expired"]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    rotated_from_token_id: str | None = None
    rotated_to_token_id: str | None = None
    last_used_at: datetime | None = None


class AuthTokenCreateResponse(BaseModel):
    token: str
    record: AuthTokenView


_auth_tokens = JsonCollection("auth-tokens", AuthTokenRecord)


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
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "providers" and parts[2] == "approvals":
        return CAPABILITY_APPROVALS
    for prefix, capability in CAPABILITY_PATHS:
        if path == prefix or path.startswith(f"{prefix}/"):
            return capability
    return CAPABILITY_ADMIN


def has_capability(principal: Principal, capability: str) -> bool:
    return bool(principal.capabilities & frozenset({capability, CAPABILITY_ADMIN, CAPABILITY_ALL}))


def validate_auth_configuration(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.effective_auth_enabled:
        return

    if parse_token_map(settings.auth_tokens):
        return
    if _active_persisted_tokens():
        return

    raise AuthConfigurationError(
        "DGentic authentication is enabled but no bearer tokens are configured. "
        "Set DGENTIC_AUTH_TOKENS, create a persisted auth token, or explicitly disable auth "
        "outside production."
    )


def create_auth_token(
    request: AuthTokenRequest,
    *,
    actor: str | None = None,
) -> AuthTokenCreateResponse:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    record = AuthTokenRecord(
        id=f"auth-token-{uuid4()}",
        operator_id=request.operator_id,
        label=request.label,
        token_hash=_hash_token(raw_token),
        capabilities=list(_normalize_capabilities(request.capabilities)),
        created_at=now,
        updated_at=now,
        expires_at=request.expires_at,
    )
    saved = _auth_tokens.upsert(record)
    _record_auth_event(
        "Created persisted auth token.",
        saved,
        actor=actor,
    )
    return AuthTokenCreateResponse(token=raw_token, record=_token_view(saved))


def list_auth_tokens() -> list[AuthTokenView]:
    now = datetime.now(UTC)
    return [
        _token_view(_expire_record_if_needed(record, now=now)) for record in _auth_tokens.list()
    ]


def rotate_auth_token(
    token_id: str,
    request: AuthTokenRotateRequest,
    *,
    actor: str | None = None,
) -> AuthTokenCreateResponse:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)

    def rotate(items: list[AuthTokenRecord]) -> tuple[list[AuthTokenRecord], AuthTokenRecord]:
        updated_items: list[AuthTokenRecord] = []
        replacement: AuthTokenRecord | None = None
        found = False
        for record in items:
            if record.id != token_id:
                updated_items.append(record)
                continue
            found = True
            expired_record = _expired_record_copy_if_needed(record, now=now)
            if expired_record.status != "active":
                raise ValueError("Auth token is not active.")
            replacement = AuthTokenRecord(
                id=f"auth-token-{uuid4()}",
                operator_id=expired_record.operator_id,
                label=request.label if request.label is not None else expired_record.label,
                token_hash=_hash_token(raw_token),
                capabilities=list(
                    _normalize_capabilities(request.capabilities or expired_record.capabilities)
                ),
                created_at=now,
                updated_at=now,
                expires_at=(
                    request.expires_at
                    if "expires_at" in request.model_fields_set
                    else expired_record.expires_at
                ),
                rotated_from_token_id=expired_record.id,
            )
            updated_items.append(
                expired_record.model_copy(
                    update={
                        "status": "revoked",
                        "revoked_at": now,
                        "rotated_to_token_id": replacement.id,
                        "updated_at": now,
                    }
                )
            )
            updated_items.append(replacement)
        if not found or replacement is None:
            raise KeyError(f"Auth token not found: {token_id}")
        return updated_items, replacement

    saved = _auth_tokens.transact(rotate)
    _record_auth_event("Rotated persisted auth token.", saved, actor=actor)
    return AuthTokenCreateResponse(token=raw_token, record=_token_view(saved))


def revoke_auth_token(
    token_id: str,
    *,
    actor: str | None = None,
) -> AuthTokenView:
    now = datetime.now(UTC)

    def revoke(record: AuthTokenRecord) -> AuthTokenRecord:
        expired_record = _expired_record_copy_if_needed(record, now=now)
        if expired_record.status == "revoked":
            return expired_record
        return expired_record.model_copy(
            update={"status": "revoked", "revoked_at": now, "updated_at": now}
        )

    try:
        saved = _auth_tokens.update(token_id, revoke)
    except KeyError as exc:
        raise KeyError(f"Auth token not found: {token_id}") from exc
    _record_auth_event("Revoked persisted auth token.", saved, actor=actor)
    return _token_view(saved)


def expire_auth_token(
    token_id: str,
    *,
    actor: str | None = None,
) -> AuthTokenView:
    now = datetime.now(UTC)

    def expire(record: AuthTokenRecord) -> AuthTokenRecord:
        return record.model_copy(
            update={
                "status": "expired",
                "expires_at": now,
                "updated_at": now,
            }
        )

    try:
        saved = _auth_tokens.update(token_id, expire)
    except KeyError as exc:
        raise KeyError(f"Auth token not found: {token_id}") from exc
    _record_auth_event("Expired persisted auth token.", saved, actor=actor)
    return _token_view(saved)


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

    persisted_principal = _principal_from_persisted_token(credentials.credentials)
    if persisted_principal is not None:
        if not has_capability(persisted_principal, required_capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bearer token lacks the required capability.",
            )
        request.state.principal = persisted_principal
        return persisted_principal

    raise _unauthorized()


def _principal_from_persisted_token(token: str) -> Principal | None:
    now = datetime.now(UTC)
    for record in _auth_tokens.list():
        record = _expire_record_if_needed(record, now=now)
        if not _verify_token_hash(token, record.token_hash):
            continue
        if record.status != "active":
            return None
        saved = _auth_tokens.update(
            record.id,
            lambda current: current.model_copy(update={"last_used_at": now, "updated_at": now}),
        )
        return Principal(
            token_id=saved.id,
            operator_id=saved.operator_id,
            capabilities=frozenset(saved.capabilities),
        )
    return None


def _active_persisted_tokens() -> list[AuthTokenRecord]:
    now = datetime.now(UTC)
    records = [_expire_record_if_needed(record, now=now) for record in _auth_tokens.list()]
    return [record for record in records if record.status == "active"]


def _expire_record_if_needed(
    record: AuthTokenRecord,
    *,
    now: datetime,
) -> AuthTokenRecord:
    expired = _expired_record_copy_if_needed(record, now=now)
    if expired == record:
        return record
    try:
        return _auth_tokens.update(record.id, lambda _current: expired)
    except KeyError:
        return expired


def _expired_record_copy_if_needed(
    record: AuthTokenRecord,
    *,
    now: datetime,
) -> AuthTokenRecord:
    if record.status != "active" or record.expires_at is None or record.expires_at > now:
        return record
    return record.model_copy(update={"status": "expired", "updated_at": now})


def _token_view(record: AuthTokenRecord) -> AuthTokenView:
    return AuthTokenView(
        id=record.id,
        operator_id=record.operator_id,
        label=record.label,
        capabilities=list(_normalize_capabilities(record.capabilities)),
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        rotated_from_token_id=record.rotated_from_token_id,
        rotated_to_token_id=record.rotated_to_token_id,
        last_used_at=record.last_used_at,
    )


def _normalize_capabilities(values: list[str]) -> tuple[str, ...]:
    capabilities: list[str] = []
    for value in values:
        capability = value.strip()
        if capability and capability not in capabilities:
            capabilities.append(capability)
    return tuple(sorted(capabilities))


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash_token(token: str) -> str:
    salt = secrets.token_hex(16)
    digest = pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        bytes.fromhex(salt),
        TOKEN_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2-sha256${TOKEN_HASH_ITERATIONS}${salt}${digest}"


def _verify_token_hash(token: str, token_hash: str) -> bool:
    if token_hash.startswith("sha256:"):
        return compare_digest("sha256:" + sha256(token.encode("utf-8")).hexdigest(), token_hash)
    try:
        algorithm, iterations, salt, digest = token_hash.split("$", 3)
        if algorithm != "pbkdf2-sha256":
            return False
        candidate = pbkdf2_hmac(
            "sha256",
            token.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
    except (TypeError, ValueError):
        return False
    return compare_digest(candidate, digest)


def _record_auth_event(
    message: str,
    record: AuthTokenRecord,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.auth,
        message,
        actor=actor or "system",
        subject_id=record.id,
        metadata={
            "operator_id": record.operator_id,
            "label": record.label,
            "capabilities": list(_normalize_capabilities(record.capabilities)),
            "status": record.status,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "rotated_from_token_id": record.rotated_from_token_id,
            "rotated_to_token_id": record.rotated_to_token_id,
        },
    )
