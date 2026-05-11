"""Tests for deterministic memory compression."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.compression_service import (
    COMPRESSION_REASON,
    MemoryCompressionService,
)
from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import Base, MemoryMetadata, VectorEmbedding
from dgentic.memory.schemas import MemoryCompressionRequest, MetadataCreateRequest


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()


def _create_compression_candidate(
    session: Session,
    *,
    now: datetime,
    entity_id: str = "compress-me",
    retention_policy: str = "automatic",
) -> MemoryMetadata:
    description = (
        "This memory has been used repeatedly by agents while planning retrieval work. "
        "It contains implementation context, validation notes, and follow-up details that "
        "can be summarized into a shorter durable record without losing its purpose."
    )
    metadata = MetadataService(session).create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id=entity_id,
            tags=["compression", "retrieval"],
            category="planning",
            description=description,
            relevance_score=0.6,
            retention_policy=retention_policy,
        )
    )
    stored = session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()
    stored.updated_at = now - timedelta(days=45)
    stored.created_at = now - timedelta(days=45)
    stored.access_count = 15
    session.commit()
    return stored


def test_memory_compression_preview_is_read_only(db_session: Session) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = _create_compression_candidate(db_session, now=now)
    original_description = metadata.description
    service = MemoryCompressionService(db_session, EmbeddingService(db_session))

    candidates = service.preview(
        MemoryCompressionRequest(reference_time=now, max_summary_chars=120)
    )
    stored = db_session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()

    assert len(candidates) == 1
    assert candidates[0].entity_id == "compress-me"
    assert candidates[0].compressed_length <= 120
    assert candidates[0].compressed_length < candidates[0].original_length
    assert stored.description == original_description
    assert stored.last_compacted_at is None


def test_memory_compression_apply_updates_metadata_and_reindexes_embedding(
    db_session: Session,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = _create_compression_candidate(db_session, now=now)
    embedding_service = EmbeddingService(db_session)
    embedding_service.embed_and_store(metadata.id, metadata.description or "")
    service = MemoryCompressionService(db_session, embedding_service)

    candidates = service.apply(MemoryCompressionRequest(reference_time=now, max_summary_chars=120))
    stored = db_session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()
    vector_records = (
        db_session.query(VectorEmbedding).filter(VectorEmbedding.metadata_id == metadata.id).all()
    )

    assert candidates[0].embedding_reindexed is True
    assert stored.description == candidates[0].compressed_description
    assert stored.last_compacted_at is not None
    assert stored.last_compacted_at.replace(tzinfo=UTC) == now
    assert stored.lifecycle_reason == COMPRESSION_REASON
    assert len(vector_records) == 1
    assert embedding_service.vector_backend.get_embedding_values(metadata.id) == (
        embedding_service.generate_embedding(stored.description or "")
    )

    repeated_candidates = service.apply(
        MemoryCompressionRequest(reference_time=now, max_summary_chars=120)
    )

    assert repeated_candidates == []


def test_memory_compression_excludes_protected_retention_policy(db_session: Session) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    _create_compression_candidate(
        db_session,
        now=now,
        entity_id="manual-memory",
        retention_policy="manual",
    )
    service = MemoryCompressionService(db_session, EmbeddingService(db_session))

    candidates = service.preview(MemoryCompressionRequest(reference_time=now))

    assert candidates == []


def test_memory_compression_excludes_inactive_and_short_descriptions_by_default(
    db_session: Session,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    inactive = _create_compression_candidate(db_session, now=now, entity_id="inactive-memory")
    inactive.lifecycle_state = "archived"
    inactive.updated_at = now - timedelta(days=45)
    short = _create_compression_candidate(db_session, now=now, entity_id="short-memory")
    short.description = "Already concise."
    short.updated_at = now - timedelta(days=45)
    db_session.commit()
    service = MemoryCompressionService(db_session, EmbeddingService(db_session))

    candidates = service.preview(
        MemoryCompressionRequest(reference_time=now, max_summary_chars=120)
    )
    inactive_candidates = service.preview(
        MemoryCompressionRequest(
            reference_time=now,
            include_inactive=True,
            max_summary_chars=120,
        )
    )

    assert candidates == []
    assert {candidate.entity_id for candidate in inactive_candidates} == {"inactive-memory"}
