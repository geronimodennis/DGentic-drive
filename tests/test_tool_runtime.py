from pathlib import Path

import pytest

from dgentic.database import get_db_session, reset_database_state
from dgentic.memory.schemas import ToolRegistryCreateRequest
from dgentic.schemas import PermissionMode, ToolManifest, ToolStatus
from dgentic.settings import get_settings
from dgentic.tool_runtime import execute_tool
from dgentic.tools import get_tool, register_tool
from dgentic.tools.registry_service import ToolRegistryService


@pytest.fixture()
def local_tool_state(tmp_path, monkeypatch) -> tuple[Path, Path]:
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    (root_dir / "localmcp").mkdir(parents=True)
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    reset_database_state()
    yield root_dir, data_dir
    reset_database_state()
    get_settings.cache_clear()


def test_execute_tool_prefers_wrapper_and_tracks_success(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "adder",
        tool_source=(
            "def run(payload):\n"
            "    return {'total': payload['a'] + payload['b'], 'source': 'tool'}\n"
        ),
        wrapper_source=(
            "from tool import run\n\n"
            "def invoke(payload):\n"
            "    print('wrapper-log')\n"
            "    result = run(payload)\n"
            "    result['source'] = 'wrapper'\n"
            "    return result\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="adder",
            description="Add two numbers.",
            entrypoint="localmcp/adder/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("adder", {"a": 2, "b": 3})
    stored = get_tool("adder")

    assert result.exit_code == 0
    assert result.cwd == tool_dir.resolve()
    assert result.entrypoint == (tool_dir / "wrapper.py").resolve()
    assert result.parsed_output == {"total": 5, "source": "wrapper"}
    assert "wrapper-log" in result.stderr
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.success_count == 1
    assert stored.failure_count == 0
    assert stored.reliability_score == 1.0
    assert stored.last_used_at is not None
    assert (data_dir / "tools.json").exists()


def test_approval_required_tool_must_be_approved(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(root_dir, "reviewer", tool_source="def run(payload):\n    return {'ok': True}\n")
    register_tool(
        ToolManifest(
            name="reviewer",
            description="Requires a human approval gate.",
            entrypoint="tool.py",
            permission_mode=PermissionMode.approval_required,
        )
    )

    with pytest.raises(PermissionError, match="requires explicit approval"):
        execute_tool("reviewer", {"approved": False})

    denied_manifest = get_tool("reviewer")
    result = execute_tool("reviewer", {"approved": True}, approved=True)
    approved_manifest = get_tool("reviewer")

    assert denied_manifest is not None
    assert denied_manifest.usage_count == 0
    assert result.exit_code == 0
    assert approved_manifest is not None
    assert approved_manifest.usage_count == 1
    assert approved_manifest.success_count == 1


@pytest.mark.parametrize(
    ("permission_mode", "status"),
    [
        (PermissionMode.blocked, ToolStatus.active),
        (PermissionMode.autopilot_safe, ToolStatus.disabled),
        (PermissionMode.autopilot_safe, ToolStatus.deprecated),
    ],
)
def test_blocked_disabled_and_deprecated_tools_do_not_run(
    local_tool_state: tuple[Path, Path],
    permission_mode: PermissionMode,
    status: ToolStatus,
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        f"guarded-{status.value}-{permission_mode.value}",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    name = tool_dir.name
    register_tool(
        ToolManifest(
            name=name,
            description="Should not execute.",
            entrypoint=f"localmcp/{name}/tool.py",
            permission_mode=permission_mode,
            status=status,
            deprecated_reason="Replaced." if status == ToolStatus.deprecated else None,
        )
    )

    with pytest.raises(PermissionError):
        execute_tool(name, {})

    stored = get_tool(name)
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def test_failed_tool_execution_tracks_failure_and_captured_output(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(
        root_dir,
        "broken",
        tool_source=(
            "def run(payload):\n    print('about-to-fail')\n    raise RuntimeError('boom')\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="broken",
            description="Raises an error.",
            entrypoint="localmcp/broken/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    result = execute_tool("broken", {"value": 1})
    stored = get_tool("broken")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.parsed_output is None
    assert "about-to-fail" in result.stderr
    assert "RuntimeError: boom" in result.stderr
    assert stored is not None
    assert stored.usage_count == 1
    assert stored.success_count == 0
    assert stored.failure_count == 1
    assert stored.reliability_score == 0.0


def test_manifest_entrypoint_must_stay_under_named_localmcp_tool_dir(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    _write_tool(root_dir, "safe-name", tool_source="def run(payload):\n    return {'ok': True}\n")
    register_tool(
        ToolManifest(
            name="safe-name",
            description="Has an unsafe manifest entrypoint.",
            entrypoint="localmcp/other-tool/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )

    with pytest.raises(PermissionError, match=r"rootDir/localmcp/\[tool_name\]"):
        execute_tool("safe-name", {})

    stored = get_tool("safe-name")
    assert stored is not None
    assert stored.usage_count == 0


def test_sql_registry_deprecated_tool_does_not_run(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "sql-deprecated",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="sql-deprecated",
            description="Local manifest is active, but SQL registry is deprecated.",
            entrypoint="localmcp/sql-deprecated/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _register_sql_registry_tool(
        "sql-deprecated",
        permission_level="autopilot_safe",
        deprecated=True,
    )

    with pytest.raises(PermissionError):
        execute_tool("sql-deprecated", {})

    stored = get_tool("sql-deprecated")
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def test_sql_registry_permission_conflict_fails_closed(
    local_tool_state: tuple[Path, Path],
) -> None:
    root_dir, _data_dir = local_tool_state
    tool_dir = _write_tool(
        root_dir,
        "sql-permission-conflict",
        tool_source=(
            "from pathlib import Path\n\n"
            "def run(payload):\n"
            "    Path('ran.txt').write_text('ran', encoding='utf-8')\n"
            "    return {'ok': True}\n"
        ),
    )
    register_tool(
        ToolManifest(
            name="sql-permission-conflict",
            description="SQL registry permission conflicts with local manifest.",
            entrypoint="localmcp/sql-permission-conflict/tool.py",
            permission_mode=PermissionMode.autopilot_safe,
        )
    )
    _register_sql_registry_tool(
        "sql-permission-conflict",
        permission_level="approval_required",
    )

    with pytest.raises(PermissionError):
        execute_tool("sql-permission-conflict", {})

    stored = get_tool("sql-permission-conflict")
    assert stored is not None
    assert stored.usage_count == 0
    assert not (tool_dir / "ran.txt").exists()


def _register_sql_registry_tool(
    name: str,
    *,
    permission_level: str,
    deprecated: bool = False,
) -> None:
    session = get_db_session()
    try:
        service = ToolRegistryService(session)
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name=name,
                version="1.0.0",
                source_path=f"localmcp/{name}/tool.py",
                interface_signature=f"sha256:{name}",
                permission_level=permission_level,
            )
        )
        if deprecated:
            service.deprecate_tool(tool.id)
    finally:
        session.close()


def _write_tool(
    root_dir: Path,
    name: str,
    *,
    tool_source: str,
    wrapper_source: str | None = None,
) -> Path:
    tool_dir = root_dir / "localmcp" / name
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(tool_source, encoding="utf-8")
    if wrapper_source is not None:
        (tool_dir / "wrapper.py").write_text(wrapper_source, encoding="utf-8")
    return tool_dir
