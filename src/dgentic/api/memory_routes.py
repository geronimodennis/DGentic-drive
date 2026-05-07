"""FastAPI routes for metadata index, retrieval, and SQLAlchemy tool registry APIs."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from dgentic.database import get_db_session
from dgentic.memory.embedding_service import EmbeddingService
from dgentic.memory.metadata_service import MetadataService
from dgentic.memory.retrieval_service import RetrievalService
from dgentic.memory.schemas import (
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
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


def get_db() -> Generator[Session]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


DBSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/api/v1/memory/metadata",
    response_model=MetadataResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_metadata(request: MetadataCreateRequest, session: DBSession):
    service = MetadataService(session)
    return service.create(request)


@router.get("/api/v1/memory/metadata/{metadata_id}", response_model=MetadataResponse)
def get_metadata(metadata_id: UUID, session: DBSession):
    service = MetadataService(session)
    metadata = service.get_by_id(metadata_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")
    return metadata


@router.get("/api/v1/memory/metadata", response_model=MetadataListResponse)
def list_metadata(
    session: DBSession,
    entity_type: str | None = None,
    category: str | None = None,
    indexed: bool | None = None,
    limit: int = 100,
    offset: int = 0,
):
    service = MetadataService(session)
    items, total = service.list_by_filters(
        entity_type=entity_type,
        category=category,
        indexed=indexed,
        limit=limit,
        offset=offset,
    )
    return MetadataListResponse(items=items, total=total, page=(offset // limit) + 1)


@router.patch("/api/v1/memory/metadata/{metadata_id}", response_model=MetadataResponse)
def update_metadata(metadata_id: UUID, updates: dict, session: DBSession):
    service = MetadataService(session)
    metadata = service.update(metadata_id, **updates)
    if not metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")
    return metadata


@router.delete("/api/v1/memory/metadata/{metadata_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_metadata(metadata_id: UUID, session: DBSession):
    service = MetadataService(session)
    if not service.delete(metadata_id):
        raise HTTPException(status_code=404, detail="Metadata not found")


@router.post("/api/v1/memory/retrieve/hybrid", response_model=HybridRetrievalResponse)
def hybrid_search(request: HybridRetrievalRequest, session: DBSession):
    embedding_service = EmbeddingService(session)
    retrieval_service = RetrievalService(session, embedding_service)
    results, query_time_ms = retrieval_service.hybrid_search(request)
    return HybridRetrievalResponse(
        results=results,
        total=len(results),
        query_time_ms=query_time_ms,
    )


@router.post("/api/v1/memory/retrieve/vector", response_model=HybridRetrievalResponse)
def vector_search(
    session: DBSession,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.7,
):
    embedding_service = EmbeddingService(session)
    retrieval_service = RetrievalService(session, embedding_service)
    results, query_time_ms = retrieval_service.vector_search(
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
    )
    return HybridRetrievalResponse(
        results=results,
        total=len(results),
        query_time_ms=query_time_ms,
    )


@router.get("/api/v1/memory/retrieve/metadata", response_model=HybridRetrievalResponse)
def metadata_search(
    session: DBSession,
    category: str | None = None,
    limit: int = 20,
):
    embedding_service = EmbeddingService(session)
    retrieval_service = RetrievalService(session, embedding_service)
    results, query_time_ms = retrieval_service.metadata_search(
        category=category,
        limit=limit,
    )
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
