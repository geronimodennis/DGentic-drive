# DGentic

DGentic is an advanced autonomous AI agent platform concept focused on local and external model orchestration, dynamic sub-agent spawning, guarded system access, persistent memory, reusable tools, and developer-facing interfaces.

The current repository contains the project specification, planning documents, and a backend MVP surface for orchestrator planning, deterministic execution runs, guardrail checks, guarded text file operations, guarded CLI execution and approvals, asynchronous CLI runs with polling and cancellation, configurable command policy rules with agent-role scoping, controlled and audited command environment overrides, local provider probes and generation calls, scored provider routing, agent lifecycle tracking, memory records, dynamically generated and executable local tools, tool governance, session summaries, event logs, and local JSON state persistence.

## Documentation

- [Project goal](docs/DGentic-goal.md)
- [Documentation index](docs/README.md)
- [Agentic tasking and workflows](docs/agentic-workflows/README.md)
- [Agent role boundary rules](docs/agentic-workflows/governance/role-boundaries.md)
- [Agile task plan](docs/planning/agile-task-plan.md)
- [Project progress log](docs/progress/project-progress-log.md)
- [How to use DGentic](docs/how-to/using-dgentic.md)
- [Developer setup](docs/how-to/developer-setup.md)
- [Repository architecture](docs/architecture/repository-architecture.md)
- [Release distribution](docs/how-to/release-distribution.md)
- [0.2.5 release notes](docs/releases/0.2.5.md)
- [0.2.4 release notes](docs/releases/0.2.4.md)
- [0.2.3 release notes](docs/releases/0.2.3.md)
- [0.2.2 release notes](docs/releases/0.2.2.md)
- [0.2.1 release notes](docs/releases/0.2.1.md)
- [0.2.0 release notes](docs/releases/0.2.0.md)
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
- `GET /tasks/plans` for persisted task plan history.
- `POST /tasks/execute` for deterministic plan execution runs.
- `GET /tasks/runs` for persisted execution run history.
- `POST /guardrails/filesystem` and `POST /guardrails/commands` for policy checks.
- `POST /filesystem/read` and `POST /filesystem/write` for policy-enforced UTF-8 text file operations inside `rootDir`.
- `POST /cli/policy/rules`, `GET /cli/policy/rules`, and `PATCH /cli/policy/rules/{rule_id}` for persisted CLI allow, approval, and block rules with executable, exact-command, contains, argument-aware matching, and optional agent-role scoping.
- `POST /cli/execute`, `POST /cli/runs`, `GET /cli/runs`, `GET /cli/runs/{run_id}`, `POST /cli/runs/{run_id}/cancel`, `POST /cli/approvals`, `POST /cli/approvals/{approval_id}/approve`, `POST /cli/approvals/{approval_id}/deny`, and `POST /cli/approvals/{approval_id}/execute` for policy-enforced command execution, asynchronous command runs, polling, cancellation, approvals, run history, agent/task context metadata, and auditable environment override keys.
- `GET /providers`, `GET /providers/{provider_id}/health`, `POST /providers/generate`, and `POST /routing/decide` for Ollama/LM Studio probes, generation calls, and scored provider routing.
- `POST /agents`, `GET /agents`, `GET /agents/{agent_id}`, `GET /agents/{agent_id}/children`, `PATCH /agents/{agent_id}/status`, and `POST /agents/reconcile` for sub-agent lifecycle contracts.
- `POST /memory` and `POST /memory/search` for in-memory retrieval contracts.
- `POST /api/v1/memory/metadata`, `GET /api/v1/memory/metadata`, `GET /api/v1/memory/metadata/{metadata_id}`, `PATCH /api/v1/memory/metadata/{metadata_id}`, and `DELETE /api/v1/memory/metadata/{metadata_id}` for SQLAlchemy-backed metadata index CRUD.
- `POST /api/v1/memory/retrieve/hybrid`, `POST /api/v1/memory/retrieve/vector`, and `GET /api/v1/memory/retrieve/metadata` for dependency-light metadata, hybrid, and vector retrieval service contracts.
- `POST /tools`, `POST /tools/generate`, `POST /tools/{name}/execute`, `GET /tools`, and `PATCH /tools/{name}/governance` for local tool registration, generation, execution, listing, and deprecation/disable governance.
- `POST /api/v1/tools/registry`, `GET /api/v1/tools/registry`, `GET /api/v1/tools/registry/{tool_id}`, `POST /api/v1/tools/registry/check-duplicate`, `POST /api/v1/tools/registry/{tool_id}/usage`, and `POST /api/v1/tools/registry/{tool_id}/deprecate` for SQLAlchemy-backed tool registry services.
- `POST /sessions/summary`, `GET /sessions/summary`, and `GET /logs` for session and observability contracts.

Local state is stored under `.dgentic/` by default and is ignored by Git. Override it with `DGENTIC_DATA_DIR`.

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

Status: backend MVP sprint surface active.

README status policy: keep this section updated after every sprint, release, or meaningful implementation change. Always list implemented features, partially implemented features, and features that are not yet implemented.

### Implemented

- Core FastAPI backend application, Pydantic schemas, health checks, and backend test baseline.
- Deterministic task planning and execution run APIs with local JSON persistence.
- Guardrail policy checks for filesystem and command access.
- Guarded UTF-8 text file read/write operations inside `rootDir`.
- Guarded CLI execution with approvals, approval queue, approve/deny/execute endpoints, run history, output redaction/truncation, asynchronous run polling, and process-local cancellation.
- Persisted CLI command policy rules with executable, exact-command, contains, argument-aware, and agent-role scoped matching.
- Shell-wrapper command inspection for common wrappers such as `cmd /c`, `sh -c`, and PowerShell command invocations.
- Controlled CLI command environment overrides with blocked sensitive runtime keys and audited environment key metadata.
- Ollama and LM Studio health/model probes, local generation calls, and scored provider routing.
- Sub-agent lifecycle tracking, parent-child relationships, status updates, and reconciliation contracts.
- Dynamic local tool generation and execution under `localmcp/`, tool registry persistence, governance status, duplicate detection, and reliability counters.
- Memory records, session summaries, event logs, and local JSON state persistence for MVP workflows.
- SQLAlchemy metadata indexing with CRUD APIs, deterministic hash embeddings, metadata fallback hybrid retrieval, stored vector retrieval, and focused retrieval/API tests.
- Agentic workflow documentation, role files, sprint lifecycle rules, release workflow, strict role write-boundary governance, and mandatory checklist/progress-update governance.
- Release distribution process with versioned release notes and zip bundles.

### Partially Implemented

- CLI integration: approvals, policy rules, polling, cancellation, context-aware rules, and environment controls exist; streaming output, restart-resilient process supervision, stale-running reconciliation, broader Windows/POSIX parsing validation, and approval/environment review UX remain.
- Filesystem runtime: guarded UTF-8 text read/write exists; binary operations, deletes, moves, richer workflows, and stronger permission granularity remain.
- Provider system: Ollama and LM Studio runtime calls exist; external provider adapters, secure credential storage, rate-limit handling, and streaming generation remain.
- Memory and retrieval: memory record storage, text/tag search, SQLAlchemy metadata index services, metadata CRUD routes, deterministic semantic retrieval fallback, stored vector retrieval, and retrieval API tests exist; production vector backend, compression, performance validation, and long-term memory lifecycle management remain production follow-up work.
- Tool runtime: local tool generation, execution, governance, reliability tracking, SQLAlchemy tool registry services, duplicate checks, usage tracking, and registry routes exist; stronger sandbox isolation, permission enforcement depth, generated-tool registry integration, and production-safe dependency isolation remain.
- Agent orchestration: lifecycle contracts and documentation exist; autonomous execution coordination, machine-readable role-boundary enforcement, and production multi-agent scheduling remain.
- Persistence: local JSON collections and SQLite-compatible SQLAlchemy service prototypes exist; production database support, migrations, indexing, concurrency controls, and backup/restore remain.

### Not Yet Implemented

- Web frontend/dashboard.
- VS Code extension.
- Dedicated CLI client interface.
- Interactive approval UI.
- Production deployment infrastructure and CI/CD pipeline.
- External AI provider adapters beyond current local-provider runtime contracts.
- Production authentication, authorization, secret management, and encrypted credential storage.
- Network/domain guardrails.
- Full autonomous backlog management and sprint execution inside the backend runtime.
- Runtime monitoring, metrics, alerting, and rollback automation.
