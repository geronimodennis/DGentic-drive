"""Hybrid retrieval service for semantic and metadata search."""

import json
import time

from sqlalchemy import or_
from sqlalchemy.orm import Session

from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.lifecycle_service import ACTIVE_LIFECYCLE_STATES, metadata_is_retrievable
from dgentic.memory.models import MemoryMetadata, VectorEmbedding
from dgentic.memory.schemas import HybridRetrievalRequest, RetrievalResult


class RetrievalService:
    """Service for hybrid vector plus metadata retrieval."""

    def __init__(self, session: Session, embedding_service: EmbeddingService):
        self.session = session
        self.embedding_service = embedding_service

    def hybrid_search(self, request: HybridRetrievalRequest) -> tuple[list[RetrievalResult], float]:
        start_time = time.time()
        query_embedding = self.embedding_service.generate_embedding(request.query)
        metadata_items, _ = self._get_metadata_candidates(
            entity_types=request.entity_types,
            tags=request.tags,
            metadata_filters=request.metadata_filters,
            include_inactive=request.include_inactive,
        )

        results: list[RetrievalResult] = []
        for metadata in metadata_items:
            vector_record = (
                self.session.query(VectorEmbedding)
                .filter(VectorEmbedding.metadata_id == metadata.id)
                .first()
            )
            stored_embedding = (
                json.loads(vector_record.embedding)
                if vector_record
                else self.embedding_service.generate_embedding(self._metadata_text(metadata))
            )
            similarity_score = EmbeddingService.cosine_similarity(query_embedding, stored_embedding)
            if similarity_score < request.similarity_threshold:
                continue

            metadata_relevance = self._calculate_metadata_relevance(metadata)
            combined_score = (similarity_score * 0.7) + (metadata_relevance * 0.3)
            results.append(
                RetrievalResult(
                    metadata_id=metadata.id,
                    entity_type=metadata.entity_type,
                    entity_id=metadata.entity_id,
                    description=metadata.description,
                    similarity_score=round(similarity_score, 3),
                    metadata_relevance=round(metadata_relevance, 3),
                    combined_score=round(combined_score, 3),
                    source="hybrid_retrieval",
                )
            )

        results.sort(key=lambda result: result.combined_score, reverse=True)
        query_time_ms = (time.time() - start_time) * 1000
        return results[: request.limit], query_time_ms

    def vector_search(
        self,
        query: str,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        include_inactive: bool = False,
    ) -> tuple[list[RetrievalResult], float]:
        start_time = time.time()
        query_embedding = self.embedding_service.generate_embedding(query)
        all_embeddings = self.session.query(VectorEmbedding).all()

        results: list[RetrievalResult] = []
        for vector_record in all_embeddings:
            stored_embedding = json.loads(vector_record.embedding)
            similarity = EmbeddingService.cosine_similarity(query_embedding, stored_embedding)
            if similarity < similarity_threshold:
                continue

            metadata = vector_record.memory_metadata
            if metadata is None or (not include_inactive and not metadata_is_retrievable(metadata)):
                continue
            results.append(
                RetrievalResult(
                    metadata_id=metadata.id,
                    entity_type=metadata.entity_type,
                    entity_id=metadata.entity_id,
                    description=metadata.description,
                    similarity_score=round(similarity, 3),
                    metadata_relevance=1.0,
                    combined_score=round(similarity, 3),
                    source="vector_search",
                )
            )

        results.sort(key=lambda result: result.combined_score, reverse=True)
        query_time_ms = (time.time() - start_time) * 1000
        return results[:limit], query_time_ms

    def metadata_search(
        self,
        entity_types: list[str] | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> tuple[list[RetrievalResult], float]:
        start_time = time.time()
        query = self.session.query(MemoryMetadata)

        if entity_types:
            query = query.filter(MemoryMetadata.entity_type.in_(entity_types))
        if category:
            query = query.filter(MemoryMetadata.category == category)
        if not include_inactive:
            query = query.filter(
                or_(
                    MemoryMetadata.lifecycle_state.is_(None),
                    MemoryMetadata.lifecycle_state.in_(ACTIVE_LIFECYCLE_STATES),
                )
            )

        metadata_items = query.order_by(MemoryMetadata.relevance_score.desc()).all()
        if tags:
            required_tags = set(tags)
            metadata_items = [
                metadata
                for metadata in metadata_items
                if required_tags.intersection(metadata.tags or [])
            ]

        results = [
            RetrievalResult(
                metadata_id=metadata.id,
                entity_type=metadata.entity_type,
                entity_id=metadata.entity_id,
                description=metadata.description,
                similarity_score=1.0,
                metadata_relevance=metadata.relevance_score,
                combined_score=metadata.relevance_score,
                source="metadata_filter",
            )
            for metadata in metadata_items[:limit]
        ]

        query_time_ms = (time.time() - start_time) * 1000
        return results, query_time_ms

    def _get_metadata_candidates(
        self,
        entity_types: list[str] | None = None,
        tags: list[str] | None = None,
        metadata_filters: dict | None = None,
        include_inactive: bool = False,
    ) -> tuple[list[MemoryMetadata], int]:
        query = self.session.query(MemoryMetadata)

        if entity_types:
            query = query.filter(MemoryMetadata.entity_type.in_(entity_types))
        if metadata_filters:
            if "category" in metadata_filters:
                query = query.filter(MemoryMetadata.category == metadata_filters["category"])
            if "retention_policy" in metadata_filters:
                query = query.filter(
                    MemoryMetadata.retention_policy == metadata_filters["retention_policy"]
                )
            if "lifecycle_state" in metadata_filters:
                query = query.filter(
                    MemoryMetadata.lifecycle_state == metadata_filters["lifecycle_state"]
                )
        if not include_inactive:
            query = query.filter(
                or_(
                    MemoryMetadata.lifecycle_state.is_(None),
                    MemoryMetadata.lifecycle_state.in_(ACTIVE_LIFECYCLE_STATES),
                )
            )

        items = query.all()
        if tags:
            required_tags = set(tags)
            items = [item for item in items if required_tags.intersection(item.tags or [])]

        return items, len(items)

    def _calculate_metadata_relevance(self, metadata: MemoryMetadata) -> float:
        score = metadata.relevance_score
        if metadata.access_count > 10:
            score *= 1.1
        return min(score, 1.0)

    def _metadata_text(self, metadata: MemoryMetadata) -> str:
        parts = [
            metadata.entity_type,
            metadata.entity_id,
            metadata.category or "",
            metadata.description or "",
            " ".join(metadata.tags or []),
        ]
        return " ".join(part for part in parts if part)
