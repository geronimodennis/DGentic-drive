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
- `DGENTIC_OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `DGENTIC_LM_STUDIO_BASE_URL=http://127.0.0.1:1234`

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

Configure persisted command policy rules when the built-in defaults are too broad or too narrow. Rules are evaluated by ascending priority and can match by executable, exact command, command substring, or argument substring:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/policy/rules `
  -ContentType "application/json" `
  -Body '{"name":"Block unsafe flag","match_type":"argument_contains","pattern":"--unsafe","permission_mode":"blocked","reason":"Unsafe flag is blocked by workspace policy.","priority":5}'
```

Check that the argument-aware rule applies:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/guardrails/commands `
  -ContentType "application/json" `
  -Body '{"command":"cmd /c echo --unsafe"}'
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
- CLI execution is policy-enforced and root-bound with configurable policy rules and approval records, but there is no interactive approval UI, cancellation API, or streaming/polling output API yet.
- Ollama and LM Studio can be probed and called for chat generation, but streaming is not implemented yet.
- Local JSON persistence exists, but no production database, semantic memory index, frontend, or VS Code extension exists yet.
- Local tools can be generated and executed under `localmcp/`, but stronger sandbox isolation is still needed.
