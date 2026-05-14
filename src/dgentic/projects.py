import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from dgentic.database import reset_database_state
from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType, StepStatus
from dgentic.settings import activate_runtime_root_dir, get_settings, runtime_root_switch_barrier
from dgentic.storage import JsonCollection

ProjectStatus = Literal["available", "archived"]
ProjectActivationCheckStatus = Literal["ok", "warning", "blocked"]

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
    switching_available: bool = True
    reason: str = (
        "Registered project activation is available when no active runs or unexecuted "
        "approval records would cross runtime roots."
    )


class ProjectActivationCheck(BaseModel):
    id: str
    label: str
    status: ProjectActivationCheckStatus
    detail: str


class ProjectActivationResponse(BaseModel):
    project: ProjectRecord
    previous_root_dir: Path
    active_root_dir: Path
    switched: bool = False
    can_activate: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[ProjectActivationCheck] = Field(default_factory=list)


class ProjectActivationBlockedError(RuntimeError):
    def __init__(self, response: ProjectActivationResponse) -> None:
        super().__init__("Project activation is blocked by active runtime state.")
        self.response = response


_projects = JsonCollection("projects", ProjectRecord)
_activation_lock = Lock()


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


def preflight_project_activation(project_id: str) -> ProjectActivationResponse:
    project = get_project(project_id)
    return _activation_response(project, switched=False)


def activate_project(project_id: str, *, actor: str | None = None) -> ProjectActivationResponse:
    with runtime_root_switch_barrier(), _activation_lock:
        project = get_project(project_id)
        response = _activation_response(project, switched=False)
        if not response.can_activate:
            raise ProjectActivationBlockedError(response)

        now = datetime.now(UTC)
        refreshed_root_dir = _validate_project_root(project.root_dir)
        previous_root_dir = _active_root_dir()
        switched = refreshed_root_dir != previous_root_dir

        def mark_opened(current: ProjectRecord) -> ProjectRecord:
            return current.model_copy(
                update={
                    "root_dir": refreshed_root_dir,
                    "markers": _project_markers(refreshed_root_dir),
                    "last_opened_at": now,
                    "updated_at": now,
                }
            )

        saved = _projects.update(project.id, mark_opened)
        if switched:
            activate_runtime_root_dir(refreshed_root_dir)
            reset_database_state()

        active_root_dir = _active_root_dir()
        activation_response = _activation_response(
            saved,
            switched=switched,
            previous_root_dir=previous_root_dir,
            active_root_dir=active_root_dir,
        )
        _record_project_event(
            "Activated project root.",
            saved,
            actor=actor,
            extra_metadata={
                "previous_root_dir": str(previous_root_dir),
                "active_root_dir": str(active_root_dir),
                "switched": switched,
                "warnings": activation_response.warnings,
            },
        )
        return activation_response


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


def _activation_response(
    project: ProjectRecord,
    *,
    switched: bool,
    previous_root_dir: Path | None = None,
    active_root_dir: Path | None = None,
) -> ProjectActivationResponse:
    previous_root = previous_root_dir or _active_root_dir()
    active_root = active_root_dir or previous_root
    target_root = _validate_project_root(project.root_dir)
    warnings: list[str] = []
    checks: list[ProjectActivationCheck] = []
    blockers: list[str] = []
    switch_required = target_root != previous_root

    def add_check(
        check_id: str,
        label: str,
        status: ProjectActivationCheckStatus,
        detail: str,
    ) -> None:
        checks.append(
            ProjectActivationCheck(
                id=check_id,
                label=label,
                status=status,
                detail=detail,
            )
        )
        if status == "blocked":
            blockers.append(detail)
        elif status == "warning":
            warnings.append(detail)

    if project.status != "available":
        add_check(
            "project-status",
            "Project status",
            "blocked",
            f"Project {project.id} is archived and cannot be activated.",
        )
    else:
        add_check("project-status", "Project status", "ok", "Project is available.")

    if switch_required:
        _append_runtime_blocking_checks(add_check)
        _append_state_anchor_warning(add_check)
    else:
        add_check("active-root", "Active root", "ok", "Project root is already active.")

    return ProjectActivationResponse(
        project=project,
        previous_root_dir=previous_root,
        active_root_dir=active_root if switched else previous_root,
        switched=switched,
        can_activate=not blockers,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
    )


def _append_runtime_blocking_checks(add_check) -> None:
    active_cli_run_ids = _active_cli_run_ids()
    if active_cli_run_ids:
        add_check(
            "active-cli-runs",
            "CLI runs",
            "blocked",
            "Active CLI runs must finish or be cancelled before switching project roots: "
            + ", ".join(active_cli_run_ids[:5]),
        )
    else:
        add_check("active-cli-runs", "CLI runs", "ok", "No active CLI runs.")

    active_execution_ids = _active_orchestration_execution_ids()
    if active_execution_ids:
        add_check(
            "active-orchestration-executions",
            "Orchestration executions",
            "blocked",
            "Active orchestration executions must finish or be cancelled before switching "
            "project roots: " + ", ".join(active_execution_ids[:5]),
        )
    else:
        add_check(
            "active-orchestration-executions",
            "Orchestration executions",
            "ok",
            "No active orchestration executions.",
        )

    active_task_ids = _active_orchestration_task_ids()
    if active_task_ids:
        add_check(
            "active-orchestration-tasks",
            "Orchestration tasks",
            "blocked",
            "Running orchestration tasks must finish or be blocked before switching "
            "project roots: " + ", ".join(active_task_ids[:5]),
        )
    else:
        add_check(
            "active-orchestration-tasks",
            "Orchestration tasks",
            "ok",
            "No running orchestration tasks.",
        )

    approval_counts = _unexecuted_approval_counts()
    if approval_counts:
        summary = ", ".join(
            f"{surface}: {count}" for surface, count in sorted(approval_counts.items())
        )
        add_check(
            "unexecuted-approvals",
            "Unexecuted approvals",
            "blocked",
            "Pending or approved approval records must be resolved before switching "
            f"project roots ({summary}).",
        )
    else:
        add_check(
            "unexecuted-approvals",
            "Unexecuted approvals",
            "ok",
            "No pending or approved approval records.",
        )


def _append_state_anchor_warning(add_check) -> None:
    settings = get_settings()
    if settings.data_dir.is_absolute():
        add_check(
            "state-anchor",
            "DGentic state",
            "ok",
            "DGentic state already uses an absolute dataDir and will stay anchored.",
        )
        return

    data_dir = (settings.root_dir.resolve() / settings.data_dir).resolve()
    add_check(
        "state-anchor",
        "DGentic state",
        "warning",
        "Relative DGentic dataDir will be pinned to its current absolute location during "
        f"this process: {data_dir}",
    )


def _active_cli_run_ids() -> list[str]:
    from dgentic.cli_runtime import CommandRunStatus, cli_runtime_service

    active_statuses = {CommandRunStatus.starting, CommandRunStatus.running}
    return [
        run.id for run in cli_runtime_service.list_command_runs() if run.status in active_statuses
    ]


def _active_orchestration_execution_ids() -> list[str]:
    from dgentic.orchestration import orchestration_service

    return orchestration_service.get_operations_summary().active_execution_ids


def _active_orchestration_task_ids() -> list[str]:
    from dgentic.orchestration import orchestration_service

    return [
        task.id
        for run in orchestration_service.list_runs()
        for task in run.tasks
        if task.status == StepStatus.running
    ]


def _unexecuted_approval_counts() -> dict[str, int]:
    counts: dict[str, int] = {}

    from dgentic.cli_runtime import CommandApprovalStatus, cli_runtime_service
    from dgentic.guardrails import FileApprovalStatus, list_file_approvals
    from dgentic.network_policy import NetworkApprovalStatus, list_network_approvals
    from dgentic.provider_runtime import ProviderApprovalStatus, list_provider_approvals
    from dgentic.tool_runtime import ToolApprovalStatus, list_tool_approvals

    cli_count = len(cli_runtime_service.list_approvals(CommandApprovalStatus.pending)) + len(
        cli_runtime_service.list_approvals(CommandApprovalStatus.approved)
    )
    file_count = len(list_file_approvals(FileApprovalStatus.pending)) + len(
        list_file_approvals(FileApprovalStatus.approved)
    )
    network_count = len(list_network_approvals(NetworkApprovalStatus.pending)) + len(
        list_network_approvals(NetworkApprovalStatus.approved)
    )
    provider_count = len(list_provider_approvals(ProviderApprovalStatus.pending)) + len(
        list_provider_approvals(ProviderApprovalStatus.approved)
    )
    tool_count = len(list_tool_approvals(ToolApprovalStatus.pending)) + len(
        list_tool_approvals(ToolApprovalStatus.approved)
    )

    for surface, count in {
        "cli": cli_count,
        "filesystem": file_count,
        "network": network_count,
        "provider": provider_count,
        "tool": tool_count,
    }.items():
        if count:
            counts[surface] = count
    return counts


def _record_project_event(
    message: str,
    project: ProjectRecord,
    *,
    actor: str | None,
    extra_metadata: dict[str, object] | None = None,
) -> None:
    metadata = {
        "project_id": project.id,
        "name": project.name,
        "root_dir": str(project.root_dir),
        "status": project.status,
        "markers": project.markers,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    event_log.record(
        LogEventType.project,
        message,
        actor=actor or "system",
        subject_id=project.id,
        metadata=metadata,
    )
