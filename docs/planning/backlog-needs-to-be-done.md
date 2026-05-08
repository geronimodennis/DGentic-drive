# Backlog List And Needs To Be Done

Date created: 2026-05-07
Owner: [PM]
Status: refined backlog for completing partially implemented feature groups.

## Purpose

This backlog turns the current partially implemented feature gaps into trackable Agile work. It is the source list for PM sprint planning until each item is implemented, tested, documented, and moved out of the root README partially implemented section.

## Refinement Checklist

- Completed: Captured every partially implemented feature group from the root README.
- Completed: Split each group into completion stories with acceptance criteria.
- Completed: Identified dependencies and recommended sprint order.
- Completed: Added Definition of Done gates for implementation, QA, review, security, DevOps, docs, and release readiness.
- Completed: Execute Sprint 8.
- Completed: Update this backlog after Sprint 8 closeout.
- Completed: Initiate Sprint 9.
- In progress: Execute Sprint 9.

## Priority Order

1. Authentication, authorization, and security baseline.
2. Production persistence foundation.
3. CLI integration hardening.
4. Filesystem runtime completion.
5. Tool runtime safety and registry integration.
6. Provider system productionization.
7. Memory and retrieval production lifecycle.
8. Agent orchestration autonomy.

Rationale: DGentic already exposes powerful backend operations such as CLI execution, file writes, tool execution, provider calls, approvals, and logs. Authentication/authorization and persistence create the durable, accountable execution base needed before expanding autonomous agents, generated tools, provider routing, and long-running workflows.

## Backlog Items

### BL-000: Authentication, Authorization, And Security Baseline

Feature group: Cross-cutting production security.

User value:
- Operators need identity, capability checks, and auditable actors before production features can safely execute commands, write files, run tools, call providers, or approve actions.

Needs to be done:
- Add operator identity model and scoped API token strategy.
- Gate sensitive routes behind authentication.
- Add role/capability authorization for CLI, filesystem, tools, providers, memory, agents, logs, and approvals.
- Bind audit events to actor identity.
- Add secret masking and no-secret-response rules.
- Add route-level tests for unauthenticated, unauthorized, and authorized access.

Acceptance criteria:
- Sensitive routes reject unauthenticated requests in production mode.
- Authorized users can only perform actions allowed by their capabilities.
- Audit records include actor identity without leaking secret values.
- Local development can still run with an explicit development-mode bypass.

Definition of Done:
- Tests cover auth required, forbidden actions, allowed actions, audit actor capture, and secret masking.
- README, developer setup, architecture docs, and progress log are updated.
- Security review confirms production exposure is not anonymous by default.

Current implementation status:
- Completed: dependency-light bearer token auth dependency, production/staging auth-on default, development auth-off default, public route exemptions, route capability mapping, admin wildcard capability, startup fail-closed validation when auth is enabled without tokens, principal attachment on request state, focused tests for public routes, 401/403 behavior, allowed capability access, admin access, invalid-token no-echo behavior, token-configuration validation, and settings helpers.
- Remaining: persisted identity records, token hashing at rest, token rotation/expiry, full audit actor propagation, bound approval identities, and external secret manager integration.

### BL-001: Production Persistence Foundation

Feature group: Persistence.

User value:
- Operators need task, agent, approval, CLI, memory, tool, and log state to survive restarts and scale beyond local JSON MVP storage.

Needs to be done:
- Choose production database target and supported local development mode.
- Add migration tooling and initial migration scripts.
- Move remaining critical JSON stores behind repository interfaces.
- Add indexes for task runs, CLI approvals/runs, agents, tools, memory metadata, and logs.
- Add transaction boundaries and concurrency behavior.
- Add backup and restore workflow.
- Add data retention and cleanup policy.
- Store auth, approval, and audit state in a migration-managed persistence layer where required.

Acceptance criteria:
- Fresh installs can initialize the database from migrations.
- Existing local development still works with SQLite-compatible storage.
- Critical state survives process restarts.
- Concurrent writes are tested for the selected backend.
- Backup and restore are documented and verified with a smoke test.

Definition of Done:
- Tests cover migrations, repository behavior, restart persistence, and failure rollback.
- README, developer setup, architecture docs, and progress log are updated.
- Security review validates that secrets are not persisted in plain text.

Current implementation status:
- Completed: BL-001a migration-managed persistence baseline with `DGENTIC_DATABASE_URL`, default SQLite URL resolution under `rootDir/dataDir`, SQLite parent directory creation, SQLite-safe engine connect args, cached engine reset helper, idempotent `schema_migrations` ledger, baseline id `0001_metadata_tool_registry_baseline`, applied-migration listing helper, and focused database tests for URL behavior, migration table creation, idempotence, and restart persistence.
- Completed: BL-001b file-backed SQLite backup/restore smoke helpers with tests and operator documentation.
- Remaining: production PostgreSQL driver packaging, explicit ordered migrations beyond the baseline, critical JSON-store repository migration, auth/approval/audit persistence, concurrency/indexing hardening, scheduled/remote backup automation, retention cleanup, and failure rollback tests for future migrations.

### BL-002: CLI Streaming And Restart-Resilient Supervision

Feature group: CLI integration.

User value:
- Users and agents need long-running command output, cancellation, and status to remain reliable across backend restarts.

Needs to be done:
- Replace direct `approved: true` bypass for approval-required commands with bound approval records.
- Bind approvals to command digest, cwd, actor, agent/task context, environment keys, policy decision, and expiry.
- Add stdout/stderr streaming or chunked output polling.
- Persist process/run state in the production persistence layer.
- Reconcile stale running commands on backend startup.
- Add restart-resilient command lifecycle states.
- Preserve truncation, redaction, rootDir checks, and approval policy enforcement.

Acceptance criteria:
- Approval-required commands require a valid single-use approval ID unless explicitly running in development/test mode.
- Long-running command output can be observed while the process runs.
- Restarted backend marks stale process-local runs accurately.
- Cancelled, completed, failed, timed-out, and stale states are auditable.
- Streaming/polling does not expose redacted values.

Definition of Done:
- Tests cover output streaming/polling, stale reconciliation, cancellation, timeout, redaction, and restart behavior.
- CLI docs, README current status, and progress log are updated.

Current implementation status:
- Completed: BL-002a chunked async CLI output polling with redacted stdout/stderr chunks, output sequence cursors, persisted output chunks on command runs, and stale-running reconciliation for orphaned persisted runs.
- Remaining: approval-required commands still need bound approval IDs instead of broad `approved: true`, full restart-resilient process supervision beyond stale marking, persisted process recovery strategy, and production multi-worker lifecycle semantics.

### BL-003: CLI Parsing And Approval Review UX Contracts

Feature group: CLI integration.

User value:
- Operators need confidence that command policies behave consistently on Windows and POSIX systems, and approval reviewers need enough context to make decisions.

Needs to be done:
- Expand Windows/POSIX command parsing matrix.
- Add shell wrapper and quoting edge-case tests.
- Add approval/environment review API fields for command, cwd, role, task, environment keys, matched policy, and risk reason.
- Add backend contracts for interactive approval UI consumers.

Acceptance criteria:
- Policy evaluator handles common Windows and POSIX shells consistently.
- Approval records expose safe review metadata without secret values.
- Reviewers can approve or deny with an explicit reason.

Definition of Done:
- Tests cover Windows/POSIX parsing, wrappers, quoting, environment review metadata, and approval decision auditing.
- Usage and developer docs include examples.

Current implementation status:
- Completed: approval records now expose safe matched policy review metadata through matched rule id/name, existing command/cwd/role/task/environment-key fields, and no persisted environment values.
- Remaining: broader Windows/POSIX parsing matrix, quoting edge cases, explicit approval review contracts for UI consumers, and richer reviewer decision metadata.

### BL-004: Filesystem Runtime Completion

Feature group: Filesystem runtime.

User value:
- Agents need realistic file operations while operators retain rootDir safety and fine-grained permissions.

Needs to be done:
- Add binary read/write APIs.
- Add delete, move, copy, rename, directory listing, and metadata APIs.
- Add permission scopes for text read/write, binary read/write, delete, move, copy, and directory operations.
- Harden path normalization, symlink handling, locked files, and large-file behavior.
- Add audit logs for file operations.

Acceptance criteria:
- All operations resolve inside rootDir.
- Each operation can be independently allowed, approval-required, or blocked.
- Binary and large-file workflows are tested.
- Destructive operations require stronger policy checks.

Definition of Done:
- Tests cover traversal attempts, symlinks, binary payloads, destructive actions, locked/missing files, and audit logging.
- README, architecture docs, usage docs, and progress log are updated.

### BL-005: Tool Runtime Safety And Registry Integration

Feature group: Tool runtime.

User value:
- Generated tools must be reusable by agents without becoming an unbounded execution risk.

Needs to be done:
- Integrate generated `localmcp/` tools with the SQLAlchemy tool registry.
- Add tool versioning policy and no-overwrite rules.
- Add stronger sandbox isolation for tool execution.
- Enforce tool permission level at execution time.
- Add per-tool dependency isolation strategy.
- Use reliability score to allow, warn, disable, or deprecate tools.

Acceptance criteria:
- Generated tools are registered once with version and interface metadata.
- Unsafe or deprecated tools are excluded from normal reuse.
- Tool execution honors approval-required/autopilot-safe classification.
- Dependency installation cannot silently affect the whole application runtime.

Definition of Done:
- Tests cover registry integration, versioning, duplicate detection, permission enforcement, deprecated tool exclusion, and dependency isolation rules.
- Security review validates sandbox and filesystem boundaries.
- README, usage docs, architecture docs, and progress log are updated.

### BL-006: Provider System Productionization

Feature group: Provider system.

User value:
- DGentic needs secure, observable model routing across local and external providers.

Needs to be done:
- Add external provider adapter contracts and at least one production-ready external adapter.
- Add secure credential storage or integration with environment/secret manager policy.
- Add credential masking and secret leak tests.
- Add rate-limit, retry, backoff, and circuit-breaker behavior.
- Add streaming generation responses.
- Add provider usage logs with latency, error, token, and cost metadata where available.

Acceptance criteria:
- Provider credentials are never returned or logged in plain text.
- Streaming and non-streaming generation both work through a shared interface.
- Router can select external providers by policy and record why.
- Rate-limit and transient failure behavior is tested.

Definition of Done:
- Tests cover adapter success/failure, credential masking, streaming, retries, backoff, routing, and logs.
- README, setup docs, provider architecture docs, and progress log are updated.

### BL-007: Memory And Retrieval Production Lifecycle

Feature group: Memory and retrieval.

User value:
- DGentic needs memory that remains useful over time instead of growing into stale or expensive context.

Needs to be done:
- Select and implement production vector backend.
- Add migrations for memory metadata and vector stores.
- Add compression/summarization workflow for long-term memory.
- Add retention, pruning, promotion, archival, and freshness policy.
- Add retrieval performance validation and indexing strategy.
- Add source attribution and scoring improvements.

Acceptance criteria:
- Retrieval works against the selected production vector backend.
- Long-term memory can be summarized or compressed on schedule or threshold.
- Retention policy can keep, archive, prune, or promote records.
- Retrieval performance is measured and documented.

Definition of Done:
- Tests cover migrations, vector retrieval, summarization/compression hooks, lifecycle policy, and performance smoke checks.
- README, memory architecture, usage docs, and progress log are updated.

### BL-008: Agent Orchestration Autonomy

Feature group: Agent orchestration.

User value:
- DGentic should coordinate work autonomously while respecting role rules, dependencies, blockers, and sprint status.

Needs to be done:
- Add backend-managed autonomous execution loop.
- Add machine-readable role-boundary enforcement.
- Add task queues, assignments, dependencies, handoffs, blockers, retries, and escalation.
- Add production multi-agent scheduling.
- Add shared context/memory coordination.
- Add automatic sprint checklist, backlog, and progress updates.

Acceptance criteria:
- Agents can be scheduled to execute a sprint task graph.
- Role boundaries are enforced by policy, not only documentation.
- Blockers and failed validations create follow-up backlog items.
- Sprint progress is updated automatically and cannot close unless DoD is met.

Definition of Done:
- Tests cover task scheduling, dependency ordering, role enforcement, blocker escalation, retry policy, and progress updates.
- Agentic workflow docs, README current status, architecture docs, and progress log are updated.

## Proposed Sprint Plan

### Sprint 8: Production Security And Persistence Foundation

Goal:
- Establish authentication/authorization, durable production persistence, and migration foundations.

Stories:
- BL-000: Authentication, Authorization, And Security Baseline.
- BL-001: Production Persistence Foundation.

Exit criteria:
- Sensitive backend routes have production-mode auth/capability gates.
- Database decision recorded.
- Migration baseline exists.
- Critical state repository pattern is defined.
- Restart persistence and migration tests pass.
- README and docs/progress are updated.

Current Sprint 8 status:
- Closed: Sprint 8 completed the production security and persistence foundation exit criteria for the MVP backend.
- Completed: BL-000 first implementation slice for production/staging bearer token route capability gates and startup fail-closed token validation.
- Completed: BL-001a migration-managed persistence baseline.
- Completed: BL-001b file-backed SQLite backup/restore smoke helpers.
- Moved to follow-up backlog: persisted identity, token rotation, external secret management, production PostgreSQL packaging, expanded migrations, JSON-store migration, concurrency/indexing hardening, scheduled/remote backup automation, retention cleanup, and failure rollback tests.

### Sprint 9: CLI Runtime Hardening

Goal:
- Complete CLI streaming, restart reconciliation, and approval review contracts.

Stories:
- BL-002: CLI Streaming And Restart-Resilient Supervision.
- BL-003: CLI Parsing And Approval Review UX Contracts.

Exit criteria:
- Long-running command output is observable.
- Stale process reconciliation works after restart.
- Approval review metadata supports UI consumers.
- Windows/POSIX parser tests pass.

Current Sprint 9 status:
- In progress: Sprint 9 initiated.
- Completed: BL-002a output chunk polling and stale-running reconciliation.
- Partially completed: BL-003 approval records expose matched policy review metadata.
- Remaining: bound approval IDs, full restart-resilient process supervision semantics, broader Windows/POSIX parsing validation, and approval review UI contracts.

### Sprint 10: Filesystem Runtime Completion

Goal:
- Finish safe local file workflows with fine-grained policy.

Stories:
- BL-004: Filesystem Runtime Completion.

Exit criteria:
- Binary, delete, move, copy, and directory workflows exist with fine-grained policy.
- Filesystem security tests pass for traversal, symlinks, destructive actions, binary files, and audit logging.

### Sprint 11: Tool Runtime Safety And Registry Integration

Goal:
- Harden generated tool registration, versioning, dependency isolation, and execution permissions.

Stories:
- BL-005: Tool Runtime Safety And Registry Integration.

Exit criteria:
- Tool execution uses registry permissions and safer isolation.
- Generated tools have version/no-overwrite policy.
- Deprecated or unsafe tools are excluded from normal reuse.
- Security tests pass for sandbox, environment, filesystem, and permission boundaries.

### Sprint 12: Provider Productionization

Goal:
- Add secure external provider support and streaming generation.

Stories:
- BL-006: Provider System Productionization.

Exit criteria:
- External provider adapter works through shared provider contracts.
- Credentials are protected.
- Streaming, retry, rate-limit, and routing tests pass.

### Sprint 13: Memory Production Lifecycle

Goal:
- Make memory durable, scalable, and self-maintaining.

Stories:
- BL-007: Memory And Retrieval Production Lifecycle.

Exit criteria:
- Production vector backend and migrations are implemented.
- Compression/summarization and lifecycle policies exist.
- Retrieval performance validation is recorded.

### Sprint 14: Autonomous Agent Orchestration

Goal:
- Complete backend-managed multi-agent sprint execution.

Stories:
- BL-008: Agent Orchestration Autonomy.

Exit criteria:
- Backend can coordinate sprint task graphs.
- Role-boundary enforcement is machine-readable.
- Progress and backlog updates are automatic.
- Sprint closure requires Definition of Done evidence.

## Release Readiness Gates

Every backlog item must satisfy these gates before it can be marked done:

- PO: user value and acceptance criteria validated.
- PM: checklist complete, status updated, and follow-up backlog captured.
- Architect: contracts and architecture reviewed.
- Dev: production source implemented without creating/modifying QA-owned tests.
- QA: tests added or updated without modifying production source.
- Reviewer: maintainability and correctness reviewed.
- Security: permission, secret, sandbox, and data exposure risk reviewed.
- DevOps: runtime, deployment, migration, rollback, and observability concerns validated.
- ReleaseManager: release notes prepared when release-worthy.
- Docs: README and relevant docs updated.
