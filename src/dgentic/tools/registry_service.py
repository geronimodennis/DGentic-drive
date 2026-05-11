"""Service for SQLAlchemy-backed tool registry and duplicate detection."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from dgentic.memory.models import ToolManifest
from dgentic.memory.schemas import (
    DuplicateCheckRequest,
    ToolRegistryCreateRequest,
    ToolUsageRequest,
)


class ToolRegistryService:
    """Service for tool registration and management."""

    def __init__(self, session: Session):
        self.session = session

    def register_tool(self, request: ToolRegistryCreateRequest) -> ToolManifest:
        tool = ToolManifest(
            tool_name=request.tool_name,
            version=request.version,
            source_path=request.source_path,
            interface_signature=request.interface_signature,
            permission_level=request.permission_level,
            tags=request.tags,
            description=request.description,
            created_by_agent=request.created_by_agent,
        )
        self.session.add(tool)
        self.session.commit()
        self.session.refresh(tool)
        self.session.expunge(tool)
        return tool

    def get_tool_by_name(self, tool_name: str) -> ToolManifest | None:
        return self.session.query(ToolManifest).filter(ToolManifest.tool_name == tool_name).first()

    def get_tool_by_id(self, tool_id: UUID | str) -> ToolManifest | None:
        return self.session.query(ToolManifest).filter(ToolManifest.id == str(tool_id)).first()

    def update_tool_registration(
        self,
        tool_id: UUID | str,
        request: ToolRegistryCreateRequest,
    ) -> ToolManifest | None:
        tool = self.get_tool_by_id(tool_id)
        if not tool:
            return None

        tool.version = request.version
        tool.source_path = request.source_path
        tool.interface_signature = request.interface_signature
        tool.permission_level = request.permission_level
        tool.tags = request.tags
        tool.description = request.description
        tool.created_by_agent = request.created_by_agent
        tool.usage_count = 0
        tool.success_count = 0
        tool.failure_count = 0
        tool.last_used_at = None
        tool.reliability_score = 1.0
        tool.deprecated = False
        tool.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(tool)
        self.session.expunge(tool)
        return tool

    def list_tools(
        self,
        tags: list[str] | None = None,
        permission_level: str | None = None,
        deprecated: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ToolManifest], int]:
        query = self.session.query(ToolManifest).filter(ToolManifest.deprecated == deprecated)

        if permission_level:
            query = query.filter(ToolManifest.permission_level == permission_level)

        items = query.order_by(ToolManifest.created_at.desc()).all()
        if tags:
            required_tags = set(tags)
            items = [item for item in items if required_tags.intersection(item.tags or [])]

        total = len(items)
        return items[offset : offset + limit], total

    def check_duplicate(self, request: DuplicateCheckRequest) -> dict:
        existing = self.get_tool_by_name(request.tool_name)
        if existing:
            return {
                "is_duplicate": True,
                "similar_tools": [
                    {
                        "tool_name": existing.tool_name,
                        "version": existing.version,
                        "similarity": 1.0,
                    }
                ],
                "recommendation": (
                    f"Tool '{request.tool_name}' already exists. Use a different name "
                    "or increment the version."
                ),
            }

        similar_tools = (
            self.session.query(ToolManifest)
            .filter(ToolManifest.interface_signature == request.interface_signature)
            .all()
        )
        if similar_tools:
            return {
                "is_duplicate": True,
                "similar_tools": [
                    {
                        "tool_name": tool.tool_name,
                        "version": tool.version,
                        "interface_signature": tool.interface_signature,
                        "similarity": 0.95,
                    }
                    for tool in similar_tools
                ],
                "recommendation": "Similar interface signature found. This may be a duplicate.",
            }

        if request.tags:
            required_tags = set(request.tags)
            tag_similar = [
                tool
                for tool in self.session.query(ToolManifest).all()
                if required_tags.intersection(tool.tags or [])
            ]
            if tag_similar:
                return {
                    "is_duplicate": False,
                    "similar_tools": [
                        {
                            "tool_name": tool.tool_name,
                            "version": tool.version,
                            "overlap_tags": list(set(tool.tags or []) & required_tags),
                            "similarity": 0.6,
                        }
                        for tool in tag_similar[:5]
                    ],
                    "recommendation": (
                        "Similar tools exist with overlapping tags. Review before proceeding."
                    ),
                }

        return {
            "is_duplicate": False,
            "similar_tools": [],
            "recommendation": "Tool is unique. Safe to register.",
        }

    def record_usage(self, tool_id: UUID | str, request: ToolUsageRequest) -> ToolManifest | None:
        tool = self.get_tool_by_id(tool_id)
        if not tool:
            return None

        success = request.status.lower() == "success"
        tool.record_usage(success=success, execution_time_ms=request.execution_time_ms)
        self.session.commit()
        self.session.refresh(tool)
        return tool

    def deprecate_tool(self, tool_id: UUID | str) -> ToolManifest | None:
        tool = self.get_tool_by_id(tool_id)
        if not tool:
            return None

        tool.mark_deprecated()
        self.session.commit()
        self.session.refresh(tool)
        return tool

    def get_most_reliable_tools(self, limit: int = 10) -> list[ToolManifest]:
        return (
            self.session.query(ToolManifest)
            .filter(ToolManifest.deprecated.is_(False))
            .order_by(ToolManifest.reliability_score.desc())
            .limit(limit)
            .all()
        )
