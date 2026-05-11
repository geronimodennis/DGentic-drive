# How To Use DGentic

Date created: 2026-05-07

DGentic is currently in backend MVP development. This guide explains how to use the repository now and how the platform is expected to be used as implementation continues.

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

In local development, API authentication is off by default. In `staging` and `production`, protected routes require bearer tokens configured with `DGENTIC_AUTH_TOKENS`, such as `admin-token=admin;task-token=tasks`. When authentication is enabled, startup fails closed if no usable token map is configured.

Example protected request in production mode:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/plan `
  -H "Authorization: Bearer task-token" `
  -H "Content-Type: application/json" `
  -d '{"objective":"Create a guarded task plan for indexing project memory."}'
```

SQLAlchemy-backed metadata and tool registry services use SQLite at `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db` by default. Set `DGENTIC_DATABASE_URL` to point those services at another SQLAlchemy database URL. Ordered schema migrations are tracked in `schema_migrations`, and file-backed SQLite state can be backed up or restored with the local `backup_sqlite_database` and `restore_sqlite_database` helpers.

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

Detached execution records are persisted with `starting`, `running`, `cancelling`, `cancelled`, `completed`, `failed`, or `stale` status. DGentic rejects a second active execution or foreground loop for the same orchestration run with a conflict response, keeps `cancelling` executions active until the owning worker finalizes them, renews a process-local heartbeat while a detached worker is running, adopts expired `starting`/`running` records from prior supervisors for open runs on backend startup, finalizes expired `cancelling` records as cancelled, marks duplicate or non-resumable stale records safely, and redacts failure errors before persistence. This is still a process-local daemon-thread worker: it does not adopt OS process output, provide durable multi-worker scheduler leases, or replace the future production scheduler.

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

Command guardrail and runtime requests may also include `agent_id`, `agent_role`, and `task_id`. When that context references a running orchestration task, all three fields must match the active task before command policy evaluation or CLI execution continues. Omitting orchestration context preserves the existing non-orchestrated behavior, and legacy agent/task context that does not match an active orchestration task remains accepted for audit compatibility:

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

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"cmd /c echo hello","timeout_seconds":5}'
```

Run a command with agent/task context and a controlled environment override. Command run history stores only the applied environment variable names:

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"cmd /c echo context","requested_by":"pm","agent_id":"agent-dev-1","agent_role":"developer","task_id":"story-5.3","environment":{"DGENTIC_TEST_FLAG":"enabled"}}'
```

For orchestration-bound CLI execution, use the `agent_id`, `agent_role`, and `task_id` from the running orchestration task. Partial or mismatched active task context is blocked and the command policy decision includes the serialized orchestration decision for audit/UI consumers.

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

Queue, approve, and execute an approval-required CLI command:

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

The review response is safe for UI consumers: it returns redacted command text, policy context, environment key names without values, command/environment HMAC digest identifiers, warnings for environment-bound, redacted-command, or legacy-digest approvals, and whether direct execution is available. Use the bound approval directly when executing with reviewed environment keys or when calling `/cli/execute` or `/cli/runs`:

```powershell
curl -X POST http://127.0.0.1:8000/cli/execute `
  -H "Content-Type: application/json" `
  -d '{"command":"python --version","timeout_seconds":10,"approval_id":"[approval_id]","requested_by":"operator"}'
```

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
curl -X POST http://127.0.0.1:8000/filesystem/copy `
  -H "Content-Type: application/json" `
  -d '{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","approved":true}'
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

The OpenAI-compatible external adapter is disabled until `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL`, `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV`, and `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS` are configured. The external base URL must use HTTPS because the adapter sends a bearer credential. The credential setting stores only the name of an environment variable; the actual API key value must be exported separately and is sent only as an outbound Authorization header after pricing, configuration, circuit-breaker, and approval gates allow transport. Direct external generation is approval-required: development/test smoke checks can include `"approved": true`; staging/production requests need a single-use bound `approval_id`.

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

Provider approval records store safe review metadata, request HMAC digests, requester/agent/task context, decision timestamps, and expiry without persisting raw prompt content or credential values. When auth is enabled, provider approval create/list/review/approve/deny routes require the separate `approvals` capability, while generation still requires `providers`. Approved records are claimed only after external request/config/circuit/credential gates pass and immediately before outbound provider transport, so actual transport failures consume the approval while earlier fail-fast paths preserve it.

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

Generated-tool approval and execution requests may include `agent_id`, `agent_role`, and `task_id`. When that context references a running orchestration task, all three fields must match the active task before approval creation or tool execution continues. Omitted context and legacy context with no active orchestration match preserve existing non-orchestrated behavior:

```powershell
curl -X POST http://127.0.0.1:8000/tools/pdf-generator/execute `
  -H "Content-Type: application/json" `
  -d ('{"payload":{"title":"Example"},"approval_id":"' + $approval.id + '","timeout_seconds":30,"agent_id":"[agent_id]","agent_role":"QA","task_id":"qa-validation"}')
```

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

Preview or apply memory lifecycle policy decisions. Preview is read-only; apply mutates only promote, archive, and soft-prune decisions. Archived and soft-pruned metadata is excluded from retrieval by default unless `include_inactive` is requested:

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

Generated tools created through `/tools/generate` are also registered in the SQLAlchemy-backed registry. Registry duplicate checks run before file creation, execution fails closed when the SQL registry marks a tool deprecated or disagrees with the local manifest permission mode, approval-required execution uses single-use bound approval IDs outside development/test mode, generated-tool approvals/executions enforce orchestration-bound active task context when supplied, approving or denying tool approvals uses the `approvals` capability when auth is enabled, completed executions sync SQL registry usage counters and apply runtime reliability policy automation, and tool stdout/stderr/parsed output plus execution audit metadata are redacted for common secret-shaped values.

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
- External providers: an OpenAI-compatible non-streaming and streaming adapter is available when explicitly configured with HTTPS, a model allowlist, an env-referenced credential, and development/test approval or a staging/production bound provider approval ID; exact provider/model pricing and role-specific provider/model routes can provide advisory usage and routing controls, credential value/header resolution is deferred on fail-fast paths, and dedicated Google AI, DeepSeek, Anthropic, Copilot, or other adapters remain future work.
- Routing rules: Cost, latency, reliability, privacy, role-to-model mapping, and task complexity.

### 3. Set Security Boundaries

Configure strict operating boundaries before running autonomous tasks:

- Workspace `rootDir`
- Bearer-token authentication, route capabilities, and startup token validation for production/staging APIs
- Filesystem text, binary, directory, metadata, delete, move, copy, and rename permissions
- CLI execution mode
- Configurable CLI allow, approval, and block rules with executable, argument-aware, and agent-role scoped matching
- Controlled CLI environment overrides and command context audit metadata
- Network policy and domain rules
- Tool creation and execution permissions

### 4. Submit A Task

Submit work through a supported interface:

- Unified chat interface
- API
- CLI
- VS Code extension

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
- Production/staging API routes have a bearer-token capability gate and startup fail-closed token validation, but persisted identity management, token rotation, bound approval identities, and full audit actor propagation are not complete yet.
- State is persisted as local JSON collections and a SQLite-compatible SQLAlchemy baseline with a schema migration ledger, additive memory lifecycle metadata migrations, and SQLite backup/restore smoke helpers, but production PostgreSQL driver packaging, JSON-store migration, vector backend integration, indexing, scheduled/remote backup automation, and concurrency controls still need to be added.
- Ollama and LM Studio have policy-validated local health/model probes and chat generation calls with redirect blocking, bounded request and upstream response payload validation, bounded retry/backoff plus in-process per-provider circuit breakers for retry-exhausted generation failures, normalized usage/cost metadata, safe telemetry, and NDJSON streaming through `/providers/generate/stream`.
- The OpenAI-compatible external adapter is disabled by default and requires HTTPS base URL, model allowlist, credential env-var configuration, and explicit approval for direct generation; it supports non-streaming and NDJSON streaming calls with single-use bound provider approval IDs outside development/test mode plus optional exact provider/model pricing estimates and role-to-model routing preferences, and it skips credential value/header resolution on fail-fast approval, configuration, pricing, and circuit paths, while encrypted credential storage, provider billing reconciliation, and provider-specific external adapters remain future work.
- Guardrails enforce text and binary reads/writes, directory listing, metadata, and approval-gated delete/move/copy/rename inside `rootDir`; bound filesystem approval records, configurable persisted filesystem policy rules, deeper locked-file handling, and OS-level filesystem isolation remain follow-up work.
- CLI guardrails can configure persisted and agent-role scoped policy rules, queue, approve, deny, execute with single-use bound approval IDs outside development/test mode, start asynchronous runs, poll run status/output chunks, reconcile stale running records, cancel process-local runs, conservatively terminate matching prior-supervisor orphan processes after restart, apply controlled environment overrides, audit agent/task context, enforce orchestration-bound active task context when supplied, and persist command runs, but there is not yet a user-facing approval UI, full process adoption/resumable output after restart, or production multi-worker lease supervision.
- Backend orchestration runs can validate task graphs, enforce canonical declared role write boundaries, schedule dependency-ready tasks into sub-agent briefs with redacted dependency-output context, publish and reuse opt-in SQL-backed shared memory through explicit tags with owner or run-scoped reuse policy, keep orchestration shared-memory metadata service-authored, owner-scope orchestration agent and shared-memory reads under auth, reconcile terminal spawned-agent lifecycle statuses through explicit cycle and bounded loop endpoints, start, poll, cooperatively cancel, and restart-adopt process-local detached bounded-loop executions with persisted status, expose owner-scoped operations summary counts, bind filesystem write actions to running task declared paths when agent context is supplied, bind CLI actions and generated-tool approvals/executions to exact running task context when active context is supplied, track blockers/follow-ups, retry failed tasks until the configured limit, recover role-boundary and retry-exhaustion blocked tasks after safe correction, resolve manual/security blockers with audit history, regenerate orchestration progress/follow-up documents, reject closed-run mutation, bound scheduling passes, and require DoD evidence before closeout, but production scheduling/lease semantics remain future work.
- Hybrid retrieval works through deterministic local hash embeddings and the SQLite JSON-vector backend abstraction for MVP usage, includes baseline retrieval performance smoke coverage and additive attribution/score explanations, can deterministically compress metadata descriptions on threshold, and excludes archived/soft-pruned metadata by default after lifecycle policy runs; pgvector production storage, optional model packaging, full-content/LLM summarization, scheduled lifecycle/compression jobs, and broader performance validation remain follow-up work.
- Tools can be generated, auto-registered in the SQL registry, duplicate-checked, indexed, migrated to strictly newer same-name versions with explicit overwrite, executed with registry permission/deprecation checks, bound approval IDs for approval-required tools outside development/test mode, orchestration-bound active task checks when agent context is supplied, runtime reliability policy automation, redacted outputs/audit metadata, local-only dependency import isolation, process-group timeout cleanup hardening, and deprecation controls, but full OS/filesystem/network sandbox isolation, parallel multi-version SQL registry rows, and production package/dependency lifecycle management are still needed.
- Frontend, dashboard, and VS Code extension components still need to be built.
- Commands for the current backend are documented in `docs/how-to/developer-setup.md`.
