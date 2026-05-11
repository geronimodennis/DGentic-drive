"""Tests for tool registry service (Story 7.1)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.models import Base, ToolManifest
from dgentic.memory.schemas import (
    DuplicateCheckRequest,
    ToolRegistryCreateRequest,
    ToolUsageRequest,
)
from dgentic.tools.registry_service import ToolRegistryService


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestToolRegistry:
    """Tests for tool registration."""

    def test_register_tool(self, db_session: Session):
        """Test registering a new tool."""
        service = ToolRegistryService(db_session)
        request = ToolRegistryCreateRequest(
            tool_name="my-tool",
            version="1.0.0",
            source_path="localmcp/my-tool",
            interface_signature="sha256:abc123",
            permission_level="approval_required",
            tags=["automation"],
            description="Test tool",
            created_by_agent="Dev1",
        )

        tool = service.register_tool(request)

        assert tool.id is not None
        assert tool.tool_name == "my-tool"
        assert tool.version == "1.0.0"
        assert tool.reliability_score == 1.0
        assert tool.deprecated is False

    def test_get_tool_by_name(self, db_session: Session):
        """Test retrieving tool by name."""
        service = ToolRegistryService(db_session)
        request = ToolRegistryCreateRequest(
            tool_name="my-tool",
            version="1.0.0",
            source_path="localmcp/my-tool",
            interface_signature="sha256:abc123",
        )
        service.register_tool(request)

        retrieved = service.get_tool_by_name("my-tool")

        assert retrieved is not None
        assert retrieved.tool_name == "my-tool"

    def test_list_tools_by_permission(self, db_session: Session):
        """Test listing tools filtered by permission level."""
        service = ToolRegistryService(db_session)

        service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="safe-tool",
                version="1.0.0",
                source_path="localmcp/safe-tool",
                interface_signature="sig1",
                permission_level="autopilot_safe",
            )
        )
        service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="unsafe-tool",
                version="1.0.0",
                source_path="localmcp/unsafe-tool",
                interface_signature="sig2",
                permission_level="approval_required",
            )
        )

        safe_tools, total = service.list_tools(permission_level="autopilot_safe")

        assert len(safe_tools) == 1
        assert safe_tools[0].tool_name == "safe-tool"

    def test_record_tool_success(self, db_session: Session):
        """Test recording successful tool usage."""
        service = ToolRegistryService(db_session)
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="test-tool",
                version="1.0.0",
                source_path="localmcp/test-tool",
                interface_signature="sig",
            )
        )

        result = service.record_usage(
            tool.id,
            ToolUsageRequest(status="success", execution_time_ms=100),
        )

        assert result.usage_count == 1
        assert result.success_count == 1
        assert result.reliability_score == 1.0

    def test_record_tool_failure(self, db_session: Session):
        """Test recording failed tool usage."""
        service = ToolRegistryService(db_session)
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="test-tool",
                version="1.0.0",
                source_path="localmcp/test-tool",
                interface_signature="sig",
            )
        )

        # Record one failure
        service.record_usage(
            tool.id,
            ToolUsageRequest(status="failure", error="Test error"),
        )
        # Record one success
        service.record_usage(
            tool.id,
            ToolUsageRequest(status="success"),
        )

        updated = service.get_tool_by_id(tool.id)

        assert updated.usage_count == 2
        assert updated.success_count == 1
        assert updated.failure_count == 1
        assert abs(updated.reliability_score - 0.5) < 0.01

    def test_update_tool_registration_resets_version_runtime_state(self, db_session: Session):
        """Test updating a generated tool registry row for a new version."""
        service = ToolRegistryService(db_session)
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="versioned-tool",
                version="1.0.0",
                source_path="localmcp/versioned-tool/tool.py",
                interface_signature="sha256:v1",
                permission_level="autopilot_safe",
                tags=["old"],
                description="Old version.",
            )
        )
        service.record_usage(tool.id, ToolUsageRequest(status="failure"))
        service.deprecate_tool(tool.id)

        updated = service.update_tool_registration(
            tool.id,
            ToolRegistryCreateRequest(
                tool_name="versioned-tool",
                version="2.0.0",
                source_path="localmcp/versioned-tool/tool.py",
                interface_signature="sha256:v2",
                permission_level="approval_required",
                tags=["new"],
                description="New version.",
                created_by_agent="main_agent",
            ),
        )

        assert updated is not None
        assert updated.id == tool.id
        assert updated.version == "2.0.0"
        assert updated.interface_signature == "sha256:v2"
        assert updated.permission_level == "approval_required"
        assert updated.tags == ["new"]
        assert updated.description == "New version."
        assert updated.created_by_agent == "main_agent"
        assert updated.usage_count == 0
        assert updated.success_count == 0
        assert updated.failure_count == 0
        assert updated.last_used_at is None
        assert updated.reliability_score == 1.0
        assert updated.deprecated is False


class TestDuplicateDetection:
    """Tests for tool duplicate detection."""

    def test_detect_exact_name_duplicate(self, db_session: Session):
        """Test detecting duplicate by exact name match."""
        service = ToolRegistryService(db_session)
        service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="my-tool",
                version="1.0.0",
                source_path="localmcp/my-tool",
                interface_signature="sig1",
            )
        )

        result = service.check_duplicate(
            DuplicateCheckRequest(
                tool_name="my-tool",
                interface_signature="sig1",
            )
        )

        assert result["is_duplicate"] is True
        assert len(result["similar_tools"]) > 0

    def test_detect_signature_duplicate(self, db_session: Session):
        """Test detecting duplicate by interface signature."""
        service = ToolRegistryService(db_session)
        service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="tool-1",
                version="1.0.0",
                source_path="localmcp/tool-1",
                interface_signature="sha256:same-sig",
            )
        )

        result = service.check_duplicate(
            DuplicateCheckRequest(
                tool_name="tool-2",
                interface_signature="sha256:same-sig",
            )
        )

        assert result["is_duplicate"] is True

    def test_unique_tool_detection(self, db_session: Session):
        """Test that unique tools pass detection."""
        service = ToolRegistryService(db_session)

        result = service.check_duplicate(
            DuplicateCheckRequest(
                tool_name="unique-tool",
                interface_signature="sha256:unique-sig",
            )
        )

        assert result["is_duplicate"] is False
        assert len(result["similar_tools"]) == 0
        assert "Safe to register" in result["recommendation"]

    def test_deprecate_tool(self, db_session: Session):
        """Test marking tool as deprecated."""
        service = ToolRegistryService(db_session)
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="test-tool",
                version="1.0.0",
                source_path="localmcp/test-tool",
                interface_signature="sig",
            )
        )

        deprecated = service.deprecate_tool(tool.id)

        assert deprecated.deprecated is True
        assert deprecated.updated_at > tool.created_at

    def test_list_exclude_deprecated(self, db_session: Session):
        """Test that deprecated tools are excluded from listing."""
        service = ToolRegistryService(db_session)

        service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="active-tool",
                version="1.0.0",
                source_path="localmcp/active",
                interface_signature="sig1",
            )
        )
        tool2 = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="old-tool",
                version="1.0.0",
                source_path="localmcp/old",
                interface_signature="sig2",
            )
        )

        service.deprecate_tool(tool2.id)

        active_tools, _ = service.list_tools(deprecated=False)

        assert len(active_tools) == 1
        assert active_tools[0].tool_name == "active-tool"


class TestPathValidation:
    """Tests for tool registry path validation (security boundary enforcement)."""

    def test_valid_localmcp_path(self, db_session: Session):
        """Test that valid localmcp paths are accepted."""
        service = ToolRegistryService(db_session)

        # Valid paths should work
        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="test-tool",
                version="1.0.0",
                source_path="localmcp/my-tool",  # Valid
                interface_signature="sig",
            )
        )

        assert tool.source_path == "localmcp/my-tool"

    def test_valid_nested_localmcp_path(self, db_session: Session):
        """Test nested paths under localmcp are valid."""
        service = ToolRegistryService(db_session)

        tool = service.register_tool(
            ToolRegistryCreateRequest(
                tool_name="nested-tool",
                version="1.0.0",
                source_path="localmcp/category/my-tool",  # Nested under localmcp
                interface_signature="sig",
            )
        )

        assert tool.source_path == "localmcp/category/my-tool"

    def test_path_traversal_rejection(self, db_session: Session):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(ValueError, match="cannot contain '..'"):
            ToolManifest(
                tool_name="bad-tool",
                version="1.0.0",
                source_path="localmcp/../escape",  # Path traversal attempt
                interface_signature="sig",
            )

    def test_absolute_path_rejection(self, db_session: Session):
        """Test that absolute paths are rejected."""
        with pytest.raises(ValueError, match="must start with 'localmcp/'"):
            ToolManifest(
                tool_name="bad-tool",
                version="1.0.0",
                source_path="/absolute/path",  # Absolute path rejected
                interface_signature="sig",
            )

    def test_missing_localmcp_prefix_rejection(self, db_session: Session):
        """Test paths without localmcp prefix are rejected."""
        with pytest.raises(ValueError, match="must start with 'localmcp/'"):
            ToolManifest(
                tool_name="bad-tool",
                version="1.0.0",
                source_path="tools/my-tool",  # Missing localmcp prefix
                interface_signature="sig",
            )

    def test_null_byte_rejection(self, db_session: Session):
        """Test null bytes in path are rejected."""
        with pytest.raises(ValueError, match="cannot contain null bytes"):
            ToolManifest(
                tool_name="bad-tool",
                version="1.0.0",
                source_path="localmcp/tool\x00escape",  # Null byte injection
                interface_signature="sig",
            )

    def test_empty_path_rejection(self, db_session: Session):
        """Test empty path is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ToolManifest(
                tool_name="bad-tool",
                version="1.0.0",
                source_path="",  # Empty path
                interface_signature="sig",
            )

    def test_windows_path_traversal_rejection(self, db_session: Session):
        """Test Windows-style path traversal is rejected."""
        with pytest.raises(ValueError, match="cannot contain '..'"):
            ToolManifest(
                tool_name="bad-tool",
                version="1.0.0",
                source_path="localmcp\\..\\escape",  # Windows path traversal
                interface_signature="sig",
            )

    def test_path_validation_on_update(self, db_session: Session):
        """Test path validation is enforced on model updates."""
        tool = ToolManifest(
            tool_name="test-tool",
            version="1.0.0",
            source_path="localmcp/valid-path",
            interface_signature="sig",
        )
        db_session.add(tool)
        db_session.commit()

        # Try to update with invalid path
        with pytest.raises(ValueError, match="must start with 'localmcp/'"):
            tool.source_path = "invalid/path"
            db_session.commit()
