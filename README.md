# DGentic

DGentic is an advanced autonomous AI agent platform concept focused on local and external model orchestration, dynamic sub-agent spawning, guarded system access, persistent memory, reusable tools, and developer-facing interfaces.

The current repository contains the project specification, planning documents, and a backend MVP surface for orchestrator planning, deterministic execution runs, guardrail checks, provider routing, agent briefs, memory records, tool manifests, session summaries, and event logs.

## Documentation

- [Project goal](docs/DGentic-goal.md)
- [Documentation index](docs/README.md)
- [Agile task plan](docs/planning/agile-task-plan.md)
- [Project progress log](docs/progress/project-progress-log.md)
- [How to use DGentic](docs/how-to/using-dgentic.md)
- [Developer setup](docs/how-to/developer-setup.md)
- [Repository architecture](docs/architecture/repository-architecture.md)
- [Release distribution](docs/how-to/release-distribution.md)
- [0.1.0 release notes](docs/releases/0.1.0.md)

## Quick Start

Install dependencies:

```powershell
uv sync --dev
```

Run the backend:

```powershell
uv run uvicorn dgentic.main:app --reload --app-dir src
```

Or use the installed command after package installation:

```powershell
dgentic-server --host 127.0.0.1 --port 8000
```

Run tests:

```powershell
uv run pytest
```

Run all quality checks:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## How To Use DGentic

DGentic is in backend MVP development. The current API is useful for exercising contracts and sprint slices, while provider integrations, durable persistence, real tool execution, frontend UI, and VS Code extension work continue.

### Review The Product Goal

Start with [docs/DGentic-goal.md](docs/DGentic-goal.md). It describes the intended platform capabilities, architecture, interface ecosystem, security model, and configuration surface.

### Plan Implementation Work

Use [docs/planning/agile-task-plan.md](docs/planning/agile-task-plan.md) as the backlog and sprint planning source. The plan is organized into epics, user stories, acceptance criteria, and milestone phases.

### Track Project Progress

Use [docs/progress/project-progress-log.md](docs/progress/project-progress-log.md) to record decisions, completed work, blockers, and next steps after each meaningful project update.

For more detail, use [docs/how-to/using-dgentic.md](docs/how-to/using-dgentic.md).

### Current Backend APIs

The backend currently exposes:

- `GET /` and `GET /health` for service status.
- `POST /tasks/plan` for deterministic starter task planning.
- `POST /tasks/execute` for deterministic plan execution runs.
- `POST /guardrails/filesystem` and `POST /guardrails/commands` for policy checks.
- `GET /providers`, `GET /providers/{provider_id}/health`, and `POST /routing/decide` for provider routing contracts.
- `POST /agents`, `GET /agents`, and `POST /agents/reconcile` for sub-agent lifecycle contracts.
- `POST /memory` and `POST /memory/search` for in-memory retrieval contracts.
- `POST /tools` and `GET /tools` for local tool manifest registration.
- `POST /sessions/summary`, `GET /sessions/summary`, and `GET /logs` for session and observability contracts.

### Add New Documentation

Place new documentation under `docs/` using focused subdirectories:

- `docs/planning/` for roadmap, sprint, and backlog documents.
- `docs/progress/` for progress logs, status updates, and decision records.
- `docs/architecture/` for system design and technical diagrams.
- `docs/how-to/` for usage, setup, and operational guides.

When implementation changes behavior, update the README plus the relevant document in `docs/` in the same change. At minimum, update the progress log for every meaningful sprint or release change.

### Future Runtime Usage

Once implemented, DGentic should be used through one or more supported interfaces:

1. Start the DGentic backend orchestrator.
2. Configure local model runtimes such as Ollama or LM Studio.
3. Add external provider credentials through the secure settings layer.
4. Set the workspace `rootDir` for guarded file and CLI access.
5. Submit a task through the chat interface, CLI, API, or VS Code extension.
6. Review the orchestrator plan, approve restricted actions, and inspect sub-agent progress.
7. Export or persist the session summary, created tools, and memory updates.

## Current Status

Status: backend MVP sprint surface started.

The FastAPI backend now includes core Pydantic schemas, deterministic planning and execution endpoints, guardrail policy checks, provider routing placeholders, sub-agent contracts, in-memory memory and tool registries, session summaries, event logs, and backend tests. Remaining work includes durable persistence, real provider adapters, approval workflow enforcement, controlled tool execution, semantic retrieval, web UI, and VS Code extension work.
