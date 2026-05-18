# How To Use DGentic

Date created: 2026-05-07

DGentic is currently in backend MVP development with an initial same-origin web dashboard. This guide explains how to use the repository now and how the platform is expected to be used as implementation continues.

## Use The Repository Today

### 1. Read The Goal

Start with `docs/DGentic-goal.md`. This is the source specification for the platform vision, required capabilities, architecture, security model, memory system, tool runtime, interfaces, and configuration settings.

### 2. Plan Work From The Agile Backlog

Use `docs/planning/agile-task-plan.md` to choose the next implementation work. The plan is organized into:

- Epics
- User stories
- Acceptance criteria
- Engineering tasks
- Milestones
- Initial Sprint 1 backlog

### 3. Record Progress

Update `docs/progress/project-progress-log.md` whenever meaningful work is completed. Each entry should include:

- Date
- Status
- Completed work
- Decisions
- Blockers
- Next steps

### 4. Keep Documentation Organized

Use these documentation folders:

- `docs/planning/` for Agile plans, roadmaps, sprint plans, and backlog notes.
- `docs/progress/` for progress logs, status reports, and decisions.
- `docs/architecture/` for system diagrams, technical designs, contracts, and security models.
- `docs/how-to/` for setup, usage, operations, and troubleshooting.

### 5. Run The Current Backend MVP

Use `docs/how-to/developer-setup.md` to install dependencies, run the FastAPI service, call the starter task planning endpoint, and run verification commands.

Current useful API checks:

```powershell
curl http://127.0.0.1:8000/health
```

Open the first Sprint 16 dashboard shell after starting the backend:

```text
http://127.0.0.1:8000/ui/
```

The dashboard provides health, first chat-style task submission with capped browser-local transcript history, Task Chat provider route preview through the existing routing contract with explicit route-to-reply handoff, Task Chat provider replies through existing guarded provider generation or streaming routes with selectable message roles, Task Chat provider approval requests through the existing guarded provider approval route using the selected role, Task Chat approval outcome cards after decisions or executions with explicit outcome-to-reply handoff, Task Chat handoff packet Markdown/JSON preview and copy controls, task-chat execution transcript/status cards for deterministic plan runs, fresh task-chat plan to orchestration-run creation through `/tasks/orchestrations`, task-chat context cards for active root, task/run counts, orchestration-run counts, active memory metadata, session summaries, pending approvals, recent activity, insertable plan/run/orchestration/memory/session/approval/log/provider-response/provider-route/approval-outcome context, plan/run/orchestration/memory/session/log/provider-reply/provider-approval/provider-route/approval-outcome cards that can insert follow-up context, apply provider routes, ask through selected routes, ask with bounded approval outcome context, reuse approval IDs, open exact reviews, or add evidence back into the composer, task planning, active root context visibility, project root preflight, registration, metadata edit/archive/restore controls for registered projects, and guarded Open controls, active-root workspace file browsing/editing with guarded change preview/apply/revert controls, guided orchestration task graph creation with raw JSON fallback, orchestration summary and detail with task graph, expandable per-task sub-agent briefs, parent-child agent graph visibility, task update/recovery/blocker resolution/closeout controls, blockers, follow-ups, execution records, and cycle/loop/background execution controls, unified approval source/status filtering, structured source-specific approval review summaries, review and approve/deny actions, approved CLI execution, CLI run output inspection, command recipe preview/approval/run/execute controls plus local command recipe creation/edit/toggle controls, local plugin trust/block controls plus plugin activation preview/list/install/disable controls, network policy preflight checks and approval requests, filesystem guardrail preflight checks and approval requests with action-specific options/content fields, structured Git workflow checkpoint blockers/warnings/diff-stat review plus AI-change metadata summary, checkpoint-bound raw Git diff review with session accept/reject decisions, decision filters, bulk visible decisions, per-section patch copy, reviewer rationale notes, metadata-only saved review artifacts that can be applied only to matching fresh checkpoint reviews, checkpoint-bound commit/push/PR approval creation, and direct checkpoint-bound Git commit/push/PR run controls, provider/tool summary with per-provider health checks, routing preview, provider routing settings review, provider approval request creation, provider generation and streaming execution with optional bound provider/network approval IDs and task-chat response context insertion, and generated-tool governance plus approval request controls, memory lifecycle summaries, active-memory task-chat context insertion, read-only hybrid memory retrieval, lifecycle preview/apply with policy threshold controls, compression preview/apply, tool-registry reliability summaries, memory/tool detail drilldowns, guarded quick edits for editable memory metadata, CLI policy, hook policy, plugin trust, policy source/status summaries, local CLI, hook policy, and network policy rule creation/edit/toggle controls, grouped effective settings with managed-field, policy-lock, and provider-role-routing summaries, Activity session summary capture/list/use-context controls, session log filtering, Activity log Use Context/Copy Evidence controls, and log polling. In development, auth is off unless explicitly enabled. In staging and production, enter a bearer token with `admin` capability before using project registration, project metadata updates, Open controls, or settings review; use a token with `cli` capability for Git checkpoint diff review, Git review artifact save/load, Git checkpoint approval creation, direct Git workflow runs, local CLI policy rule creation or updates, local command recipe creation or updates, and plugin command recipe activation; use a token with `filesystem` capability for filesystem guardrail preflight, workspace file apply/revert, filesystem approval requests, and guarded filesystem execution; use a token with `memory` capability for memory retrieval, memory-to-task-chat context insertion, memory detail drilldowns, metadata quick edits, lifecycle preview/apply, and compression preview/apply; use a token with `sessions` capability for session summary capture/list flows, a token with `logs` capability for log polling, filtering, and Activity log context handoff, use a token with `hooks` capability for local hook policy rule creation or updates and plugin hook-policy activation; use a token with `tools` capability for local plugin trust changes, inert reference component activation, tool detail drilldowns, generated-tool governance updates, and generated-tool approval request creation; use a token with `network` capability for network policy preflight checks and web-retrieval approval requests, `providers` capability for provider health checks, routing preview, and provider generation, or the relevant approval capability for generic network and provider approval creation. A token with `tasks` but not `agents` can still load orchestration task data, but the richer sub-agent brief and graph panels will show agent detail as unavailable.

The Policy panel can also create, edit, and enable or disable local network-domain policy rules. Those controls use `POST /network/policy/rules`, `GET /network/policy/rules`, and `PATCH /network/policy/rules/{rule_id}` and require the `network` capability when auth is enabled. Managed network rules render first and read-only; a managed `network_policy` lock blocks local rule mutation while leaving list and preflight checks available.

The task area now includes a first task-chat composer that submits a message to the existing `/tasks/plan` contract, renders the created plan in a transcript, and can run that plan through `/tasks/execute`. The Task Chat provider controls include a Message Role selector for the backend-supported `user`, `system`, `developer`, `assistant`, and `tool` roles; the selected role is used for both Ask Provider and Request Approval payloads. Provider Route cards can Use Route to fill provider/model controls, Use Route & Ask to invoke the existing guarded provider reply path with the current composer/provider control state, or Use Context to insert route rationale. Approval decisions, approved CLI execution, and dashboard-callable bound execution append bounded Approval Outcome cards with Use Outcome, Use Outcome & Ask, and Review actions; Use Outcome & Ask inserts bounded non-capability outcome context before using the existing provider reply path and does not expose raw outcome IDs or copy them into provider approval fields. The Handoff Packet panel generates a bounded client-side continuation bundle from the current composer, active root, context stream, Activity/session/log evidence, approvals, provider route/reply metadata, and transcript summaries, then copies Markdown or `dgentic.task-chat-handoff.v1` JSON without creating backend packet state. When a chat plan runs, the transcript updates a single execution card from running to completed or failed, summarizes deterministic step results, refreshes task counts and context cards, and exposes `Use Evidence` so follow-up turns can include the exact run summary without retyping it. Fresh plan cards also expose `Create Orchestration`, which maps the plan steps to the existing `/tasks/orchestrations` create contract, shows the new orchestration run in the transcript, selects the run in the orchestration detail panel, and intentionally does not call orchestration cycle, loop, or detached execution endpoints. Plan cards expose a `Use Context` action, run rows expose a `Use Evidence` action, orchestration context cards plus created-run transcript cards expose `Use Context`, active memory cards and memory detail/retrieval rows expose `Use In Task Chat`, session summary cards expose `Use Context`, and pending approval context cards expose `Review` to open the exact safe approval review in the unified inbox. The Activity panel can capture session summaries through `/sessions/summary`, list recent summaries, filter `session` events through `/logs`, and insert bounded summary context into Task Chat. The transcript is saved in capped browser-local history and restored after reloads; the Clear control removes saved history. Restored plan cards are display-only so stale saved plans are not directly re-run or converted to orchestration runs, and bearer tokens remain session-only. The structured planner still renders recent plans as actionable cards with constraints, acceptance criteria, step detail, related deterministic run history, and a Run Plan control.

Approved non-CLI approval reviews now show guided editable bound execution request panels instead of a direct CLI-style execute button. Filesystem, web retrieval, provider, and tool approvals require their normal execution endpoint plus the approved `approval_id` and matching request fields; the dashboard shows the endpoint, a safe payload scaffold, recursive guided fields for nested objects and arrays, editable JSON, binding validation, execution output, and approval refresh. Provider/tool network approvals are handoff-only because they must be consumed as `network_approval_id` by the matching provider or tool execution request.

Project Open switches the active runtime `rootDir` only inside the current FastAPI process. DGentic pins a relative `DGENTIC_DATA_DIR` to its current absolute path before switching so state does not silently move to the newly opened project. Opening a project is blocked while CLI runs are starting/running, orchestration executions or tasks are active, or CLI/filesystem/network/provider/tool approvals are pending or approved but not executed. The Project panel can edit registered project names and archive or restore non-active project records through the existing metadata update route; archived projects cannot be opened until restored. Restart-stable active project selection and distributed multi-worker activation locks remain follow-up work.

In local development, API authentication is off by default. In `staging` and `production`, protected routes require bearer tokens. Operators can bootstrap with `DGENTIC_AUTH_TOKENS`, such as `admin-token=admin;task-token=tasks`, then create persisted operator profiles, operator groups, and generated tokens through the auth APIs. Operator records live in `operators.json`, operator group records live in `operator-groups.json`, persisted token records live in `auth-tokens.json` under `DGENTIC_DATA_DIR`, stored tokens use salted PBKDF2 hashes instead of raw token values, and the raw token is returned only in the create or rotate response. New persisted tokens must target an active operator and cannot exceed that operator's current effective capabilities from direct assignments plus active group-inherited capabilities. Operator display/role metadata, operator group display/description metadata, generated-token labels, credential-reference labels, plugin trust reasons, and hook policy reasons are redacted for common secret-shaped values before responses, audit metadata, and new or mutated JSON state. Plugin discovery, trust, and inert component preview/list/install/disable routes require `tools`, plugin command recipe activation requires `tools` plus `cli` or `admin`, and plugin hook-policy activation requires `tools` plus `hooks` or `admin`. Hook policy rule routes require `hooks`. CLI approval creation, approved-command execution, git workflow checkpoints, and git commit/push/PR approval creation require `cli`; CLI approval list, review, approve, and deny routes require `approvals`. The effective-settings endpoint requires `admin` when authentication is enabled. When authentication is enabled, startup fails closed if no usable environment token or active persisted token is configured.

Set `DGENTIC_MANAGED_SETTINGS_FILE` to load deployment-owned runtime policy settings from a JSON file. The managed file must contain a top-level `settings` object; supported managed fields override `.env` and process environment values, unsupported bootstrap or secret-bearing fields fail closed, and `GET /settings/effective` returns redacted values with source labels plus the managed-file digest for audit.

Managed settings can also lock selected mutable policy surfaces so deployment-owned policy stays read-only through the API while operators can still list, preview, or evaluate current policy state:

```json
{
  "settings": {
    "managed_policy_locks": [
      "cli_policy",
      "network_policy",
      "command_recipes",
      "hook_policy",
      "plugin_trust",
      "plugin_components",
      "plugin_command_recipes",
      "plugin_hook_policies"
    ]
  }
}
```

`managed_policy_locks` only takes effect from `DGENTIC_MANAGED_SETTINGS_FILE`; the same value from a normal environment variable is ignored for locking. Locked surfaces reject mutation routes with `403`, including CLI policy create/update, network policy create/update, command recipe create/update, hook policy create/update, plugin trust changes, plugin reference component install/disable, plugin command recipe install/disable, and plugin hook-policy install/disable. Read routes, recipe previews, plugin discovery, plugin component previews/lists, plugin activation previews, command-policy and network-policy evaluation, and git checkpoints remain available.

Managed settings can also publish read-only CLI policy rules. `managed_cli_policy_rules` is honored only when it comes from `DGENTIC_MANAGED_SETTINGS_FILE`; the same value in a normal environment variable is ignored for managed-rule loading. Managed CLI policy rules are validated fail-closed, listed with `source: "managed"` by `GET /cli/policy/rules`, evaluated before local mutable rules, and cannot be patched through `/cli/policy/rules/{rule_id}`. Local CLI policy rules can still be created and updated unless `managed_policy_locks` includes `cli_policy`:

```json
{
  "settings": {
    "managed_cli_policy_rules": [
      {
        "id": "managed.deploy-review",
        "name": "Managed deploy review",
        "match_type": "contains",
        "pattern": "deploy",
        "permission_mode": "approval_required",
        "reason": "Deployment commands require managed approval.",
        "agent_roles": ["developer", "qa"],
        "priority": 10
      }
    ]
  }
}
```

The same managed-source pattern is available for hook policies through `managed_hook_policy_rules`. Managed hook rules are validated with the hook-policy schema plus stable non-secret pattern checks, listed with `source: "managed"` by `GET /guardrails/hooks/rules`, evaluated before local and plugin-installed hook rules, excluded from `hook-policy-rules.json`, and rejected by normal hook-policy PATCH routes. Local hook rules and plugin hook-policy activation still work unless the corresponding `hook_policy` or `plugin_hook_policies` managed lock is active:

```json
{
  "settings": {
    "managed_hook_policy_rules": [
      {
        "id": "managed.deploy-hook",
        "name": "Managed deploy hook",
        "surface": "command",
        "action": "execute",
        "match_type": "contains",
        "pattern": "deploy",
        "effect": "approval_required",
        "reason": "Deployment commands require managed hook approval.",
        "agent_roles": ["developer", "qa"],
        "priority": 10
      }
    ]
  }
}
```

Deployment-owned command recipes can be published through `managed_command_recipes`. Managed recipes are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, validated fail-closed for duplicate normalized fields, duplicate normalized ids, unsafe templates, unused or undeclared parameters, and secret-shaped text, listed with `source: "managed"` by `GET /cli/recipes`, and returned by `GET /cli/recipes/{recipe_id}`. They use the existing recipe preview, execute, approval, and run routes, but they are never written to `command-recipes.json`; local or plugin recipe mutation routes cannot create, patch, or shadow a managed recipe id:

```json
{
  "settings": {
    "managed_command_recipes": [
      {
        "id": "managed.git-status",
        "name": "Managed git status",
        "command_template": "git status --short {{path}}",
        "parameters": [
          {
            "name": "path",
            "default": "."
          }
        ],
        "tags": ["managed", "git"]
      }
    ]
  }
}
```

Deployment-owned credential references can be published through `managed_credential_references`. Managed credential references are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, support `env`, `external_process`, and `secret_manager` source metadata, are listed by `GET /credentials/references` with `source: "managed"`, can be used anywhere a credential reference id is accepted, and are never written to `credential-references.json`. Local rows with the same id are shadowed, local rows that spoof `source: "managed"` are ignored, and managed ids cannot be revoked through the local credential API:

```json
{
  "settings": {
    "managed_credential_references": [
      {
        "id": "managed.provider-key",
        "source_type": "env",
        "env_var": "OPENAI_API_KEY",
        "label": "Managed provider key",
        "purpose": "provider",
        "status": "active"
      }
    ]
  }
}
```

HashiCorp Vault KV v2 credential adapters can also be declared through managed settings or environment settings. Configure `credential_secret_manager_adapters` with metadata only, add the exact normalized Vault base URL to `credential_secret_manager_allowed_base_urls`, and store the Vault token in the adapter's `token_env_var`. DGentic resolves the Vault secret only at provider/runtime transport time, disables redirects and proxies for the Vault HTTP call, rejects non-HTTPS non-localhost Vault URLs, blocks `deny` or `approval_required` network-policy modes before token lookup, and never persists the Vault token or resolved secret:

```json
{
  "settings": {
    "credential_secret_manager_adapters": {
      "vault-main": {
        "type": "hashicorp_vault_kv2",
        "base_url": "https://vault.example.test/v1",
        "mount": "secret",
        "field": "api_key",
        "token_env_var": "DGENTIC_VAULT_TOKEN"
      }
    },
    "credential_secret_manager_allowed_base_urls": "https://vault.example.test/v1",
    "managed_credential_references": [
      {
        "id": "managed.provider-vault",
        "source_type": "secret_manager",
        "adapter_id": "vault-main",
        "secret_name": "providers/openai",
        "purpose": "provider",
        "status": "active"
      }
    ]
  }
}
```

Deployment-owned network rules can be declared with `managed_network_domain_policy_rules`. These records are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, evaluate before local `network_domain_policy.rules`, and are useful when provider, web retrieval, generated-tool, or Vault egress policy must be centrally enforced. Each record needs a stable non-secret `id`, an exact host or `*.example.test` domain, and a mode of `allow`, `audit`, `deny`, or `approval_required`; optional `reason`, `enabled`, and `priority` fields control review text, rollout toggles, and ordering:

```json
{
  "settings": {
    "managed_network_domain_policy_rules": [
      {
        "id": "managed.provider-egress",
        "domain": "provider.example.test",
        "mode": "approval_required",
        "reason": "Deployment review required for provider egress.",
        "priority": 10
      }
    ]
  }
}
```

Network policy decisions include safe `matched_rule_id` and `matched_rule_source` metadata, and approval bindings are invalidated when the effective managed rule identity, mode, reason, priority, domain, or enabled state changes. Generated tools receive only a sanitized domain/mode policy handoff, not managed ids, reasons, settings paths, or approval digests.

Local network-domain policy rules are stored separately from the managed settings file and legacy `network_domain_policy` JSON. Managed rules evaluate first, legacy environment/config JSON rules stay compatible, and local persisted rules evaluate after those sources. Use the dashboard Policy panel or the guarded `/network/policy/rules` API to add, edit, or disable local rules.

Managed settings can also pin plugin trust to exact manifest digests through `managed_plugin_trust_records`. These records are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, reported with `trust_source: "managed"` by `GET /plugins`, override local `plugin-trust.json` records for the same plugin id, reject local trust mutation as read-only, and become `stale` when the manifest bytes change:

```json
{
  "settings": {
    "managed_plugin_trust_records": [
      {
        "plugin_id": "example-plugin",
        "manifest_digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "status": "trusted",
        "reason": "Deployment reviewed this exact manifest digest.",
        "decided_by": "platform-security"
      }
    ]
  }
}
```

Managed settings can also publish inert plugin component records through `managed_plugin_component_records`. These records are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, are returned by `GET /plugins/{plugin_id}/components` with `source: "managed"`, shadow same-id local `plugin-components.json` rows, never persist to local plugin component state, and make local component install/disable routes read-only for the managed plugin id. The list route reports managed records as `stale` when the plugin manifest digest changes and `drifted` when the referenced component bytes are missing, resized, or digest-mismatched:

```json
{
  "settings": {
    "managed_plugin_component_records": [
      {
        "plugin_id": "example-plugin",
        "component_type": "tools",
        "name": "Reviewed scanner metadata",
        "manifest_digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "component_path": "tools/scanner.json",
        "component_digest": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "component_size_bytes": 2048,
        "status": "installed"
      }
    ]
  }
}
```

Example protected request in production mode:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/plan `
  -H "Authorization: Bearer task-token" `
  -H "Content-Type: application/json" `
  -d '{"objective":"Create a guarded task plan for indexing project memory."}'
```

Create an operator group, assign it to an operator, issue a persisted token inside the operator's effective capabilities, and rotate that token with a bootstrap admin token:

```powershell
$group = curl -X POST http://127.0.0.1:8000/auth/operator-groups `
  -H "Authorization: Bearer admin-token" `
  -H "Content-Type: application/json" `
  -d '{"group_id":"group-ops","display_name":"Operations","capabilities":["logs"]}'

$operator = curl -X POST http://127.0.0.1:8000/auth/operators `
  -H "Authorization: Bearer admin-token" `
  -H "Content-Type: application/json" `
  -d '{"operator_id":"operator-alpha","display_name":"Operator Alpha","role":"automation","capabilities":["tasks"],"group_ids":["group-ops"]}'

$created = curl -X POST http://127.0.0.1:8000/auth/tokens `
  -H "Authorization: Bearer admin-token" `
  -H "Content-Type: application/json" `
  -d '{"operator_id":"operator-alpha","label":"task automation","capabilities":["tasks","logs"]}'

curl -X POST "http://127.0.0.1:8000/auth/tokens/$($created.record.id)/rotate" `
  -H "Authorization: Bearer admin-token" `
  -H "Content-Type: application/json" `
  -d '{"label":"rotated task automation","capabilities":["tasks","logs"]}'
```

SQLAlchemy-backed metadata and tool registry services use SQLite at `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db` by default. Set `DGENTIC_DATABASE_URL` to point those services at another SQLAlchemy database URL. Ordered schema migrations are tracked in `schema_migrations`, and file-backed SQLite state can be backed up or restored with the local `backup_sqlite_database` and `restore_sqlite_database` helpers.

Local vault credential references can be re-encrypted after a Fernet key change through `POST /credentials/references/local-vault/rotate-key` with a principal that has the `credentials` capability. The request supplies `current_vault_key` and `new_vault_key`; the response returns only `rotated_count`, `skipped_count`, and `rotated_at`. The operation rotates every persisted `local_vault` record in one transaction, skips environment and external-process references, fails without partial writes on wrong keys or malformed ciphertext, and does not expose keys, plaintext, or ciphertext in API responses or audit metadata.

Plugin manifests can be discovered through `GET /plugins`, inspected through `GET /plugins/{plugin_id}`, and explicitly trusted or blocked through `PATCH /plugins/{plugin_id}/trust`. DGentic reads only direct manifests at `DGENTIC_ROOT_DIR/plugins/[plugin_id]/dgentic-plugin.json`, computes a SHA-256 digest over the raw manifest bytes, returns redacted safe metadata, persists trust records in `plugin-trust.json`, and marks trust `stale` when the manifest changes. Discovery rejects symlinked, out-of-root, oversized, malformed, or id-mismatched manifests. Trusted current manifests can preview inert `agent_blueprints`, `skills`, `tools`, and `docs` component references through `POST /plugins/{plugin_id}/components/preview`; this returns type/name/path/digest/size metadata only and does not parse, import, index, install, load, or execute referenced content. `POST /plugins/{plugin_id}/components/install` persists the same inert provenance metadata to `plugin-components.json`, `GET /plugins/{plugin_id}/components` lists local plus deployment-managed installed or disabled records, and `POST /plugins/{plugin_id}/components/disable` disables local records without deleting history. Managed component records from `DGENTIC_MANAGED_SETTINGS_FILE` are read-only, never persisted locally, filter local spoof rows that claim `source: "managed"`, shadow local rows with the same computed component id, and surface `stale` or `drifted` provenance status. Trusted current manifests can also activate declarative command recipe and hook-policy JSON components, but activation only reads bounded JSON files, records manifest/component digest provenance, and still executes through the normal CLI or hook-policy contracts; DGentic does not import plugin code, run plugin scripts, or load plugin hooks/tools/agents/skills in this slice. The `/ui/` Policy panel exposes these same plugin activation routes with managed lock read-only states for `plugin_components`, `plugin_command_recipes`, and `plugin_hook_policies`.

```powershell
curl -X POST http://127.0.0.1:8000/tasks/plan `
  -H "Content-Type: application/json" `
  -d '{"objective":"Create a guarded task plan for indexing project memory."}'
```

```powershell
curl http://127.0.0.1:8000/tasks/plans
```

Create a backend-managed orchestration run for a role-bounded task graph:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations `
  -H "Content-Type: application/json" `
  -d '{"objective":"Coordinate a sprint slice.","required_dod_evidence":["tests","review"],"tasks":[{"id":"dev-implementation","title":"Implement source changes","description":"Modify production code only.","role":"Developer","declared_write_paths":["src/dgentic/orchestration.py"],"expected_output":"Source changes are ready.","validation":"Developer smoke passes."},{"id":"qa-validation","title":"Validate behavior","description":"Add tests only.","role":"QA","declared_write_paths":["tests/test_orchestration.py"],"expected_output":"Focused tests pass.","validation":"pytest tests/test_orchestration.py passes."},{"id":"pm-closeout","title":"Record progress","description":"Update sprint status after validation.","role":"PM","dependencies":["dev-implementation","qa-validation"],"declared_write_paths":["docs/progress/project-progress-log.md"],"expected_output":"Progress is recorded.","validation":"DoD evidence is present."}]}'
```

The response includes `role_boundary_decisions`, `scheduled_task_ids`, blockers, follow-ups, and sub-agent ids for tasks that are dependency-ready and inside their role write boundary. The create request accepts client-owned task specs only; lifecycle fields such as `status`, `agent_id`, `output`, `error`, and `completed_at` are server-owned. Update running tasks as agent work completes:

```powershell
curl -X PATCH http://127.0.0.1:8000/tasks/orchestrations/[run_id]/tasks/dev-implementation `
  -H "Content-Type: application/json" `
  -d '{"status":"completed","output":{"source":"implemented"}}'
```

Run an orchestration execution cycle when spawned agent lifecycle state changed. A cycle reconciles terminal agent statuses back into running tasks, applies retry or blocked behavior, and schedules any newly ready dependent tasks:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/cycle
```

Run a bounded autonomous loop when the backend should continue cycling until it reaches waiting agents, blockers, all-complete state, quiescence, or the iteration limit:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/loop `
  -H "Content-Type: application/json" `
  -d '{"max_iterations":10,"stop_on_blocked":true}'
```

Start the same bounded loop as a detached process-local background execution when the API caller should get an immediate `202` response and poll completion separately:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/executions `
  -H "Content-Type: application/json" `
  -d '{"max_iterations":10,"stop_on_blocked":true}'
```

Poll or list detached execution records:

```powershell
curl http://127.0.0.1:8000/tasks/orchestrations/[run_id]/executions/[execution_id]
curl http://127.0.0.1:8000/tasks/orchestrations/[run_id]/executions
```

Cancel a detached execution when the backend should stop the detached loop without cancelling already spawned task/agent work:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/executions/[execution_id]/cancel
```

Detached execution records are persisted with `starting`, `running`, `cancelling`, `cancelled`, `completed`, `failed`, or `stale` status. DGentic rejects a second active execution or foreground loop/advance/cycle scheduler call for the same orchestration run with a conflict response, keeps `cancelling` executions active until the owning worker finalizes them, renews a process-local heartbeat and a private scheduler lease while a detached worker is running, adopts expired `starting`/`running` records from prior supervisors for open runs on backend startup, finalizes expired `cancelling` records as cancelled, marks duplicate or non-resumable stale records safely, and redacts failure errors before persistence. Scheduler passes persist fenced task claims and fixed agent ids before spawning agents, repair missing agent rows by reusing the persisted id, and roll back unspawned claims if agent spawn fails. Scheduler leases are stored in `orchestration-scheduler-leases.json` under `DGENTIC_DATA_DIR`, expire after 300 seconds, and are renewed by the detached heartbeat path every 30 seconds; execution API responses expose only `scheduler_lease_id`, not the private lease token. This is JSON-backed local MVP coordination, not a replacement for a future distributed queue or SQL row-lock scheduler in a horizontally scaled deployment.

Get an owner-scoped operations summary for visible orchestration runs, task/execution status counts, active/stale execution ids, and open blocker/follow-up totals:

```powershell
curl http://127.0.0.1:8000/tasks/orchestrations/operations/summary
```

When a dependent task is scheduled, DGentic includes the run objective plus redacted, bounded summaries of completed dependency outputs in the spawned agent brief context. The dependent agent still receives dependency ids in `required_data` for traceability.

For opt-in shared memory, set `shared_memory_tags` on the orchestration or an individual task. When a tagged task completes, DGentic upserts one SQL metadata record in category `orchestration_context` with a redacted, bounded task-output summary. Later tagged tasks receive up to three active matching summaries in their spawned agent brief context. DGentic only injects records produced by completed orchestration tasks, scoped to the same authenticated orchestration owner (or local `system` owner when auth is disabled); arbitrary metadata rows, tampered service-authored rows, and inactive lifecycle records are ignored, and a consumer's tags must cover all tags on the stored shared-memory record. The public metadata API cannot create, patch, or delete `orchestration_context` rows, and authenticated non-admin callers only see orchestration shared-memory metadata and orchestration agent briefs for runs they own. The default `shared_memory_policy` is `owner`, which allows reuse across runs owned by the same actor after the provenance, lifecycle, and tag checks pass. Set `shared_memory_policy` to `run` when memory reuse must stay inside the same orchestration run; if either the source run or consumer run uses `run`, cross-run reuse is skipped.

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations `
  -H "Content-Type: application/json" `
  -d '{"objective":"Reuse QA learnings within this run.","shared_memory_tags":["qa-context"],"shared_memory_policy":"run","tasks":[{"id":"qa-validation","title":"QA validation","description":"Validate with run-scoped shared memory.","role":"QA","declared_write_paths":["tests/test_api.py"],"validation":"QA receives shared memory."}]}'
```

You can filter visible SQL metadata records by tag through the metadata API:

```powershell
curl "http://127.0.0.1:8000/api/v1/memory/metadata?category=orchestration_context&tags=qa-context"
```

Recover a system-blocked task only after recording the resolution. Recovery supports role-boundary and retry-exhaustion blockers; manual blockers stay unresolved for separate review. Recovery may also correct the task role or declared write paths, then DGentic revalidates role boundaries before clearing task blockers/follow-ups and rescheduling dependency-ready work:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/tasks/qa-validation/recover `
  -H "Content-Type: application/json" `
  -d '{"resolution":"Reassigned implementation work to Developer.","role":"Developer","declared_write_paths":["src/dgentic/orchestration.py"],"reset_retry_count":true}'
```

Resolve a manual or security blocker through an explicit admin-reviewed path. The blocker remains in the run history with resolution metadata. When no unresolved blockers remain, the task becomes pending; `reschedule` controls whether DGentic schedules it immediately:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/blockers/[blocker_id]/resolve `
  -H "Content-Type: application/json" `
  -d '{"resolution":"Security accepted the documented mitigation.","reschedule":true}'
```

Close an orchestration only after every task is completed and required Definition of Done evidence is present:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/orchestrations/[run_id]/close `
  -H "Content-Type: application/json" `
  -d '{"evidence":{"tests":"pytest tests/test_orchestration.py passed","review":"Reviewer reported no blockers."}}'
```

Every persisted orchestration state change also regenerates two project documents: `docs/progress/orchestration-runs.md` for run status and `docs/planning/orchestration-follow-ups.md` for open follow-ups and unresolved blockers. The generated text is redacted for common secret-shaped values, completed runs are excluded from the open follow-up backlog, and sync failures are audited without rolling back the orchestration state transition.

Filesystem requests can optionally include `agent_id`, `agent_role`, and `task_id` from a running orchestration task. When all three are present, write actions must target the task's declared write paths; read-only filesystem actions are allowed for the bound running task. Omitting all three fields preserves the existing non-orchestrated filesystem behavior:

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/write `
  -H "Content-Type: application/json" `
  -d '{"agent_id":"[agent_id]","agent_role":"QA","task_id":"qa-validation","path":"tests/test_orchestration.py","content":"# orchestration-bound update"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/guardrails/commands `
  -H "Content-Type: application/json" `
  -d '{"command":"git status"}'
```

Explicit executable paths must resolve inside the configured workspace. Direct commands, shell-wrapped commands, and launcher payloads such as PowerShell `Start-Process` are blocked when the executable path points outside `rootDir`; configured safe rules cannot downgrade that boundary.

Command guardrail and runtime requests may also include `agent_id`, `agent_role`, and `task_id`. When supplied context is evaluated during active orchestration work, all three fields must match a running task before command policy evaluation or CLI execution continues. Context that references a known but non-running task is rejected as stale. Omitting orchestration context preserves the existing non-orchestrated behavior, and unknown legacy agent/task context remains accepted only when it does not collide with active orchestration work:

```powershell
curl -X POST http://127.0.0.1:8000/guardrails/commands `
  -H "Content-Type: application/json" `
  -d '{"command":"git status","agent_id":"[agent_id]","agent_role":"Developer","task_id":"dev-implementation"}'
```

Create a persisted argument-aware CLI policy rule:

```powershell
curl -X POST http://127.0.0.1:8000/cli/policy/rules `
  -H "Content-Type: application/json" `
  -d '{"name":"Block unsafe flag","match_type":"argument_contains","pattern":"--unsafe","permission_mode":"blocked","reason":"Unsafe flag is blocked by workspace policy.","priority":5}'
```

Create a role-scoped CLI policy rule:

```powershell
curl -X POST http://127.0.0.1:8000/cli/policy/rules `
  -H "Content-Type: application/json" `
  -d '{"name":"Developers may inspect git","match_type":"executable","pattern":"git","permission_mode":"autopilot_safe","reason":"Developer git inspection is allowed.","agent_roles":["developer"],"priority":5}'
```

```powershell
curl http://127.0.0.1:8000/cli/policy/rules
```

```powershell
curl -X PATCH http://127.0.0.1:8000/cli/policy/rules/[rule_id] `
  -H "Content-Type: application/json" `
  -d '{"enabled":false}'
```

Configured-safe `git` rules are intentionally limited to recognized read-only inspections such as `git status`, `git diff`, `git log`, and similar metadata commands. Mutating or ambiguous subcommands such as `git add`, `git commit`, `git push`, `git branch -D`, `git reset`, `git checkout`, `git switch`, `git merge`, `git rebase`, `git tag`, and shell-wrapped equivalents still require approval even when a broad executable rule marks `git` as autopilot-safe.

Managed CLI policy rules follow the same non-downgrade protections as local configured rules. A managed `autopilot_safe` rule cannot bypass hard-coded approval requirements for mutating `git`, GitHub CLI, DGentic state-file reads, shell-wrapper risks, executable path boundaries, or startup hardening.

Create a read-only git workflow checkpoint before preparing a commit, push, or PR:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/checkpoints `
  -H "Content-Type: application/json" `
  -d '{"action":"commit","test_evidence":["python -m pytest tests/test_git_workflows.py -q"],"requested_by":"operator"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/checkpoints `
  -H "Content-Type: application/json" `
  -d '{"action":"push","test_evidence":["python -m pytest -q --maxfail=1 -x"],"requested_by":"operator"}'
```

The checkpoint response includes branch/head/upstream metadata, upstream remote name, a remote URL digest, ahead/behind counts, staged/unstaged/untracked counts, redacted changed paths, diff stats, blockers, warnings, and a `checkpoint_digest`. Commit checkpoints require staged changes and test evidence; push and PR checkpoints require a clean worktree, test evidence, and a non-protected branch. Staged protected files such as `.env` or `.pem` files and secret-shaped staged additions block readiness. The digest includes internal staged and unstaged diff hashes plus the remote URL digest without returning raw diff text or raw remote URLs, so later staged-content or remote-target changes invalidate the checkpoint.

Load a checkpoint-bound raw Git diff review for tracked staged and unstaged content:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/diff-reviews `
  -H "Content-Type: application/json" `
  -d '{"action":"commit","checkpoint_digest":"sha256:[checkpoint-digest]","test_evidence":["python -m pytest tests/test_git_workflows.py -q"],"include_staged":true,"include_unstaged":true,"context_lines":3,"requested_by":"operator"}'
```

`POST /cli/git/diff-reviews` re-runs the selected checkpoint action and requires the supplied digest to match the fresh repository state before returning patch sections. It returns staged and/or unstaged tracked patches only, excludes untracked file content, omits protected or secret-shaped paths, redacts secret-shaped patch text, caps each returned section, and records audit metadata without patch bodies. In `/ui/`, loaded diff sections can be accepted, rejected, cleared, and annotated with bounded reviewer rationale notes; rejected sections pause the dashboard Git approval/direct-run buttons until the reviewer clears or accepts them, while backend checkpoint readiness remains the authoritative safety boundary. Saved change-review artifacts persist only metadata, sanitized notes, and section digests for matching fresh checkpoints, not raw patch bodies.

Create a pending approval for a commit from a fresh ready checkpoint:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/commit-approvals `
  -H "Content-Type: application/json" `
  -d '{"checkpoint_digest":"sha256:[checkpoint-digest]","commit_message":"Add guarded commit approval","test_evidence":["python -m pytest -q --maxfail=1 -x"],"requested_by":"operator"}'
```

`POST /cli/git/commit-approvals` re-runs the commit checkpoint, requires the supplied digest to match the fresh ready state, validates a single-line non-secret commit message, and queues a normal pending CLI approval for `git commit -m ...`. It does not execute the commit; execution still requires the existing CLI approval review, approve, and execute flow.

Create a pending approval for a push from a fresh ready checkpoint:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/push-approvals `
  -H "Content-Type: application/json" `
  -d '{"checkpoint_digest":"sha256:[checkpoint-digest]","test_evidence":["python -m pytest -q --maxfail=1 -x"],"requested_by":"operator"}'
```

`POST /cli/git/push-approvals` re-runs the push checkpoint, requires a matching ready digest, requires an upstream remote URL digest, requires local commits ahead of upstream, rejects branches that are behind upstream, and queues a workflow-bound pending CLI approval for exactly `git push`. The request does not accept remote, branch, refspec, flag, environment, or arbitrary command fields. Commit and push approvals store a workflow binding in the CLI approval record; `/cli/approvals/{approval_id}/execute`, `/cli/execute`, and `/cli/runs` revalidate the current git checkpoint before claiming a workflow-bound approval. Push approval creation does not perform a network push; the later approved `git push` execution can perform network I/O through the normal CLI approval path.

Create a pending approval for PR creation from a fresh ready checkpoint after the branch has already been pushed:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/pr-approvals `
  -H "Content-Type: application/json" `
  -d '{"checkpoint_digest":"sha256:[checkpoint-digest]","title":"Open guarded PR","body":"Validation passed and branch is ready for review.","base_branch":"main","draft":true,"test_evidence":["python -m pytest -q --maxfail=1 -x"],"requested_by":"operator"}'
```

`POST /cli/git/pr-approvals` re-runs the PR checkpoint, requires a matching ready digest, requires an upstream remote URL digest, rejects branches that are ahead of or behind upstream, validates bounded single-line non-secret `title`, `body`, and optional `base_branch`, and queues a workflow-bound pending CLI approval for a constrained `gh pr create` command using the current branch as `--head`. The request does not accept remote, head branch, arbitrary command, environment, flag, label, reviewer, assignee, project, template, or browser fields. PR approval creation does not execute `gh` or perform network I/O; the later approved `gh pr create` execution can perform network I/O through the normal CLI approval path, and `/cli/approvals/{approval_id}/execute`, `/cli/execute`, and `/cli/runs` revalidate the current git checkpoint before claiming the workflow-bound approval. Broad configured-safe `gh` command policy rules cannot downgrade GitHub CLI commands to autopilot-safe. Use `POST /cli/git/pr-runs` only when the backend should create the PR directly; direct runs require an explicit `GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, or `GHE_TOKEN` environment variable for `gh`, isolate `GH_CONFIG_DIR`, and return only safe digest metadata plus a strict sanitized PR URL when one is emitted.

Create a backend hook policy rule when a cross-surface pre-action policy should attach an audited hook decision to command, filesystem, or network guardrail evaluations:

```powershell
curl -X POST http://127.0.0.1:8000/guardrails/hooks/rules `
  -H "Content-Type: application/json" `
  -d '{"name":"Review deploy command","surface":"command","action":"execute","match_type":"contains","pattern":"deploy","effect":"approval_required","reason":"Deployment commands require hook review.","priority":5}'
```

```powershell
curl http://127.0.0.1:8000/guardrails/hooks/rules
```

Hook rules are persisted in `hook-policy-rules.json`, evaluated by priority, and support `audit`, `approval_required`, and `blocked` effects. They do not load plugin hook code. Hook-forced command, filesystem, and network approval decisions are included in approval binding digests, so a later hook-rule change invalidates stale approvals. Filesystem hook `blocked` decisions enforce immediately.

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"cmd /c echo hello","timeout_seconds":5}'
```

Run a command with agent/task context and a controlled environment override. DGentic rejects override keys that can alter startup or host linking behavior, including shell startup files, dynamic-loader preloads/library paths, and interpreter option/library injection variables. Command run history stores only the applied environment variable names:

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"cmd /c echo context","requested_by":"pm","agent_id":"agent-dev-1","agent_role":"developer","task_id":"story-5.3","environment":{"DGENTIC_TEST_FLAG":"enabled"}}'
```

For orchestration-bound CLI execution, use the `agent_id`, `agent_role`, and `task_id` from the running orchestration task. Partial or mismatched active task context is blocked and the command policy decision includes the serialized orchestration decision for audit/UI consumers.

DGentic hardens top-level launches at execution time without changing the reviewed command text. Bare executable names are rejected when they would resolve from the workspace current directory or a workspace `PATH` entry; use an explicit reviewed path for workspace-local tools. `cmd`/`cmd.exe` receive `/d` to suppress Command Processor AutoRun hooks, and `powershell`/`pwsh` receive `-NoProfile -NonInteractive` unless equivalent switches are already present. Commands should not depend on profile aliases, AutoRun setup, or prompts; include required setup explicitly in the reviewed command.

In `development` and `test`, an explicit `approved: true` bypass can be used for local CLI smoke checks. In `staging` and `production`, approval-required commands need a single-use approved `approval_id`.

Start, poll, and cancel an asynchronous CLI run in local development:

```powershell
curl -X POST http://127.0.0.1:8000/cli/runs `
  -H "Content-Type: application/json" `
  -d '{"command":"python -c \"import time; time.sleep(30)\"","approved":true,"timeout_seconds":60}'
```

```powershell
curl http://127.0.0.1:8000/cli/runs/[run_id]
```

```powershell
curl "http://127.0.0.1:8000/cli/runs/[run_id]/output?after_sequence=0"
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/runs/[run_id]/cancel
```

Queue, approve, and execute an approval-required CLI command. When auth is enabled, the queue and execute calls use a token with `cli`, while list/review/approve/deny calls use a token with `approvals`:

```powershell
curl -X POST "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"command":"python --version","timeout_seconds":10,"requested_by":"operator"}'
```

```powershell
curl http://127.0.0.1:8000/cli/approvals/[approval_id]/review
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/approvals/[approval_id]/approve `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Version check is acceptable."}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/approvals/[approval_id]/execute
```

The review response is safe for UI consumers: it returns redacted command text, redacted requester and agent/task context, policy context, environment key names without values, command/environment HMAC digest identifiers, warnings for environment-bound, redacted-command, or legacy-digest approvals, and whether direct execution is available. `GET /cli/approvals` lists approval records for approval reviewers. Use the bound approval directly when executing with reviewed environment keys or when calling `/cli/execute` or `/cli/runs`:

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"python --version","timeout_seconds":10,"approval_id":"[approval_id]","requested_by":"operator"}'
```

For guarded git workflow automation, create a checkpoint before requesting an approval or direct run. A direct commit run is local-only: it rechecks the staged state, requires the fresh checkpoint digest to match, requires test evidence, validates a single-line non-secret commit message, runs `git commit -m ...` without shell expansion, disables repository hooks and GPG signing for the runner, and records only safe digest metadata:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/checkpoints `
  -H "Content-Type: application/json" `
  -d '{"action":"commit","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/commit-runs `
  -H "Content-Type: application/json" `
  -d '{"checkpoint_digest":"[checkpoint_digest]","commit_message":"Add safe local milestone","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'
```

Use `POST /cli/git/commit-approvals` instead when the commit should stay in the normal approval queue. Push and PR approvals remain available through `POST /cli/git/push-approvals` and `POST /cli/git/pr-approvals`; those routes do not run `git push`, `gh`, or network PR operations during approval creation.

A direct push run is intentionally narrower than a general `git push`: create a push checkpoint on a clean, non-protected branch with local commits ahead of its configured upstream, then pass that exact digest to `POST /cli/git/push-runs`. The runner rechecks the checkpoint, derives the remote and upstream branch from repository config, runs a shell-free `git push` only to that upstream ref, disables repository hooks and push GPG signing, and returns ahead/behind plus remote URL digest metadata without raw remote URL or command output:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/checkpoints `
  -H "Content-Type: application/json" `
  -d '{"action":"push","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/push-runs `
  -H "Content-Type: application/json" `
  -d '{"checkpoint_digest":"[checkpoint_digest]","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'
```

A direct PR run is narrower than a general `gh pr create`: create a PR checkpoint after the branch has already been pushed and is current with upstream, then pass that digest to `POST /cli/git/pr-runs`. The runner rechecks the checkpoint, requires an explicit GitHub CLI token environment, runs shell-free `gh pr create --title ... --body ... --head [current-branch]` with optional `--base` and `--draft`, isolates `gh` config in a temporary directory, rejects caller-supplied remote/head/flag/template/reviewer fields, and returns title/body digests plus a strict sanitized PR URL without raw command output:

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/checkpoints `
  -H "Content-Type: application/json" `
  -d '{"action":"pr","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/git/pr-runs `
  -H "Content-Type: application/json" `
  -d '{"checkpoint_digest":"[checkpoint_digest]","title":"Open guarded PR","body":"Validation passed.","base_branch":"main","draft":true,"test_evidence":["python -m pytest -q"],"requested_by":"operator"}'
```

Create, preview, approve, execute, and run a reusable command recipe. Recipes are persisted in `command-recipes.json`, expand safe `{{parameter}}` placeholders into an existing CLI execution request, and then use the same command policy, approval, runtime, redaction, and audit behavior as `/cli/execute` and `/cli/runs`. Recipe execution payloads do not accept `approved`; in staging and production, approval-required expanded commands must use a standard bound `approval_id`:

The `/ui/` Policy view can create, edit, enable, and disable local command recipes through the same guarded routes. Managed and plugin-owned recipes remain visible but read-only, and a managed `command_recipes` policy lock disables the local recipe editor while leaving list, preview, approval, run, and execute actions available where the backend allows them.

```powershell
curl -X POST http://127.0.0.1:8000/cli/recipes `
  -H "Content-Type: application/json" `
  -d '{"id":"git.status","name":"Git status","command_template":"git status --short {{path}}","parameters":[{"name":"path","default":"."}],"timeout_seconds":10,"tags":["git","inspection"]}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/recipes/git.status/preview `
  -H "Content-Type: application/json" `
  -d '{"parameters":{"path":"."},"requested_by":"operator"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/recipes/git.status/execute `
  -H "Content-Type: application/json" `
  -d '{"parameters":{"path":"."},"approval_id":"[approval_id]","requested_by":"operator"}'
```

```powershell
curl -X POST "http://127.0.0.1:8000/cli/recipes/git.status/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"parameters":{"path":"."},"requested_by":"operator"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/cli/recipes/git.status/runs `
  -H "Content-Type: application/json" `
  -d '{"parameters":{"path":"."},"approval_id":"[approval_id]","requested_by":"operator"}'
```

Recipe templates and parameter defaults cannot contain secret-shaped text. Parameter values are intentionally constrained to safe identifier/path-like text, and unknown parameters fail closed before command policy evaluation.

Deployment-managed recipes declared as `managed_command_recipes` in `DGENTIC_MANAGED_SETTINGS_FILE` appear from the same list/detail routes and use the same preview, execute, approval, and run endpoints. They are read-only API records with `source: "managed"`, cannot be shadowed by local or plugin recipe writes, and record usage through CLI audit events without mutating local `command-recipes.json`.

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/write `
  -H "Content-Type: application/json" `
  -d '{"path":"notes/sprint.txt","content":"Sprint note."}'
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/read `
  -H "Content-Type: application/json" `
  -d '{"path":"notes/sprint.txt"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/write-binary `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts/blob.bin","content_base64":"AAEC/w=="}'
```

```powershell
curl -X POST http://127.0.0.1:8000/filesystem/list `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts"}'
```

```powershell
$approval = curl -X POST http://127.0.0.1:8000/filesystem/approvals `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","action":"copy","requested_by":"operator"}' | ConvertFrom-Json

curl -X POST "http://127.0.0.1:8000/filesystem/approvals/$($approval.id)/approve" `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Reviewed copy."}'

curl -X POST http://127.0.0.1:8000/filesystem/copy `
  -H "Content-Type: application/json" `
  -d ('{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","approval_id":"' + $approval.id + '"}')
```

```powershell
curl -X POST http://127.0.0.1:8000/routing/decide `
  -H "Content-Type: application/json" `
  -d '{"privacy_required":true}'
```

Provider health checks can probe local Ollama and LM Studio runtimes:

```powershell
curl http://127.0.0.1:8000/providers/ollama/health
curl http://127.0.0.1:8000/providers/lm-studio/health
```

Run a local provider generation request:

```powershell
curl -X POST http://127.0.0.1:8000/providers/generate `
  -H "Content-Type: application/json" `
  -d '{"provider_id":"ollama","model":"llama3.1","messages":[{"role":"user","content":"Say hello."}]}'
```

Provider calls must target exact allowlisted base URLs. By default, DGentic allows only the configured Ollama and LM Studio endpoints; add trusted extra endpoints with `DGENTIC_PROVIDER_ALLOWED_BASE_URLS` when needed. Redirects are blocked, request payloads are bounded, malformed upstream success payloads become generic provider failures, configured URLs with embedded credentials are not displayed, and logs keep provider usage/cost metadata without persisting raw completion content. Generation uses bounded retry/backoff for retryable `429` and upstream `5xx` failures; repeated retry-exhausted generation failures open an in-process per-provider circuit breaker and return fast `503` responses until cooldown expires. Health probes stay single-attempt.

Set `DGENTIC_NETWORK_DOMAIN_POLICY` when exact base URL allowlists need a domain-level decision layer. The policy JSON accepts `default_mode` and ordered `rules` with exact domains or wildcard subdomains such as `*.example.com`. Modes are `allow`, `deny`, `approval_required`, and `audit`; `allow` and `audit` proceed, `deny` fails closed, and `approval_required` requires a matching single-use `network_approval_id` for provider generation/streaming before transport. Generated-tool subprocesses also consume a sanitized domain/mode copy of this policy for common Python socket egress; `deny` fails the tool run, `allow` and `audit` proceed, and `approval_required` proceeds only when tool execution supplies a single-use approval bound to surface `generated_tool`, action `socket_connect`, and the exact host plus explicit port URL. This generated-tool behavior is a Python runtime guardrail, not OS-level or non-Python network sandboxing.

```powershell
$env:DGENTIC_NETWORK_DOMAIN_POLICY = '{"default_mode":"deny","rules":[{"domain":"provider.example.test","mode":"allow"},{"domain":"*.review.example.test","mode":"approval_required"}]}'
```

Check a URL without making an outbound request:

```powershell
curl -X POST http://127.0.0.1:8000/guardrails/network `
  -H "Content-Type: application/json" `
  -d '{"url":"https://provider.example.test/v1/chat/completions"}'
```

The OpenAI-compatible external adapter is disabled until `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL`, `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS`, and either `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV` or `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF` are configured. The external base URL must use HTTPS because the adapter sends a bearer credential. Credential references can store an external location, such as an environment variable name, a configured `external_process` adapter id plus secret name, a configured `secret_manager` adapter id plus secret name, or local vault ciphertext encrypted with the operator-supplied `DGENTIC_CREDENTIAL_VAULT_KEY`; deployment-managed env, external-process, and secret-manager references can provide the same ids without local persistence. The actual API key value is sent only as an outbound Authorization header after pricing, configuration, circuit-breaker, credential egress, and approval gates allow transport. Direct external generation is approval-required: development/test smoke checks can include `"approved": true`; staging/production requests need a single-use bound `approval_id`.

External process credential adapters are disabled by default. When configured with `DGENTIC_CREDENTIAL_PROCESS_ADAPTERS`, DGentic runs the fixed adapter argv without a shell, appends the credential reference `secret_name`, closes stdin, uses a minimal inherited environment, enforces timeout and output-size limits, and rejects stderr, non-zero exit, empty, multiline, or oversized output. This is adapter plumbing for externally managed secret systems, not encrypted local vaulting.

HashiCorp Vault KV v2 adapters are disabled by default. Configure `DGENTIC_CREDENTIAL_SECRET_MANAGER_ADAPTERS` as JSON and set `DGENTIC_CREDENTIAL_SECRET_MANAGER_ALLOWED_BASE_URLS` to the exact Vault base URL before using a `secret_manager` credential reference. The adapter reads `X-Vault-Token` only from the configured token environment variable, builds `/v1/[mount]/data/[secret_name]`, expects a KV v2 response shaped like `{"data":{"data":{"field":"secret"}}}`, and rejects missing, non-string, multiline, NUL-containing, or oversized secret values. Vault requests do not follow redirects, do not use proxies, and fail closed when the Vault host is denied or approval-required by network policy.

Local vault credential references require a Fernet key in `DGENTIC_CREDENTIAL_VAULT_KEY`; DGentic does not generate, store, rotate, or recover that key. The create request is the only API call that accepts `secret_value`; persisted state stores ciphertext, while API views and credential audit events omit both plaintext and ciphertext. Missing, malformed, or wrong keys fail closed before provider transport and before provider approval claims.

Set `DGENTIC_PROVIDER_PRICING_CATALOG` when operators want advisory cost estimates for exact provider/model pairs. Token rates use USD per 1,000 prompt/completion tokens, and `request_estimate_usd` is used by routing before usage metadata is available. These estimates are for controls and telemetry only; they are not authoritative billing records, and invalid catalogs fail closed before provider transport.

Set `DGENTIC_PROVIDER_ROLE_ROUTING` when operators want exact role-to-provider/model preferences, for example `{"planner":{"provider_id":"lm-studio","model":"local-model"}}`. Role routes still honor normal eligibility gates such as privacy, required capabilities, max cost, enabled provider status, and model availability; a blocked configured route fails clearly instead of silently falling back to another provider.

Queue and approve a provider request before external generation in production-style mode:

```powershell
$approval = curl -X POST "http://127.0.0.1:8000/providers/external-openai-compatible/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hello."}]}'

curl http://127.0.0.1:8000/providers/approvals/[approval_id]/review

curl -X POST http://127.0.0.1:8000/providers/approvals/[approval_id]/approve `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Approved for this request."}'

curl -X POST http://127.0.0.1:8000/providers/generate `
  -H "Content-Type: application/json" `
  -d '{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hello."}],"approval_id":"[approval_id]","requested_by":"operator"}'
```

Provider approval records store safe review metadata, request HMAC digests, requester/agent/task context, decision timestamps, and expiry without persisting raw prompt content or credential values. The credential binding digest covers the configured credential reference identity rather than the raw secret. When auth is enabled, provider approval create/list/review/approve/deny routes require the separate `approvals` capability, while generation still requires `providers`. Approved records are claimed only after external request/config/circuit/credential gates pass and immediately before outbound provider transport, so actual transport failures consume the approval while earlier fail-fast paths preserve it.

Provider generation, provider approval creation, and network approval create/claim requests may include `agent_id`, `agent_role`, and `task_id`. When supplied, that context must either match a running orchestration task exactly or be omitted entirely; partial context, stale known-task context, and unrelated active-task context are rejected before provider credential lookup, approval claim, or outbound transport.

For OpenAI-compatible streaming, call `POST /providers/generate/stream`. The endpoint returns newline-delimited JSON chunk events for LM Studio and the configured external adapter, while `/providers/generate` remains the non-streaming JSON endpoint.

Generate a reusable local tool:

```powershell
curl -X POST http://127.0.0.1:8000/tools/generate `
  -H "Content-Type: application/json" `
  -d '{"name":"pdf-generator","description":"Generate a PDF from structured input.","trigger_source":"main_agent","permission_mode":"approval_required","tags":["pdf","document"]}'
```

Deprecate a tool:

```powershell
curl -X PATCH http://127.0.0.1:8000/tools/pdf-generator/governance `
  -H "Content-Type: application/json" `
  -d '{"status":"deprecated","reason":"Replaced by a more reliable tool."}'
```

Create, approve, and execute an approval-required generated tool:

```powershell
$approval = curl -X POST "http://127.0.0.1:8000/tools/pdf-generator/approvals?requested_by=operator" `
  -H "Content-Type: application/json" `
  -d '{"payload":{"title":"Example"},"timeout_seconds":30}' | ConvertFrom-Json

curl -X POST "http://127.0.0.1:8000/tools/approvals/$($approval.id)/approve" `
  -H "Content-Type: application/json" `
  -d '{"decided_by":"reviewer","reason":"Safe local generated tool run."}'

curl -X POST http://127.0.0.1:8000/tools/pdf-generator/execute `
  -H "Content-Type: application/json" `
  -d ('{"payload":{"title":"Example"},"approval_id":"' + $approval.id + '","timeout_seconds":30,"requested_by":"operator"}')
```

Generated-tool approval and execution requests may include `agent_id`, `agent_role`, and `task_id`. When supplied context is evaluated during active orchestration work, all three fields must match a running task before approval creation or tool execution continues. Context that references a known but non-running task is rejected as stale. Omitted context and unknown legacy context with no active orchestration match preserve existing non-orchestrated behavior:

```powershell
curl -X POST http://127.0.0.1:8000/tools/pdf-generator/execute `
  -H "Content-Type: application/json" `
  -d ('{"payload":{"title":"Example"},"approval_id":"' + $approval.id + '","timeout_seconds":30,"agent_id":"[agent_id]","agent_role":"QA","task_id":"qa-validation"}')
```

Review a local plugin manifest and record a trust decision without executing plugin content:

```powershell
curl http://127.0.0.1:8000/plugins

curl -X PATCH http://127.0.0.1:8000/plugins/example-plugin/trust `
  -H "Content-Type: application/json" `
  -d '{"status":"trusted","reason":"Manifest metadata reviewed."}'
```

Preview trusted non-executing plugin component references:

```powershell
curl -X POST http://127.0.0.1:8000/plugins/example-plugin/components/preview

curl -X POST http://127.0.0.1:8000/plugins/example-plugin/components/install

curl http://127.0.0.1:8000/plugins/example-plugin/components

curl -X POST http://127.0.0.1:8000/plugins/example-plugin/components/disable
```

For a plugin that declares command recipe components such as `"command_recipes":[{"path":"recipes/git-status.json"}]`, preview and install those recipes after the manifest is trusted. When auth is enabled, these routes require a principal with both `tools` and `cli`, or `admin`:

```powershell
curl -X POST http://127.0.0.1:8000/plugins/example-plugin/command-recipes/preview

curl -X POST http://127.0.0.1:8000/plugins/example-plugin/command-recipes/install

curl -X POST http://127.0.0.1:8000/plugins/example-plugin/command-recipes/disable
```

Installed plugin-owned recipes carry plugin provenance in `command-recipes.json` and fail closed if the plugin is blocked, the manifest trust becomes stale, the component file digest changes, or the plugin recipe activation is disabled. Manual `/cli/recipes/{recipe_id}` mutation is rejected for plugin-owned recipes; reinstall from the trusted plugin component to update them.

For a plugin that declares hook-policy components such as `"hook_policies":[{"path":"hooks/deploy.json"}]`, preview and install those rules after the manifest is trusted. Each hook-policy component may contain one rule object or a list of rule objects. When auth is enabled, these routes require a principal with both `tools` and `hooks`, or `admin`:

```powershell
curl -X POST http://127.0.0.1:8000/plugins/example-plugin/hook-policies/preview

curl -X POST http://127.0.0.1:8000/plugins/example-plugin/hook-policies/install

curl -X POST http://127.0.0.1:8000/plugins/example-plugin/hook-policies/disable
```

Installed plugin-owned hook-policy rules carry plugin provenance in `hook-policy-rules.json`, participate in normal command/filesystem/network hook-policy evaluation while active, and are skipped after plugin hook-policy disable. Manual `/guardrails/hooks/rules/{rule_id}` mutation is rejected for plugin-owned hook-policy rules; reinstall from the trusted plugin component to refresh them.

Create a SQLAlchemy-backed metadata index record:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/memory/metadata `
  -H "Content-Type: application/json" `
  -d '{"entity_type":"memory","entity_id":"memory-1","tags":["sprint","metadata"],"category":"planning","description":"Sprint metadata record.","relevance_score":0.8}'
```

Run dependency-light hybrid retrieval over metadata text. The default embedding model is deterministic and does not require model downloads:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/memory/retrieve/hybrid `
  -H "Content-Type: application/json" `
  -d '{"query":"sprint metadata retrieval","tags":["sprint"],"similarity_threshold":0.1}'
```

Retrieval responses include additive attribution fields such as `source_type`, `source_id`, `matched_fields`, and `score_reasons` so callers can see whether a result came from stored vectors, metadata-text fallback, or metadata filters.

Preview or apply memory lifecycle policy decisions. Preview is read-only; apply mutates only promote, archive, and soft-prune decisions. The dashboard Reliability panel exposes the same archive, soft-prune, promote, and compression-candidate threshold fields as the API payload. The Reliability memory detail editor can also patch tags, category, description, relevance, and retention policy for editable metadata rows, and detail/retrieval rows can insert bounded memory context into Task Chat; orchestration shared-memory rows remain service-authored and read-only. Archived and soft-pruned metadata is excluded from retrieval by default unless `include_inactive` is requested:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/memory/lifecycle/preview `
  -H "Content-Type: application/json" `
  -d '{"category":"planning","reference_time":"2027-01-01T00:00:00+00:00"}'

curl -X POST http://127.0.0.1:8000/api/v1/memory/lifecycle/apply `
  -H "Content-Type: application/json" `
  -d '{"category":"planning","reference_time":"2027-01-01T00:00:00+00:00"}'
```

Preview or apply deterministic metadata-description compression for frequently used older records:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/memory/compression/preview `
  -H "Content-Type: application/json" `
  -d '{"category":"planning","compress_after_days":30,"compress_access_count_threshold":10,"max_summary_chars":240}'

curl -X POST http://127.0.0.1:8000/api/v1/memory/compression/apply `
  -H "Content-Type: application/json" `
  -d '{"category":"planning","compress_after_days":30,"compress_access_count_threshold":10,"max_summary_chars":240}'
```

Register a tool in the SQLAlchemy-backed registry:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/tools/registry `
  -H "Content-Type: application/json" `
  -d '{"tool_name":"example-tool","version":"1.0.0","source_path":"localmcp/example-tool","interface_signature":"sha256:example","permission_level":"approval_required","tags":["example"]}'
```

Generated tools created through `/tools/generate` are also registered in the SQLAlchemy-backed registry. Registry duplicate checks run before file creation, execution fails closed when the SQL registry marks a tool deprecated or disagrees with the local manifest permission mode, approval-required execution uses single-use bound approval IDs outside development/test mode, generated-tool approvals/executions enforce orchestration-bound active task context when supplied, approving or denying tool approvals uses the `approvals` capability when auth is enabled, completed executions sync SQL registry usage counters and apply runtime reliability policy automation, configured network policy guards common Python socket egress before generated-tool imports and during execution, approval-required socket targets can consume one matching `network_approval_id` per execution, and tool stdout/stderr/parsed output plus execution audit metadata are redacted for common secret-shaped values.

The interactive OpenAPI docs are available at `http://127.0.0.1:8000/docs` when the backend is running.

Local MVP state is written to `.dgentic/` by default. Set `DGENTIC_DATA_DIR` to move state elsewhere.

## Future Platform Usage

Once implemented, DGentic should support this workflow:

### 1. Start The Backend

Run the DGentic backend orchestrator. The backend will own task planning, execution state, provider routing, agent lifecycle, tool execution, memory access, and audit logs.

### 2. Configure Model Providers

Configure local model providers first:

- Local runtimes: Ollama and LM Studio.
- Extra trusted endpoints: add exact comma-separated base URLs with `DGENTIC_PROVIDER_ALLOWED_BASE_URLS`.
- External providers: an OpenAI-compatible non-streaming and streaming adapter is available when explicitly configured with HTTPS, a model allowlist, a persisted credential reference or env-var fallback, and development/test approval or a staging/production bound provider approval ID; persisted references can point at environment variables, local encrypted vault ciphertext, or configured shell-free external process adapters. Exact provider/model pricing and role-specific provider/model routes can provide advisory usage and routing controls, credential value/header resolution is deferred on fail-fast paths, and dedicated Google AI, DeepSeek, Anthropic, Copilot, or other adapters remain future work.
- Routing rules: Cost, latency, reliability, privacy, role-to-model mapping, and task complexity.

### 3. Set Security Boundaries

Configure strict operating boundaries before running autonomous tasks:

- Workspace `rootDir`
- Bearer-token authentication, route capabilities, persisted operator profiles, persisted operator groups with capability inheritance, persisted generated token lifecycle APIs, and startup token validation for production/staging APIs
- Filesystem text, binary, directory, metadata, delete, move, copy, and rename permissions
- CLI execution mode
- Configurable CLI allow, approval, and block rules with executable, argument-aware, and agent-role scoped matching
- Controlled CLI environment overrides with startup/preload injection blocking, top-level shell startup hardening, and command context audit metadata
- Network policy and domain rules for provider calls, guarded web retrieval fetches, and common generated-tool Python socket egress, with future expansion to OS-level egress isolation and UI approval flows
- Tool creation and execution permissions
- Plugin manifest discovery and trust decisions before any future plugin installation or execution workflow

### 4. Submit A Task

Current backend MVP task submission is through the HTTP API, and the first `/ui/` dashboard can create task plans from a task-chat composer or structured inputs, preview provider routes through the existing routing contract, apply a route and explicitly ask through the existing guarded provider reply path, ask selected providers for non-streaming or streaming replies through existing guarded provider routes using a selected provider message role, create pending provider approvals from the same Task Chat prompt and selected role through the existing guarded provider approval route, append approval outcome cards after decisions and executions, use approval outcomes as bounded context before explicitly asking through the existing provider reply path, restore capped local task-chat history, create orchestration runs from fresh task-chat plans, insert bounded orchestration run, memory, session summary, log event, provider route, provider response, and approval outcome context into follow-up chat turns, preview/copy bounded Task Chat handoff packets as Markdown or JSON, open exact approval reviews from pending task-chat approval context cards, run non-streaming and streaming provider generation with optional bound provider/network approvals and task-chat response context insertion, review configured provider role routing from effective settings, create/list session summaries and reuse filtered log rows through the Activity workbench, and create orchestration runs from structured task graphs. Approval-dashboard backend contracts now have scenario coverage across CLI, filesystem, network, provider, and tool sources, and browser smoke coverage drives seeded CLI approval review/approve, seeded filesystem delete approval review/approve/bound-execute, filesystem preflight-to-approval creation with options and validation, seeded web-retrieval network approval review/approve/bound-fetch, seeded provider approval review/approve/bound-generate with approved network approval consumption, seeded generated-tool approval review/approve/bound-execute with approved socket network approval consumption, provider generation and streaming through the Providers panel with approved provider/network approval consumption, Task Chat provider route preview/application/context insertion and route-to-reply flows, Task Chat provider reply payload and context insertion flows, Task Chat provider approval request/review/outcome handoff and outcome-to-reply flows with selected roles, Task Chat memory context insertion from active memory/detail/retrieval rows, Task Chat handoff packet Markdown/JSON flows, Activity session summary capture/filter/use-context flows, Activity log context handoff flows, provider routing settings review handoff flows, memory metadata detail quick edits through the existing PATCH contract, and fresh task-chat plan to orchestration creation/context reuse without detached execution records through the dashboard. Richer unified chat remains Sprint 16 work, while the dedicated CLI client and VS Code chat extension are planned for Sprint 17. The VS Code extension should integrate with VS Code's native workspace folders, Explorer, editor, and diff review instead of duplicating project file explorer/code editor UI inside the extension.

Current interfaces:

- API
- `/ui/` dashboard for task-chat planning with capped local history, Task Chat provider replies with selectable message roles, Task Chat route-to-reply and outcome-to-reply handoffs, Task Chat provider approval request cards using the selected role, insertable chat context cards including active memory/detail/retrieval/session-summary/log-event/approval-outcome context, Task Chat handoff packet Markdown/JSON preview and copy controls, approval-review and approval-outcome handoff cards, structured task planning, deterministic plan runs, fresh task-chat plan to orchestration creation and context reuse, Activity session summary capture/list/use-context controls, Activity log Use Context/Copy Evidence controls, provider generation and streaming response context insertion, guided orchestration creation/review, structured approval review summaries, guided bound non-CLI execution request handoffs, filesystem preflight-to-approval requests with options/content and bound validation, workspace files with guarded change preview/apply/revert controls, command recipe preview/approval/run/execute plus local recipe editing, Git checkpoints with AI-change metadata, checkpoint-bound raw diff review, session decisions, review rationale notes, diff decision filters, bulk visible diff decisions, saved metadata-only review artifacts, checkpoint-bound approval creation, direct checkpoint-bound Git runs, policy/source summaries, local CLI and hook policy rule creation/edit/toggle controls, grouped settings review, and reliability summaries
- `/ui/` network policy editor for local network-domain rule create/edit/toggle controls backed by guarded API routes and managed-rule read-only rendering

Planned interfaces:

- Deeper unified chat interface
- Dedicated CLI client
- VS Code chat extension with native Explorer/editor/diff integration

DGentic should respond with a task plan, required context, proposed tools, model routing decisions, and any actions requiring approval.

### 5. Review Agent Work

During execution, inspect:

- Orchestrator status
- Sub-agent task progress
- CLI and filesystem action logs
- Provider usage
- Tool runs
- Validation results
- Approval prompts

Log responses redact common secret assignments, secret-like flags, shell-substitution values, and structured sensitive metadata keys such as token, password, secret, credential, and API key fields.

Web retrieval includes a narrow single-URL fetch runtime plus separate preflight routes. `POST /web-retrieval/network/check` evaluates a URL as the `web_retrieval` surface and `fetch` action, `POST /web-retrieval/network/approvals` creates a matching network approval when policy requires one, and `POST /web-retrieval/network/authorize` claims a matching approval for clients that need to authorize a future operation themselves. `POST /web-retrieval/fetch` performs the guarded fetch directly and does not require a prior `/authorize` call. Fetch execution requires the target host to match an explicit network policy rule, uses GET-only transport, sends fixed non-secret headers, disables proxies and redirects, rejects URL credentials and fragments, accepts only text-like content, reads only up to `DGENTIC_WEB_RETRIEVAL_MAX_RESPONSE_BYTES` plus one byte for truncation detection, and returns sanitized URL/policy metadata plus redacted bounded text. `approval_required` hosts must supply a single-use approval id bound to `web_retrieval`/`fetch`; approval ids are rejected when the current host policy is `allow` or `audit`. These routes use the `network` capability when auth is enabled and return sanitized URL previews without query strings or fragments.

### 6. Review Final Output

At task completion, DGentic should provide:

- Final answer or artifact
- Steps performed
- Files changed
- Tools created or reused
- Memory updates
- Known risks or unresolved issues
- Suggested next steps

### 7. Resume Later

DGentic should persist session state so future sessions can resume with context, memory, task history, and relevant project decisions.

## Current Limitations

- DGentic has backend MVP contracts, not production autonomy.
- Production/staging API routes have a bearer-token capability gate, startup fail-closed token validation, persisted operator profiles with direct and group-inherited effective capability assignment, persisted operator groups, persisted generated token create/list/rotate/revoke/expire APIs with hashed storage, authenticated audit actors across the main API-triggered execution/mutation surfaces, persisted credential-reference APIs with env, local encrypted vault plus supplied-key rotation, shell-free external-process sources, first-class HashiCorp Vault KV v2 sources, and deployment-managed credential references, provider-call network/domain guardrails, guarded web retrieval fetch runtime, bound filesystem approval records, generated-tool Python socket network policy guardrails with bound network approval consumption, plugin manifest trust controls, managed policy surface locks, managed-source credential/CLI/hook/command-recipe/plugin records, active-task verification for caller-supplied orchestration agent context across CLI, generated-tool, provider, and network approval surfaces, and secret-shaped metadata redaction for operator/group/token/credential/plugin trust labels, but richer production identity workflows beyond operator groups, managed KMS integration, additional secret-manager adapters, and OS-level egress isolation are not complete yet.
- State is persisted as local JSON collections and a SQLite-compatible SQLAlchemy baseline with a schema migration ledger, additive memory lifecycle metadata migrations, dashboard metadata quick-edit coverage, and SQLite backup/restore smoke helpers, but production PostgreSQL driver packaging, JSON-store migration, vector backend integration, indexing, scheduled/remote backup automation, and concurrency controls still need to be added.
- Ollama and LM Studio have policy-validated local health/model probes and chat generation calls with redirect blocking, bounded request and upstream response payload validation, bounded retry/backoff plus in-process per-provider circuit breakers for retry-exhausted generation failures, normalized usage/cost metadata, safe telemetry, and NDJSON streaming through `/providers/generate/stream`.
- The OpenAI-compatible external adapter is disabled by default and requires HTTPS base URL, model allowlist, credential reference or env-var configuration, and explicit approval for direct generation; it supports non-streaming and NDJSON streaming calls with single-use bound provider approval IDs outside development/test mode plus optional exact provider/model pricing estimates and role-to-model routing preferences, and it skips credential value/header resolution on fail-fast approval, configuration, pricing, and circuit paths, while provider billing reconciliation, managed KMS, additional secret-manager adapters beyond HashiCorp Vault KV v2, and provider-specific external adapters remain future work.
- Guardrails enforce text and binary reads/writes, directory listing, metadata, approval-gated delete/move/copy/rename, and single-use bound filesystem approval records inside `rootDir`; configurable persisted filesystem policy rules, deeper locked-file handling, and OS-level filesystem isolation remain follow-up work.
- CLI guardrails can configure persisted and agent-role scoped policy rules, queue, approve, deny, execute with single-use bound approval IDs outside development/test mode, block explicit executable paths outside `rootDir`, block configured-safe command path/directory flags that resolve outside `rootDir`, keep mutating `git` subcommands and GitHub CLI commands approval-required despite broad configured-safe rules, create read-only git workflow checkpoints for commit/push/PR readiness, run direct checkpoint-bound local git commits, configured-upstream pushes, and constrained GitHub PR creation with safe audit metadata, create checkpoint-bound pending git commit/push/PR approvals with execution-time workflow revalidation, block nested `cmd`/PowerShell startup paths that lack hardened flags, block workspace-resolved bare executables and workspace `PATH` entries including `cmd /c` inner commands, suppress top-level `cmd` AutoRun and PowerShell profiles/prompts at launch, record failed runs for claimed synchronous approvals when process launch fails, start asynchronous runs, poll run status/output chunks, reconcile stale running records, cancel process-local runs, conservatively terminate matching prior-supervisor orphan processes after restart, apply controlled environment overrides with startup/preload injection blocking, audit agent/task context, enforce orchestration-bound active task context when supplied, and persist command runs, but richer approval filtering/non-CLI execution UX, full process adoption/resumable output after restart, and production multi-worker lease supervision remain follow-up work.
- Backend orchestration runs can validate task graphs, enforce canonical declared role write boundaries, schedule dependency-ready tasks into sub-agent briefs with redacted dependency-output context, fence scheduling with durable JSON-backed scheduler leases, persist task claims before agent spawn, repair missing agent rows with fixed ids, publish and reuse opt-in SQL-backed shared memory through explicit tags with owner or run-scoped reuse policy, keep orchestration shared-memory metadata service-authored, owner-scope orchestration agent and shared-memory reads under auth, reconcile terminal spawned-agent lifecycle statuses through explicit cycle and bounded loop endpoints, start, poll, cooperatively cancel, and restart-adopt process-local detached bounded-loop executions with persisted status, expose owner-scoped operations summary counts, bind filesystem write actions to running task declared paths when agent context is supplied, bind CLI actions and generated-tool approvals/executions to exact running task context when active context is supplied, track blockers/follow-ups, retry failed tasks until the configured limit, recover role-boundary and retry-exhaustion blocked tasks after safe correction, resolve manual/security blockers with audit history, regenerate orchestration progress/follow-up documents, reject closed-run mutation, bound scheduling passes, and require DoD evidence before closeout. Deployment-grade distributed job queues remain future operations work.
- Hybrid retrieval works through deterministic local hash embeddings and the SQLite JSON-vector backend abstraction for MVP usage, includes baseline retrieval performance smoke coverage and additive attribution/score explanations, can deterministically compress metadata descriptions on threshold, and excludes archived/soft-pruned metadata by default after lifecycle policy runs; pgvector production storage, optional model packaging, full-content/LLM summarization, scheduled lifecycle/compression jobs, and broader performance validation remain follow-up work.
- Tools can be generated, auto-registered in the SQL registry, duplicate-checked, indexed, migrated to strictly newer same-name versions with explicit overwrite, executed with registry permission/deprecation checks, bound approval IDs for approval-required tools outside development/test mode, orchestration-bound active task checks when agent context is supplied, runtime reliability policy automation, redacted outputs/audit metadata, local-only dependency import isolation, common Python socket network policy guardrails, process-group timeout cleanup hardening, and deprecation controls. Plugin manifests can be discovered/trusted/blocked and trusted current manifests can activate declarative command recipe and hook-policy components with digest-bound provenance, but plugin hook-code/tool/agent/skill loading, full OS/filesystem/network sandbox isolation, parallel multi-version SQL registry rows, and production package/dependency lifecycle management are still needed.
- The first same-origin dashboard is implemented, including a first task-chat composer/transcript with capped local history, Task Chat provider route preview/apply/context controls and explicit route-to-reply handoff, Task Chat provider reply controls with selectable message roles, Task Chat provider approval request controls using the selected role, bounded Task Chat approval outcome cards with explicit outcome-to-reply handoff, Task Chat handoff packet Markdown/JSON preview and copy controls, insertable task-chat context cards with active memory/detail/retrieval/session-summary/log-event/provider-route/approval-outcome context, reusable plan/run/orchestration/memory/session/log context and provider response evidence controls, task-chat approval-review handoff cards, task-chat execution transcript/status cards, fresh task-chat plan to orchestration-run creation, Activity session summary capture/list/use-context controls, Activity log context/evidence controls, actionable task plan/run cards, workspace file change preview/apply/revert controls, structured approval review summaries, recursive guided editable non-CLI bound execution request panels, read-only settings/policy/provider-routing review summaries, local CLI policy, hook policy, network policy, and command recipe creation/edit/toggle controls, provider generation and streaming execution with optional bound provider/network approvals, Git checkpoint AI-change metadata, checkpoint-bound raw Git diff review with session accept/reject decisions, reviewer rationale notes, decision filters, bulk visible decisions, saved metadata-only review artifacts, checkpoint-bound Git approval creation, and direct checkpoint-bound Git run controls, but richer unified chat semantics beyond deterministic execution, richer provider reply automation beyond explicit route/outcome-to-reply handoffs, active memory/session/log context beyond bounded cards and handoff packets, orchestration creation, reusable orchestration context, and broader approval-response automation beyond bounded outcome context, actual Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations, broader editable settings/policy UX beyond read-only provider routing review, CLI policy, hook policy, network policy, and command recipes, VS Code extension, and dedicated CLI client still need to be built.
- Local network-domain policy rule creation/edit/toggle controls are also implemented; remaining editable settings/policy work is now centered on provider, routing, filesystem policy, and richer policy lifecycle flows.
- Commands for the current backend are documented in `docs/how-to/developer-setup.md`.
