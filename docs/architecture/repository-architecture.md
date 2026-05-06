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
      main.py
      planner.py
      schemas.py
      settings.py
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
- `api/routes.py`: HTTP routes for health checks and task planning.
- `schemas.py`: Pydantic contracts for tasks, plans, providers, agents, tools, and logs.
- `planner.py`: Deterministic starter planner used until model-backed planning is implemented.
- `settings.py`: Environment-based backend settings.

### `tests/`

Automated tests for backend behavior. The current tests validate health checks and the task planning endpoint.

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

Initial endpoints:

- `GET /`: Service health response.
- `GET /health`: Service health response.
- `POST /tasks/plan`: Creates a structured starter task plan.

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
