import json
import os
import re
import subprocess
import threading
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field, field_validator, model_validator

from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType
from dgentic.settings import Settings, get_settings
from dgentic.storage import JsonCollection

CREDENTIAL_ENV_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
CREDENTIAL_ADAPTER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
CREDENTIAL_SECRET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.:/@-]{1,200}$")
CREDENTIAL_LOCAL_VAULT_SECRET_MAX_BYTES = 64 * 1024
CredentialSourceType = Literal["env", "external_process", "local_vault"]


class CredentialReferenceError(RuntimeError):
    """Base error for credential-reference configuration or resolution failures."""


class CredentialConfigurationError(CredentialReferenceError):
    """Raised when a credential reference or resolver adapter is not configured."""


class CredentialResolutionError(CredentialReferenceError):
    """Raised when a configured credential resolver cannot return a usable secret."""


class CredentialProcessAdapter(BaseModel):
    argv: list[str] = Field(min_length=1, max_length=20)


class CredentialReferenceRequest(BaseModel):
    source_type: CredentialSourceType = "env"
    env_var: str = Field(default="", max_length=128)
    adapter_id: str = Field(default="", max_length=80)
    secret_name: str = Field(default="", max_length=200)
    secret_value: str = Field(default="", repr=False, exclude=True)
    label: str = Field(default="", max_length=120)
    purpose: Literal["provider", "runtime"] = "provider"

    @field_validator("env_var")
    @classmethod
    def env_var_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not CREDENTIAL_ENV_PATTERN.fullmatch(normalized):
            raise ValueError("env_var must be a valid environment variable name.")
        return normalized

    @field_validator("adapter_id")
    @classmethod
    def adapter_id_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not CREDENTIAL_ADAPTER_ID_PATTERN.fullmatch(normalized):
            raise ValueError("adapter_id contains unsupported characters.")
        return normalized

    @field_validator("secret_name")
    @classmethod
    def secret_name_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not CREDENTIAL_SECRET_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("secret_name contains unsupported characters.")
        return normalized

    @field_validator("label")
    @classmethod
    def label_must_be_trimmed(cls, value: str) -> str:
        return _redact_credential_label(value)

    @model_validator(mode="after")
    def source_fields_must_match_source_type(self) -> "CredentialReferenceRequest":
        _validate_source_fields(
            source_type=self.source_type,
            env_var=self.env_var,
            adapter_id=self.adapter_id,
            secret_name=self.secret_name,
        )
        return self


class CredentialReferenceRecord(BaseModel):
    id: str
    source_type: CredentialSourceType = "env"
    env_var: str = ""
    adapter_id: str = ""
    secret_name: str = ""
    encrypted_secret: str = ""
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
        if normalized and not CREDENTIAL_ENV_PATTERN.fullmatch(normalized):
            raise ValueError("env_var must be a valid environment variable name.")
        return normalized

    @field_validator("adapter_id")
    @classmethod
    def adapter_id_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not CREDENTIAL_ADAPTER_ID_PATTERN.fullmatch(normalized):
            raise ValueError("adapter_id contains unsupported characters.")
        return normalized

    @field_validator("secret_name")
    @classmethod
    def secret_name_must_be_safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not CREDENTIAL_SECRET_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("secret_name contains unsupported characters.")
        return normalized

    @field_validator("label")
    @classmethod
    def label_must_be_trimmed(cls, value: str) -> str:
        return _redact_credential_label(value)

    @model_validator(mode="after")
    def source_fields_must_match_source_type(self) -> "CredentialReferenceRecord":
        _validate_source_fields(
            source_type=self.source_type,
            env_var=self.env_var,
            adapter_id=self.adapter_id,
            secret_name=self.secret_name,
        )
        if self.source_type == "local_vault":
            if not self.encrypted_secret:
                raise ValueError("encrypted_secret is required for local_vault credentials.")
        elif self.encrypted_secret:
            raise ValueError("Invalid credential source fields.")
        return self

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
    source_type: CredentialSourceType
    env_var: str = ""
    adapter_id: str = ""
    secret_name: str = ""
    label: str = ""
    purpose: Literal["provider", "runtime"]
    status: Literal["active", "revoked"]
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


class CredentialVaultRotationRequest(BaseModel):
    current_vault_key: str = Field(min_length=1, max_length=512, repr=False, exclude=True)
    new_vault_key: str = Field(min_length=1, max_length=512, repr=False, exclude=True)

    @field_validator("current_vault_key", "new_vault_key")
    @classmethod
    def keys_must_be_trimmed(cls, value: str) -> str:
        return value.strip()


class CredentialVaultRotationResponse(BaseModel):
    rotated_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    rotated_at: datetime


_credential_references = JsonCollection("credential-references", CredentialReferenceRecord)


def create_credential_reference(
    request: CredentialReferenceRequest,
    *,
    actor: str | None = None,
) -> CredentialReferenceView:
    now = datetime.now(UTC)
    encrypted_secret = ""
    if request.source_type == "local_vault":
        encrypted_secret = _encrypt_local_vault_secret(request.secret_value)
    elif request.secret_value:
        raise ValueError("Invalid credential source fields.")
    record = CredentialReferenceRecord(
        id=f"credential-ref-{uuid4()}",
        source_type=request.source_type,
        env_var=request.env_var,
        adapter_id=request.adapter_id,
        secret_name=request.secret_name,
        encrypted_secret=encrypted_secret,
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


def rotate_local_vault_credential_references(
    request: CredentialVaultRotationRequest,
    *,
    actor: str | None = None,
) -> CredentialVaultRotationResponse:
    if request.current_vault_key == request.new_vault_key:
        raise ValueError("Credential vault rotation failed.")
    current_fernet = _fernet_for_raw_key(request.current_vault_key)
    new_fernet = _fernet_for_raw_key(request.new_vault_key)
    now = datetime.now(UTC)

    def rotate(
        items: list[CredentialReferenceRecord],
    ) -> tuple[list[CredentialReferenceRecord], CredentialVaultRotationResponse]:
        rotated_count = 0
        skipped_count = 0
        updated_items: list[CredentialReferenceRecord] = []
        for record in items:
            if record.source_type != "local_vault":
                skipped_count += 1
                updated_items.append(record)
                continue
            try:
                decrypted_secret = current_fernet.decrypt(record.encrypted_secret.encode("ascii"))
            except (InvalidToken, UnicodeEncodeError, ValueError) as exc:
                raise CredentialResolutionError("Credential vault rotation failed.") from exc
            _validate_local_vault_secret_bytes(decrypted_secret)
            encrypted_secret = new_fernet.encrypt(decrypted_secret).decode("ascii")
            updated_items.append(
                record.model_copy(
                    update={
                        "encrypted_secret": encrypted_secret,
                        "updated_at": now,
                    }
                )
            )
            rotated_count += 1
        return (
            updated_items,
            CredentialVaultRotationResponse(
                rotated_count=rotated_count,
                skipped_count=skipped_count,
                rotated_at=now,
            ),
        )

    response = _credential_references.transact(rotate)
    _record_credential_vault_rotation_event(response, actor=actor)
    return response


def credential_env_for_reference(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None = None,
) -> str:
    record = _credential_reference_for_use(credential_ref_id, purpose=purpose)
    if record.source_type != "env":
        raise PermissionError("Credential reference is not environment-backed.")
    return record.env_var


def credential_secret_for_reference(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None = None,
    environ: Any | None = None,
    settings: Settings | None = None,
) -> str:
    record = _credential_reference_for_use(credential_ref_id, purpose=purpose)
    if record.source_type == "env":
        credential_environ = os.environ if environ is None else environ
        credential_value = credential_environ.get(record.env_var, "")
        if not isinstance(credential_value, str) or not credential_value.strip():
            raise CredentialResolutionError("Credential value is not available.")
        return credential_value.strip()
    if record.source_type == "external_process":
        return _external_process_secret(record, settings=settings or get_settings())
    if record.source_type == "local_vault":
        return _local_vault_secret(record, settings=settings or get_settings())
    raise CredentialConfigurationError("Credential reference source is not supported.")


def credential_identity_for_reference(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None = None,
    settings: Settings | None = None,
) -> str:
    record = _credential_reference_for_use(credential_ref_id, purpose=purpose)
    if record.source_type == "env":
        return f"credential-reference:{credential_ref_id}:{record.env_var}"
    if record.source_type == "external_process":
        adapter_digest = _process_adapter_digest(
            record.adapter_id,
            settings=settings or get_settings(),
        )
        secret_name_digest = sha256(record.secret_name.encode("utf-8")).hexdigest()[:16]
        return (
            f"credential-reference:{credential_ref_id}:external_process:"
            f"{record.adapter_id}:{secret_name_digest}:{adapter_digest}"
        )
    if record.source_type == "local_vault":
        _credential_vault_fernet(settings or get_settings())
        encrypted_secret_digest = sha256(record.encrypted_secret.encode("utf-8")).hexdigest()[:16]
        return f"credential-reference:{credential_ref_id}:local_vault:{encrypted_secret_digest}"
    raise CredentialConfigurationError("Credential reference source is not supported.")


def credential_reference_is_configured(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None = None,
    settings: Settings | None = None,
) -> bool:
    try:
        credential_identity_for_reference(
            credential_ref_id,
            purpose=purpose,
            settings=settings or get_settings(),
        )
    except (KeyError, PermissionError, CredentialReferenceError, ValueError):
        return False
    return True


def _credential_reference_view(record: CredentialReferenceRecord) -> CredentialReferenceView:
    return CredentialReferenceView(
        id=record.id,
        source_type=record.source_type,
        env_var=record.env_var,
        adapter_id=record.adapter_id,
        secret_name=_redact_credential_label(record.secret_name),
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
            "source_type": record.source_type,
            "env_var": record.env_var,
            "adapter_id": record.adapter_id,
            "secret_name": _redact_credential_label(record.secret_name),
            "encrypted_secret_present": bool(record.encrypted_secret),
            "label": _redact_credential_label(record.label),
            "purpose": record.purpose,
            "status": record.status,
        },
    )


def _record_credential_vault_rotation_event(
    response: CredentialVaultRotationResponse,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.credential,
        "Rotated credential vault key.",
        actor=actor or "system",
        metadata={
            "rotated_count": response.rotated_count,
            "skipped_count": response.skipped_count,
            "rotated_at": response.rotated_at.isoformat(),
        },
    )


def _redact_credential_label(value: str) -> str:
    return redact_sensitive_values(value.strip())


def _credential_reference_for_use(
    credential_ref_id: str,
    *,
    purpose: Literal["provider", "runtime"] | None,
) -> CredentialReferenceRecord:
    record = _credential_references.get(credential_ref_id)
    if record is None:
        raise KeyError(f"Credential reference not found: {credential_ref_id}")
    if record.status != "active":
        raise PermissionError("Credential reference is not active.")
    if purpose is not None and record.purpose != purpose:
        raise PermissionError("Credential reference purpose is not allowed.")
    return record


def _validate_source_fields(
    *,
    source_type: CredentialSourceType,
    env_var: str,
    adapter_id: str,
    secret_name: str,
) -> None:
    if source_type == "env":
        if not env_var:
            raise ValueError("env_var is required for env credential references.")
        if adapter_id or secret_name:
            raise ValueError("Invalid credential source fields.")
        return
    if source_type == "external_process":
        if env_var:
            raise ValueError("env_var is only valid for env credential references.")
        if not adapter_id or not secret_name:
            raise ValueError("Invalid credential source fields.")
        return
    if source_type == "local_vault":
        if env_var or adapter_id or secret_name:
            raise ValueError("Invalid credential source fields.")
        return
    raise ValueError("Credential reference source_type is not supported.")


def _encrypt_local_vault_secret(secret_value: str, *, settings: Settings | None = None) -> str:
    secret = secret_value.strip()
    if not secret or "\x00" in secret:
        raise ValueError("Credential secret is invalid.")
    if len(secret.encode("utf-8")) > CREDENTIAL_LOCAL_VAULT_SECRET_MAX_BYTES:
        raise ValueError("Credential secret is invalid.")
    return (
        _credential_vault_fernet(settings or get_settings())
        .encrypt(secret.encode("utf-8"))
        .decode("ascii")
    )


def _local_vault_secret(record: CredentialReferenceRecord, *, settings: Settings) -> str:
    try:
        decrypted = _credential_vault_fernet(settings).decrypt(
            record.encrypted_secret.encode("ascii")
        )
    except (InvalidToken, UnicodeEncodeError, ValueError) as exc:
        raise CredentialResolutionError("Credential vault secret is not available.") from exc
    try:
        secret = decrypted.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialResolutionError("Credential vault secret is not available.") from exc
    if not secret or "\x00" in secret:
        raise CredentialResolutionError("Credential vault secret is not available.")
    return secret


def _credential_vault_fernet(settings: Settings) -> Fernet:
    return _fernet_for_raw_key(settings.credential_vault_key)


def _fernet_for_raw_key(raw_key: str) -> Fernet:
    raw_key = raw_key.strip()
    if not raw_key:
        raise CredentialConfigurationError("Credential vault key is not configured.")
    try:
        return Fernet(raw_key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise CredentialConfigurationError("Credential vault key is not configured.") from exc


def _validate_local_vault_secret_bytes(secret_bytes: bytes) -> None:
    if len(secret_bytes) > CREDENTIAL_LOCAL_VAULT_SECRET_MAX_BYTES:
        raise CredentialResolutionError("Credential vault secret is not available.")
    try:
        secret = secret_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialResolutionError("Credential vault secret is not available.") from exc
    if not secret or "\x00" in secret:
        raise CredentialResolutionError("Credential vault secret is not available.")


def _credential_process_adapters(settings: Settings) -> dict[str, CredentialProcessAdapter]:
    raw_config = settings.credential_process_adapters.strip()
    if not raw_config:
        return {}
    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise CredentialConfigurationError(
            "Credential process adapters are not configured."
        ) from exc
    if not isinstance(parsed, dict):
        raise CredentialConfigurationError("Credential process adapters are not configured.")

    adapters: dict[str, CredentialProcessAdapter] = {}
    for adapter_id, adapter_config in parsed.items():
        if not isinstance(adapter_id, str) or not CREDENTIAL_ADAPTER_ID_PATTERN.fullmatch(
            adapter_id
        ):
            raise CredentialConfigurationError("Credential process adapters are not configured.")
        if isinstance(adapter_config, list):
            adapter_payload = {"argv": adapter_config}
        elif isinstance(adapter_config, dict):
            adapter_payload = {
                "argv": adapter_config.get("argv", adapter_config.get("command")),
            }
        else:
            raise CredentialConfigurationError("Credential process adapters are not configured.")
        try:
            adapter = CredentialProcessAdapter.model_validate(adapter_payload)
        except ValueError as exc:
            raise CredentialConfigurationError(
                "Credential process adapters are not configured."
            ) from exc
        if not Path(adapter.argv[0]).is_absolute():
            raise CredentialConfigurationError("Credential process adapters are not configured.")
        if any(not isinstance(arg, str) or not arg.strip() for arg in adapter.argv):
            raise CredentialConfigurationError("Credential process adapters are not configured.")
        adapters[adapter_id] = adapter
    return adapters


def _process_adapter_for_record(
    record: CredentialReferenceRecord,
    *,
    settings: Settings,
) -> CredentialProcessAdapter:
    adapter = _credential_process_adapters(settings).get(record.adapter_id)
    if adapter is None:
        raise CredentialConfigurationError("Credential process adapter is not configured.")
    return adapter


def _process_adapter_digest(adapter_id: str, *, settings: Settings) -> str:
    adapter = _credential_process_adapters(settings).get(adapter_id)
    if adapter is None:
        raise CredentialConfigurationError("Credential process adapter is not configured.")
    payload = json.dumps(adapter.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _external_process_secret(record: CredentialReferenceRecord, *, settings: Settings) -> str:
    adapter = _process_adapter_for_record(record, settings=settings)
    argv = [*adapter.argv, record.secret_name]
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_minimal_process_env(),
            stdin=subprocess.DEVNULL,
            shell=False,
        )
    except OSError as exc:
        raise CredentialResolutionError("Credential process adapter failed.") from exc

    try:
        stdout_text, stderr = _communicate_with_bounded_output(
            process,
            timeout_seconds=settings.credential_process_timeout_seconds,
            max_output_bytes=settings.credential_process_max_output_bytes,
        )
    except CredentialResolutionError:
        _terminate_process(process)
        raise
    except subprocess.TimeoutExpired as exc:
        _terminate_process(process)
        raise CredentialResolutionError("Credential process adapter failed.") from exc

    if process.returncode != 0 or stderr.strip():
        raise CredentialResolutionError("Credential process adapter failed.")
    secret = stdout_text.strip()
    if not secret or "\n" in secret or "\r" in secret or "\x00" in secret:
        raise CredentialResolutionError("Credential process adapter output is invalid.")
    return secret


def _minimal_process_env() -> dict[str, str]:
    if os.name != "nt":
        return {}
    return {
        key: value
        for key in ("SystemRoot", "SYSTEMROOT", "WINDIR", "PATHEXT")
        if (value := os.environ.get(key))
    }


def _communicate_with_bounded_output(
    process: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
    max_output_bytes: int,
) -> tuple[str, bytes]:
    if process.stdout is None or process.stderr is None:
        raise CredentialResolutionError("Credential process adapter failed.")

    stdout = bytearray()
    stderr = bytearray()
    output_exceeded = threading.Event()

    def read_stream(stream, buffer: bytearray) -> None:
        try:
            while True:
                chunk = stream.read(1024)
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > max_output_bytes:
                    output_exceeded.set()
                    _kill_process(process)
                    break
        finally:
            stream.close()

    stdout_reader = threading.Thread(target=read_stream, args=(process.stdout, stdout), daemon=True)
    stderr_reader = threading.Thread(target=read_stream, args=(process.stderr, stderr), daemon=True)
    stdout_reader.start()
    stderr_reader.start()

    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_process(process)
        stdout_reader.join(timeout=1.0)
        stderr_reader.join(timeout=1.0)
        raise

    stdout_reader.join(timeout=1.0)
    stderr_reader.join(timeout=1.0)

    if output_exceeded.is_set() or len(stdout) > max_output_bytes or len(stderr) > max_output_bytes:
        raise CredentialResolutionError("Credential process adapter output is invalid.")
    try:
        stdout_text = bytes(stdout).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialResolutionError("Credential process adapter output is invalid.") from exc
    return stdout_text, bytes(stderr)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    _kill_process(process)
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        return


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.kill()
