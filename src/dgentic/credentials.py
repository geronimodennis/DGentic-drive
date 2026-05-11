import re
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType
from dgentic.storage import JsonCollection

CREDENTIAL_ENV_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class CredentialReferenceRequest(BaseModel):
    env_var: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=120)
    purpose: Literal["provider", "runtime"] = "provider"

    @field_validator("env_var")
    @classmethod
    def env_var_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if not CREDENTIAL_ENV_PATTERN.fullmatch(normalized):
            raise ValueError("env_var must be a valid environment variable name.")
        return normalized

    @field_validator("label")
    @classmethod
    def label_must_be_trimmed(cls, value: str) -> str:
        return _redact_credential_label(value)


class CredentialReferenceRecord(BaseModel):
    id: str
    env_var: str
    label: str = ""
    purpose: Literal["provider", "runtime"] = "provider"
    status: Literal["active", "revoked"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None

    @field_validator("env_var")
    @classmethod
    def env_var_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if not CREDENTIAL_ENV_PATTERN.fullmatch(normalized):
            raise ValueError("env_var must be a valid environment variable name.")
        return normalized

    @field_validator("label")
    @classmethod
    def label_must_be_trimmed(cls, value: str) -> str:
        return _redact_credential_label(value)

    @field_validator("created_at", "updated_at", "revoked_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class CredentialReferenceView(BaseModel):
    id: str
    env_var: str
    label: str = ""
    purpose: Literal["provider", "runtime"]
    status: Literal["active", "revoked"]
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


_credential_references = JsonCollection("credential-references", CredentialReferenceRecord)


def create_credential_reference(
    request: CredentialReferenceRequest,
    *,
    actor: str | None = None,
) -> CredentialReferenceView:
    now = datetime.now(UTC)
    record = CredentialReferenceRecord(
        id=f"credential-ref-{uuid4()}",
        env_var=request.env_var,
        label=request.label,
        purpose=request.purpose,
        created_at=now,
        updated_at=now,
    )
    saved = _credential_references.upsert(record)
    _record_credential_event("Created credential reference.", saved, actor=actor)
    return _credential_reference_view(saved)


def list_credential_references() -> list[CredentialReferenceView]:
    return [_credential_reference_view(record) for record in _credential_references.list()]


def revoke_credential_reference(
    credential_ref_id: str,
    *,
    actor: str | None = None,
) -> CredentialReferenceView:
    now = datetime.now(UTC)

    def revoke(record: CredentialReferenceRecord) -> CredentialReferenceRecord:
        if record.status == "revoked":
            return record
        return record.model_copy(update={"status": "revoked", "revoked_at": now, "updated_at": now})

    try:
        saved = _credential_references.update(credential_ref_id, revoke)
    except KeyError as exc:
        raise KeyError(f"Credential reference not found: {credential_ref_id}") from exc
    _record_credential_event("Revoked credential reference.", saved, actor=actor)
    return _credential_reference_view(saved)


def credential_env_for_reference(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None = None,
) -> str:
    record = _credential_references.get(credential_ref_id)
    if record is None:
        raise KeyError(f"Credential reference not found: {credential_ref_id}")
    if record.status != "active":
        raise PermissionError("Credential reference is not active.")
    if purpose is not None and record.purpose != purpose:
        raise PermissionError("Credential reference purpose is not allowed.")
    return record.env_var


def credential_identity_for_reference(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None = None,
) -> str:
    env_var = credential_env_for_reference(credential_ref_id, purpose=purpose)
    return f"credential-reference:{credential_ref_id}:{env_var}"


def _credential_reference_view(record: CredentialReferenceRecord) -> CredentialReferenceView:
    return CredentialReferenceView(
        id=record.id,
        env_var=record.env_var,
        label=_redact_credential_label(record.label),
        purpose=record.purpose,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        revoked_at=record.revoked_at,
    )


def _record_credential_event(
    message: str,
    record: CredentialReferenceRecord,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.credential,
        message,
        actor=actor or "system",
        subject_id=record.id,
        metadata={
            "env_var": record.env_var,
            "label": _redact_credential_label(record.label),
            "purpose": record.purpose,
            "status": record.status,
        },
    )


def _redact_credential_label(value: str) -> str:
    return redact_sensitive_values(value.strip())
