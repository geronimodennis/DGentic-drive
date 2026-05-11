# Sprint 6: Memory System Architecture

Date: 2026-05-07
Architect: [Architect]
Status: APPROVED ARCHITECTURE DRAFT; MVP reconciliation uses SQLite-compatible SQLAlchemy storage first.

## Overview

This document defines the architecture for Stories 6.1 (Metadata Index) and 6.2 (Hybrid Retrieval) in Sprint 6.

## 1. Data Models

### Metadata Schema

```python
# Memory metadata record
metadata {
  id: UUID (primary key)
  entity_type: "skill" | "memory" | "tool" | "pattern" (enum)
  entity_id: string (reference to actual entity)
  tags: list[string]
  category: string
  description: string
  created_at: datetime
  updated_at: datetime
  last_accessed_at: datetime
  access_count: int
  relevance_score: float (0-1, user-defined)
  embedding_id: UUID (reference to vector)
  retention_policy: "permanent" | "automatic" | "manual" (enum)
  owner_agent: string (optional)
  indexed: boolean
  lifecycle_state: "active" | "promoted" | "archived" | "soft_pruned"
  lifecycle_reason: string (optional)
  lifecycle_updated_at: datetime (optional)
  archived_at: datetime (optional)
  pruned_at: datetime (optional)
  expires_at: datetime (optional)
  freshness_score: float (0-1)
  last_compacted_at: datetime (optional)
}
```

### Vector Embedding Schema

```python
# Vector embeddings for semantic search
vector_embedding {
  id: UUID (primary key)
  metadata_id: UUID (foreign key)
  model: string (embedding model name: "all-MiniLM-L6-v2", etc.)
  embedding: vector[384] (float32 array)
  created_at: datetime
}
```

### Tool Registry Schema

```python
# Tool manifest and registry
tool_manifest {
  id: UUID (primary key)
  tool_name: string (unique)
  version: string (semantic versioning)
  source_path: string (relative to rootDir/localmcp/)
  interface_signature: string (JSON schema hash)
  permission_level: "autopilot_safe" | "approval_required" (enum)
  tags: list[string]
  description: string
  created_at: datetime
  updated_at: datetime
  created_by_agent: string
  usage_count: int
  success_count: int
  failure_count: int
  last_used_at: datetime
  reliability_score: float (0-1, calculated)
  deprecated: boolean
  metadata_id: UUID (reference for retrieval indexing)
}
```

## 2. Database Selection: PostgreSQL + pgvector

Implementation note: the reconciled MVP service layer currently uses SQLite-compatible SQLAlchemy models and a SQLite JSON-vector backend in `.dgentic/dgentic.db` so tests and local development do not require PostgreSQL or pgvector. PostgreSQL plus pgvector remains the production-oriented target pending production driver packaging and migration rollout.

**Rationale:**
- PostgreSQL provides ACID transactions and reliability
- pgvector extension enables native vector operations
- Supports both structured (metadata) and unstructured (embeddings) data
- Open-source, cost-effective, self-hostable
- Strong Python support via SQLAlchemy ORM

**Alternatives Considered:**
- Pinecone: Fully managed but high cost and vendor lock-in
- Weaviate: Strong but adds deployment complexity
- Milvus: Open-source but requires separate service

## 3. API Contracts

### Story 6.1: Metadata Index Service

**Base Path:** `/api/v1/memory/metadata`

#### Create Metadata Entry
```
POST /api/v1/memory/metadata
Request:
{
  "entity_type": "skill",
  "entity_id": "skill-123",
  "tags": ["search", "filtering"],
  "category": "retrieval",
  "description": "Metadata indexing for skills",
  "relevance_score": 0.8,
  "retention_policy": "permanent"
}

Response (201):
{
  "id": "meta-uuid",
  "entity_type": "skill",
  "entity_id": "skill-123",
  "tags": ["search", "filtering"],
  "category": "retrieval",
  "description": "Metadata indexing for skills",
  "created_at": "2026-05-07T10:00:00Z",
  "access_count": 0,
  "indexed": false
}
```

#### List Metadata (with Filters)
```
GET /api/v1/memory/metadata?category=retrieval&entity_type=skill&tags=search
Response (200):
{
  "items": [
    {
      "id": "meta-uuid",
      "entity_type": "skill",
      "tags": ["search", "filtering"],
      "category": "retrieval",
      "access_count": 5,
      "relevance_score": 0.8,
      "indexed": true
    }
  ],
  "total": 1,
  "page": 1
}
```

#### Update Metadata
```
PATCH /api/v1/memory/metadata/{id}
Request:
{
  "tags": ["search", "filtering", "indexing"],
  "relevance_score": 0.9,
  "access_count": 6
}

Response (200): Updated metadata object
```

#### Delete Metadata
```
DELETE /api/v1/memory/metadata/{id}
Response (204): No content
```

### Story 6.2: Hybrid Retrieval Service

**Base Path:** `/api/v1/memory/retrieve`

#### Semantic Search (Vector + Metadata)
```
POST /api/v1/memory/retrieve/hybrid
Request:
{
  "query": "How do I implement semantic search?",
  "entity_types": ["skill", "memory"],
  "tags": ["search"],
  "limit": 10,
  "similarity_threshold": 0.7,
  "metadata_filters": {
    "category": "retrieval",
    "retention_policy": "permanent"
  }
}

Response (200):
{
  "results": [
    {
      "metadata_id": "meta-uuid",
      "entity_type": "skill",
      "entity_id": "skill-456",
      "description": "Vector search implementation",
      "similarity_score": 0.92,
      "metadata_relevance": 0.85,
      "combined_score": 0.89,
      "source": "hybrid_retrieval"
    }
  ],
  "total": 1,
  "query_time_ms": 45
}
```

#### Vector Search Only
```
POST /api/v1/memory/retrieve/vector
Request:
{
  "query": "Semantic search in AI systems",
  "limit": 5,
  "similarity_threshold": 0.7
}
```

#### Metadata Filter Only
```
GET /api/v1/memory/retrieve/metadata?category=retrieval&tags=indexing&limit=20
Response: List of metadata without vector scoring
```

### Sprint 13: Memory Lifecycle Policy

**Base Path:** `/api/v1/memory/lifecycle`

The lifecycle service is SQL-backed and deterministic. It can preview or apply lifecycle decisions for metadata records using age, retention policy, expiry, relevance, and access count. Preview never mutates data. Apply mutates only `promote`, `archive`, and `soft_prune`; `compress_candidate` is executed through the separate compression endpoints.

```
POST /api/v1/memory/lifecycle/preview
POST /api/v1/memory/lifecycle/apply
Request:
{
  "category": "planning",
  "archive_after_days": 90,
  "soft_prune_after_days": 365,
  "reference_time": "2027-01-01T00:00:00Z"
}

Response (200):
{
  "decisions": [
    {
      "metadata_id": "meta-uuid",
      "entity_type": "memory",
      "entity_id": "memory-1",
      "retention_policy": "automatic",
      "current_state": "active",
      "recommended_action": "archive",
      "reason": "Memory is stale and eligible for archival.",
      "freshness_score": 0.671,
      "last_accessed_at": null
    }
  ],
  "total": 1,
  "applied": false
}
```

Hybrid, vector, and metadata retrieval exclude `archived` and `soft_pruned` metadata by default. Callers can request inactive metadata with `include_inactive` for review or maintenance workflows.

### Sprint 13: Deterministic Metadata Compression

**Base Path:** `/api/v1/memory/compression`

Compression is deterministic and extractive for the current SQL metadata surface. It shortens long metadata descriptions that meet age/access thresholds, records `last_compacted_at`, updates lifecycle audit fields, preserves lifecycle state, and reindexes an existing stored embedding. It does not call an external LLM and does not summarize legacy JSON `MemoryRecord.content`.

```
POST /api/v1/memory/compression/preview
POST /api/v1/memory/compression/apply
Request:
{
  "category": "planning",
  "compress_after_days": 30,
  "compress_access_count_threshold": 10,
  "max_summary_chars": 240,
  "reference_time": "2027-01-01T00:00:00Z"
}
```

### Story 7.1: Tool Registry API

**Base Path:** `/api/v1/tools/registry`

#### Register Tool
```
POST /api/v1/tools/registry
Request:
{
  "tool_name": "my-custom-tool",
  "version": "1.0.0",
  "source_path": "localmcp/my-custom-tool",
  "interface_signature": "sha256:abc123...",
  "permission_level": "approval_required",
  "tags": ["custom", "automation"],
  "description": "Custom tool for task automation",
  "created_by_agent": "Dev1"
}

Response (201):
{
  "id": "tool-uuid",
  "tool_name": "my-custom-tool",
  "version": "1.0.0",
  "permission_level": "approval_required",
  "usage_count": 0,
  "success_count": 0,
  "failure_count": 0,
  "reliability_score": 1.0,
  "created_at": "2026-05-07T10:05:00Z"
}
```

#### Detect Duplicate Tools
```
POST /api/v1/tools/registry/check-duplicate
Request:
{
  "tool_name": "my-custom-tool",
  "interface_signature": "sha256:abc123...",
  "tags": ["custom"]
}

Response (200):
{
  "is_duplicate": false,
  "similar_tools": [],
  "recommendation": "Tool is unique. Safe to register."
}
```

#### List Tools with Filters
```
GET /api/v1/tools/registry?tags=automation&deprecated=false
Response (200):
{
  "items": [
    {
      "id": "tool-uuid",
      "tool_name": "my-custom-tool",
      "version": "1.0.0",
      "permission_level": "approval_required",
      "usage_count": 5,
      "reliability_score": 0.98
    }
  ],
  "total": 1
}
```

#### Record Tool Usage
```
POST /api/v1/tools/registry/{id}/usage
Request:
{
  "status": "success" | "failure",
  "execution_time_ms": 250,
  "error": null
}

Response (200): Updated tool with reliability_score recalculated
```

## 4. Database Schema (SQL)

```sql
-- Metadata Index Table
CREATE TABLE memory_metadata (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type VARCHAR(50) NOT NULL CHECK (entity_type IN ('skill', 'memory', 'tool', 'pattern')),
  entity_id VARCHAR(255) NOT NULL,
  tags TEXT[] DEFAULT ARRAY[]::TEXT[],
  category VARCHAR(100),
  description TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_accessed_at TIMESTAMP,
  access_count INTEGER DEFAULT 0,
  relevance_score FLOAT DEFAULT 0.5,
  embedding_id UUID,
  retention_policy VARCHAR(50) DEFAULT 'automatic',
  owner_agent VARCHAR(100),
  indexed BOOLEAN DEFAULT FALSE,
  UNIQUE(entity_type, entity_id)
);

CREATE INDEX idx_metadata_entity ON memory_metadata(entity_type, entity_id);
CREATE INDEX idx_metadata_tags ON memory_metadata USING GIN(tags);
CREATE INDEX idx_metadata_category ON memory_metadata(category);
CREATE INDEX idx_metadata_indexed ON memory_metadata(indexed);

-- Vector Embeddings Table
CREATE TABLE vector_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  metadata_id UUID NOT NULL REFERENCES memory_metadata(id) ON DELETE CASCADE,
  model VARCHAR(255) NOT NULL,
  embedding vector(384) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(metadata_id, model)
);

CREATE INDEX idx_embedding_metadata ON vector_embeddings(metadata_id);
CREATE INDEX idx_embedding_model ON vector_embeddings(model);

-- Tool Registry Table
CREATE TABLE tool_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_name VARCHAR(255) NOT NULL UNIQUE,
  version VARCHAR(50) NOT NULL,
  source_path VARCHAR(500) NOT NULL,
  interface_signature VARCHAR(255) NOT NULL,
  permission_level VARCHAR(50) NOT NULL CHECK (permission_level IN ('autopilot_safe', 'approval_required')),
  tags TEXT[] DEFAULT ARRAY[]::TEXT[],
  description TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by_agent VARCHAR(100),
  usage_count INTEGER DEFAULT 0,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  last_used_at TIMESTAMP,
  reliability_score FLOAT DEFAULT 1.0,
  deprecated BOOLEAN DEFAULT FALSE,
  metadata_id UUID REFERENCES memory_metadata(id) ON DELETE SET NULL,
  UNIQUE(tool_name, version)
);

CREATE INDEX idx_tool_name ON tool_registry(tool_name);
CREATE INDEX idx_tool_tags ON tool_registry USING GIN(tags);
CREATE INDEX idx_tool_deprecated ON tool_registry(deprecated);
CREATE INDEX idx_tool_permission ON tool_registry(permission_level);
```

## 5. Embedding Model Selection

**MVP default:** `dgentic-hash-embedding-v1`

Sprint 7 uses a deterministic hashed bag-of-words embedding as the default semantic retrieval path. It produces 384-dimensional vectors locally without downloading models or requiring heavyweight dependencies, which keeps tests and local MVP usage reliable.

**Optional production path:** `sentence-transformers/all-MiniLM-L6-v2`

Operators can still configure a sentence-transformers model name when the optional dependency is installed. PostgreSQL plus pgvector and a production embedding model remain the target for a production retrieval backend.

**Vector backend boundary:** Sprint 13 adds a `VectorBackend` contract and `SQLiteVectorBackend` default implementation. Retrieval code now stores, fetches, deletes, and searches embeddings through that backend boundary. The current backend still scans JSON vectors in SQLite for local MVP compatibility; pgvector can replace the backend behind the same retrieval contract in a later production slice.

**Rationale:**
- Default retrieval is dependency-light and deterministic for CI and local development.
- 384-dimensional vectors keep the MVP compatible with the planned pgvector shape.
- Optional sentence-transformers support preserves a stronger semantic path without making normal installs download model packages.
- Embeddings remain local; no external API calls are required.

## 6. Implementation Libraries

```python
# Core MVP dependency
"sqlalchemy>=2.0.0,<3.0.0"           # ORM and database access
```

Future production dependencies under review:

```python
"alembic>=1.13.0,<2.0.0"               # Database migrations
"sentence-transformers>=2.2.0,<3.0.0"  # Optional embedding generation
"pgvector>=0.2.0,<1.0.0"               # PostgreSQL vector support
"psycopg[binary]>=3.1.0,<4.0.0"        # PostgreSQL driver
```

## 7. Service Layer Architecture

```
dgentic/
├── memory/
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy ORM models
│   ├── compression_service.py # Deterministic metadata compression
│   ├── metadata_service.py    # CRUD for metadata
│   ├── retrieval_service.py   # Hybrid search logic
│   ├── embedding_service.py   # Vector generation
│   ├── vector_backend.py      # Vector backend contract/default
│   └── schemas.py             # Pydantic request/response models
├── tools/
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy ORM for registry
│   ├── registry_service.py    # Tool registration & lookup
│   ├── duplicate_detector.py  # Signature comparison
│   └── schemas.py             # Pydantic models
├── api/
│   ├── routes.py              # Add /memory and /tools endpoints
│   └── dependencies.py        # Database session injection
└── database.py                # SQLAlchemy session factory
```

## 8. Acceptance Criteria Mapping

**Story 6.1:** ✓ Metadata schema defined | ✓ Database backend selected | ✓ API contracts defined

**Story 6.2:** ✓ Dependency-light vector generation implemented | ✓ Retrieval API defined | ✓ Vector backend abstraction implemented | ✓ Deterministic metadata compression implemented | Full-content summarization remains future work

**Story 7.1:** ✓ Tool manifest schema defined | ✓ API contracts defined | ✓ Duplicate detection endpoint

## 9. Security & Boundary Considerations

- **Filesystem:** Tool registry `source_path` validated against `rootDir/localmcp/` prefix
- **Database Access:** SQLAlchemy sessions scoped to agent context (multi-tenancy ready)
- **Vector Privacy:** Embeddings stored locally; no external API calls
- **Tool Permissions:** Registry enforces approval_required vs autopilot_safe classification

## 10. Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Metadata index CRUD | <50ms | In-memory cache layer optional |
| Metadata filter query | <100ms | Index on tags and category |
| Vector search (top-10) | <100ms | pgvector HNSW index |
| Hybrid retrieval | <200ms | Parallel queries + merge |
| Tool registry lookup | <50ms | Primary key lookup |
| Duplicate detection | <500ms | Signature hashing + comparison |

Baseline performance smoke:
- The SQLite JSON-vector backend has a deterministic smoke test for top-10 vector retrieval over 75 stored embeddings with a generous CI-safe timing budget.
- This is not the production performance target. It is a regression baseline until pgvector search is integrated.

---

## Next: Implementation Begins (Day 2)

Developer and QA ready to start Story 6.1 scaffolding and database migrations.
