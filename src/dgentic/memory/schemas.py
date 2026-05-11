"""Pydantic schemas for metadata and tool registry services."""

from datetime import datetime
from typing import Literal
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
    expires_at: datetime | None = Field(default=None, description="Optional expiry timestamp")


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
    retention_policy: str
    owner_agent: str | None
    indexed: bool
    lifecycle_state: str
    lifecycle_reason: str | None
    lifecycle_updated_at: datetime | None
    archived_at: datetime | None
    pruned_at: datetime | None
    expires_at: datetime | None
    freshness_score: float
    last_compacted_at: datetime | None


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
    include_inactive: bool = Field(
        default=False, description="Include archived or soft-pruned metadata"
    )


class MemoryLifecycleRequest(BaseModel):
    """Request to preview or apply SQL-backed memory lifecycle policy."""

    entity_types: list[str] | None = Field(default=None, description="Filter by entity types")
    tags: list[str] | None = Field(default=None, description="Filter by tags")
    category: str | None = Field(default=None, description="Filter by category")
    retention_policy: str | None = Field(default=None, description="Filter by retention policy")
    lifecycle_state: str | None = Field(default=None, description="Filter by lifecycle state")
    include_inactive: bool = Field(default=False, description="Evaluate archived/pruned records")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records to evaluate")
    archive_after_days: int = Field(default=90, ge=1, le=3650)
    soft_prune_after_days: int = Field(default=365, ge=1, le=3650)
    archive_relevance_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    soft_prune_relevance_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    promote_relevance_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    promote_access_count_threshold: int = Field(default=20, ge=1, le=1_000_000)
    compress_after_days: int = Field(default=30, ge=1, le=3650)
    compress_access_count_threshold: int = Field(default=10, ge=1, le=1_000_000)
    reference_time: datetime | None = Field(
        default=None, description="Deterministic policy timestamp for tests/jobs"
    )


class MemoryLifecycleDecision(BaseModel):
    """A deterministic lifecycle recommendation for one metadata record."""

    metadata_id: UUID
    entity_type: str
    entity_id: str
    retention_policy: str
    current_state: str
    recommended_action: Literal["keep", "promote", "archive", "soft_prune", "compress_candidate"]
    reason: str
    freshness_score: float
    last_accessed_at: datetime | None


class MemoryLifecycleResponse(BaseModel):
    """Lifecycle preview/apply response."""

    decisions: list[MemoryLifecycleDecision]
    total: int
    applied: bool


class MemoryCompressionRequest(BaseModel):
    """Request to preview or apply deterministic memory compression."""

    entity_types: list[str] | None = Field(default=None, description="Filter by entity types")
    tags: list[str] | None = Field(default=None, description="Filter by tags")
    category: str | None = Field(default=None, description="Filter by category")
    retention_policy: str | None = Field(default=None, description="Filter by retention policy")
    include_inactive: bool = Field(default=False, description="Evaluate archived/pruned records")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records to evaluate")
    compress_after_days: int = Field(default=30, ge=1, le=3650)
    compress_access_count_threshold: int = Field(default=10, ge=1, le=1_000_000)
    max_summary_chars: int = Field(default=240, ge=80, le=4_000)
    reference_time: datetime | None = Field(
        default=None, description="Deterministic compression timestamp for tests/jobs"
    )


class MemoryCompressionCandidate(BaseModel):
    """A deterministic compression candidate."""

    metadata_id: UUID
    entity_type: str
    entity_id: str
    original_description: str | None
    compressed_description: str
    original_length: int
    compressed_length: int
    reason: str
    embedding_reindexed: bool = False


class MemoryCompressionResponse(BaseModel):
    """Compression preview/apply response."""

    candidates: list[MemoryCompressionCandidate]
    total: int
    applied: bool


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
