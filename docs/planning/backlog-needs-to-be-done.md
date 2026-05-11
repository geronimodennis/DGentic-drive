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
- Moved to follow-up backlog: bound filesystem approval records/UI, persisted configurable filesystem policy rules, deeper platform-specific locked-file validation, and OS-level filesystem isolation.

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
- Partially implemented: production/staging bearer-token capability gates, startup fail-closed auth validation, no-echo invalid token behavior, principal attachment on request state, persisted operator identity records with capability assignments and active/inactive status, persisted generated bearer-token records with salted PBKDF2 hashes, one-time raw token return, token listing without hashes, rotation, revocation, expiry, auth audit events, `DGENTIC_AUTH_TOKENS` compatibility, legacy persisted-token compatibility, persisted-token startup bootstrap after env-token removal, assignment-limited token issuance, deactivated-operator token rejection, operator-id actor binding for persisted-token approval decisions, authenticated principal binding for direct CLI execution/runs, direct CLI approval execution, filesystem and command-policy audit events, provider generation/streaming, generated-tool execution, task, agent, memory, tool, and session mutations, persisted external credential references, OpenAI-compatible provider resolution through a configured credential reference without storing raw secret values, shell-free external-process credential resolver adapters with timeout/output bounds, provider-call network/domain guardrails with allow, deny, approval-required, audit decisions, single-use bound network approval records for approval-required provider transport, configured Python socket network policy guardrail for generated-tool subprocesses, active-task verification for caller-supplied orchestration agent context across CLI, generated-tool, provider, and network approval surfaces, and secret-shaped metadata redaction for operator display/role fields plus auth-token and credential-reference labels across responses, audit metadata, and new or mutated JSON state.
- Risk updated after Sprint 9 hardening: built-in read-only CLI path operands now receive cwd-aware rootDir checks, symlink escape checks, shell expansion checks, and Windows/POSIX path-shape regressions; broader host-boundary risks remain for trusted custom policy rules, non-built-in exfiltration commands, and time-of-check/time-of-use workspace changes.
- Remaining: richer user/group identity workflows beyond persisted operators, encrypted local credential vaulting, first-class external secret manager adapters beyond the generic process-adapter bridge, broader CLI host-boundary enforcement beyond the current built-in read-only command set, web retrieval network enforcement, and OS-level/non-Python generated-tool egress isolation beyond the current Python socket guardrail.

### BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience

Feature group: Interface ecosystem.

User value:
- Users need a usable cross-platform interface for task submission, sub-agent status, approvals, action logs, provider activity, memory, tools, settings, and runtime health instead of calling backend APIs directly.

Needs to be done:
- Build the web frontend shell for chat/task workflows, sub-agent progress, and rich output rendering.
- Add interactive approval UI for CLI, filesystem, tool, provider, and network approval-required actions.
- Add settings UI for auth/session connection, providers, routing, filesystem boundaries, CLI policy, memory, tools, and agent blueprints.
- Add settings and dashboard surfaces for DGentic-native plugin bundles, command recipes, hook-style safety rules, managed policy sources, and git workflow checkpoints inspired by the Claude Code study.
- Add dashboard views for runtime status, action logs, provider usage, memory health, tool reliability, and task history.
- Add API client contracts, authentication handling, loading/error states, and responsive layouts.
- Add frontend testing strategy and smoke validation against the backend.

Acceptance criteria:
- A user can submit a task, inspect plan/progress, review approval-required actions, and view action logs through the UI.
- Approval UI displays safe review metadata without secret values and records reviewer decisions.
- Settings and dashboard views cover the core backend surfaces needed for MVP operation.
- Plugin, command recipe, hook policy, and managed-settings views expose effective policy state without leaking secrets or permitting unaudited enablement.
- UI works on common desktop browser sizes and remains usable on smaller screens.

Definition of Done:
- Tests or smoke checks cover task flow, approval flow, auth handling, settings persistence/contracts, and dashboard data loading.
- README, setup docs, usage docs, architecture docs, and progress log are updated.
- PM confirms the root README not-yet-implemented entries for web frontend/dashboard and interactive approval UI can move to implemented or partially implemented status.

Current implementation status:
- Not yet implemented: web frontend/dashboard and interactive approval UI.

### BL-011: VS Code Extension And Dedicated CLI Client

Feature group: Developer interfaces.

User value:
- Developers need DGentic available from their editor and terminal so they can trigger tasks, inspect agents, review approvals, and reuse generated tools without leaving their normal workflow.

Needs to be done:
- Scaffold a VS Code extension with command palette commands, backend connection settings, token configuration, and sidebar views.
- Add VS Code task submission, active agent status, memory/tool status, and approval review surfaces.
- Add generated-tool discovery or launch integration where safe.
- Build a dedicated CLI client for health checks, task planning/execution, approvals, CLI runs, providers, memory, tools, and logs.
- Add a terminal-first command recipe layer for repeated workflows such as sprint execution, approval review, provider checks, git commit/push/PR preparation, branch cleanup, PR review, and release closeout.
- Define an original DGentic plugin package format for reusable command recipes, agent blueprints, skills, hook policies, generated-tool references, MCP/tool adapter references, and documentation.
- Share or align API contracts between the web UI, VS Code extension, and CLI client where practical.
- Add packaging, installation, and smoke validation for both interfaces.

Acceptance criteria:
- VS Code users can connect to a DGentic backend, submit a task, inspect active agents, and review approval-required actions.
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
- Not yet implemented: VS Code extension and dedicated CLI client interface.

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
- Moved to follow-up backlog: bound filesystem approval records/UI, persisted configurable filesystem policy rules, deeper platform-specific locked-file validation, and OS-level filesystem isolation.

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
- Remaining after BL-009j: richer user/group identity workflows, encrypted local credential vaulting, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, and broader CLI host-boundary enforcement.
- Claude Code study incorporation: remaining Sprint 15 security work should also shape DGentic-native hook policy records, managed-settings precedence, plugin trust controls, and pre-action command/filesystem/network safety checks rather than treating these as UI-only features.

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

Exit criteria:
- Users can submit tasks, inspect plan/sub-agent progress, review approvals, and view action logs through the web UI.
- Dashboard surfaces provider, memory, tool, task, CLI, approval, and runtime health data.
- Settings UI covers provider, routing, filesystem, CLI policy, memory, tools, and agent blueprint configuration.
- UI approval decisions use safe review metadata and do not expose secrets.
- UI exposes command recipes, plugin trust, hook decisions, managed settings, and git workflow checkpoint state without bypassing backend approvals.

### Sprint 17: VS Code Extension And Dedicated CLI Client

Goal:
- Add developer-facing editor and terminal interfaces on top of the backend contracts.

Stories:
- BL-011: VS Code Extension And Dedicated CLI Client.

Exit criteria:
- VS Code extension can connect to DGentic, submit tasks, show agent/status context, and review approvals.
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

## Not-Yet-Implemented Coverage Map

- Web frontend/dashboard: BL-010, Sprint 16.
- VS Code extension: BL-011, Sprint 17.
- Dedicated CLI client interface: BL-011, Sprint 17.
- Interactive approval UI: BL-010, Sprint 16.
- Production deployment infrastructure and CI/CD pipeline: BL-012, Sprint 18.
- Provider-specific external AI adapters beyond the generic OpenAI-compatible adapter: BL-013, Sprint 19.
- Full production identity management, secret management, encrypted credential storage, and token rotation: BL-009, Sprint 15. Persisted operator profiles, generated token lifecycle APIs, identity/token/credential metadata redaction, generic external-process credential adapter plumbing, and active-task verification for caller-supplied orchestration agent context are complete; richer identity workflows, encrypted local vaulting, and first-class secret-manager adapters remain.
- Provider-call network/domain guardrails: completed under BL-009/Sprint 15 BL-009c, with provider-call network approval records completed under BL-009h and generated-tool Python socket policy enforcement completed under BL-009j. Web retrieval network enforcement and OS-level/non-Python egress isolation remain under BL-009/Sprint 15 follow-up.
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
