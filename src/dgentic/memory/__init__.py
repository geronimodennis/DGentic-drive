"""Memory services and existing MVP memory record registry."""

from datetime import UTC, datetime
from uuid import uuid4

from dgentic.events import event_log
from dgentic.memory.compression_service import MemoryCompressionService
from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.lifecycle_service import MemoryLifecycleService
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.retrieval_service import RetrievalService
from dgentic.memory.vector_backend import SQLiteVectorBackend, VectorBackend
from dgentic.schemas import LogEventType, MemoryQuery, MemoryRecord, MemorySearchResult
from dgentic.storage import JsonCollection

_records = JsonCollection("memory", MemoryRecord)


def add_memory(record: MemoryRecord, *, actor: str | None = None) -> MemoryRecord:
    memory = record.model_copy(
        update={
            "id": record.id or f"memory-{uuid4()}",
            "updated_at": datetime.now(UTC),
        }
    )
    _records.upsert(memory)
    event_log.record(
        LogEventType.memory,
        "Indexed memory record.",
        actor=actor or "system",
        subject_id=memory.id,
        metadata={"tags": memory.tags, "kind": memory.kind},
    )
    return memory


def search_memory(query: MemoryQuery, *, actor: str | None = None) -> list[MemorySearchResult]:
    text = query.text.lower().strip()
    tags = set(query.tags)
    results: list[MemorySearchResult] = []
    for record in _records.list():
        score = 0.0
        if text and (text in record.title.lower() or text in record.content.lower()):
            score += 0.7
        if tags:
            score += 0.3 * (len(tags.intersection(record.tags)) / len(tags))
        if not text and not tags:
            score = record.relevance
        if score > 0:
            results.append(MemorySearchResult(record=record, score=round(score, 3)))
            _records.upsert(record.model_copy(update={"usage_count": record.usage_count + 1}))

    results.sort(key=lambda result: result.score, reverse=True)
    event_log.record(
        LogEventType.memory,
        "Searched memory records.",
        actor=actor or "system",
        metadata={"query": query.model_dump(), "matches": len(results)},
    )
    return results[: query.limit]


__all__ = [
    "EmbeddingService",
    "MemoryCompressionService",
    "MemoryLifecycleService",
    "MetadataService",
    "RetrievalService",
    "SQLiteVectorBackend",
    "VectorBackend",
    "add_memory",
    "search_memory",
]
