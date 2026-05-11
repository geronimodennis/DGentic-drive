"""Tests for SQL-backed memory lifecycle policy."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.lifecycle_service import MemoryLifecycleService
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import Base, MemoryMetadata
from dgentic.memory.schemas import MemoryLifecycleRequest, MetadataCreateRequest


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()


def _create_metadata(
    session: Session,
    *,
    entity_id: str,
    now: datetime,
    age_days: int = 0,
    relevance_score: float = 0.5,
    access_count: int = 0,
    retention_policy: str = "automatic",
    expires_at: datetime | None = None,
) -> MemoryMetadata:
    metadata = MetadataService(session).create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id=entity_id,
            tags=["lifecycle"],
            description=f"Lifecycle metadata {entity_id}.",
            relevance_score=relevance_score,
            retention_policy=retention_policy,
            expires_at=expires_at,
        )
    )
    stored = session.query(MemoryMetadata).filter(MemoryMetadata.id == str(metadata.id)).one()
    activity_at = now - timedelta(days=age_days)
    stored.created_at = activity_at
    stored.updated_at = activity_at
    stored.access_count = access_count
    session.commit()
    return stored


def test_memory_lifecycle_preview_recommends_conservative_actions(db_session: Session) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    _create_metadata(db_session, entity_id="promote-me", now=now, relevance_score=0.96)
    _create_metadata(db_session, entity_id="archive-me", now=now, age_days=120, relevance_score=0.3)
    _create_metadata(
        db_session,
        entity_id="prune-me",
        now=now,
        age_days=400,
        relevance_score=0.1,
    )
    _create_metadata(
        db_session,
        entity_id="compress-me",
        now=now,
        age_days=40,
        relevance_score=0.5,
        access_count=15,
    )
    _create_metadata(
        db_session,
        entity_id="manual-memory",
        now=now,
        age_days=500,
        relevance_score=0.1,
        retention_policy="manual",
    )

    decisions = MemoryLifecycleService(db_session).preview(
        MemoryLifecycleRequest(reference_time=now)
    )
    actions = {decision.entity_id: decision.recommended_action for decision in decisions}

    assert actions["promote-me"] == "promote"
    assert actions["archive-me"] == "archive"
    assert actions["prune-me"] == "soft_prune"
    assert actions["compress-me"] == "compress_candidate"
    assert actions["manual-memory"] == "keep"


def test_memory_lifecycle_apply_soft_updates_metadata_idempotently(
    db_session: Session,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = _create_metadata(
        db_session,
        entity_id="archive-me",
        now=now,
        age_days=120,
        relevance_score=0.3,
    )
    service = MemoryLifecycleService(db_session)

    first_decisions = service.apply(MemoryLifecycleRequest(reference_time=now))
    stored = db_session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()
    second_decisions = service.apply(
        MemoryLifecycleRequest(reference_time=now, include_inactive=True)
    )

    assert first_decisions[0].recommended_action == "archive"
    assert stored.lifecycle_state == "archived"
    assert stored.archived_at is not None
    assert stored.archived_at.replace(tzinfo=UTC) == now
    assert stored.lifecycle_reason == "Memory is stale and eligible for archival."
    assert second_decisions[0].recommended_action == "keep"


def test_memory_lifecycle_apply_promotes_high_value_memory(db_session: Session) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = _create_metadata(
        db_session,
        entity_id="promote-me",
        now=now,
        relevance_score=0.95,
    )

    decisions = MemoryLifecycleService(db_session).apply(MemoryLifecycleRequest(reference_time=now))
    stored = db_session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()

    assert decisions[0].recommended_action == "promote"
    assert stored.lifecycle_state == "promoted"
    assert stored.retention_policy == "permanent"


def test_memory_lifecycle_apply_does_not_mutate_compression_candidates(
    db_session: Session,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = _create_metadata(
        db_session,
        entity_id="compress-me",
        now=now,
        age_days=40,
        relevance_score=0.5,
        access_count=15,
    )
    original_updated_at = metadata.updated_at

    first_decisions = MemoryLifecycleService(db_session).apply(
        MemoryLifecycleRequest(reference_time=now)
    )
    stored = db_session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()
    second_decisions = MemoryLifecycleService(db_session).preview(
        MemoryLifecycleRequest(reference_time=now)
    )

    assert first_decisions[0].recommended_action == "compress_candidate"
    assert stored.lifecycle_state == "active"
    assert stored.lifecycle_reason is None
    assert stored.last_compacted_at is None
    assert stored.updated_at == original_updated_at
    assert second_decisions[0].recommended_action == "compress_candidate"
