"""Embedding service for vector generation and storage."""

import hashlib
import math
import re
from uuid import UUID

from sqlalchemy.orm import Session

from dgentic.memory.models import VectorEmbedding
from dgentic.memory.vector_backend import SQLiteVectorBackend, VectorBackend, cosine_similarity

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class EmbeddingService:
    """Service for generating and storing vector embeddings.

    The default model is a deterministic hashed bag-of-words embedding. It is dependency-light,
    testable, and good enough for MVP semantic retrieval contracts. Operators can still pass a
    sentence-transformers model name when that optional dependency is installed.
    """

    DEFAULT_MODEL = "dgentic-hash-embedding-v1"
    EMBEDDING_DIMENSION = 384

    def __init__(
        self,
        session: Session,
        model_name: str | None = None,
        vector_backend: VectorBackend | None = None,
    ):
        self.session = session
        self.model_name = model_name or self.DEFAULT_MODEL
        self.vector_backend = vector_backend or SQLiteVectorBackend(session)
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "Semantic embedding generation requires the optional "
                    "`sentence-transformers` dependency."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def generate_embedding(self, text: str) -> list[float]:
        content = text or "[empty]"
        if self.model_name == self.DEFAULT_MODEL:
            return self._generate_hash_embedding(content)
        embedding = self.model.encode(content, convert_to_tensor=False)
        return embedding.tolist()

    def _generate_hash_embedding(self, text: str) -> list[float]:
        vector = [0.0] * self.EMBEDDING_DIMENSION
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            tokens = ["empty"]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.EMBEDDING_DIMENSION
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def store_embedding(self, metadata_id: UUID | str, embedding: list[float]) -> VectorEmbedding:
        return self.vector_backend.store_embedding(metadata_id, self.model_name, embedding)

    def embed_and_store(self, metadata_id: UUID | str, text: str) -> VectorEmbedding:
        embedding = self.generate_embedding(text)
        return self.store_embedding(metadata_id, embedding)

    def get_embedding(self, metadata_id: UUID | str) -> VectorEmbedding | None:
        return self.vector_backend.get_embedding(metadata_id)

    def delete_embedding(self, metadata_id: UUID | str) -> bool:
        return self.vector_backend.delete_embedding(metadata_id)

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        return cosine_similarity(vec1, vec2)
