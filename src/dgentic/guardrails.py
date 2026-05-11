import base64
import binascii
import shutil
from datetime import UTC, datetime
from pathlib import Path

from dgentic.command_policy import evaluate_command_policy as evaluate_configured_command_policy
from dgentic.events import event_log
from dgentic.orchestration import authorize_filesystem_action
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandPolicyDecision,
    CommandPolicyRequest,
    FileAccessDecision,
    FileAccessRequest,
    FileBinaryReadRequest,
    FileBinaryReadResponse,
    FileBinaryWriteRequest,
    FileCopyRequest,
    FileCopyResponse,
    FileDeleteRequest,
    FileDeleteResponse,
    FileListEntry,
    FileListRequest,
    FileListResponse,
    FileMetadataRequest,
    FileMetadataResponse,
    FileMoveRequest,
    FileMoveResponse,
    FileReadRequest,
    FileReadResponse,
    FileRenameRequest,
    FileRenameResponse,
    FileWriteRequest,
    FileWriteResponse,
    LogEventType,
    PermissionMode,
)
from dgentic.settings import get_settings

_APPROVAL_REQUIRED_ACTIONS = frozenset({"delete", "move", "copy", "rename"})
_TARGET_ACTIONS = frozenset({"move", "copy", "rename"})


def _root_and_data_dirs() -> tuple[Path, Path]:
    settings = get_settings()
    root_dir = settings.root_dir.resolve()
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = root_dir / data_dir
    return root_dir, data_dir.resolve()


def _candidate_path(path: Path, root_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return root_dir / path


def _resolve_guarded_path(path: Path, root_dir: Path) -> Path:
    return _candidate_path(path, root_dir).resolve()


def _is_inside(path: Path, root_dir: Path) -> bool:
    return path == root_dir or root_dir in path.parents


def _is_protected(path: Path, protected_data_dir: Path) -> bool:
    return path == protected_data_dir or protected_data_dir in path.parents


def _blocked_decision(
    request: FileAccessRequest,
    resolved_path: Path,
    reason: str,
    *,
    resolved_target_path: Path | None = None,
) -> FileAccessDecision:
    return FileAccessDecision(
        path=request.path,
        resolved_path=resolved_path,
        target_path=request.target_path,
        resolved_target_path=resolved_target_path,
        allowed=False,
        permission_mode=PermissionMode.blocked,
        reason=reason,
    )


def evaluate_file_access(
    request: FileAccessRequest, *, actor: str | None = None
) -> FileAccessDecision:
    root_dir, protected_data_dir = _root_and_data_dirs()
    resolved = _resolve_guarded_path(request.path, root_dir)
    target_resolved: Path | None = None

    if not _is_inside(resolved, root_dir):
        decision = _blocked_decision(
            request,
            resolved,
            f"Path resolves outside configured rootDir: {root_dir}",
        )
    elif _is_protected(resolved, protected_data_dir):
        decision = _blocked_decision(
            request,
            resolved,
            "DGentic state files are protected from guarded filesystem access.",
        )
    elif request.action in _TARGET_ACTIONS and request.target_path is None:
        decision = _blocked_decision(
            request,
            resolved,
            f"{request.action} operations require a target_path.",
        )
    else:
        if request.target_path is not None:
            target_resolved = _resolve_guarded_path(request.target_path, root_dir)
            if not _is_inside(target_resolved, root_dir):
                decision = _blocked_decision(
                    request,
                    resolved,
                    f"Target path resolves outside configured rootDir: {root_dir}",
                    resolved_target_path=target_resolved,
                )
            elif _is_protected(target_resolved, protected_data_dir):
                decision = _blocked_decision(
                    request,
                    resolved,
                    "DGentic state files are protected from guarded filesystem access.",
                    resolved_target_path=target_resolved,
                )
            else:
                decision = _allowed_file_decision(request, resolved, target_resolved)
        else:
            decision = _allowed_file_decision(request, resolved, None)

    decision = _apply_orchestration_filesystem_binding(request, decision, root_dir)
    event_log.record(
        LogEventType.filesystem,
        "Evaluated filesystem access policy.",
        actor=actor or "system",
        metadata=decision.model_dump(mode="json"),
    )
    return decision


def _apply_orchestration_filesystem_binding(
    request: FileAccessRequest,
    decision: FileAccessDecision,
    root_dir: Path,
) -> FileAccessDecision:
    if decision.permission_mode == PermissionMode.blocked or not _has_orchestration_context(
        request
    ):
        return decision

    orchestration_decision = authorize_filesystem_action(
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        action=request.action,
        paths=_orchestration_write_paths(request, decision, root_dir),
    )
    if orchestration_decision.allowed:
        return decision.model_copy(update={"orchestration": orchestration_decision})

    return decision.model_copy(
        update={
            "allowed": False,
            "permission_mode": PermissionMode.blocked,
            "reason": orchestration_decision.reason,
            "orchestration": orchestration_decision,
        }
    )


def _has_orchestration_context(request: FileAccessRequest) -> bool:
    return any([request.agent_id, request.agent_role, request.task_id])


def _file_access_request(
    request,
    action: str,
    target_path: Path | None = None,
) -> FileAccessRequest:
    return FileAccessRequest(
        agent_id=getattr(request, "agent_id", None),
        agent_role=getattr(request, "agent_role", None),
        task_id=getattr(request, "task_id", None),
        path=request.path,
        action=action,
        target_path=target_path,
    )


def _orchestration_write_paths(
    request: FileAccessRequest,
    decision: FileAccessDecision,
    root_dir: Path,
) -> list[str]:
    if request.action in {"read", "binary_read", "metadata", "list"}:
        return []
    if request.action == "copy" and decision.resolved_target_path is not None:
        return [_relative_repo_path(decision.resolved_target_path, root_dir)]
    paths = [_relative_repo_path(decision.resolved_path, root_dir)]
    if request.action in {"move", "rename"} and decision.resolved_target_path is not None:
        paths.append(_relative_repo_path(decision.resolved_target_path, root_dir))
    return paths


def _relative_repo_path(path: Path, root_dir: Path) -> str:
    return path.relative_to(root_dir).as_posix()


def _allowed_file_decision(
    request: FileAccessRequest,
    resolved: Path,
    target_resolved: Path | None,
) -> FileAccessDecision:
    if request.action in _APPROVAL_REQUIRED_ACTIONS:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            target_path=request.target_path,
            resolved_target_path=target_resolved,
            allowed=False,
            permission_mode=PermissionMode.approval_required,
            reason=f"{request.action.title()} operations require explicit approval.",
        )
    else:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            target_path=request.target_path,
            resolved_target_path=target_resolved,
            allowed=True,
            permission_mode=PermissionMode.autopilot_safe,
            reason="Path is inside rootDir and action is allowed.",
        )
    return decision


def _require_file_permission(decision: FileAccessDecision, *, approved: bool = False) -> None:
    if decision.permission_mode == PermissionMode.blocked:
        raise PermissionError(decision.reason)
    if decision.permission_mode == PermissionMode.approval_required and not approved:
        raise PermissionError(f"{decision.reason} Approval is required before execution.")


def _ensure_payload_size(size_bytes: int) -> None:
    max_bytes = get_settings().max_filesystem_bytes
    if size_bytes > max_bytes:
        raise ValueError(
            f"Filesystem payload exceeds maximum filesystem payload size of {max_bytes} bytes."
        )


def _ensure_parent(path: Path, *, create_parent_dirs: bool) -> None:
    if create_parent_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.exists():
        raise FileNotFoundError(str(path.parent))


def _file_type(path: Path) -> str:
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    return "other"


def _metadata_response(path: Path, logical_path: Path) -> FileMetadataResponse:
    stat_result = path.stat()
    return FileMetadataResponse(
        path=logical_path,
        type=_file_type(path),
        size_bytes=stat_result.st_size if path.is_file() else None,
        modified_at=datetime.fromtimestamp(stat_result.st_mtime, UTC),
        is_symlink=path.is_symlink(),
    )


def _copy_path(source: Path, target: Path, *, overwrite: bool, recursive: bool) -> int | None:
    if target.exists():
        if not overwrite:
            raise FileExistsError(str(target))
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    if source.is_dir():
        if not recursive:
            raise IsADirectoryError(str(source))
        shutil.copytree(source, target)
        return None

    _ensure_payload_size(source.stat().st_size)
    shutil.copy2(source, target)
    return target.stat().st_size


def read_guarded_text_file(
    request: FileReadRequest, *, actor: str | None = None
) -> FileReadResponse:
    decision = evaluate_file_access(_file_access_request(request, "read"), actor=actor)
    _require_file_permission(decision)
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_file():
        raise IsADirectoryError(str(decision.path))
    _ensure_payload_size(decision.resolved_path.stat().st_size)

    content = decision.resolved_path.read_text(encoding="utf-8")
    response = FileReadResponse(
        path=decision.path,
        content=content,
        bytes_read=len(content.encode("utf-8")),
    )
    event_log.record(
        LogEventType.filesystem,
        "Read guarded text file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_read": response.bytes_read},
    )
    return response


def write_guarded_text_file(
    request: FileWriteRequest, *, actor: str | None = None
) -> FileWriteResponse:
    decision = evaluate_file_access(_file_access_request(request, "write"), actor=actor)
    _require_file_permission(decision)
    content_bytes = request.content.encode("utf-8")
    _ensure_payload_size(len(content_bytes))

    _ensure_parent(decision.resolved_path, create_parent_dirs=request.create_parent_dirs)

    decision.resolved_path.write_text(request.content, encoding="utf-8")
    response = FileWriteResponse(
        path=decision.path,
        bytes_written=len(content_bytes),
    )
    event_log.record(
        LogEventType.filesystem,
        "Wrote guarded text file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_written": response.bytes_written},
    )
    return response


def read_guarded_binary_file(
    request: FileBinaryReadRequest, *, actor: str | None = None
) -> FileBinaryReadResponse:
    decision = evaluate_file_access(_file_access_request(request, "binary_read"), actor=actor)
    _require_file_permission(decision)
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_file():
        raise IsADirectoryError(str(decision.path))
    _ensure_payload_size(decision.resolved_path.stat().st_size)

    content = decision.resolved_path.read_bytes()
    response = FileBinaryReadResponse(
        path=decision.path,
        content_base64=base64.b64encode(content).decode("ascii"),
        bytes_read=len(content),
    )
    event_log.record(
        LogEventType.filesystem,
        "Read guarded binary file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_read": response.bytes_read},
    )
    return response


def write_guarded_binary_file(
    request: FileBinaryWriteRequest, *, actor: str | None = None
) -> FileWriteResponse:
    decision = evaluate_file_access(_file_access_request(request, "binary_write"), actor=actor)
    _require_file_permission(decision)
    try:
        content = base64.b64decode(request.content_base64.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ValueError("content_base64 must be valid base64.") from exc
    _ensure_payload_size(len(content))
    _ensure_parent(decision.resolved_path, create_parent_dirs=request.create_parent_dirs)

    decision.resolved_path.write_bytes(content)
    response = FileWriteResponse(path=decision.path, bytes_written=len(content))
    event_log.record(
        LogEventType.filesystem,
        "Wrote guarded binary file.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "bytes_written": response.bytes_written},
    )
    return response


def delete_guarded_path(
    request: FileDeleteRequest, *, actor: str | None = None
) -> FileDeleteResponse:
    decision = evaluate_file_access(_file_access_request(request, "delete"), actor=actor)
    _require_file_permission(decision, approved=request.approved)
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if decision.resolved_path.is_dir():
        if request.recursive:
            shutil.rmtree(decision.resolved_path)
        else:
            decision.resolved_path.rmdir()
    else:
        decision.resolved_path.unlink()
    response = FileDeleteResponse(path=decision.path, deleted=True)
    event_log.record(
        LogEventType.filesystem,
        "Deleted guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "recursive": request.recursive,
            "approved": request.approved,
        },
    )
    return response


def move_guarded_path(request: FileMoveRequest, *, actor: str | None = None) -> FileMoveResponse:
    decision = evaluate_file_access(
        _file_access_request(request, "move", request.target_path), actor=actor
    )
    _require_file_permission(decision, approved=request.approved)
    if decision.resolved_target_path is None:
        raise PermissionError("Move operation requires a target path.")
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    _ensure_parent(decision.resolved_target_path, create_parent_dirs=True)
    if decision.resolved_target_path.exists():
        if not request.overwrite:
            raise FileExistsError(str(decision.target_path))
        if decision.resolved_target_path.is_dir():
            shutil.rmtree(decision.resolved_target_path)
        else:
            decision.resolved_target_path.unlink()

    shutil.move(str(decision.resolved_path), str(decision.resolved_target_path))
    response = FileMoveResponse(path=decision.path, target_path=request.target_path, moved=True)
    event_log.record(
        LogEventType.filesystem,
        "Moved guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "target_path": str(request.target_path),
            "overwrite": request.overwrite,
            "approved": request.approved,
        },
    )
    return response


def copy_guarded_path(request: FileCopyRequest, *, actor: str | None = None) -> FileCopyResponse:
    decision = evaluate_file_access(
        _file_access_request(request, "copy", request.target_path), actor=actor
    )
    _require_file_permission(decision, approved=request.approved)
    if decision.resolved_target_path is None:
        raise PermissionError("Copy operation requires a target path.")
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    _ensure_parent(decision.resolved_target_path, create_parent_dirs=True)
    bytes_copied = _copy_path(
        decision.resolved_path,
        decision.resolved_target_path,
        overwrite=request.overwrite,
        recursive=request.recursive,
    )
    response = FileCopyResponse(
        path=decision.path,
        target_path=request.target_path,
        copied=True,
        bytes_copied=bytes_copied,
    )
    event_log.record(
        LogEventType.filesystem,
        "Copied guarded filesystem path.",
        actor=actor or "system",
        metadata={
            "path": str(decision.path),
            "target_path": str(request.target_path),
            "overwrite": request.overwrite,
            "recursive": request.recursive,
            "bytes_copied": bytes_copied,
            "approved": request.approved,
        },
    )
    return response


def rename_guarded_path(
    request: FileRenameRequest, *, actor: str | None = None
) -> FileRenameResponse:
    target_logical_path = request.path.parent / request.new_name
    move_request = FileMoveRequest(
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        path=request.path,
        target_path=target_logical_path,
        overwrite=request.overwrite,
        approved=request.approved,
    )
    moved = move_guarded_path(move_request, actor=actor)
    return FileRenameResponse(path=moved.path, target_path=moved.target_path, renamed=moved.moved)


def get_guarded_path_metadata(
    request: FileMetadataRequest, *, actor: str | None = None
) -> FileMetadataResponse:
    decision = evaluate_file_access(_file_access_request(request, "metadata"), actor=actor)
    _require_file_permission(decision)
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    response = _metadata_response(decision.resolved_path, decision.path)
    event_log.record(
        LogEventType.filesystem,
        "Read guarded filesystem metadata.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "type": response.type},
    )
    return response


def list_guarded_directory(
    request: FileListRequest, *, actor: str | None = None
) -> FileListResponse:
    decision = evaluate_file_access(_file_access_request(request, "list"), actor=actor)
    _require_file_permission(decision)
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_dir():
        raise NotADirectoryError(str(decision.path))

    root_dir, protected_data_dir = _root_and_data_dirs()
    entries: list[FileListEntry] = []
    for child in sorted(decision.resolved_path.iterdir(), key=lambda entry: entry.name.lower()):
        child_resolved = child.resolve()
        if not _is_inside(child_resolved, root_dir) or _is_protected(
            child_resolved, protected_data_dir
        ):
            continue
        logical_path = request.path / child.name if request.path != Path(".") else Path(child.name)
        metadata = _metadata_response(child_resolved, logical_path)
        entries.append(FileListEntry(name=child.name, **metadata.model_dump()))

    response = FileListResponse(path=decision.path, entries=entries)
    event_log.record(
        LogEventType.filesystem,
        "Listed guarded filesystem directory.",
        actor=actor or "system",
        metadata={"path": str(decision.path), "entry_count": len(entries)},
    )
    return response


def evaluate_command_policy(
    request: CommandPolicyRequest,
    *,
    actor: str | None = None,
) -> CommandPolicyDecision:
    return evaluate_configured_command_policy(request, actor=actor)


def execute_guarded_command(request: CommandExecutionRequest) -> CommandExecutionResult:
    from dgentic.cli_runtime import cli_runtime_service

    return cli_runtime_service.execute_command(request)
