"""Vector storage backend contracts and SQLite default implementation."""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from dgentic.memory.models import MemoryMetadata, VectorEmbedding


@dataclass(frozen=True)
class VectorSearchMatch:
    """A vector search match with its attached metadata."""

    metadata: MemoryMetadata
    similarity_score: float
    vector_record: VectorEmbedding | None


class VectorBackend(Protocol):
    """Backend contract for vector storage and similarity search."""

    def store_embedding(
        self,
        metadata_id: UUID | str,
        model: str,
        embedding: Sequence[float],
    ) -> VectorEmbedding:
        """Store an embedding vector for a metadata record."""
        ...

    def get_embedding(self, metadata_id: UUID | str) -> VectorEmbedding | None:
        """Fetch the first stored embedding row for a metadata record."""
        ...

    def get_embedding_values(self, metadata_id: UUID | str) -> list[float] | None:
        """Fetch decoded embedding values for a metadata record."""
        ...

    def delete_embedding(self, metadata_id: UUID | str) -> bool:
        """Delete the first stored embedding row for a metadata record."""
        ...

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        similarity_threshold: float = 0.7,
        limit: int | None = None,
    ) -> list[VectorSearchMatch]:
        """Search stored embeddings by cosine similarity."""
        ...


class SQLiteVectorBackend:
    """SQLite-compatible JSON-vector backend used by the MVP runtime."""

    def __init__(self, session: Session):
        self.session = session

    def store_embedding(
        self,
        metadata_id: UUID | str,
        model: str,
        embedding: Sequence[float],
    ) -> VectorEmbedding:
        vector_record = VectorEmbedding(
            metadata_id=str(metadata_id),
            model=model,
            embedding=json.dumps(list(embedding)),
        )
        self.session.add(vector_record)
        self.session.commit()
        self.session.refresh(vector_record)
        return vector_record

    def get_embedding(self, metadata_id: UUID | str) -> VectorEmbedding | None:
        return (
            self.session.query(VectorEmbedding)
            .filter(VectorEmbedding.metadata_id == str(metadata_id))
            .first()
        )

    def get_embedding_values(self, metadata_id: UUID | str) -> list[float] | None:
        record = self.get_embedding(metadata_id)
        if record is None:
            return None
        return _decode_embedding(record.embedding)

    def delete_embedding(self, metadata_id: UUID | str) -> bool:
        record = self.get_embedding(metadata_id)
        if record is None:
            return False

        self.session.delete(record)
        self.session.commit()
        return True

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        similarity_threshold: float = 0.7,
        limit: int | None = None,
    ) -> list[VectorSearchMatch]:
        matches: list[VectorSearchMatch] = []
        for vector_record in self.session.query(VectorEmbedding).all():
            metadata = vector_record.memory_metadata
            if metadata is None:
                continue

            similarity = cosine_similarity(
                query_embedding,
                _decode_embedding(vector_record.embedding),
            )
            if similarity < similarity_threshold:
                continue
            matches.append(
                VectorSearchMatch(
                    metadata=metadata,
                    similarity_score=similarity,
                    vector_record=vector_record,
                )
            )

        matches.sort(key=lambda match: match.similarity_score, reverse=True)
        if limit is None:
            return matches
        return matches[:limit]


def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    """Calculate cosine similarity between two vectors."""

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def _decode_embedding(raw_embedding: str) -> list[float]:
    values = json.loads(raw_embedding)
    return [float(value) for value in values]
