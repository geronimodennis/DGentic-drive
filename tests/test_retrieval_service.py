"""Tests for dependency-light semantic retrieval (Story 6.2)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import Base, MemoryMetadata
from dgentic.memory.retrieval_service import RetrievalService
from dgentic.memory.schemas import HybridRetrievalRequest, MetadataCreateRequest


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()


def test_hash_embedding_is_deterministic_and_semantic_enough(db_session: Session) -> None:
    service = EmbeddingService(db_session)

    first = service.generate_embedding("semantic search metadata indexing")
    second = service.generate_embedding("semantic search metadata indexing")
    related = service.generate_embedding("metadata indexing for semantic search")
    unrelated = service.generate_embedding("release packaging checksum upload")

    assert first == second
    assert len(first) == service.EMBEDDING_DIMENSION
    assert EmbeddingService.cosine_similarity(first, related) > EmbeddingService.cosine_similarity(
        first, unrelated
    )


def test_hybrid_search_scores_metadata_text_without_stored_embedding(db_session: Session) -> None:
    metadata_service = MetadataService(db_session)
    embedding_service = EmbeddingService(db_session)
    retrieval_service = RetrievalService(db_session, embedding_service)

    metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="semantic-memory",
            tags=["semantic", "retrieval"],
            category="memory",
            description="Semantic retrieval combines metadata filters and vector similarity.",
            relevance_score=0.8,
        )
    )
    metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="release-memory",
            tags=["release"],
            category="release",
            description="Release bundles include wheel hashes and zip artifacts.",
            relevance_score=0.9,
        )
    )

    results, query_time_ms = retrieval_service.hybrid_search(
        HybridRetrievalRequest(
            query="semantic metadata retrieval",
            tags=["semantic"],
            similarity_threshold=0.1,
        )
    )

    assert query_time_ms >= 0
    assert len(results) == 1
    assert results[0].entity_id == "semantic-memory"
    assert results[0].source == "hybrid_retrieval"
    assert results[0].combined_score > 0


def test_vector_search_uses_stored_embeddings(db_session: Session) -> None:
    metadata_service = MetadataService(db_session)
    embedding_service = EmbeddingService(db_session)
    retrieval_service = RetrievalService(db_session, embedding_service)

    semantic = metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="semantic-memory",
            tags=["semantic"],
            description="Semantic vector retrieval for indexed metadata.",
        )
    )
    release = metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="release-memory",
            tags=["release"],
            description="Release bundles and checksums.",
        )
    )
    embedding_service.embed_and_store(semantic.id, semantic.description)
    embedding_service.embed_and_store(release.id, release.description)

    results, _query_time_ms = retrieval_service.vector_search(
        "semantic vector metadata",
        similarity_threshold=0.1,
    )

    assert results
    assert results[0].entity_id == "semantic-memory"
    assert results[0].source == "vector_search"


def test_retrieval_excludes_inactive_metadata_by_default(db_session: Session) -> None:
    metadata_service = MetadataService(db_session)
    embedding_service = EmbeddingService(db_session)
    retrieval_service = RetrievalService(db_session, embedding_service)

    for entity_id, lifecycle_state in (
        ("active-memory", "active"),
        ("archived-memory", "archived"),
        ("soft-pruned-memory", "soft_pruned"),
    ):
        metadata = metadata_service.create(
            MetadataCreateRequest(
                entity_type="memory",
                entity_id=entity_id,
                tags=["lifecycle"],
                category="retrieval",
                description="Lifecycle retrieval candidate.",
                relevance_score=0.8,
            )
        )
        stored = db_session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata.id).one()
        stored.lifecycle_state = lifecycle_state
    db_session.commit()

    default_results, _ = retrieval_service.metadata_search(category="retrieval")
    inactive_results, _ = retrieval_service.metadata_search(
        category="retrieval",
        include_inactive=True,
    )

    assert {result.entity_id for result in default_results} == {"active-memory"}
    assert {result.entity_id for result in inactive_results} == {
        "active-memory",
        "archived-memory",
        "soft-pruned-memory",
    }


def test_vector_and_hybrid_retrieval_include_inactive_only_when_requested(
    db_session: Session,
) -> None:
    metadata_service = MetadataService(db_session)
    embedding_service = EmbeddingService(db_session)
    retrieval_service = RetrievalService(db_session, embedding_service)

    active = metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="active-vector",
            tags=["lifecycle"],
            category="retrieval",
            description="Lifecycle vector retrieval candidate.",
        )
    )
    archived = metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="archived-vector",
            tags=["lifecycle"],
            category="retrieval",
            description="Lifecycle vector retrieval candidate.",
        )
    )
    stored_archived = (
        db_session.query(MemoryMetadata).filter(MemoryMetadata.id == archived.id).one()
    )
    stored_archived.lifecycle_state = "archived"
    db_session.commit()
    embedding_service.embed_and_store(active.id, active.description)
    embedding_service.embed_and_store(archived.id, archived.description)

    default_vector_results, _ = retrieval_service.vector_search(
        "lifecycle vector retrieval candidate",
        similarity_threshold=0.0,
    )
    inactive_vector_results, _ = retrieval_service.vector_search(
        "lifecycle vector retrieval candidate",
        similarity_threshold=0.0,
        include_inactive=True,
    )
    default_hybrid_results, _ = retrieval_service.hybrid_search(
        HybridRetrievalRequest(
            query="lifecycle vector retrieval candidate",
            metadata_filters={"category": "retrieval"},
            similarity_threshold=0.0,
        )
    )
    inactive_hybrid_results, _ = retrieval_service.hybrid_search(
        HybridRetrievalRequest(
            query="lifecycle vector retrieval candidate",
            metadata_filters={"category": "retrieval"},
            similarity_threshold=0.0,
            include_inactive=True,
        )
    )

    assert {result.entity_id for result in default_vector_results} == {"active-vector"}
    assert {result.entity_id for result in inactive_vector_results} == {
        "active-vector",
        "archived-vector",
    }
    assert {result.entity_id for result in default_hybrid_results} == {"active-vector"}
    assert {result.entity_id for result in inactive_hybrid_results} == {
        "active-vector",
        "archived-vector",
    }
