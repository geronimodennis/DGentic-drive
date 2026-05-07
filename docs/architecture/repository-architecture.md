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
      command_policy.py
      events.py
      cli_runtime.py
      execution.py
      guardrails.py
      main.py
      memory.py
      planner.py
      provider_runtime.py
      providers.py
      schemas.py
      sessions.py
      settings.py
      storage.py
      tool_runtime.py
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
- `api/routes.py`: HTTP routes for health checks, tasks, guardrails, CLI policy and approvals, providers, routing, agents, memory, tools, sessions, and logs.
- `schemas.py`: Pydantic contracts for tasks, execution runs, guardrails, CLI policy rules, providers, routing, agents, memory, tools, sessions, and logs.
- `command_policy.py`: Persisted CLI policy rule storage and executable, exact-command, contains, and argument-aware command matching.
- `cli_runtime.py`: CLI approvals, root-bound command execution, output redaction/truncation, and command run history.
- `planner.py`: Deterministic starter planner used until model-backed planning is implemented.
- `execution.py`: Deterministic plan execution run service for MVP workflow validation.
- `guardrails.py`: Filesystem policy evaluation plus guarded UTF-8 text file reads, writes, and command execution compatibility wrappers.
- `providers.py`: Provider registry, Ollama/LM Studio health and model probes, external provider contract placeholder, and scored routing decisions.
- `provider_runtime.py`: Ollama and LM Studio chat/completion request execution.
- `agents.py`: Sub-agent brief registry, parent-child lifecycle tracking, status updates, and output reconciliation.
- `memory.py`: In-memory memory record indexing and search.
- `tools.py`: Local tool manifest registration, guarded tool generation, duplicate detection, and governance updates.
- `tool_runtime.py`: Generated tool subprocess execution and reliability counter updates.
- `sessions.py`: Session summary registry.
- `events.py`: Central event log backed by local JSON state.
- `storage.py`: JSON collection persistence helper for MVP local state.
- `settings.py`: Environment-based backend settings.

### `tests/`

Automated tests for backend behavior. The current tests validate health checks, task planning, persisted task history, deterministic execution, guardrail checks, configurable CLI policy rules, CLI approvals and run history, provider routing and generation runtime, dynamic tool generation, tool execution and governance, agent lifecycle APIs, session summaries, and logs.

### `localmcp/`

Location for generated reusable tools. DGentic-created tools live under:

```text
localmcp/[tool_name]/
  tool.py
  wrapper.py
  manifest.json
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
- `GET /tasks/plans`: Lists persisted task plans.
- `POST /tasks/execute`: Creates a deterministic execution run from a task plan.
- `GET /tasks/runs`: Lists persisted task execution runs.
- `POST /guardrails/filesystem`: Evaluates filesystem action policy against `rootDir`.
- `POST /filesystem/read`: Reads a UTF-8 text file after root boundary policy approval.
- `POST /filesystem/write`: Writes a UTF-8 text file after root boundary policy approval.
- `POST /guardrails/commands`: Classifies CLI command risk.
- `POST /cli/policy/rules`: Creates a persisted CLI policy rule.
- `GET /cli/policy/rules`: Lists persisted CLI policy rules in evaluation order.
- `PATCH /cli/policy/rules/{rule_id}`: Updates a persisted CLI policy rule.
- `POST /cli/execute`: Executes allowed or explicitly approved commands inside `rootDir`.
- `POST /cli/approvals`: Creates a pending approval for approval-required commands.
- `GET /cli/approvals`: Lists CLI approval records.
- `POST /cli/approvals/{approval_id}/approve`: Approves a pending CLI command.
- `POST /cli/approvals/{approval_id}/deny`: Denies a pending CLI command.
- `POST /cli/approvals/{approval_id}/execute`: Executes an approved CLI command once.
- `GET /cli/runs`: Lists persisted CLI command run history.
- `GET /providers`: Lists configured providers with discovered local model names when reachable.
- `GET /providers/{provider_id}/health`: Returns provider configuration health.
- `POST /providers/generate`: Runs an Ollama or LM Studio chat/completion request.
- `POST /routing/decide`: Returns a scored provider routing decision with candidate scores.
- `POST /agents`: Registers a running sub-agent brief.
- `GET /agents`: Lists registered sub-agent briefs.
- `GET /agents/{agent_id}`: Returns a specific sub-agent brief.
- `GET /agents/{agent_id}/children`: Lists child agents for a parent agent.
- `PATCH /agents/{agent_id}/status`: Updates sub-agent lifecycle status.
- `POST /agents/reconcile`: Reconciles sub-agent output reports.
- `POST /memory`: Adds an in-memory memory record.
- `POST /memory/search`: Searches memory records by text and tags.
- `POST /tools`: Registers a local tool manifest.
- `POST /tools/generate`: Generates a local tool directory with source, wrapper, manifest, and README files.
- `POST /tools/{name}/execute`: Executes a registered generated tool and updates reliability counters.
- `GET /tools`: Lists registered tool manifests.
- `PATCH /tools/{name}/governance`: Deprecates, disables, or reactivates a registered tool.
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

## Local State

DGentic stores MVP local state as JSON collections under `.dgentic/` by default. The directory is ignored by Git and can be changed with `DGENTIC_DATA_DIR`.

Current collections:

- `task-plans.json`
- `task-runs.json`
- `events.json`
- `agents.json`
- `memory.json`
- `tools.json`
- `sessions.json`
- `cli-approvals.json`
- `cli-command-policy-rules.json`
- `cli-command-runs.json`

## Architecture Decisions

- Start with a backend-first monorepo because orchestration, permissions, schemas, and logs define the core product contracts.
- Keep model-provider execution out of the first slice; the initial planner is deterministic and auditable.
- Define Pydantic schemas early so future UI, extension, memory, routing, and tool runtime work can share stable contracts.
- Generate tools only under `rootDir/localmcp/[tool_name]/`, with source, wrapper, manifest, README, registry entry, and memory artifact indexing.
- Use local JSON collections for the MVP sprint surface; replace or migrate them before production use where concurrency, indexing, or schema migrations matter.
- Probe Ollama and LM Studio through lightweight local HTTP health/model discovery; keep external providers as contract placeholders until credential and rate-limit handling are ready.
- Execute Ollama and LM Studio chat requests through provider runtime contracts; streaming and external providers remain follow-up work.
- Perform filesystem operations only through guardrail evaluation; current runtime support is intentionally limited to UTF-8 text reads and writes inside `rootDir`.
- Execute CLI commands only through configurable command policy evaluation, root-bound working directories, approval records, sanitized output capture, persisted run history, and audit logging.
- Keep built-in CLI defaults for blocked and approval-required executables, but let persisted rules override or refine those defaults by executable, exact command, command substring, or argument substring.
