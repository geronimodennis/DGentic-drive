# DGentic Agile Task Plan

Date created: 2026-05-07

## Product Goal

Build DGentic as an autonomous AI agent platform that can orchestrate local and external AI models, spawn and coordinate sub-agents, safely interact with files and CLI tools, maintain persistent memory, create reusable tools, and expose the system through chat, dashboard, API, and VS Code interfaces.

## Delivery Strategy

Use iterative Agile delivery with short, testable increments. Each sprint should produce a demonstrable slice of the platform, beginning with the orchestrator and safety boundaries before adding autonomy, memory, tools, and user interfaces.

## Production Completion Backlog

The refined backlog for completing partially implemented feature groups is maintained in [backlog-needs-to-be-done.md](backlog-needs-to-be-done.md).

Current production-completion sprint sequence:
- Sprint 8: Production Security And Persistence Foundation.
- Sprint 9: CLI Runtime Hardening.
- Sprint 10: Filesystem Runtime Completion.
- Sprint 11: Tool Runtime Safety And Registry Integration.
- Sprint 12: Provider Productionization.
- Sprint 13: Memory Production Lifecycle.
- Sprint 14: Autonomous Agent Orchestration.
- Sprint 15: Production Identity, Secrets, And Network Guardrails.
- Sprint 16: Cross-Platform UI And Approval Dashboard.
- Sprint 17: VS Code Extension And Dedicated CLI Client.
- Sprint 18: Deployment, CI/CD, Observability, And Rollback.

These sprints track the remaining work for authentication/authorization, CLI integration, filesystem runtime, provider system, memory/retrieval, tool runtime, agent orchestration, persistence, identity/secrets, network guardrails, web UI/dashboard, VS Code extension, dedicated CLI client, deployment/CI/CD, observability, alerting, and rollback. PM must update the backlog document, this Agile plan, the root README current status, and the project progress log when each sprint starts or closes.

## Roles

- Product owner: Defines priorities, acceptance criteria, and release readiness.
- Tech lead: Owns architecture, sequencing, security posture, and implementation standards.
- Backend engineer: Builds orchestrator, routing, memory, tool runtime, and APIs.
- Frontend engineer: Builds chat interface, dashboard, settings, and approval workflows.
- Extension engineer: Builds VS Code integration.
- QA/security reviewer: Validates behavior, guardrails, tests, and permission boundaries.

## Epic 1: Foundation And Repository Setup

### Story 1.1: Define Project Structure

As a maintainer, I want a clear repository structure so backend, frontend, extension, tools, and documentation can evolve independently.

Acceptance criteria:
- Repository layout is documented.
- Backend, frontend, extension, local tool, and docs directories are defined.
- Development setup instructions exist.

Tasks:
- Choose monorepo layout.
- Add initial backend, frontend, extension, and `localmcp` directory conventions.
- Document setup and contribution workflow.

### Story 1.2: Establish Engineering Baseline

As a developer, I want linting, testing, formatting, and CI conventions so future work remains stable.

Acceptance criteria:
- Formatting and linting commands are documented.
- Test command conventions are defined.
- CI plan exists, even if implementation is deferred.

Tasks:
- Select Python and TypeScript tooling.
- Define test strategy.
- Add quality gate checklist.

## Epic 2: Orchestrator Core

### Story 2.1: Create Task Planning Engine

As a user, I want DGentic to break a goal into executable steps so complex work can be handled predictably.

Acceptance criteria:
- User task can be represented as structured plan data.
- Plan contains objective, constraints, steps, tools, dependencies, and validation criteria.
- Ambiguous requests can produce clarification prompts.

Tasks:
- Define task, plan, step, and result schemas.
- Implement planner service interface.
- Add plan validation rules.

### Story 2.2: Add Execution Loop

As a user, I want DGentic to execute planned steps and adapt when outputs fail validation.

Acceptance criteria:
- Steps can run sequentially.
- Each step records status, output, error, and retry metadata.
- Failed steps can trigger correction or escalation.

Tasks:
- Implement execution state machine.
- Add retry and failure policies.
- Persist run history.

## Epic 3: Model Provider And Routing Layer

### Story 3.1: Integrate Local Model Runtimes

As a user, I want DGentic to use local AI models so sensitive or low-cost work can stay on-device.

Acceptance criteria:
- Ollama and LM Studio provider adapters are designed.
- Provider health check exists.
- Model metadata can be listed and selected.

Tasks:
- Define provider adapter interface.
- Implement local runtime configuration.
- Add local provider tests with mocked responses.

### Story 3.2: Integrate External AI Providers

As a user, I want DGentic to use external AI services through one interface so tasks can route to the best available model.

Acceptance criteria:
- External provider interface supports authentication, request, response, error, and rate-limit metadata.
- Provider credentials are not stored in plain text.
- Routing layer can select providers by role or policy.

Tasks:
- Define external provider contracts.
- Add secure credential storage design.
- Implement first provider adapter after architecture review.

### Story 3.3: Build Hybrid Router

As a user, I want DGentic to route tasks based on cost, latency, complexity, and reliability.

Acceptance criteria:
- Routing policy accepts cost, latency, reliability, privacy, and capability constraints.
- Router decision is logged.
- User can override routing behavior.

Tasks:
- Define router scoring model.
- Implement routing decision logs.
- Add configuration for model roles.

## Epic 4: Multi-Agent System

### Story 4.1: Spawn Sub-Agents

As a user, I want DGentic to create sub-agents for specialized work so complex tasks can run in parallel.

Acceptance criteria:
- Sub-agent brief includes task, context, constraints, required data, and expected output.
- Sub-agent lifecycle is tracked.
- Parent orchestrator can collect outputs.

Tasks:
- Define agent blueprint schema.
- Implement agent lifecycle manager.
- Add parent-child task relationship tracking.

### Story 4.2: Reconcile Agent Outputs

As a user, I want DGentic to cross-check sub-agent outputs so final answers are reliable.

Acceptance criteria:
- Outputs can be compared against acceptance criteria.
- Conflicts are detected and surfaced.
- Final synthesis includes confidence and unresolved issues.

Tasks:
- Implement reconciliation workflow.
- Add validation and cross-check policies.
- Log conflicts and resolutions.

## Epic 5: Guarded System Access

### Story 5.1: Implement File System Boundary

As a user, I want DGentic to access only an assigned root directory so project files are protected.

Acceptance criteria:
- All file operations resolve inside configured `rootDir`.
- Attempts outside `rootDir` are denied and logged.
- Read, write, and delete permissions are separately controlled.

Tasks:
- Define filesystem access policy.
- Implement path resolution guard.
- Add audit logs and tests.

### Story 5.2: Implement Safe CLI Execution

As a user, I want DGentic to run command-line operations safely so automation does not create unacceptable risk.

Acceptance criteria:
- CLI commands are classified as autopilot-safe or approval-required.
- Blocked commands are denied before execution.
- Command output and exit status are logged.

Tasks:
- Define command policy model.
- Implement approval workflow interface.
- Add command audit logging.

### Story 5.3: Complete Production CLI Integration

As an operator, I want CLI execution to support approvals, policy configuration, safe parsing, run history, streaming, redaction, cancellation, and agent-aware permissions so command automation is useful without losing control.

Acceptance criteria:
- Approval-required commands create pending approval records instead of relying only on an `approved: true` request field.
- Pending CLI approvals can be approved or denied through API endpoints.
- CLI execution records are persisted separately from generic logs.
- Command policy supports configurable allowlists, denylists, argument-aware rules, and per-command permission modes.
- Command parsing avoids unsafe shell behavior and has explicit Windows and POSIX behavior.
- Command output supports truncation and redaction of sensitive values.
- Long-running command output can be streamed or polled.
- Running commands can be cancelled.
- CLI permissions can vary by triggering agent, role, or task context.
- Command environment variables are controlled and auditable.
- CLI execution remains constrained to `rootDir` unless explicitly approved by policy.
- Tests cover approval creation, approve/deny, policy configuration, argument rules, redaction, run history, cancellation, and root boundary enforcement.
- README, architecture documentation, usage guide, developer setup, and progress log are updated when the sprint completes.

Tasks:
- Define CLI approval, command run, command policy, and command environment schemas.
- Add pending approval storage and approve/deny endpoints.
- Add persisted command run history endpoints.
- Add configurable command allowlist/denylist and argument-aware policy evaluator.
- Add output truncation and redaction layer.
- Add command cancellation support.
- Add command streaming or polling API.
- Add agent/context-aware permission checks.
- Add tests and documentation updates.

Current implementation status:
- Completed: CLI approvals, single-use bound approval IDs outside development/test mode, approve/deny/execute endpoints, persisted command run history, output redaction/truncation, persisted command policy rules, executable/exact/contains/argument-aware matching, asynchronous run start, run polling by id, process-local cancellation, shell-wrapper policy hardening, agent/context-aware permission decisions, role-scoped policy rules, controlled command environment variables, environment-key audit metadata, and focused tests.
- Remaining: streaming output, restart-resilient process supervision with stale-running reconciliation, broader safe parsing validation across Windows/POSIX shells, and interactive approval/environment review UX.

## Epic 6: Memory And Retrieval

### Story 6.1: Build Metadata Index

As a user, I want skills and memories indexed by metadata so DGentic can retrieve context efficiently.

Acceptance criteria:
- Metadata includes tags, category, relevance, usage count, and timestamps.
- Lookup and retrieval targets are documented.
- Index update operations are logged.

Tasks:
- Define metadata schema.
- Select database backend.
- Implement indexing service.

Current implementation status:
- Completed: SQLAlchemy metadata model, SQLite-compatible local MVP storage, metadata CRUD/filter service, access tracking, Pydantic request/response schemas, metadata API routes, focused service tests, and API CRUD tests.
- Remaining: production database decision, migrations, event log integration for metadata updates, and concurrency/indexing hardening.

### Story 6.2: Build Hybrid Retrieval

As a user, I want DGentic to combine structured index lookup with semantic vector search so relevant memory is found quickly.

Acceptance criteria:
- Retrieval can combine metadata filters and vector similarity.
- Retrieval result includes source and score.
- Long-term memory can be compressed or summarized.

Tasks:
- Select vector backend.
- Implement retrieval query flow.
- Add compression strategy design.

Current implementation status:
- Completed: vector embedding record model, dependency-light deterministic hash embedding service, optional sentence-transformers wrapper path, cosine similarity helper, retrieval service structure, metadata-only retrieval, hybrid metadata-text fallback when stored vectors are absent, stored vector search, hybrid/vector API route definitions, architecture documentation draft, focused service tests, and hybrid retrieval API tests.
- Remaining: production vector backend decision, optional external embedding model packaging/operations strategy, compression/summarization workflow, migrations, and performance validation.

## Epic 7: Tool Runtime And Self-Extensibility

### Story 7.1: Create Local Tool Registry

As a user, I want generated tools stored and registered consistently so agents can reuse them safely.

Acceptance criteria:
- Tools are stored under `rootDir/localmcp/[tool_name]/`.
- Each tool has source code, metadata, interface wrapper, version, and permission classification.
- Duplicate tools can be detected.

Tasks:
- Define local tool manifest.
- Implement registration workflow.
- Add governance metadata.

Current implementation status:
- Completed: SQLAlchemy tool registry model, registration/list/get service, duplicate checks by name/signature/tag overlap, usage/reliability tracking, deprecation workflow, `localmcp/` source path validation, API routes, focused service tests, and API duplicate/usage/deprecation tests.
- Remaining: integration with generated `localmcp/` tool creation flow, migration strategy, and production permission/governance enforcement.

### Story 7.2: Execute Tools Safely

As a user, I want DGentic to execute generated tools in a controlled runtime so tool use remains auditable.

Acceptance criteria:
- Tool execution honors permission level.
- Tool runs are logged with inputs, outputs, duration, and failures.
- Unsafe tools can be deprecated or disabled.

Tasks:
- Define sandbox/runtime strategy.
- Implement tool execution wrapper.
- Add reliability tracking.

### Story 7.3: Fully Implement Dynamic Tool Creation

As a user, I want DGentic to generate, store, register, govern, and reuse local tools when main agents, sub-agents, or skills identify repeatable work.

Acceptance criteria:
- Tool creation can be triggered by the main agent, sub-agents, or skills/modules through a shared backend contract.
- Generated tools are written under `rootDir/localmcp/[tool_name]/`.
- Each generated tool directory includes source code, metadata, an interface wrapper, version information, and documentation.
- Tool generation uses filesystem guardrails and cannot write outside `rootDir/localmcp/`.
- Tools are registered in the persisted tool registry and indexed for memory/skill lookup.
- Tool permission mode is inherited from the triggering context or explicitly classified as `autopilot_safe` or `approval_required`.
- Duplicate tools are detected before generation by name, tags, description, and interface signature.
- Tool versions are tracked and new versions do not overwrite existing versions without policy approval.
- Tool usage count, success count, failure count, last-used timestamp, reliability score, and deprecation status are tracked.
- Unsafe or unreliable tools can be disabled or deprecated and excluded from reuse.
- Generated tools are reusable by the main agent and sub-agents.
- Tests cover generation, duplicate detection, registration, permission classification, governance fields, and root boundary enforcement.
- README, architecture documentation, usage guide, and progress log are updated when the sprint completes.

Tasks:
- Define tool generation request, result, interface, governance, and usage schemas.
- Add `POST /tools/generate` to create tool directories under `rootDir/localmcp/[tool_name]/`.
- Generate `manifest.json`, source file, interface wrapper, and README for each tool.
- Add duplicate detection and versioning policy.
- Persist governance and reliability metadata in the tool registry.
- Add memory/skill indexing hook for generated tools.
- Add deprecate/disable endpoint for unsafe tools.
- Add tests for successful generation and blocked outside-root writes.
- Add tests for duplicate detection, versioning, permission inheritance, and governance updates.

## Epic 8: User Interfaces

### Story 8.1: Build Unified Chat And Project Workspace Interface

As a user, I want a chat interface that shows orchestrator reasoning, project context, sub-agent progress, rich output, approvals, file changes, and action logs.

Acceptance criteria:
- Chat supports Markdown, code, and LaTeX rendering.
- Users can add a project or open an existing project folder as the active `rootDir`.
- Users can browse the active project through a file explorer.
- Users can open and edit project files in a code editor while preserving root-boundary protections.
- Users can review AI-proposed file changes with a Codex-style diff/change-review surface before accepting or rejecting them.
- Sub-agent progress is visible.
- Approval-required actions can be reviewed in context.
- Action logs are available without overwhelming the main conversation.

Tasks:
- Design chat, project workspace, and review-panel layout and state model.
- Implement task submission flow.
- Implement project add/open and active project context display.
- Implement root-bound file explorer and code editor views.
- Implement AI-change diff/review flow for pending file edits.
- Add approval and log panels.

### Story 8.2: Build Configuration Settings

As a user, I want to configure providers, routing, filesystem boundaries, CLI policy, memory, and tooling.

Acceptance criteria:
- Settings cover providers, routing, hardware limits, filesystem jail, CLI guardrails, network policy, memory, and agent blueprints.
- Sensitive values are masked.
- Settings changes are audited.

Tasks:
- Define settings schema.
- Build settings UI.
- Add backend settings API.

### Story 8.3: Build VS Code Chat Extension

As a developer, I want DGentic chat inside VS Code so I can trigger tasks, inspect agents, review changes, and use generated tools from my editor without leaving VS Code's native project workspace.

Acceptance criteria:
- Command palette can trigger DGentic tasks.
- DGentic chat is available in a VS Code view or panel for task submission, progress, approvals, action logs, and follow-up instructions.
- Sidebar shows active agents, memory status, and task decomposition.
- Extension can connect to DGentic backend using configured endpoint and token.
- Extension binds DGentic `rootDir` to an opened VS Code workspace folder, with explicit selection for multi-root workspaces.
- Extension uses VS Code's native Explorer and editor for file navigation and editing instead of duplicating those surfaces.
- Extension shows AI-proposed file edits in VS Code-native diff/editor review flows before changes are accepted or rejected.

Tasks:
- Scaffold VS Code extension.
- Implement connection settings.
- Add DGentic chat view.
- Add workspace-folder to backend `rootDir` binding.
- Add editor and selection context commands.
- Add native diff/change-review flow for AI-proposed edits.
- Add sidebar/status views.

### Story 8.4: Build Dedicated CLI Client

As an operator or developer, I want a dedicated DGentic CLI client so I can perform common backend workflows without manually crafting HTTP requests.

Acceptance criteria:
- CLI can check health, create task plans, review approvals, start/poll/cancel CLI runs, inspect providers, query memory, manage tools, create session summaries, and view logs.
- CLI supports backend URL and token configuration.
- Sensitive token and secret values are masked in output and logs.

Tasks:
- Define CLI command structure.
- Implement shared backend API client behavior.
- Add local install and smoke-test documentation.

Current implementation status:
- Partially implemented: web frontend/dashboard and interactive approval UI are active in Sprint 16, with dashboard shell, first task-chat composer/transcript with capped browser-local history, task-chat provider reply controls, task-chat provider approval request handoff controls, task-chat context stream, reusable plan/run/orchestration/provider-response follow-up context controls, task-chat execution transcript/status cards, fresh task-chat plan to orchestration-run creation, actionable task plan/run cards, task planning, project context/open controls, workspace file browsing/editing with guarded file-change preview/apply/revert controls, guided orchestration creation, orchestration detail/execution controls, expandable per-task sub-agent briefs, parent-child agent graph visibility, task update/recovery/blocker resolution/closeout controls, unified approval source/status filtering plus structured review/decision actions, approved CLI execution, guided editable non-CLI bound execution request panels with recursive nested payload controls, command recipe actions plus local command recipe creation/edit/toggle controls, local plugin trust/block controls and trusted-plugin activation controls, network policy preflight checks and approval requests, filesystem guardrail preflight checks and approval requests with action-specific approval options/content, provider health checks, provider routing preview, provider approval request creation, provider generation and streaming execution with optional bound provider/network approvals, generated-tool governance controls, Git checkpoint visibility with AI-change metadata summary, checkpoint-bound raw Git diff review, session accept/reject decisions for loaded Git diff sections, decision filters, bulk visible decisions, persistent metadata-only AI-change review artifacts, checkpoint-bound commit/push/PR approval creation, direct checkpoint-bound Git run controls, memory/tool reliability summaries, read-only hybrid memory retrieval, memory lifecycle preview/apply with policy threshold controls, memory compression preview/apply, memory/tool detail drilldowns, guarded memory metadata quick-edit controls, policy/plugin visibility with source/status summaries, local CLI, hook policy, and network policy rule creation/edit/toggle controls, grouped effective-settings review, richer filesystem review digest visibility, filesystem bound-execution path/target/option validation, and logs implemented.
- Sprint 16 BL-010bl update: local network-domain policy rule creation, edit, and enable/disable controls are implemented through guarded backend APIs, with managed network rules and managed `network_policy` locks rendered read-only.
- Sprint 16 BL-010bm update: task-chat pending approval context cards can open the exact safe approval review in the unified inbox using existing backend approval contracts.
- Sprint 16 BL-010bn update: memory lifecycle policy threshold controls are implemented through existing Reliability-panel preview/apply calls and backend lifecycle contracts.
- Sprint 16 BL-010bo update: Git diff review bulk decision controls are implemented on top of existing checkpoint-bound raw diff review data without adding backend Git mutation authority.
- Sprint 16 BL-010bp update: memory metadata quick-edit controls are implemented through the existing metadata PATCH contract for editable Reliability-panel detail rows; orchestration shared-memory rows stay read-only.
- Sprint 16 BL-010bq update: plugin activation console controls are implemented through existing guarded plugin preview/list/install/disable contracts for trusted reference components, command recipes, and hook policies; managed plugin activation locks render read-only.
- Sprint 16 BL-010br update: provider and generated-tool approval request builders are implemented in the Providers runtime panel through existing guarded provider/tool approval creation routes, with unified inbox refresh to the matching pending source.
- Sprint 16 BL-010bs update: registered project metadata edit/archive/restore controls are implemented in the Project panel through the existing guarded project metadata PATCH route.
- Sprint 16 BL-010bt update: provider generation console controls are implemented in the Providers runtime panel through the existing guarded `/providers/generate` route, with optional bound provider/network approval IDs and task-chat response context insertion.
- Sprint 16 BL-010bu update: provider streaming generation console controls are implemented in the Providers runtime panel through the existing guarded `/providers/generate/stream` route, with NDJSON chunk accumulation, unsupported-provider stream gating, safe metadata rendering, and task-chat streamed response context insertion.
- Sprint 16 BL-010bv update: Task Chat provider reply controls are implemented through the existing guarded provider generation and streaming routes, with provider/model population, optional bound approval IDs, transcript reply cards, and bounded Use Response context insertion.
- Sprint 16 BL-010bw update: Task Chat provider approval request handoff controls are implemented through the existing guarded provider approval route, with approval-safe payload construction from the chat prompt, transcript approval cards, approval-ID reuse, and exact provider-review navigation.
- Not yet implemented: richer unified chat semantics beyond deterministic task execution, explicit orchestration creation, reusable orchestration context, and approval-review handoff, actual Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations, richer AI-change review semantics beyond saved metadata-only review artifacts and UI-side diff decisions, broader editable settings/policy UX beyond the currently implemented project metadata, CLI policy, hook policy, network policy, command recipes, plugin trust/activation, generated-tool governance, memory lifecycle/compression administration beyond manual thresholded preview/apply and metadata quick-edit controls, VS Code extension, and dedicated CLI client.
- Planned: remaining Story 8.1 and Story 8.2 work continues in Sprint 16; Story 8.3 and Story 8.4 are covered by Sprint 17.

## Epic 9: Observability, Analytics, And Post-Session Behavior

### Story 9.1: Add Action And Performance Logs

As an operator, I want logs for actions, provider usage, tool usage, memory health, and latency so system behavior is explainable.

Acceptance criteria:
- Logs include task, agent, provider, tool, CLI, filesystem, and approval events.
- Performance metrics include latency and token or cost estimates where available.
- Logs can feed dashboard views.

Tasks:
- Define event schema.
- Implement logging service.
- Add dashboard data contracts.

### Story 9.2: Add Session Summaries

As a user, I want DGentic to summarize each session so work can resume cleanly later.

Acceptance criteria:
- Session summary includes actions, decisions, learned knowledge, created tools, and next steps.
- Memory optimization can run after session completion.
- Resume state can reload the previous context.

Tasks:
- Define session state file.
- Implement summarization workflow.
- Add resume workflow.

## Milestone Plan

### Milestone 0: Documentation And Planning

Goal: Establish the project source of truth.

Deliverables:
- Product goal document.
- Agile task plan.
- Project progress log.
- Root README and documentation index.

### Milestone 1: Core Backend Skeleton

Goal: Build the backend foundation for orchestrator, plans, execution state, and logs.

Deliverables:
- FastAPI service skeleton.
- Pydantic schemas for task, plan, step, result, provider, agent, and log events.
- Basic task planning endpoint.
- Local persistence for development.

### Milestone 2: Guardrails And Execution

Goal: Add guarded file and CLI access before enabling broader autonomy.

Deliverables:
- Filesystem jail.
- CLI policy engine.
- Approval-required action flow.
- Audit logging.

### Milestone 3: Provider Routing And Agents

Goal: Support model providers, routing rules, and sub-agent lifecycle.

Deliverables:
- Local provider adapters.
- External provider contract.
- Router policy implementation.
- Agent manager and output reconciliation.

### Milestone 4: Memory And Tool Runtime

Goal: Add reusable memory and controlled local tool creation.

Deliverables:
- Metadata index.
- Vector retrieval path.
- `localmcp` tool registry.
- Tool execution wrapper.

### Milestone 5: Interfaces

Goal: Make DGentic usable through web and editor workflows.

Deliverables:
- Chat interface.
- Settings interface.
- Analytics dashboard.
- VS Code extension MVP.
- Dedicated CLI client.

## Definition Of Ready

A story is ready when:
- The user value is clear.
- Acceptance criteria are testable.
- Dependencies are identified.
- Security and permission impact is understood.
- Required interfaces or schemas are drafted.

## Definition Of Done

A story is done when:
- Acceptance criteria are met.
- Tests or verification notes are recorded.
- Documentation is updated.
- Security and permission behavior is reviewed.
- Progress log is updated.

## Sprint Close Checklist

Every sprint completion must include:
- Update the root `README.md` when behavior, setup, API surface, or project status changes.
- Update the relevant documentation under `docs/`.
- Update `docs/progress/project-progress-log.md` with completed work, verification, decisions, blockers, and next steps.
- Mark remaining unfinished story work clearly as follow-up production work.
- Run the quality gates and record the verification result before commit.

## Initial Sprint 1 Backlog

Sprint goal: Turn the DGentic specification into a maintainable implementation foundation.

Candidate tasks:
- Finalize repository layout.
- Create backend skeleton.
- Define core Pydantic schemas.
- Add task planning endpoint.
- Add project configuration template.
- Add first architecture document.
- Add developer setup guide.
- Add progress log update after implementation.
