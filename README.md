# DGentic

DGentic is an advanced autonomous AI agent platform concept focused on local and external model orchestration, dynamic sub-agent spawning, backend-managed agent task graphs, guarded system access, persistent memory, reusable tools, and developer-facing interfaces.

The current repository contains the project specification, planning documents, and a backend MVP surface for orchestrator planning, deterministic execution runs, backend-managed orchestration runs with detached background execution polling and cooperative cancellation, production/staging bearer-token capability gates with startup fail-closed validation, persisted operator/group identity records, and persisted hashed token lifecycle APIs, guardrail checks, guarded filesystem operations, guarded CLI execution with single-use bound approval IDs, cwd-aware rootDir command policy checks, read-only path operand, explicit executable path, and configured-safe command path-argument hardening, bare executable workspace/PATH trust checks, top-level `cmd` AutoRun and PowerShell profile suppression, asynchronous CLI runs with status polling, chunked output polling, supervision metadata, auditable lifecycle states, cancellation, and stale-running reconciliation, configurable command policy rules with agent-role scoping, backend hook-policy records for command/filesystem/network pre-action escalation, controlled and audited command environment overrides with startup/preload injection blocking, local provider probes and generation calls, network/domain policy checks for provider egress and generated-tool Python socket egress, scored provider routing, agent lifecycle tracking, memory records, dynamically generated and executable local tools, backend-only plugin manifest discovery and trust records, tool governance, session summaries, event logs, local JSON state persistence, and a migration-managed SQLAlchemy persistence baseline with SQLite backup/restore helpers for metadata and tool registry tables.

## Documentation

- [Project goal](docs/DGentic-goal.md)
- [Documentation index](docs/README.md)
- [Agentic tasking and workflows](docs/agentic-workflows/README.md)
- [Agent role boundary rules](docs/agentic-workflows/governance/role-boundaries.md)
- [Agile task plan](docs/planning/agile-task-plan.md)
- [Backlog list and needs to be done](docs/planning/backlog-needs-to-be-done.md)
- [Generated orchestration follow-up backlog](docs/planning/orchestration-follow-ups.md)
- [Project progress log](docs/progress/project-progress-log.md)
- [Generated orchestration run status](docs/progress/orchestration-runs.md)
- [How to use DGentic](docs/how-to/using-dgentic.md)
- [Developer setup](docs/how-to/developer-setup.md)
- [Repository architecture](docs/architecture/repository-architecture.md)
- [Release distribution](docs/how-to/release-distribution.md)
- [0.2.6 release notes](docs/releases/0.2.6.md)
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

DGentic is in backend MVP development. The current API is useful for exercising contracts and sprint slices, while frontend UI, VS Code extension, deployment, and operations work continue.

### Review The Product Goal

Start with [docs/DGentic-goal.md](docs/DGentic-goal.md). It describes the intended platform capabilities, architecture, interface ecosystem, security model, and configuration surface.

### Plan Implementation Work

Use [docs/planning/agile-task-plan.md](docs/planning/agile-task-plan.md) as the Agile source and [docs/planning/backlog-needs-to-be-done.md](docs/planning/backlog-needs-to-be-done.md) as the refined backlog for completing partially implemented feature groups. The plan is organized into epics, user stories, acceptance criteria, and milestone phases.

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
- `POST /tasks/orchestrations`, `GET /tasks/orchestrations`, `GET /tasks/orchestrations/operations/summary`, `GET /tasks/orchestrations/{run_id}`, `POST /tasks/orchestrations/{run_id}/advance`, `POST /tasks/orchestrations/{run_id}/cycle`, `POST /tasks/orchestrations/{run_id}/loop`, `POST /tasks/orchestrations/{run_id}/executions`, `GET /tasks/orchestrations/{run_id}/executions`, `GET /tasks/orchestrations/{run_id}/executions/{execution_id}`, `POST /tasks/orchestrations/{run_id}/executions/{execution_id}/cancel`, `PATCH /tasks/orchestrations/{run_id}/tasks/{task_id}`, `POST /tasks/orchestrations/{run_id}/tasks/{task_id}/recover`, `POST /tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve`, and `POST /tasks/orchestrations/{run_id}/close` for backend-managed task graphs with dependency scheduling, role-boundary decisions, blockers, follow-ups, retry escalation, bounded autonomous cycling, operations summary counts, detached background loop execution polling/cancellation, manual/security blocker resolution, Definition of Done close gates, and generated project-document sync.
- `POST /auth/operator-groups`, `GET /auth/operator-groups`, `GET /auth/operator-groups/{group_id}`, and `PATCH /auth/operator-groups/{group_id}` for persisted operator group records, group capability bundles, active/inactive status, and safe group metadata.
- `POST /auth/operators`, `GET /auth/operators`, `GET /auth/operators/{operator_id}`, and `PATCH /auth/operators/{operator_id}` for persisted operator identity records, role labels, active/inactive status, direct capability assignments, assigned `group_ids`, and computed `effective_capabilities`.
- `POST /auth/tokens`, `GET /auth/tokens`, `POST /auth/tokens/{token_id}/rotate`, `POST /auth/tokens/{token_id}/revoke`, and `POST /auth/tokens/{token_id}/expire` for persisted generated bearer-token issuance, listing, rotation, revocation, and expiry without returning stored token hashes or raw token values after the one-time create/rotate response. New persisted tokens must target an active operator and cannot exceed that operator's effective capabilities, including active group-inherited capabilities.
- `POST /credentials/references`, `GET /credentials/references`, `POST /credentials/references/{credential_ref_id}/revoke`, and `POST /credentials/references/local-vault/rotate-key` for persisted credential references backed by environment variables, configured shell-free external process adapters, or local encrypted vault ciphertext without returning raw secret values, plus counts-only local vault key rotation for persisted local-vault ciphertext.
- `POST /guardrails/filesystem`, `POST /guardrails/commands`, and `POST /guardrails/network` for policy checks.
- `POST /guardrails/hooks/rules`, `GET /guardrails/hooks/rules`, and `PATCH /guardrails/hooks/rules/{rule_id}` for persisted backend hook-policy rules that can audit, require approval, or block command, filesystem, and network guardrail decisions without loading plugin hook code.
- `POST /filesystem/read`, `POST /filesystem/write`, `POST /filesystem/read-binary`, `POST /filesystem/write-binary`, `POST /filesystem/list`, `POST /filesystem/metadata`, `POST /filesystem/delete`, `POST /filesystem/move`, `POST /filesystem/copy`, and `POST /filesystem/rename` for policy-enforced filesystem operations inside `rootDir`.
- `POST /cli/policy/rules`, `GET /cli/policy/rules`, and `PATCH /cli/policy/rules/{rule_id}` for persisted CLI allow, approval, and block rules with executable, exact-command, contains, argument-aware matching, and optional agent-role scoping.
- `POST /cli/execute`, `POST /cli/runs`, `GET /cli/runs`, `GET /cli/runs/{run_id}`, `GET /cli/runs/{run_id}/output`, `POST /cli/runs/{run_id}/cancel`, `POST /cli/approvals`, `GET /cli/approvals`, `GET /cli/approvals/{approval_id}/review`, `POST /cli/approvals/{approval_id}/approve`, `POST /cli/approvals/{approval_id}/deny`, and `POST /cli/approvals/{approval_id}/execute` for policy-enforced command execution, asynchronous command runs, status polling, chunked output polling, cancellation, single-use bound approval IDs, safe approval review contracts, run history, supervision metadata, timeout/status/stale reason fields, agent/task context metadata, matched policy review metadata, auditable decision reasons, and auditable environment override keys.
- `GET /providers`, `GET /providers/{provider_id}/health`, `POST /providers/generate`, and `POST /routing/decide` for Ollama/LM Studio probes, allowlisted generation calls, safe provider telemetry, and scored provider routing.
- `POST /agents`, `GET /agents`, `GET /agents/{agent_id}`, `GET /agents/{agent_id}/children`, `PATCH /agents/{agent_id}/status`, and `POST /agents/reconcile` for sub-agent lifecycle contracts.
- `POST /memory` and `POST /memory/search` for in-memory retrieval contracts.
- `POST /api/v1/memory/metadata`, `GET /api/v1/memory/metadata`, `GET /api/v1/memory/metadata/{metadata_id}`, `PATCH /api/v1/memory/metadata/{metadata_id}`, and `DELETE /api/v1/memory/metadata/{metadata_id}` for SQLAlchemy-backed metadata index CRUD.
- `POST /api/v1/memory/retrieve/hybrid`, `POST /api/v1/memory/retrieve/vector`, and `GET /api/v1/memory/retrieve/metadata` for dependency-light metadata, hybrid, and vector retrieval service contracts.
- `POST /tools`, `POST /tools/generate`, `POST /tools/{name}/execute`, `GET /tools`, and `PATCH /tools/{name}/governance` for local tool registration, generation, execution, listing, and deprecation/disable governance.
- `GET /plugins`, `GET /plugins/{plugin_id}`, and `PATCH /plugins/{plugin_id}/trust` for backend-only plugin manifest discovery, safe redacted metadata summaries, SHA-256 manifest digests, and persisted explicit trust decisions without loading or executing plugin content.
- `POST /api/v1/tools/registry`, `GET /api/v1/tools/registry`, `GET /api/v1/tools/registry/{tool_id}`, `POST /api/v1/tools/registry/check-duplicate`, `POST /api/v1/tools/registry/{tool_id}/usage`, and `POST /api/v1/tools/registry/{tool_id}/deprecate` for SQLAlchemy-backed tool registry services.
- `POST /sessions/summary`, `GET /sessions/summary`, and `GET /logs` for session and redacted observability contracts.

Authentication is off by default in `development`, on by default in `staging` and `production`, and can be explicitly controlled with `DGENTIC_AUTH_ENABLED`. Protected routes can use bootstrap bearer tokens from `DGENTIC_AUTH_TOKENS`, for example `admin-token=admin;task-token=tasks`, or persisted generated tokens stored as salted PBKDF2 hashes in `auth-tokens.json` and assigned to persisted operator profiles in `operators.json`. Operator groups live in `operator-groups.json`; operators can reference them through `group_ids`, and token issuance plus runtime authorization are constrained by the operator's current direct plus active group-inherited effective capabilities. Operator display/role metadata, operator group display/description metadata, generated-token labels, credential-reference labels, and plugin trust reasons are redacted for common secret-shaped values before API responses, audit metadata, and new or mutated JSON persistence. Capability groups include `auth`, `credentials`, `tasks`, `filesystem`, `cli`, `providers`, `approvals`, `network`, `hooks`, `agents`, `memory`, `tools`, `sessions`, `logs`, and `admin`. Plugin discovery and trust routes use the `tools` capability. Hook policy rule management uses the `hooks` capability. CLI approval creation and approved-command execution use the `cli` capability, while CLI approval list, review, approve, and deny routes use the separate `approvals` capability. When authentication is enabled, application startup fails closed if no usable environment token or active persisted token is configured.

Local state is stored under `.dgentic/` by default and is ignored by Git. Override JSON state with `DGENTIC_DATA_DIR` and SQLAlchemy state with `DGENTIC_DATABASE_URL` when needed. Malformed or schema-invalid JSON collection files are quarantined in-place and the active collection is repaired to an empty valid file so the backend can continue starting. File-backed SQLite databases can be backed up and restored with the `backup_sqlite_database` and `restore_sqlite_database` helpers for local/operator smoke workflows.

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

Status: backend MVP sprint surface active; Sprint 15 production identity, secrets, and network guardrails is in progress, with BL-009a through BL-009v implemented.

README status policy: keep this section updated after every sprint, release, or meaningful implementation change. Always list implemented features, partially implemented features, and features that are not yet implemented.

### Implemented

- Core FastAPI backend application, Pydantic schemas, health checks, and backend test baseline.
- Deterministic task planning and execution run APIs with local JSON persistence.
- Guardrail policy checks for filesystem, command, and outbound network domain access.
- Guarded filesystem operations inside `rootDir`, including UTF-8 text read/write, base64 binary read/write, directory listing, metadata, approval-gated delete/move/copy/rename, protected state-file blocking, symlink escape blocking, size limits through `DGENTIC_MAX_FILESYSTEM_BYTES`, and filesystem audit events.
- Guarded CLI execution with approvals, single-use bound approval IDs for approval-required commands outside development/test mode, cwd-aware rootDir policy evaluation, read-only path operand, explicit executable path, configured-safe command path-argument boundary checks, and nested shell startup hardening checks, bare executable workspace/PATH trust checks including `cmd /c` inner command preflight and Windows default PATHEXT candidates, approval queue, safe approval review endpoint, method-aware reviewer capability separation, top-level `cmd /d` AutoRun suppression and PowerShell `-NoProfile -NonInteractive` profile/prompt suppression at launch, approve/deny/execute endpoints, redacted decision reasons, run history, failed launch run records for claimed synchronous approvals, output redaction/truncation, asynchronous status polling, chunked output polling, supervision metadata, starting/running/completed/failed/timed-out/cancelled/stale lifecycle tracking, stale-running reconciliation, process-local cancellation, and conservative prior-supervisor orphan termination after backend restart when process identity still matches.
- Production/staging bearer-token authentication gate with route capability groups for tasks, auth-token management, credentials, filesystem, CLI, providers, approvals, network, agents, memory, tools, sessions, logs, startup fail-closed validation when auth is enabled without tokens, persisted operator identity records with direct capability assignments, group assignments, effective capabilities, and active/inactive status, persisted operator group records with active/inactive capability bundles, persisted generated bearer tokens with salted PBKDF2 hashing, one-time raw token return, rotation, revocation, expiry, safe audit events, effective-capability-limited issuance and runtime authorization, deactivated-operator fail-closed behavior, operator-id actor binding for persisted tokens, authenticated-principal actor binding for direct CLI execution/runs, CLI approval execution, CLI approval list/review/approve/deny separation under the `approvals` capability, filesystem and command-policy audits, provider generation/streaming, generated-tool execution, task, agent, memory, tool, and session mutation events, persisted encrypted local credential-vault references with operator-supplied Fernet keys, counts-only supplied-key local vault ciphertext rotation, and secret-shaped metadata redaction for operator display/role fields, operator group display/description fields, auth-token labels, and credential-reference labels across responses, audit metadata, and new or mutated JSON state.
- Persisted CLI command policy rules with executable, exact-command, contains, argument-aware, and agent-role scoped matching.
- Shell-wrapper command inspection for common wrappers such as `cmd /c`, `sh -c`, and PowerShell command invocations, POSIX host execution translation for policy-approved `cmd /c` and `cmd.exe /c` commands, Windows/POSIX command flag parsing regressions, command-name escape decoding, launcher payload inspection, explicit executable-path rootDir boundary checks for direct, shell-wrapped, and launcher payload commands, and protected state-file path checks for common shell escape forms.
- Controlled CLI command environment overrides with blocked sensitive runtime, shell startup-hook, dynamic-loader preload/library path, and interpreter injection keys plus audited environment key metadata.
- Ollama, LM Studio, and disabled-by-default OpenAI-compatible external provider contracts, with health/model probes for local runtimes, local generation calls, NDJSON streaming for OpenAI-compatible runtimes, provider-scoped exact base URL allowlist checks, configurable network/domain policy enforcement with allow, deny, approval-required, and audit modes, single-use bound `network_approval_id` records for approval-required provider transport, redirect blocking, bounded retry/backoff and in-process circuit breakers for retry-exhausted generation failures, safe provider response metadata, HTTPS-only credential-safe external adapter configuration with persisted external credential references or env-var fallback, local encrypted vault references, shell-free external-process credential resolver adapters, deferred credential/header resolution until transport, single-use bound external provider approvals, bounded provider/model pricing estimates, role-aware provider/model routing, and scored provider routing.
- Sub-agent lifecycle tracking, parent-child relationships, status updates, and reconciliation contracts.
- Dynamic local tool generation and execution under `localmcp/`, SQLAlchemy-backed registry auto-registration for generated tools, registry duplicate preflight checks, explicit monotonic version migration policy, governance status, deprecated-tool exclusion, permission conflict fail-closed checks, local-only dependency import isolation, configured Python socket network policy guardrail for generated-tool subprocesses, process-group launch and timeout cleanup hardening, reduced inherited execution environment, and reliability counters.
- Backend-only plugin trust foundation for `rootDir/plugins/[plugin_id]/dgentic-plugin.json` manifests, including direct-manifest discovery only, no plugin import/load/execution, SHA-256 digesting over exact manifest bytes, redacted metadata summaries, persisted trust/block decisions in `plugin-trust.json`, stale trust detection when manifest bytes change, symlink/out-of-root/oversized/malformed manifest rejection, and `tools` capability enforcement for `/plugins`.
- Backend hook-policy foundation with persisted `hook-policy-rules.json` records, `hooks` capability route protection, command/filesystem/network surfaces, `any`/`exact`/`contains`/`prefix` matching, priority and agent-role scoping, redacted rule metadata and hook audit events, command and network approval binding for hook-forced approval decisions, filesystem hook block enforcement, and report-only filesystem hook approval decisions until bound filesystem approval records exist.
- Memory records, session summaries, redacted event logs, and local JSON state persistence with corrupt-file quarantine/restore helpers for MVP workflows.
- SQLAlchemy metadata indexing with CRUD APIs, additive memory lifecycle metadata migration, deterministic lifecycle preview/apply APIs, deterministic metadata compression preview/apply APIs, deterministic hash embeddings, SQLite vector backend abstraction, metadata fallback hybrid retrieval, stored vector retrieval, additive retrieval attribution and score explanations, inactive-memory exclusion by default with explicit opt-in, configurable database URLs, schema migration ledger baseline, file-backed SQLite backup/restore helpers, and focused retrieval/database/API tests.
- Backend orchestration runs for multi-agent task graphs, including dependency-aware scheduling into sub-agent briefs with redacted dependency-output context handoff, persisted scheduler leases and fenced task claims before agent spawn, fixed agent ids for crash repair, spawn-failure rollback for unspawned claims, stale-update conflict detection for scheduling mutations, opt-in SQL-backed shared memory handoff through explicit `shared_memory_tags` with orchestration provenance, owner-scope checks, optional run-scoped reuse policy, service-authored shared-memory metadata, and owner/admin-scoped orchestration agent and shared-memory reads when auth is enabled, explicit agent lifecycle reconciliation cycles, bounded autonomous loop execution, owner-scoped operations summary counts, detached process-local background loop execution with persisted pollable execution records, cooperative cancellation, heartbeat-based stale reconciliation, startup adoption/resume for expired prior-supervisor executions, active-run conflict rejection for foreground loop/advance/cycle calls, machine-readable role-boundary decisions, orchestration-bound filesystem write checks, orchestration-bound CLI action checks, orchestration-bound generated-tool approval/execution checks, orchestration-bound provider generation/approval checks, orchestration-bound network approval checks for active agent context, blocker and follow-up records, retry escalation, blocked task recovery for role-boundary and retry-exhaustion blockers, admin-reviewed manual/security blocker resolution with audit history, generated orchestration progress and follow-up documents, persisted run history, and Definition of Done evidence gates before closeout.
- Agentic workflow documentation, role files, sprint lifecycle rules, release workflow, strict role write-boundary governance, and mandatory checklist/progress-update governance.
- Refined backlog and sprint sequence for completing the partially implemented feature groups, starting with production auth/security and persistence.
- Release distribution process with versioned release notes and zip bundles.

### Partially Implemented

- CLI integration: approvals, single-use bound approval IDs, policy rules, status polling, chunked output polling, supervision metadata, stale-running reconciliation, cancellation, conservative post-restart orphan termination for single-worker restart recovery, context-aware rules, matched policy review metadata, safe approval review API contracts, environment controls with startup/preload injection override blocking, top-level `cmd` AutoRun and PowerShell profile/prompt suppression, bare executable workspace/PATH trust checks, POSIX execution parity for simple `cmd /c` wrappers, cwd-aware approval policy evaluation, reviewer routes split to the `approvals` capability when auth is enabled, broader Windows/POSIX wrapper parsing regressions, command-name escape decoding, launcher payload inspection, protected state-file escape checks, read-only path operand boundary checks, explicit executable path boundary checks, command-specific path argument hardening for configured-safe `git`, `npm`, `pnpm`, `yarn`, and `uv` directory flags, and nested shell startup hardening checks exist; full process adoption/resumable output after restart, production multi-worker lease semantics, full shell emulation/OS sandboxing, and the interactive approval UI remain.
- Filesystem runtime: text/binary read/write, directory listing, metadata, approval-gated delete/move/copy/rename, root/state boundary checks, symlink escape checks, size limits, and audit logs exist; bound filesystem approval records/UI, persisted configurable filesystem policy rules, deeper platform-specific locked-file handling, and OS-level filesystem isolation remain.
- Provider system: Sprint 12 scoped productionization is complete for Ollama, LM Studio, and the disabled-by-default OpenAI-compatible external adapter. Runtime calls have endpoint allowlist enforcement, network/domain policy enforcement, bound network approval records for approval-required provider domains, redirect blocking, bounded request and response payload validation, bounded retry/backoff and in-process circuit breakers for retry-exhausted generation failures, normalized usage/cost metadata, safe provider telemetry, NDJSON streaming, single-use bound provider approvals outside development/test mode, persisted credential references backed by environment variables, local encrypted vault ciphertext, or shell-free external-process adapters, local vault key rotation, deferred API-key/header resolution until transport-eligible execution, advisory provider/model pricing, and exact eligible role-to-provider/model routes. Durable multi-worker circuit state, provider-specific billing reconciliation, first-class external secret-manager adapters, managed KMS integration, and named provider-specific adapters remain future follow-up work.
- Memory and retrieval: memory record storage, text/tag search, SQLAlchemy metadata index services, metadata CRUD routes, deterministic semantic retrieval fallback, SQLite vector backend abstraction, stored vector retrieval, additive retrieval attribution/score reasons, lifecycle metadata, preview/apply lifecycle APIs, deterministic metadata-description compression, and retrieval API tests exist; pgvector integration, scheduled lifecycle/compression jobs, full-content or LLM summarization, broader performance validation, and deeper provenance/scoring policy remain later production-hardening work.
- Tool runtime: local tool generation, execution, governance, reliability tracking, runtime reliability policy automation, generated-tool SQL registry auto-registration, registry duplicate preflight checks, explicit same-name version migration with SQL reliability reset, deprecated registry exclusion, permission conflict fail-closed checks, bound approval records for approval-required tool execution outside development/test mode, orchestration-bound active task checks when tool agent context is supplied, output/log redaction for tool execution, local-only dependency import isolation, configured Python socket network policy guardrail for common generated-tool egress, process-group launch and timeout cleanup hardening, usage tracking, and registry routes exist; full OS/filesystem/network sandbox isolation, parallel multi-version SQL registry rows, and production package/dependency lifecycle management remain.
- Persistence: local JSON collections with corrupt-file quarantine/restore helpers and a migration-managed SQLite-compatible SQLAlchemy baseline with SQLite backup/restore smoke helpers exist; production database driver packaging, migration expansion beyond the baseline, JSON-store migration, indexing/concurrency hardening, and scheduled/remote backup automation remain.
- Security/auth: production and staging auth default-on route capability gates, persisted operator identity records with direct and group-inherited effective capability assignments, persisted operator groups, persisted hashed bearer tokens with rotation, revocation, expiry, operator-id approval actor binding, authenticated audit actors across the main API-triggered execution/mutation surfaces, persisted external credential references, encrypted local credential-vault references with supplied-key rotation, shell-free external-process credential resolver adapters, provider-call network/domain guardrails with bound approval records, active-task verification for caller-supplied orchestration agent context across CLI, generated-tool, provider, and network approval surfaces, method-aware CLI approval reviewer capability separation, generated-tool Python socket network policy enforcement, plugin manifest trust controls, backend hook-policy records for command/filesystem/network guardrail escalation, explicit CLI executable path rootDir enforcement, configured-safe command path-argument hardening, nested shell startup hardening checks, and secret-shaped metadata redaction for identity/token/credential/plugin trust/hook labels exist; richer production identity workflows beyond operator groups, managed KMS integration, first-class secret-manager adapters, web retrieval network enforcement, bound filesystem approval records, and OS-level egress isolation remain.

### Not Yet Implemented

- Web frontend/dashboard: planned for Sprint 16.
- VS Code extension: planned for Sprint 17.
- Dedicated CLI client interface: planned for Sprint 17.
- Interactive approval UI: planned for Sprint 16.
- DGentic-native plugin bundles beyond manifest discovery/trust, command recipes, hook-style safety policies, managed settings surfaces, and guarded git/PR workflow automation: planned across remaining Sprint 15 security follow-ups plus Sprint 16 UI, Sprint 17 CLI/VS Code, and Sprint 18 CI/observability work after the Claude Code repository study.
- Production deployment infrastructure and CI/CD pipeline: planned for Sprint 18.
- Provider-specific external AI adapters beyond the generic OpenAI-compatible adapter: planned for Sprint 19 follow-up after a concrete provider target is selected.
- Full production identity management beyond operator groups, managed KMS integration, first-class external secret-manager adapters, web retrieval network enforcement, and OS-level egress isolation: planned for remaining Sprint 15 follow-up; persisted operator profiles, persisted operator groups with capability inheritance, generated token lifecycle APIs, external credential references, encrypted local credential-vault references with supplied-key rotation, shell-free external-process credential resolver adapters, provider-call network/domain guardrails with bound approval records, generated-tool Python socket network policy enforcement, plugin manifest trust controls, task-scoped active orchestration context checks, method-aware CLI approval reviewer capability separation, explicit CLI executable path boundary enforcement, top-level shell startup hardening, bare executable workspace/PATH trust checks, configured-safe command path-argument hardening, nested shell startup hardening checks, and identity/token/credential/plugin-trust metadata redaction are implemented as Sprint 15 slices.
- Runtime monitoring, metrics, alerting, and rollback automation: planned for Sprint 18.
