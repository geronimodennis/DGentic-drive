# Developer Setup

Date created: 2026-05-07

This guide explains how to run the current DGentic backend foundation.

## Prerequisites

- Python 3.11 or newer, below Python 3.15.
- `uv` for dependency management.

## Install Dependencies

From the repository root:

```powershell
uv sync --dev
```

## Configure Environment

Copy `.env.example` to `.env` if local overrides are needed:

```powershell
Copy-Item .env.example .env
```

Default settings:

- `DGENTIC_APP_NAME=DGentic`
- `DGENTIC_ENVIRONMENT=development`
- `DGENTIC_ROOT_DIR=.`
- `DGENTIC_DATA_DIR=.dgentic`
- `DGENTIC_DATABASE_URL` unset, which means SQLAlchemy uses SQLite at `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db`
- `DGENTIC_AUTOPILOT_ENABLED=false`
- `DGENTIC_AUTH_ENABLED` unset, which means auth is off in development and on in staging/production
- `DGENTIC_AUTH_TOKENS` empty by default
- `DGENTIC_OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `DGENTIC_LM_STUDIO_BASE_URL=http://127.0.0.1:1234`

## Configure API Authentication

Local development is usable without authentication by default. In `staging` and `production`, DGentic enables bearer-token capability checks unless `DGENTIC_AUTH_ENABLED=false` is explicitly set.

When authentication is enabled, DGentic requires at least one valid `token=capabilities` entry in `DGENTIC_AUTH_TOKENS`. Startup fails closed if auth is enabled without usable tokens.

Token configuration uses semicolon-separated token entries and comma-separated capabilities:

```powershell
$env:DGENTIC_ENVIRONMENT = "production"
$env:DGENTIC_AUTH_TOKENS = "admin-token=admin;task-token=tasks;cli-token=cli"
```

Use a bearer token when calling protected routes:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tasks/plan `
  -Headers @{ Authorization = "Bearer task-token" } `
  -ContentType "application/json" `
  -Body '{"objective":"Create a guarded plan for indexing project memory."}'
```

Capability groups currently include `admin`, `tasks`, `filesystem`, `cli`, `providers`, `agents`, `memory`, `tools`, `sessions`, and `logs`. The `admin` capability can access all protected route groups. Public routes remain `GET /`, `GET /health`, `/docs`, `/redoc`, and `/openapi.json`.

## Configure Database Persistence

By default, SQLAlchemy-backed metadata and tool registry services use SQLite at:

```text
DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db
```

Override the database URL when needed:

```powershell
$env:DGENTIC_DATABASE_URL = "sqlite:///C:/workspace/dgentic-state/dgentic.db"
```

On first use, DGentic initializes the current SQLAlchemy metadata tables and records the baseline migration in `schema_migrations` as `0001_metadata_tool_registry_baseline`. Production PostgreSQL remains the planned database target, but driver packaging, production migrations beyond the baseline, JSON-store migration, scheduled backup automation, and concurrency hardening remain follow-up work.

## Backup And Restore Local SQLite State

For local/operator smoke workflows using the default file-backed SQLite database, create a backup with:

```powershell
uv run python -c "from dgentic.database import backup_sqlite_database; backup_sqlite_database('backups/dgentic.db')"
```

Restore from a backup with:

```powershell
uv run python -c "from dgentic.database import restore_sqlite_database; restore_sqlite_database('backups/dgentic.db')"
```

These helpers are intended for file-backed SQLite state. PostgreSQL-native backup, retention, and scheduled remote backup automation remain production follow-up work.

## Run The Backend

```powershell
uv run uvicorn dgentic.main:app --reload --app-dir src
```

After installing the package, you can also run:

```powershell
dgentic-server --host 127.0.0.1 --port 8000
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Create A Task Plan

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tasks/plan `
  -ContentType "application/json" `
  -Body '{"objective":"Create a guarded plan for indexing project memory.","constraints":["Only operate inside rootDir."],"acceptance_criteria":["Plan includes validation step."]}'
```

Task plans and execution runs are persisted in local JSON state:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/tasks/plans
Invoke-RestMethod -Uri http://127.0.0.1:8000/tasks/runs
```

By default, local state files are written under `.dgentic/`, which is ignored by Git.

## Use Guarded Text File Operations

Write a UTF-8 text file inside `DGENTIC_ROOT_DIR`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/write `
  -ContentType "application/json" `
  -Body '{"path":"notes/sprint.txt","content":"Sprint note."}'
```

## Use Guarded CLI Execution

Safe commands can run inside `DGENTIC_ROOT_DIR`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"cmd /c echo hello","timeout_seconds":5}'
```

Command requests can include agent/task context and explicit environment overrides. DGentic builds a controlled process environment, blocks sensitive runtime overrides such as `PATH`, `PYTHONPATH`, `SYSTEMROOT`, and `COMSPEC`, and stores only the applied environment variable names in command run history:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"cmd /c echo context","requested_by":"pm","agent_id":"agent-dev-1","agent_role":"developer","task_id":"story-5.3","environment":{"DGENTIC_TEST_FLAG":"enabled"}}'
```

In `development` and `test`, approval-required commands can still use the explicit `approved: true` bypass for local smoke checks:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"git status","approved":true,"timeout_seconds":5}'
```

In `staging` and `production`, approval-required commands need a single-use approved `approval_id`. Approval records are bound to command, cwd, timeout, requester, agent/task context, environment keys, policy decision metadata, and expiry:

```powershell
$approval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"command":"python --version","timeout_seconds":10,"requested_by":"operator"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($approval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer"}'

$executeBody = @{
  command = "python --version"
  timeout_seconds = 10
  approval_id = $approval.id
  requested_by = "operator"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/execute" `
  -ContentType "application/json" `
  -Body $executeBody
```

Approvals can also be executed through `POST /cli/approvals/{approval_id}/execute` when no environment override is required. Approval requests may include environment overrides for review, but only the environment variable names are persisted; the execution request must include the same environment keys when using `approval_id` directly.

Long-running commands can be started asynchronously, polled for status and output chunks, and cancelled. Policy checks and `rootDir` working-directory checks still run before the process starts:

```powershell
$runApproval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"command":"python -c \"import time; time.sleep(30)\"","timeout_seconds":60,"requested_by":"operator"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($runApproval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer"}'

$runBody = @{
  command = "python -c `"import time; time.sleep(30)`""
  timeout_seconds = 60
  approval_id = $runApproval.id
  requested_by = "operator"
} | ConvertTo-Json

$run = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/runs `
  -ContentType "application/json" `
  -Body $runBody

Invoke-RestMethod -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)"

Invoke-RestMethod -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)/output?after_sequence=0"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)/cancel"
```

Output chunks include sequence numbers and redacted stdout/stderr text. Persisted runs that are still marked `running` without a process in the current backend process are reconciled to `stale` on runtime service initialization.

Configure persisted command policy rules when the built-in defaults are too broad or too narrow. Rules are evaluated by ascending priority and can match by executable, exact command, command substring, or argument substring. Rules can also be scoped to agent roles:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/policy/rules `
  -ContentType "application/json" `
  -Body '{"name":"Developers may inspect git","match_type":"executable","pattern":"git","permission_mode":"autopilot_safe","reason":"Developer git inspection is allowed.","agent_roles":["developer"],"priority":5}'
```

Check that the role-scoped rule applies:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/guardrails/commands `
  -ContentType "application/json" `
  -Body '{"command":"git status","agent_role":"developer","agent_id":"agent-dev-1","task_id":"story-5.3"}'
```

List or disable configured policy rules:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/cli/policy/rules

Invoke-RestMethod `
  -Method Patch `
  -Uri http://127.0.0.1:8000/cli/policy/rules/[rule_id] `
  -ContentType "application/json" `
  -Body '{"enabled":false}'
```

## Check Local Providers

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/providers/ollama/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/providers/lm-studio/health
```

Run a local provider generation request:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/providers/generate `
  -ContentType "application/json" `
  -Body '{"provider_id":"ollama","model":"llama3.1","messages":[{"role":"user","content":"Say hello."}]}'
```

## Generate A Local Tool

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tools/generate `
  -ContentType "application/json" `
  -Body '{"name":"pdf-generator","description":"Generate a PDF from structured input.","trigger_source":"main_agent","permission_mode":"approval_required","tags":["pdf","document"]}'
```

This creates:

- `localmcp/pdf-generator/tool.py`
- `localmcp/pdf-generator/wrapper.py`
- `localmcp/pdf-generator/manifest.json`
- `localmcp/pdf-generator/README.md`

Generated tools are registered in local JSON state and indexed as memory artifacts.

Execute a generated tool:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tools/pdf-generator/execute `
  -ContentType "application/json" `
  -Body '{"payload":{"title":"Example"},"approved":true}'
```

Read it back:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/read `
  -ContentType "application/json" `
  -Body '{"path":"notes/sprint.txt"}'
```

## Use Metadata And Tool Registry Services

Create and query a SQLAlchemy-backed metadata index record:

```powershell
$metadata = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/metadata `
  -ContentType "application/json" `
  -Body '{"entity_type":"memory","entity_id":"memory-1","tags":["sprint","metadata"],"category":"planning","description":"Sprint metadata record.","relevance_score":0.8}'

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/memory/metadata/$($metadata.id)"
```

Run dependency-light hybrid retrieval over metadata text. The default embedding model is deterministic and does not require `sentence-transformers`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/retrieve/hybrid `
  -ContentType "application/json" `
  -Body '{"query":"sprint metadata retrieval","tags":["sprint"],"similarity_threshold":0.1}'
```

Register a tool in the SQLAlchemy-backed registry and record usage:

```powershell
$tool = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/tools/registry `
  -ContentType "application/json" `
  -Body '{"tool_name":"example-tool","version":"1.0.0","source_path":"localmcp/example-tool","interface_signature":"sha256:example","permission_level":"approval_required","tags":["example"]}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/tools/registry/$($tool.id)/usage" `
  -ContentType "application/json" `
  -Body '{"status":"success","execution_time_ms":25}'
```

Semantic and hybrid retrieval work with the default deterministic hash embedding. Configure an optional sentence-transformers model only when stronger production embeddings are required and the dependency is installed.

## Run Tests

```powershell
uv run pytest
```

## Run Lint And Format Checks

```powershell
uv run ruff check .
uv run ruff format --check .
```

To format files:

```powershell
uv run ruff format .
```

## Current Limitations

- The planner is deterministic and does not call local or external models yet.
- Filesystem runtime support is limited to guarded UTF-8 text reads and writes inside `DGENTIC_ROOT_DIR`.
- CLI execution is policy-enforced and root-bound with configurable and agent-role scoped policy rules, single-use bound approval IDs, asynchronous status/output polling, stale-running reconciliation, process-local cancellation, controlled environment overrides, and context audit metadata, but there is no interactive approval UI or full restart-resilient process supervision yet.
- Ollama and LM Studio can be probed and called for chat generation, but streaming is not implemented yet.
- Local JSON persistence and SQLite-compatible semantic memory prototypes exist with local SQLite backup/restore helpers, but no production database migration set, production vector backend, frontend, or VS Code extension exists yet.
- Local tools can be generated and executed under `localmcp/`, but stronger sandbox isolation is still needed.
