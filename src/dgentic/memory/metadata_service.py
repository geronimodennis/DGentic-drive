"""CRUD service for metadata index records."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from dgentic.memory.models import MemoryMetadata
from dgentic.memory.schemas import MetadataCreateRequest


class MetadataService:
    """Service for metadata index CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, request: MetadataCreateRequest) -> MemoryMetadata:
        metadata = MemoryMetadata(
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            tags=request.tags,
            category=request.category,
            description=request.description,
            relevance_score=request.relevance_score,
            retention_policy=request.retention_policy,
            owner_agent=request.owner_agent,
        )
        self.session.add(metadata)
        self.session.commit()
        self.session.refresh(metadata)
        self.session.expunge(metadata)
        return metadata

    def get_by_id(self, metadata_id: UUID | str) -> MemoryMetadata | None:
        metadata = (
            self.session.query(MemoryMetadata).filter(MemoryMetadata.id == str(metadata_id)).first()
        )
        if metadata:
            metadata.increment_access()
            self.session.commit()
            self.session.refresh(metadata)
        return metadata

    def list_by_filters(
        self,
        entity_type: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        indexed: bool | None = None,
        retention_policy: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[MemoryMetadata], int]:
        query = self.session.query(MemoryMetadata)

        if entity_type:
            query = query.filter(MemoryMetadata.entity_type == entity_type)
        if category:
            query = query.filter(MemoryMetadata.category == category)
        if indexed is not None:
            query = query.filter(MemoryMetadata.indexed == indexed)
        if retention_policy:
            query = query.filter(MemoryMetadata.retention_policy == retention_policy)

        items = query.order_by(MemoryMetadata.created_at.desc()).all()
        if tags:
            required_tags = set(tags)
            items = [item for item in items if required_tags.intersection(item.tags or [])]

        total = len(items)
        return items[offset : offset + limit], total

    def update(self, metadata_id: UUID | str, **kwargs) -> MemoryMetadata | None:
        metadata = (
            self.session.query(MemoryMetadata).filter(MemoryMetadata.id == str(metadata_id)).first()
        )
        if not metadata:
            return None

        for key, value in kwargs.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)

        metadata.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(metadata)
        return metadata

    def delete(self, metadata_id: UUID | str) -> bool:
        metadata = (
            self.session.query(MemoryMetadata).filter(MemoryMetadata.id == str(metadata_id)).first()
        )
        if not metadata:
            return False

        self.session.delete(metadata)
        self.session.commit()
        return True

    def get_recent_memories(self, limit: int = 10) -> list[MemoryMetadata]:
        return (
            self.session.query(MemoryMetadata)
            .order_by(MemoryMetadata.last_accessed_at.desc())
            .limit(limit)
            .all()
        )

    def get_high_relevance(self, threshold: float = 0.8, limit: int = 10) -> list[MemoryMetadata]:
        return (
            self.session.query(MemoryMetadata)
            .filter(MemoryMetadata.relevance_score >= threshold)
            .order_by(MemoryMetadata.relevance_score.desc())
            .limit(limit)
            .all()
        )
