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

In `development` and `test`, an explicit `approved: true` bypass can be used for local CLI smoke checks. In `staging` and `production`, approval-required commands need a single-use approved `approval_id`.

Start, poll, and cancel an asynchronous CLI run in local development:

```powershell
curl -X POST http://127.0.0.1:8000/cli/runs `
  -H "Content-Type: application/json" `
  -d '{"command":"python -c \"import time; time.sleep(30)\"","approved":true,"timeout_seconds":60}'
```

```powershell
curl http://127.0.0.1:8000/cli/runs/[run_id]
```

```powershell
curl "http://127.0.0.1:8000/cli/runs/[run_id]/output?after_sequence=0"
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/runs/[run_id]/cancel
```

Queue, approve, and execute an approval-required CLI command:

```powershell
curl -X POST "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"command":"python --version","timeout_seconds":10,"requested_by":"operator"}'
```

```powershell
curl http://127.0.0.1:8000/cli/approvals/[approval_id]/review
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/approvals/[approval_id]/approve `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Version check is acceptable."}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/approvals/[approval_id]/execute
```

The review response is safe for UI consumers: it returns redacted command text, policy context, environment key names without values, command/environment HMAC digest identifiers, warnings for environment-bound, redacted-command, or legacy-digest approvals, and whether direct execution is available. Use the bound approval directly when executing with reviewed environment keys or when calling `/cli/execute` or `/cli/runs`:

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"python --version","timeout_seconds":10,"approval_id":"[approval_id]","requested_by":"operator"}'
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
curl -X POST http://127.0.0.1:8000/filesystem/write-binary `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts/blob.bin","content_base64":"AAEC/w=="}'
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/list `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/copy `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","approved":true}'
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

Provider calls must target exact allowlisted base URLs. By default, DGentic allows only the configured Ollama and LM Studio endpoints; add trusted extra endpoints with `DGENTIC_PROVIDER_ALLOWED_BASE_URLS` when needed. Redirects are blocked, request payloads are bounded, malformed upstream success payloads become generic provider failures, configured URLs with embedded credentials are not displayed, and logs keep provider usage/cost metadata without persisting raw completion content. Generation uses bounded retry/backoff for retryable `429` and upstream `5xx` failures; health probes stay single-attempt.

The OpenAI-compatible external adapter is disabled until `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL`, `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV`, and `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS` are configured. The external base URL must use HTTPS because the adapter sends a bearer credential. The credential setting stores only the name of an environment variable; the actual API key value must be exported separately and is sent only as an outbound Authorization header. Direct external generation is approval-required: development/test smoke checks can include `"approved": true`; staging/production requests need a single-use bound `approval_id`.

Queue and approve a provider request before external generation in production-style mode:

```powershell
$approval = curl -X POST "http://127.0.0.1:8000/providers/external-openai-compatible/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hello."}]}'

curl http://127.0.0.1:8000/providers/approvals/[approval_id]/review

curl -X POST http://127.0.0.1:8000/providers/approvals/[approval_id]/approve `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Approved for this request."}'

curl -X POST http://127.0.0.1:8000/providers/generate `
  -H "Content-Type: application/json" `
  -d '{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hello."}],"approval_id":"[approval_id]","requested_by":"operator"}'
```

Provider approval records store safe review metadata, request HMAC digests, requester/agent/task context, decision timestamps, and expiry without persisting raw prompt content or credential values. When auth is enabled, provider approval create/list/review/approve/deny routes require the separate `approvals` capability, while generation still requires `providers`. Approved records are claimed before outbound provider transport, so a failed provider call still consumes the approval.

For OpenAI-compatible streaming, call `POST /providers/generate/stream`. The endpoint returns newline-delimited JSON chunk events for LM Studio and the configured external adapter, while `/providers/generate` remains the non-streaming JSON endpoint.

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

Create, approve, and execute an approval-required generated tool:

```powershell
$approval = curl -X POST "http://127.0.0.1:8000/tools/pdf-generator/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"payload":{"title":"Example"},"timeout_seconds":30}' | ConvertFrom-Json

curl -X POST "http://127.0.0.1:8000/tools/approvals/$($approval.id)/approve" `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Safe local generated tool run."}'

curl -X POST http://127.0.0.1:8000/tools/pdf-generator/execute `
  -H "Content-Type: application/json" `
  -d ('{"payload":{"title":"Example"},"approval_id":"' + $approval.id + '","timeout_seconds":30,"requested_by":"operator"}')
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

Generated tools created through `/tools/generate` are also registered in the SQLAlchemy-backed registry. Registry duplicate checks run before file creation, execution fails closed when the SQL registry marks a tool deprecated or disagrees with the local manifest permission mode, approval-required execution uses single-use bound approval IDs outside development/test mode, approving or denying tool approvals uses the `approvals` capability when auth is enabled, completed executions sync SQL registry usage counters and apply runtime reliability policy automation, and tool stdout/stderr/parsed output plus execution audit metadata are redacted for common secret-shaped values.

The interactive OpenAPI docs are available at `http://127.0.0.1:8000/docs` when the backend is running.

Local MVP state is written to `.dgentic/` by default. Set `DGENTIC_DATA_DIR` to move state elsewhere.

## Future Platform Usage

Once implemented, DGentic should support this workflow:

### 1. Start The Backend

Run the DGentic backend orchestrator. The backend will own task planning, execution state, provider routing, agent lifecycle, tool execution, memory access, and audit logs.

### 2. Configure Model Providers

Configure local model providers first:

- Local runtimes: Ollama and LM Studio.
- Extra trusted endpoints: add exact comma-separated base URLs with `DGENTIC_PROVIDER_ALLOWED_BASE_URLS`.
- External providers: an OpenAI-compatible non-streaming and streaming adapter is available when explicitly configured with HTTPS, a model allowlist, an env-referenced credential, and development/test approval or a staging/production bound provider approval ID; dedicated Google AI, DeepSeek, Anthropic, Copilot, or other adapters remain future work.
- Routing rules: Cost, latency, reliability, privacy, role-to-model mapping, and task complexity.

### 3. Set Security Boundaries

Configure strict operating boundaries before running autonomous tasks:

- Workspace `rootDir`
- Bearer-token authentication, route capabilities, and startup token validation for production/staging APIs
- Filesystem text, binary, directory, metadata, delete, move, copy, and rename permissions
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

Log responses redact common secret assignments, secret-like flags, shell-substitution values, and structured sensitive metadata keys such as token, password, secret, credential, and API key fields.

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
- Ollama and LM Studio have policy-validated local health/model probes and chat generation calls with redirect blocking, bounded request and upstream response payload validation, bounded retry/backoff for retryable generation failures, normalized usage/cost metadata, safe telemetry, and NDJSON streaming through `/providers/generate/stream`.
- The OpenAI-compatible external adapter is disabled by default and requires HTTPS base URL, model allowlist, credential env-var configuration, and explicit approval for direct generation; it supports non-streaming and NDJSON streaming calls with single-use bound provider approval IDs outside development/test mode, while encrypted credential storage and provider-specific external adapters remain future work.
- Guardrails enforce text and binary reads/writes, directory listing, metadata, and approval-gated delete/move/copy/rename inside `rootDir`; bound filesystem approval records, configurable persisted filesystem policy rules, deeper locked-file handling, and OS-level filesystem isolation remain follow-up work.
- CLI guardrails can configure persisted and agent-role scoped policy rules, queue, approve, deny, execute with single-use bound approval IDs outside development/test mode, start asynchronous runs, poll run status/output chunks, reconcile stale running records, cancel process-local runs, conservatively terminate matching prior-supervisor orphan processes after restart, apply controlled environment overrides, audit agent/task context, and persist command runs, but there is not yet a user-facing approval UI, full process adoption/resumable output after restart, or production multi-worker lease supervision.
- Hybrid retrieval works through deterministic local hash embeddings for MVP usage; production vector storage, optional model packaging, compression/summarization, and performance validation remain follow-up work.
- Tools can be generated, auto-registered in the SQL registry, duplicate-checked, indexed, migrated to strictly newer same-name versions with explicit overwrite, executed with registry permission/deprecation checks, bound approval IDs for approval-required tools outside development/test mode, runtime reliability policy automation, redacted outputs/audit metadata, local-only dependency import isolation, process-group timeout cleanup hardening, and deprecation controls, but full OS/filesystem/network sandbox isolation, parallel multi-version SQL registry rows, and production package/dependency lifecycle management are still needed.
- Frontend, dashboard, and VS Code extension components still need to be built.
- Commands for the current backend are documented in `docs/how-to/developer-setup.md`.
