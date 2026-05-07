"""Pydantic schemas for metadata and tool registry services."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataCreateRequest(BaseModel):
    """Request to create a metadata entry."""

    entity_type: str = Field(description="Type: skill, memory, tool, or pattern")
    entity_id: str = Field(description="Reference ID of the entity")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    category: str | None = Field(default=None, description="Category classification")
    description: str | None = Field(default=None, description="Human-readable description")
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Relevance 0-1")
    retention_policy: str = Field(
        default="automatic", description="permanent, automatic, or manual"
    )
    owner_agent: str | None = Field(default=None, description="Agent that owns this")


class MetadataResponse(BaseModel):
    """Response with metadata entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: str
    tags: list[str]
    category: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None
    access_count: int
    relevance_score: float
    indexed: bool


class MetadataListResponse(BaseModel):
    """Response with a list of metadata entries."""

    items: list[MetadataResponse]
    total: int
    page: int


class HybridRetrievalRequest(BaseModel):
    """Request for hybrid vector plus metadata search."""

    query: str = Field(description="Natural language query")
    entity_types: list[str] | None = Field(default=None, description="Filter by entity types")
    tags: list[str] | None = Field(default=None, description="Filter by tags")
    limit: int = Field(default=10, ge=1, le=100, description="Max results")
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Min similarity")
    metadata_filters: dict | None = Field(default=None, description="Additional metadata filters")


class RetrievalResult(BaseModel):
    """Single result from hybrid retrieval."""

    metadata_id: UUID
    entity_type: str
    entity_id: str
    description: str | None
    similarity_score: float
    metadata_relevance: float
    combined_score: float
    source: str


class HybridRetrievalResponse(BaseModel):
    """Response from hybrid retrieval."""

    results: list[RetrievalResult]
    total: int
    query_time_ms: float


class ToolRegistryCreateRequest(BaseModel):
    """Request to register a tool in the SQLAlchemy registry."""

    tool_name: str = Field(description="Unique tool name")
    version: str = Field(description="Semantic version")
    source_path: str = Field(description="Path under localmcp/")
    interface_signature: str = Field(description="Hash or signature of the interface")
    permission_level: str = Field(
        default="approval_required", description="autopilot_safe or approval_required"
    )
    tags: list[str] = Field(default_factory=list, description="Classification tags")
    description: str | None = Field(default=None, description="Tool description")
    created_by_agent: str | None = Field(default=None, description="Creating agent")


class ToolManifestResponse(BaseModel):
    """Response with a tool registry manifest."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tool_name: str
    version: str
    source_path: str
    permission_level: str
    tags: list[str]
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by_agent: str | None
    usage_count: int
    success_count: int
    failure_count: int
    last_used_at: datetime | None
    reliability_score: float
    deprecated: bool


class ToolManifestListResponse(BaseModel):
    """Response with a list of tool registry manifests."""

    items: list[ToolManifestResponse]
    total: int
    page: int


class DuplicateCheckRequest(BaseModel):
    """Request to check for duplicate tools."""

    tool_name: str = Field(description="Tool name to check")
    interface_signature: str = Field(description="Interface signature hash")
    tags: list[str] | None = Field(default=None, description="Tool tags")


class DuplicateCheckResponse(BaseModel):
    """Response from duplicate detection."""

    is_duplicate: bool
    similar_tools: list[dict] = Field(default_factory=list, description="Similar existing tools")
    recommendation: str


class ToolUsageRequest(BaseModel):
    """Request to record tool usage."""

    status: str = Field(description="success or failure")
    execution_time_ms: int = Field(default=0, ge=0, description="Execution time in milliseconds")
    error: str | None = Field(default=None, description="Error message if failed")
