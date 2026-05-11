"""CRUD service for metadata index records."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
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
            expires_at=request.expires_at,
        )
        self.session.add(metadata)
        self.session.commit()
        self.session.refresh(metadata)
        self.session.expunge(metadata)
        return metadata

    def upsert_by_entity(self, request: MetadataCreateRequest) -> MemoryMetadata:
        matches = (
            self.session.query(MemoryMetadata)
            .filter(
                MemoryMetadata.entity_type == request.entity_type,
                MemoryMetadata.entity_id == request.entity_id,
            )
            .order_by(MemoryMetadata.created_at.asc())
            .all()
        )
        if matches:
            metadata = matches[0]
            for duplicate in matches[1:]:
                self.session.delete(duplicate)
        else:
            metadata = MemoryMetadata(
                entity_type=request.entity_type,
                entity_id=request.entity_id,
            )
            self.session.add(metadata)

        self._apply_upsert(metadata, request)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            metadata = (
                self.session.query(MemoryMetadata)
                .filter(
                    MemoryMetadata.entity_type == request.entity_type,
                    MemoryMetadata.entity_id == request.entity_id,
                )
                .order_by(MemoryMetadata.created_at.asc())
                .first()
            )
            if metadata is None:
                raise
            self._apply_upsert(metadata, request)
            self.session.commit()

        self.session.refresh(metadata)
        self.session.expunge(metadata)
        return metadata

    def _apply_upsert(
        self,
        metadata: MemoryMetadata,
        request: MetadataCreateRequest,
    ) -> None:
        metadata.tags = request.tags
        metadata.category = request.category
        metadata.description = request.description
        metadata.relevance_score = request.relevance_score
        metadata.retention_policy = request.retention_policy
        metadata.owner_agent = request.owner_agent
        metadata.expires_at = request.expires_at
        metadata.lifecycle_state = "active"
        metadata.lifecycle_reason = None
        metadata.lifecycle_updated_at = datetime.now(UTC)
        metadata.archived_at = None
        metadata.pruned_at = None
        metadata.updated_at = datetime.now(UTC)

    def get_by_id(
        self,
        metadata_id: UUID | str,
        *,
        update_access: bool = True,
    ) -> MemoryMetadata | None:
        metadata = (
            self.session.query(MemoryMetadata).filter(MemoryMetadata.id == str(metadata_id)).first()
        )
        if metadata and update_access:
            metadata.increment_access()
            self.session.commit()
            self.session.refresh(metadata)
        return metadata

    def list_by_filters(
        self,
        entity_type: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        match_all_tags: bool = False,
        indexed: bool | None = None,
        retention_policy: str | None = None,
        lifecycle_state: str | None = None,
        owner_agent: str | None = None,
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
        if lifecycle_state:
            query = query.filter(MemoryMetadata.lifecycle_state == lifecycle_state)
        if owner_agent:
            query = query.filter(MemoryMetadata.owner_agent == owner_agent)

        items = query.order_by(MemoryMetadata.created_at.desc()).all()
        if tags:
            required_tags = set(tags)
            if match_all_tags:
                items = [
                    item
                    for item in items
                    if (item_tags := set(item.tags or [])) and item_tags.issubset(required_tags)
                ]
            else:
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
