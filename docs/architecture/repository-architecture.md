# Repository Architecture

Date created: 2026-05-07

## Purpose

This document defines the initial DGentic repository layout. The structure is intentionally modular so backend, frontend, extension, generated tools, and documentation can evolve independently while sharing the same product direction.

## Current Layout

```text
dgentic/
  docs/
    architecture/
    how-to/
    planning/
    progress/
  localmcp/
  src/
    dgentic/
      api/
      agents.py
      events.py
      execution.py
      guardrails.py
      main.py
      memory.py
      planner.py
      providers.py
      schemas.py
      sessions.py
      settings.py
      tools.py
  tests/
  .env.example
  .gitignore
  pyproject.toml
  README.md
```

## Directory Responsibilities

### `src/dgentic/`

Python backend package for the DGentic orchestrator API.

Current modules:

- `main.py`: FastAPI app factory and application instance.
- `api/routes.py`: HTTP routes for health checks, tasks, guardrails, providers, routing, agents, memory, tools, sessions, and logs.
- `schemas.py`: Pydantic contracts for tasks, execution runs, guardrails, providers, routing, agents, memory, tools, sessions, and logs.
- `planner.py`: Deterministic starter planner used until model-backed planning is implemented.
- `execution.py`: Deterministic plan execution run service for MVP workflow validation.
- `guardrails.py`: Filesystem and CLI policy classification.
- `providers.py`: Provider registry, health checks, and placeholder routing decisions.
- `agents.py`: Sub-agent brief registry and output reconciliation.
- `memory.py`: In-memory memory record indexing and search.
- `tools.py`: Local tool manifest registration.
- `sessions.py`: Session summary registry.
- `events.py`: Central in-memory event log.
- `settings.py`: Environment-based backend settings.

### `tests/`

Automated tests for backend behavior. The current tests validate health checks, task planning, deterministic execution, guardrail checks, provider routing, agent and registry APIs, session summaries, and logs.

### `localmcp/`

Reserved location for future generated reusable tools. DGentic-created tools should eventually live under:

```text
localmcp/[tool_name]/
  manifest.json
  src/
  README.md
```

### `docs/`

Project documentation:

- `planning/`: Agile plans and sprint backlog.
- `progress/`: Project progress log.
- `architecture/`: Technical architecture and design records.
- `how-to/`: Setup, usage, and operations guides.

## Planned Layout Additions

Future milestones should add:

```text
apps/
  web/
extensions/
  vscode/
infra/
scripts/
```

These are intentionally deferred until the backend foundation is stable enough to define real integration contracts.

## Backend API Surface

Current endpoints:

- `GET /`: Service health response.
- `GET /health`: Service health response.
- `POST /tasks/plan`: Creates a structured starter task plan.
- `POST /tasks/execute`: Creates a deterministic execution run from a task plan.
- `POST /guardrails/filesystem`: Evaluates filesystem action policy against `rootDir`.
- `POST /guardrails/commands`: Classifies CLI command risk.
- `GET /providers`: Lists configured provider placeholders.
- `GET /providers/{provider_id}/health`: Returns provider configuration health.
- `POST /routing/decide`: Returns a basic provider routing decision.
- `POST /agents`: Registers a running sub-agent brief.
- `GET /agents`: Lists registered sub-agent briefs.
- `POST /agents/reconcile`: Reconciles sub-agent output reports.
- `POST /memory`: Adds an in-memory memory record.
- `POST /memory/search`: Searches memory records by text and tags.
- `POST /tools`: Registers a local tool manifest.
- `GET /tools`: Lists registered tool manifests.
- `POST /sessions/summary`: Creates a session summary.
- `GET /sessions/summary`: Lists session summaries.
- `GET /logs`: Lists recorded events, optionally filtered by event type.

## Engineering Baseline

Initial tooling:

- Python package manager: `uv`
- Backend framework: FastAPI
- Schema system: Pydantic v2
- Test runner: pytest
- Linter/formatter: Ruff

Quality gates:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`

## Architecture Decisions

- Start with a backend-first monorepo because orchestration, permissions, schemas, and logs define the core product contracts.
- Keep model-provider execution out of the first slice; the initial planner is deterministic and auditable.
- Define Pydantic schemas early so future UI, extension, memory, routing, and tool runtime work can share stable contracts.
- Create `localmcp/` now to reserve the generated-tool boundary without enabling tool execution yet.
- Use in-memory registries for the MVP sprint surface; replace them with durable storage before production use.
- Keep provider adapters as placeholders until guardrails, routing policy, credentials, and audit behavior are ready to harden together.
