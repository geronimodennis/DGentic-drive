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
- No CLI execution runtime exists yet.
- Local JSON persistence exists, but no production database, semantic memory index, frontend, or VS Code extension exists yet.
- `localmcp/` is reserved for future generated tools but tool execution is not implemented.
