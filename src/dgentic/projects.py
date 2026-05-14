import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

ProjectStatus = Literal["available", "archived"]

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_PROJECT_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "README.md",
    "docs",
    "src",
    "tests",
)


class ProjectRequest(BaseModel):
    id: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    root_dir: Path

    @field_validator("id")
    @classmethod
    def id_must_be_stable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not _PROJECT_ID_RE.fullmatch(normalized):
            raise ValueError("Project id must use safe identifier text.")
        if redact_sensitive_values(normalized) != normalized:
            raise ValueError("Project id must not contain secret-shaped text.")
        return normalized

    @field_validator("name")
    @classmethod
    def name_must_be_redacted(cls, value: str) -> str:
        name = redact_sensitive_values(value.strip())
        if not name:
            raise ValueError("Project name must not be blank.")
        return name


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: ProjectStatus | None = None

    @field_validator("name")
    @classmethod
    def name_must_be_redacted(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = redact_sensitive_values(value.strip())
        if not name:
            raise ValueError("Project name must not be blank.")
        return name


class ProjectPreflightRequest(BaseModel):
    root_dir: Path
    name: str | None = Field(default=None, max_length=120)

    @field_validator("name")
    @classmethod
    def name_must_be_redacted(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = redact_sensitive_values(value.strip())
        return name or None


class ProjectPreflightResponse(BaseModel):
    root_dir: Path
    name: str
    valid: bool = True
    markers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProjectRecord(BaseModel):
    id: str
    name: str
    root_dir: Path
    status: ProjectStatus = "available"
    markers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_opened_at: datetime | None = None


class ActiveProjectResponse(BaseModel):
    active_root_dir: Path
    project: ProjectRecord | None = None
    switching_available: bool = False
    reason: str = (
        "Project root switching is not enabled yet; registered projects are preflighted "
        "metadata only."
    )


_projects = JsonCollection("projects", ProjectRecord)


def preflight_project_root(request: ProjectPreflightRequest) -> ProjectPreflightResponse:
    root_dir = _validate_project_root(request.root_dir)
    name = request.name or _default_project_name(root_dir)
    warnings = [
        "Registering a project does not change the active runtime root.",
    ]
    if root_dir == _active_root_dir():
        warnings.append("This root matches the active runtime root.")
    return ProjectPreflightResponse(
        root_dir=root_dir,
        name=name,
        markers=_project_markers(root_dir),
        warnings=warnings,
    )


def create_project(request: ProjectRequest, *, actor: str | None = None) -> ProjectRecord:
    preflight = preflight_project_root(
        ProjectPreflightRequest(root_dir=request.root_dir, name=request.name)
    )
    project_id = request.id or _project_id(preflight.name, preflight.root_dir)
    now = datetime.now(UTC)
    record = ProjectRecord(
        id=project_id,
        name=preflight.name,
        root_dir=preflight.root_dir,
        markers=preflight.markers,
        created_at=now,
        updated_at=now,
        last_opened_at=now if preflight.root_dir == _active_root_dir() else None,
    )

    def insert(items: list[ProjectRecord]) -> tuple[list[ProjectRecord], ProjectRecord]:
        for item in items:
            if item.id == record.id:
                raise ValueError(f"Project id already exists: {record.id}")
            if item.root_dir.resolve() == record.root_dir:
                raise ValueError(f"Project root is already registered: {record.root_dir}")
        return [*items, record], record

    saved = _projects.transact(insert)
    _record_project_event("Registered project root.", saved, actor=actor)
    return saved


def list_projects() -> list[ProjectRecord]:
    return sorted(_projects.list(), key=lambda project: (project.name.lower(), project.id))


def get_project(project_id: str) -> ProjectRecord:
    project = _projects.get(project_id)
    if project is None:
        raise KeyError(f"Project not found: {project_id}")
    return project


def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    *,
    actor: str | None = None,
) -> ProjectRecord:
    now = datetime.now(UTC)

    def update(current: ProjectRecord) -> ProjectRecord:
        updates: dict[str, object] = {"updated_at": now}
        if request.name is not None:
            updates["name"] = request.name
        if request.status is not None:
            updates["status"] = request.status
        return current.model_copy(update=updates)

    saved = _projects.update(project_id, update)
    _record_project_event("Updated project root metadata.", saved, actor=actor)
    return saved


def get_active_project() -> ActiveProjectResponse:
    active_root = _active_root_dir()
    matching_project = next(
        (
            project
            for project in list_projects()
            if project.status == "available" and project.root_dir.resolve() == active_root
        ),
        None,
    )
    return ActiveProjectResponse(active_root_dir=active_root, project=matching_project)


def _validate_project_root(path: Path) -> Path:
    raw_path = str(path)
    if "\x00" in raw_path:
        raise ValueError("Project root path contains an invalid character.")
    if not path.is_absolute():
        raise ValueError("Project root must be an absolute path.")
    if path.is_symlink():
        raise ValueError("Project root must not be a symlink.")
    try:
        root_dir = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Project root must exist.") from exc
    if not root_dir.is_dir():
        raise ValueError("Project root must be a directory.")
    if _inside_active_data_dir(root_dir):
        raise ValueError("Project root must not be inside DGentic state data.")
    return root_dir


def _inside_active_data_dir(path: Path) -> bool:
    settings = get_settings()
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = settings.root_dir / data_dir
    try:
        resolved_data_dir = data_dir.resolve()
    except OSError:
        resolved_data_dir = data_dir.resolve(strict=False)
    return path == resolved_data_dir or resolved_data_dir in path.parents


def _active_root_dir() -> Path:
    return get_settings().root_dir.resolve()


def _default_project_name(root_dir: Path) -> str:
    return redact_sensitive_values(root_dir.name.strip() or str(root_dir))


def _project_markers(root_dir: Path) -> list[str]:
    return [marker for marker in _PROJECT_MARKERS if (root_dir / marker).exists()]


def _project_id(name: str, root_dir: Path) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", name.strip()).strip("-._:")
    slug = slug[:72] or "project"
    digest = sha256(str(root_dir).encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def _record_project_event(message: str, project: ProjectRecord, *, actor: str | None) -> None:
    event_log.record(
        LogEventType.project,
        message,
        actor=actor or "system",
        subject_id=project.id,
        metadata={
            "project_id": project.id,
            "name": project.name,
            "root_dir": str(project.root_dir),
            "status": project.status,
            "markers": project.markers,
        },
    )
