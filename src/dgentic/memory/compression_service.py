"""Deterministic memory compression service."""

import re
from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.lifecycle_service import ACTIVE_LIFECYCLE_STATES, PROTECTED_RETENTION_POLICIES
from dgentic.memory.models import MemoryMetadata
from dgentic.memory.schemas import (
    MemoryCompressionCandidate,
    MemoryCompressionRequest,
)

COMPRESSION_REASON = "Memory was deterministically compressed from lifecycle policy."
COMPRESSION_CANDIDATE_REASON = "Memory meets compression age/access thresholds."
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class MemoryCompressionService:
    """Preview and apply deterministic extractive memory compression."""

    def __init__(self, session: Session, embedding_service: EmbeddingService):
        self.session = session
        self.embedding_service = embedding_service

    def preview(self, request: MemoryCompressionRequest) -> list[MemoryCompressionCandidate]:
        candidates: list[MemoryCompressionCandidate] = []
        for metadata, reason in self._candidate_records(request):
            candidate = self._candidate(metadata, reason, request)
            if _candidate_reduces_description(candidate):
                candidates.append(candidate)
        return candidates

    def apply(self, request: MemoryCompressionRequest) -> list[MemoryCompressionCandidate]:
        now = _reference_time(request)
        candidates: list[MemoryCompressionCandidate] = []
        for metadata, reason in self._candidate_records(request):
            candidate = self._candidate(metadata, reason, request)
            if not _candidate_reduces_description(candidate):
                continue
            had_embedding = self.embedding_service.get_embedding(metadata.id) is not None
            metadata.description = candidate.compressed_description
            metadata.last_compacted_at = now
            metadata.lifecycle_reason = COMPRESSION_REASON
            metadata.lifecycle_updated_at = now
            metadata.updated_at = now
            if had_embedding:
                self.embedding_service.delete_embedding(metadata.id)
                self.embedding_service.embed_and_store(
                    metadata.id,
                    candidate.compressed_description,
                )
                candidate.embedding_reindexed = True
            candidates.append(candidate)
        self.session.commit()
        return candidates

    def _candidate_records(
        self,
        request: MemoryCompressionRequest,
    ) -> list[tuple[MemoryMetadata, str]]:
        now = _reference_time(request)
        query = self.session.query(MemoryMetadata)
        if request.entity_types:
            query = query.filter(MemoryMetadata.entity_type.in_(request.entity_types))
        if request.category:
            query = query.filter(MemoryMetadata.category == request.category)
        if request.retention_policy:
            query = query.filter(MemoryMetadata.retention_policy == request.retention_policy)
        if not request.include_inactive:
            query = query.filter(
                or_(
                    MemoryMetadata.lifecycle_state.is_(None),
                    MemoryMetadata.lifecycle_state.in_(ACTIVE_LIFECYCLE_STATES),
                )
            )

        records = query.order_by(MemoryMetadata.updated_at.asc()).all()
        if request.tags:
            required_tags = set(request.tags)
            records = [
                metadata for metadata in records if required_tags.intersection(metadata.tags or [])
            ]
        candidates = [
            (metadata, COMPRESSION_CANDIDATE_REASON)
            for metadata in records
            if _meets_compression_thresholds(metadata, request, now)
        ]
        return candidates[: request.limit]

    def _candidate(
        self,
        metadata: MemoryMetadata,
        reason: str,
        request: MemoryCompressionRequest,
    ) -> MemoryCompressionCandidate:
        original_description = metadata.description
        compressed_description = _compress_metadata_description(metadata, request.max_summary_chars)
        return MemoryCompressionCandidate(
            metadata_id=metadata.id,
            entity_type=metadata.entity_type,
            entity_id=metadata.entity_id,
            original_description=original_description,
            compressed_description=compressed_description,
            original_length=len(original_description or ""),
            compressed_length=len(compressed_description),
            reason=reason,
        )


def _meets_compression_thresholds(
    metadata: MemoryMetadata,
    request: MemoryCompressionRequest,
    now: datetime,
) -> bool:
    retention_policy = (metadata.retention_policy or "").strip().lower()
    description = " ".join((metadata.description or "").split())
    return (
        retention_policy not in PROTECTED_RETENTION_POLICIES
        and len(description) > request.max_summary_chars
        and _age_days(metadata, now) >= request.compress_after_days
        and metadata.access_count >= request.compress_access_count_threshold
    )


def _age_days(metadata: MemoryMetadata, now: datetime) -> int:
    activity_time = (
        metadata.last_compacted_at
        or metadata.last_accessed_at
        or metadata.updated_at
        or metadata.created_at
    )
    return max(
        (now - _as_utc(activity_time)).days,
        0,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _reference_time(request: MemoryCompressionRequest) -> datetime:
    if request.reference_time is None:
        return datetime.now(UTC)
    if request.reference_time.tzinfo is None:
        return request.reference_time.replace(tzinfo=UTC)
    return request.reference_time.astimezone(UTC)


def _compress_metadata_description(metadata: MemoryMetadata, max_summary_chars: int) -> str:
    source = " ".join((metadata.description or "").split())
    if len(source) <= max_summary_chars:
        return source

    summary_parts: list[str] = []
    for sentence in _SENTENCE_RE.split(source):
        candidate = " ".join([*summary_parts, sentence]).strip()
        if len(candidate) > max_summary_chars:
            break
        summary_parts.append(sentence)

    if summary_parts:
        return " ".join(summary_parts)
    return _truncate_on_word_boundary(source, max_summary_chars)


def _truncate_on_word_boundary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    suffix = "..."
    slice_end = max(max_chars - len(suffix), 1)
    truncated = text[:slice_end].rsplit(" ", 1)[0].strip()
    if not truncated:
        truncated = text[:slice_end].strip()
    return f"{truncated.rstrip('.,;:')}{suffix}"


def _candidate_reduces_description(candidate: MemoryCompressionCandidate) -> bool:
    return (
        candidate.original_length > 0
        and candidate.compressed_length > 0
        and candidate.compressed_length < candidate.original_length
    )
