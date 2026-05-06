# DGentic Project Progress Log

This log records meaningful project progress, decisions, blockers, and next steps.

## 2026-05-07

### Sprint 3 Local Persistence Pass

Status: MVP local state now persists across backend process restarts.

Completed:
- Added `DGENTIC_DATA_DIR` setting with `.dgentic/` as the default local state directory.
- Added `.dgentic/` to `.gitignore`.
- Added reusable JSON collection storage for MVP state.
- Persisted task plans, task runs, event logs, agent briefs, memory records, tool manifests, and session summaries.
- Added task history endpoints: `GET /tasks/plans` and `GET /tasks/runs`.
- Added test coverage proving task plans and execution runs are written to local state files.
- Updated README, architecture documentation, usage guide, developer setup, environment template, and progress log.

Verification:
- `uv run pytest` passed with 8 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Remaining production work:
- Add schema migrations or versioned storage format for persisted records.
- Add concurrency controls appropriate for multi-worker deployments.
- Replace JSON collections with a production database when dashboard, retrieval, and long-running agents need richer querying.
- Add API support for deleting, archiving, and exporting local state.

---

### Sprint 2 MVP Execution Pass

Status: remaining sprint themes have backend MVP coverage.

Completed:
- Added deterministic task execution runs with per-step results.
- Added filesystem boundary policy checks for read, write, and delete actions.
- Added CLI command policy classification for safe, approval-required, and blocked commands.
- Added provider registry, provider health checks, and basic routing decisions.
- Added sub-agent brief spawning and output reconciliation contracts.
- Added in-memory memory indexing and search by text and tags.
- Added local tool manifest registration.
- Added session summary creation and retrieval.
- Added centralized event logging across task, provider, agent, filesystem, CLI, memory, tool, and session events.
- Added FastAPI endpoints for guardrails, execution, providers, routing, agents, memory, tools, summaries, and logs.
- Added API tests covering the new MVP sprint surfaces.

Verification:
- API test coverage has been expanded for deterministic execution, guardrails, provider routing, registries, session summaries, and logs.

Process update:
- Added a sprint close checklist to the Agile task plan requiring README updates, relevant documentation updates, progress log updates, follow-up notes, and quality gate verification whenever a sprint is completed.

Remaining production work:
- Replace in-memory stores with durable persistence.
- Replace placeholder provider adapters with Ollama, LM Studio, and external provider integrations.
- Add real command execution with approval workflow enforcement.
- Add real filesystem read/write operations behind the guardrail policy.
- Add semantic vector retrieval and memory compression.
- Add controlled tool execution runtime.
- Build the web chat, settings, dashboard, and VS Code extension interfaces.

---

### Release Distribution Update

Status: DGentic 0.1.0 release distribution created.

Completed:
- Added package build backend configuration with Hatchling.
- Added installed server command: `dgentic-server`.
- Added release notes in `docs/releases/0.1.0.md`.
- Added release distribution guide in `docs/how-to/release-distribution.md`.
- Built source distribution: `dist/dgentic-0.1.0.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.1.0-py3-none-any.whl`.
- Added artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.1.0.zip`.

Verification:
- `uv sync --dev` completed successfully.
- `uv run pytest` passed with 2 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.1.0-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8010.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.1.0.tar.gz`: `3BBC535C8ECF711183D651949B3388F659E96BAE555E89E33D9FB0538F037283`
- `dgentic-0.1.0-py3-none-any.whl`: `56590261C723EC01FC74A88AE4B51265AE93C3EBC78756BAEE12B8A3F540D682`
- `dgentic-0.1.0.zip`: `75DEC3D8C86226D8E3C400BA7857B9884D72707E7BD697D4810FEC6300319B21`

Next steps:
- Decide whether to initialize Git and tag `v0.1.0`.
- Add filesystem jail and permission policy implementation.
- Add local persistence for task plans and log events.

---

### Sprint 1 Execution Update

Status: backend foundation started.

Completed:
- Added Python/FastAPI backend package under `src/dgentic/`.
- Added project metadata and dependency configuration in `pyproject.toml`.
- Added environment template in `.env.example`.
- Added core Pydantic schemas for tasks, plans, steps, providers, agents, tools, and log events.
- Added deterministic starter planner in `src/dgentic/planner.py`.
- Added API routes for `GET /`, `GET /health`, and `POST /tasks/plan`.
- Added backend tests in `tests/test_api.py`.
- Added reserved `localmcp/` directory for future generated tools.
- Added repository architecture document in `docs/architecture/repository-architecture.md`.
- Added developer setup guide in `docs/how-to/developer-setup.md`.
- Updated root README, documentation index, and DGentic usage guide.

Verification:
- `uv sync --dev` completed successfully.
- `uv run pytest` passed with 2 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Decisions:
- Use `uv` for dependency management.
- Use FastAPI for the orchestrator API foundation.
- Use Pydantic v2 for shared backend contracts.
- Keep the initial planner deterministic until model routing and provider adapters are implemented.
- Reserve `localmcp/` now but defer generated tool execution until guardrails exist.

Next steps:
- Implement filesystem jail and permission policy models.
- Add CLI policy engine design and tests.
- Add local persistence for task plans and log events.
- Expand planning endpoint toward execution state tracking.
- Begin provider adapter contracts for local runtimes.

---

### Initial Documentation Status

Planning phase.

### Completed

- Captured the DGentic product goal in `docs/DGentic-goal.md`.
- Created documentation structure for planning and progress tracking.
- Created Agile task plan in `docs/planning/agile-task-plan.md`.
- Created project progress log in `docs/progress/project-progress-log.md`.
- Created documentation index in `docs/README.md`.
- Created root README with project overview and DGentic usage guidance.

### Decisions

- Use Agile delivery with epics, user stories, acceptance criteria, milestones, and sprint backlogs.
- Prioritize orchestrator foundation and guardrails before advanced autonomy.
- Keep project progress under `docs/progress/`.
- Keep planning documents under `docs/planning/`.
- Add future technical design documents under `docs/architecture/`.
- Add future setup and operating instructions under `docs/how-to/`.

### Blockers

- No runtime implementation exists yet.
- No package manifest, backend service, frontend app, or VS Code extension exists yet.
- Technical architecture needs to be decomposed into concrete implementation documents before coding begins.

### Next Steps

- Create a repository architecture document.
- Select the initial monorepo layout.
- Scaffold the FastAPI backend.
- Define core schemas for tasks, plans, steps, agents, providers, logs, and tool manifests.
- Create a developer setup guide.
- Start Sprint 1 using the backlog in `docs/planning/agile-task-plan.md`.
