import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dgentic.cli_runtime import resolve_command_cwd
from dgentic.events import event_log
from dgentic.guardrails import evaluate_command_policy
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandPolicyDecision,
    CommandPolicyRequest,
    LogEventType,
)
from dgentic.storage import JsonCollection

_RECIPE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_PARAMETER_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\\-]{0,255}$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_MAX_COMMAND_TEMPLATE_CHARS = 1000


class CommandRecipeParameter(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=300)
    required: bool = True
    default: str | None = Field(default=None, max_length=256)

    @field_validator("name")
    @classmethod
    def name_must_be_identifier(cls, value: str) -> str:
        name = value.strip()
        if not _PARAMETER_NAME_RE.fullmatch(name):
            raise ValueError("Recipe parameter names must be identifiers.")
        return name

    @field_validator("description")
    @classmethod
    def description_must_be_redacted(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())

    @field_validator("default")
    @classmethod
    def default_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _safe_parameter_value(value)


class CommandRecipeRequest(BaseModel):
    id: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    command_template: str = Field(min_length=1, max_length=_MAX_COMMAND_TEMPLATE_CHARS)
    cwd: Path | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    parameters: list[CommandRecipeParameter] = Field(default_factory=list, max_length=25)
    tags: list[str] = Field(default_factory=list, max_length=25)
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def id_must_be_stable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_recipe_id(value)

    @field_validator("name", "command_template")
    @classmethod
    def required_text_must_be_safe(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Recipe text fields must not be blank.")
        redacted = redact_sensitive_values(stripped)
        if redacted != stripped:
            raise ValueError("Command recipes must not contain secret-shaped text.")
        return stripped

    @field_validator("description")
    @classmethod
    def description_must_be_safe(cls, value: str) -> str:
        stripped = value.strip()
        redacted = redact_sensitive_values(stripped)
        if redacted != stripped:
            raise ValueError("Command recipes must not contain secret-shaped text.")
        return stripped

    @field_validator("tags")
    @classmethod
    def tags_must_be_safe(cls, value: list[str]) -> list[str]:
        tags: list[str] = []
        for item in value:
            tag = item.strip()
            if not tag:
                continue
            if not _RECIPE_ID_RE.fullmatch(tag):
                raise ValueError("Recipe tags must use safe identifier text.")
            if tag not in tags:
                tags.append(tag)
        return sorted(tags)

    @model_validator(mode="after")
    def placeholders_must_match_parameters(self) -> "CommandRecipeRequest":
        _validate_template_parameters(self.command_template, self.parameters)
        return self


class CommandRecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    command_template: str | None = Field(default=None, min_length=1, max_length=1000)
    cwd: Path | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    parameters: list[CommandRecipeParameter] | None = Field(default=None, max_length=25)
    tags: list[str] | None = Field(default=None, max_length=25)
    enabled: bool | None = None

    @field_validator("name", "command_template")
    @classmethod
    def optional_required_text_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Recipe text fields must not be blank.")
        redacted = redact_sensitive_values(stripped)
        if redacted != stripped:
            raise ValueError("Command recipes must not contain secret-shaped text.")
        return stripped

    @field_validator("description")
    @classmethod
    def optional_description_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        redacted = redact_sensitive_values(stripped)
        if redacted != stripped:
            raise ValueError("Command recipes must not contain secret-shaped text.")
        return stripped

    @field_validator("tags")
    @classmethod
    def optional_tags_must_be_safe(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return CommandRecipeRequest(
            name="tag validation",
            command_template="cmd /c echo tag-validation",
            tags=value,
        ).tags


class CommandRecipe(BaseModel):
    id: str
    name: str
    description: str = ""
    command_template: str
    cwd: Path | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    parameters: list[CommandRecipeParameter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    usage_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def recipe_must_still_be_valid(self) -> "CommandRecipe":
        _normalize_recipe_id(self.id)
        _validate_template_parameters(self.command_template, self.parameters)
        return self


class CommandRecipeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameters: dict[str, str] = Field(default_factory=dict, max_length=25)
    approval_id: str | None = None
    requested_by: str | None = Field(default=None, max_length=256)
    agent_id: str | None = Field(default=None, max_length=256)
    agent_role: str | None = Field(default=None, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("parameters")
    @classmethod
    def parameter_values_must_be_safe(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            key = raw_key.strip()
            if not _PARAMETER_NAME_RE.fullmatch(key):
                raise ValueError("Recipe parameter names must be identifiers.")
            normalized[key] = _safe_parameter_value(str(raw_value))
        return normalized


class CommandRecipeExpansion(BaseModel):
    recipe_id: str
    command: str
    cwd: Path
    timeout_seconds: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    parameter_names: list[str] = Field(default_factory=list)
    policy: CommandPolicyDecision


_command_recipes = JsonCollection("command-recipes", CommandRecipe)


def create_command_recipe(
    request: CommandRecipeRequest,
    *,
    actor: str | None = None,
) -> CommandRecipe:
    now = datetime.now(UTC)
    recipe = CommandRecipe(
        id=request.id or f"command-recipe-{uuid4()}",
        name=redact_sensitive_values(request.name),
        description=redact_sensitive_values(request.description),
        command_template=request.command_template,
        cwd=request.cwd,
        timeout_seconds=request.timeout_seconds,
        parameters=request.parameters,
        tags=request.tags,
        enabled=request.enabled,
        created_at=now,
        updated_at=now,
    )

    def create(items: list[CommandRecipe]) -> tuple[list[CommandRecipe], CommandRecipe]:
        if any(item.id == recipe.id for item in items):
            raise ValueError(f"Command recipe already exists: {recipe.id}")
        return [*items, recipe], recipe

    saved = _command_recipes.transact(create)
    _record_recipe_event("Created command recipe.", saved, actor=actor)
    return saved


def list_command_recipes() -> list[CommandRecipe]:
    return sorted(_command_recipes.list(), key=lambda item: item.id)


def get_command_recipe(recipe_id: str) -> CommandRecipe:
    recipe = _command_recipes.get(_normalize_recipe_id(recipe_id))
    if recipe is None:
        raise KeyError(f"Command recipe not found: {recipe_id}")
    return recipe


def update_command_recipe(
    recipe_id: str,
    update: CommandRecipeUpdate,
    *,
    actor: str | None = None,
) -> CommandRecipe:
    now = datetime.now(UTC)

    def apply_update(recipe: CommandRecipe) -> CommandRecipe:
        payload = recipe.model_dump()
        for field_name in update.model_fields_set:
            payload[field_name] = getattr(update, field_name)
        payload["updated_at"] = now
        candidate = CommandRecipe.model_validate(payload)
        _validate_template_parameters(candidate.command_template, candidate.parameters)
        return candidate

    try:
        saved = _command_recipes.update(_normalize_recipe_id(recipe_id), apply_update)
    except KeyError as exc:
        raise KeyError(f"Command recipe not found: {recipe_id}") from exc
    _record_recipe_event("Updated command recipe.", saved, actor=actor)
    return saved


def build_command_recipe_request(
    recipe_id: str,
    request: CommandRecipeExecutionRequest,
) -> CommandExecutionRequest:
    recipe = get_command_recipe(recipe_id)
    if not recipe.enabled:
        raise PermissionError(f"Command recipe is disabled: {recipe.id}")

    command = _render_command_template(recipe, request.parameters)
    return CommandExecutionRequest(
        command=command,
        cwd=recipe.cwd,
        timeout_seconds=recipe.timeout_seconds,
        approved=False,
        approval_id=request.approval_id,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )


def expand_command_recipe(
    recipe_id: str,
    request: CommandRecipeExecutionRequest,
    *,
    actor: str | None = None,
) -> CommandRecipeExpansion:
    recipe = get_command_recipe(recipe_id)
    command_request = build_command_recipe_request(recipe.id, request)
    cwd = resolve_command_cwd(command_request.cwd)
    policy = evaluate_command_policy(
        CommandPolicyRequest(
            command=command_request.command,
            cwd=cwd,
            agent_role=command_request.agent_role,
            agent_id=command_request.agent_id,
            task_id=command_request.task_id,
        ),
        actor=actor or command_request.requested_by,
    )
    return CommandRecipeExpansion(
        recipe_id=recipe.id,
        command=redact_sensitive_values(command_request.command),
        cwd=cwd,
        timeout_seconds=command_request.timeout_seconds,
        requested_by=command_request.requested_by,
        agent_id=command_request.agent_id,
        agent_role=command_request.agent_role,
        task_id=command_request.task_id,
        parameter_names=sorted(request.parameters),
        policy=policy,
    )


def record_command_recipe_usage(
    recipe_id: str,
    *,
    action: str,
    actor: str | None = None,
) -> CommandRecipe:
    now = datetime.now(UTC)

    def update_usage(recipe: CommandRecipe) -> CommandRecipe:
        return recipe.model_copy(update={"usage_count": recipe.usage_count + 1, "updated_at": now})

    saved = _command_recipes.update(_normalize_recipe_id(recipe_id), update_usage)
    _record_recipe_event(
        "Used command recipe.",
        saved,
        actor=actor,
        extra_metadata={"action": action},
    )
    return saved


def _render_command_template(recipe: CommandRecipe, parameters: dict[str, str]) -> str:
    declared = {parameter.name: parameter for parameter in recipe.parameters}
    unknown = sorted(set(parameters) - set(declared))
    if unknown:
        raise ValueError(f"Unknown command recipe parameters: {', '.join(unknown)}")

    values: dict[str, str] = {}
    for name, parameter in declared.items():
        if name in parameters:
            values[name] = _safe_parameter_value(parameters[name])
            continue
        if parameter.default is not None:
            values[name] = _safe_parameter_value(parameter.default)
            continue
        if parameter.required:
            raise ValueError(f"Missing required command recipe parameter: {name}")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return values.get(name, "")

    return _PLACEHOLDER_RE.sub(replace, recipe.command_template)


def _validate_template_parameters(
    command_template: str,
    parameters: list[CommandRecipeParameter],
) -> None:
    declared: set[str] = set()
    for parameter in parameters:
        if parameter.name in declared:
            raise ValueError(f"Duplicate command recipe parameter: {parameter.name}")
        declared.add(parameter.name)

    placeholders = set(_PLACEHOLDER_RE.findall(command_template))
    undeclared = sorted(placeholders - declared)
    unused = sorted(declared - placeholders)
    if undeclared:
        raise ValueError(f"Command recipe placeholders are undeclared: {', '.join(undeclared)}")
    if unused:
        raise ValueError(f"Command recipe parameters are unused: {', '.join(unused)}")


def _safe_parameter_value(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Recipe parameter values must not be blank.")
    if redact_sensitive_values(candidate) != candidate:
        raise ValueError("Recipe parameter values must not contain secret-shaped text.")
    if candidate == ".":
        return candidate
    if not _PARAMETER_VALUE_RE.fullmatch(candidate):
        raise ValueError(
            "Recipe parameter values may only contain letters, numbers, dot, dash, "
            "underscore, colon, slash, or backslash."
        )
    return candidate


def _normalize_recipe_id(value: str) -> str:
    recipe_id = value.strip()
    if not _RECIPE_ID_RE.fullmatch(recipe_id):
        raise ValueError("Command recipe id must use safe identifier text.")
    return recipe_id


def _record_recipe_event(
    message: str,
    recipe: CommandRecipe,
    *,
    actor: str | None,
    extra_metadata: dict[str, object] | None = None,
) -> None:
    metadata: dict[str, object] = {
        "recipe_id": recipe.id,
        "name": redact_sensitive_values(recipe.name),
        "enabled": recipe.enabled,
        "parameter_names": sorted(parameter.name for parameter in recipe.parameters),
        "tags": recipe.tags,
        "usage_count": recipe.usage_count,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    event_log.record(
        LogEventType.cli,
        message,
        actor=actor or "system",
        subject_id=recipe.id,
        metadata=metadata,
    )
