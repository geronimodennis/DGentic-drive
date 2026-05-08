# How To Use DGentic

Date created: 2026-05-07

DGentic is currently in backend MVP development. This guide explains how to use the repository now and how the platform is expected to be used as implementation continues.

## Use The Repository Today

### 1. Read The Goal

Start with `docs/DGentic-goal.md`. This is the source specification for the platform vision, required capabilities, architecture, security model, memory system, tool runtime, interfaces, and configuration settings.

### 2. Plan Work From The Agile Backlog

Use `docs/planning/agile-task-plan.md` to choose the next implementation work. The plan is organized into:

- Epics
- User stories
- Acceptance criteria
- Engineering tasks
- Milestones
- Initial Sprint 1 backlog

### 3. Record Progress

Update `docs/progress/project-progress-log.md` whenever meaningful work is completed. Each entry should include:

- Date
- Status
- Completed work
- Decisions
- Blockers
- Next steps

### 4. Keep Documentation Organized

Use these documentation folders:

- `docs/planning/` for Agile plans, roadmaps, sprint plans, and backlog notes.
- `docs/progress/` for progress logs, status reports, and decisions.
- `docs/architecture/` for system diagrams, technical designs, contracts, and security models.
- `docs/how-to/` for setup, usage, operations, and troubleshooting.

### 5. Run The Current Backend MVP

Use `docs/how-to/developer-setup.md` to install dependencies, run the FastAPI service, call the starter task planning endpoint, and run verification commands.

Current useful API checks:

```powershell
curl http://127.0.0.1:8000/health
```

In local development, API authentication is off by default. In `staging` and `production`, protected routes require bearer tokens configured with `DGENTIC_AUTH_TOKENS`, such as `admin-token=admin;task-token=tasks`. When authentication is enabled, startup fails closed if no usable token map is configured.

Example protected request in production mode:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/plan `
  -H "Authorization: Bearer task-token" `
  -H "Content-Type: application/json" `
  -d '{"objective":"Create a guarded task plan for indexing project memory."}'
```

SQLAlchemy-backed metadata and tool registry services use SQLite at `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db` by default. Set `DGENTIC_DATABASE_URL` to point those services at another SQLAlchemy database URL. The current schema baseline is tracked in `schema_migrations`, and file-backed SQLite state can be backed up or restored with the local `backup_sqlite_database` and `restore_sqlite_database` helpers.

```powershell
curl -X POST http://127.0.0.1:8000/tasks/plan `
  -H "Content-Type: application/json" `
  -d '{"objective":"Create a guarded task plan for indexing project memory."}'
```

```powershell
curl http://127.0.0.1:8000/tasks/plans
```

```powershell
curl -X POST http://127.0.0.1:8000/guardrails/commands `
  -H "Content-Type: application/json" `
  -d '{"command":"git status"}'
```

Create a persisted argument-aware CLI policy rule:

```powershell
curl -X POST http://127.0.0.1:8000/cli/policy/rules `
  -H "Content-Type: application/json" `
  -d '{"name":"Block unsafe flag","match_type":"argument_contains","pattern":"--unsafe","permission_mode":"blocked","reason":"Unsafe flag is blocked by workspace policy.","priority":5}'
```

Create a role-scoped CLI policy rule:

```powershell
curl -X POST http://127.0.0.1:8000/cli/policy/rules `
  -H "Content-Type: application/json" `
  -d '{"name":"Developers may inspect git","match_type":"executable","pattern":"git","permission_mode":"autopilot_safe","reason":"Developer git inspection is allowed.","agent_roles":["developer"],"priority":5}'
```

```powershell
curl http://127.0.0.1:8000/cli/policy/rules
```

```powershell
curl -X PATCH http://127.0.0.1:8000/cli/policy/rules/[rule_id] `
  -H "Content-Type: application/json" `
  -d '{"enabled":false}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"cmd /c echo hello","timeout_seconds":5}'
```

Run a command with agent/task context and a controlled environment override. Command run history stores only the applied environment variable names:

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"cmd /c echo context","requested_by":"pm","agent_id":"agent-dev-1","agent_role":"developer","task_id":"story-5.3","environment":{"DGENTIC_TEST_FLAG":"enabled"}}'
```

Start, poll, and cancel an asynchronous CLI run:

```powershell
curl -X POST http://127.0.0.1:8000/cli/runs `
  -H "Content-Type: application/json" `
  -d '{"command":"python -c \"import time; time.sleep(30)\"","approved":true,"timeout_seconds":60}'
```

```powershell
curl http://127.0.0.1:8000/cli/runs/[run_id]
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/runs/[run_id]/cancel
```

Queue, approve, and execute an approval-required CLI command:

```powershell
curl -X POST "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"command":"python --version","timeout_seconds":10}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/approvals/[approval_id]/approve `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/approvals/[approval_id]/execute
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/write `
  -H "Content-Type: application/json" `
  -d '{"path":"notes/sprint.txt","content":"Sprint note."}'
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/read `
  -H "Content-Type: application/json" `
  -d '{"path":"notes/sprint.txt"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/routing/decide `
  -H "Content-Type: application/json" `
  -d '{"privacy_required":true}'
```

Provider health checks can probe local Ollama and LM Studio runtimes:

```powershell
curl http://127.0.0.1:8000/providers/ollama/health
curl http://127.0.0.1:8000/providers/lm-studio/health
```

Run a local provider generation request:

```powershell
curl -X POST http://127.0.0.1:8000/providers/generate `
  -H "Content-Type: application/json" `
  -d '{"provider_id":"ollama","model":"llama3.1","messages":[{"role":"user","content":"Say hello."}]}'
```

Generate a reusable local tool:

```powershell
curl -X POST http://127.0.0.1:8000/tools/generate `
  -H "Content-Type: application/json" `
  -d '{"name":"pdf-generator","description":"Generate a PDF from structured input.","trigger_source":"main_agent","permission_mode":"approval_required","tags":["pdf","document"]}'
```

Deprecate a tool:

```powershell
curl -X PATCH http://127.0.0.1:8000/tools/pdf-generator/governance `
  -H "Content-Type: application/json" `
  -d '{"status":"deprecated","reason":"Replaced by a more reliable tool."}'
```

Execute a generated tool:

```powershell
curl -X POST http://127.0.0.1:8000/tools/pdf-generator/execute `
  -H "Content-Type: application/json" `
  -d '{"payload":{"title":"Example"},"approved":true}'
```

Create a SQLAlchemy-backed metadata index record:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/memory/metadata `
  -H "Content-Type: application/json" `
  -d '{"entity_type":"memory","entity_id":"memory-1","tags":["sprint","metadata"],"category":"planning","description":"Sprint metadata record.","relevance_score":0.8}'
```

Run dependency-light hybrid retrieval over metadata text. The default embedding model is deterministic and does not require model downloads:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/memory/retrieve/hybrid `
  -H "Content-Type: application/json" `
  -d '{"query":"sprint metadata retrieval","tags":["sprint"],"similarity_threshold":0.1}'
```

Register a tool in the SQLAlchemy-backed registry:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/tools/registry `
  -H "Content-Type: application/json" `
  -d '{"tool_name":"example-tool","version":"1.0.0","source_path":"localmcp/example-tool","interface_signature":"sha256:example","permission_level":"approval_required","tags":["example"]}'
```

The interactive OpenAPI docs are available at `http://127.0.0.1:8000/docs` when the backend is running.

Local MVP state is written to `.dgentic/` by default. Set `DGENTIC_DATA_DIR` to move state elsewhere.

## Future Platform Usage

Once implemented, DGentic should support this workflow:

### 1. Start The Backend

Run the DGentic backend orchestrator. The backend will own task planning, execution state, provider routing, agent lifecycle, tool execution, memory access, and audit logs.

### 2. Configure Model Providers

Configure local and external model providers:

- Local runtimes: Ollama and LM Studio.
- External providers: OpenAI, Google AI, DeepSeek, Anthropic, Copilot, or other supported services.
- Routing rules: Cost, latency, reliability, privacy, role-to-model mapping, and task complexity.

### 3. Set Security Boundaries

Configure strict operating boundaries before running autonomous tasks:

- Workspace `rootDir`
- Bearer-token authentication, route capabilities, and startup token validation for production/staging APIs
- Filesystem read, write, and delete permissions
- CLI execution mode
- Configurable CLI allow, approval, and block rules with executable, argument-aware, and agent-role scoped matching
- Controlled CLI environment overrides and command context audit metadata
- Network policy and domain rules
- Tool creation and execution permissions

### 4. Submit A Task

Submit work through a supported interface:

- Unified chat interface
- API
- CLI
- VS Code extension

DGentic should respond with a task plan, required context, proposed tools, model routing decisions, and any actions requiring approval.

### 5. Review Agent Work

During execution, inspect:

- Orchestrator status
- Sub-agent task progress
- CLI and filesystem action logs
- Provider usage
- Tool runs
- Validation results
- Approval prompts

### 6. Review Final Output

At task completion, DGentic should provide:

- Final answer or artifact
- Steps performed
- Files changed
- Tools created or reused
- Memory updates
- Known risks or unresolved issues
- Suggested next steps

### 7. Resume Later

DGentic should persist session state so future sessions can resume with context, memory, task history, and relevant project decisions.

## Current Limitations

- DGentic has backend MVP contracts, not production autonomy.
- Production/staging API routes have a bearer-token capability gate and startup fail-closed token validation, but persisted identity management, token rotation, bound approval identities, and full audit actor propagation are not complete yet.
- State is persisted as local JSON collections and a SQLite-compatible SQLAlchemy baseline with a schema migration ledger plus SQLite backup/restore smoke helpers, but production PostgreSQL driver packaging, JSON-store migration, vector backend integration, expanded migrations, indexing, scheduled/remote backup automation, and concurrency controls still need to be added.
- Ollama and LM Studio have local health/model probes and chat generation calls, but streaming is not implemented yet.
- External provider adapters are still contract placeholders.
- Guardrails enforce UTF-8 text file reads and writes inside `rootDir`; binary files, deletes, moves, and broader file workflows still need production handling.
- CLI guardrails can configure persisted and agent-role scoped policy rules, queue, approve, deny, execute, start asynchronous runs, poll run status, cancel process-local runs, apply controlled environment overrides, audit agent/task context, and persist command runs, but there is not yet a user-facing approval UI, streaming output API, or restart-resilient process supervision.
- Hybrid retrieval works through deterministic local hash embeddings for MVP usage; production vector storage, optional model packaging, compression/summarization, and performance validation remain follow-up work.
- Tools can be generated, registered, indexed, executed, and deprecated, but stronger sandbox isolation is still needed.
- Frontend, dashboard, and VS Code extension components still need to be built.
- Commands for the current backend are documented in `docs/how-to/developer-setup.md`.
