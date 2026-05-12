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
from dgentic.redaction import redact_sensitive_values
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
CAPABILITY_NETWORK = "network"
CAPABILITY_PROVIDERS = "providers"
CAPABILITY_SESSIONS = "sessions"
CAPABILITY_TASKS = "tasks"
CAPABILITY_TOOLS = "tools"
CAPABILITY_AUTH = "auth"
CAPABILITY_ALL = "*"
KNOWN_CAPABILITIES = frozenset(
    {
        CAPABILITY_ADMIN,
        CAPABILITY_AGENTS,
        CAPABILITY_APPROVALS,
        CAPABILITY_AUTH,
        CAPABILITY_CLI,
        CAPABILITY_CREDENTIALS,
        CAPABILITY_FILESYSTEM,
        CAPABILITY_LOGS,
        CAPABILITY_MEMORY,
        CAPABILITY_NETWORK,
        CAPABILITY_PROVIDERS,
        CAPABILITY_SESSIONS,
        CAPABILITY_TASKS,
        CAPABILITY_TOOLS,
        CAPABILITY_ALL,
    }
)

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
    ("/network/approvals", CAPABILITY_APPROVALS),
    ("/guardrails/network", CAPABILITY_NETWORK),
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
        return _normalize_operator_id(value)

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str]) -> list[str]:
        capabilities = _normalize_capabilities(value, validate_known=True)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)

    @field_validator("label")
    @classmethod
    def label_must_be_redacted(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())


class AuthTokenRotateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    capabilities: list[str] | None = Field(default=None, max_length=50)
    expires_at: datetime | None = None

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        capabilities = _normalize_capabilities(value, validate_known=True)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)

    @field_validator("label")
    @classmethod
    def label_must_be_redacted(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return redact_sensitive_values(value.strip())


class OperatorRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=120)
    capabilities: list[str] = Field(min_length=1, max_length=50)
    group_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("operator_id")
    @classmethod
    def operator_id_must_not_be_blank(cls, value: str) -> str:
        return _normalize_operator_id(value)

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str]) -> list[str]:
        capabilities = _normalize_capabilities(value, validate_known=True)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("group_ids")
    @classmethod
    def group_ids_must_be_normalized(cls, value: list[str]) -> list[str]:
        return list(_normalize_group_ids(value))

    @field_validator("display_name", "role")
    @classmethod
    def text_fields_must_be_stripped(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())


class OperatorUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    capabilities: list[str] | None = Field(default=None, max_length=50)
    group_ids: list[str] | None = Field(default=None, max_length=50)
    status: Literal["active", "inactive"] | None = None

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        capabilities = _normalize_capabilities(value, validate_known=True)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("group_ids")
    @classmethod
    def group_ids_must_be_normalized(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(_normalize_group_ids(value))

    @field_validator("display_name", "role")
    @classmethod
    def text_fields_must_be_stripped(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return redact_sensitive_values(value.strip())


class OperatorGroupRequest(BaseModel):
    group_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)
    capabilities: list[str] = Field(min_length=1, max_length=50)

    @field_validator("group_id")
    @classmethod
    def group_id_must_not_be_blank(cls, value: str) -> str:
        return _normalize_group_id(value)

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str]) -> list[str]:
        capabilities = _normalize_capabilities(value, validate_known=True)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("display_name", "description")
    @classmethod
    def text_fields_must_be_stripped(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())


class OperatorGroupUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    capabilities: list[str] | None = Field(default=None, max_length=50)
    status: Literal["active", "inactive"] | None = None

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        capabilities = _normalize_capabilities(value, validate_known=True)
        if not capabilities:
            raise ValueError("capabilities must include at least one non-blank value.")
        return list(capabilities)

    @field_validator("display_name", "description")
    @classmethod
    def text_fields_must_be_stripped(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return redact_sensitive_values(value.strip())


class OperatorRecord(BaseModel):
    id: str
    display_name: str = ""
    role: str = ""
    capabilities: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deactivated_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        return _normalize_operator_id(value)

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str]) -> list[str]:
        return list(_normalize_capabilities(value, validate_known=True))

    @field_validator("group_ids")
    @classmethod
    def group_ids_must_be_normalized(cls, value: list[str]) -> list[str]:
        return list(_normalize_group_ids(value))

    @field_validator("display_name", "role")
    @classmethod
    def text_fields_must_be_redacted(cls, value: str) -> str:
        return _redact_auth_metadata_text(value)

    @field_validator("created_at", "updated_at", "deactivated_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)


class OperatorView(BaseModel):
    id: str
    display_name: str = ""
    role: str = ""
    capabilities: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    effective_capabilities: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive"]
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None


class OperatorGroupRecord(BaseModel):
    id: str
    display_name: str = ""
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deactivated_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        return _normalize_group_id(value)

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_normalized(cls, value: list[str]) -> list[str]:
        return list(_normalize_capabilities(value, validate_known=True))

    @field_validator("display_name", "description")
    @classmethod
    def text_fields_must_be_redacted(cls, value: str) -> str:
        return _redact_auth_metadata_text(value)

    @field_validator("created_at", "updated_at", "deactivated_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc_datetime(value)


class OperatorGroupView(BaseModel):
    id: str
    display_name: str = ""
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive"]
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None


class AuthTokenRecord(BaseModel):
    id: str
    operator_id: str
    label: str = ""
    token_hash: str
    capabilities: list[str] = Field(default_factory=list)
    operator_profile_required: bool = False
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

    @field_validator("label")
    @classmethod
    def label_must_be_redacted(cls, value: str) -> str:
        return _redact_auth_metadata_text(value)

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
_operators = JsonCollection("operators", OperatorRecord)
_operator_groups = JsonCollection("operator-groups", OperatorGroupRecord)


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


def capability_for_request(method: str, path: str) -> str | None:
    if path in PUBLIC_PATHS:
        return None

    parts = path.strip("/").split("/")
    normalized_method = method.strip().upper()
    if len(parts) >= 2 and parts[0] == "cli" and parts[1] == "approvals":
        action = parts[3] if len(parts) >= 4 else ""
        if action in {"approve", "deny", "review"}:
            return CAPABILITY_APPROVALS
        if action == "execute":
            return CAPABILITY_CLI
        if len(parts) == 2 and normalized_method == "GET":
            return CAPABILITY_APPROVALS
        return CAPABILITY_CLI

    return capability_for_path(path)


def has_capability(principal: Principal, capability: str) -> bool:
    return bool(principal.capabilities & frozenset({capability, CAPABILITY_ADMIN, CAPABILITY_ALL}))


def validate_auth_configuration(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.effective_auth_enabled:
        return

    if parse_token_map(settings.auth_tokens):
        return
    if _usable_persisted_tokens():
        return

    raise AuthConfigurationError(
        "DGentic authentication is enabled but no bearer tokens are configured. "
        "Set DGENTIC_AUTH_TOKENS, create a persisted auth token, or explicitly disable auth "
        "outside production."
    )


def create_operator(
    request: OperatorRequest,
    *,
    actor: str | None = None,
) -> OperatorView:
    now = datetime.now(UTC)
    _validate_operator_group_ids(request.group_ids)
    record = OperatorRecord(
        id=request.operator_id,
        display_name=request.display_name,
        role=request.role,
        capabilities=list(_normalize_capabilities(request.capabilities, validate_known=True)),
        group_ids=list(_normalize_group_ids(request.group_ids)),
        created_at=now,
        updated_at=now,
    )

    def create(items: list[OperatorRecord]) -> tuple[list[OperatorRecord], OperatorRecord]:
        if any(item.id == record.id for item in items):
            raise ValueError(f"Operator already exists: {record.id}")
        return [*items, record], record

    saved = _operators.transact(create)
    _record_operator_event("Created operator identity.", saved, actor=actor)
    return _operator_view(saved)


def create_operator_group(
    request: OperatorGroupRequest,
    *,
    actor: str | None = None,
) -> OperatorGroupView:
    now = datetime.now(UTC)
    record = OperatorGroupRecord(
        id=request.group_id,
        display_name=request.display_name,
        description=request.description,
        capabilities=list(_normalize_capabilities(request.capabilities, validate_known=True)),
        created_at=now,
        updated_at=now,
    )

    def create(
        items: list[OperatorGroupRecord],
    ) -> tuple[list[OperatorGroupRecord], OperatorGroupRecord]:
        if any(item.id == record.id for item in items):
            raise ValueError(f"Operator group already exists: {record.id}")
        return [*items, record], record

    saved = _operator_groups.transact(create)
    _record_operator_group_event("Created operator group.", saved, actor=actor)
    return _operator_group_view(saved)


def list_operators() -> list[OperatorView]:
    return [_operator_view(record) for record in _operators.list()]


def list_operator_groups() -> list[OperatorGroupView]:
    return [_operator_group_view(record) for record in _operator_groups.list()]


def get_operator(operator_id: str) -> OperatorView:
    record = _operators.get(_normalize_operator_id(operator_id))
    if record is None:
        raise KeyError(f"Operator not found: {operator_id}")
    return _operator_view(record)


def get_operator_group(group_id: str) -> OperatorGroupView:
    record = _operator_groups.get(_normalize_group_id(group_id))
    if record is None:
        raise KeyError(f"Operator group not found: {group_id}")
    return _operator_group_view(record)


def update_operator(
    operator_id: str,
    request: OperatorUpdateRequest,
    *,
    actor: str | None = None,
) -> OperatorView:
    now = datetime.now(UTC)
    normalized_operator_id = _normalize_operator_id(operator_id)

    def update(record: OperatorRecord) -> OperatorRecord:
        changes: dict[str, object] = {"updated_at": now}
        if "display_name" in request.model_fields_set:
            changes["display_name"] = request.display_name or ""
        if "role" in request.model_fields_set:
            changes["role"] = request.role or ""
        if request.capabilities is not None:
            changes["capabilities"] = list(
                _normalize_capabilities(request.capabilities, validate_known=True)
            )
        if request.group_ids is not None:
            _validate_operator_group_ids(request.group_ids)
            changes["group_ids"] = list(_normalize_group_ids(request.group_ids))
        if request.status is not None:
            changes["status"] = request.status
            changes["deactivated_at"] = now if request.status == "inactive" else None
        return record.model_copy(update=changes)

    try:
        saved = _operators.update(normalized_operator_id, update)
    except KeyError as exc:
        raise KeyError(f"Operator not found: {operator_id}") from exc
    _record_operator_event("Updated operator identity.", saved, actor=actor)
    return _operator_view(saved)


def update_operator_group(
    group_id: str,
    request: OperatorGroupUpdateRequest,
    *,
    actor: str | None = None,
) -> OperatorGroupView:
    now = datetime.now(UTC)
    normalized_group_id = _normalize_group_id(group_id)

    def update(record: OperatorGroupRecord) -> OperatorGroupRecord:
        changes: dict[str, object] = {"updated_at": now}
        if "display_name" in request.model_fields_set:
            changes["display_name"] = request.display_name or ""
        if "description" in request.model_fields_set:
            changes["description"] = request.description or ""
        if request.capabilities is not None:
            changes["capabilities"] = list(
                _normalize_capabilities(request.capabilities, validate_known=True)
            )
        if request.status is not None:
            changes["status"] = request.status
            changes["deactivated_at"] = now if request.status == "inactive" else None
        return record.model_copy(update=changes)

    try:
        saved = _operator_groups.update(normalized_group_id, update)
    except KeyError as exc:
        raise KeyError(f"Operator group not found: {group_id}") from exc
    _record_operator_group_event("Updated operator group.", saved, actor=actor)
    return _operator_group_view(saved)


def create_auth_token(
    request: AuthTokenRequest,
    *,
    actor: str | None = None,
) -> AuthTokenCreateResponse:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    operator = _active_operator_for_token_request(request.operator_id)
    capabilities = _normalize_capabilities(request.capabilities, validate_known=True)
    _validate_operator_capabilities(operator, capabilities)
    record = AuthTokenRecord(
        id=f"auth-token-{uuid4()}",
        operator_id=operator.id,
        label=request.label,
        token_hash=_hash_token(raw_token),
        capabilities=list(capabilities),
        operator_profile_required=True,
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
            operator = _operator_for_auth_record(expired_record)
            capabilities = _normalize_capabilities(
                request.capabilities or expired_record.capabilities,
                validate_known=True,
            )
            if operator is not None:
                _validate_operator_capabilities(operator, capabilities)
            replacement = AuthTokenRecord(
                id=f"auth-token-{uuid4()}",
                operator_id=expired_record.operator_id,
                label=request.label if request.label is not None else expired_record.label,
                token_hash=_hash_token(raw_token),
                capabilities=list(capabilities),
                operator_profile_required=expired_record.operator_profile_required
                or operator is not None,
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

    required_capability = capability_for_request(request.method, request.url.path)
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
        try:
            operator = _operator_for_auth_record(record)
        except ValueError:
            return None
        capabilities = frozenset(record.capabilities)
        if operator is not None:
            operator_capabilities = frozenset(_operator_effective_capabilities(operator))
            if not _capabilities_allowed_by_operator(operator_capabilities, capabilities):
                capabilities = capabilities & operator_capabilities
            if not capabilities:
                return None
        saved = _auth_tokens.update(
            record.id,
            lambda current: current.model_copy(update={"last_used_at": now, "updated_at": now}),
        )
        return Principal(
            token_id=saved.id,
            operator_id=saved.operator_id,
            capabilities=capabilities,
        )
    return None


def _active_persisted_tokens() -> list[AuthTokenRecord]:
    now = datetime.now(UTC)
    records = [_expire_record_if_needed(record, now=now) for record in _auth_tokens.list()]
    return [record for record in records if record.status == "active"]


def _usable_persisted_tokens() -> list[AuthTokenRecord]:
    usable_records: list[AuthTokenRecord] = []
    for record in _active_persisted_tokens():
        try:
            operator = _operator_for_auth_record(record)
        except ValueError:
            continue
        if operator is not None:
            token_capabilities = frozenset(record.capabilities)
            operator_capabilities = frozenset(_operator_effective_capabilities(operator))
            if not _capabilities_allowed_by_operator(operator_capabilities, token_capabilities):
                token_capabilities = token_capabilities & operator_capabilities
            if not token_capabilities:
                continue
        usable_records.append(record)
    return usable_records


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
        label=_redact_auth_metadata_text(record.label),
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


def _operator_view(record: OperatorRecord) -> OperatorView:
    return OperatorView(
        id=record.id,
        display_name=_redact_auth_metadata_text(record.display_name),
        role=_redact_auth_metadata_text(record.role),
        capabilities=list(_normalize_capabilities(record.capabilities)),
        group_ids=list(_normalize_group_ids(record.group_ids)),
        effective_capabilities=list(_operator_effective_capabilities(record)),
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deactivated_at=record.deactivated_at,
    )


def _operator_group_view(record: OperatorGroupRecord) -> OperatorGroupView:
    return OperatorGroupView(
        id=record.id,
        display_name=_redact_auth_metadata_text(record.display_name),
        description=_redact_auth_metadata_text(record.description),
        capabilities=list(_normalize_capabilities(record.capabilities)),
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deactivated_at=record.deactivated_at,
    )


def _active_operator_for_token_request(operator_id: str) -> OperatorRecord:
    normalized_operator_id = _normalize_operator_id(operator_id)
    operator = _operators.get(normalized_operator_id)
    if operator is None:
        raise ValueError(f"Operator not found: {normalized_operator_id}")
    if operator.status != "active":
        raise ValueError(f"Operator is not active: {normalized_operator_id}")
    return operator


def _operator_for_auth_record(record: AuthTokenRecord) -> OperatorRecord | None:
    operator = _operators.get(_normalize_operator_id(record.operator_id))
    if operator is None:
        if record.operator_profile_required:
            raise ValueError(f"Operator not found: {record.operator_id}")
        return None
    if operator.status != "active":
        raise ValueError(f"Operator is not active: {record.operator_id}")
    return operator


def _validate_operator_capabilities(
    operator: OperatorRecord,
    requested_capabilities: tuple[str, ...],
) -> None:
    operator_capabilities = frozenset(_operator_effective_capabilities(operator))
    requested = frozenset(requested_capabilities)
    if _capabilities_allowed_by_operator(operator_capabilities, requested):
        return
    raise ValueError("Requested token capabilities exceed operator assignment.")


def _operator_effective_capabilities(operator: OperatorRecord) -> tuple[str, ...]:
    capabilities = set(_normalize_capabilities(operator.capabilities, validate_known=True))
    for group_id in _normalize_group_ids(operator.group_ids):
        group = _operator_groups.get(group_id)
        if group is None or group.status != "active":
            continue
        capabilities.update(_normalize_capabilities(group.capabilities, validate_known=True))
    return _normalize_capabilities(list(capabilities), validate_known=True)


def _validate_operator_group_ids(group_ids: list[str]) -> None:
    for group_id in _normalize_group_ids(group_ids):
        if _operator_groups.get(group_id) is None:
            raise ValueError(f"Operator group not found: {group_id}")


def _capabilities_allowed_by_operator(
    operator_capabilities: frozenset[str],
    requested_capabilities: frozenset[str],
) -> bool:
    if operator_capabilities & frozenset({CAPABILITY_ADMIN, CAPABILITY_ALL}):
        return True
    return requested_capabilities.issubset(operator_capabilities)


def _normalize_capabilities(
    values: list[str],
    *,
    validate_known: bool = False,
) -> tuple[str, ...]:
    capabilities: list[str] = []
    for value in values:
        capability = value.strip()
        if validate_known and capability and capability not in KNOWN_CAPABILITIES:
            raise ValueError(f"Unknown capability: {capability}")
        if capability and capability not in capabilities:
            capabilities.append(capability)
    return tuple(sorted(capabilities))


def _normalize_operator_id(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("operator_id must not be blank.")
    return stripped


def _normalize_group_id(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("group_id must not be blank.")
    return stripped


def _normalize_group_ids(values: list[str]) -> tuple[str, ...]:
    group_ids: list[str] = []
    for value in values:
        group_id = _normalize_group_id(value)
        if group_id and group_id not in group_ids:
            group_ids.append(group_id)
    return tuple(sorted(group_ids))


def _redact_auth_metadata_text(value: str) -> str:
    return redact_sensitive_values(value.strip())


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
            "label": _redact_auth_metadata_text(record.label),
            "capabilities": list(_normalize_capabilities(record.capabilities)),
            "status": record.status,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "rotated_from_token_id": record.rotated_from_token_id,
            "rotated_to_token_id": record.rotated_to_token_id,
        },
    )


def _record_operator_event(
    message: str,
    record: OperatorRecord,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.auth,
        message,
        actor=actor or "system",
        subject_id=record.id,
        metadata={
            "operator_id": record.id,
            "display_name": _redact_auth_metadata_text(record.display_name),
            "role": _redact_auth_metadata_text(record.role),
            "capabilities": list(_normalize_capabilities(record.capabilities)),
            "group_ids": list(_normalize_group_ids(record.group_ids)),
            "effective_capabilities": list(_operator_effective_capabilities(record)),
            "status": record.status,
            "deactivated_at": record.deactivated_at.isoformat() if record.deactivated_at else None,
        },
    )


def _record_operator_group_event(
    message: str,
    record: OperatorGroupRecord,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.auth,
        message,
        actor=actor or "system",
        subject_id=record.id,
        metadata={
            "group_id": record.id,
            "display_name": _redact_auth_metadata_text(record.display_name),
            "description": _redact_auth_metadata_text(record.description),
            "capabilities": list(_normalize_capabilities(record.capabilities)),
            "status": record.status,
            "deactivated_at": record.deactivated_at.isoformat() if record.deactivated_at else None,
        },
    )
