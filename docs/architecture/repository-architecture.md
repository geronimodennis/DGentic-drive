# Repository Architecture

Date created: 2026-05-07

## Purpose

This document defines the initial DGentic repository layout. The structure is intentionally modular so backend, frontend, extension, generated tools, and documentation can evolve independently while sharing the same product direction.

## Current Layout

```text
dgentic/
  docs/
    architecture/
    how-to/
    planning/
    progress/
  localmcp/
  src/
    dgentic/
      api/
      ui/
        index.html
        app.css
        app.js
      agents.py
      auth.py
      command_recipes.py
      command_policy.py
      events.py
      git_workflows.py
      cli_runtime.py
      execution.py
      guardrails.py
      hook_policy.py
      main.py
      memory.py
      migrations.py
      memory/
        embedding_service.py
        compression_service.py
        metadata_service.py
        models.py
        retrieval_service.py
        schemas.py
        vector_backend.py
      planner.py
      plugins.py
      provider_policy.py
      provider_pricing.py
      provider_runtime.py
      providers.py
      orchestration.py
      orchestration_documents.py
      schemas.py
      sessions.py
      settings.py
      storage.py
      tool_runtime.py
      tools.py
      tools/
        registry_service.py
  tests/
  .env.example
  .gitignore
  pyproject.toml
  README.md
```

## Directory Responsibilities

### `src/dgentic/`

Python backend package for the DGentic orchestrator API.

Current modules:

- `main.py`: FastAPI app factory, application instance, a same-origin static `/ui/` dashboard mount, and an in-process HTTP request barrier that keeps project-root activation from overlapping other dashboard/API request handling in the local runtime.
- `ui/`: Static Sprint 16 dashboard shell served by FastAPI. It provides browser-session bearer-token handling, health cards, first chat-style task planning through the existing `/tasks/plan` and `/tasks/execute` contracts with capped browser-local transcript history, structured task planning, active root context visibility, project root preflight, registration, and guarded Open controls, active-root workspace file browsing and text editing through guarded filesystem APIs, guided orchestration task graph creation that writes the existing JSON create contract, orchestration summary/detail with task graph, expandable per-task sub-agent briefs and parent-child agent graph visibility from the existing `/agents` contracts when authorized, task update/recovery/blocker resolution/closeout controls backed by existing orchestration mutation endpoints, blockers, follow-ups, execution records, and cycle/loop/background execution controls, unified approval inbox source/status filtering with structured safe review summaries, warning/binding/digest/audit context, and approved CLI execution, CLI run output polling, command recipe preview/approval/run/execute controls through existing recipe contracts, structured Git checkpoint blockers/warnings/diff-stat review plus AI-change metadata summaries, checkpoint-bound raw Git diff review with session accept/reject annotations and copyable review evidence, checkpoint-bound commit/push/PR approval creation, and direct checkpoint-bound commit/push/PR run controls through existing Git workflow routes, provider/tool summary, memory lifecycle and tool-registry reliability summaries, read-only CLI policy, hook policy, plugin trust, and policy source/status summaries, local CLI policy rule creation/edit/toggle controls through existing guarded policy routes, grouped effective settings with managed-field and policy-lock summaries, and event log polling while relying on the existing backend API capability gates for protected data and actions.
  The task planner portion now renders actionable task plan cards with step detail, context chips, related deterministic task-run history, and a Run Plan action that posts the existing `TaskPlan` contract to `/tasks/execute`.
  The approval review portion shows editable bound execution panels for approved non-CLI approval families, with existing endpoint targets, safe payload scaffolds, guided field controls that sync into the canonical JSON payload, binding checks, direct execution for dashboard-callable bound requests, and handoff-only payloads for provider/tool network approvals instead of bypassing filesystem, network, provider, or tool request-binding checks.
- `auth.py`: Production/staging bearer-token authentication, route and method-aware capability mapping, persisted operator identity records with direct capability assignments, assigned operator groups, computed effective capabilities, and active/inactive status, persisted operator group records with active/inactive capability bundles, persisted generated bearer-token records with salted PBKDF2 hashes, rotation/revocation/expiry helpers, operator-id actor binding, direct plus group-inherited capability checks for token issuance/authentication, startup fail-closed configuration validation, CLI approval reviewer capability separation, and secret-shaped metadata redaction for operator display/role fields, operator group display/description fields, and generated-token labels before responses, auth audit metadata, and new or mutated JSON persistence.
- `api/routes.py`: HTTP routes for health checks, persisted operator/auth-token and credential-reference management, project root preflight/registry/activation metadata, tasks, orchestration runs and detached orchestration execution polling, filesystem/command/network guardrails, hook policy rules, filesystem approvals, CLI policy and approvals, git workflow checkpoints, checkpoint-bound raw diff reviews, direct commit/push/PR runs, commit/push/PR approval creation, provider approvals, providers, routing, owner-scoped orchestration agent reads, memory, tools, plugin discovery/trust/component previews, sessions, and logs. Authenticated principals are bound into requester/audit actors for direct execution and mutation routes when auth is enabled. Managed policy locks can make selected mutation routes fail closed while keeping read/preview/evaluation routes available.
- `projects.py`: Admin-gated project registry and activation service for preflighting absolute existing project roots, rejecting symlink roots and current DGentic state directories, persisting canonical root metadata in `projects.json`, reporting active-runtime-root matches, and safely activating available registered project roots in-process. Activation blocks active CLI runs, active orchestration executions, running orchestration tasks, and pending/approved CLI/filesystem/network/provider/tool approvals; pins relative `data_dir` to its current absolute location; resets cached SQLAlchemy state after switching; and records project audit metadata.
- `api/memory_routes.py`: SQLAlchemy-backed metadata index, retrieval, and tool registry routes under `/api/v1`, including service-authored orchestration shared-memory metadata protections and owner/admin read scoping when auth is enabled.
- `schemas.py`: Pydantic contracts for tasks, execution runs, orchestration runs, detached orchestration execution records, explicit orchestration shared-memory tags and reuse policy, guardrails, hook policy rules and decisions, network policy decisions, CLI policy rules, command context, controlled command environments, providers, routing, agents, memory, tools, sessions, logs, auth/operator audit events, and credential audit events.
- `orchestration.py`: Backend orchestration control plane for persisted task graphs, canonical declared-path role-boundary validation, dependency-aware sub-agent scheduling with redacted dependency-output context handoff, durable JSON-backed scheduler leases, fenced pending-to-running task claims before agent spawn, fixed agent ids for crash repair, unspawned-claim rollback on spawn failure, opt-in SQL-backed shared memory publishing/reuse by explicit tags with owner or run-scoped reuse policy, service-authored shared-memory provenance validation, orchestration-owned agent visibility helpers, orchestration-bound filesystem plus shared active-task context authorization for CLI, generated-tool, provider, and network approval actions, explicit and bounded loop-based agent lifecycle reconciliation, detached process-local background loop execution with pollable records, active-run conflict rejection, heartbeat renewal, stale-supervisor reconciliation, and startup adoption/resume for expired prior-supervisor executions, retry escalation, blocked-task recovery, manual/security blocker resolution with audit history, blockers, follow-ups, bounded scheduling passes, actor-attributed events when auth is enabled, closed-run immutability, audited generated project-document sync, and DoD evidence close gates.
- `orchestration_documents.py`: Generated orchestration project-document sync for redacted run status and open follow-up/blocker backlog Markdown files under `docs/progress/` and `docs/planning/`, with fixed paths, symlink rejection, and a shared sync lock.
- `command_policy.py`: Persisted local CLI policy rule storage, managed-source read-only CLI policy rule merging, optional agent-role rule scoping, executable, exact-command, contains, and argument-aware command matching, shell-wrapper inspection, cwd-aware evaluation, hook-policy escalation, orchestration-bound CLI action checks when agent context is supplied, read-only path operand, explicit executable path, configured-safe command path-argument rootDir boundary checks, mutating-git downgrade protection for configured-safe `git` rules, nested shell startup hardening checks, and actor-attributed policy audit events.
- `git_workflows.py`: Shell-free git workflow checkpoint service for commit, push, and PR preparation, checkpoint-bound raw diff review, direct local checkpoint-bound commit execution, direct checkpoint-bound configured-upstream push execution, direct checkpoint-bound GitHub PR creation, and checkpoint-bound commit, push, and PR approval request construction. It resolves `git` and `gh` outside `rootDir`, bounds cwd and repository roots under `rootDir`, inspects status/ahead-behind/diff stats without optional locks or prompts, hashes staged and unstaged diff content plus upstream remote URL digests into checkpoint digests, returns readiness blockers and warnings, redacts paths and secret-shaped findings, returns raw diff review patches only after the supplied checkpoint digest still matches fresh repository state, omits protected or secret-shaped paths from raw review patches, excludes untracked file content, redacts secret-shaped patch text, caps each returned section, records metadata-only diff-review audit events without patch bodies, validates non-secret single-line commit messages and bounded non-secret PR title/body/base fields, runs direct local commits only after a fresh ready commit checkpoint digest still matches, runs direct pushes only after a fresh ready push checkpoint digest still matches and only to the checkpoint-derived remote plus `HEAD:refs/heads/[upstream]`, runs direct PR creation only after a fresh ready PR checkpoint digest still matches and the branch is pushed/current with upstream, requires explicit GitHub CLI token environment for direct PR creation, isolates `gh` config with a temporary `GH_CONFIG_DIR`, returns commit SHA, push ahead/behind metadata, or a strict sanitized PR URL without stdout/stderr or approval creation, builds generated `git commit -m ...`, `git push`, or constrained `gh pr create ...` CLI approval requests only when fresh ready checkpoint digests match, rejects caller-supplied remote/branch/refspec/flag/command/head payloads, and validates workflow-bound approvals against fresh checkpoint state before CLI approval claim. It intentionally avoids `git add`, arbitrary `gh` flags, untracked-file diff content, caller-supplied PR head branches, `gh` execution during approval creation, browser/template/label/reviewer PR automation, or destructive branch cleanup.
- `command_recipes.py`: Local and managed command recipe registry for safe, parameterized command templates. Recipes expand into existing CLI execution requests, reject secret-shaped text and unsafe parameter values, expose policy preview contracts, merge deployment-managed recipes from `DGENTIC_MANAGED_SETTINGS_FILE` ahead of local records without writing them to `command-recipes.json`, block local/plugin shadowing of managed ids, ignore locally persisted rows that spoof `source: "managed"`, record managed usage through audit events without mutating managed state, and fail closed for plugin-owned recipes when plugin trust, manifest digest, component digest, or activation status drifts.
- `cli_runtime.py`: CLI approvals, single-use bound approval IDs, hook-policy-bound approval digests, optional workflow-bound approval metadata with git workflow revalidation before approval claim, root-bound synchronous and asynchronous command execution, POSIX translation for policy-approved `cmd /c` and `cmd.exe /c` wrappers, top-level `cmd /d` AutoRun suppression and PowerShell `-NoProfile -NonInteractive` launch hardening, bare executable workspace/PATH trust checks for direct and `cmd /c` inner commands before approval claim or subprocess launch, Windows default PATHEXT fallback candidates, failed launch run records for claimed synchronous approvals, chunked output polling, supervision metadata, auditable lifecycle states, stale-running reconciliation, process-local cancellation, controlled environment construction with startup/preload injection override blocking, agent/task context auditing, output redaction/truncation, and command run history.
- `planner.py`: Deterministic starter planner used until model-backed planning is implemented.
- `execution.py`: Deterministic plan execution run service for MVP workflow validation.
- `guardrails.py`: Filesystem policy evaluation plus guarded text, binary, directory, metadata, delete, move, copy, rename, single-use bound filesystem approval records, hook-policy decision attachment/approval/block escalation, orchestration-bound filesystem action checks when agent context is supplied, actor-attributed filesystem audit events, and command execution compatibility wrappers.
- `hook_policy.py`: Persisted backend hook-policy rule storage for command, filesystem, and network guardrail surfaces, with managed-source read-only hook rule merging ahead of local/plugin records. Rules support ordered matching, optional agent-role scoping, audit/approval/block effects, plugin provenance for declaratively installed plugin-owned rules, redacted persistence and audit metadata, managed ID collision protection, and safe pre-action escalation without loading or executing plugin hook content.
- `network_policy.py`: Configurable outbound domain policy parser and evaluator with exact-domain and wildcard-subdomain rules plus `allow`, `deny`, `approval_required`, and `audit` modes, deployment-managed rule records that evaluate before local/environment rules with safe matched-rule source metadata, canonical effective-policy approval digests, hook-policy escalation, backed by redacted single-use network approval records for approval-required provider and generated-tool socket requests and active orchestration task-context verification before approval create/validate/claim side effects.
- `web_retrieval.py`: Guarded web retrieval contract that pins retrieval requests to the `web_retrieval` surface and `fetch` action, reuses domain policy, hook-policy escalation, active-task context checks, and bound network approval claiming, and provides a narrow single-URL fetch runtime. Fetch execution requires an explicit matching network policy rule, uses GET-only transport without caller headers, cookies, proxies, request bodies, credentials, fragments, or redirects, accepts only text-like content, reads at most the configured byte cap plus one byte for truncation detection, redacts response text and audit metadata for common secret shapes, and records safe web retrieval audit events.
- `provider_policy.py`: Shared provider endpoint policy, exact base URL normalization, network/domain and hook policy enforcement, bound network approval validation/claiming for approval-required provider domains, allowlist validation, and redirect-blocking HTTP opener.
- `provider_pricing.py`: Bounded provider/model pricing catalog parser and advisory usage/request cost estimation helpers.
- `provider_routing.py`: Bounded role-to-provider/model routing catalog parser for explicit role-specific routing preferences.
- `provider_transport.py`: Shared provider JSON and streaming transport with bounded retry/backoff before response streaming starts, safe upstream error types, retry metadata, and no-retry health-probe support.
- `providers.py`: Provider registry, policy-validated Ollama/LM Studio health and model probes, disabled external placeholder, config-only OpenAI-compatible external provider status through configured local or managed credential references or env-var fallback, external-process and HashiCorp Vault KV v2 adapter configuration validation without secret retrieval, pricing-aware provider estimates, role-aware provider/model routing, and scored routing decisions.
- `provider_runtime.py`: Ollama, LM Studio, and OpenAI-compatible external chat/completion request execution with provider endpoint and network-domain policy enforcement, `network_approval_id` binding for approval-required provider domains, active orchestration task-context verification before approval creation, credential lookup, approval claim, or transport, Ollama/OpenAI-compatible streaming, bounded retry/backoff, in-process circuit breakers, deferred credential-safe headers for external fail-fast paths, local and managed credential-reference resolution at transport time, local encrypted vault, shell-free external-process, and HashiCorp Vault KV v2 credential adapter support, model allowlist checks, single-use bound external provider approvals, advisory usage-based cost estimates, and safe response telemetry.
- `credentials.py`: Local persisted and deployment-managed references to credential locations or ciphertext, including environment variables, operator-key encrypted local vault records, configured shell-free external process adapters, first-class HashiCorp Vault KV v2 adapters, and read-only managed env/external-process/secret-manager records from `DGENTIC_MANAGED_SETTINGS_FILE`, with lifecycle/audit helpers, counts-only local vault key rotation, no raw secret-value response or event storage, external-process timeout/output bounds, explicit secret-manager base URL allowlists, deny/approval-required network-policy blocking before Vault token lookup, redirect/proxy-disabled Vault HTTP reads, managed-over-local overlay, local managed-source spoof filtering, and secret-shaped metadata redaction before responses, credential audit metadata, and new or mutated JSON persistence.
- `plugins.py`: Backend-only plugin manifest discovery, local and managed trust records, inert reference component registry records, and declarative command recipe plus hook-policy activation for direct `rootDir/plugins/[plugin_id]/dgentic-plugin.json` manifests. The service never imports plugin code, runs plugin scripts, or loads plugin hooks/tools/agents/skills; it validates exact root-bound manifest paths, rejects symlinked/out-of-root/oversized/malformed manifests, computes SHA-256 digests over raw manifest bytes, returns redacted safe metadata summaries, persists explicit local trust/block decisions in `plugin-trust.json`, applies managed exact-digest plugin trust records ahead of local trust when configured, marks trust stale when manifest bytes change, previews and metadata-installs inert agent blueprint, skill, tool, and docs component references from trusted current manifests with bounded reads and component digests, overlays deployment-managed inert component records ahead of local rows without local persistence, reports managed component records as `stale` or `drifted` when manifest or component bytes change, filters local rows that spoof `source: "managed"`, and installs only bounded JSON command recipe and hook-policy components with component digest provenance.
- `agents.py`: Sub-agent brief registry, parent-child lifecycle tracking, status updates, and output reconciliation.
- `memory.py`: Legacy in-memory memory record indexing and search module. The active import path is reconciled through the `dgentic.memory` package.
- `memory/`: SQLAlchemy metadata index models, schemas, metadata CRUD/upsert service, lifecycle policy service, deterministic compression service, optional embedding service, vector backend contract/default SQLite implementation, and retrieval service contracts.
- `tools.py`: Legacy local tool manifest registration, guarded tool generation, duplicate detection, and governance module. The active import path is reconciled through the `dgentic.tools` package.
- `tools/`: SQLAlchemy-backed tool registry service plus generated-tool integration with duplicate preflight checks, auto-registration, monotonic same-name version migration, usage tracking, reliability scoring, and source-path validation.
- `tool_runtime.py`: Generated tool approval records, bound approval validation, orchestration-bound active task checks when agent context is supplied, process-group subprocess execution and timeout cleanup, SQL registry permission/deprecation checks, local-only dependency import isolation, configured network-domain policy guardrails for common Python socket egress inside generated-tool subprocesses, single-use `generated_tool`/`socket_connect` network approval consumption for one explicit host and port, reduced inherited execution environment, redacted output/audit events, SQL reliability counter sync, and runtime reliability policy automation.
- `sessions.py`: Session summary registry.
- `events.py`: Central event log backed by local JSON state with response-time redaction for common secret patterns and structured sensitive metadata keys.
- `migrations.py`: SQLAlchemy schema migration ledger for the current metadata, vector embedding, tool registry baseline, and additive memory lifecycle metadata migration.
- `database.py`: Configurable SQLAlchemy engine/session helper, migration initialization, cached database reset, SQLite path resolution, and file-backed SQLite backup/restore helpers.
- `storage.py`: JSON collection persistence helper for MVP local state with corrupt-file quarantine/restore helpers and inter-process locked reads plus item update/collection transactions for approval claims, decisions, orchestration execution claims, and scheduler lease claims.
- `settings.py`: Environment-based backend settings plus the opt-in managed-settings precedence foundation, including auth mode, bootstrap bearer token capability configuration, network domain policy configuration, external provider credential reference configuration, operator-supplied local credential vault key configuration, bounded credential process adapter configuration, HashiCorp Vault KV v2 adapter and allowed-base-URL configuration, managed-file validation, managed policy surface locks, managed credential reference parsing, managed CLI, hook-policy, and network-domain rule parsing, managed command recipe parsing, managed plugin trust record parsing, managed plugin component record parsing, in-process runtime root overrides for guarded project activation, and redacted effective-settings source reporting.

### `tests/`

Automated tests for backend behavior. The current tests validate health checks, task planning, persisted task history, deterministic execution, persisted operator identity lifecycle and assignment-limited token issuance, persisted auth-token issuance/restart, one-time raw token return, salted hash storage, rotation, revocation, expiry, deactivated-operator token rejection, env-token and legacy persisted-token coexistence, auth capability mapping, persisted external credential references, managed credential reference records, local encrypted credential-vault references, external-process credential resolver adapters, HashiCorp Vault KV v2 credential adapters, credential capability gates, provider credential-reference resolution without raw secret persistence, network/domain policy decisions, network approval lifecycle/redaction/binding, web retrieval network guard approval binding, filesystem approval lifecycle/redaction/binding, provider and Vault credential egress enforcement before transport, generated-tool Python socket network-policy enforcement, plugin manifest discovery/trust redaction, symlink/out-of-root manifest rejection, stale trust detection, plugin reference component metadata registry gates, plugin command recipe activation capability/provenance/drift gates, plugin hook-policy activation capability/provenance/disable gates, no raw-token/credential/plugin-secret log exposure, and operator-id approval actor binding, orchestration scheduling, scheduler lease fencing across service instances, foreground scheduler conflict responses while detached executions are active, scheduler adoption after restart, spawn-failure rollback, role-boundary enforcement, detached orchestration background execution polling, duplicate-active rejection, cooperative cancellation, owner-scoped execution access, owner-scoped operations summary counts, restart adoption of expired prior-supervisor detached executions, expired cancellation finalization, and non-resumable stale handling, opt-in orchestration shared-memory publishing/reuse with completed-task provenance, owner scoping, tag authorization, owner/run reuse policy boundaries, service-authored shared-memory metadata enforcement, owner/admin agent and memory read scoping, inactive-record exclusion, and fail-soft SQL behavior, orchestration-bound filesystem, CLI, and generated-tool action checks, guardrail checks, configurable and agent-role scoped CLI policy rules, managed credential, CLI, hook-policy, and command-recipe precedence/read-only behavior, shell-wrapper command policy hardening, mutating-git and GitHub CLI configured-safe downgrade protection, git workflow checkpoint readiness, checkpoint-bound git commit/push/PR approval creation and execution-time workflow revalidation, managed policy surface locks, command recipe registry/preview/execution contracts, CLI approvals, single-use approval ID binding, asynchronous CLI status/output polling, supervision metadata, stale-running reconciliation, cancellation and timeout lifecycle behavior, controlled command environments, command context auditing, run history, provider routing and generation runtime, dynamic tool generation, tool execution and governance, memory lifecycle policy, deterministic memory compression, vector backend contracts, retrieval attribution and inactive-state filtering, memory/database migrations, agent lifecycle APIs, session summaries, and logs.

Recent Sprint 15 managed-policy tests also cover deployment-managed plugin component records and managed network-domain records, including managed-only settings loading, fail-closed record validation, managed-over-local precedence, safe matched-rule source metadata, approval drift invalidation, provider/runtime enforcement, generated-tool policy handoff without managed metadata leakage, no `plugin-components.json` persistence for managed rows, and `stale`/`drifted` plugin component status reporting.

Recent managed credential reference tests cover managed-only settings loading, fail-closed parser validation, source-attributed credential list responses, local collision shadowing, local managed-source spoof filtering, read-only revoke behavior, provider runtime use of managed env and secret-manager references, explicit HashiCorp Vault KV v2 adapter allowlists, deny/approval-required Vault egress blocking before token lookup, and no local `credential-references.json` writes for managed rows.

Recent direct git commit runner tests cover successful checkpoint-bound local commits without approval creation, stale digest rejection, non-ready checkpoint rejection, protected-file and secret-shaped staged-addition blocking, secret-shaped and multiline commit-message rejection, repository hook isolation, no raw commit-message audit exposure, and auth/capability principal binding for `POST /cli/git/commit-runs`.

Recent direct git push runner tests cover successful configured-upstream pushes without approval creation, stale digest rejection, dirty worktree rejection, no-upstream and no-ahead rejection, extra remote/branch/flag payload rejection, secret-shaped remote URL non-exposure, repository pre-push hook isolation, and auth/capability principal binding for `POST /cli/git/push-runs`.

Recent direct git PR runner tests cover successful constrained `gh pr create` invocation without approval creation, stale digest rejection, dirty/no-upstream/unpushed/behind checkpoint rejection, extra command/remote/flag payload rejection, secret-shaped and multiline PR text rejection, unsafe `gh` output non-exposure, explicit GitHub token environment requirements, isolated `gh` configuration, and auth/capability principal binding for `POST /cli/git/pr-runs`.

Recent web retrieval runtime tests cover explicit-policy fetch requirements, allow/audit success through mocked transport, denial and missing approval before transport, approval-required single-use execution, wrong/reused approval rejection, active-task context checks, URL credential and fragment rejection, redirect blocking, text-like content enforcement, bounded truncation, and response/log redaction.

Recent web UI tests cover `/ui/` static entrypoint and asset serving, favicon browser-noise suppression, responsive panel shrink/wrap CSS guards, task-chat selector/helper wiring, task-chat local history helpers, task plan/execute endpoint reuse, active root context display wiring, project registry/preflight/activation endpoint wiring, workspace file browser/editor endpoint wiring, orchestration creation form and POST payload wiring, guided task graph builder wiring, orchestration detail/action-control wiring, per-task agent-brief and agent-graph wiring, orchestration task update/recovery/blocker resolution/closeout endpoint wiring, approval source/status filter wiring, structured approval review summary and warning/audit wiring, guided non-CLI bound request field wiring, approved CLI execution and CLI run output endpoint wiring, command recipe action endpoint wiring, structured Git checkpoint and AI-change metadata renderer wiring, checkpoint-bound raw Git diff review wiring, session Git diff accept/reject decision controls and evidence-copy wiring, checkpoint-bound Git approval form and endpoint wiring, direct checkpoint-bound Git run button/endpoint/result wiring, memory/tool reliability endpoint wiring, read-only policy/plugin endpoint wiring with policy review summaries, local CLI policy creation/edit/toggle form wiring, grouped effective-settings review wiring, session bearer-token header wiring, plus the auth-enabled boundary where the dashboard shell remains loadable while protected API routes still require a bearer token. Project registry and activation tests cover canonical root validation, duplicate root rejection, registry persistence, admin-only route capability, active-root matching, the guarantee that registration alone does not switch `/settings/effective` or guarded filesystem list behavior, successful activation with anchored state, old-root file invisibility after switching, unexecuted approval blockers, active CLI run blockers, running orchestration task blockers, archived project rejection, and invalid/deleted root rejection.
Task planner UI tests also assert the richer plan-card helpers, `/tasks/execute` wiring, Run Plan affordance, and task plan/run CSS hooks. Approval UI tests assert the non-CLI bound execution scaffold helpers, endpoint targets, editable payload path, binding validation, execution action, output refresh, copy action, and CSS hooks.

### `localmcp/`

Location for generated reusable tools. DGentic-created tools live under:

```text
localmcp/[tool_name]/
  tool.py
  wrapper.py
  manifest.json
  README.md
```

### `docs/`

Project documentation:

- `planning/`: Agile plans and sprint backlog.
- `progress/`: Project progress log.
- `architecture/`: Technical architecture and design records.
- `how-to/`: Setup, usage, and operations guides.

## Planned Layout Additions

Future milestones should add:

```text
apps/
  web/
  cli/
extensions/
  vscode/
plugins/
  [plugin_name]/
    dgentic-plugin.json
    commands/
    agents/
    skills/
    hooks/
    tools/
infra/
scripts/
config/
  managed-settings/
```

The `plugins/[plugin_name]/dgentic-plugin.json` manifest location now has a backend discovery and trust foundation. The nested command, agent, skill, hook, and tool package contents remain future work and must not be loaded or executed by the discovery path. The Claude Code incorporation study in `docs/architecture/claude-code-incorporation-study.md` recommends a DGentic-native plugin and command recipe layer, but all implementation must be original DGentic work and must preserve backend approval, auth, audit, credential, network, and orchestration boundaries.

## Backend API Surface

Authentication:

- `GET /`, `GET /health`, `/docs`, `/redoc`, `/openapi.json`, and the static `/ui/` dashboard assets are public.
- Development mode is auth-off by default.
- Staging and production modes are auth-on by default unless `DGENTIC_AUTH_ENABLED=false` is explicitly set.
- Protected route groups require bearer tokens configured through `DGENTIC_AUTH_TOKENS` or persisted generated bearer tokens assigned to active operator profiles, using effective capabilities from the operator's direct assignments plus active operator groups. Capability names include `auth`, `credentials`, `tasks`, `filesystem`, `cli`, `providers`, `approvals`, `network`, `hooks`, `agents`, `memory`, `tools`, `sessions`, `logs`, or `admin`.
- `GET /settings/effective` is protected by the default `admin` capability mapping and returns redacted source-attributed runtime settings, runtime override attribution for active project activation, and managed-file digest metadata.
- `managed_policy_locks` only takes effect from `DGENTIC_MANAGED_SETTINGS_FILE`, not from ordinary environment variables, and can lock `cli_policy`, `command_recipes`, `hook_policy`, `plugin_trust`, `plugin_components`, `plugin_command_recipes`, and `plugin_hook_policies` mutation routes. The same managed file can declare `managed_credential_references`, `managed_cli_policy_rules`, `managed_hook_policy_rules`, `managed_command_recipes`, `managed_plugin_component_records`, and `managed_plugin_trust_records`; these are parsed as deployment-owned read-only records, source-attributed as `managed`, evaluated or listed ahead of local records where applicable, hidden from local mutable state persistence, and rejected by normal mutation routes for their policy surfaces.
- When auth is enabled, startup fails closed if there is no valid bootstrap `token=capabilities` entry and no active persisted token.

Current endpoints:

- `GET /`: Service health response.
- `GET /health`: Service health response.
- `GET /ui/`: Serves the static Sprint 16 dashboard shell, including the first task-chat planner with capped browser-local history, actionable task plan/run UI, session Git diff review decisions, editable guided bound execution panels, and responsive layout guards. The shell itself is public, but all protected API calls it makes still require an entered bearer token when auth is enabled.
- `POST /projects/preflight`: Validates a candidate absolute project root without registering or activating it.
- `GET /projects`: Lists registered project roots.
- `POST /projects`: Registers a preflighted project root without activating it.
- `GET /projects/active`: Reports the active runtime root and any registered project matching it.
- `GET /projects/{project_id}` and `PATCH /projects/{project_id}`: Read or update registered project metadata and archive state.
- `POST /projects/{project_id}/activation/preflight`: Reports whether a registered project can be safely activated, including blockers and warnings.
- `POST /projects/{project_id}/activate`: Safely switches the current process runtime root to an available registered project after active-run, active-task, and unexecuted-approval checks.
- `POST /auth/operator-groups`: Creates a persisted operator group with assigned capabilities.
- `GET /auth/operator-groups`: Lists persisted operator groups.
- `GET /auth/operator-groups/{group_id}`: Retrieves one persisted operator group.
- `PATCH /auth/operator-groups/{group_id}`: Updates operator group display fields, assigned capabilities, or active/inactive status.
- `POST /auth/operators`: Creates a persisted operator identity with direct capabilities and optional `group_ids`.
- `GET /auth/operators`: Lists persisted operator identities.
- `GET /auth/operators/{operator_id}`: Retrieves one persisted operator identity.
- `PATCH /auth/operators/{operator_id}`: Updates operator display fields, direct capabilities, assigned `group_ids`, or active/inactive status. Operator responses include `effective_capabilities`.
- `POST /tasks/plan`: Creates a structured starter task plan.
- `GET /tasks/plans`: Lists persisted task plans.
- `POST /tasks/execute`: Creates a deterministic execution run from a task plan.
- `GET /tasks/runs`: Lists persisted task execution runs.
- `POST /tasks/orchestrations`: Creates a persisted orchestration run from a client-owned task graph spec, validates dependencies, records role-boundary decisions, rejects server-owned task lifecycle fields, blocks out-of-bound tasks, and schedules dependency-ready tasks into sub-agent briefs.
- `GET /tasks/orchestrations`: Lists persisted orchestration runs.
- `GET /tasks/orchestrations/{run_id}`: Returns a persisted orchestration run by id.
- `POST /tasks/orchestrations/{run_id}/advance`: Attempts to schedule pending tasks whose dependencies are completed, using a scheduler lease to persist fenced task claims before spawn and passing redacted completed-dependency output summaries into each spawned dependent agent brief.
- `POST /tasks/orchestrations/{run_id}/cycle`: Reconciles terminal spawned-agent lifecycle states back into running orchestration tasks, applies retry/block behavior, and schedules newly dependency-ready tasks with scheduler fencing and redacted dependency-output context.
- `POST /tasks/orchestrations/{run_id}/loop`: Runs a bounded synchronous orchestration loop over the cycle machinery until waiting agents, blockers, all-complete state, quiescence, or the configured iteration limit stops progress.
- `PATCH /tasks/orchestrations/{run_id}/tasks/{task_id}`: Updates a running task to completed, failed, or blocked through stale-update conflict detection, then applies retry, blocker, follow-up, and dependency scheduling behavior. Completed task output is redacted and bounded before it is included in downstream spawned-agent context.
- `POST /tasks/orchestrations/{run_id}/tasks/{task_id}/recover`: Recovers a task with system-generated role-boundary or retry-exhaustion blockers after a non-blank resolution note, optional role or declared write-path correction, role-boundary revalidation, task-scoped recoverable blocker/follow-up clearing, and dependency-aware rescheduling. Manual blockers remain unresolved for separate review.
- `POST /tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve`: Resolves manual or security blockers with a non-blank resolution note, preserves blocker audit history, unblocks the task to pending when no unresolved blockers remain, optionally schedules the task immediately, and requires admin authority when authentication is enabled. Role-boundary and retry-exhaustion blockers stay on the task recovery path.
- `POST /tasks/orchestrations/{run_id}/close`: Closes a completed orchestration only when every task is complete, blockers are resolved, and required Definition of Done evidence is present.
- Orchestration state changes synchronize generated Markdown documents at `docs/progress/orchestration-runs.md` and `docs/planning/orchestration-follow-ups.md`. These files are generated from persisted orchestration state and manual edits may be replaced. Successful and failed sync attempts are audited; sync failures do not roll back the already-persisted orchestration state.
- `POST /guardrails/filesystem`: Evaluates filesystem action policy against `rootDir`.
- `POST /guardrails/network`: Evaluates the configured outbound network domain policy for a URL without making a network request.
- `POST /web-retrieval/network/check`, `POST /web-retrieval/network/approvals`, and `POST /web-retrieval/network/authorize`: Evaluate, queue, and claim bound network approvals for web retrieval fetches using the pinned `web_retrieval` surface and `fetch` action. These routes do not fetch remote content; they provide sanitized, approval-bound preflight contracts for retrieval clients and require the `network` capability when auth is enabled.
- `POST /web-retrieval/fetch`: Executes one guarded GET request after web retrieval policy authorization. The target host must match an explicit network policy rule; `approval_required` hosts consume a single-use approval bound to `web_retrieval`/`fetch`, while stray approval ids are rejected for `allow` or `audit` hosts. Fetch blocks redirects, URL credentials, fragments, caller-supplied headers, cookies, proxies, non-text-like content, and responses beyond the configured hard cap except for explicit truncation; responses include safe URL, host, status, content type, charset, content digest, size, truncation state, redacted bounded text, policy metadata, and consumed approval id.
- `POST /guardrails/hooks/rules`: Creates a persisted hook policy rule for command, filesystem, or network guardrail decisions. When auth is enabled, this route requires `hooks`.
- `GET /guardrails/hooks/rules`: Lists managed, local, and plugin hook policy rules in evaluation order.
- `PATCH /guardrails/hooks/rules/{rule_id}`: Updates a local hook policy rule without storing secret-shaped match patterns; managed and plugin-owned rules remain read-only through this route.
- `POST /network/approvals`, `GET /network/approvals`, `GET /network/approvals/{approval_id}/review`, `POST /network/approvals/{approval_id}/approve`, and `POST /network/approvals/{approval_id}/deny`: Manage redacted, single-use network approval records for approval-required network policy decisions. Provider generation and streaming consume matching records through `network_approval_id`. When approval requests or claims include `agent_id`, `agent_role`, or `task_id`, the context must either be omitted entirely or match a running orchestration task; partial, stale known-task, or unrelated active-task context is rejected.
- `POST /filesystem/approvals`, `GET /filesystem/approvals`, `GET /filesystem/approvals/{approval_id}/review`, `POST /filesystem/approvals/{approval_id}/approve`, and `POST /filesystem/approvals/{approval_id}/deny`: Manage redacted, single-use filesystem approval records for approval-required filesystem decisions. Records are bound to action, path/target digests, write payload digests, source/target state digests, options, actor/task context, orchestration decisions, and hook-policy decisions. Creating approvals and executing bound filesystem actions require `filesystem`; list/review/approve/deny require `approvals`.
- `POST /filesystem/read`: Reads a UTF-8 text file after root boundary policy approval.
- `POST /filesystem/write`: Writes a UTF-8 text file after root boundary policy approval and payload-size validation.
- `POST /filesystem/read-binary`: Reads a binary file as base64 after root boundary policy approval and payload-size validation.
- `POST /filesystem/write-binary`: Writes base64 binary content after root boundary policy approval and payload-size validation.
- `POST /filesystem/list`: Lists safe directory entries after root boundary policy approval.
- `POST /filesystem/metadata`: Returns file or directory metadata after root boundary policy approval.
- `POST /filesystem/delete`: Deletes a file or directory after destructive-operation approval. In staging/production, approval-required operations require a bound `approval_id`; `approved: true` remains development/test-only.
- `POST /filesystem/move`: Moves a file or directory after destructive-operation approval. In staging/production, approval-required operations require a bound `approval_id`; `approved: true` remains development/test-only.
- `POST /filesystem/copy`: Copies a file or directory after destructive-operation approval. In staging/production, approval-required operations require a bound `approval_id`; `approved: true` remains development/test-only.
- `POST /filesystem/rename`: Renames a file or directory after destructive-operation approval. In staging/production, approval-required operations require a bound `approval_id`; `approved: true` remains development/test-only.
- Filesystem request bodies may include `agent_id`, `agent_role`, and `task_id`; when supplied together, write actions are also checked against the matching running orchestration task and its declared write paths, while omitted context preserves the existing non-orchestrated behavior.
- `POST /guardrails/commands`: Classifies CLI command risk, optionally using agent role, agent id, and task id context. Explicit executable paths in direct commands, shell wrappers, and launcher payloads, command-specific directory/path flags for configured-safe `git`, `npm`, `pnpm`, `yarn`, and `uv` rules, and nested `cmd`/PowerShell startup flags must satisfy root and startup-hardening boundaries before configured policy rules can allow the command. If context is supplied while orchestration work is active, all three fields must exactly match a running task before command policy evaluation can continue. Context that references a known but non-running task is rejected as stale. Omitted context and unknown legacy context when no active task matches preserve the existing non-orchestrated behavior.
- `POST /cli/policy/rules`: Creates a persisted local CLI policy rule, optionally scoped to one or more agent roles, unless the `cli_policy` managed lock is active.
- `GET /cli/policy/rules`: Lists managed and local CLI policy rules in evaluation order. Managed rules are marked with `source: "managed"` and sort before local rules.
- `PATCH /cli/policy/rules/{rule_id}`: Updates a persisted local CLI policy rule. Managed-source rules are read-only and return `403`.
- `POST /cli/execute`: Executes allowed commands or approval-required commands with a bound `approval_id` inside `rootDir` after cwd, read-only operand, explicit executable path, configured-safe command path-argument boundary checks, nested shell startup-hardening checks, controlled environment override validation, bare executable workspace/PATH trust checks, and top-level shell startup hardening, with audited agent/task context and orchestration-bound active task checks when context is supplied. The `approved: true` bypass is limited to development/test mode.
- `POST /cli/runs`: Starts an allowed asynchronous command run or an approval-required run with a bound `approval_id`, audited agent/task context, orchestration-bound active task checks when context is supplied, controlled environment override validation, bare executable workspace/PATH trust checks, and top-level shell startup hardening. The `approved: true` bypass is limited to development/test mode.
- `GET /cli/runs/{run_id}`: Polls a persisted command run by id.
- `GET /cli/runs/{run_id}/output`: Polls redacted stdout/stderr output chunks by sequence number.
- `POST /cli/runs/{run_id}/cancel`: Requests cancellation for a running command in the current backend process.
- `POST /cli/approvals`: Creates a pending approval for approval-required commands. Approval records include command digest, cwd, timeout, requester, agent/task context, environment keys without values, matched policy metadata, and expiry. When auth is enabled, this route requires the `cli` capability.
- `GET /cli/approvals`: Lists CLI approval records. When auth is enabled, this route requires the `approvals` capability.
- `GET /cli/approvals/{approval_id}/review`: Returns the safe approval review contract for UI consumers, including redacted review command, cwd, timeout, permission mode, policy reason, requester, agent/task context, environment keys without values, matched rule metadata, command/environment HMAC digests, bound-execution warnings, direct-execute availability, decision reasons, run id, and lifecycle timestamps. When auth is enabled, this route requires the `approvals` capability.
- `POST /cli/approvals/{approval_id}/approve`: Approves a pending CLI command with an optional redacted decision reason. When auth is enabled, this route requires the `approvals` capability.
- `POST /cli/approvals/{approval_id}/deny`: Denies a pending CLI command with an optional redacted decision reason. When auth is enabled, this route requires the `approvals` capability.
- `POST /cli/approvals/{approval_id}/execute`: Executes an approved CLI command once when no environment override is required. When auth is enabled, this route requires the `cli` capability.
- `GET /cli/runs`: Lists persisted CLI command run history.
- `POST /cli/recipes`: Creates a persisted safe command recipe under the `cli` capability.
- `GET /cli/recipes`: Lists persisted command recipes.
- `GET /cli/recipes/{recipe_id}`: Returns one persisted command recipe.
- `PATCH /cli/recipes/{recipe_id}`: Updates recipe metadata, template, parameters, tags, timeout, cwd, or enabled status.
- `POST /cli/recipes/{recipe_id}/preview`: Expands a recipe with safe parameters and returns the resulting command, cwd, timeout, parameter names, and command policy decision without executing it.
- `POST /cli/recipes/{recipe_id}/execute`: Expands and executes a recipe synchronously through the existing CLI runtime; production approval-required recipes must use a bound `approval_id`.
- `POST /cli/recipes/{recipe_id}/approvals`: Creates a standard CLI approval for the expanded recipe command.
- `POST /cli/recipes/{recipe_id}/runs`: Expands and starts a recipe asynchronously through the existing CLI runtime; production approval-required recipes must use a bound `approval_id`.
- `POST /cli/git/checkpoints`: Creates a read-only git readiness checkpoint for `commit`, `push`, or `pr` preparation. The response includes branch/head/upstream metadata, ahead/behind counts, staged/unstaged/untracked counts, redacted changed paths, diff stats, blockers, warnings, and a checkpoint digest; it does not execute commits, pushes, PR creation, or network calls.
- `POST /cli/git/commit-runs`: Re-runs a commit checkpoint and executes one direct local `git commit -m ...` only when the supplied checkpoint digest still matches a fresh ready commit checkpoint. The runner validates a bounded single-line non-secret commit message, requires test evidence through the checkpoint contract, runs `git` by argv with optional locks/prompts disabled, isolates repository hooks with an empty temporary hooks path, disables GPG signing, records safe CLI audit metadata with commit-message digests instead of raw messages, returns head-before/head-after metadata, and does not create a CLI approval or return raw command output.
- `POST /cli/git/push-runs`: Re-runs a push checkpoint and executes one direct `git push --porcelain [remote] HEAD:refs/heads/[upstream-branch]` only when the supplied checkpoint digest still matches a fresh ready push checkpoint. The runner requires a clean non-protected branch, configured upstream remote URL digest, local commits ahead, no behind-upstream state, no caller-supplied remote/refspec/flag fields, shell-free argv execution, hook isolation, push GPG-signing disablement, safe ahead/behind result metadata, no raw remote URL or command output, and no CLI approval creation.
- `POST /cli/git/commit-approvals`, `POST /cli/git/push-approvals`, and `POST /cli/git/pr-approvals`: Create pending workflow-bound CLI approvals from fresh ready git checkpoints for constrained commit, push, and PR creation commands. PR approval creation accepts only bounded non-secret PR title/body/base/draft fields, requires the current branch to be clean, non-protected, configured with an upstream remote URL digest, already pushed, and current with upstream, and queues `gh pr create` for later normal CLI approval execution without running `gh` or performing network I/O during approval creation.
- `GET /providers`: Lists configured providers with safe display base URLs and discovered local model names when reachable.
- `GET /providers/{provider_id}/health`: Returns provider configuration health after endpoint policy validation.
- `POST /providers/generate`: Runs an Ollama, LM Studio, or approved configured OpenAI-compatible external chat/completion request against an allowlisted base URL and returns whitelisted response metadata. Caller-supplied orchestration agent context is verified before credential lookup, approval claim, or outbound transport.
- `POST /providers/generate/stream`: Streams Ollama or OpenAI-compatible generation chunks as newline-delimited JSON events for Ollama, LM Studio, or an approved configured OpenAI-compatible external provider. Caller-supplied orchestration agent context follows the same active-task verification contract as non-streaming generation.
- `POST /providers/{provider_id}/approvals`: Creates a pending approval for configured external provider generation. Approval records include safe message review metadata, request/base URL/credential-reference/model-allowlist HMAC digests, stream mode, timeout, requester, agent/task context, and expiry, after any supplied orchestration context is verified against active task state. When auth is enabled, this route requires the separate `approvals` capability.
- `GET /providers/approvals`: Lists provider approval records. When auth is enabled, this route requires the `approvals` capability.
- `GET /providers/approvals/{approval_id}/review`: Returns the safe provider approval review contract for UI consumers without raw prompt content or credential values.
- `POST /providers/approvals/{approval_id}/approve`: Approves a pending provider request with an optional redacted decision reason. The transition is persisted through an inter-process locked JSON transaction.
- `POST /providers/approvals/{approval_id}/deny`: Denies a pending provider request with an optional redacted decision reason. The transition is persisted through an inter-process locked JSON transaction.
- `POST /routing/decide`: Returns a scored provider routing decision with candidate scores.
- `POST /credentials/references`: Creates a local persisted credential reference backed by an environment variable, a configured external process adapter, a configured HashiCorp Vault KV v2 adapter, or a local encrypted vault ciphertext. Local vault creation accepts a raw `secret_value` only in the create request, encrypts it with the operator-provided `DGENTIC_CREDENTIAL_VAULT_KEY`, and omits plaintext plus ciphertext from API views and credential audit events. Secret-manager references persist only adapter id and secret name metadata; the Vault token and resolved secret are never written to credential state.
- `GET /credentials/references`: Lists local persisted credential references plus deployment-managed records from `managed_credential_references`, with `source` attribution and without raw secret values.
- `POST /credentials/references/{credential_ref_id}/revoke`: Revokes a local persisted credential reference so provider runtime resolution fails closed; managed credential references are read-only and cannot be revoked through the API.
- `POST /credentials/references/local-vault/rotate-key`: Re-encrypts persisted `local_vault` credential ciphertext from a supplied current Fernet key to a supplied new Fernet key in one JSON collection transaction, skips non-local-vault references, returns counts only, and records an audit event without keys, plaintext, ciphertext, credential ids, labels, or secret names.
- `POST /agents`: Registers a running sub-agent brief.
- `GET /agents`: Lists registered sub-agent briefs.
- `GET /agents/{agent_id}`: Returns a specific sub-agent brief.
- `GET /agents/{agent_id}/children`: Lists child agents for a parent agent.
- `PATCH /agents/{agent_id}/status`: Updates sub-agent lifecycle status.
- `POST /agents/reconcile`: Reconciles sub-agent output reports.
- `POST /memory`: Adds an in-memory memory record.
- `POST /memory/search`: Searches memory records by text and tags.
- `POST /api/v1/memory/metadata`: Creates a SQLAlchemy-backed metadata index record.
- `GET /api/v1/memory/metadata`: Lists metadata index records with filters.
- `GET /api/v1/memory/metadata/{metadata_id}`: Retrieves a metadata index record and updates access tracking.
- `PATCH /api/v1/memory/metadata/{metadata_id}`: Updates a metadata index record.
- `DELETE /api/v1/memory/metadata/{metadata_id}`: Deletes a metadata index record.
- `POST /api/v1/memory/retrieve/hybrid`: Runs the hybrid retrieval contract. Semantic embedding generation currently requires an optional embedding dependency.
- `POST /api/v1/memory/retrieve/vector`: Runs the vector retrieval contract. Semantic embedding generation currently requires an optional embedding dependency.
- `GET /api/v1/memory/retrieve/metadata`: Runs metadata-only retrieval.
- `POST /tools`: Registers a local tool manifest.
- `POST /tools/generate`: Generates a local tool directory with source, wrapper, manifest, README files, and optional validated local dependency path metadata after JSON and SQL registry duplicate preflight checks, then registers the generated tool in local JSON state and the SQLAlchemy-backed tool registry. Same-name regeneration is treated as a version migration and requires `overwrite=true` plus a strictly newer version; accepted migrations update the single SQL row in place and reset reliability counters for the new generated artifact version.
- `POST /tools/{name}/approvals`: Creates a pending approval for approval-required generated tools under the `tools` capability. Approval records include redacted payload preview, payload/artifact/approval HMAC digests, tool version/status, entrypoint, timeout, requester, agent/task context, orchestration-bound active task checks when context is supplied, serialized orchestration decisions, and expiry.
- `GET /tools/approvals`: Lists generated tool approval records.
- `GET /tools/approvals/{approval_id}/review`: Returns the safe generated-tool approval review contract for UI consumers with redacted payload preview, digest identifiers, lifecycle timestamps, and bound-execution warnings.
- `POST /tools/approvals/{approval_id}/approve`: Approves a pending generated tool execution request with an optional redacted decision reason. When auth is enabled, this route requires the separate `approvals` capability.
- `POST /tools/approvals/{approval_id}/deny`: Denies a pending generated tool execution request with an optional redacted decision reason. When auth is enabled, this route requires the separate `approvals` capability.
- `POST /tools/{name}/execute`: Executes a registered generated tool, blocks deprecated/disabled/blocked tools, fails closed on SQL registry permission conflicts, requires a single-use bound `approval_id` for approval-required tools outside development/test mode, can consume one single-use `network_approval_id` for an approval-required `generated_tool`/`socket_connect` host and explicit port, enforces orchestration-bound active task checks when agent context is supplied, launches Python with isolated import semantics and only tool-local dependency paths, passes only sanitized network-domain policy decisions plus the claimed approved endpoint into the subprocess runner, installs common Python socket egress guards before generated tool imports run, starts the subprocess in a process group or new process group where the host supports it, cleans up the process tree on timeout, uses a reduced inherited environment, redacts stdout/stderr/parsed output for common secret patterns, records execution audit metadata with serialized orchestration decisions and consumed network approval ids, syncs SQL registry usage counters when a row exists, and applies reliability policy warnings/disable/deprecation after enough runtime evidence.
- `GET /tools`: Lists registered tool manifests.
- `PATCH /tools/{name}/governance`: Deprecates, disables, or reactivates a registered tool.
- `GET /plugins`: Discovers direct plugin manifests under `rootDir/plugins/[plugin_id]/dgentic-plugin.json`, returns redacted metadata summaries, trust source/status metadata, and safe discovery errors, and rejects symlinked, out-of-root, oversized, or malformed manifests without loading plugin content.
- `GET /plugins/{plugin_id}`: Returns one discovered plugin summary by id.
- `PATCH /plugins/{plugin_id}/trust`: Persists an explicit local `trusted` or `blocked` decision for the current manifest digest, with redacted reason and actor metadata. Later manifest byte changes surface the trust status as `stale`; plugin ids with managed trust records reject local trust mutation as read-only.
- `GET /plugins/{plugin_id}/components`: Lists inert installed or disabled plugin reference component metadata from managed settings and `plugin-components.json`; deployment-managed records are source-attributed as `managed`, listed ahead of local rows, never persisted locally, and reported as `stale` or `drifted` when manifest or component provenance no longer matches disk.
- `POST /plugins/{plugin_id}/components/preview`: Reads bounded inert agent blueprint, skill, tool, and docs component references from a trusted current plugin manifest, returns stable component ids, type, name, component path, component digest, size, and manifest digest metadata, and does not parse, import, index, install, persist, load, or execute referenced content.
- `POST /plugins/{plugin_id}/components/install`: Persists or refreshes inert plugin reference component metadata in `plugin-components.json` for trusted current manifests without loading or executing referenced content; plugins with deployment-managed component records are read-only through this local mutation route.
- `POST /plugins/{plugin_id}/components/disable`: Marks installed inert plugin reference component metadata disabled without deleting the provenance record; plugins with deployment-managed component records are read-only through this local mutation route.
- `POST /plugins/{plugin_id}/command-recipes/preview`: Reads bounded declarative command recipe JSON components from a trusted current plugin manifest, returns recipe ids, names, component paths, and component digests, and does not persist or execute anything.
- `POST /plugins/{plugin_id}/command-recipes/install`: Installs or refreshes trusted current plugin command recipe components into `command-recipes.json` with plugin id, manifest digest, component path, component digest, and active status provenance.
- `POST /plugins/{plugin_id}/command-recipes/disable`: Disables installed plugin-owned command recipes without deleting the provenance record.
- `POST /plugins/{plugin_id}/hook-policies/preview`: Reads bounded declarative hook-policy JSON components from a trusted current plugin manifest, accepts a single rule or a list of rules per component, returns generated rule ids, names, component paths, and component digests, and does not persist or execute anything.
- `POST /plugins/{plugin_id}/hook-policies/install`: Installs or refreshes trusted current plugin hook-policy components into `hook-policy-rules.json` with plugin id, manifest digest, component path, component digest, and active status provenance.
- `POST /plugins/{plugin_id}/hook-policies/disable`: Disables installed plugin-owned hook-policy rules without deleting the provenance record.
- `POST /api/v1/tools/registry`: Registers a SQLAlchemy-backed tool registry entry.
- `GET /api/v1/tools/registry`: Lists SQLAlchemy-backed tool registry entries.
- `GET /api/v1/tools/registry/{tool_id}`: Retrieves a tool registry entry.
- `POST /api/v1/tools/registry/check-duplicate`: Checks duplicate tools by name, interface signature, and tag overlap.
- `POST /api/v1/tools/registry/{tool_id}/usage`: Records tool usage and updates reliability.
- `POST /api/v1/tools/registry/{tool_id}/deprecate`: Marks a tool registry entry as deprecated.
- `POST /sessions/summary`: Creates a session summary.
- `GET /sessions/summary`: Lists session summaries.
- `GET /logs`: Lists recorded events, optionally filtered by event type, with common secret patterns and structured sensitive metadata keys redacted on write and response.

## Engineering Baseline

Initial tooling:

- Python package manager: `uv`
- Backend framework: FastAPI
- Schema system: Pydantic v2
- Test runner: pytest
- Linter/formatter: Ruff

Quality gates:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`

## Local State

DGentic stores MVP local state as JSON collections under `.dgentic/` by default. The directory is ignored by Git and can be changed with `DGENTIC_DATA_DIR`. When a JSON collection file is malformed or no longer validates against its model, the storage layer moves the original file to a timestamped `*.corrupt-*.json` quarantine beside the active file and repairs the active collection to an empty valid array. SQLAlchemy-backed metadata and registry services use `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db` by default for the local MVP database and can be pointed at another SQLAlchemy database with `DGENTIC_DATABASE_URL`.

Current collections:

- `task-plans.json`
- `task-runs.json`
- `operators.json`
- `operator-groups.json`
- `auth-tokens.json`
- `credential-references.json`
- `orchestrations.json`
- `orchestration-executions.json`
- `orchestration-scheduler-leases.json`
- `events.json`
- `agents.json`
- `memory.json`
- `tools.json`
- `plugin-trust.json`
- `plugin-components.json`
- `hook-policy-rules.json`
- `filesystem-approvals.json`
- `sessions.json`
- `cli-approvals.json`
- `cli-command-policy-rules.json`
- `cli-command-runs.json`
- `dgentic.db`

JSON collections expose `list_quarantined_files()` and `restore_quarantine()` helper methods for operator or test repair workflows when a quarantined file is valid enough to restore. SQLAlchemy schema state is tracked in `schema_migrations`. The current baseline id is `0001_metadata_tool_registry_baseline`. File-backed SQLite local databases can be backed up and restored with `backup_sqlite_database()` and `restore_sqlite_database()` for operator smoke workflows; scheduled, remote, and PostgreSQL-native backup automation remains future production work.

Generated orchestration documents are stored in normal project docs rather than `.dgentic/`: `docs/progress/orchestration-runs.md` summarizes persisted run status, and `docs/planning/orchestration-follow-ups.md` lists open follow-ups and unresolved blockers for non-completed runs.

## Sprint 9 BL-003 Parser And Approval Review Contract Scope

Architect status: implementation-ready scope for the next Sprint 9 slice.

Goal:

- Make command policy parsing behavior explicit across common Windows and POSIX command shapes.
- Confirm approval-review metadata is safe and sufficient for future UI consumers.
- Keep this slice focused on parser/review contracts, not process supervision or UI implementation.

Current parser contract:

- `parse_command()` stores the raw first token for executable path boundary checks, normalizes that token into an executable name for policy matching, and leaves remaining tokens as arguments.
- Persisted command policy rules can match by executable, exact command, command substring, or argument substring.
- Common shell wrappers inspect inner commands for `cmd /c`, `sh -c`, `bash -c`, `powershell -Command`, `powershell -c`, `pwsh -Command`, and `pwsh -c`.
- Built-in defaults classify known destructive commands as blocked, runtime-changing commands as approval-required, and other commands as autopilot-safe.

Current approval-review contract:

- Approval records expose command, cwd, timeout, requested_by, agent_id, agent_role, task_id, permission mode, policy reason, environment keys, matched rule id/name, command digest, expiry, decision actor, decision reason, denial reason, run id, and lifecycle timestamps.
- `GET /cli/approvals/{approval_id}/review` exposes the UI-facing safe review contract with redacted `review_command`, environment key names only, command/environment HMAC digest identifiers, warnings for redacted-command or environment-bound execution, and `direct_execute_available` only when an approved, unexpired approval can be directly executed without a bound request.
- Environment values are not persisted in approval records; only environment variable names are stored for review and binding.
- Approve and deny decision reasons plus approval audit/log metadata are redacted for common secret assignments, secret-like flags, shell substitutions, and structured sensitive metadata keys before persistence or response.
- When auth is enabled, CLI approval list/review/approve/deny routes require `approvals`, while approval creation and approved-command execution remain under `cli`.
- Direct execution with a bound approval id validates command, cwd, timeout, requester, agent/task context, environment keys, permission mode, matched policy metadata, and digest before execution.
- The backend approval review contract, structured dashboard review summaries, and editable guided non-CLI bound execution UX are implemented; deeper nested type-specific editors and end-to-end approval scenarios remain BL-010/Sprint 16 work.

BL-003a Developer scope:

- Add source changes only if needed to make parser behavior deterministic for the QA matrix below.
- Preserve the existing public request/response shapes unless the parser matrix exposes missing review metadata.
- Do not add tests in the Developer step.
- Do not implement interactive approval UI in this slice.

BL-003a QA matrix:

- Windows wrappers: `cmd /c`, `cmd.exe /c`, `powershell -Command`, `powershell -c`, `powershell.exe -Command`, `pwsh -Command`, and `pwsh -c`.
- POSIX wrappers: `sh -c` and `bash -c`.
- Quoting cases: quoted executable paths, quoted inner shell commands, mixed single/double quotes, and commands with spaces in arguments.
- Policy behavior: blocked inner commands stay blocked, approval-required inner commands stay approval-required, safe inner commands remain autopilot-safe, and uninspectable wrappers require approval.
- Rule behavior: executable, exact, contains, argument_contains, priority ordering, disabled rules, and agent-role scoping remain stable.
- Review metadata: approval records expose command/cwd/role/task/environment keys/policy reason/matched rule metadata without environment values or secret values.

Architect handoff:

- Next role: Developer.
- Developer should inspect `src/dgentic/command_policy.py`, `src/dgentic/schemas.py`, and `src/dgentic/cli_runtime.py`.
- Developer may change production source only.
- Developer should hand off expected parser/review behavior and any source changes to QA for tests-only coverage.

## Architecture Decisions

- Start with a backend-first monorepo because orchestration, permissions, schemas, and logs define the core product contracts.
- Keep model-provider execution out of the first slice; the initial planner is deterministic and auditable.
- Define Pydantic schemas early so future UI, extension, memory, routing, and tool runtime work can share stable contracts.
- Generate tools only under `rootDir/localmcp/[tool_name]/`, with source, wrapper, manifest, README, local JSON manifest, optional validated local dependency path metadata, SQL registry entry, duplicate preflight checks, and memory artifact indexing.
- Discover plugins only from direct `rootDir/plugins/[plugin_id]/dgentic-plugin.json` manifest files, compute trust digests from exact raw manifest bytes, and keep plugin package loading, hooks, tools, agents, skills, scripts, and arbitrary execution out of the discovery/trust foundation. Reference component preview/install may compute and persist inert digests and sizes for trusted current agent blueprint, skill, tool, and docs files, but those records remain metadata only.
- Allow trusted current plugin manifests to activate declarative command recipe and hook-policy JSON components only through digest-bound provenance records and existing runtime gates; command recipe component drift, stale trust, blocked trust, or disabled activation must fail closed before preview or execution, while plugin-owned hook-policy rules remain inert when disabled and cannot be manually patched through local hook-policy routes.
- Keep command recipes as a thin registry and resolver over the existing CLI request contract. Recipe endpoints may create, preview, approve, execute, and run expanded commands, but policy evaluation, approval binding, runtime execution, redaction, cancellation, and audit remain owned by CLI policy/runtime services.
- Use local JSON collections for the MVP sprint surface; inter-process locked reads and item updates protect provider approval decisions and claims, while broader indexing, querying, and schema migration needs still require a production database migration path.
- Fence orchestration scheduling with a JSON-backed run-level scheduler lease. Scheduling passes claim pending dependency-ready tasks as running with fixed agent ids before agent spawn, foreground schedule endpoints conflict while a detached execution owns the run, background workers renew the private lease with their execution heartbeat every 30 seconds, leases expire after 300 seconds, execution APIs expose only lease ids instead of private lease tokens, expired/lost leases force stale background finalization, and unspawned claims roll back on spawn failure.
- Use SQLite-compatible SQLAlchemy models for the metadata index, memory lifecycle metadata, JSON-vector default backend, and tool registry MVP slice, with configurable database URLs, a schema migration ledger, and local SQLite backup/restore smoke helpers. PostgreSQL with pgvector remains the production target, while production driver packaging, JSON-store migration, scheduled backup automation, and pgvector storage remain follow-up work.
- Require bearer-token capability checks by default in staging and production while keeping development mode auth-off unless explicitly enabled. Production/staging startup fails closed when auth is enabled without configured bearer tokens.
- Let deployment-owned managed settings coarse-lock mutable policy surfaces and publish read-only managed CLI and hook-policy rules. Surface locks fail closed for mutation routes while preserving read, preview, and evaluation access for operators and UI clients; managed CLI rules are evaluated before local rules but still cannot downgrade hard-coded command safety boundaries, and managed hook rules are evaluated before local/plugin hook records while remaining outside mutable JSON persistence.
- Probe Ollama and LM Studio through lightweight local HTTP health/model discovery after exact provider base URL allowlist validation; report the OpenAI-compatible external adapter through config-only health so listing providers does not make authenticated external calls.
- Execute Ollama, LM Studio, and configured OpenAI-compatible chat requests through provider runtime contracts using provider-scoped egress policy, bound `network_approval_id` records for approval-required provider domains, redirect blocking, bounded request and provider-specific success-payload validation, bounded retry/backoff for retryable generation failures before stream bytes begin, in-process per-provider circuit breakers for retry-exhausted generation failures, NDJSON downstream streaming for Ollama and OpenAI-compatible chunks, safe response metadata, normalized usage metadata, an exact provider/model pricing catalog for advisory usage-based and routing cost estimates, role-to-provider/model routing preferences that still honor privacy/capability/cost/model eligibility, HTTPS-only credential-safe outbound headers that are resolved only after external pricing/config/circuit/approval gates allow transport, single-use bound approvals for external generation outside development/test mode, model allowlist checks, and generic upstream failure details; vault key rotation/KMS integration, durable multi-worker circuit state, provider billing reconciliation, and provider-specific external adapters remain follow-up work.
- Perform filesystem operations only through guardrail evaluation; current runtime support includes text and base64 binary read/write, directory listing, metadata, approval-gated delete/move/copy/rename, and single-use bound approval records inside `rootDir`, with protected state-file blocking, symlink escape checks, size limits, and audit logging.
- Execute CLI commands only through configurable command policy evaluation, managed-before-local CLI policy rule precedence, root-bound and cwd-aware working directories, explicit executable path checks for direct commands, shell wrappers, and launcher payloads, configured-safe command path-argument checks for common tool directory flags, mutating-git downgrade protection, nested shell startup-hardening checks, orchestration-bound active task checks when agent/task context matches a running orchestration task, controlled inherited environments plus explicit non-sensitive overrides that reject startup-hook/preload/interpreter injection keys, bare executable workspace/PATH trust checks before approval claim or subprocess launch, top-level `cmd` AutoRun and PowerShell profile/prompt suppression at launch, single-use approval records for approval-required commands outside development/test mode, sanitized output capture, persisted run history, and audit logging.
- Support asynchronous CLI runs through persisted run records, redacted output chunks, supervision metadata, auditable lifecycle states, stale-running reconciliation, timeout handling, process-local cancellation, and conservative post-restart orphan termination when the persisted process identity still matches the live process. Full process adoption/resumable output after restart and production multi-worker supervision with durable leases remain follow-up work.
- Keep built-in CLI defaults for blocked and approval-required executables, inspect common shell wrappers such as `cmd /c`, `sh -c`, and PowerShell command invocations for blocked inner commands, block explicit executable paths, built-in read-only path operands, configured-safe command path arguments that resolve or shell-expand outside `rootDir`, and mutating `git` subcommands before configured-safe rules can downgrade them, block nested `cmd` invocations without `/d` and nested PowerShell/pwsh invocations without `-NoProfile -NonInteractive`, block bare executables that would resolve from the workspace current directory or any workspace `PATH` entry including `cmd /c` inner commands, translate simple policy-approved `cmd /c` and `cmd.exe /c` wrappers to `sh -c` on POSIX hosts, add top-level Windows shell startup hardening only to the launched argv while preserving the reviewed command string and approval digest, and let persisted rules override or refine defaults by executable, exact command, command substring, argument substring, or agent role only after non-downgradable host-boundary checks pass.
