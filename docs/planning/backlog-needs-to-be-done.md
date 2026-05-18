# Backlog List And Needs To Be Done

Date created: 2026-05-07
Owner: [PM]
Status: refined backlog for completing partially implemented and not-yet-implemented feature groups.

## Purpose

This backlog turns the current partially implemented and not-yet-implemented feature gaps into trackable Agile work. It is the source list for PM sprint planning until each item is implemented, tested, documented, and moved out of the root README partially implemented or not-yet-implemented sections.

## Refinement Checklist

- Completed: Captured every partially implemented feature group from the root README.
- Completed: Split each group into completion stories with acceptance criteria.
- Completed: Identified dependencies and recommended sprint order.
- Completed: Added Definition of Done gates for implementation, QA, review, security, DevOps, docs, and release readiness.
- Completed: Execute Sprint 8.
- Completed: Update this backlog after Sprint 8 closeout.
- Completed: Initiate Sprint 9.
- Completed: Map all root README not-yet-implemented items into remaining or newly added sprints.
- Completed: Execute Sprint 9.
- Completed: Close Sprint 9 scoped CLI runtime hardening and move production-grade process adoption/leasing to follow-up backlog.
- Completed: Initiate Sprint 10.
- Completed: Execute Sprint 10 scoped MVP filesystem runtime completion.
- Completed: Initiate Sprint 11.

## Priority Order

1. Authentication, authorization, and security baseline.
2. Production persistence foundation.
3. CLI integration hardening.
4. Filesystem runtime completion.
5. Tool runtime safety and registry integration.
6. Provider system productionization.
7. Memory and retrieval production lifecycle.
8. Agent orchestration autonomy.
9. Production identity, secret management, and network guardrails.
10. Cross-platform web UI, dashboard, and interactive approval experience.
11. VS Code extension and dedicated CLI client.
12. Production deployment, CI/CD, observability, alerting, and rollback automation.

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
- Remaining: richer identity/group workflows, full audit actor propagation beyond current approval/operator-bound surfaces, bound approval identities for every approval family, and external secret manager integration.

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
- Remaining: production PostgreSQL driver packaging, explicit ordered migrations beyond the baseline, critical JSON-store repository migration, auth/approval/audit persistence, DB-backed process ownership leases for multi-worker CLI supervision, concurrency/indexing hardening, scheduled/remote backup automation, retention cleanup, and failure rollback tests for future migrations.

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
- Align Windows and POSIX host execution behavior with the documented command-policy contract so safe wrapper commands and tests behave consistently across platforms.
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
- Completed: BL-002b single-use bound approval IDs for approval-required command execution outside development/test mode, including command digest, cwd, timeout, requester, agent/task context, environment-key, policy-metadata, and expiry binding.
- Completed: BL-002c POSIX host execution parity for policy-approved `cmd /c` and `cmd.exe /c` wrappers by translating inspectable wrappers to `sh -c` after policy evaluation.
- Completed: BL-002d restart-resilient supervision metadata and lifecycle accuracy, including persisted supervisor and timeout metadata, starting/failed states, timeout/status/stale reasons, launch-intent persistence before `Popen`, failed-launch persistence, async nonzero failed status, same-supervisor cancellation race guards, POSIX cancellation escalation, stale orphan cancellation, and monotonic output chunk cursors after retention trimming.
- Completed: BL-002e JSON state corrupt-file quarantine and restore helpers for local JSON collections.
- Completed: BL-002f conservative prior-supervisor orphan termination after backend restart, including persisted process identity metadata, skipped/not-found/terminated/failed termination statuses, POSIX process-group termination, Windows `taskkill /T /F` termination, and stale lifecycle recording.
- Remaining: full process recovery/adoption with resumable output after backend restart and production multi-worker lifecycle/lease semantics backed by durable ownership leases.

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
- Completed: BL-003a command parsing and boundary hardening slice for cwd-aware policy evaluation, read-only path operand rootDir checks, symlink escape checks, shell-variable and parameter-expansion path checks, tilde path checks, Windows absolute/backslash path checks, Windows slash switch handling, and focused API/runtime/policy regressions.
- Completed: BL-003b safe approval review backend contract with `GET /cli/approvals/{approval_id}/review`, redacted review command, cwd/role/task/policy/environment-key context, HMAC digests, bound-execution warnings, direct-execute availability, explicit approve/deny decision reasons, shared approval/log secret redaction, and decision-reason secret redaction before persistence.
- Completed: BL-003c broader Windows/POSIX shell semantics validation for supported wrappers, including PowerShell `/Command` and abbreviated command flags, cmd combined `/c` switch forms, POSIX `sh`/`bash -c` script-argument boundaries, POSIX-translated `cmd` wrapper semantics, command-name escape decoding, PowerShell script-block flow scanning, Start-Process/launcher payload downgrade prevention, escaped protected state-file path checks, and PowerShell backtick-secret redaction.
- Remaining: interactive approval UI implementation scheduled in BL-010/Sprint 16. Full shell emulation and OS sandboxing remain out of scope for BL-003.

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

Current implementation status:
- Completed: BL-004a scoped MVP filesystem runtime completion with base64 binary read/write APIs, metadata, directory listing, approval-gated delete/move/copy/rename APIs, operation-specific policy decisions, rootDir and protected state-file checks for source and target paths, symlink escape blocking, payload-size limits via `DGENTIC_MAX_FILESYSTEM_BYTES`, no-overwrite defaults for copy/move/rename, recursive directory safeguards, filesystem audit events, and API/auth tests.
- Completed under BL-009w: bound filesystem approval records for approval-required filesystem decisions.
- Moved to follow-up backlog: persisted configurable filesystem policy rules, deeper platform-specific locked-file validation, and OS-level filesystem isolation.

### BL-005: Tool Runtime Safety And Registry Integration

Feature group: Tool runtime.

User value:
- Generated tools must be reusable by agents without becoming an unbounded execution risk.

Needs to be done:
- Integrate generated `localmcp/` tools with the SQLAlchemy tool registry.
- Add tool versioning policy and no-overwrite rules.
- Add stronger sandbox isolation for tool execution.
- Enforce tool permission level at execution time.
- Replace the caller-supplied tool `approved` boolean with approval/audit-bound execution semantics.
- Minimize inherited environment exposure and add output/log redaction for generated tool execution.
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

Current implementation status:
- Completed: BL-005a generated-tool SQL registry integration and execution permission hardening, including generated-tool duplicate preflight against SQL registry rows/interface signatures, generated-tool auto-registration in the SQLAlchemy registry, one registry row per generated tool name, no file writes on SQL duplicate conflicts, execution-time SQL registry deprecation blocking, permission conflict fail-closed behavior, and a reduced inherited subprocess environment.
- Completed: BL-005b tool execution output and audit redaction, including stdout/stderr/parsed-output redaction for common secret-shaped values, safer flag redaction after other secret assignments, and tool execution audit events that avoid raw output and payload content.
- Completed: BL-005c bound tool approval records, including redacted payload review records, payload/full-artifact-tree/approval HMAC digests, single-use approval IDs for approval-required tools outside development/test mode, approved-boolean rejection in production/staging, payload/context/artifact binding, decision reason and identity/context redaction, separate `approvals` capability for approve/deny when auth is enabled, and API review/approve/deny/list endpoints.
- Completed: BL-005d runtime reliability policy automation, including SQL registry usage counter sync on actual generated-tool execution, warning events after enough low-reliability evidence, automatic disabling for repeatedly weak tools, automatic deprecation for very low-reliability tools, and no counter increments for pre-execution approval/permission blocks.
- Completed: BL-005e per-tool local dependency import isolation, including validated manifest/generation dependency paths, Python isolated import mode for generated-tool subprocesses, host Python/virtualenv/library path environment stripping, standard `vendor` support, explicit dependency path fail-closed behavior, and symlink escape blocking before usage counters increment.
- Completed: BL-005f generated-tool process cleanup hardening, including explicit `Popen` launch controls, process-group/new-process-group startup where supported, process-tree cleanup on timeout, partial timeout output preservation, and Windows `taskkill` timeout fallback to process kill.
- Completed: BL-005g bounded generated-tool version migration policy, including explicit same-name migration through `overwrite=true`, strictly newer version enforcement, no file rewrites on conflict, in-place SQL registry row updates, SQL reliability counter reset, and SQL deprecation clearing for the new generated artifact version.
- Remaining: full OS/filesystem/network sandbox isolation, production package/dependency lifecycle management beyond local vendor paths, and parallel multi-version SQL registry rows if production use needs multiple active versions of one tool name.

### BL-006: Provider System Productionization

Feature group: Provider system.

User value:
- DGentic needs secure, observable model routing across local and external providers.

Needs to be done:
- Add external provider adapter contracts and at least one production-ready external adapter.
- Add secure credential storage or integration with environment/secret manager policy.
- Add credential masking and secret leak tests.
- Constrain provider network targets with allowlist or policy controls instead of unrestricted caller-supplied endpoints.
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

Current implementation status:
- Completed for Sprint 12 scope: Ollama and LM Studio health checks, local generation calls, scored routing, OpenAI-compatible external adapter support, streaming, retry/backoff, circuit breakers, approval controls, safe telemetry, pricing estimates, and role-routing are implemented for the backend MVP.
- Completed: BL-006a provider egress policy and safe telemetry, including exact provider base URL allowlist enforcement for generation and health probes, redirect blocking, safe display of configured base URLs, disabled/non-routable external placeholder behavior, generic malformed-upstream API failures, provider completion logs without raw content, and whitelisted response metadata with preserved numeric usage counters.
- Completed: BL-006b shared provider transport and bounded retry/backoff for generation, including deterministic retry policy settings, retry-after parsing/capping, generic rate-limit and upstream failure API mapping, safe retry metadata logging, no retries for policy/unsupported/malformed/ordinary 4xx failures, and no-retry health probes.
- Completed: BL-006c OpenAI-compatible external provider adapter boundary, including disabled-by-default HTTPS configuration, env-var-referenced bearer credential, explicit external-generation approval checks, model allowlist enforcement, provider-scoped egress allowlist, no live external health probe, external routing when configured and policy-allowed, privacy routing exclusion, and credential no-leak tests.
- Completed: BL-006d OpenAI-compatible streaming generation contract for LM Studio and the configured external OpenAI-compatible adapter, including upstream SSE parsing, downstream NDJSON events, pre-stream retry behavior, post-chunk sanitized error events, streaming provider advertisement, and no-content/no-secret logs.
- Completed: BL-006e bound provider approval records for configured external provider generation, including create/list/review/approve/deny APIs, approval-capability separation, safe prompt review metadata, request/config HMAC binding, development/test boolean bypass preservation, staging/production single-use `approval_id` enforcement for non-streaming and streaming calls, inter-process locked approval decisions/claims, and focused no-leak tests.
- Completed: BL-006f Ollama streaming generation support, including `/api/chat` stream payload construction, Ollama NDJSON parsing, terminal chunk handling, sanitized Ollama stream error mapping, provider capability advertisement, and runtime/API no-content/no-secret log tests.
- Completed: BL-006g provider request and upstream response payload validation, including bounded provider/model/message/options/timeout/token/temperature request shapes, supported chat-role enforcement, JSON-compatible option validation, provider error-object rejection, malformed success-payload rejection for Ollama/OpenAI-compatible responses, and generic no-secret API failure mapping.
- Completed: BL-006h normalized provider usage and static request-cost metadata, including non-streaming result usage/cost fields, streaming event usage/cost fields, provider completion log usage/cost metadata, and max-cost routing ceilings.
- Completed: BL-006i in-process provider circuit breaker behavior, including configurable per-provider failure thresholds/cooldowns, retry-exhausted failure counting, fast `503` responses while open, cooldown reset, successful-call reset, provider/base-URL isolation, half-open probe locking/cleanup, and approval-preserving external fail-fast behavior.
- Completed: BL-006j provider pricing catalog and advisory cost estimation, including bounded exact provider/model pricing configuration, usage-based external cost estimates for non-streaming and streaming responses, routing request estimates, invalid-catalog fail-closed behavior before transport, and no-content/no-secret log coverage.
- Completed: BL-006k external credential-resolution ordering hardening, including deferred external API-key/header construction until pricing/configuration/circuit/approval gates allow transport, approval preservation for fail-fast paths before transport eligibility, and runtime/API regressions that prove rejected paths do not read credential values.
- Completed: BL-006l provider role-routing policy, including bounded `DGENTIC_PROVIDER_ROLE_ROUTING` parsing, exact role-to-provider/model preferences, normal eligibility enforcement for configured role routes, fail-closed invalid configuration before probes, and no-silent-fallback behavior for blocked role routes.
- Moved to follow-up backlog: encrypted credential storage or secret-manager integration is tracked under BL-009/Sprint 15, durable multi-worker circuit state is tracked under BL-012/Sprint 18 deployment work, provider-specific billing reconciliation remains future operations/provider-specific work, and named provider-specific adapters beyond OpenAI-compatible chat completions are tracked under BL-013/Sprint 19.

### BL-013: Provider-Specific External Adapter Expansion

Feature group: Provider system follow-up.

User value:
- Operators may eventually want first-class adapters for specific AI providers when OpenAI-compatible endpoints are not enough.

Needs to be done:
- Select concrete provider targets based on product need, account availability, and API-contract differences.
- Add provider-specific request/stream/usage adapters only when they need behavior not covered by the generic OpenAI-compatible adapter.
- Prefer delivering provider-specific adapters as DGentic plugin packages when the adapter can preserve the shared provider, credential, network, approval, routing, telemetry, and test contracts.
- Preserve existing provider egress, approval, retry, circuit, pricing, role-routing, and safe telemetry controls.
- Add provider-specific usage/cost normalization and error mapping where APIs differ materially.

Acceptance criteria:
- A named adapter can be configured, routed, approved, called, streamed if supported, and monitored without leaking credentials or raw prompt/completion content.
- The adapter fails closed on invalid config, unsupported models, and policy-blocked routes.
- Tests cover adapter success, failure, streaming if supported, usage/cost metadata, approval paths, no-secret logs, and routing behavior.

Definition of Done:
- Tests, README, setup docs, architecture docs, and progress log are updated for each named adapter.
- Security review confirms no credential, prompt, or provider-controlled metadata leak paths.

Current implementation status:
- Not yet implemented: named Google AI, DeepSeek, Anthropic, Copilot, or other provider-specific adapters. The generic OpenAI-compatible external adapter remains the supported Sprint 12 external-provider path.

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

Current implementation status:
- Completed: BL-007a adds additive lifecycle metadata fields, a migration ledger entry, deterministic lifecycle preview/apply APIs, retention-aware promote/archive/soft-prune decisions, advisory compression-candidate detection, default retrieval exclusion for archived/soft-pruned records, and explicit `include_inactive` opt-in retrieval.
- Completed: BL-007b adds a vector backend contract, keeps the current SQLite/JSON vector backend as the default implementation, routes vector retrieval through the backend boundary, and adds a deterministic baseline retrieval performance smoke test.
- Completed: BL-007c adds deterministic metadata-description compression preview/apply APIs, threshold-based compression execution, lifecycle audit updates, `last_compacted_at`, and stored-embedding reindexing after compression.
- Completed: BL-007d adds additive retrieval attribution fields and deterministic score reasons for hybrid, vector, and metadata-only retrieval without changing existing ranking formulas.
- Closed for scoped backend MVP: Sprint 13 delivers the memory production lifecycle foundation without adding new infrastructure dependencies.
- Moved to follow-up backlog: pgvector production backend integration, scheduled lifecycle/compression jobs, full-content or LLM summarization beyond metadata descriptions, broader retrieval performance validation, deeper provenance, and configurable scoring policy.

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

Current implementation status:
- Completed: BL-008a backend orchestration control plane with persisted orchestration runs, DAG validation, dependency-aware scheduling into sub-agent briefs, machine-readable role-boundary decisions with canonical declared-path validation, blocker and follow-up records, retry escalation, bounded scheduling passes, API lifecycle endpoints under `/tasks/orchestrations`, closed-run mutation rejection, and DoD evidence gating before run closeout.
- Completed: BL-008b orchestration-bound filesystem action checks, including optional agent context compatibility, fail-closed partial/mismatched context, declared write-path enforcement for writes, read-only action allowance for running bound tasks, and serialized orchestration decisions in filesystem policy audit metadata.
- Completed: BL-008c orchestration-bound CLI action checks, including backward-compatible omitted/no-active-match context, fail-closed partial or mismatched active orchestration context, exact running task role/agent/task matching, command policy blocking before execution, and serialized orchestration decisions in command policy/API/run metadata.
- Completed: BL-008d orchestration-bound generated-tool action checks, including backward-compatible omitted/no-active-match context, fail-closed partial or mismatched active orchestration context, exact running task role/agent/task matching for tool approvals and execution, and serialized orchestration decisions in tool approval/review/result/API/audit metadata.
- Completed: BL-008e blocked orchestration task recovery for system-generated role-boundary and retry-exhaustion blockers, including explicit recovery endpoint, non-blank resolution notes, optional role and declared write-path correction, role-boundary revalidation, dependency-aware rescheduling, owner/admin scoping through existing orchestration access rules, manual blocker preservation, generic unsafe-recovery denials, and redacted recovery audit metadata.
- Completed: BL-008f explicit orchestration execution cycle that reconciles terminal spawned-agent lifecycle states into running task outcomes, preserves terminal agent audit timestamps, applies existing retry/blocker semantics, accumulates all tasks scheduled during a multi-task cycle, rejects closed-run cycles, and respects existing owner/admin orchestration access scoping.
- Completed: BL-008g admin-reviewed manual/security blocker resolution workflow, including a dedicated blocker resolution endpoint, non-blank redacted resolution notes, resolved blocker audit metadata, repeated/system blocker rejection, task unblocking without stranding when `reschedule=false`, optional immediate rescheduling, closeout over resolved blocker history, and admin-only API access when auth is enabled.
- Completed: BL-008h redacted dependency-output context handoff for spawned dependent agents, including objective redaction, bounded completed-dependency output summaries, preserved dependency ids in agent `required_data`, and API visibility through existing agent detail contracts without raw secret leakage.
- Completed: BL-008i bounded autonomous orchestration loop, including a dedicated loop endpoint/result contract, repeated cycle execution until waiting agents/blockers/all-complete/quiescence/max-iteration stop conditions, owner/admin scoping through existing orchestration access rules, and iteration bounds to avoid unbounded API work.
- Completed: BL-008j generated orchestration project-document sync, including automatic writes to `docs/progress/orchestration-runs.md` and `docs/planning/orchestration-follow-ups.md`, redacted run/blocker/follow-up text, resolved/completed item filtering for open backlog sections, symlink-aware repository path checks, and focused document-generation tests.
- Completed: BL-008k detached process-local background orchestration execution, including persisted execution records, start/list/get API endpoints, duplicate-active execution and foreground-loop conflict rejection, periodic process-local heartbeat renewal, age-based stale-supervisor reconciliation on start/poll, owner/status-conditional finalization, redacted failure persistence, and focused service/API tests.
- Completed: BL-008l opt-in SQL-backed orchestration shared memory, including explicit run/task `shared_memory_tags`, durable task-completion memory upsert, completed-task provenance checks, owner-scope filtering, active lifecycle filtering, stricter tag authorization, metadata tag filtering, and focused service/API tests.
- Completed: BL-008m detached orchestration execution cancellation, including a cancel endpoint, `cancelling`/`cancelled` execution states, queued-execution terminal cancellation, cooperative running-execution cancellation, active conflict preservation until worker finalization, owner/admin API scoping, and focused service/API tests.
- Completed: BL-008n orchestration operations summary, including an owner/admin-scoped summary endpoint with run/task/execution status counts, active/stale execution ids, unresolved blocker totals, open follow-up totals, and focused service/API tests.
- Completed: BL-008o shared-memory reuse policy and exposure hardening, including default owner-scoped reuse compatibility, optional run-scoped reuse policy on create/run contracts, same-run run-policy reuse, source- or consumer-side run-policy cross-run blocking, owner-boundary preservation, service-authored orchestration shared-memory metadata enforcement, tampered metadata exclusion, owner/admin-scoped orchestration agent and shared-memory metadata reads when auth is enabled, and focused service/API tests.
- Completed: BL-008p detached worker restart adoption/resume, including startup adoption of expired prior-supervisor `starting`/`running` executions for open runs, same execution id reuse, heartbeat/supervisor takeover, expired `cancelling` finalization, non-resumable/duplicate stale handling, start-failure finalization, and focused service/API tests.
- Completed: BL-008q production scheduling lease/fencing hardening, including JSON-backed run-level scheduler leases, persisted pending-to-running task claims before agent spawn, fixed agent ids for missing-agent repair, foreground advance/cycle/loop conflict responses while a detached execution owns the run, detached worker lease adoption/renewal/finalization, stale-update conflict detection for scheduling mutations, and spawn-failure rollback for unspawned claims.
- Remaining: none for the Sprint 14 backend MVP scope.

### BL-009: Production Identity, Secret Management, And Network Guardrails

Feature group: Cross-cutting production security and network policy.

User value:
- Operators need real identity records, token lifecycle controls, encrypted secrets, and network egress boundaries before DGentic can safely expose provider credentials, external services, UI approvals, and autonomous network-capable workflows.

Needs to be done:
- Add persisted operator identity records and role/capability assignment workflows.
- Hash tokens at rest and add token rotation, expiry, revocation, and audit trails.
- Bind approval decisions, direct executions, and audit events to authenticated actor identities.
- Add encrypted credential storage or external secret manager integration for provider and runtime credentials.
- Add network/domain guardrail policy for web retrieval, provider calls, generated tools, and future UI/API clients.
- Add allowlist, denylist, approval-required, and audit modes for outbound network access.
- Add secret masking and no-secret-response tests across auth, providers, approvals, logs, and settings.

Acceptance criteria:
- Operators can create, rotate, revoke, and expire tokens without storing raw token values.
- Approval records and audit logs identify the authenticated actor responsible for decisions and executions.
- Provider credentials are stored or referenced through a secure secret strategy and are never returned in API responses.
- Network access can be allowed, denied, or approval-required by domain/policy.
- Tests prove secrets are masked and network policy is enforced.

Definition of Done:
- Tests cover identity persistence, token hashing/rotation/expiry/revocation, actor-bound approvals/executions/audits, secret masking, credential storage boundaries, and network policy decisions.
- Security review validates identity, secret, and network exposure risk.
- README, setup docs, architecture docs, usage docs, and progress log are updated.

Current implementation status:
- Partially implemented: production/staging bearer-token capability gates, startup fail-closed auth validation, no-echo invalid token behavior, principal attachment on request state, persisted operator identity records with direct capability assignments, assigned `group_ids`, computed `effective_capabilities`, and active/inactive status, persisted operator group records with active/inactive capability bundles, persisted generated bearer-token records with salted PBKDF2 hashes, one-time raw token return, token listing without hashes, rotation, revocation, expiry, auth audit events, `DGENTIC_AUTH_TOKENS` compatibility, legacy persisted-token compatibility, persisted-token startup bootstrap after env-token removal, effective-capability-limited token issuance and runtime authorization, deactivated-operator token rejection, operator-id actor binding for persisted-token approval decisions, authenticated principal binding for direct CLI execution/runs, direct CLI approval execution, method-aware CLI and filesystem approval list/review/approve/deny separation under the `approvals` capability, filesystem and command-policy audit events, provider generation/streaming, generated-tool execution, task, agent, memory, tool, and session mutations, persisted credential references for env, local encrypted vault with supplied-key rotation, external-process sources, and HashiCorp Vault KV v2 secret-manager sources, deployment-managed credential reference records, OpenAI-compatible provider resolution through configured local or managed credential references without returning raw secret values, shell-free external-process credential resolver adapters with timeout/output bounds, first-class HashiCorp Vault KV v2 credential adapters with explicit base-URL allowlists and network-policy blocking before token lookup, provider-call network/domain guardrails with allow, deny, approval-required, audit decisions, web retrieval network guard contracts and bounded fetch runtime, single-use bound network approval records for approval-required provider and web-retrieval transport gates, single-use bound filesystem approval records for approval-required filesystem decisions, backend hook-policy records for command/filesystem/network guardrail escalation, managed settings precedence and policy surface locks, managed-source read-only credential, CLI, hook-policy, command-recipe, plugin-trust, and plugin-component records with managed-before-local precedence where applicable, configured Python socket network policy guardrail for generated-tool subprocesses, active-task verification for caller-supplied orchestration agent context across CLI, generated-tool, provider, and network approval surfaces, explicit CLI executable path rootDir boundary checks for direct commands, shell wrappers, and launcher payloads, bare executable workspace/PATH trust checks including `cmd /c` inner commands and Windows default PATHEXT candidates, command-specific path argument hardening for configured-safe tool directory flags, nested shell startup hardening checks, CLI environment override blocking for shell startup hooks, dynamic-loader preloads/library paths, and interpreter injection variables, git workflow checkpoints with checkpoint-bound commit/push/PR approval creation, checkpoint-bound direct commit/push/PR runners, execution-time workflow revalidation, GitHub CLI downgrade protection for broad configured-safe `gh` rules, and secret-shaped metadata redaction for operator display/role fields, operator group display/description fields, auth-token labels, credential-reference labels, and hook policy labels/reasons across responses, audit metadata, and new or mutated JSON state.
- Risk updated after Sprint 15 CLI host-boundary hardening: built-in read-only CLI path operands now receive cwd-aware rootDir checks, symlink escape checks, shell expansion checks, and Windows/POSIX path-shape regressions; explicit executable path tokens now fail closed when they resolve outside `rootDir` before configured rules can downgrade them; bare executables fail closed when launch resolution would use the workspace current directory, a `cmd /c` inner command, or a workspace `PATH` entry; configured-safe `git`, `npm`, `pnpm`, `yarn`, and `uv` path/directory flags fail closed when they resolve outside `rootDir`; mutating `git` subcommands remain approval-required even when broad configured-safe `git` rules exist; nested `cmd` invocations without `/d` and nested PowerShell/pwsh invocations without `-NoProfile -NonInteractive` fail closed before configured rules can downgrade them; CLI environment overrides now reject common startup-hook, preload, and interpreter injection keys; top-level `cmd` AutoRun and PowerShell profile/prompt behavior is suppressed at launch; broader host-boundary risks remain for non-built-in exfiltration commands and time-of-check/time-of-use workspace changes.
- Remaining: richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, additional external secret-manager adapters beyond HashiCorp Vault KV v2, managed policy-source controls beyond credential/CLI/hook/command-recipe/plugin-trust/plugin-component records and coarse surface locks, and OS-level/non-Python generated-tool egress isolation beyond the current Python socket guardrail.

### BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience

Feature group: Interface ecosystem.

User value:
- Users need a usable cross-platform interface for task submission, project/workspace management, sub-agent status, approvals, action logs, provider activity, memory, tools, settings, and runtime health instead of calling backend APIs directly.

Needs to be done:
- Build the web frontend shell for chat/task workflows, sub-agent progress, and rich output rendering.
- Add a project/workspace management line in the chat interface for adding a project or opening an existing project folder as the active `rootDir`.
- Add a project file explorer for the active `rootDir`, using existing guarded filesystem contracts and preserving root-boundary protections.
- Add an in-browser code editor for safe file viewing and editing inside the active project.
- Add an AI-change review surface, similar in spirit to Codex, that lets users inspect pending AI file edits, diffs, and affected paths before accepting or rejecting changes.
- Add interactive approval UI for CLI, filesystem, tool, provider, and network approval-required actions.
- Add settings UI for auth/session connection, providers, routing, filesystem boundaries, CLI policy, memory, tools, and agent blueprints.
- Add settings and dashboard surfaces for DGentic-native plugin bundles, command recipes, hook-style safety rules, managed policy sources, and git workflow checkpoints inspired by the Claude Code study.
- Add dashboard views for runtime status, action logs, provider usage, memory health, tool reliability, and task history.
- Add API client contracts, authentication handling, loading/error states, and responsive layouts.
- Add frontend testing strategy and smoke validation against the backend.

Acceptance criteria:
- A user can submit a task, inspect plan/progress, review approval-required actions, and view action logs through the UI.
- A user can add a new project or open an existing folder as the active project `rootDir`, and the UI clearly shows the current project context.
- A user can browse the active project files, open files in a code editor, and keep all read/write operations constrained to the active `rootDir`.
- A user can review AI-proposed file changes in a diff/change-review view before accepting, rejecting, or requesting follow-up work.
- Approval UI displays safe review metadata without secret values and records reviewer decisions.
- Settings and dashboard views cover the core backend surfaces needed for MVP operation.
- Plugin, command recipe, hook policy, and managed-settings views expose effective policy state without leaking secrets or permitting unaudited enablement.
- UI works on common desktop browser sizes and remains usable on smaller screens.

Definition of Done:
- Tests or smoke checks cover task flow, approval flow, auth handling, settings persistence/contracts, and dashboard data loading.
- README, setup docs, usage docs, architecture docs, and progress log are updated.
- PM confirms the root README not-yet-implemented entries for web frontend/dashboard and interactive approval UI can move to implemented or partially implemented status.

Current implementation status:
- Partially implemented: BL-010a same-origin web dashboard shell served at `/ui/`, including bearer-token session control, runtime health cards, task planning, orchestration summary, unified approval inbox for CLI/filesystem/network/provider/tool approvals with safe review plus approve/deny decisions, Git checkpoint visibility, provider/tool summary, effective settings view, log polling, focused static-serving/auth-boundary tests, and browser smoke validation. BL-010b adds a current configured `rootDir` workspace file browser and text editor using existing guarded `/filesystem/list`, `/filesystem/read`, and `/filesystem/write` APIs without introducing rootDir switching. BL-010c adds approved CLI approval execution when the review contract permits direct execution plus CLI run list/output polling. BL-010d adds read-only CLI policy rule, command recipe, hook policy, and plugin trust visibility panels. BL-010e adds active root context visibility, workspace root-reset controls, and structured Git checkpoint blockers/warnings/diff-stat review. BL-010f adds admin-gated project root preflight/register/list/detail/update APIs and dashboard project registry controls without activating roots. BL-010g adds admin-gated registered-project activation with in-process runtime `rootDir` switching, anchored state directory semantics, active CLI/orchestration/approval blockers, and dashboard Open controls. BL-010h adds a richer orchestration console with run selection, task graph/status detail, blockers, follow-ups, execution records, and cycle/loop/background start/cancel controls using existing backend contracts. BL-010i adds approval source/status filters and filtered summary counts for the unified approval inbox. BL-010j adds expandable per-task sub-agent briefs in the orchestration console by joining existing `/agents` data when the current token has access and failing softly when the `agents` capability is unavailable. BL-010k adds dashboard controls for running-task completion/failure/blocking, blocked-task recovery, blocker resolution, and required Definition of Done evidence closeout through existing orchestration mutation contracts. BL-010l adds dashboard orchestration run creation from objective, task graph JSON, DoD evidence keys, shared-memory tags, and shared-memory reuse policy through the existing create contract. BL-010m adds compact parent-child agent graph visibility for selected orchestration runs using existing visible agent records. BL-010n adds read-only memory lifecycle/freshness and SQL tool-registry reliability dashboards using existing metadata and registry APIs. BL-010o adds a guided orchestration task graph builder that writes the existing task JSON contract without backend/API expansion. BL-010p adds command recipe preview, approval, async run, and execute controls through existing recipe contracts. BL-010q adds read-only effective-settings grouping, managed settings and policy-lock summaries, policy-surface source/status counts, and an AI-change metadata summary for Git checkpoints using existing safe backend fields. BL-010r adds first editable CLI policy creation UI through the existing guarded local CLI policy API, with backend managed-lock enforcement preserved. BL-010s adds local CLI policy rule edit and enable/disable controls through the existing guarded PATCH API, with managed rules and locked policy surfaces rendered read-only. BL-010t adds checkpoint-bound commit, push, and PR approval creation from ready Git checkpoints through the existing guarded Git workflow approval APIs, with unified CLI approval inbox refresh after approval creation. BL-010u adds structured source-specific approval review summaries, warning/binding/digest visibility, and decision audit fields while keeping raw safe review JSON as a secondary detail. BL-010v adds checkpoint-bound raw Git diff review for tracked staged/unstaged patch sections with protected-path omission, redaction/truncation markers, and metadata-only audit logging. BL-010w adds dashboard direct-run controls for the existing checkpoint-bound commit, push, and PR runners with safe metadata result summaries. BL-010ax adds generated-tool governance controls that mark tools active, deprecated, or disabled through the existing `/tools/{name}/governance` contract without executing tools. BL-010ay adds read-only hybrid memory retrieval through the existing `/api/v1/memory/retrieve/hybrid` contract. BL-010az adds read-only memory lifecycle preview through the existing `/api/v1/memory/lifecycle/preview` contract. BL-010ba adds read-only memory compression preview through the existing `/api/v1/memory/compression/preview` contract. BL-010bb adds read-only Reliability drilldowns for memory metadata and SQL tool registry rows through existing safe detail `GET` contracts. BL-010bd adds confirmed memory lifecycle/compression apply controls through existing guarded apply contracts. BL-010be adds filesystem guardrail preflight checks through the existing `/guardrails/filesystem` contract. BL-010bf adds filesystem preflight-to-approval request controls through the existing `/filesystem/approvals` contract with fresh approval-required preflight gating. BL-010bg adds action-specific filesystem approval options/content fields, richer filesystem review digest detail, and client-side path/target/option validation before bound filesystem execution. BL-010bh adds guarded workspace file change preview/apply/revert controls through existing `/filesystem/write` semantics. BL-010bi adds task-chat execution transcript/status cards through existing task plan/execute contracts. BL-010bj adds task-chat fresh-plan orchestration creation through the existing `/tasks/orchestrations` create contract without starting cycle, loop, or detached execution records. BL-010bk adds task-chat orchestration context reuse for recent and newly created orchestration runs without adding execution authority.
- BL-010y adds non-CLI bound execution handoff panels for approved filesystem, network, provider, and tool approvals, showing the exact existing execution endpoint and a safe payload scaffold with `approval_id` and known review context.
- BL-010z adds a first chat-style task workflow in the dashboard task area, with a task composer, transcript, `/tasks/plan` submission, plan-card rendering, and optional `/tasks/execute` run handoff for the created plan.
- BL-010aa adds checkpoint-bound AI-change review decisions for loaded raw Git diff sections, including session accept/reject/clear controls, decision counts, copyable review evidence, and a client-side dashboard closeout pause when a section is rejected.
- BL-010ab adds editable non-CLI bound request payload panels with JSON validation, approval/network approval binding checks, direct execution for dashboard-callable filesystem/web retrieval/provider/tool endpoints, result output, approval refresh, and handoff-only handling for provider/tool network approvals.
- BL-010ac adds responsive/browser validation hardening for the dashboard, including constrained panel layout, wrapping mobile segmented approval filters, favicon 404 suppression, static CSS guards, and desktop/tablet/mobile Playwright smoke evidence with no horizontal overflow or browser errors.
- BL-010ad adds capped browser-local task-chat history, saved/restored status, Clear-backed history removal, corrupt/quota-tolerant local storage handling, and display-only restored plan cards so stale saved plans are not directly re-run.
- BL-010ae adds guided non-CLI bound request fields that sync into the canonical JSON editor, lock approval binding fields, support scalar/boolean/numeric/nested JSON values, and preserve raw JSON fallback plus handoff-only network approval behavior.
- BL-010af adds approval-dashboard backend contract scenario coverage across CLI, filesystem, network, provider, and tool inbox sources, verifies bound execution fields against backend consumers, pins the dashboard approval source matrix to backend routes, expands method-aware approval capability coverage for unified routes, and hardens CLI approval/run context redaction for secret-shaped requester, agent, and decision fields.
- BL-010ag adds the first browser-driven seeded approval scenario: a local browser opens `/ui/`, filters the unified inbox to CLI, reviews a backend-seeded pending CLI approval, approves it through the dashboard form, and verifies the refreshed approved review/direct-execute affordance.
- BL-010ah adds browser-driven seeded filesystem approval execution coverage: a local browser filters the unified inbox to filesystem, reviews and approves a backend-seeded delete approval, executes the guided bound filesystem payload through the dashboard, and verifies the executed review state plus deleted file. The slice also hardens the HTTP runtime root-switch guard so separate app event loops keep independent request barriers during browser validation.
- BL-010ai adds browser-driven seeded web-retrieval network approval execution coverage: a local browser filters the unified inbox to network, reviews and approves a backend-seeded web-retrieval approval, executes the guided bound fetch payload through the dashboard against a local text server, and verifies executed review state plus returned content.
- BL-010aj adds browser-driven seeded provider approval execution coverage: a local browser filters the unified inbox to provider, reviews and approves a backend-seeded external-provider approval, executes the guided bound generation payload through the dashboard using deterministic fake transport, and verifies executed review state plus returned content.
- BL-010ak adds browser-driven seeded generated-tool approval execution coverage: a local browser filters the unified inbox to tool, reviews and approves a backend-seeded generated-tool approval, executes the guided bound tool payload through the dashboard, and verifies executed review state plus returned payload value.
- BL-010al adds provider browser bound execution with network approval consumption: provider and generated-tool payload scaffolds expose optional `network_approval_id`, and the provider browser smoke fills an approved network approval before executing the bound provider generation request.
- BL-010am adds generated-tool browser bound execution with network approval consumption: a local browser fills an approved `generated_tool/socket_connect` network approval into the guided bound generated-tool payload, executes a socket-using generated tool, and verifies both tool and network approval records are executed.
- BL-010an adds persistent AI-change review artifacts: checkpoint-bound session decisions can be saved as metadata-only JSON records, listed/retrieved through guarded Git workflow APIs, restored into the dashboard for matching current checkpoints, and shown as stale without unblocking Git closeout when the checkpoint digest no longer matches.
- BL-010ao adds recursive guided non-CLI bound payload editors: guided fields now recurse into nested objects and arrays, edit nested JSON paths directly, keep approval binding fields locked, and preserve raw JSON fallback for complex payloads.
- BL-010ap adds local hook policy rule creation/edit/toggle controls through the existing guarded hook-policy APIs, keeps managed and plugin-owned rules read-only, respects managed `hook_policy` locks after settings refresh, and validates non-`any` match patterns before submission.
- BL-010aq adds a unified task-chat context stream that summarizes active project/root, task plans, task runs, pending approvals, and recent logs, then lets users insert compact context cards into the chat context composer without duplicating approval execution authority. BL-010bc extends that reusable context pattern to task-chat plan and run cards so operators can insert the exact plan context or deterministic run evidence back into the composer for follow-up turns. BL-010bd adds confirmed memory lifecycle and compression apply controls through the existing guarded backend contracts. BL-010be adds filesystem guardrail preflight controls without executing filesystem operations. BL-010bf adds pending filesystem approval creation from fresh approval-required preflights without executing filesystem operations. BL-010bg adds filesystem approval option/content details and bound execution validation without adding backend execution bypasses. BL-010bh adds guarded workspace file change preview/apply/revert controls through existing filesystem read/write contracts without adding Git patch mutation routes. BL-010bi adds task-chat execution transcript/status cards for deterministic `/tasks/execute` runs, including step-result summaries, context refresh, and follow-up evidence insertion. BL-010bj adds task-chat fresh-plan orchestration creation through `/tasks/orchestrations` while keeping orchestration execution explicit. BL-010bk adds bounded orchestration context insertion from recent context cards and created-run transcript cards.
- BL-010ar adds local command recipe creation/edit/toggle controls through the existing guarded command-recipe APIs, keeps managed/plugin-owned recipes read-only, respects managed `command_recipes` locks after settings refresh, and preserves preview/approval/run/execute actions for existing recipes.
- BL-010bl adds local network-domain policy rule creation/edit/toggle controls through guarded `/network/policy/rules` APIs, keeps managed network rules read-only and first in evaluation order, respects managed `network_policy` locks after settings refresh, and preserves network preflight/approval flows.
- BL-010bm adds task-chat approval handoff cards: pending approval context cards can open the exact safe approval review in the unified inbox while preserving backend approval contracts.
- BL-010bn adds memory lifecycle policy threshold controls so Reliability-panel preview/apply calls can tune archive, soft-prune, promote, and compression-candidate thresholds through existing backend lifecycle contracts.
- BL-010bo adds Git diff review decision filters, bulk visible accept/reject/clear actions, and per-section patch copy on top of existing checkpoint-bound raw diff review data without adding backend Git mutation authority.
- BL-010bp adds guarded Reliability-panel memory metadata quick-edit controls for tags, category, description, relevance, and retention policy through the existing metadata PATCH contract while keeping orchestration shared-memory metadata read-only.
- BL-010bq adds a Policy-panel plugin activation console for trusted plugin inert reference components plus declarative command recipe and hook-policy components, using existing guarded preview/list/install/disable routes and managed plugin activation locks.
- BL-010br adds Providers-panel approval request builders for external-provider generation and generated-tool execution approvals, using existing guarded backend approval creation routes and the unified approval inbox.
- BL-010bs adds Project-panel registered project metadata edit/archive/restore controls through the existing guarded project metadata PATCH route.
- Remaining: richer unified chat semantics beyond deterministic execution, explicit orchestration creation, reusable orchestration context, and approval-review handoff, actual Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations, richer AI-change review semantics beyond metadata-only review artifacts, UI-side diff decisions, and reviewer rationale notes, broader editable policy/settings surfaces for providers, routing, and filesystem policy, richer CLI policy lifecycle, deeper memory lifecycle/compression administration beyond the new guarded apply controls, threshold tuning, and metadata quick edits, deeper tools/plugins workflows beyond governance, trust, and activation controls, and persistent/multi-worker project activation semantics.

### BL-011: VS Code Extension And Dedicated CLI Client

Feature group: Developer interfaces.

User value:
- Developers need DGentic available from their editor and terminal so they can chat with the agent, trigger tasks, inspect agents, review approvals, and reuse generated tools without leaving their normal workflow.

Needs to be done:
- Scaffold a VS Code extension with command palette commands, backend connection settings, token configuration, and sidebar views.
- Add a DGentic chat view inside VS Code for task submission, plan/status updates, approvals, action logs, and follow-up instructions.
- Integrate with VS Code's native workspace/project model: use opened workspace folders as project `rootDir` candidates and require explicit selection when multiple folders are open.
- Integrate with VS Code's native Explorer and editor instead of rebuilding a separate project file explorer or code editor inside the extension.
- Add editor/context commands to send the active file, selected range, diagnostics, or workspace context to DGentic while preserving backend root-boundary checks.
- Show AI-proposed file edits through VS Code-native diff/editor review flows before applying changes, with clear accept/reject/follow-up controls.
- Add VS Code active agent status, memory/tool status, and approval review surfaces.
- Add generated-tool discovery or launch integration where safe.
- Build a dedicated CLI client for health checks, task planning/execution, approvals, CLI runs, providers, memory, tools, and logs.
- Add a terminal-first command recipe layer for repeated workflows such as sprint execution, approval review, provider checks, git commit/push/PR preparation, branch cleanup, PR review, and release closeout.
- Define an original DGentic plugin package format for reusable command recipes, agent blueprints, skills, hook policies, generated-tool references, MCP/tool adapter references, and documentation.
- Share or align API contracts between the web UI, VS Code extension, and CLI client where practical.
- Add packaging, installation, and smoke validation for both interfaces.

Acceptance criteria:
- VS Code users can connect to a DGentic backend, chat with DGentic, submit a task, inspect active agents, and review approval-required actions.
- VS Code users can bind the active DGentic project to an opened workspace folder as `rootDir`, with explicit selection for multi-root workspaces.
- VS Code users can use the native Explorer and editor for project navigation and file editing while DGentic actions remain constrained by backend rootDir/approval rules.
- VS Code users can review AI-proposed file changes in native diff/editor views before accepting, rejecting, or asking for revisions.
- CLI users can perform core operational workflows without manually crafting HTTP requests.
- CLI and VS Code command recipes are auditable, capability-gated, and use the same safe review contracts as backend approvals.
- Git workflow automation checks the dirty worktree, blocks obvious secret files, records test evidence when available, and asks for approval before destructive branch cleanup or remote publication.
- Tokens and sensitive settings are masked and not logged.
- Interface packaging and local install instructions are documented.

Definition of Done:
- Tests or smoke checks cover extension activation/connection, CLI command flows, auth handling, and approval review.
- README, setup docs, usage docs, architecture docs, and progress log are updated.
- PM confirms the root README not-yet-implemented entries for VS Code extension and dedicated CLI client can move to implemented or partially implemented status.

Current implementation status:
- Not yet implemented: VS Code extension with DGentic chat, native workspace/Explorer/editor integration, native AI-change diff review, and dedicated CLI client interface.

### BL-012: Production Deployment, CI/CD, Observability, And Rollback

Feature group: DevOps, release, and operations.

User value:
- Operators need repeatable builds, automated validation, deployable environments, monitoring, alerting, and rollback paths before DGentic can be run as a production service.

Needs to be done:
- Add CI pipeline for tests, lint, format, packaging, and release artifact checks.
- Add CI validation for DGentic plugin manifests, hook policy schemas, command recipe contracts, and dedicated CLI smoke flows.
- Add deployment infrastructure for local/staging/production environments.
- Add container or service packaging strategy where appropriate.
- Add runtime metrics for API latency, task/agent state, provider usage, CLI/tool runs, memory health, and errors.
- Add structured logs, dashboards, alerts, and operational runbooks.
- Add managed-settings deployment guidance for organization-wide auth, network, command, hook, plugin trust, provider, and approval policies.
- Add or validate production-safe CLI process ownership leases before enabling multi-worker deployments, or explicitly constrain deployment to a single worker until BL-001/BL-002 follow-up work lands.
- Add rollback automation and deployment smoke checks.
- Add release readiness gates for deployment validation and incident response.

Acceptance criteria:
- CI runs the documented quality gates and produces actionable results.
- A staging deployment can be created and smoke-tested reproducibly.
- Operators can see health, metrics, logs, and alerts for critical runtime surfaces.
- Operators can audit effective settings, plugin trust state, hook decisions, command recipe usage, PR review outcomes, and git checkpoint freshness.
- Rollback procedure is documented and verified through a smoke workflow.

Definition of Done:
- Tests or pipeline checks cover CI quality gates, package build, deployment smoke checks, metrics exposure, alert configuration, and rollback documentation.
- README, release docs, architecture docs, operations docs, and progress log are updated.
- PM confirms the root README not-yet-implemented entries for production deployment/CI/CD and runtime monitoring/metrics/alerting/rollback can move to implemented or partially implemented status.

Current implementation status:
- Partially implemented: release distribution artifacts, release notes, package builds, and local wheel smoke checks.
- Not yet implemented: production deployment infrastructure, CI/CD pipeline, runtime monitoring, metrics, alerting, multi-worker CLI deployment lease validation, and rollback automation.

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
- Closed: Sprint 9 completed the scoped CLI runtime hardening exit criteria for the MVP backend.
- Completed: BL-002a output chunk polling and stale-running reconciliation.
- Completed: BL-002b bound approval IDs for approval-required commands outside development/test mode.
- Completed: BL-002c POSIX execution parity for policy-approved `cmd /c` and `cmd.exe /c` wrappers.
- Completed: BL-002d restart-resilient supervision metadata and lifecycle accuracy for async CLI runs.
- Completed: BL-003 approval records expose matched policy review metadata.
- Completed: BL-003a cwd-aware command policy evaluation and read-only path operand rootDir boundary hardening.
- Completed: BL-003b safe approval review backend contract for UI consumers with decision reason auditing and secret redaction.
- Completed: BL-002e JSON state corrupt-file quarantine and restore helpers for local JSON collections.
- Completed: BL-003c broader Windows/POSIX shell semantics validation and hardening for supported wrappers, quoting, escaping, launcher payload, and protected state-file cases.
- Completed: BL-002f conservative post-restart orphan termination for prior-supervisor running records with matching process identity, including termination metadata exposed through run status/cancel contracts.
- Moved to follow-up backlog: full process adoption/resumable output after backend restart and production multi-worker lifecycle/lease semantics backed by durable ownership leases.

### Sprint 10: Filesystem Runtime Completion

Goal:
- Finish safe local file workflows with fine-grained policy.

Stories:
- BL-004: Filesystem Runtime Completion.

Exit criteria:
- Binary, delete, move, copy, and directory workflows exist with fine-grained policy.
- Filesystem security tests pass for traversal, symlinks, destructive actions, binary files, and audit logging.

Current Sprint 10 status:
- Closed: Sprint 10 completed the scoped MVP filesystem runtime exit criteria.
- Completed: BL-004a binary read/write, list, metadata, approval-gated delete/move/copy/rename, source/target rootDir checks, protected state-file blocking, symlink escape checks, payload-size limits, and filesystem audit coverage.
- Moved to follow-up backlog: persisted configurable filesystem policy rules, deeper platform-specific locked-file validation, and OS-level filesystem isolation.

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

Current Sprint 11 status:
- Closed: Sprint 11 completed the scoped generated-tool runtime safety and registry integration exit criteria for the MVP backend.
- Completed: generated-tool SQL registry auto-registration, duplicate preflight, no file writes on SQL duplicate conflicts, deprecated registry row blocking, permission conflict fail-closed behavior, and reduced inherited subprocess environment.
- Completed: tool execution stdout/stderr/parsed-output redaction and execution audit events without raw output or payload content.
- Completed: bound approval records for approval-required generated tools outside development/test mode, including payload/context/full-artifact-tree binding, safe review endpoints, and a separate `approvals` capability for approval decisions when auth is enabled.
- Completed: runtime reliability policy automation for actual generated-tool execution, including SQL usage sync, warning events, auto-disable, and auto-deprecation.
- Completed: per-tool local dependency import isolation for generated-tool execution.
- Completed: generated-tool process-group launch and timeout cleanup hardening.
- Completed: bounded generated-tool version migration policy for strictly newer same-name overwrites.
- Remaining: full OS/filesystem/network sandbox isolation, production package/dependency lifecycle management beyond local vendor paths, and parallel multi-version SQL registry rows if needed.

### Sprint 12: Provider Productionization

Goal:
- Add secure external provider support and streaming generation.

Stories:
- BL-006: Provider System Productionization.

Exit criteria:
- External provider adapter works through shared provider contracts.
- Credentials are protected.
- Streaming, retry, rate-limit, and routing tests pass.
- Completed so far: BL-006a protects local provider egress and telemetry before external credentials or adapters are introduced; BL-006b adds bounded retry/backoff through a shared provider transport; BL-006c adds a disabled-by-default OpenAI-compatible external adapter using env-referenced credentials and a model allowlist; BL-006d adds OpenAI-compatible streaming for LM Studio and the configured external adapter; BL-006e adds bound provider approval records for external generation in staging/production; BL-006f adds Ollama streaming; BL-006g adds provider request and upstream response payload validation; BL-006h adds normalized usage/cost metadata and max-cost routing ceilings; BL-006i adds in-process provider circuit breakers; BL-006j adds bounded provider/model pricing estimates for external usage and routing; BL-006k hardens external credential-resolution ordering so fail-fast paths avoid API-key lookup/header construction; BL-006l adds bounded role-to-provider/model routing preferences.

Current Sprint 12 status:
- Closed: Sprint 12 completed the scoped provider productionization exit criteria for the backend MVP.
- Moved to follow-up backlog: encrypted credential storage or secret-manager integration to Sprint 15, durable multi-worker circuit state to Sprint 18, provider-specific billing reconciliation to future operations/provider-specific work, and named provider-specific external adapters to Sprint 19 after a concrete provider target is selected.

### Sprint 13: Memory Production Lifecycle

Goal:
- Make memory durable, scalable, and self-maintaining.

Stories:
- BL-007: Memory And Retrieval Production Lifecycle.

Exit criteria:
- Production vector backend and migrations are implemented.
- Compression/summarization and lifecycle policies exist.
- Retrieval performance validation is recorded.

Current Sprint 13 status:
- Closed: Sprint 13 completed the scoped backend MVP memory production lifecycle.
- Completed: BL-007a SQL-backed lifecycle policy foundation.
- Completed: BL-007b vector backend abstraction and baseline retrieval performance smoke.
- Completed: BL-007c deterministic metadata compression execution.
- Completed: BL-007d retrieval attribution and score-reason explanations.
- Moved to follow-up backlog: pgvector production backend integration, scheduled lifecycle/compression runs, full-content or LLM summarization, broader performance validation, deeper provenance, and configurable scoring policy.

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

Current Sprint 14 status:
- Closed: BL-008a through BL-008q complete the backend orchestration control plane foundation plus filesystem, CLI, generated-tool runtime action binding, system-blocked task recovery, explicit and bounded-loop agent lifecycle reconciliation, manual/security blocker resolution, redacted dependency context handoff, generated project-document sync, detached process-local execution polling/cancellation/restart adoption, owner-scoped operations summary surfacing, opt-in SQL-backed shared memory handoff with owner or run-scoped reuse policy and API exposure hardening, and production scheduling lease/fencing hardening for the backend MVP.
- Completed: task graph creation/list/get/advance/update/cycle/loop/background-execution/cancel/summary/close/recover/blocker-resolution contracts, dependency scheduling with redacted context handoff, durable scheduler leases, task claims persisted before agent spawn, fixed agent ids for crash repair, spawn-failure rollback, foreground scheduler conflict responses while detached executions own a run, explicit shared-memory tags and SQL metadata handoff with completed-task provenance, owner scoping, active lifecycle filtering, tag authorization, owner/run reuse policy, service-authored metadata enforcement, tampered metadata exclusion, and owner/admin-scoped orchestration agent and shared-memory metadata reads, role-boundary blocking with canonical declared-path validation, retry escalation, follow-up creation, closed-run mutation rejection, bounded scheduling passes and loop iterations, process-local detached execution records with duplicate-active/foreground-loop conflict rejection, cooperative cancellation, heartbeat-based stale reconciliation, and startup adoption/resume for expired prior-supervisor executions, owner-scoped operations summary counts, orchestration-bound filesystem write checks, orchestration-bound CLI command policy/runtime checks, orchestration-bound generated-tool approval/execution checks for active agent context, recoverable blocker rescheduling, admin-reviewed manual/security blocker resolution, agent terminal-status reconciliation, generated progress/follow-up document sync, and DoD evidence close gates.
- Remaining before Sprint 14 can close: none.

### Sprint 15: Production Identity, Secrets, And Network Guardrails

Goal:
- Complete production identity, secret management, credential safety, actor-bound approvals, and network/domain guardrails.

Stories:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Current Sprint 15 status:
- Completed checkpoint: BL-009a persisted auth-token lifecycle is implemented and validated. This slice covers salted hash storage, create/list/rotate/revoke/expire APIs, one-time raw token return, active persisted-token startup bootstrap, env-token compatibility, safe auth audit events, inactive-token rotation rejection, expiry preservation on rotation, nonblank operator ids, and operator-id actor binding for persisted-token approval requesters and decisions.
- Completed checkpoint: BL-009b external credential references are implemented and focused-validation clean. This slice covers persisted references to externally managed credential locations, credential-reference capability gates, no raw secret-value storage, OpenAI-compatible provider credential-reference configuration, config-only provider listing/health/routing without secret-value lookup, and transport-time secret resolution.
- Completed checkpoint: BL-009c network/domain guardrails are implemented and focused-validation clean. This slice covers `DGENTIC_NETWORK_DOMAIN_POLICY`, exact and wildcard domain rules, `allow`, `deny`, `approval_required`, and `audit` modes, `/guardrails/network` decisions, provider egress enforcement before transport, and a dedicated `network` capability.
- Completed checkpoint: BL-009d persisted operator identity and assignment workflows are implemented and focused-validation clean. This slice covers `operators.json`, `/auth/operators` create/list/get/update APIs, role/display metadata, capability normalization, token issuance limited to active operator assignments, deactivated-operator token rejection, legacy persisted-token compatibility, and safe operator audit events.
- Completed checkpoint: BL-009e cross-surface identity/credential metadata redaction is implemented and focused-validation clean. This slice covers secret-shaped redaction for operator display/role fields, auth-token labels, and credential-reference labels before API responses, audit metadata, new persistence, and legacy-state mutation rewrites.
- Completed checkpoint: BL-009f credential resolver adapter plumbing is implemented and focused-validation clean. This slice covers env-reference compatibility plus shell-free `external_process` credential references, bounded adapter config, transport-time-only provider secret resolution, approval preservation on adapter failure, no-secret persistence/logging, and oversized adapter output rejection.
- Completed checkpoint: BL-009g authenticated audit actor propagation is implemented and focused-validation clean. This slice covers authenticated principal override for spoofed direct execution/generation requesters, cross-principal direct CLI approval execution blocking unless admin, and authenticated audit actors for filesystem, CLI policy, CLI runs, provider generation/streaming, generated tools, task, agent, memory, tool, and session mutation events.
- Completed checkpoint: BL-009h network approval records are implemented and focused-validation clean. This slice covers `network-approvals.json`, safe review/list/approve/deny APIs, HMAC-bound URL and policy digests, single-use provider transport claims through `network_approval_id`, authenticated requester/decider binding, and no-secret URL/query/context persistence.
- Completed checkpoint: BL-009i task-scoped orchestration agent-context verification is implemented and focused-validation clean. This slice adds shared active-task context verification for CLI, generated-tool, provider, and network approval surfaces, blocks partial or unmatched caller-supplied `agent_id`/`agent_role`/`task_id` while orchestration tasks are running, preserves omitted-context compatibility, and keeps provider/network approval digests bound to the verified context.
- Completed checkpoint: BL-009j generated-tool network policy guardrail is implemented and focused-validation clean. This slice validates the configured `DGENTIC_NETWORK_DOMAIN_POLICY` before generated-tool subprocess launch, passes only sanitized domain/mode rules to the child process, installs Python socket guards before generated tool imports run, allows `allow` and `audit`, and fails closed for `deny` or `approval_required` generated-tool Python socket attempts.
- Completed checkpoint: BL-009k local encrypted credential-vault references are implemented and focused-validation clean. This slice adds a `local_vault` credential source encrypted with operator-supplied `DGENTIC_CREDENTIAL_VAULT_KEY`, omits plaintext and ciphertext from API views and audit events, binds provider approvals to credential identity digests instead of plaintext, and preserves transport-time-only decryption plus approval preservation on missing, malformed, or wrong keys.
- Completed checkpoint: BL-009l CLI executable path host-boundary enforcement is implemented and focused-validation clean. This slice blocks explicit command executable paths that resolve outside `rootDir` before configured rules or approvals can downgrade them, including direct commands, shell-wrapped commands, PowerShell launcher payloads, Windows-style paths, and POSIX absolute paths on Windows hosts.
- Completed checkpoint: BL-009m CLI startup/preload environment override hardening is implemented and focused-validation clean. This slice extends controlled CLI environment overrides so shell startup hooks, dynamic-loader preload/library path variables, interpreter option/library injection variables, and `BASH_FUNC_`/`DYLD_` prefixed overrides fail validation before approval binding or subprocess launch.
- Completed checkpoint: BL-009n CLI approval reviewer capability separation is implemented and focused-validation clean. This slice keeps CLI approval creation and approved-command execution under `cli`, while list/review/approve/deny operations require the separate `approvals` capability when auth is enabled.
- Completed checkpoint: BL-009o CLI shell profile/AutoRun launch hardening is implemented and focused-validation clean. This slice suppresses top-level `cmd` AutoRun with `/d` and launches PowerShell/pwsh with `-NoProfile -NonInteractive` unless equivalent switches are already present, while preserving reviewed command strings and approval digests.
- Completed checkpoint: BL-009p bare executable workspace/PATH trust checks are implemented and focused-validation clean. This slice blocks bare executable launches before approval claim or subprocess start when the executable would resolve from the workspace current directory or from a `PATH` entry under `rootDir`, while preserving explicit reviewed executable paths inside `rootDir` for normal policy/approval handling.
- Completed checkpoint: BL-009q command-specific path argument hardening is implemented and focused-validation clean. This slice prevents configured-safe rules for `git`, `npm`, `pnpm`, `yarn`, and `uv` from downgrading directory/path flags that resolve outside `rootDir`; the same checkpoint also closes BL-009p review findings by checking `cmd /c` inner bare executables, always including Windows default PATHEXT candidates, and recording failed synchronous launch run records after approval claim.
- Completed checkpoint: BL-009r nested shell startup hardening checks are implemented and focused-validation clean. This slice prevents configured-safe rules from downgrading nested `cmd` invocations that omit `/d` or nested PowerShell/pwsh invocations that omit `-NoProfile -NonInteractive`, while preserving configured-safe behavior when hardened nested startup flags are explicit.
- Completed checkpoint: BL-009s operator group capability inheritance is implemented and focused-validation clean. This slice covers `operator-groups.json`, `/auth/operator-groups` create/list/get/update APIs, operator `group_ids`, response `effective_capabilities`, unknown-group mutation rejection, active-group capability inheritance for token issuance and runtime authorization, group deactivation/capability-reduction fail-closed behavior for existing tokens, and secret-shaped group metadata redaction in responses, state, and auth events.
- Completed checkpoint: BL-009t local credential-vault key rotation is implemented and focused-validation clean. This slice covers `POST /credentials/references/local-vault/rotate-key`, supplied current/new Fernet keys, one-transaction re-encryption of all persisted `local_vault` ciphertext including revoked records, env/external-process skip counts, wrong-key/malformed-ciphertext/same-key/invalid-key generic failure without partial writes, credentials capability enforcement, and counts-only no-secret audit metadata.
- Completed checkpoint: BL-009u plugin trust foundation is implemented and focused-validation clean. This slice covers backend-only discovery of direct `rootDir/plugins/[plugin_id]/dgentic-plugin.json` manifests, no plugin import/load/execution, SHA-256 digests over exact manifest bytes, redacted safe metadata summaries, `plugin-trust.json` trust/block persistence, stale trust detection on manifest byte changes, symlink/out-of-root/oversized/malformed manifest rejection, trust audit redaction, and `tools` capability enforcement for `/plugins`.
- Completed checkpoint: BL-009v hook policy foundation is implemented and focused-validation clean. This slice covers backend-only persisted `hook-policy-rules.json` records, `/guardrails/hooks/rules` CRUD under the `hooks` capability, command/filesystem/network surfaces, ordered matching with optional agent-role scoping, audited redacted hook decisions, command and network approval digest binding for hook-forced approval decisions, filesystem hook block enforcement, and report-only filesystem hook approval decisions until bound filesystem approval records exist.
- Completed checkpoint: BL-009w bound filesystem approval records are implemented and focused-validation clean. This slice covers persisted `filesystem-approvals.json` records, safe create/list/review/approve/deny APIs, single-use HMAC-bound approval IDs for approval-required filesystem decisions, production/staging rejection of the old `approved: true` bypass, path/target/write-payload/source-state/target-state/options/policy/hook/orchestration binding, filesystem hook `approval_required` enforcement, and method-aware filesystem approval reviewer capability separation.
- Completed checkpoint: BL-009x managed settings precedence foundation is implemented and focused-validation clean. This slice covers opt-in `DGENTIC_MANAGED_SETTINGS_FILE` loading, managed-over-environment supported runtime setting precedence, malformed/unknown/unsupported/oversized/secret-shaped fail-closed handling, unsupported bootstrap/secret field rejection, managed auth enablement over env disable, already-effective auth downgrade rejection, redacted source-attributed effective settings, managed-file SHA-256 digest reporting, and admin-gated `GET /settings/effective`.
- Completed checkpoint: BL-009y command recipe execution contracts are implemented and validation-clean. This slice covers persisted `command-recipes.json` records, safe placeholder and parameter contracts, secret-shaped template/default/value rejection, policy-preview expansion, synchronous recipe execution, recipe approval creation, asynchronous recipe runs, usage auditing, auth principal binding, and explicit rejection of recipe-level `approved` bypasses in favor of existing CLI `approval_id` flows.
- Completed checkpoint: BL-009z plugin command recipe activation governance is implemented and focused-validation clean. This slice covers trusted-current-manifest-only activation, declarative JSON command recipe component paths, root-bound and symlink-rejected component reads, component SHA-256 digest provenance, plugin-owned recipe disable/reinstall, `tools` plus `cli` activation authorization, manual plugin-owned recipe mutation rejection, and fail-closed recipe preview/execute/approval/run behavior after plugin trust, manifest digest, component digest, or activation-status drift.
- Completed checkpoint: BL-009aa git workflow safety checkpoints are implemented and focused-validation clean. This slice covers the read-only `POST /cli/git/checkpoints` endpoint, shell-free root-bounded git inspection for commit/push/PR readiness, staged/unstaged/untracked and diff-stat metadata, checkpoint digests, test-evidence gates, protected branch/file blockers, secret-shaped staged-addition blockers without raw secret exposure, authenticated requester binding, no-network PR warnings, and command-policy protection so configured-safe `git` rules cannot downgrade mutating git commands.
- Completed checkpoint: BL-009ab managed policy surface locks are implemented and focused-validation clean. This slice covers `managed_policy_locks` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only enforcement, fail-closed validation of unknown lock surfaces, and mutation locks for CLI policy rules, command recipes, hook policy rules, plugin trust decisions, and plugin command recipe install/disable while preserving read/preview/evaluation routes.
- Completed checkpoint: BL-009ac checkpoint-bound git commit approval creation is implemented and validation-clean. This slice covers `POST /cli/git/commit-approvals`, fresh ready commit checkpoint digest matching, internal diff-content hashes inside checkpoint digests, single-line non-secret commit-message validation, authenticated requester binding, pending CLI approval creation for generated `git commit -m ...` commands, and no direct `git commit`, `git push`, `gh`, or network PR execution.
- Completed checkpoint: BL-009ad checkpoint-bound git push approval creation is implemented and validation-clean. This slice covers `POST /cli/git/push-approvals`, fresh ready push checkpoint digest matching, upstream remote URL digest binding, ahead/behind safety gates, rejection of caller-supplied remote/branch/refspec/flag payloads, workflow-bound CLI approval metadata, and execution-time git workflow revalidation before approval claim.
- Completed checkpoint: BL-009ae checkpoint-bound guarded PR approval creation is implemented and focused-validation clean. This slice covers `POST /cli/git/pr-approvals`, fresh ready PR checkpoint digest matching, upstream remote URL digest binding, already-pushed/current-with-upstream gates, bounded single-line non-secret title/body/base validation, rejection of caller-supplied command/remote/head/flag payloads, workflow-bound CLI approval metadata with PR intent digests, execution-time git workflow revalidation before approval claim, and command-policy protection so broad configured-safe `gh` rules cannot downgrade GitHub CLI commands.
- Completed checkpoint: BL-009af trusted declarative plugin hook-policy activation governance is implemented and focused-validation clean. This slice covers trusted-current-manifest-only activation for declarative JSON hook-policy components, single-rule or list payloads, root-bound and symlink-rejected bounded component reads, component SHA-256 digest provenance, plugin-owned hook-policy disable/reinstall workflows, `tools` plus `hooks` activation authorization, manual plugin-owned hook-policy mutation rejection, `plugin_hook_policies` managed locks, and no plugin hook-code import/load/execution.
- Completed checkpoint: BL-009ag managed CLI policy rule precedence is implemented and focused-validation clean. This slice covers `managed_cli_policy_rules` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only loading, fail-closed validation, source-attributed managed rules in `GET /cli/policy/rules`, managed-before-local evaluation order, API read-only managed records, local rule coexistence when `cli_policy` is not locked, no local persistence of managed records, and bound approval invalidation when managed rule identity changes.
- Completed checkpoint: BL-009ah managed hook-policy rule precedence is implemented and focused-validation clean. This slice covers `managed_hook_policy_rules` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only loading, fail-closed validation, source-attributed managed rules in `GET /guardrails/hooks/rules`, managed-before-local/plugin evaluation order, API read-only managed records, local and plugin rule coexistence when the corresponding managed locks are not active, no local persistence of managed records, plugin install collision rejection for managed IDs, and bound approval invalidation when managed hook rule identity changes.
- Completed checkpoint: BL-009ai web retrieval network guard contract is implemented and focused-validation clean. This slice covers transport-free `web_retrieval`/`fetch` network policy checks, approval creation, approval-claim authorization, sanitized URL and policy-reason responses, hook-policy escalation, active-task context checks, and `network` capability enforcement for future retrieval clients without implementing crawling or remote content fetching.
- Completed checkpoint: BL-009aj plugin reference component preview governance is implemented and focused-validation clean. This slice covers trusted-current-manifest-only, digest-only previews for inert agent blueprint, skill, generated-tool, and documentation component references, with safe relative paths, root-bound and symlink-rejected bounded reads, component SHA-256 digests, component sizes, duplicate-reference rejection, no component content exposure, `tools` capability enforcement, and no parsing/importing/indexing/installing/loading/execution of referenced content.
- Completed checkpoint: BL-009ak inert plugin reference component registry governance is implemented and focused-validation clean. This slice covers `plugin-components.json` metadata-only install/list/disable records for trusted current agent blueprint, skill, generated-tool, and documentation references, stable component ids, component digest/size provenance, disable/reinstall workflows, `plugin_components` managed mutation locks, and no parsing/importing/indexing/loading/execution of referenced content.
- Completed checkpoint: BL-009al managed plugin trust records are implemented and focused-validation clean. This slice covers `managed_plugin_trust_records` in `DGENTIC_MANAGED_SETTINGS_FILE`, exact-manifest-digest trusted/blocked decisions, managed trust-source reporting, managed-over-local trust precedence, stale trust surfacing after manifest drift, fail-closed parser validation, local trust mutation rejection for managed plugin ids, and no local `plugin-trust.json` writes for managed trust.
- Completed checkpoint: BL-009am generated-tool network approval consumption is implemented and focused-validation clean. This slice covers `ToolExecutionRequest.network_approval_id`, API/runtime plumbing for generated-tool execution, parent-side single-use network approval claims for `generated_tool`/`socket_connect`, explicit host-plus-port approval requirements, sanitized child-runner host/port handoff, approval-required Python socket allowance for the approved endpoint, wrong-surface/pending/reused/policy-drift rejection before subprocess launch, and audit/result metadata for consumed network approvals.
- Completed checkpoint: BL-009an managed command recipes are implemented and focused-validation clean. This slice covers `managed_command_recipes` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only loading, fail-closed validation for malformed records, duplicate normalized fields and ids, unsafe templates, and secret-shaped text, source-attributed managed recipes in `GET /cli/recipes` and `GET /cli/recipes/{recipe_id}`, existing preview/execute/approval/run route support, local/plugin managed-id collision rejection, no local `command-recipes.json` writes for managed records, usage audit events without mutating managed state, and filtering of locally persisted rows that spoof `source: "managed"`.
- Completed checkpoint: BL-009ao managed plugin component records are implemented and focused-validation clean. This slice covers `managed_plugin_component_records` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only loading, fail-closed validation for malformed records, duplicate normalized fields and component ids, invalid paths, invalid digests, invalid status, and secret-shaped metadata, source-attributed managed records in `GET /plugins/{plugin_id}/components`, managed-over-local component overlay, local managed-source spoof filtering, read-only install/disable rejection for managed plugin ids, no local `plugin-components.json` writes for managed records, and `stale`/`drifted` provenance reporting.
- Completed checkpoint: BL-009ap guarded web retrieval fetch runtime is implemented and focused-validation clean. This slice covers `POST /web-retrieval/fetch`, explicit network-policy rule requirements, GET-only fetches with fixed non-secret headers, disabled proxies and redirects, URL credential/fragment rejection, text-like content enforcement, configured timeout/byte caps, truncation reporting, single-use `web_retrieval`/`fetch` approval consumption, stray approval-id rejection for `allow`/`audit`, active-task context checks, web retrieval audit events, sanitized URL/policy metadata, and no fetched body text in logs.
- Completed checkpoint: BL-009aq managed credential reference records are implemented and focused-validation clean. This slice covers `managed_credential_references` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only loading, fail-closed validation for stable ids, supported `env` and `external_process` source metadata, purpose/status, and secret-shaped metadata, source-attributed records in `GET /credentials/references`, managed-over-local id shadowing, local managed-source spoof filtering, read-only revoke behavior, provider runtime use through `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF`, and no local `credential-references.json` writes for managed records.
- Completed checkpoint: BL-009ar direct git commit runner is implemented and focused-validation clean. This slice covers `POST /cli/git/commit-runs`, fresh ready commit checkpoint digest revalidation, bounded single-line non-secret commit-message validation, shell-free local `git commit -m ...`, repository hook isolation, GPG-signing disablement, no CLI approval creation, safe commit-message digest audit metadata, no raw stdout/stderr response, protected-file/secret-shaped staged-addition blocking through the checkpoint contract, and `cli` capability enforcement with authenticated requester binding.
- Completed checkpoint: BL-009as direct git push runner is implemented and focused-validation clean. This slice covers `POST /cli/git/push-runs`, fresh ready push checkpoint digest revalidation, clean non-protected branch and ahead/behind gates, configured upstream remote URL digest binding, shell-free checkpoint-derived remote/refspec execution, pre-push hook isolation, push GPG-signing disablement, no caller-supplied remote/refspec/flag payload, no CLI approval creation, safe ahead/behind audit/result metadata, no raw remote URL/output exposure, and `cli` capability enforcement with authenticated requester binding.
- Completed checkpoint: BL-009at direct git PR runner is implemented and focused-validation clean. This slice covers `POST /cli/git/pr-runs`, fresh ready PR checkpoint digest revalidation, already-pushed and current-with-upstream gates, bounded single-line non-secret title/body/base validation, shell-free constrained `gh pr create` argv execution with checkpoint-derived `--head`, explicit GitHub CLI token environment requirements, isolated `GH_CONFIG_DIR`, no caller-supplied remote/head/flag/template/reviewer payload, no CLI approval creation, strict sanitized PR URL extraction, safe title/body/URL digest metadata, no raw stdout/stderr/token/remote URL exposure, and `cli` capability enforcement with authenticated requester binding.
- Completed checkpoint: BL-009au HashiCorp Vault KV v2 credential adapter is implemented and focused-validation clean. This slice covers `secret_manager` credential references, `credential_secret_manager_adapters`, `credential_secret_manager_allowed_base_urls`, local and managed secret-manager reference metadata, Vault KV v2 GET resolution at provider/runtime transport time, explicit base-URL allowlist checks, deny/approval-required network-policy blocking before token lookup, proxy/redirect-disabled Vault HTTP transport, sanitized environment token lookup, bounded response reads, KV field validation, no raw Vault token/secret persistence, and provider approval preservation on pre-transport credential failures.
- Completed checkpoint: BL-009av managed network-domain policy rule records are implemented and focused-validation clean. This slice covers `managed_network_domain_policy_rules` in `DGENTIC_MANAGED_SETTINGS_FILE`, managed-only loading, fail-closed validation for stable ids, domains, modes, priorities, enabled flags, unknown fields, duplicates, and secret-shaped text, managed-before-local network policy evaluation, safe `matched_rule_id`/`matched_rule_source` decision metadata, canonical effective-policy approval drift binding, generated-tool subprocess handoff without managed ids/reasons, provider/runtime enforcement, and generic network guardrail URL/reason redaction.
- Closed safe checkpoint: Sprint 15 backend security MVP is closed at BL-009av so user-facing Sprint 16 and Sprint 17 work can start. Remaining Sprint 15 items stay on the backlog as deferred backend security follow-ups, not cancelled scope.
- Remaining after BL-009av: richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, additional secret-manager adapters beyond HashiCorp Vault KV v2, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, and managed policy-source controls beyond credential/CLI/hook/network/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks.
- Claude Code study incorporation: remaining Sprint 15 security work should also shape managed-settings precedence, plugin installation governance, command recipe contracts, and guarded git/PR workflow automation rather than treating these as UI-only features.

Exit criteria:
- Tokens are hashed at rest and support rotation, expiry, and revocation.
- Approval decisions and audit events are bound to authenticated actor identities.
- Provider/runtime credentials use encrypted storage or an external secret manager strategy.
- Network/domain guardrails can allow, block, audit, or require bound approval records for approval-required provider decisions by policy.
- Secret masking and no-secret-response tests pass across auth, credentials, approvals, providers, logs, and settings.

### Sprint 16: Cross-Platform UI And Approval Dashboard

Goal:
- Build the cross-platform web frontend, operational dashboard, settings surfaces, and interactive approval experience.

Stories:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Current Sprint 16 status:
- Active: BL-010a same-origin dashboard shell, BL-010b current-root workspace file browser/editor, BL-010c CLI approval execution/run-output visibility, BL-010d read-only policy/plugin visibility, BL-010e active root context plus structured Git checkpoint review, BL-010f project registry/root preflight, BL-010g safe registered-project activation, BL-010h richer orchestration console, BL-010i approval source/status filtering, BL-010j per-task sub-agent briefs, BL-010k orchestration recovery/closeout controls, BL-010l orchestration run creation, BL-010m sub-agent graph visibility, BL-010n memory/tool reliability dashboards, BL-010o guided task graph builder, BL-010p command recipe actions, BL-010q settings/policy/Git review summaries, BL-010r CLI policy creation UI, BL-010s CLI policy edit/toggle UI, BL-010t Git checkpoint approval actions, BL-010u structured approval review summaries, BL-010v checkpoint-bound raw Git diff review, BL-010w checkpoint review-to-run Git actions, and BL-010x through BL-010bz are implemented and validation-clean. These slices provide the first user-facing UI surface for task planning, Task Chat provider replies with selectable message roles and provider approval request handoff, reusable task-chat plan/run/orchestration/memory/provider-response context and evidence controls, task-chat execution transcript/status cards, fresh task-chat plan to orchestration-run creation, task-chat approval review handoff, workspace file browsing/editing plus guarded apply/revert controls inside the active `rootDir`, active root context visibility, project root preflight, registration, metadata edit/archive/restore controls, and guarded Open flows, guided orchestration creation, orchestration summary/detail with task graph, expandable agent brief detail, parent-child agent graph detail, task update/recovery/blocker resolution/closeout controls, execution controls, memory/tool reliability summaries, active memory context cards, read-only hybrid memory retrieval, lifecycle preview/apply, compression preview/apply, memory/tool detail drilldowns, guarded memory metadata quick-edit controls, and memory detail/retrieval Use In Task Chat controls, approval review/decisions/filtering with structured warning/binding/digest/audit context, approved CLI execution, command recipe preview/approval/run/execute controls plus local command recipe create/edit/toggle controls, local plugin trust/block controls plus trusted-plugin activation controls, network policy preflight checks and approval requests, filesystem guardrail preflight checks and approval requests with action-specific approval details, provider and generated-tool approval request creation, provider generation and streaming execution with optional bound provider/network approvals, filesystem bound-execution path/target/option validation, CLI run output inspection, structured Git checkpoint blockers/warnings/diff-stat review plus AI-change metadata summary, checkpoint-bound raw Git diff review with decision filters, bulk visible decisions, and reviewer rationale notes in metadata-only saved artifacts, checkpoint-bound commit/push/PR approval creation, and direct checkpoint-bound Git run controls, provider/tool summaries, provider health checks, provider routing preview, generated-tool governance controls, policy/plugin visibility with source/status summaries, local CLI, hook policy, and network policy rule creation/edit/toggle controls, task-chat context cards, grouped effective settings with managed-field and lock summaries, and logs while preserving backend approval/auth/filesystem/CLI/policy boundaries.
- BL-010bl update: local network policy rule editing is implemented and validation-clean; the dashboard can create, edit, and toggle local network-domain policy rules while managed rules and managed `network_policy` locks stay read-only.
- BL-010bm update: task-chat approval handoff cards are implemented and validation-clean; pending approval context cards can open the exact safe approval review with unified-inbox filters synchronized.
- BL-010bn update: memory lifecycle policy threshold controls are implemented and validation-clean; the Reliability panel can tune archive, soft-prune, promote, and compression-candidate policy thresholds for preview/apply calls through the existing lifecycle API contracts.
- BL-010x update: richer task plan/run UI is implemented and validation-clean; the dashboard task planner now renders actionable plan cards with step detail, context chips, related deterministic task-run history, and a Run Plan action bound to the existing `/tasks/execute` API.
- BL-010y update: non-CLI bound execution handoff UI is implemented and validation-clean; approved filesystem, network, provider, and tool reviews now show bound execution endpoints and payload scaffolds without bypassing existing backend approval binding.
- BL-010z update: first chat-style task workflow is implemented and validation-clean; the dashboard task area now has a transcript-based composer that creates plans through `/tasks/plan`, renders the created plan, and can immediately run it through `/tasks/execute`.
- BL-010aa update: session AI-change review decisions are implemented and validation-clean; loaded Git diff sections can be accepted, rejected, cleared, summarized, and copied as review evidence, with rejected sections pausing dashboard Git approval/direct-run controls.
- BL-010ab update: non-CLI bound request editor/execution UX is implemented and validation-clean; approved non-CLI review panels now support editable JSON payloads, binding validation, dashboard-callable execution, result output, and approval refresh while keeping provider/tool network approvals as handoff-only payloads.
- BL-010ac update: responsive/browser validation hardening is implemented and validation-clean; dashboard panels now shrink inside mobile viewports, approval status filters wrap without page overflow, favicon requests no longer create browser 404 noise, and Playwright desktop/tablet/mobile smoke checks pass with no overflow, console errors, page errors, or failed requests.
- BL-010ad update: local task-chat history is implemented and validation-clean; the dashboard restores capped transcript history from browser storage, clears saved history from the Clear control, handles corrupt or unavailable local storage without breaking the page, keeps bearer tokens in session storage, and restores saved plan cards as display-only history.
- BL-010ae update: guided non-CLI bound request fields are implemented and validation-clean; approved non-CLI review panels now render top-level typed controls for scaffold payload fields, sync edits into the canonical JSON payload, lock binding fields, and keep provider/tool network approvals as handoff-only payloads.
- BL-010af update: approval dashboard contract coverage is implemented and validation-clean; backend/API tests now seed all five approval inbox sources, exercise safe list/review/approve contracts, validate bound execution fields against CLI/filesystem/provider/network/tool consumers, pin the dashboard source matrix to backend routes, and verify method-aware approval capability splits. The QA slice also exposed and fixed CLI approval/run context redaction so secret-shaped requester, agent, and decision text is not echoed in CLI approval records or run results.
- BL-010ag update: browser-driven seeded CLI approval coverage is implemented and validation-clean; a dependency-light browser smoke test starts the FastAPI UI, launches the installed Chromium-family browser through DevTools, filters the approval inbox to CLI, reviews a seeded approval, approves it through the dashboard, and verifies the approved review state plus direct-execute control.
- BL-010ah update: browser-driven seeded filesystem approval execution coverage is implemented and validation-clean; the dependency-light browser smoke test now also filters to filesystem, reviews and approves a seeded delete approval, executes the guided bound filesystem payload, verifies executed status, and confirms the target file is removed. The HTTP request barrier now uses event-loop-scoped locks so repeated local browser servers do not share a stale async lock across test event loops.
- BL-010ai update: browser-driven seeded web-retrieval network approval execution coverage is implemented and validation-clean; the dependency-light browser smoke test now also filters to network, reviews and approves a seeded web-retrieval approval, executes the guided bound fetch payload against a local text server, verifies executed status, and confirms the returned content is shown.
- BL-010aj update: browser-driven seeded provider approval execution coverage is implemented and validation-clean; the dependency-light browser smoke test now also filters to provider, reviews and approves a seeded provider approval, executes the guided bound generation payload through deterministic fake transport, verifies executed status, and confirms the returned content is shown.
- BL-010ak update: browser-driven seeded generated-tool approval execution coverage is implemented and validation-clean; the dependency-light browser smoke test now also filters to tool, reviews and approves a seeded generated-tool approval, executes the guided bound tool payload, verifies executed status, and confirms the returned payload value is shown.
- BL-010al update: provider browser bound execution with network approval consumption is implemented and validation-clean; provider/tool scaffold payloads now expose optional `network_approval_id`, and the provider browser smoke consumes an approved network approval while executing the provider request.
- BL-010am update: generated-tool browser bound execution with network approval consumption is implemented and validation-clean; the browser smoke now fills an approved socket network approval into the generated-tool payload, executes the socket-using generated tool, and verifies both approval records are executed.
- BL-010an update: persistent AI-change review artifacts are implemented and validation-clean; the dashboard can save metadata-only decision artifacts for loaded raw diff reviews, list saved artifacts, apply artifacts only when their checkpoint digest matches the current review, and render stale artifacts as non-unblocking history.
- BL-010ao update: recursive guided non-CLI bound payload editing is implemented and validation-clean; nested provider/tool payload objects and arrays now render as expandable guided groups whose scalar controls sync back into the canonical JSON editor.
- BL-010ap update: local hook policy editing is implemented and validation-clean; the dashboard can add, edit, and enable/disable local hook policy rules while rendering managed/plugin-owned records and managed `hook_policy` locks as read-only.
- BL-010aq update: unified task-chat context stream is implemented and validation-clean; the task-chat panel now shows active root, task/run counts, pending approvals, latest activity, and insertable context cards for recent plans, runs, approvals, and log events.
- BL-010ar update: local command recipe editing is implemented and validation-clean; the dashboard can add, edit, and enable/disable local command recipes while rendering managed/plugin-owned records and managed `command_recipes` locks as read-only.
- BL-010as update: local plugin trust controls are implemented and validation-clean; the dashboard can trust or block local plugin manifests while rendering managed plugin trust records and managed `plugin_trust` locks as read-only.
- BL-010at update: network policy preflight is implemented and validation-clean; the dashboard can check generic and web-retrieval network policy decisions through existing read-only backend contracts.
- BL-010au update: network approval requests are implemented and validation-clean; the dashboard can create a pending generic or web-retrieval network approval from a fresh `approval_required` preflight result.
- BL-010av update: provider health checks are implemented and validation-clean; the dashboard can run existing per-provider health checks and render availability/model details.
- BL-010aw update: provider routing preview is implemented and validation-clean; the dashboard can preview provider/model routing decisions through the existing `/routing/decide` contract.
- BL-010ax update: generated-tool governance controls are implemented and validation-clean; the dashboard can mark generated tools active, deprecated, or disabled through the existing `/tools/{name}/governance` contract.
- BL-010ay update: read-only hybrid memory retrieval is implemented and validation-clean; the dashboard can search memory from the Reliability panel through the existing `/api/v1/memory/retrieve/hybrid` contract.
- BL-010az update: memory lifecycle preview is implemented and validation-clean; the dashboard can preview lifecycle recommendations from the Reliability panel through the existing `/api/v1/memory/lifecycle/preview` contract without applying changes.
- BL-010ba update: memory compression preview is implemented and validation-clean; the dashboard can preview deterministic compression candidates from the Reliability panel through the existing `/api/v1/memory/compression/preview` contract without applying changes.
- BL-010bb update: read-only Reliability detail drilldowns are implemented and validation-clean; the dashboard can open memory metadata and SQL tool registry details through existing `GET /api/v1/memory/metadata/{id}` and `GET /api/v1/tools/registry/{id}` contracts without calling lifecycle/compression apply, metadata mutation, or tool mutation routes.
- BL-010bc update: task-chat follow-up context controls are implemented and validation-clean; plan cards can insert bounded plan context and run rows can insert deterministic run evidence back into the chat context composer without adding new backend mutation paths.
- BL-010bd update: memory lifecycle and compression apply controls are implemented and validation-clean; the dashboard can confirm and apply lifecycle or compression results through the existing `/api/v1/memory/lifecycle/apply` and `/api/v1/memory/compression/apply` contracts, then refresh Reliability state.
- BL-010bg update: filesystem approval detail editors are implemented and validation-clean; the dashboard can add action-specific filesystem approval options/content, show richer filesystem review digests and decision details, and validate bound filesystem path/target/options before execution.
- BL-010bh update: guarded workspace file change apply/revert controls are implemented and validation-clean; the dashboard can preview pending editor deltas, apply the current editor content through `/filesystem/write`, and revert the last dashboard-applied content through the same guarded filesystem route.
- BL-010bi update: task-chat execution transcript/status cards are implemented and validation-clean; the dashboard updates a single task-chat execution card from running to completed/failed, shows deterministic step-result summaries, refreshes task context after execution, and inserts run evidence back into follow-up chat context.
- BL-010bj update: task-chat orchestration creation is implemented and validation-clean; fresh plan cards can create backend-managed orchestration runs, render an orchestration transcript card, select the created run in the orchestration detail panel, and leave cycle/loop/background execution to explicit orchestration controls.
- BL-010bk update: task-chat orchestration context reuse is implemented and validation-clean; recent orchestration runs now appear in the task-chat context stream with counts, and created-run transcript cards can insert bounded orchestration context into follow-up turns without starting orchestration execution.
- BL-010bl update: local network policy rule editing is implemented and validation-clean; persisted local rules now flow through guarded network policy APIs, dashboard editor controls, managed-source precedence, and browser preflight validation.
- BL-010bm update: task-chat approval handoff cards are implemented and validation-clean; context cards for pending approvals now open the exact safe approval review instead of only offering passive context.
- BL-010bn update: memory lifecycle policy threshold controls are implemented and validation-clean; dashboard lifecycle preview/apply can now include bounded archive, soft-prune, promote, and compression-candidate threshold fields without changing backend authority.
- BL-010bo update: Git diff review bulk decision controls are implemented and validation-clean; loaded raw diff reviews can be filtered by section decision, bulk-update visible sections, and copy individual patches without adding hunk apply/revert authority.
- BL-010bp update: memory metadata quick-edit controls are implemented and validation-clean; editable Reliability-panel memory detail rows can patch tags, category, description, relevance, and retention policy while orchestration shared-memory rows stay read-only.
- BL-010bq update: plugin activation console controls are implemented and validation-clean; trusted plugin cards can preview/list/install/disable inert reference components and preview/install/disable plugin command recipes or hook policies through existing guarded routes while managed plugin activation locks render read-only.
- BL-010br update: provider and generated-tool approval request builders are implemented and validation-clean; the Providers runtime panel can create pending provider/tool approvals through existing guarded routes and refresh the unified inbox to the matching pending source.
- BL-010bs update: registered project metadata edit/archive/restore controls are implemented and validation-clean through the existing guarded project PATCH route.
- BL-010bt update: provider generation console controls are implemented and validation-clean; the Providers runtime panel can run non-streaming `/providers/generate` calls with optional bound provider and network approval IDs, render safe response metadata, and insert bounded response content into task-chat context.
- BL-010bu update: provider streaming generation controls are implemented and validation-clean; the Providers runtime panel can run `/providers/generate/stream`, accumulate NDJSON chunks with safe metadata, disable streaming for unsupported catalog providers, and insert bounded streamed responses into task-chat context.
- BL-010bv update: Task Chat provider replies are implemented and validation-clean; the task-chat composer can ask selected providers through existing non-streaming or streaming provider routes, render transcript reply cards, and insert bounded provider output into follow-up context.
- BL-010bw update: Task Chat provider approval request handoff is implemented and validation-clean; the task-chat composer can create a pending provider approval from the same provider/model/stream and composed prompt fields, omit generation-only provider/network approval IDs from the creation payload, render the approval in the transcript, reuse the approval ID, and open the exact safe provider review in the unified inbox.
- BL-010bx update: Git change-review rationale notes are implemented and validation-clean; the checkpoint-bound raw diff review UI can attach bounded per-section reviewer notes to decisions, copy them in review evidence, save them in metadata-only artifacts with secret redaction, and restore them only for matching fresh checkpoints.
- BL-010by update: Task Chat memory context controls are implemented and validation-clean; active SQL memory metadata now appears in the task-chat context stream, and Reliability-panel memory detail rows plus hybrid retrieval results can insert bounded memory context into the composer without adding backend memory write or execution authority.
- BL-010bz update: Task Chat provider message-role selection is implemented and validation-clean; the shared Task Chat provider payload builder now uses the selected supported role for both provider replies and provider approval requests instead of hardcoding `user`.
- Remaining: richer unified chat semantics beyond deterministic execution, explicit provider replies with selectable roles, active memory context insertion, orchestration creation, reusable orchestration context, and approval-review/request/response handoff, actual Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations, richer AI-change review semantics beyond metadata-only review artifacts, UI-side diff decisions, and reviewer rationale notes, broader editable policy/settings surfaces beyond the currently implemented project metadata, CLI policy, hook policy, network policy, command recipes, plugin trust/activation, generated-tool governance, memory lifecycle/compression administration beyond active metadata context insertion, manual thresholded preview/apply, and metadata quick-edit controls, and persistent/multi-worker project activation semantics.

Exit criteria:
- Users can submit tasks, inspect plan/sub-agent progress, review approvals, and view action logs through the web UI.
- Dashboard surfaces provider, memory, tool, task, CLI, approval, and runtime health data.
- Settings UI covers provider, routing, filesystem, CLI policy, memory, tools, and agent blueprint configuration.
- UI approval decisions use safe review metadata and do not expose secrets.
- UI exposes command recipes, plugin trust and activation state, hook decisions, managed settings, and git workflow checkpoint state without bypassing backend approvals.

### Sprint 17: VS Code Extension And Dedicated CLI Client

Goal:
- Add developer-facing editor and terminal interfaces on top of the backend contracts.

Stories:
- BL-011: VS Code Extension And Dedicated CLI Client.

Exit criteria:
- VS Code extension can connect to DGentic, provide a DGentic chat view, submit tasks, show agent/status context, and review approvals.
- VS Code extension integrates with native VS Code workspace folders, Explorer, editor, and diff review instead of duplicating file explorer/editor UI inside the extension.
- CLI client can run core health, task, approval, CLI-run, provider, memory, tool, session, and log workflows.
- CLI client includes original DGentic command recipes for common terminal workflows, including safe git commit/push/PR preparation and PR review orchestration.
- DGentic plugin packages can describe reusable command recipes, agent blueprints, skills, hook policies, generated-tool references, and documentation with audited installation.
- Extension and CLI auth handling masks tokens and avoids sensitive logs.
- Local installation and smoke validation are documented.

### Sprint 18: Deployment, CI/CD, Observability, And Rollback

Goal:
- Make DGentic deployable and operable with automated validation, monitoring, alerting, and rollback procedures.

Stories:
- BL-012: Production Deployment, CI/CD, Observability, And Rollback.

Exit criteria:
- CI runs tests, lint, format, package build, and release artifact checks.
- CI validates plugin manifests, hook policy schemas, command recipe contracts, and CLI smoke flows.
- Staging deployment can be created and smoke-tested reproducibly.
- Runtime metrics, structured logs, dashboards, and alerts cover critical surfaces.
- Observability covers hook decisions, plugin execution, command recipe usage, PR review outcomes, and git checkpoint freshness.
- Multi-worker CLI deployments either have DB-backed process ownership lease validation or are explicitly constrained to a single backend worker.
- Rollback workflow is documented and smoke-verified.

### Sprint 19: Provider-Specific External Adapter Expansion

Goal:
- Add first-class named external adapters only when the generic OpenAI-compatible adapter does not satisfy a concrete provider requirement.

Stories:
- BL-013: Provider-Specific External Adapter Expansion.

Exit criteria:
- At least one selected named adapter has a documented configuration contract, guarded generation/streaming support where applicable, approval-safe credential handling, routing integration, no-secret telemetry, and provider-specific tests.
- Named adapters are packaged as DGentic plugins when that packaging can preserve provider, credential, network, approval, routing, telemetry, streaming, and no-secret guarantees.
- Existing OpenAI-compatible provider contracts remain backward compatible.

### Git Workflow Timeline

Decision:
- Do not downsize the planned backend Git workflow feature set. Sequence the work so user-facing UI, VS Code, and CLI surfaces start sooner, but keep remaining Git capabilities on the roadmap.

Sprint placement:
- Sprint 15: backend Git safety foundation. Completed scope includes read-only Git workflow checkpoints, checkpoint-bound commit/push/PR approval creation, direct checkpoint-bound local commit/configured-upstream push/GitHub PR creation runners, authenticated actor binding, protected branch/file checks, secret-shaped staged-addition checks, workflow revalidation, and safe audit metadata.
- Sprint 16: web UI and approval dashboard surfaces for the existing Git checkpoints, Git approvals, Git run history, safe review metadata, blockers, and checkpoint freshness. Add only backend Git work that directly blocks these UI flows.
- Sprint 17: VS Code extension and dedicated CLI client commands for the existing Git workflows, including checkpoint, commit, push, PR creation, review, and status flows.
- Sprint 18: deployment/CI/observability coverage for Git workflow usage, PR review outcomes, checkpoint freshness, policy decisions, and remote publication audit trails.
- Later Git backend hardening lane: branch cleanup, PR labels/reviewers/assignees/projects/templates, remote fetch freshness, rollback/revert workflows, allowed remote/branch policies, destructive branch operation approval, richer Git audit/observability, and any additional GitHub/Git provider integrations.

Safe stopping rule:
- Do not pause Git work in the middle of a dependent feature chain. Stop only after the current Git slice or sprint checkpoint is fully validated, documented, committed, pushed, and its remaining work is recorded as deferred rather than cancelled.

## Not-Yet-Implemented Coverage Map

- Web frontend/dashboard: BL-010, Sprint 16. BL-010a same-origin `/ui/` dashboard shell, BL-010b current-root workspace file browser/editor, BL-010c CLI approval execution/run-output visibility, BL-010d read-only policy/plugin visibility, BL-010e active root context plus structured Git checkpoint review, BL-010f project registry/root preflight, BL-010g safe in-process project activation/rootDir switching, BL-010h richer orchestration console, BL-010i approval filtering, BL-010j per-task sub-agent briefs, BL-010k orchestration recovery/closeout controls, BL-010l orchestration creation, BL-010m sub-agent graph visibility, BL-010n memory/tool reliability dashboards, BL-010o guided task graph builder, BL-010p command recipe actions, BL-010q read-only settings/policy/Git review summaries, BL-010r CLI policy rule creation UI, BL-010s CLI policy rule edit/toggle UI, BL-010t Git checkpoint approval actions, BL-010u structured approval review summaries, BL-010v checkpoint-bound raw Git diff review, BL-010w checkpoint review-to-run Git actions, BL-010y non-CLI bound execution handoff panels, BL-010z first task-chat workflow, BL-010aa session AI-change review decisions, BL-010ab non-CLI bound request editor/execution UX, BL-010ac responsive/browser validation hardening, BL-010ad local task-chat history, BL-010ae guided non-CLI bound request fields, BL-010af approval-dashboard backend contract coverage, BL-010ag browser-driven seeded CLI approval coverage, BL-010ah browser-driven seeded filesystem approval execution coverage, BL-010ai browser-driven seeded web-retrieval network approval execution coverage, BL-010aj browser-driven seeded provider approval execution coverage, BL-010ak browser-driven seeded generated-tool approval execution coverage, BL-010al provider browser network-approval consumption, BL-010am generated-tool browser network-approval consumption, BL-010an persistent AI-change review artifacts, BL-010ao recursive guided non-CLI bound payload editing, BL-010ap local hook policy editing, BL-010aq unified task-chat context stream, BL-010ar local command recipe editing, BL-010as local plugin trust controls, BL-010at network policy preflight, BL-010au network approval requests, BL-010av provider health checks, BL-010aw provider routing preview, BL-010ax generated-tool governance controls, BL-010ay read-only hybrid memory retrieval, BL-010az memory lifecycle preview, BL-010ba memory compression preview, BL-010bb read-only memory/tool reliability detail drilldowns, BL-010bc task-chat follow-up context controls, BL-010bd memory lifecycle/compression apply controls, BL-010be filesystem guardrail preflight controls, BL-010bf filesystem preflight-to-approval request controls, BL-010bg filesystem approval detail editors, BL-010bh guarded workspace file change apply/revert controls, BL-010bi task-chat execution transcript/status cards, BL-010bj task-chat orchestration creation, BL-010bk task-chat orchestration context reuse, BL-010bl network policy editing, BL-010bm task-chat approval handoff, BL-010bn memory lifecycle policy threshold controls, BL-010bo Git diff review bulk decision controls, BL-010bp memory metadata quick-edit controls, BL-010bq plugin activation console controls, BL-010br provider/tool approval request builders, BL-010bs registered project metadata controls, BL-010bt provider generation console controls, BL-010bu provider streaming generation console controls, BL-010bv Task Chat provider reply controls, BL-010bw Task Chat provider approval request handoff controls, BL-010bx Git change-review rationale notes, BL-010by Task Chat memory context controls, and BL-010bz Task Chat provider message-role selector are implemented; richer dashboard, richer unified chat semantics beyond deterministic execution, provider replies with selectable roles, active memory context insertion, orchestration creation, reusable orchestration context, and approval-review/request/response handoff, actual Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations, richer AI-change review semantics beyond metadata-only review artifacts, UI-side diff decisions, and reviewer rationale notes, broader editable settings/policy beyond the currently implemented project metadata, CLI policy, hook policy, command recipes, plugin trust/activation, generated-tool governance, memory lifecycle/compression administration beyond active metadata context insertion, manual thresholded preview/apply, and metadata quick-edit controls, and persistent or multi-worker project activation remain.
- Network policy dashboard editing: BL-010bl, Sprint 16. Implemented local network-domain policy rule create/list/edit/toggle controls, managed read-only rendering, managed-lock enforcement, and browser preflight validation through the existing Policy panel.
- Task-chat approval handoff: BL-010bm, Sprint 16. Implemented exact approval-review opening from pending approval context cards using existing unified inbox and safe review contracts.
- Git diff review ergonomics: BL-010bo/BL-010bx, Sprint 16. Implemented decision filters, bulk visible accept/reject/clear actions, per-section patch copy, and bounded per-section reviewer rationale notes that persist only as metadata on matching checkpoint-bound review artifacts without adding backend hunk apply/revert authority.
- Memory metadata quick edit: BL-010bp, Sprint 16. Implemented Reliability-panel metadata edit controls for editable rows through existing PATCH semantics while preserving service-authored orchestration shared-memory protection.
- Plugin activation console: BL-010bq, Sprint 16. Implemented trusted-plugin preview/list/install/disable controls for inert reference components plus preview/install/disable controls for plugin command recipes and hook policies, using existing backend activation routes and managed lock read-only states.
- Provider/tool approval request builders: BL-010br, Sprint 16. Implemented Providers-panel forms for creating pending external-provider generation and generated-tool execution approvals through existing guarded routes, with browser coverage for inbox refresh and safe provider review metadata.
- Project metadata controls: BL-010bs, Sprint 16. Implemented Project-panel edit/archive/restore controls for registered project records through the existing guarded project metadata PATCH route; active-root switching remains governed by the existing activation barrier.
- Provider generation console: BL-010bt, Sprint 16. Implemented a Providers-panel non-streaming generation form through `/providers/generate`, optional bound provider/network approval IDs, safe result rendering, and task-chat response context insertion.
- Provider streaming generation console: BL-010bu, Sprint 16. Implemented a Providers-panel Stream mode through `/providers/generate/stream`, NDJSON chunk accumulation, unsupported-provider stream gating, safe metadata rendering, and task-chat streamed response context insertion.
- Task Chat provider replies: BL-010bv, Sprint 16. Implemented Ask Provider controls in Task Chat for non-streaming and streaming provider replies through existing guarded provider routes, including provider/model population, optional bound approvals, transcript reply cards, and bounded context insertion.
- Task Chat provider approval requests: BL-010bw, Sprint 16. Implemented Request Approval controls in Task Chat that create pending provider approvals from the composed chat prompt through the existing guarded provider approval route, exclude generation-only approval IDs, render transcript approval cards, fill the Ask Provider approval ID, and open the exact provider review.
- Task Chat memory context: BL-010by, Sprint 16. Implemented active-memory context cards plus Use In Task Chat controls for memory detail and hybrid retrieval rows through existing memory list/detail/retrieval contracts.
- Task Chat provider message roles: BL-010bz, Sprint 16. Implemented a Task Chat provider Message Role selector so provider replies and provider approval requests use the selected supported provider role through existing guarded provider contracts.
- Web task planner/run UI: BL-010x, BL-010z, BL-010ad, BL-010bc, BL-010bi, BL-010bj, and BL-010bk, Sprint 16. Implemented actionable task plan cards, plan-step detail, context chips, related deterministic run history, Run Plan execution through `/tasks/execute`, a task-chat composer that creates plans and optionally runs them through existing task APIs, capped local transcript restoration with display-only restored plan cards, reusable plan/run/orchestration context and evidence insertion controls, execution transcript/status cards for deterministic task-chat runs, fresh-plan orchestration creation through `/tasks/orchestrations` without starting orchestration execution, and bounded orchestration context insertion for follow-up chat turns; richer unified chat remains.
- VS Code extension: BL-011, Sprint 17.
- Dedicated CLI client interface: BL-011, Sprint 17.
- Interactive approval UI: BL-010, Sprint 16. BL-010a unified approval inbox with review plus approve/deny actions, BL-010c approved CLI execution, BL-010i source/status filtering, BL-010u structured safe review summaries, BL-010y non-CLI bound execution handoff panels, BL-010ab editable bound request execution, BL-010ae guided bound request fields, BL-010af unified approval contract coverage, BL-010ag browser-driven seeded CLI approval review/approve coverage, BL-010ah browser-driven seeded filesystem approval execution coverage, BL-010ai browser-driven seeded web-retrieval network approval execution coverage, BL-010aj browser-driven seeded provider approval execution coverage, BL-010ak browser-driven seeded generated-tool approval execution coverage, BL-010al provider browser network-approval consumption, BL-010am generated-tool browser network-approval consumption, BL-010ao recursive guided bound payload editing, BL-010bf filesystem preflight-to-approval creation, and BL-010bg filesystem approval detail editors are implemented; more type-specific domain editors remain as future polish.
- Production deployment infrastructure and CI/CD pipeline: BL-012, Sprint 18.
- Provider-specific external AI adapters beyond the generic OpenAI-compatible adapter: BL-013, Sprint 19.
- Full production identity management, secret management, encrypted credential storage, and token rotation: BL-009, Sprint 15. Persisted operator profiles, persisted operator groups with capability inheritance, generated token lifecycle APIs, identity/token/credential/plugin-trust metadata redaction, operator-supplied local encrypted vault references with supplied-key rotation, generic external-process credential adapter plumbing, first-class HashiCorp Vault KV v2 credential adapters, plugin manifest trust controls, managed plugin trust records, managed command recipes, managed plugin component records, plugin command recipe activation governance, inert plugin reference component records, backend hook-policy records, bound filesystem approval records, managed settings precedence foundation, managed policy surface locks, managed CLI, hook-policy, network-domain, and command-recipe precedence, command recipe execution contracts, read-only git workflow safety checkpoints, checkpoint-bound git commit/push/PR approval creation, direct checkpoint-bound local git commit/configured-upstream push/GitHub PR creation execution, and active-task verification for caller-supplied orchestration agent context are complete; richer identity workflows beyond operator groups, managed KMS integration, additional secret-manager adapters beyond HashiCorp Vault KV v2, plugin hook/tool/agent/skill loading governance beyond inert records, and broader managed policy-source controls remain.
- Network/domain guardrails: provider-call network policy is completed under BL-009/Sprint 15 BL-009c, provider-call network approval records are completed under BL-009h, generated-tool Python socket policy enforcement is completed under BL-009j, the web retrieval network guard contract is completed under BL-009ai, generated-tool network approval consumption is completed under BL-009am, the guarded web retrieval fetch runtime is completed under BL-009ap, and managed network-domain policy rule records are completed under BL-009av. OS-level/non-Python egress isolation remains under BL-009/Sprint 15 follow-up.
- CLI host-boundary guardrails: explicit executable paths outside `rootDir` are blocked under BL-009l for direct commands, shell wrappers, and launcher payloads, startup/preload/interpreter injection environment overrides are blocked under BL-009m, CLI approval reviewer routes are separated under the `approvals` capability under BL-009n, top-level shell profile/AutoRun launch hardening is implemented under BL-009o, bare executable workspace/PATH trust checks are implemented under BL-009p, command-specific path argument hardening for configured-safe tools is implemented under BL-009q, and nested shell startup hardening checks are implemented under BL-009r.
- Runtime monitoring, metrics, alerting, and rollback automation: BL-012, Sprint 18.
- Full process adoption/resumable output after backend restart: BL-002 follow-up, scheduled after the MVP CLI hardening scope.
- Production multi-worker CLI process ownership and lease validation: BL-001 and BL-012 follow-up, Sprint 18 deployment gating.

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
