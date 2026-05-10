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
      auth.py
      command_policy.py
      events.py
      cli_runtime.py
      execution.py
      guardrails.py
      main.py
      memory.py
      migrations.py
      memory/
        embedding_service.py
        metadata_service.py
        models.py
        retrieval_service.py
        schemas.py
      planner.py
      provider_runtime.py
      providers.py
      schemas.py
      sessions.py
      settings.py
      storage.py
      tool_runtime.py
      tools.py
      tools/
        registry_service.py
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
- `auth.py`: Production/staging bearer-token authentication, route capability mapping, and startup fail-closed configuration validation.
- `api/routes.py`: HTTP routes for health checks, tasks, guardrails, CLI policy and approvals, providers, routing, agents, memory, tools, sessions, and logs.
- `api/memory_routes.py`: SQLAlchemy-backed metadata index, retrieval, and tool registry routes under `/api/v1`.
- `schemas.py`: Pydantic contracts for tasks, execution runs, guardrails, CLI policy rules, command context, controlled command environments, providers, routing, agents, memory, tools, sessions, and logs.
- `command_policy.py`: Persisted CLI policy rule storage, optional agent-role rule scoping, executable, exact-command, contains, and argument-aware command matching, shell-wrapper inspection, cwd-aware evaluation, and read-only path operand rootDir boundary checks.
- `cli_runtime.py`: CLI approvals, single-use bound approval IDs, root-bound synchronous and asynchronous command execution, POSIX translation for policy-approved `cmd /c` and `cmd.exe /c` wrappers, chunked output polling, supervision metadata, auditable lifecycle states, stale-running reconciliation, process-local cancellation, controlled environment construction, agent/task context auditing, output redaction/truncation, and command run history.
- `planner.py`: Deterministic starter planner used until model-backed planning is implemented.
- `execution.py`: Deterministic plan execution run service for MVP workflow validation.
- `guardrails.py`: Filesystem policy evaluation plus guarded UTF-8 text file reads, writes, and command execution compatibility wrappers.
- `providers.py`: Provider registry, Ollama/LM Studio health and model probes, external provider contract placeholder, and scored routing decisions.
- `provider_runtime.py`: Ollama and LM Studio chat/completion request execution.
- `agents.py`: Sub-agent brief registry, parent-child lifecycle tracking, status updates, and output reconciliation.
- `memory.py`: Legacy in-memory memory record indexing and search module. The active import path is reconciled through the `dgentic.memory` package.
- `memory/`: SQLAlchemy metadata index models, schemas, metadata CRUD service, optional embedding service, and retrieval service contracts.
- `tools.py`: Legacy local tool manifest registration, guarded tool generation, duplicate detection, and governance module. The active import path is reconciled through the `dgentic.tools` package.
- `tools/`: SQLAlchemy-backed tool registry service with duplicate detection, usage tracking, reliability scoring, and source-path validation.
- `tool_runtime.py`: Generated tool subprocess execution and reliability counter updates.
- `sessions.py`: Session summary registry.
- `events.py`: Central event log backed by local JSON state.
- `migrations.py`: Minimal SQLAlchemy schema migration ledger for the current metadata, vector embedding, and tool registry baseline.
- `database.py`: Configurable SQLAlchemy engine/session helper, migration initialization, cached database reset, SQLite path resolution, and file-backed SQLite backup/restore helpers.
- `storage.py`: JSON collection persistence helper for MVP local state.
- `settings.py`: Environment-based backend settings, including auth mode and bearer token capability configuration.

### `tests/`

Automated tests for backend behavior. The current tests validate health checks, task planning, persisted task history, deterministic execution, guardrail checks, configurable and agent-role scoped CLI policy rules, shell-wrapper command policy hardening, CLI approvals, single-use approval ID binding, asynchronous CLI status/output polling, supervision metadata, stale-running reconciliation, cancellation and timeout lifecycle behavior, controlled command environments, command context auditing, run history, provider routing and generation runtime, dynamic tool generation, tool execution and governance, agent lifecycle APIs, session summaries, and logs.

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

Authentication:

- `GET /`, `GET /health`, `/docs`, `/redoc`, and `/openapi.json` are public.
- Development mode is auth-off by default.
- Staging and production modes are auth-on by default unless `DGENTIC_AUTH_ENABLED=false` is explicitly set.
- Protected route groups require bearer tokens configured through `DGENTIC_AUTH_TOKENS`, using capabilities such as `tasks`, `filesystem`, `cli`, `providers`, `agents`, `memory`, `tools`, `sessions`, `logs`, or `admin`.
- When auth is enabled, startup fails closed if `DGENTIC_AUTH_TOKENS` does not contain at least one valid `token=capabilities` entry.

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
- `POST /guardrails/commands`: Classifies CLI command risk, optionally using agent role, agent id, and task id context.
- `POST /cli/policy/rules`: Creates a persisted CLI policy rule, optionally scoped to one or more agent roles.
- `GET /cli/policy/rules`: Lists persisted CLI policy rules in evaluation order.
- `PATCH /cli/policy/rules/{rule_id}`: Updates a persisted CLI policy rule.
- `POST /cli/execute`: Executes allowed commands or approval-required commands with a bound `approval_id` inside `rootDir` with audited agent/task context and controlled environment overrides. The `approved: true` bypass is limited to development/test mode.
- `POST /cli/runs`: Starts an allowed asynchronous command run or an approval-required run with a bound `approval_id` and audited agent/task context and controlled environment overrides. The `approved: true` bypass is limited to development/test mode.
- `GET /cli/runs/{run_id}`: Polls a persisted command run by id.
- `GET /cli/runs/{run_id}/output`: Polls redacted stdout/stderr output chunks by sequence number.
- `POST /cli/runs/{run_id}/cancel`: Requests cancellation for a running command in the current backend process.
- `POST /cli/approvals`: Creates a pending approval for approval-required commands. Approval records include command digest, cwd, timeout, requester, agent/task context, environment keys without values, matched policy metadata, and expiry.
- `GET /cli/approvals`: Lists CLI approval records.
- `POST /cli/approvals/{approval_id}/approve`: Approves a pending CLI command.
- `POST /cli/approvals/{approval_id}/deny`: Denies a pending CLI command.
- `POST /cli/approvals/{approval_id}/execute`: Executes an approved CLI command once when no environment override is required.
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
- `POST /api/v1/memory/metadata`: Creates a SQLAlchemy-backed metadata index record.
- `GET /api/v1/memory/metadata`: Lists metadata index records with filters.
- `GET /api/v1/memory/metadata/{metadata_id}`: Retrieves a metadata index record and updates access tracking.
- `PATCH /api/v1/memory/metadata/{metadata_id}`: Updates a metadata index record.
- `DELETE /api/v1/memory/metadata/{metadata_id}`: Deletes a metadata index record.
- `POST /api/v1/memory/retrieve/hybrid`: Runs the hybrid retrieval contract. Semantic embedding generation currently requires an optional embedding dependency.
- `POST /api/v1/memory/retrieve/vector`: Runs the vector retrieval contract. Semantic embedding generation currently requires an optional embedding dependency.
- `GET /api/v1/memory/retrieve/metadata`: Runs metadata-only retrieval.
- `POST /tools`: Registers a local tool manifest.
- `POST /tools/generate`: Generates a local tool directory with source, wrapper, manifest, and README files.
- `POST /tools/{name}/execute`: Executes a registered generated tool and updates reliability counters.
- `GET /tools`: Lists registered tool manifests.
- `PATCH /tools/{name}/governance`: Deprecates, disables, or reactivates a registered tool.
- `POST /api/v1/tools/registry`: Registers a SQLAlchemy-backed tool registry entry.
- `GET /api/v1/tools/registry`: Lists SQLAlchemy-backed tool registry entries.
- `GET /api/v1/tools/registry/{tool_id}`: Retrieves a tool registry entry.
- `POST /api/v1/tools/registry/check-duplicate`: Checks duplicate tools by name, interface signature, and tag overlap.
- `POST /api/v1/tools/registry/{tool_id}/usage`: Records tool usage and updates reliability.
- `POST /api/v1/tools/registry/{tool_id}/deprecate`: Marks a tool registry entry as deprecated.
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

DGentic stores MVP local state as JSON collections under `.dgentic/` by default. The directory is ignored by Git and can be changed with `DGENTIC_DATA_DIR`. SQLAlchemy-backed metadata and registry services use `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db` by default for the local MVP database and can be pointed at another SQLAlchemy database with `DGENTIC_DATABASE_URL`.

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
- `dgentic.db`

SQLAlchemy schema state is tracked in `schema_migrations`. The current baseline id is `0001_metadata_tool_registry_baseline`. File-backed SQLite local databases can be backed up and restored with `backup_sqlite_database()` and `restore_sqlite_database()` for operator smoke workflows; scheduled, remote, and PostgreSQL-native backup automation remains future production work.

## Sprint 9 BL-003a Parser And Approval Review Contract Scope

Architect status: implementation-ready scope for the next Sprint 9 slice.

Goal:

- Make command policy parsing behavior explicit across common Windows and POSIX command shapes.
- Confirm approval-review metadata is safe and sufficient for future UI consumers.
- Keep this slice focused on parser/review contracts, not process supervision or UI implementation.

Current parser contract:

- `parse_command()` normalizes the first token into an executable name and leaves remaining tokens as arguments.
- Persisted command policy rules can match by executable, exact command, command substring, or argument substring.
- Common shell wrappers inspect inner commands for `cmd /c`, `sh -c`, `bash -c`, `powershell -Command`, `powershell -c`, `pwsh -Command`, and `pwsh -c`.
- Built-in defaults classify known destructive commands as blocked, runtime-changing commands as approval-required, and other commands as autopilot-safe.

Current approval-review contract:

- Approval records expose command, cwd, timeout, requested_by, agent_id, agent_role, task_id, permission mode, policy reason, environment keys, matched rule id/name, command digest, expiry, decision actor, denial reason, run id, and lifecycle timestamps.
- Environment values are not persisted in approval records; only environment variable names are stored for review and binding.
- Direct execution with a bound approval id validates command, cwd, timeout, requester, agent/task context, environment keys, permission mode, matched policy metadata, and digest before execution.

BL-003a Developer scope:

- Add source changes only if needed to make parser behavior deterministic for the QA matrix below.
- Preserve the existing public request/response shapes unless the parser matrix exposes missing review metadata.
- Do not add tests in the Developer step.
- Do not implement interactive approval UI in this slice.

BL-003a QA matrix:

- Windows wrappers: `cmd /c`, `cmd.exe /c`, `powershell -Command`, `powershell -c`, `powershell.exe -Command`, `pwsh -Command`, and `pwsh -c`.
- POSIX wrappers: `sh -c` and `bash -c`.
- Quoting cases: quoted executable paths, quoted inner shell commands, mixed single/double quotes, and commands with spaces in arguments.
- Policy behavior: blocked inner commands stay blocked, approval-required inner commands stay approval-required, safe inner commands remain autopilot-safe, and uninspectable wrappers require approval.
- Rule behavior: executable, exact, contains, argument_contains, priority ordering, disabled rules, and agent-role scoping remain stable.
- Review metadata: approval records expose command/cwd/role/task/environment keys/policy reason/matched rule metadata without environment values or secret values.

Architect handoff:

- Next role: Developer.
- Developer should inspect `src/dgentic/command_policy.py`, `src/dgentic/schemas.py`, and `src/dgentic/cli_runtime.py`.
- Developer may change production source only.
- Developer should hand off expected parser/review behavior and any source changes to QA for tests-only coverage.

## Architecture Decisions

- Start with a backend-first monorepo because orchestration, permissions, schemas, and logs define the core product contracts.
- Keep model-provider execution out of the first slice; the initial planner is deterministic and auditable.
- Define Pydantic schemas early so future UI, extension, memory, routing, and tool runtime work can share stable contracts.
- Generate tools only under `rootDir/localmcp/[tool_name]/`, with source, wrapper, manifest, README, registry entry, and memory artifact indexing.
- Use local JSON collections for the MVP sprint surface; replace or migrate them before production use where concurrency, indexing, or schema migrations matter.
- Use SQLite-compatible SQLAlchemy models for the metadata index and tool registry MVP slice, with configurable database URLs, a schema migration ledger, and local SQLite backup/restore smoke helpers. PostgreSQL remains the production target, while production driver packaging, migration expansion, JSON-store migration, scheduled backup automation, and vector storage remain follow-up work.
- Require bearer-token capability checks by default in staging and production while keeping development mode auth-off unless explicitly enabled. Production/staging startup fails closed when auth is enabled without configured bearer tokens.
- Probe Ollama and LM Studio through lightweight local HTTP health/model discovery; keep external providers as contract placeholders until credential and rate-limit handling are ready.
- Execute Ollama and LM Studio chat requests through provider runtime contracts; streaming and external providers remain follow-up work.
- Perform filesystem operations only through guardrail evaluation; current runtime support is intentionally limited to UTF-8 text reads and writes inside `rootDir`.
- Execute CLI commands only through configurable command policy evaluation, root-bound and cwd-aware working directories, controlled inherited environments plus explicit non-sensitive overrides, single-use approval records for approval-required commands outside development/test mode, sanitized output capture, persisted run history, and audit logging.
- Support asynchronous CLI runs through persisted run records, redacted output chunks, supervision metadata, auditable lifecycle states, stale-running reconciliation, timeout handling, and process-local cancellation; production process recovery and multi-worker supervision remain follow-up work.
- Keep built-in CLI defaults for blocked and approval-required executables, inspect common shell wrappers such as `cmd /c`, `sh -c`, and PowerShell command invocations for blocked inner commands, block built-in read-only path operands that resolve or shell-expand outside `rootDir`, translate simple policy-approved `cmd /c` and `cmd.exe /c` wrappers to `sh -c` on POSIX hosts, and let persisted rules override or refine defaults by executable, exact command, command substring, argument substring, or agent role.
