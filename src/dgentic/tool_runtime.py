import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from dgentic.database import get_db_session
from dgentic.events import event_log
from dgentic.memory.models import ToolManifest as RegistryToolManifest
from dgentic.redaction import redact_metadata, redact_sensitive_values
from dgentic.schemas import LogEventType, PermissionMode, ToolManifest, ToolStatus
from dgentic.settings import get_settings
from dgentic.tools import get_tool, save_tool_manifest

DEFAULT_TOOL_TIMEOUT_SECONDS = 30
TIMEOUT_EXIT_CODE = -1
ENTRYPOINT_FILENAMES = ("wrapper.py", "tool.py")
SUBPROCESS_ENV_KEYS = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "CONDA_PREFIX",
        "CURL_CA_BUNDLE",
        "DYLD_LIBRARY_PATH",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LD_LIBRARY_PATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PYTHONHOME",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USERPROFILE",
        "VIRTUAL_ENV",
        "WINDIR",
    }
)

_RUNNER_SOURCE = r"""
import contextlib
import importlib.util
import json
import sys
import traceback
from pathlib import Path


def _main():
    entrypoint = Path(sys.argv[1])
    sys.path.insert(0, str(entrypoint.parent))

    payload = json.load(sys.stdin)
    spec = importlib.util.spec_from_file_location("_dgentic_tool_entrypoint", entrypoint)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load tool entrypoint: {entrypoint}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    handler = getattr(module, "invoke", None) or getattr(module, "run", None)
    if handler is None:
        raise AttributeError("Tool entrypoint must define invoke(payload) or run(payload).")

    with contextlib.redirect_stdout(sys.stderr):
        output = handler(payload)

    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


try:
    _main()
except BaseException:
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""


class ToolExecutionResult(BaseModel):
    tool_name: str
    entrypoint: Path
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    parsed_output: Any | None = None
    manifest: ToolManifest = Field(
        description="The manifest after reliability counters were updated."
    )


def execute_tool(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    approved: bool = False,
    timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS,
) -> ToolExecutionResult:
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1.")

    manifest = get_tool(name)
    if manifest is None:
        raise LookupError(f"Tool not found: {name}")

    _ensure_registry_allows_manifest(manifest)
    _ensure_tool_can_run(manifest, approved=approved)
    root_dir = get_settings().root_dir.resolve()
    tool_dir = _tool_dir_for(manifest.name, root_dir)
    _validate_manifest_entrypoint(manifest, root_dir, tool_dir)
    entrypoint = _resolve_entrypoint(tool_dir)

    started_at = perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _RUNNER_SOURCE, str(entrypoint)],
            cwd=tool_dir,
            input=json.dumps(payload or {}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=_subprocess_env(tool_dir),
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = TIMEOUT_EXIT_CODE
        stdout = _coerce_timeout_output(exc.stdout)
        stderr = _coerce_timeout_output(exc.stderr)
        timeout_message = f"Tool timed out after {timeout_seconds} seconds."
        stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message

    duration_ms = round((perf_counter() - started_at) * 1000)
    parsed_output = _parse_json_output(stdout)
    redacted_output = redact_metadata(parsed_output) if parsed_output is not None else None
    stdout = _redact_stdout(stdout, redacted_output)
    stderr = redact_sensitive_values(stderr)
    updated_manifest = _record_run(manifest, succeeded=exit_code == 0)
    _record_execution_event(
        updated_manifest,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
    )

    return ToolExecutionResult(
        tool_name=manifest.name,
        entrypoint=entrypoint,
        cwd=tool_dir,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        parsed_output=redacted_output,
        manifest=updated_manifest,
    )


def _ensure_tool_can_run(manifest: ToolManifest, *, approved: bool) -> None:
    if manifest.permission_mode == PermissionMode.blocked:
        raise PermissionError(f"Tool is blocked and cannot run: {manifest.name}")
    if manifest.status == ToolStatus.disabled:
        raise PermissionError(f"Tool is disabled and cannot run: {manifest.name}")
    if manifest.status == ToolStatus.deprecated:
        reason = f": {manifest.deprecated_reason}" if manifest.deprecated_reason else "."
        raise PermissionError(f"Tool is deprecated and cannot run{reason}")
    if manifest.permission_mode == PermissionMode.approval_required and not approved:
        raise PermissionError("Tool requires explicit approval before execution.")


def _ensure_registry_allows_manifest(manifest: ToolManifest) -> None:
    session = get_db_session()
    try:
        registry_tool = (
            session.query(RegistryToolManifest)
            .filter(RegistryToolManifest.tool_name == manifest.name)
            .first()
        )
        if registry_tool is None:
            return

        if registry_tool.deprecated:
            raise PermissionError(
                f"Tool registry row is deprecated and cannot run: {manifest.name}"
            )

        try:
            registry_permission = PermissionMode(registry_tool.permission_level)
        except ValueError as exc:
            raise PermissionError(
                f"Tool registry permission_level is invalid and cannot run: {manifest.name}"
            ) from exc

        if registry_permission != manifest.permission_mode:
            raise PermissionError(
                "Tool registry permission_level conflicts with JSON manifest "
                f"permission_mode for tool: {manifest.name}"
            )
    finally:
        session.close()


def _tool_dir_for(name: str, root_dir: Path) -> Path:
    if not name or "/" in name or "\\" in name:
        raise PermissionError("Tool execution must stay inside rootDir/localmcp/[tool_name].")

    localmcp_dir = (root_dir / "localmcp").resolve()
    tool_dir = (localmcp_dir / name).resolve()
    if tool_dir.parent != localmcp_dir:
        raise PermissionError("Tool execution must stay inside rootDir/localmcp/[tool_name].")
    return tool_dir


def _validate_manifest_entrypoint(manifest: ToolManifest, root_dir: Path, tool_dir: Path) -> None:
    if not manifest.entrypoint:
        return

    entrypoint = Path(manifest.entrypoint)
    if not entrypoint.is_absolute():
        base_dir = tool_dir if entrypoint.parent == Path(".") else root_dir
        entrypoint = base_dir / entrypoint
    resolved = entrypoint.resolve()
    if resolved.parent != tool_dir:
        raise PermissionError("Tool entrypoint must stay inside rootDir/localmcp/[tool_name].")


def _resolve_entrypoint(tool_dir: Path) -> Path:
    for filename in ENTRYPOINT_FILENAMES:
        candidate = (tool_dir / filename).resolve()
        if candidate.parent != tool_dir:
            raise PermissionError("Tool entrypoint must stay inside rootDir/localmcp/[tool_name].")
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Tool entrypoint not found: expected wrapper.py or tool.py in {tool_dir}"
    )


def _subprocess_env(tool_dir: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in SUBPROCESS_ENV_KEYS}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(tool_dir)
    return env


def _parse_json_output(stdout: str) -> Any | None:
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _redact_stdout(stdout: str, parsed_output: Any | None) -> str:
    if parsed_output is not None:
        suffix = "\n" if stdout.endswith("\n") else ""
        return json.dumps(parsed_output, ensure_ascii=False) + suffix
    return redact_sensitive_values(stdout)


def _record_run(manifest: ToolManifest, *, succeeded: bool) -> ToolManifest:
    usage_count = manifest.usage_count + 1
    success_count = manifest.success_count + (1 if succeeded else 0)
    failure_count = manifest.failure_count + (0 if succeeded else 1)
    reliability_score = success_count / usage_count if usage_count else 1.0

    updated = manifest.model_copy(
        update={
            "usage_count": usage_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "last_used_at": datetime.now(UTC),
            "reliability_score": reliability_score,
        }
    )
    return save_tool_manifest(updated)


def _record_execution_event(
    manifest: ToolManifest,
    *,
    exit_code: int,
    duration_ms: int,
    stdout: str,
    stderr: str,
) -> None:
    event_log.record(
        LogEventType.tool,
        "Executed generated tool.",
        subject_id=manifest.name,
        metadata={
            "tool_name": manifest.name,
            "permission_mode": manifest.permission_mode,
            "status": manifest.status,
            "exit_code": exit_code,
            "succeeded": exit_code == 0,
            "duration_ms": duration_ms,
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        },
    )


def _coerce_timeout_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


__all__ = [
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "TIMEOUT_EXIT_CODE",
    "ToolExecutionResult",
    "execute_tool",
]
