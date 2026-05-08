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
- `DGENTIC_AUTOPILOT_ENABLED=false`
- `DGENTIC_AUTH_ENABLED` unset, which means auth is off in development and on in staging/production
- `DGENTIC_AUTH_TOKENS` empty by default
- `DGENTIC_OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `DGENTIC_LM_STUDIO_BASE_URL=http://127.0.0.1:1234`

## Configure API Authentication

Local development is usable without authentication by default. In `staging` and `production`, DGentic enables bearer-token capability checks unless `DGENTIC_AUTH_ENABLED=false` is explicitly set.

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

Approval-required commands must include `approved: true`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"git status","approved":true,"timeout_seconds":5}'
```

Approval-required commands can also use the approval queue:

```powershell
$approval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"command":"python --version","timeout_seconds":10}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($approval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($approval.id)/execute"
```

Approval records keep agent/task context, but environment values are rejected by the approval queue because queued approval storage does not persist runtime secrets. Execute with `approved: true` after reviewing the environment keys when an environment override is required.

Long-running commands can be started asynchronously, polled, and cancelled. Policy checks and `rootDir` working-directory checks still run before the process starts:

```powershell
$run = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/runs `
  -ContentType "application/json" `
  -Body '{"command":"python -c \"import time; time.sleep(30)\"","approved":true,"timeout_seconds":60}'

Invoke-RestMethod -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)/cancel"
```

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
- CLI execution is policy-enforced and root-bound with configurable and agent-role scoped policy rules, approval records, asynchronous polling, process-local cancellation, controlled environment overrides, and context audit metadata, but there is no interactive approval UI, streaming output API, or restart-resilient process supervision yet.
- Ollama and LM Studio can be probed and called for chat generation, but streaming is not implemented yet.
- Local JSON persistence and SQLite-compatible semantic memory prototypes exist, but no production database migrations, production vector backend, frontend, or VS Code extension exists yet.
- Local tools can be generated and executed under `localmcp/`, but stronger sandbox isolation is still needed.
