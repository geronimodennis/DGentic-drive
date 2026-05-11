"""FastAPI routes for metadata index, retrieval, and SQLAlchemy tool registry APIs."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from dgentic.database import get_db_session
from dgentic.memory.compression_service import MemoryCompressionService
from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.lifecycle_service import MemoryLifecycleService
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.models import MemoryMetadata
from dgentic.memory.retrieval_service import RetrievalService
from dgentic.memory.schemas import (
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    MemoryCompressionRequest,
    MemoryCompressionResponse,
    MemoryLifecycleRequest,
    MemoryLifecycleResponse,
    MetadataCreateRequest,
    MetadataListResponse,
    MetadataResponse,
    ToolManifestListResponse,
    ToolManifestResponse,
    ToolRegistryCreateRequest,
    ToolUsageRequest,
)
from dgentic.tools.registry_service import ToolRegistryService

router = APIRouter()
ORCHESTRATION_MEMORY_CATEGORY = "orchestration_context"


def get_db() -> Generator[Session]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


DBSession = Annotated[Session, Depends(get_db)]


def _request_actor(request: Request) -> str | None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return None
    return principal.actor_id


def _request_is_admin(request: Request) -> bool:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return True
    return bool(set(principal.capabilities) & {"admin", "*"})


def _is_orchestration_memory_category(category: object) -> bool:
    return isinstance(category, str) and category.strip().lower() == ORCHESTRATION_MEMORY_CATEGORY


def _metadata_is_visible(metadata: MemoryMetadata | None, request: Request) -> bool:
    if metadata is None or not _is_orchestration_memory_category(metadata.category):
        return True
    return _request_is_admin(request) or metadata.owner_agent == _request_actor(request)


def _visible_metadata_items(
    items: list[MemoryMetadata],
    request: Request,
) -> list[MemoryMetadata]:
    return [item for item in items if _metadata_is_visible(item, request)]


def _reject_public_orchestration_metadata_write(category: object) -> None:
    if _is_orchestration_memory_category(category):
        raise HTTPException(
            status_code=403,
            detail="Orchestration shared-memory metadata is service-authored.",
        )


def _reject_orchestration_context_bulk_mutation(
    category: str | None,
    request: Request,
) -> None:
    if _request_is_admin(request):
        return
    if category is None or _is_orchestration_memory_category(category):
        raise HTTPException(
            status_code=403,
            detail="Bulk memory mutation that may target orchestration context requires admin.",
        )


def _filter_visible_retrieval_results(
    results,
    session: Session,
    request: Request,
):
    if _request_is_admin(request):
        return results
    metadata_ids = [str(result.metadata_id) for result in results]
    if not metadata_ids:
        return results
    metadata_by_id = {
        str(metadata.id): metadata
        for metadata in session.query(MemoryMetadata)
        .filter(MemoryMetadata.id.in_(metadata_ids))
        .all()
    }
    return [
        result
        for result in results
        if _metadata_is_visible(metadata_by_id.get(str(result.metadata_id)), request)
    ]


@router.post(
    "/api/v1/memory/metadata",
    response_model=MetadataResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_metadata(request: MetadataCreateRequest, session: DBSession):
    _reject_public_orchestration_metadata_write(request.category)
    service = MetadataService(session)
    return service.create(request)


@router.post("/api/v1/memory/lifecycle/preview", response_model=MemoryLifecycleResponse)
def preview_memory_lifecycle(
    request: MemoryLifecycleRequest,
    http_request: Request,
    session: DBSession,
) -> MemoryLifecycleResponse:
    service = MemoryLifecycleService(session)
    decisions = service.preview(request)
    if not _request_is_admin(http_request):
        metadata_by_id = {
            str(metadata.id): metadata
            for metadata in session.query(MemoryMetadata)
            .filter(MemoryMetadata.id.in_([str(decision.metadata_id) for decision in decisions]))
            .all()
        }
        decisions = [
            decision
            for decision in decisions
            if _metadata_is_visible(metadata_by_id.get(str(decision.metadata_id)), http_request)
        ]
    return MemoryLifecycleResponse(decisions=decisions, total=len(decisions), applied=False)


@router.post("/api/v1/memory/lifecycle/apply", response_model=MemoryLifecycleResponse)
def apply_memory_lifecycle(
    request: MemoryLifecycleRequest,
    http_request: Request,
    session: DBSession,
) -> MemoryLifecycleResponse:
    _reject_orchestration_context_bulk_mutation(request.category, http_request)
    service = MemoryLifecycleService(session)
    decisions = service.apply(request)
    return MemoryLifecycleResponse(decisions=decisions, total=len(decisions), applied=True)


@router.post("/api/v1/memory/compression/preview", response_model=MemoryCompressionResponse)
def preview_memory_compression(
    request: MemoryCompressionRequest,
    http_request: Request,
    session: DBSession,
) -> MemoryCompressionResponse:
    embedding_service = EmbeddingService(session)
    service = MemoryCompressionService(session, embedding_service)
    candidates = service.preview(request)
    if not _request_is_admin(http_request):
        metadata_by_id = {
            str(metadata.id): metadata
            for metadata in session.query(MemoryMetadata)
            .filter(MemoryMetadata.id.in_([str(candidate.metadata_id) for candidate in candidates]))
            .all()
        }
        candidates = [
            candidate
            for candidate in candidates
            if _metadata_is_visible(metadata_by_id.get(str(candidate.metadata_id)), http_request)
        ]
    return MemoryCompressionResponse(candidates=candidates, total=len(candidates), applied=False)


@router.post("/api/v1/memory/compression/apply", response_model=MemoryCompressionResponse)
def apply_memory_compression(
    request: MemoryCompressionRequest,
    http_request: Request,
    session: DBSession,
) -> MemoryCompressionResponse:
    _reject_orchestration_context_bulk_mutation(request.category, http_request)
    embedding_service = EmbeddingService(session)
    service = MemoryCompressionService(session, embedding_service)
    candidates = service.apply(request)
    return MemoryCompressionResponse(candidates=candidates, total=len(candidates), applied=True)


@router.get("/api/v1/memory/metadata/{metadata_id}", response_model=MetadataResponse)
def get_metadata(metadata_id: UUID, request: Request, session: DBSession):
    service = MetadataService(session)
    metadata = service.get_by_id(metadata_id, update_access=False)
    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")
    if not _metadata_is_visible(metadata, request):
        raise HTTPException(status_code=404, detail="Metadata not found")
    return service.get_by_id(metadata_id)


@router.get("/api/v1/memory/metadata", response_model=MetadataListResponse)
def list_metadata(
    request: Request,
    session: DBSession,
    entity_type: str | None = None,
    category: str | None = None,
    tags: Annotated[list[str] | None, Query()] = None,
    indexed: bool | None = None,
    retention_policy: str | None = None,
    lifecycle_state: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    service = MetadataService(session)
    owner_agent = (
        _request_actor(request)
        if not _request_is_admin(request) and _is_orchestration_memory_category(category)
        else None
    )
    items, total = service.list_by_filters(
        entity_type=entity_type,
        category=category,
        tags=tags,
        indexed=indexed,
        retention_policy=retention_policy,
        lifecycle_state=lifecycle_state,
        owner_agent=owner_agent,
        limit=limit,
        offset=offset,
    )
    items = _visible_metadata_items(items, request)
    total = len(items) if not _request_is_admin(request) and category is None else total
    return MetadataListResponse(items=items, total=total, page=(offset // limit) + 1)


@router.patch("/api/v1/memory/metadata/{metadata_id}", response_model=MetadataResponse)
def update_metadata(metadata_id: UUID, updates: dict, session: DBSession):
    service = MetadataService(session)
    existing = service.get_by_id(metadata_id, update_access=False)
    if not existing:
        raise HTTPException(status_code=404, detail="Metadata not found")
    _reject_public_orchestration_metadata_write(existing.category)
    _reject_public_orchestration_metadata_write(updates.get("category"))
    metadata = service.update(metadata_id, **updates)
    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")
    return metadata


@router.delete("/api/v1/memory/metadata/{metadata_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_metadata(metadata_id: UUID, session: DBSession):
    service = MetadataService(session)
    existing = service.get_by_id(metadata_id, update_access=False)
    if not existing:
        raise HTTPException(status_code=404, detail="Metadata not found")
    _reject_public_orchestration_metadata_write(existing.category)
    if not service.delete(metadata_id):
        raise HTTPException(status_code=404, detail="Metadata not found")


@router.post("/api/v1/memory/retrieve/hybrid", response_model=HybridRetrievalResponse)
def hybrid_search(request: HybridRetrievalRequest, http_request: Request, session: DBSession):
    embedding_service = EmbeddingService(session)
    retrieval_service = RetrievalService(session, embedding_service)
    results, query_time_ms = retrieval_service.hybrid_search(request)
    results = _filter_visible_retrieval_results(results, session, http_request)
    return HybridRetrievalResponse(
        results=results,
        total=len(results),
        query_time_ms=query_time_ms,
    )


@router.post("/api/v1/memory/retrieve/vector", response_model=HybridRetrievalResponse)
def vector_search(
    request: Request,
    session: DBSession,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.7,
    include_inactive: bool = False,
):
    embedding_service = EmbeddingService(session)
    retrieval_service = RetrievalService(session, embedding_service)
    results, query_time_ms = retrieval_service.vector_search(
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
        include_inactive=include_inactive,
    )
    results = _filter_visible_retrieval_results(results, session, request)
    return HybridRetrievalResponse(
        results=results,
        total=len(results),
        query_time_ms=query_time_ms,
    )


@router.get("/api/v1/memory/retrieve/metadata", response_model=HybridRetrievalResponse)
def metadata_search(
    request: Request,
    session: DBSession,
    category: str | None = None,
    limit: int = 20,
    include_inactive: bool = False,
):
    embedding_service = EmbeddingService(session)
    retrieval_service = RetrievalService(session, embedding_service)
    results, query_time_ms = retrieval_service.metadata_search(
        category=category,
        limit=limit,
        include_inactive=include_inactive,
    )
    results = _filter_visible_retrieval_results(results, session, request)
    return HybridRetrievalResponse(
        results=results,
        total=len(results),
        query_time_ms=query_time_ms,
    )


@router.post(
    "/api/v1/tools/registry",
    response_model=ToolManifestResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_tool(request: ToolRegistryCreateRequest, session: DBSession):
    service = ToolRegistryService(session)
    return service.register_tool(request)


@router.get("/api/v1/tools/registry", response_model=ToolManifestListResponse)
def list_tools(
    session: DBSession,
    tags: str | None = None,
    permission_level: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    service = ToolRegistryService(session)
    tag_list = tags.split(",") if tags else None
    tools, total = service.list_tools(
        tags=tag_list,
        permission_level=permission_level,
        limit=limit,
        offset=offset,
    )
    return ToolManifestListResponse(items=tools, total=total, page=(offset // limit) + 1)


@router.post("/api/v1/tools/registry/check-duplicate", response_model=DuplicateCheckResponse)
def check_duplicate(request: DuplicateCheckRequest, session: DBSession):
    service = ToolRegistryService(session)
    result = service.check_duplicate(request)
    return DuplicateCheckResponse(**result)


@router.get("/api/v1/tools/registry/{tool_id}", response_model=ToolManifestResponse)
def get_tool(tool_id: UUID, session: DBSession):
    service = ToolRegistryService(session)
    tool = service.get_tool_by_id(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.post("/api/v1/tools/registry/{tool_id}/usage", response_model=ToolManifestResponse)
def record_tool_usage(tool_id: UUID, request: ToolUsageRequest, session: DBSession):
    service = ToolRegistryService(session)
    tool = service.record_usage(tool_id, request)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.post("/api/v1/tools/registry/{tool_id}/deprecate", response_model=ToolManifestResponse)
def deprecate_tool(tool_id: UUID, session: DBSession):
    service = ToolRegistryService(session)
    tool = service.deprecate_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool
