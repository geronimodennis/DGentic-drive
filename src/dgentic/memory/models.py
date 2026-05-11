"""SQLAlchemy ORM models for metadata indexing and tool registry services."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class MemoryMetadata(Base):
    """Metadata index for skills, memories, tools, and learned patterns."""

    __tablename__ = "memory_metadata"

    id = Column(String(36), primary_key=True, default=_new_id)
    entity_type = Column(String(50), nullable=False, default="memory")
    entity_id = Column(String(255), nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    category = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    last_accessed_at = Column(DateTime, nullable=True)
    access_count = Column(Integer, default=0)
    relevance_score = Column(Float, default=0.5)
    embedding_id = Column(String(36), nullable=True)
    retention_policy = Column(String(50), default="automatic")
    owner_agent = Column(String(100), nullable=True)
    indexed = Column(Boolean, default=False)
    lifecycle_state = Column(String(50), nullable=False, default="active")
    lifecycle_reason = Column(Text, nullable=True)
    lifecycle_updated_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    pruned_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    freshness_score = Column(Float, default=1.0)
    last_compacted_at = Column(DateTime(timezone=True), nullable=True)

    vector_embeddings = relationship(
        "VectorEmbedding",
        back_populates="memory_metadata",
        cascade="all, delete-orphan",
    )
    tool_manifest = relationship("ToolManifest", back_populates="memory_metadata", uselist=False)

    __table_args__ = (
        Index("idx_metadata_entity", "entity_type", "entity_id"),
        Index("idx_metadata_category", "category"),
        Index("idx_metadata_indexed", "indexed"),
        Index("idx_metadata_lifecycle_state", "lifecycle_state"),
        Index("idx_metadata_expires_at", "expires_at"),
    )

    def increment_access(self) -> None:
        self.access_count += 1
        self.last_accessed_at = _now()


class VectorEmbedding(Base):
    """Serialized vector embedding for semantic search prototypes."""

    __tablename__ = "vector_embeddings"

    id = Column(String(36), primary_key=True, default=_new_id)
    metadata_id = Column(
        String(36),
        ForeignKey("memory_metadata.id", ondelete="CASCADE"),
        nullable=False,
    )
    model = Column(String(255), nullable=False)
    embedding = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    memory_metadata = relationship("MemoryMetadata", back_populates="vector_embeddings")

    __table_args__ = (
        Index("idx_embedding_metadata", "metadata_id"),
        Index("idx_embedding_model", "model"),
    )


class ToolManifest(Base):
    """SQLAlchemy tool registry entry used by the metadata-backed registry service."""

    __tablename__ = "tool_registry"

    id = Column(String(36), primary_key=True, default=_new_id)
    tool_name = Column(String(255), nullable=False, unique=True)
    version = Column(String(50), nullable=False)
    source_path = Column(String(500), nullable=False)
    interface_signature = Column(String(255), nullable=False)
    permission_level = Column(String(50), nullable=False, default="approval_required")
    tags = Column(JSON, nullable=False, default=list)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    created_by_agent = Column(String(100), nullable=True)
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    reliability_score = Column(Float, default=1.0)
    deprecated = Column(Boolean, default=False)
    metadata_id = Column(
        String(36),
        ForeignKey("memory_metadata.id", ondelete="SET NULL"),
        nullable=True,
    )

    memory_metadata = relationship("MemoryMetadata", back_populates="tool_manifest")

    __table_args__ = (
        Index("idx_tool_name", "tool_name"),
        Index("idx_tool_deprecated", "deprecated"),
        Index("idx_tool_permission", "permission_level"),
    )

    def __init__(self, **kwargs):
        if "source_path" in kwargs:
            self._validate_source_path(kwargs["source_path"])
        super().__init__(**kwargs)

    @staticmethod
    def _validate_source_path(path: str) -> None:
        if not path:
            raise ValueError("source_path cannot be empty")

        normalized_path = path.replace("\\", "/")
        if ".." in normalized_path:
            raise ValueError("source_path cannot contain '..' (directory traversal)")
        if "\x00" in path:
            raise ValueError("source_path cannot contain null bytes")
        if not normalized_path.startswith("localmcp/"):
            raise ValueError(f"source_path must start with 'localmcp/' prefix. Got: {path}")
        if normalized_path.split("/")[0] != "localmcp":
            raise ValueError("source_path must be under localmcp/ directory")

    def record_usage(self, success: bool, execution_time_ms: int = 0) -> None:
        self.usage_count += 1
        self.last_used_at = _now()
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        if self.usage_count > 0:
            self.reliability_score = self.success_count / self.usage_count

    def mark_deprecated(self) -> None:
        self.deprecated = True
        self.updated_at = _now()


@event.listens_for(ToolManifest.source_path, "set")
def validate_tool_source_path(target, value, oldvalue, initiator):
    ToolManifest._validate_source_path(value)
    return value
