"""Tests for vector backend contracts."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import Base
from dgentic.memory.schemas import MetadataCreateRequest
from dgentic.memory.vector_backend import SQLiteVectorBackend, cosine_similarity


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()


def test_sqlite_vector_backend_stores_fetches_searches_and_deletes(
    db_session: Session,
) -> None:
    metadata_service = MetadataService(db_session)
    backend = SQLiteVectorBackend(db_session)
    first = metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="first-vector",
            description="First vector record.",
        )
    )
    second = metadata_service.create(
        MetadataCreateRequest(
            entity_type="memory",
            entity_id="second-vector",
            description="Second vector record.",
        )
    )

    first_record = backend.store_embedding(first.id, "test-vector-model", [1.0, 0.0])
    backend.store_embedding(second.id, "test-vector-model", [0.0, 1.0])
    matches = backend.search([1.0, 0.0], similarity_threshold=0.0)

    assert first_record.model == "test-vector-model"
    assert backend.get_embedding(first.id) is not None
    assert backend.get_embedding_values(first.id) == [1.0, 0.0]
    assert [match.metadata.entity_id for match in matches] == ["first-vector", "second-vector"]
    assert matches[0].similarity_score > matches[1].similarity_score
    assert backend.delete_embedding(first.id) is True
    assert backend.get_embedding(first.id) is None
    assert backend.delete_embedding(first.id) is False


def test_cosine_similarity_handles_zero_vectors() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
