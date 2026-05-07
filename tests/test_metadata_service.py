"""Tests for metadata service (Story 6.1)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import Base
from dgentic.memory.schemas import MetadataCreateRequest


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestMetadataService:
    """Tests for MetadataService CRUD operations."""

    def test_create_metadata(self, db_session: Session):
        """Test creating a metadata entry."""
        service = MetadataService(db_session)
        request = MetadataCreateRequest(
            entity_type="skill",
            entity_id="skill-123",
            tags=["search", "filtering"],
            category="retrieval",
            description="Test skill",
            relevance_score=0.8,
        )

        metadata = service.create(request)

        assert metadata.id is not None
        assert metadata.entity_type == "skill"
        assert metadata.entity_id == "skill-123"
        assert "search" in metadata.tags
        assert metadata.access_count == 0

    def test_get_metadata_by_id(self, db_session: Session):
        """Test retrieving metadata by ID."""
        service = MetadataService(db_session)
        request = MetadataCreateRequest(
            entity_type="memory",
            entity_id="mem-456",
            tags=["important"],
            description="Test memory",
        )
        created = service.create(request)

        retrieved = service.get_by_id(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.access_count == 1  # Should increment

    def test_list_by_entity_type(self, db_session: Session):
        """Test filtering by entity type."""
        service = MetadataService(db_session)

        # Create multiple entries
        for i in range(3):
            service.create(
                MetadataCreateRequest(
                    entity_type="skill",
                    entity_id=f"skill-{i}",
                    tags=["test"],
                )
            )

        for i in range(2):
            service.create(
                MetadataCreateRequest(
                    entity_type="memory",
                    entity_id=f"mem-{i}",
                    tags=["test"],
                )
            )

        skills, total = service.list_by_filters(entity_type="skill")

        assert len(skills) == 3
        assert total == 3

    def test_list_by_tags(self, db_session: Session):
        """Test filtering by tags."""
        service = MetadataService(db_session)

        service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-1",
                tags=["search", "indexing"],
            )
        )
        service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-2",
                tags=["filtering"],
            )
        )

        results, total = service.list_by_filters(tags=["indexing"])

        assert len(results) == 1
        assert results[0].entity_id == "skill-1"

    def test_update_metadata(self, db_session: Session):
        """Test updating metadata."""
        service = MetadataService(db_session)
        created = service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-1",
                relevance_score=0.5,
            )
        )

        updated = service.update(created.id, relevance_score=0.9)

        assert updated.relevance_score == 0.9
        assert updated.updated_at > created.updated_at

    def test_delete_metadata(self, db_session: Session):
        """Test deleting metadata."""
        service = MetadataService(db_session)
        created = service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-1",
            )
        )

        success = service.delete(created.id)

        assert success is True
        assert service.get_by_id(created.id) is None

    def test_get_high_relevance(self, db_session: Session):
        """Test retrieving high-relevance entries."""
        service = MetadataService(db_session)

        service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-1",
                relevance_score=0.95,
            )
        )
        service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-2",
                relevance_score=0.5,
            )
        )

        high_rel = service.get_high_relevance(threshold=0.8)

        assert len(high_rel) == 1
        assert high_rel[0].entity_id == "skill-1"


class TestMetadataAccess:
    """Tests for metadata access tracking."""

    def test_increment_access_counter(self, db_session: Session):
        """Test that access counter increments."""
        service = MetadataService(db_session)
        metadata = service.create(
            MetadataCreateRequest(
                entity_type="skill",
                entity_id="skill-1",
            )
        )

        initial_count = metadata.access_count
        metadata.increment_access()
        db_session.commit()

        assert metadata.access_count == initial_count + 1
        assert metadata.last_accessed_at is not None
