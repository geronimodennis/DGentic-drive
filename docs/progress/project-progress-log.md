# DGentic Project Progress Log

This log records meaningful project progress, decisions, blockers, and next steps.

For the current sprint, priority order, safe stopping rules, and source-of-truth links, start with [docs/project-status.md](../project-status.md). Keep this file as the historical append-only progress ledger.

## 2026-05-19

### Sprint 16 BL-010bn Memory Lifecycle Policy Threshold Controls

Status: completed for the scoped Reliability-panel lifecycle threshold slice; Sprint 16 remains active for model-backed/streaming chat, durable backend conversation records, cross-surface chat sync, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, network policy, command recipes, plugin trust, generated-tool governance, memory lifecycle/compression administration beyond manual thresholded preview/apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a compact memory administration slice after BL-010bm because the backend lifecycle API already accepts policy thresholds but the dashboard only exposed filters and defaulted the lifecycle policy.
- Completed: Architect/Reviewer kept the slice on existing `/api/v1/memory/lifecycle/preview` and `/api/v1/memory/lifecycle/apply` contracts; no scheduled jobs, new backend mutation authority, metadata editing, or compression apply semantics were added.
- Completed: Developer added Reliability-panel threshold controls for archive age/relevance, soft-prune age/relevance, promote relevance/access count, and compression-candidate age/access count, plus bounded payload mapping to the existing lifecycle request fields.
- Completed: QA added static UI contract coverage for the new controls and payload fields, plus a browser smoke that seeds expired memory, previews a soft-prune recommendation, confirms lifecycle apply, and verifies the metadata state changes to `soft_pruned`.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can tune archive, soft-prune, promote, and compression-candidate thresholds before lifecycle preview or apply from the Reliability panel.
- Implemented in this slice: lifecycle threshold inputs are bounded to the same ranges as the backend request schema before being sent.
- Implemented in this slice: browser coverage now validates the lifecycle preview/apply UI against a seeded metadata record and the persisted lifecycle result.
- Still out of scope after this slice: scheduled lifecycle/compression jobs, metadata editing, model-backed summarization, richer memory administration workflows, and cross-surface memory management.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 20 passed.
- Static validation passed: `node --check src\dgentic\ui\app.js`.
- Quality gates passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010bm Task-Chat Approval Handoff Cards

Status: completed for the scoped task-chat to approval-review handoff slice; Sprint 16 remains active for model-backed/streaming chat, durable backend conversation records, cross-surface chat sync, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, network policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected task-chat approval handoff cards as the next compact user-facing Sprint 16 slice because task-chat already surfaced pending approvals but could only insert text context or jump to the generic approvals panel.
- Completed: Architect/Reviewer kept the slice client-side on existing approval list/review contracts; no backend approval authority, decision route, or execution route was added.
- Completed: Developer added a `Review` action to pending-approval context cards, source/status filter synchronization, exact safe-review loading, and review-status refresh from the review response.
- Completed: QA added static UI contract coverage and browser smoke coverage that seeds a CLI approval, opens it from the task-chat context stream, and verifies the exact CLI review loads with the source filter set.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: pending approval context cards now include a `Review` action alongside `Use Context` and `Open`.
- Implemented in this slice: clicking `Review` switches to the unified inbox, sets the source/status filters for the card, refreshes the approval list, and opens the exact safe review contract.
- Implemented in this slice: approval review rendering now uses the review response status for the selected item so handoff cards stay correct if the approval changed since the context stream loaded.
- Still out of scope after this slice: model-backed chat, streaming assistant responses, durable backend conversation records, cross-surface chat sync, and approval decisions directly inside the chat transcript.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_task_chat_approval_context_opens_exact_review` with 2 passed.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010bl Local Network Policy Rule Editing

Status: completed for the scoped editable network policy slice; Sprint 16 remains active for richer unified chat semantics beyond deterministic execution, explicit orchestration creation, and reusable orchestration context, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, network policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local network policy rule creation/edit/toggle controls as the next compact Sprint 16 editable-policy slice after CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance were already surfaced.
- Completed: Architect/Reviewer kept the slice aligned with existing network-policy semantics: managed rules evaluate before local rules, legacy environment JSON rules stay compatible, and managed `network_policy` locks block mutation while preserving read/evaluation access.
- Completed: Developer added local JSON-backed network-domain policy rule persistence, create/list/update APIs, `network` capability mapping, managed-lock enforcement, and dashboard rule editor/list controls.
- Completed: QA added persistence/sort/evaluation tests, API capability and managed-read-only tests, static dashboard contract coverage, and a browser smoke that creates a deny rule, verifies preflight denial, toggles the rule disabled, and verifies the preflight allows again.
- Completed: Reviewer/Security confirmed the dashboard uses guarded backend policy APIs, keeps managed records read-only, and does not bypass network approval or provider/web-retrieval/generated-tool binding rules.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: local network-domain policy rules can be created through `POST /network/policy/rules`, listed through `GET /network/policy/rules`, and updated through `PATCH /network/policy/rules/{rule_id}`.
- Implemented in this slice: managed network-domain policy rules remain read-only, are listed ahead of local records, and continue to evaluate before legacy environment JSON rules and local persisted rules.
- Implemented in this slice: the dashboard Policy panel can create local rules, render managed/local source state, and edit or toggle local rules while respecting managed `network_policy` locks after settings refresh.
- Still out of scope after this slice: provider/routing/filesystem policy editors, richer policy lifecycle workflows, OS-level egress isolation, and backend Git expansion beyond the existing safe checkpoint/approval/run contracts.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_network_policy.py::test_local_network_policy_rules_persist_sort_and_control_decisions tests\test_api.py::test_network_policy_rule_api_requires_network_capability tests\test_api.py::test_managed_policy_locks_block_mutable_policy_surfaces tests\test_api.py::test_network_policy_rule_api_persists_and_controls_domain_decisions tests\test_api.py::test_managed_network_policy_rules_api_are_read_only_and_precede_local_rules tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_policy_panel_can_create_and_toggle_network_rule` with 8 passed.
- Broader UI/browser validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 17 passed.
- Focused network/API validation passed: `uv run pytest -q tests\test_network_policy.py tests\test_api.py -k "network_policy_rule or network_domain_policy or guardrails_network or managed_policy_locks or network_approval"` with 22 passed and 207 deselected.
- Syntax/static checks passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.
- Full regression passed: `uv run pytest -q` with 1,376 passed and 2 skipped.

### Sprint 16 BL-010bk Task-Chat Orchestration Context Reuse

Status: completed for the scoped orchestration context reuse slice; Sprint 16 remains active for richer unified chat semantics beyond deterministic execution, explicit orchestration creation, and reusable orchestration context, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a narrow follow-up after BL-010bj so task-chat, deterministic runs, and orchestration review can share bounded context without giving chat new execution authority.
- Completed: Architect/Reviewer kept the slice on existing read contracts: task-chat context now reads `/tasks/orchestrations`, but orchestration cycle, loop, start, and cancel remain explicit orchestration-detail controls.
- Completed: Developer added orchestration counts and recent orchestration context cards to the task-chat context stream, plus a `Use Context` action on created-run transcript cards.
- Completed: QA expanded static UI coverage for orchestration context helpers, endpoint wiring, summary counters, and the transcript action.
- Completed: QA expanded browser coverage so fresh task-chat orchestration creation verifies the context-stream orchestration count, inserts bounded orchestration context into the composer, and still confirms no detached execution records were started.
- Completed: Reviewer/Security confirmed the slice uses text-safe DOM construction and does not add execution-triggering calls from task-chat context reuse.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: recent orchestration runs are summarized in the task-chat context stream with bounded reusable context lines.
- Implemented in this slice: created orchestration transcript cards can insert run id, objective, status, task summary, evidence keys, and updated timestamp into the task-chat context composer.
- Still out of scope after this slice: model-backed/streaming chat, durable backend conversation records, cross-surface chat sync, and starting orchestration execution from chat.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_task_chat_can_create_orchestration_from_fresh_plan` with 2 passed.
- Touched-test formatting and lint passed: `uv run ruff format --check tests\test_ui.py tests\test_ui_browser.py` and `uv run ruff check tests\test_ui.py tests\test_ui_browser.py`.
- Broader UI/browser validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 16 passed.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Full regression passed: `uv run pytest -q` with 1,371 passed and 2 skipped.

## 2026-05-18

### Sprint 16 BL-010bj Task-Chat Orchestration Creation Browser Coverage And Closeout

Status: completed for the scoped fresh task-chat plan to orchestration creation slice; Sprint 16 remains active for richer unified chat semantics beyond deterministic execution and explicit orchestration creation, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM continued Sprint 16 under the autonomous workflow and confirmed the implementation checkpoint already pushed in `5e88d01` should be closed with QA browser coverage and PM documentation.
- Completed: QA added browser coverage that creates a fresh task-chat plan with auto-run disabled, clicks `Create Orchestration`, verifies the orchestration transcript/detail surfaces, confirms one created orchestration run with five tasks and required DoD evidence, and confirms no detached orchestration execution records were started.
- Completed: Reviewer/Security confirmed the chat action creates through `POST /tasks/orchestrations`, performs only read-only refresh/detail loads afterward, does not trigger cycle/loop/background execution endpoints, and continues to render task-chat/orchestration UI through text-safe DOM construction.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage notes, and this progress log so BL-010bj is recorded as validation-clean and remaining Sprint 16 chat work is narrowed to richer unified semantics rather than the basic orchestration-creation handoff.

Feature tracking:
- Implemented in this slice: fresh task-chat plan cards can create backend-managed orchestration runs using the existing orchestration create contract.
- Implemented in this slice: created orchestration runs are shown in the task-chat transcript and selected in the orchestration detail console for operator review.
- Implemented in this slice: task-chat orchestration creation leaves execution explicit; it does not start orchestration cycle, loop, or detached execution records from chat.
- Still out of scope after this slice: model-backed/streaming chat, richer unified chat semantics across deterministic runs and orchestration runs, and starting orchestration execution from chat.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_task_chat_can_create_orchestration_from_fresh_plan` with 2 passed.
- Touched-test formatting and lint passed: `uv run ruff format --check tests\test_ui.py tests\test_ui_browser.py` and `uv run ruff check tests\test_ui.py tests\test_ui_browser.py`.
- Broader UI/browser validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 16 passed.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Full regression passed: `uv run pytest -q` with 1,371 passed and 2 skipped.

## 2026-05-16

### Sprint 16 BL-010bi Task-Chat Execution Transcript Status Cards

Status: completed for the scoped deterministic task-chat execution transcript slice; Sprint 16 remains active for task-chat to orchestration-run handoff and richer unified chat semantics, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a bounded task-chat execution transcript/status slice because BL-010z, BL-010ad, BL-010aq, and BL-010bc already provided the composer, local history, context stream, and reusable plan/run evidence controls.
- Completed: Architect/Reviewer confirmed the slice should stay on existing `/tasks/plan`, `/tasks/execute`, `/tasks/plans`, and `/tasks/runs` contracts and treat deterministic task execution as evidence only, not as orchestration or approval bypass.
- Completed: Developer updated task-chat run handling so a single transcript execution card is created while running and then updated to completed or failed instead of appending detached run messages.
- Completed: Developer added bounded execution/run compaction, step-result summaries, duration/status metadata, and an execution-card `Use Evidence` action that inserts deterministic run evidence through the existing task-chat context helper.
- Completed: QA expanded static UI coverage for the execution transcript helpers, DOM hooks, and CSS hooks.
- Completed: QA added browser coverage for task-chat plan creation with auto-run, execution transcript rendering, dashboard metric/context refresh, backend run persistence, and evidence insertion back into the composer.
- Completed: Reviewer/Security confirmed the slice adds no new mutation authority, uses text-safe DOM construction, keeps restored browser-history plan cards display-only, and continues to rely on backend capability gates for protected routes.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: task-chat auto-run now produces a live execution transcript/status card that transitions to completed or failed for the deterministic `/tasks/execute` run.
- Implemented in this slice: execution cards show plan/run ids, run timing, result counts, and bounded per-step result summaries without exposing raw execution output beyond the existing safe task-run contract.
- Implemented in this slice: operators can insert deterministic run evidence from the execution card back into the task-chat context composer for follow-up turns.
- Still out of scope after this slice: model-backed chat, streaming assistant responses, task-chat to orchestration-run draft creation, starting orchestration cycles from chat, and any approval/filesystem/provider/tool bypass.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_task_chat_can_plan_run_and_insert_execution_evidence` with 2 passed.
- Broader UI/browser validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 15 passed.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010bh Guarded Workspace File Change Apply/Revert Controls

Status: completed for the scoped guarded workspace file mutation slice; Sprint 16 remains active for deeper full-chat execution semantics beyond the context stream and reusable plan/run evidence controls, deeper Git hunk/patch apply or revert workflows beyond guarded workspace editor mutations and metadata-only review artifacts, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected guarded workspace file change apply/revert as the next bounded Sprint 16 slice because the dashboard already had active-root file browsing/editing and existing guarded filesystem read/write contracts.
- Completed: Architect/Reviewer confirmed raw Git diff reviews remain evidence-only because they can be redacted, truncated, protected-path omitted, and exclude untracked file content; full Git hunk/patch apply or revert stays deferred rather than forced through unsafe client patch semantics.
- Completed: Developer added workspace editor baseline tracking, pending-change preview summaries, guarded Apply Change, and Revert Last controls that call the existing `/filesystem/write` route instead of adding backend mutation routes.
- Completed: Developer kept the existing Save button aligned with the guarded apply path so dashboard-written content records a reversible last-applied baseline.
- Completed: QA expanded static UI coverage for the new DOM hooks, helper functions, guarded write payloads, status text, and CSS hooks.
- Completed: QA added browser coverage for opening a file, previewing a pending editor delta, applying the change through the dashboard, and reverting the last dashboard-applied content.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can preview pending workspace editor changes with byte, line, changed-line, and revert-availability summaries before mutating the file.
- Implemented in this slice: Apply Change and Save both use the existing guarded filesystem write contract and preserve the previous loaded/applied content for a one-step dashboard revert.
- Implemented in this slice: Revert Last writes the preserved prior content through the same guarded filesystem route and refreshes the workspace state.
- Still out of scope after this slice: authoritative Git hunk/file patch application, Git checkout/restore/revert flows, untracked file content review, and backend rollback/revert workflows.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_workspace_editor_can_apply_and_revert_file_change` with 3 passed.
- Broader UI/browser validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 14 passed.
- Full regression passed: `uv run pytest -q` with 1,369 passed and 2 skipped.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

## 2026-05-15

### Sprint 16 BL-010bg Filesystem Approval Detail Editors

Status: completed for the scoped filesystem approval detail editor slice; Sprint 16 remains active for deeper full-chat execution semantics beyond the context stream and reusable plan/run evidence controls, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected filesystem approval detail editors as the next bounded Sprint 16 slice because BL-010bf opened the filesystem preflight-to-approval path and the backend already exposes bound approval review and execution contracts.
- Completed: Architect/Reviewer confirmed the slice could stay on existing `/guardrails/filesystem`, `/filesystem/approvals`, filesystem review, and bound filesystem execution contracts without adding backend execution routes.
- Completed: Developer split filesystem preflight access payloads from approval payloads so guardrail checks stay lean while approval creation can carry action-specific options/content.
- Completed: Developer added filesystem approval request fields for recursive, overwrite, create-parent-directories, text content, and base64 content with action-specific visibility and stale-preflight invalidation.
- Completed: Developer expanded filesystem review summaries with hook/orchestration detail plus path, target, payload, state, options, policy, and approval digests.
- Completed: Developer added client-side validation so approved filesystem bound execution blocks mismatched path, target/new-name, recursive, overwrite, and create-parent-directory values before posting.
- Completed: QA expanded static UI coverage for the new DOM hooks, helpers, review fields, CSS hook, and validation messages.
- Completed: QA added browser coverage for copy approval creation with overwrite, approval review digest visibility, client-side target mismatch blocking, and successful bound copy execution after correction.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: filesystem approval requests from the Policy panel can include the options and content fields needed for bound approval digests.
- Implemented in this slice: filesystem approval review provides richer digest and decision context before operators approve or execute.
- Implemented in this slice: the dashboard refuses obvious filesystem bound-execution payload drift before calling backend execution endpoints.
- Still out of scope after this slice: persisted configurable filesystem policy rules, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_policy_panel_preserves_filesystem_approval_options tests\test_ui_browser.py::test_browser_policy_panel_can_request_filesystem_approval_after_preflight tests\test_ui_browser.py::test_browser_approval_dashboard_can_execute_seeded_filesystem_delete_approval` with 5 passed.
- Additional focused filesystem/browser validation passed earlier in the slice with 5 passed across filesystem preflight approval creation, option preservation, and seeded filesystem delete execution.
- Full regression passed: `uv run pytest -q` with 1,368 passed and 2 skipped.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010bf Filesystem Preflight Approval Requests

Status: completed for the scoped filesystem preflight-to-approval UI slice; Sprint 16 remains active for deeper full-chat execution semantics beyond the context stream and reusable plan/run evidence controls, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, broader memory lifecycle/compression management beyond apply controls, richer filesystem approval detail editors, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected filesystem preflight-to-approval creation as the next bounded approval-dashboard slice because BL-010be exposed filesystem guardrail decisions and the backend already has bound `/filesystem/approvals` creation.
- Completed: Developer added a disabled-by-default Filesystem Request Approval control, fresh preflight tracking, approval-required gating, input-change invalidation, and `/filesystem/approvals` creation using only the existing backend contract.
- Completed: Developer preserved the existing execution boundary: the dashboard creates a pending approval only and does not execute filesystem operations or bypass bound approval review.
- Completed: QA expanded static UI coverage for the new DOM hook, helper functions, endpoint wiring, freshness message, approval success/failure messages, and click binding.
- Completed: QA added browser smoke coverage that preflights an approval-required delete, creates a pending filesystem approval, verifies it through the API, and sees it in the unified approval inbox.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can create a pending filesystem approval directly from a fresh approval-required filesystem guardrail preflight in the Policy panel.
- Implemented in this slice: editing action/path/target/agent/task inputs invalidates the cached preflight and disables approval creation until the operator checks the current request again.
- Still out of scope after this slice: filesystem policy editing, richer filesystem approval detail editors, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_ui_browser.py::test_browser_policy_panel_can_preflight_filesystem_guardrail tests\test_ui_browser.py::test_browser_policy_panel_can_request_filesystem_approval_after_preflight` with 4 passed.
- Full regression passed: `uv run pytest -q` with 1,367 passed and 2 skipped.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010be Filesystem Guardrail Preflight Controls

Status: completed for the scoped filesystem guardrail preflight UI slice; Sprint 16 remains active for deeper full-chat execution semantics beyond the context stream and reusable plan/run evidence controls, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, memory lifecycle/compression apply controls, and filesystem guardrail preflight, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a read-only filesystem guardrail preflight slice because the backend already exposes `/guardrails/filesystem` and the Policy panel already has a network preflight pattern.
- Completed: Developer added a Filesystem Check panel with action, path, optional target path, and optional agent/task context fields.
- Completed: Developer wired the panel only to the existing `/guardrails/filesystem` contract, renders allowed/mode/path/target/orchestration/hook-policy review details plus raw JSON, and does not execute filesystem operations or create approval records.
- Completed: QA expanded Web UI static coverage for the new DOM hooks, payload helper, decision renderer, endpoint wiring, submit binding, success/failure messages, and browser-driven preflight behavior.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can preview filesystem guardrail outcomes from the Policy panel before attempting guarded filesystem operations.
- Implemented in this slice: the preflight is review-only and preserves existing filesystem approval, auth, hook-policy, and orchestration boundaries.
- Still out of scope after this slice: filesystem policy editing, filesystem approval creation from preflight, richer filesystem approval detail editors, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served` with 2 passed.
- Browser smoke validation passed: `uv run pytest -q tests\test_ui_browser.py::test_browser_policy_panel_can_preflight_filesystem_guardrail` with 1 passed.
- Full regression passed: `uv run pytest -q` with 1,366 passed and 2 skipped.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010bd Memory Lifecycle And Compression Apply Controls

Status: completed for the scoped memory lifecycle/compression apply UI slice; Sprint 16 remains active for deeper full-chat execution semantics beyond the context stream and reusable plan/run evidence controls, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the currently implemented CLI policy, hook policy, command recipes, plugin trust, generated-tool governance, and memory lifecycle/compression apply controls, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected the next Reliability panel slice because the backend already exposes guarded lifecycle and compression apply contracts and the dashboard already had matching preview payloads.
- Completed: Developer added explicit Apply Lifecycle and Apply Compression controls that reuse the current preview filters, require a browser confirmation before mutation, call the existing `/api/v1/memory/lifecycle/apply` and `/api/v1/memory/compression/apply` contracts, and refresh Reliability summaries after success.
- Completed: Developer kept the slice on existing backend contracts only; no new memory mutation route, approval bypass, scheduler, or backend policy surface was added.
- Completed: QA expanded Web UI static coverage for the apply DOM hooks, confirmation prompts, endpoint wiring, success/failure messages, applied result rendering, and refresh binding.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can apply deterministic memory lifecycle recommendations from the dashboard after confirmation.
- Implemented in this slice: operators can apply deterministic memory compression from the dashboard after confirmation.
- Still out of scope after this slice: scheduled memory lifecycle/compression jobs, metadata editing, model-backed memory summarization, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_memory_lifecycle_api_previews_applies_and_excludes_inactive tests\test_api.py::test_memory_compression_api_applies_and_retrieves_compressed_metadata` with 4 passed.
- Browser smoke validation passed: `uv run pytest -q tests\test_ui_browser.py` with 6 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010bc Task-Chat Follow-Up Context Controls

Status: completed for the scoped task-chat follow-up context slice; Sprint 16 remains active for deeper full-chat execution semantics beyond the context stream and reusable plan/run evidence controls, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the implemented CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance surfaces, memory lifecycle/compression apply actions beyond preview/detail surfaces, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a small full-chat semantics slice after BL-010bb because the task-chat area already had plan/run cards and safe context insertion helpers.
- Completed: Developer added shared plan/run context-line builders, reused them in the task-chat context stream, added `Use Context` on plan cards, and added `Use Evidence` on run rows.
- Completed: Developer kept the slice client-side and bound to existing task APIs only; the controls insert bounded plan/run summaries into the composer and do not create new backend mutation, approval, or execution paths.
- Completed: QA expanded Web UI static coverage for the new context helper functions, plan/run action hooks, visible labels, insert wiring, and run-row layout CSS.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can carry a created plan into a follow-up task-chat turn with one click.
- Implemented in this slice: operators can carry deterministic run evidence into a follow-up task-chat turn with one click.
- Still out of scope after this slice: model-backed multi-turn chat semantics, streaming assistant responses, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_static_assets_are_served` with 1 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Syntax validation passed: `node --check src\dgentic\ui\app.js`.
- Lint/static checks passed: `uv run ruff format --check .` and `uv run ruff check .`.

### Sprint 16 BL-010bb Reliability Detail Drilldowns

Status: completed for the scoped read-only Reliability detail drilldown slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the implemented CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance surfaces, memory lifecycle/compression apply actions beyond preview/detail surfaces, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM reassessed the Sprint 16 backlog after BL-010ba and selected a read-only Reliability drilldown slice after read-only review flagged lifecycle/compression apply as a direct mutation path that should wait for approval-bound design.
- Completed: Developer added memory and tool detail output regions to the Reliability panel and attached Details actions to listed memory metadata and SQL tool-registry rows.
- Completed: Developer wired memory details only to `GET /api/v1/memory/metadata/{id}` and tool details only to `GET /api/v1/tools/registry/{id}`, rendering lifecycle, freshness, retention, tags, description, usage, reliability, source, and safe raw JSON without calling apply, patch, delete, usage, deprecate, or execution routes.
- Completed: QA expanded Web UI static coverage for the new detail DOM hooks, detail render helpers, route wiring, detail action buttons, success/failure messages, and the absence of memory lifecycle/compression apply route calls in the dashboard script.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/setup/usage notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can drill into memory metadata records from the Reliability panel without leaving the dashboard.
- Implemented in this slice: operators can drill into SQL tool registry records from the Reliability panel without mutating tool usage, deprecation, governance, or execution state.
- Still out of scope after this slice: lifecycle apply, compression apply, metadata editing, tool registry mutation workflows, full unified chat, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served` with 2 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010ba Memory Compression Preview UI

Status: completed for the scoped read-only memory compression preview UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the implemented CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance surfaces, memory lifecycle/compression apply actions beyond preview, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected memory compression preview as the next safe Sprint 16 reliability slice because the backend already exposes deterministic compression preview and apply contracts, and only preview is needed for a safe dashboard surface.
- Completed: Developer added a Compression Preview panel with entity type, tag, category, retention policy, limit, max summary characters, age, access-count threshold, and include-inactive controls.
- Completed: Developer wired the panel only to `/api/v1/memory/compression/preview`, renders total candidates, applied=false status, original/compressed lengths, estimated savings, reasons, compressed descriptions, embedding reindex status, and safe raw JSON, and did not expose compression apply.
- Completed: QA expanded Web UI static coverage for compression preview DOM hooks, payload helper, preview route wiring, candidate renderer, candidate fields, submit binding, and success/failure messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can preview deterministic compression candidates from the dashboard before any memory mutation.
- Implemented in this slice: compression preview remains read-only and does not compact, reindex, archive, delete, or edit memory records.
- Still out of scope after this slice: compression apply, lifecycle apply, metadata editing, full unified chat, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_memory_compression_api_applies_and_retrieves_compressed_metadata` with 3 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010az Memory Lifecycle Preview UI

Status: completed for the scoped read-only memory lifecycle preview UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the implemented CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance surfaces, memory lifecycle apply/compression actions beyond preview, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected memory lifecycle preview as the next safe Sprint 16 reliability slice because the backend already exposes a preview-only lifecycle contract.
- Completed: Developer added a Lifecycle Preview panel with entity type, tag, category, retention policy, lifecycle state, limit, and include-inactive controls.
- Completed: Developer wired the panel only to `/api/v1/memory/lifecycle/preview`, renders total decisions, applied=false status, recommended actions, current state, freshness, reasons, and safe raw JSON, and did not expose lifecycle apply.
- Completed: QA expanded Web UI static coverage for lifecycle preview DOM hooks, payload helper, preview route wiring, decision renderer, dynamic applied guard, action fields, submit binding, and success/failure messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can preview deterministic lifecycle recommendations from the dashboard before any memory mutation.
- Implemented in this slice: lifecycle preview remains read-only and does not archive, soft-prune, promote, compress, delete, or edit memory records.
- Still out of scope after this slice: lifecycle apply, compression preview/apply UI, metadata editing, full unified chat, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_memory_lifecycle_api_previews_applies_and_excludes_inactive` with 3 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010ay Memory Retrieval Explorer UI

Status: completed for the scoped read-only memory retrieval UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the implemented CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance surfaces, memory lifecycle actions beyond retrieval, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a read-only memory retrieval explorer as the next safe Sprint 16 reliability slice because the backend already exposes the hybrid retrieval contract and the dashboard already has a Reliability panel.
- Completed: Developer added a Memory Retrieval panel with query, entity type, tag, category, lifecycle state, limit, threshold, and include-inactive controls.
- Completed: Developer wired the form to `/api/v1/memory/retrieve/hybrid` and renders result counts, query timing, combined/similarity/metadata scores, descriptions, matched fields, score reasons, and safe raw JSON.
- Completed: QA expanded Web UI static coverage for the memory retrieval DOM hooks, payload helper, hybrid retrieval route wiring, result renderer, score attribution fields, submit binding, and success/failure messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can query indexed memory from the dashboard without leaving the Reliability panel.
- Implemented in this slice: memory retrieval remains read-only and does not apply lifecycle changes, compress memory, mutate metadata, or alter stored records.
- Still out of scope after this slice: memory lifecycle apply/compression actions, metadata editing, full unified chat, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_hybrid_retrieval_api_uses_default_hash_embedding` with 3 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010ax Generated-Tool Governance UI

Status: completed for the scoped generated-tool governance UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond the implemented CLI policy, hook policy, command recipes, plugin trust, and generated-tool governance surfaces, memory retrieval exploration, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected generated-tool governance as the next safe Sprint 16 editable tools slice because the backend already exposes guarded `/tools` listing and `/tools/{name}/governance` update contracts.
- Completed: Developer added a Tool Governance panel to the Provider/Runtime dashboard area with a governance reason field and Active, Deprecate, and Disable actions for generated tools.
- Completed: Developer wired the actions to the existing PATCH governance contract, required a reason for non-active status changes, refreshed the safe tool list after updates, and kept tool execution out of scope.
- Completed: QA expanded Web UI static coverage for the governance DOM hooks, payload helper, update wiring, status action buttons, reason-required guard, and success/failure messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can change generated-tool lifecycle status from the dashboard without leaving the runtime panel.
- Implemented in this slice: generated-tool governance uses the existing backend contract and does not execute tools, generate new tools, mutate tool code, or bypass approval controls.
- Still out of scope after this slice: generated-tool creation UX, tool execution workflow redesign, tool permission-mode editing, memory retrieval exploration, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_dynamic_tool_generation_blocks_invalid_permission_and_deprecates_tool` with 3 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010aw Provider Routing Preview UI

Status: completed for the scoped provider routing preview UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI policy, hook policy, command recipes, and plugin trust, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected provider routing preview as the next safe Sprint 16 runtime-visibility slice after provider health checks because the backend already exposes a read-only routing decision contract.
- Completed: Developer added a Provider panel routing preview form for role, privacy, maximum latency, maximum cost, and required capabilities through `/routing/decide`.
- Completed: Developer renders selected provider, model, score, echoed policy constraints, candidate scores, and safe raw routing JSON without starting provider generation or creating approvals.
- Completed: QA expanded Web UI static coverage for the routing preview DOM hooks, payload helper, route wiring, decision rendering, candidate scores, and success/failure messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can preview DGentic provider/model selection from the dashboard before running a provider request.
- Implemented in this slice: routing preview stays read-only and does not change provider configuration, credentials, routing policy, or execution state.
- Still out of scope after this slice: provider configuration editing, routing policy editing, direct provider generation from the provider panel, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_provider_routing_prefers_local_when_privacy_is_required` with 3 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010av Provider Health Check UI

Status: completed for the scoped provider health visibility UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI policy, hook policy, command recipes, and plugin trust, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected provider health checks as the next safe Sprint 16 runtime-visibility slice because the backend already exposes provider listing and per-provider health contracts.
- Completed: Developer added per-provider Health actions to the Provider panel and a safe output region for availability, checked timestamp, model names, and raw health JSON.
- Completed: Developer kept the slice read-only and did not change provider execution, routing, credentials, or network policy behavior.
- Completed: QA expanded Web UI static coverage for the provider health output area, route wiring, health action button, render helper, and success/failure messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can check provider runtime health directly from the dashboard instead of calling `/providers/{provider_id}/health` manually.
- Implemented in this slice: health details use existing backend redaction/no-secret behavior and do not resolve credentials beyond the existing provider health contract.
- Still out of scope after this slice: provider configuration editing, routing policy editing, actual provider generation from the provider panel, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_provider_listing_and_health_do_not_leak_invalid_configured_base_url` with 3 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010au Network Approval Request UI

Status: completed for the scoped network approval request UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI policy, hook policy, command recipes, and plugin trust, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected approval request creation as the bounded follow-on to BL-010at because the dashboard can now produce a safe, fresh `approval_required` network policy decision.
- Completed: Developer added a Request Approval action that remains disabled until the latest matching network preflight returns `approval_required`.
- Completed: Developer wired generic network checks to the existing `/network/approvals` provider-request contract and web-retrieval checks to `/web-retrieval/network/approvals`, then refreshes the approval inbox after creation.
- Completed: QA expanded Web UI static coverage for approval button state, stale-check guarding, endpoint selection, request payloads, and success messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can create a pending network approval directly from an approval-required Policy dashboard preflight result.
- Implemented in this slice: approval creation still uses the existing backend approval contracts, existing auth gates, redaction, policy drift checks, and the unified approval inbox for review/decision.
- Still out of scope after this slice: editing network policy rules from the dashboard, executing network fetches from the preflight panel, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_network_approval_api_lifecycle_redacts_safe_metadata tests\test_api.py::test_web_retrieval_network_api_pins_surface_claims_approval_and_redacts` with 4 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010at Network Policy Preflight UI

Status: completed for the scoped read-only network policy preflight UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI policy, hook policy, command recipes, and plugin trust, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected network policy preflight as the next safe Sprint 16 policy UX slice because the backend already exposes guarded generic and web-retrieval check contracts.
- Completed: Developer added a dashboard Network Check panel that can check generic network policy through `/guardrails/network` or web-retrieval fetch policy through `/web-retrieval/network/check`.
- Completed: Developer kept the slice read-only and renders allow, deny, approval-required, audit, matched-domain, matched-rule, managed/local source, and hook-policy decision details from existing safe response fields.
- Completed: QA expanded Web UI static coverage for the network policy panel DOM hooks, endpoint selection, decision rendering, event wiring, and status messages.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: operators can now preflight network policy decisions from the Policy dashboard without crafting HTTP requests.
- Implemented in this slice: generic and web-retrieval policy checks stay on the existing backend authority boundaries and do not create approvals, mutate settings, or execute network fetches.
- Still out of scope after this slice: editable network policy management, network approval creation from the preflight panel, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_guardrails_network_returns_policy_decision tests\test_api.py::test_web_retrieval_network_api_pins_surface_claims_approval_and_redacts` with 4 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010as Local Plugin Trust Controls

Status: completed for the scoped local plugin trust control UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI policy, hook policy, command recipes, and plugin trust, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local plugin trust controls as the next low-risk Sprint 16 policy UI slice because the backend already exposes guarded plugin discovery and trust mutation contracts.
- Completed: Developer added dashboard Policy controls to trust or block local plugin manifests through the existing `/plugins/{plugin_id}/trust` route, with an operator-supplied reason field and result output.
- Completed: Developer kept deployment-managed plugin trust read-only in the UI, including managed trust-source records and managed `plugin_trust` locks from effective settings.
- Completed: QA expanded Web UI static coverage for the plugin trust editor DOM hooks, route wiring, managed-lock checks, trust/block controls, result messages, and CSS selector.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: local plugin manifests can now be explicitly trusted or blocked from the Policy dashboard without adding new backend mutation authority.
- Implemented in this slice: managed plugin trust decisions remain visible but read-only, and managed `plugin_trust` locks disable trust/block actions even when settings load after policy data.
- Still out of scope after this slice: plugin hook-code/tool/agent/skill loading beyond inert/declarative records, broader policy/settings editors beyond CLI policy, hook policy, command recipes, and plugin trust; actual AI-change file apply/revert mutation; full unified chat; and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_api.py::test_plugin_trust_persists_redacted_decision_and_becomes_stale tests\test_api.py::test_managed_plugin_trust_records_are_read_only_and_digest_scoped` with 4 passed.
- Full regression passed: `uv run pytest -q` with 1,365 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010ar Local Command Recipe Editor UI

Status: completed for the scoped local command recipe editor UI slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI policy, hook policy, and command recipes, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local command recipe editing as the next low-risk Sprint 16 policy UI slice because the backend guarded command-recipe CRUD routes already exist.
- Completed: Developer added a dashboard command recipe editor for local recipe create/update and enable/disable flows using the existing `/cli/recipes` routes.
- Completed: Developer added guided parameter-row editing for recipe parameters while preserving the existing recipe preview/approval/run/execute action panel.
- Completed: Developer kept managed and plugin-owned command recipes read-only in the UI, and re-renders command-recipe lock state after settings refresh so deployment-managed `command_recipes` locks disable mutation controls consistently.
- Completed: QA expanded Web UI static coverage for the command recipe editor DOM hooks, route wiring, managed-lock checks, edit/toggle controls, parameter builder CSS, and event handlers.
- Completed: QA added backend route coverage for local command-recipe PATCH enable/disable behavior and disabled-preview rejection.
- Completed: PM updated README, project status, backlog, Agile plan, architecture/usage status notes, and this progress log.

Feature tracking:
- Implemented in this slice: local command recipes can now be created, edited, and enabled/disabled from the Policy dashboard through the existing guarded API.
- Implemented in this slice: managed-source and plugin-owned command recipes stay visible but read-only, and managed `command_recipes` locks prevent submit/toggle actions even when settings load after policy data.
- Still out of scope after this slice: broader policy/settings editors beyond CLI policy, hook policy, and command recipes; actual AI-change file apply/revert mutation; full unified chat; and persistent or multi-worker project activation semantics.

Validation:
- Focused validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served tests\test_command_recipes.py::test_recipe_api_patch_toggles_local_recipe_execution` with 3 passed.
- JavaScript syntax check passed: `node --check src\dgentic\ui\app.js`.

### Sprint 16 BL-010aq Unified Task Chat Context Stream

Status: completed for the scoped unified task-chat context stream slice; Sprint 16 remains active for deeper full-chat execution semantics, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI and hook policy, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a bounded chat-context slice after confirming actual AI-change apply/revert needs a safer backend mutation contract before UI exposure.
- Completed: Developer added a task-chat context stream that reads existing project, task plan/run, pending approval, and log APIs and renders compact summary/context cards above the transcript.
- Completed: Developer added Use Context controls that insert bounded plan/run/approval/log summaries into the existing chat context composer without storing bearer tokens or replacing the approval dashboard as execution authority.
- Completed: Developer kept expected authorization gaps for optional context sources as quiet limited-source counts, and refreshed context after project activation so the displayed root does not stay stale.
- Completed: QA expanded Web UI static coverage for the new DOM hooks, route wiring, insert helpers, authorization-gap handling, refresh wiring, and CSS selectors.
- Completed: Reviewer identified stale project activation context and noisy optional-capability failures; Developer fixed both and QA covered the fixes.
- Completed: PM updated README, usage, developer setup, project status, backlog, Agile plan, architecture notes, and this progress log.

Feature tracking:
- Implemented in this slice: task chat now shows active root/project context, task/run counts, pending approval counts, latest activity, and insertable recent plan/run/approval/log context cards.
- Implemented in this slice: context cards use existing backend reads only and do not add new mutation authority or duplicate the approval execution surface.
- Still out of scope after this slice: backend conversational memory/session semantics, autonomous follow-up execution from chat, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused UI validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served` with 2 passed.
- Full regression passed: `uv run pytest -q` with 1,364 passed and 2 skipped.
- Lint/static checks passed before full regression: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010ap Local Hook Policy Editor UI

Status: completed for the scoped local hook policy editor UI slice; Sprint 16 remains active for full unified chat beyond local task history, actual AI-change file apply/revert mutation workflows, broader editable settings and policy workflows beyond CLI and hook policy, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local hook policy editing as the next low-risk Sprint 16 policy UI slice because the backend guarded hook-policy routes already exist.
- Completed: Developer added the dashboard Hook Policy editor for local rule create/update and enable/disable flows using the existing `/guardrails/hooks/rules` routes.
- Completed: Developer kept managed and plugin-owned hook rules read-only in the UI and re-renders hook lock state after settings refresh so deployment-managed `hook_policy` locks disable mutation controls consistently.
- Completed: Developer added client-side pattern validation for non-`any` hook matches so the default form cannot submit a backend-invalid blank match pattern.
- Completed: QA expanded Web UI static coverage for the hook editor form, route wiring, managed-lock checks, pattern validation, and event handlers.
- Completed: Reviewer identified stale managed-lock rendering and blank-pattern validation risks; Developer fixed both and QA covered the fixes.
- Completed: PM updated README, usage, developer setup, project status, backlog, Agile plan, architecture notes, and this progress log.

Feature tracking:
- Implemented in this slice: local hook policy rules can now be created, edited, and enabled/disabled from the Policy dashboard through the existing guarded API.
- Implemented in this slice: managed-source and plugin-owned hook policy records stay visible but read-only, and managed `hook_policy` locks prevent submit/toggle actions even when settings load after policy data.
- Still out of scope after this slice: broader policy/settings editors beyond CLI and hook policy, actual AI-change file apply/revert mutation, full unified chat, and persistent or multi-worker project activation semantics.

Validation:
- Focused UI validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_entrypoint_is_served tests\test_ui.py::test_web_ui_static_assets_are_served` with 2 passed.
- Full regression passed: `uv run pytest -q` with 1,364 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010ao Recursive Guided Bound Payload Editing

Status: completed for the scoped recursive guided non-CLI bound payload editor slice; Sprint 16 remains active for broader editable settings and policy workflows, full unified chat beyond local task history, actual AI-change file apply/revert mutation workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected recursive guided bound payload editing as a bounded UI-deepening slice already supported by the existing approval dashboard execution contracts.
- Completed: Developer updated the dashboard guided bound request editor so nested objects and arrays render as expandable guided groups and scalar nested controls sync back into the canonical JSON payload.
- Completed: QA updated static UI coverage for the nested guided group functions, path labels, nested path sync helper, and CSS selectors.
- Completed: PM updated README, usage, developer setup, project status, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: non-CLI bound execution payloads now support recursive guided editing for nested objects and arrays, including provider `messages`, `options`, tool `payload`, and optional network approval fields.
- Implemented in this slice: only the top-level approval binding field remains locked by guided editing, while nested scalar controls write through stable path metadata into the JSON editor.
- Still out of scope after this slice: richer domain-specific nested editors, broader hook-policy/settings editors, full unified chat, actual AI-change file apply/revert mutation, and persistent or multi-worker project activation semantics.

Validation:
- Focused UI validation passed: `uv run pytest -q tests\test_ui.py::test_web_ui_static_assets_are_served` with 1 passed.
- Dashboard validation passed: `uv run pytest -q tests\test_ui.py tests\test_ui_browser.py` with 10 passed.
- Full regression passed: `uv run pytest -q` with 1,364 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010an Persistent AI-Change Review Artifacts

Status: completed for the scoped persistent AI-change review artifact slice; Sprint 16 remains active for actual AI-change file apply/revert mutation workflows, deeper nested type-specific request editors, full unified chat beyond local task history, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM/Architect selected a metadata-only persistence slice instead of full patch apply/revert because raw diff reviews can be redacted, truncated, protected-path omitted, and untracked-content excluded, making them review evidence rather than safe mutation source material.
- Completed: Developer added guarded Git change review artifact models and `/cli/git/change-review-artifacts` create/list/get routes backed by local JSON state.
- Completed: Developer updated the dashboard raw diff review panel with Save Artifact, saved-artifact listing, matching-checkpoint Apply controls, and stale-artifact rendering that does not unblock Git closeout.
- Completed: QA added focused tests for metadata-only persistence, stale checkpoint rejection, mismatched section digest rejection, artifact list/get APIs, and UI static contract hooks.
- Completed: PM updated README, usage, architecture, project status, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: checkpoint-bound AI-change review decisions can now be saved as metadata-only artifacts with accepted/rejected/pending decisions, derived path metadata, redaction/truncation flags, checkpoint digest binding, branch/head metadata, and test-evidence count.
- Implemented in this slice: artifact save revalidates a fresh matching checkpoint digest and validates supplied section patch digests against the current raw diff review before persistence.
- Implemented in this slice: the dashboard can apply saved decisions only when the artifact checkpoint digest matches the currently loaded raw diff review; stale artifacts are visible history but cannot unblock Git approval/direct-run controls.
- Still out of scope after this slice: hunk/file apply or revert mutation, untracked file content review, rollback/revert backend Git flows, broader Git branch/PR metadata automation, full unified chat, broader editable policy/settings workflows, and persistent or multi-worker project activation semantics.

Validation:
- Focused artifact/UI validation passed: `uv run pytest -q tests\test_git_workflows.py::test_git_change_review_artifact_persists_metadata_only tests\test_git_workflows.py::test_git_change_review_artifact_api_lists_and_retrieves_saved_artifacts tests\test_git_workflows.py::test_git_change_review_artifact_rejects_stale_checkpoint_digest tests\test_git_workflows.py::test_git_change_review_artifact_rejects_mismatched_section_digest tests\test_ui.py::test_web_ui_static_assets_are_served` with 5 passed.
- Focused changed-surface validation passed: `uv run pytest -q tests\test_ui.py tests\test_git_workflows.py::test_git_raw_diff_review_api_returns_checkpoint_bound_sections tests\test_git_workflows.py::test_git_change_review_artifact_persists_metadata_only tests\test_git_workflows.py::test_git_change_review_artifact_api_lists_and_retrieves_saved_artifacts tests\test_git_workflows.py::test_git_change_review_artifact_rejects_stale_checkpoint_digest tests\test_git_workflows.py::test_git_change_review_artifact_rejects_mismatched_section_digest` with 9 passed.
- Full regression passed: `uv run pytest -q` with 1,364 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010am Generated-Tool Browser Network-Approval Consumption

Status: completed for the scoped generated-tool browser network-approval consumption scenario; Sprint 16 remains active for deeper nested type-specific request editors, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected generated-tool network-approval consumption after provider network consumption because the UI already exposes optional `network_approval_id` and the backend has a deterministic socket approval contract.
- Completed: QA added a local TCP listener fixture and a browser-driven generated-tool network scenario that creates a socket-using approval-required tool, creates and approves a `generated_tool/socket_connect` network approval, fills that id into the dashboard payload editor, executes the bound tool request, and verifies both approvals are executed.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: the current browser smoke matrix now covers review/approve/bound execution across CLI, filesystem, web-retrieval network, provider, generated-tool, provider network approval consumption, and generated-tool socket network approval consumption.
- Still out of scope after this slice: deeper nested type-specific editors, persistent AI-change artifact apply/revert workflows, full unified chat, broader editable settings/policy workflows, and persistent or multi-worker project activation semantics.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 10 passed.
- Focused browser lint checks passed: `uv run ruff format --check tests\test_ui_browser.py` and `uv run ruff check tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,360 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010al Provider Browser Network-Approval Consumption

Status: completed for the scoped provider browser network-approval consumption scenario; Sprint 16 remains active for generated-tool network-approval consuming browser flows, deeper nested type-specific request editors, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected provider network-approval consumption as the next bounded browser scenario after the core approval-family browser matrix was covered.
- Completed: Developer added optional `network_approval_id` fields to provider and generated-tool bound execution payload scaffolds so operators can paste approved network approval ids without hand-adding JSON fields.
- Completed: QA updated the provider browser smoke to create and approve a provider network approval, fill that `network_approval_id` into the dashboard payload editor, execute the bound provider request, and verify both provider and network approval records are executed.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: provider browser bound execution now validates the dashboard path for consuming an approved `network_approval_id` while preserving backend provider/network binding checks.
- Still out of scope after this slice: generated-tool network approval consuming browser scenarios, deeper nested type-specific editors, persistent AI-change artifact apply/revert workflows, full unified chat, and broader editable settings/policy workflows.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 9 passed.
- Focused browser/source checks passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui_browser.py`, and `uv run ruff check tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,359 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010ak Browser-Driven Seeded Generated-Tool Approval Execution

Status: completed for the scoped browser-driven seeded generated-tool approval execution scenario; Sprint 16 remains active for provider/tool network-approval consuming browser flows, deeper nested type-specific request editors, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected generated-tool approval as the final current approval-family browser scenario after CLI, filesystem, web-retrieval network, and provider browser paths were covered.
- Completed: QA added a browser-driven generated-tool approval scenario that creates an approval-required local tool, filters the unified approval inbox to tool, reviews and approves a seeded tool approval, executes the guided bound tool payload, verifies returned payload value rendering, and confirms the approval review status is executed.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: browser smoke coverage now validates seeded approval review/approve/bound execution across CLI, filesystem, web-retrieval network, provider, and generated-tool approval families.
- Still out of scope after this slice: provider/tool network approval consuming browser scenarios, deeper nested type-specific editors, persistent AI-change artifact apply/revert workflows, full unified chat, and broader editable settings/policy workflows.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 9 passed.
- Focused browser lint checks passed: `uv run ruff format --check tests\test_ui_browser.py` and `uv run ruff check tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,359 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010aj Browser-Driven Seeded Provider Approval Execution

Status: completed for the scoped browser-driven seeded provider approval execution scenario; Sprint 16 remains active for the remaining generated-tool browser approval scenario, deeper nested type-specific request editors, provider/tool network-approval consuming browser flows, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected provider approval as the next bounded browser scenario because CLI, filesystem, and web-retrieval network browser paths were already covered and provider execution can be isolated with deterministic fake transport.
- Completed: QA configured the browser test app with the external OpenAI-compatible provider settings and a fake provider transport that validates credential header binding without external network calls.
- Completed: QA added a browser-driven provider approval scenario that filters the unified approval inbox to provider, reviews and approves a seeded provider approval, executes the guided bound generation payload, verifies returned content rendering, and confirms the approval review status is executed.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: browser smoke coverage now validates a seeded provider approval from inbox filtering through safe review, visible approval decision, guided bound provider generation execution, returned content rendering, and backend executed status.
- Still out of scope after this slice: generated-tool browser approval scenario, provider/tool network approval consuming flows, deeper nested type-specific editors, persistent AI-change artifact apply/revert workflows, and full unified chat.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 8 passed.
- Focused browser lint checks passed: `uv run ruff format --check tests\test_ui_browser.py` and `uv run ruff check tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,358 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010ai Browser-Driven Seeded Web-Retrieval Network Approval Execution

Status: completed for the scoped browser-driven seeded web-retrieval network approval execution scenario; Sprint 16 remains active for provider/tool browser approval scenarios, deeper nested type-specific request editors, provider/tool network-approval consuming browser flows, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected web-retrieval network approval as the next bounded browser scenario because CLI and filesystem browser paths were already covered and web retrieval can execute against a deterministic local text server.
- Completed: QA added a local HTTP text-response fixture and configured the browser test app with an approval-required localhost network policy.
- Completed: QA added a browser-driven network approval scenario that filters the unified approval inbox to network, reviews and approves a seeded web-retrieval approval, executes the guided bound fetch payload, verifies the execution output content, and confirms the approval review status is executed.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: browser smoke coverage now validates a seeded web-retrieval network approval from inbox filtering through safe review, visible approval decision, guided bound fetch execution, returned content rendering, and backend executed status.
- Still out of scope after this slice: provider/tool browser approval scenarios, provider/tool network approval consuming flows, deeper nested type-specific editors, persistent AI-change artifact apply/revert workflows, and full unified chat.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 7 passed.
- Focused browser lint checks passed: `uv run ruff format --check tests\test_ui_browser.py` and `uv run ruff check tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,357 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010ah Browser-Driven Seeded Filesystem Approval Execution

Status: completed for the scoped browser-driven seeded filesystem approval execution scenario; Sprint 16 remains active for remaining network/provider/tool browser approval scenarios, deeper nested type-specific request editors, provider/tool network-approval consuming browser flows, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected filesystem delete approval as the next non-CLI browser scenario because BL-010ag covered CLI review/approval but did not verify bound non-CLI execution through the dashboard.
- Completed: QA updated the browser smoke harness to seed approvals through the live FastAPI server instead of mixing `TestClient` with Uvicorn during browser tests.
- Completed: QA added a browser-driven filesystem scenario that filters the unified approval inbox to filesystem, reviews and approves a seeded delete approval, executes the guided bound filesystem payload, verifies the executed review state, and confirms the file was deleted.
- Completed: Developer fixed the validation-discovered HTTP runtime root-switch guard issue by using event-loop-scoped async locks so repeated local browser servers do not share a stale module-level lock across event loops.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: browser smoke coverage now validates a seeded filesystem approval from inbox filtering through safe review, visible approval decision, guided bound execution, backend executed status, and filesystem side effect.
- Implemented in this slice: the HTTP request barrier keeps its root-switch serialization behavior while avoiding cross-event-loop lock binding when multiple local app servers are created in one test process.
- Still out of scope after this slice: network/provider/tool browser approval scenarios, provider/tool network approval consuming flows, deeper nested type-specific editors, persistent AI-change artifact apply/revert workflows, and full unified chat.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 6 passed.
- Focused browser/source lint checks passed: `uv run ruff format --check src\dgentic\main.py tests\test_ui_browser.py` and `uv run ruff check src\dgentic\main.py tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,356 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010ag Browser-Driven Seeded CLI Approval Scenario

Status: completed for the scoped first browser-driven seeded approval scenario; Sprint 16 remains active for broader non-CLI browser approval scenarios, deeper nested type-specific request editors, provider/tool network-approval consuming browser flows, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected the smallest browser-driven seeded approval path after BL-010af: CLI approval review and approval through the actual dashboard UI.
- Completed: QA explorer confirmed CLI approvals are the lowest-friction seeded source and recommended stopping before direct command execution for this first browser slice.
- Completed: QA added `tests/test_ui_browser.py`, including a live FastAPI UI fixture, dependency-light local Chromium/Edge DevTools driver, seeded CLI approval setup, browser inbox filtering, review-panel interaction, dashboard approval submission, and refreshed approved-state assertion.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: the test suite now drives a real browser against `/ui/` to verify that a seeded pending CLI approval appears in the dashboard, can be reviewed, can be approved through the visible form, and refreshes to an approved review state with the direct-execute affordance enabled.
- Still out of scope after this slice: direct browser execution of the approved command, browser-driven filesystem/network/provider/tool approval scenarios, provider/tool network approval consuming flows, and type-specific nested editor browser tests.

Validation:
- Focused browser/UI validation passed: `uv run pytest -q tests\test_ui_browser.py tests\test_ui.py` with 5 passed.
- Focused browser lint/static checks passed: `uv run ruff format --check tests\test_ui_browser.py` and `uv run ruff check tests\test_ui_browser.py`.
- Full regression passed: `uv run pytest -q` with 1,355 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010af Approval Dashboard Contract Coverage

Status: completed for the scoped approval-dashboard backend contract and redaction-hardening slice; Sprint 16 remains active for browser-driven seeded approval scenarios, deeper nested type-specific request editors, provider/tool network-approval consuming browser flows, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, and persistent or multi-worker project activation semantics.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected approval scenario coverage as the next Sprint 16 slice after BL-010ae because the dashboard now exposes all approval sources and bound request scaffolds, but lacked one contract test spanning the unified inbox.
- Completed: QA explorer identified concrete gaps in unified approval-inbox coverage, method-aware approval capability coverage, and the UI approval source matrix contract.
- Completed: QA added `tests/test_approval_dashboard_contracts.py` to seed CLI, filesystem, network, provider, and tool approval records, exercise safe list/review/approve flows, and validate bound execution fields against backend consumers.
- Completed: Developer fixed a QA-discovered CLI approval/run redaction gap so secret-shaped requester, agent/task, and decision context is redacted in CLI approval records, run records, run results, and binding validation while preserving approval digest matching.
- Completed: QA expanded method-aware auth capability coverage for unified approval routes and pinned the dashboard approval source matrix to the backend approval route contracts.
- Completed: PM updated README, usage, architecture, project status, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: backend/dashboard approval contracts now have end-to-end API scenario coverage for all five approval inbox sources, including safe review metadata, approve decisions, direct CLI execution, filesystem `approval_id` consumption, provider `approval_id` plus network `network_approval_id` consumption, and generated-tool `approval_id` consumption.
- Implemented in this slice: CLI approval and run context now redacts secret-shaped requester, agent/task, supervisor, status, and decision fields before response or persisted run output exposure.
- Still out of scope after this slice: Playwright/browser-seeded approval inbox decisions, nested provider message editors, tool-schema-aware payload editors, and richer provider/tool network-approval consumption UI.

Validation:
- Focused dashboard contract validation passed: `uv run pytest -q tests\test_approval_dashboard_contracts.py tests\test_ui.py::test_web_ui_approval_sources_match_backend_contracts tests\test_auth.py::test_capability_for_request_splits_approval_review_from_execution` with 38 passed.
- Focused CLI/API regression passed: `uv run pytest -q tests\test_cli_runtime.py tests\test_api.py::test_cli_approval_api_persists_and_executes_approved_command tests\test_api.py::test_cli_approval_api_splits_requester_and_reviewer_capabilities tests\test_api.py::test_cli_approval_direct_execute_requires_bound_authenticated_requester tests\test_api.py::test_cli_approval_review_api_returns_safe_bound_execution_contract tests\test_api.py::test_cli_approval_api_redacts_decision_reason_secrets tests\test_api.py::test_cli_execute_api_requires_bound_approval_id_in_production` with 95 passed and 2 skipped.
- Full regression passed: `uv run pytest -q` with 1,354 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, and `git diff --check`.

### Sprint 16 BL-010ae Guided Bound Request Fields

Status: completed for the scoped guided non-CLI bound request field slice; Sprint 16 remains active for deeper nested type-specific request editors, provider/tool network-approval consuming flows, full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, persistent or multi-worker project activation semantics, and end-to-end approval scenarios.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected guided non-CLI bound request fields as the next Sprint 16 approval-dashboard slice because BL-010ab made raw JSON execution possible but still required operators to hand-edit every request.
- Completed: Explorer recommended a UI-only typed editor that keeps the canonical JSON textarea as the source of truth, locks approval binding fields, and preserves backend request-binding enforcement.
- Completed: Developer added guided field rendering for scaffold payloads, scalar/boolean/number/nested JSON controls, field-to-JSON synchronization, locked binding fields, and guided-field error handling without adding or bypassing backend endpoints.
- Completed: QA extended static UI coverage for guided-field helpers, binding locks, filesystem/network/provider/tool field coverage, raw JSON fallback, and handoff-only provider/tool network approval behavior.
- Completed: PM updated README, usage, project status, backlog, architecture notes, and this progress log.

Feature tracking:
- Implemented in this slice: approved non-CLI bound request panels now expose guided top-level fields for filesystem, web retrieval, provider, and tool payload scaffolds while keeping raw JSON visible and backend binding validation authoritative.
- Still out of scope after this slice: deep nested provider message row editors, tool-schema-aware payload editors, direct provider/tool network-approval consumption outside matching provider/tool execution requests, and end-to-end approval scenario tests with seeded approvals.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `uv run pytest tests\test_ui.py -q` with 3 tests, and `git diff --check`.
- Guided-editor browser smoke passed against a temporary Uvicorn server on `127.0.0.1:8771` at tablet 820x1180: guided text, checkbox, number, and nested JSON controls synced into the canonical payload textarea, the approval binding field remained disabled with the locked-title affordance, no horizontal overflow appeared, and there were zero console messages, page errors, failed requests, or HTTP responses at status 400 or higher. Screenshot evidence was written to `.dgentic/ui-smoke/bl010ae-guided-editor.png`.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010ad Local Task-Chat History

Status: completed for the scoped local task-chat history slice; Sprint 16 remains active for full unified chat beyond local task history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, richer type-specific non-CLI request editors, provider/tool network-approval consuming flows, persistent or multi-worker project activation semantics, and end-to-end approval scenarios.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local task-chat history as the next bounded Sprint 16 slice after BL-010ac because the first task-chat composer still reset to an empty transcript on reload.
- Completed: QA identified the key safety risks: do not persist bearer tokens in local storage, cap saved transcript size, tolerate corrupt storage, and avoid treating restored plan objects as fresh executable state.
- Completed: Developer added capped browser-local task-chat message storage, save/restore/clear helpers, history status text, compact stored plan/run snapshots, corrupt/quota-tolerant fallback behavior, and display-only restored plan cards.
- Completed: QA extended static UI coverage for the local-history contract, storage helpers, history status selectors, no `TOKEN_KEY` localStorage write, and CSS hooks.
- Completed: PM updated README, usage, project status, backlog, Agile plan, architecture notes, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` task-chat transcript history survives reloads in capped browser-local storage, Clear removes the saved history, corrupt or unavailable local storage no longer breaks the dashboard, and restored plan cards remain reviewable without enabling stale direct execution.
- Still out of scope after this slice: full unified chat with durable backend conversation records, streaming responses, cross-surface chat integration, and AI-change apply/revert workflows.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `uv run pytest tests\test_ui.py -q` with 3 tests, and `git diff --check`.
- Browser history smoke passed against a temporary Uvicorn server on `127.0.0.1:8770` at mobile 390x844: saved transcript restored after reload, restored plan Run button was disabled with display-only title, Clear removed `localStorage` history and reset the transcript, no horizontal overflow appeared, and there were zero console messages, page errors, failed requests, or HTTP responses at status 400 or higher. Screenshot evidence was written to `.dgentic/ui-smoke/bl010ad-mobile-history.png`.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010ac Responsive Browser Validation Hardening

Status: completed for the scoped responsive/browser validation slice; Sprint 16 remains active for deeper conversational history, persistent AI-change artifact apply/revert workflows, broader editable settings and policy workflows, richer type-specific non-CLI request editors, provider/tool network-approval consuming flows, persistent or multi-worker project activation semantics, and end-to-end approval scenarios.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected responsive/browser validation as the next bounded Sprint 16 slice after BL-010ab because the dashboard had accumulated several dense approval, task, and Git surfaces that needed real viewport coverage.
- Completed: QA reproduced the mobile issue at 390x844 where the approval panel created horizontal overflow through an unconstrained internal grid track and segmented approval filter controls.
- Completed: Developer constrained panel grid tracks, allowed panel children and action rows to shrink/wrap, wrapped mobile segmented controls, and added an inline empty favicon declaration to remove `/favicon.ico` 404 browser noise.
- Completed: QA added static UI coverage for the favicon declaration, panel shrink guard, and mobile segmented-control wrapping.
- Completed: PM updated README, project status, backlog, architecture notes, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` desktop/tablet/mobile smoke coverage is clean, mobile approval filters stay inside the viewport, panel content no longer widens the page, and browser startup no longer emits favicon 404 noise.
- Still out of scope after this slice: richer end-to-end approval scenarios with seeded approvals and operator decisions, persistent AI-change artifact apply/revert behavior, deeper task-chat history, and broader editable policy/settings workflows.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `uv run pytest tests\test_ui.py -q` with 3 tests, and `git diff --check`.
- Responsive Playwright smoke passed against a temporary Uvicorn server on `127.0.0.1:8769` for desktop 1440x1100, tablet 820x1180, and mobile 390x844. Each viewport reported `scrollWidth == clientWidth`, zero overflowing elements, visible overview/tasks/approvals/git/settings panels, zero console messages, zero page errors, zero failed requests, and zero HTTP responses at status 400 or higher. Screenshots were refreshed under `.dgentic/ui-smoke/bl010ac-desktop.png`, `.dgentic/ui-smoke/bl010ac-tablet.png`, and `.dgentic/ui-smoke/bl010ac-mobile.png`.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010ab Non-CLI Bound Request Editor And Execution UX

Status: completed for the scoped editable non-CLI bound execution slice; Sprint 16 remains active for richer type-specific non-CLI editors, provider/tool network-approval consuming flows, persistent AI-change artifact apply/revert workflows, deeper conversational history, broader editable settings and policy workflows, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected non-CLI bound request editor/execution UX as the next bounded Sprint 16 slice because BL-010y exposed safe payload scaffolds but still required operators to leave the dashboard for execution.
- Completed: Explorer confirmed the safe path is to reuse existing filesystem, web retrieval, provider, and tool execution endpoints, preserve approval binding, and keep provider/tool network approvals as handoff-only `network_approval_id` payloads.
- Completed: Developer added editable JSON payloads, JSON object validation, approval/network-approval binding checks, direct execution for dashboard-callable bound requests, result rendering, approval refresh, and disabled handoff-only handling for provider/tool network approvals.
- Completed: QA extended static UI coverage for editable payload controls, binding validation, execution action, result/error output, approval refresh, handoff-only behavior, and CSS hooks.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: approved non-CLI review panels can edit and execute bound payloads for dashboard-callable requests while keeping existing backend single-use binding checks authoritative.
- Still out of scope after this slice: type-specific guided editors for each non-CLI request family, restoring redacted original provider/tool values automatically, direct provider/tool network-approval consumption outside the matching provider/tool execution request, and end-to-end browser approval scenarios.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Focused bound-execution API regression passed: `uv run pytest tests\test_api.py::test_guarded_filesystem_destructive_operations_require_approval tests\test_api.py::test_web_retrieval_network_api_pins_surface_claims_approval_and_redacts tests\test_api.py::test_web_retrieval_fetch_claims_single_use_approval tests\test_api.py::test_generated_tool_execute_api_requires_bound_approval_in_production -q` with 4 tests.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:61697`: `/ui/` served and `/ui/app.js` included the editable bound execution helpers.

### Sprint 16 BL-010aa AI-Change Review Decisions

Status: completed for the scoped session-level AI-change review decision slice; Sprint 16 remains active for persistent AI-change artifact apply/revert workflows, deeper conversational history, full non-CLI bound request editors/execution, broader editable settings and policy workflows, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected AI-change review decisions as the next bounded Sprint 16 slice after BL-010z because raw checkpoint-bound Git diff review already existed and accept/reject review remained a visible user-facing gap.
- Completed: Explorer confirmed the current backend exposes staged/unstaged diff sections, not authoritative per-file apply/revert artifacts, so the safe scope is session review annotation without backend mutation semantics.
- Completed: Developer added accept/reject/clear controls to loaded Git diff sections, decision counts, copyable review evidence, rejected-section status, and a client-side pause for dashboard Git approval/direct-run controls when a loaded section is rejected.
- Completed: QA extended static UI coverage for review decision state, evidence helper wiring, rejected-section gating, decision controls, CSS hooks, and continued avoidance of HTML injection helpers.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can annotate loaded checkpoint-bound staged/unstaged diff sections as accepted or rejected, summarize the decisions, copy review evidence, and pause dashboard Git closeout actions when a section is rejected.
- Still out of scope after this slice: persisted review decisions, authoritative per-file/per-hunk accept/reject, applying or reverting AI-change artifacts, untracked file content preview, branch cleanup, PR metadata expansion, rollback/revert flows, allowed remote/branch policy editors, and deeper Git audit/observability.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Focused Git diff API regression passed: `uv run pytest tests\test_git_workflows.py::test_git_raw_diff_review_api_returns_checkpoint_bound_sections -q` with 1 test.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49766`: `/ui/` served and `/ui/app.js` included the Git change review decision helpers.

### Sprint 16 BL-010z First Chat-Style Task Workflow

Status: completed for the scoped first chat-style task workflow slice; Sprint 16 remains active for deeper conversational history, accept/reject AI-change artifact workflows, full non-CLI bound request editors/execution, broader editable settings and policy workflows, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a first task-chat workflow as the next bounded Sprint 16 slice after BL-010y because it directly addresses the remaining chat gap while reusing existing task APIs.
- Completed: Explorer confirmed the safest implementation point is inside the existing dashboard task panel with no backend/API expansion.
- Completed: Developer added a task-chat composer, transcript, safe text-rendered messages, `/tasks/plan` submission, plan rendering, and optional `/tasks/execute` handoff for the created plan.
- Completed: QA extended static UI coverage for task-chat markup, helper wiring, endpoint reuse, CSS hooks, and continued avoidance of HTML injection helpers.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can create a task plan from a chat-style message, render the resulting plan in a transcript, and optionally run it through the existing deterministic task execution contract.
- Still out of scope after this slice: persisted conversational history, streaming agent responses, unified approval/change review in the chat thread, accept/reject AI-change artifacts, full non-CLI request editors/execution, broader editable settings/policy surfaces, and broader responsive/browser validation.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Focused task API regression passed: `uv run pytest tests\test_api.py::test_task_plan_contains_expected_execution_shape tests\test_api.py::test_plan_can_execute_deterministically tests\test_api.py::test_task_history_is_persisted_to_local_state -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49690`: `/ui/` served `taskChatForm` and `/ui/app.js` included `submitTaskChatMessage`.

### Sprint 16 BL-010y Non-CLI Bound Execution Handoff UI

Status: completed for the scoped non-CLI bound execution handoff UI slice; Sprint 16 remains active for full chat workflows beyond the task-plan cards, accept/reject AI-change artifact workflows, full non-CLI bound request editors/execution, broader editable settings and policy workflows, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected non-CLI approval execution UX as the next bounded Sprint 16 approval-dashboard slice after BL-010x.
- Completed: Explorer confirmed filesystem, network, provider, and tool approvals require normal bound execution requests rather than CLI-style direct approval execute routes.
- Completed: Developer added dashboard approval execution controls that preserve CLI direct execution and render bound execution request panels for approved non-CLI reviews.
- Completed: Developer added filesystem, network, provider, and tool payload scaffold builders with approval context, known safe review fields, endpoint selection, notes for original-value requirements, and copy support.
- Completed: QA extended static UI coverage for the bound execution helpers, endpoint scaffolds, copy affordance, and CSS hook.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` shows the correct bound execution endpoint and safe payload scaffold for approved filesystem, network, provider, and tool approvals without bypassing backend digest/request binding.
- Still out of scope after this slice: browser-side full request editors, direct non-CLI execution submission from the dashboard, full chat UX, accept/reject AI-change artifacts, broader editable settings/policy surfaces, end-to-end approval scenarios, and broader browser/responsive validation.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49718`: `/ui/` served and `/ui/app.js` included the bound execution scaffold helpers, endpoint targets, and copy affordance.

### Sprint 16 BL-010x Richer Task Plan And Run UI

Status: completed for the scoped richer task plan/run UI slice; Sprint 16 remains active for full chat workflows beyond the task-plan cards, accept/reject AI-change artifact workflows, broader editable settings and policy workflows, broader non-CLI approval execution UX, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected richer planner/run UI as the next user-facing Sprint 16 slice because the backend already exposes deterministic task planning, persisted plan/run listing, and `POST /tasks/execute`.
- Completed: Developer replaced the simple recent-plan list with actionable plan cards showing objective metadata, context chips, step detail, and related deterministic run history.
- Completed: Developer added a Run Plan action that posts the full `TaskPlan` to the existing `/tasks/execute` contract, refreshes task metrics and run history, and preserves safe text-only rendering through existing DOM helpers.
- Completed: QA extended static UI coverage for the task-plan helpers, `/tasks/execute` endpoint wiring, Run Plan affordance, and CSS hooks.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can inspect recent deterministic task plans as actionable cards and execute a selected plan through the existing backend task-run contract, then show related run evidence.
- Still out of scope after this slice: full chat UX, conversational task history, accept/reject AI-change artifacts, broader editable policy/settings surfaces, broader non-CLI approval execution UX, persistent/multi-worker project activation semantics, end-to-end approval scenarios, and broader browser/responsive validation.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49717`: `/ui/` served and `/ui/app.js` included the richer task plan/run helpers and `/tasks/execute` wiring.

### Sprint 16 BL-010w Checkpoint Review-To-Run Git Actions

Status: completed for the scoped Git review-to-run UI slice; Sprint 16 remains active for full chat workflows, accept/reject AI-change artifact workflows, broader editable settings and policy workflows, broader non-CLI approval execution UX, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected direct checkpoint-bound Git run controls as the next user-facing Sprint 16 slice because BL-010v made raw checkpoint-bound review available and the backend already exposes guarded direct commit, push, and PR runners.
- Completed: Explorer confirmed the smallest safe scope is UI wiring around existing `/cli/git/commit-runs`, `/cli/git/push-runs`, and `/cli/git/pr-runs`, with branch cleanup, PR metadata expansion, rollback/revert, and arbitrary Git commands kept deferred.
- Completed: Developer added a direct Run Now control beside Git approval creation, reusing the current checkpoint digest, evidence, commit message, timeout, and PR fields.
- Completed: Developer added direct Git run endpoint/payload helpers, blocked-checkpoint disabling, commit/PR required-field validation for the direct button, safe metadata result rendering, and post-run button disabling so stale checkpoint state is not reused.
- Completed: QA extended static UI coverage for the direct-run controls, endpoint routing, shared payload helper, result renderer, event binding, and CSS hooks.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can run the existing checkpoint-bound direct Git commit, push, and PR workflows after a ready checkpoint, using safe backend revalidation and displaying metadata-only results.
- Still out of scope after this slice: `git add`, untracked file preview, accept/reject AI-change artifacts, direct non-Git approval replay, branch cleanup, PR labels/reviewers/assignees/projects/templates, rollback/revert flows, allowed remote/branch policy editors, and deeper Git audit/observability.

Validation:
- Focused UI validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49696`: `/ui/` served the direct Git run control and the direct Git run routes were registered.

### Sprint 16 BL-010v Checkpoint-Bound Raw Git Diff Review

Status: completed for the scoped raw Git diff review slice; Sprint 16 remains active for full chat workflows, accept/reject AI-change artifact workflows, broader editable settings and policy workflows, broader non-CLI approval execution UX, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected checkpoint-bound raw Git diff review as the next user-facing Sprint 16 slice because Git checkpoint approval creation exposed the need for file-level review before commit/push/PR closeout.
- Completed: Security/Architect recommended a read-only `/cli/git/diff-reviews` contract that revalidates the checkpoint digest, excludes untracked file content, omits protected paths, redacts secret-shaped patch text, caps output, and avoids patch bodies in logs.
- Completed: Developer added `POST /cli/git/diff-reviews`, raw diff review response models, staged/unstaged section generation, protected-path omission, redaction/truncation flags, NUL-separated Git path parsing, and metadata-only audit events.
- Completed: Developer added the dashboard Load Diff panel under Git checkpoints, safe `<pre>` text rendering for patch content, section metadata chips, omitted-path visibility, and error handling for stale/unavailable reviews.
- Completed: QA added Git workflow/API coverage for staged and unstaged redaction, stale digest rejection, protected-path omission, response binding, and large patch truncation, plus auth capability and static UI wiring assertions.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can load a checkpoint-bound raw Git diff review for tracked staged and unstaged patch content, and the backend returns only fresh digest-bound, redacted, bounded sections with safe metadata.
- Still out of scope after this slice: accept/reject AI-change artifacts, untracked file content preview, direct Git run buttons from the dashboard, branch cleanup, PR labels/reviewers/assignees/projects/templates, rollback/revert flows, allowed remote/branch policy editors, and deeper Git audit/observability.

Validation:
- Focused backend/UI validation passed: `uv run ruff format --check src\dgentic\git_workflows.py src\dgentic\api\routes.py tests\test_git_workflows.py tests\test_auth.py tests\test_ui.py`, `uv run ruff check src\dgentic\git_workflows.py src\dgentic\api\routes.py tests\test_git_workflows.py tests\test_auth.py tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, `uv run pytest tests\test_git_workflows.py -q` with 55 tests, `uv run pytest tests\test_auth.py -q` with 136 tests, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,336 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49695`: `/ui/` served, `/cli/git/diff-reviews` was registered, and `/ui/app.js` exposed the Git diff review helpers.

### Sprint 16 BL-010u Structured Approval Review Summaries

Status: completed for the scoped approval-review UX slice; Sprint 16 remains active for full chat workflows, full raw diff/AI-change review, broader editable settings and policy workflows, broader non-CLI approval execution UX, persistent or multi-worker project activation semantics, end-to-end approval scenarios, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected structured approval review summaries as the next user-facing approval-dashboard slice because safe review contracts already exist for CLI, filesystem, network, provider, and tool approval families.
- Completed: Architect/Explorer confirmed source-specific review fields and warned that non-CLI direct execution should remain out of scope.
- Completed: Developer replaced raw JSON-first approval review rendering with structured source-specific summary cards, warning rows, binding/digest context, and decision audit fields while preserving raw review JSON in a secondary details view.
- Completed: Developer changed approve/deny handling to reload the safe `/review` response after decision mutations instead of treating approval records as review DTOs.
- Completed: QA extended UI static contract tests for structured review helpers, warning fields, bound/direct execution flags, workflow binding visibility, safe review reload after decisions, and CSS hooks.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` shows structured approval review summaries for CLI, filesystem, network, provider, and tool approvals using existing safe backend review contracts.
- Still out of scope after this slice: non-CLI direct execution UX, end-to-end approval scenario browser tests, raw diff/AI-change review, and backend approval schema changes.

Validation:
- Focused UI/static validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49694`: `/ui/` served the approval review container and `/ui/app.js` served the structured approval review helpers.

### Sprint 16 BL-010t Git Checkpoint Approval Actions

Status: completed for the scoped Git checkpoint approval UX slice; Sprint 16 remains active for full chat workflows, full raw diff/AI-change review, broader editable settings and policy workflows, broader non-CLI approval execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected checkpoint-bound Git approval creation as the next user-facing Sprint 16 slice because the backend already exposes guarded commit, push, and PR approval APIs while deeper backend Git roadmap items remain deferred, not cancelled.
- Completed: Architect/Explorer confirmed the current backend supports safe checkpoint metadata review plus approval creation, but not raw patch display or accept/reject AI-change artifacts.
- Completed: Developer added a Git approval action panel that opens after checkpoint review, stores the checkpoint request evidence, and exposes the correct commit, push, or PR approval form for ready checkpoints.
- Completed: Developer wired approval creation through `/cli/git/commit-approvals`, `/cli/git/push-approvals`, and `/cli/git/pr-approvals`, then refreshes the unified CLI approval inbox for reviewer follow-through.
- Completed: QA extended UI static contract tests for the Git approval form, checkpoint state helpers, endpoint routing, payload fields, approval inbox refresh, and CSS hook.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can create checkpoint-bound Git commit, push, and PR approvals from ready Git checkpoints using existing backend Git workflow approval routes.
- Still out of scope after this slice: raw file-by-file diff display, accept/reject AI-change artifacts, direct Git run buttons from the dashboard, branch cleanup, PR labels/reviewers/assignees/projects/templates, rollback/revert flows, allowed remote/branch policy editors, and deeper Git audit/observability.

Validation:
- Focused UI/static validation passed: `node --check src\dgentic\ui\app.js`, `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against an in-process temporary Uvicorn server on `127.0.0.1:49693`: `/ui/` served the Git approval action panel and `/ui/app.js` served `createGitApproval` plus the Git approval route helper.

## 2026-05-14

### Sprint 16 BL-010s CLI Policy Edit And Toggle UI

Status: completed for the scoped CLI policy update UX slice; Sprint 16 remains active for full chat workflows, full Codex-style AI-change diff review, broader editable settings and policy workflows, broader non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local CLI policy update/toggle controls as the next compact Sprint 16 editable-policy slice because the backend already exposes guarded PATCH contracts and managed-rule read-only behavior.
- Completed: Explorer recommended the smallest safe per-rule enable/disable flow and confirmed the full partial-update contract for local CLI policy rules.
- Completed: Developer replaced the generic CLI policy renderer with a dedicated list that shows local rule actions while disabling edit/toggle affordances for managed rules or managed `cli_policy` locks.
- Completed: Developer added edit-mode population for existing local rules, cancel-edit reset behavior, and PATCH submission through the existing `/cli/policy/rules/{rule_id}` route.
- Completed: QA extended UI static contract tests for the edit/toggle renderer, PATCH helper, cancel binding, managed-lock helper, and dynamic toggle metadata.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can edit local CLI policy rule fields and enable or disable local CLI rules through existing backend policy routes while preserving backend capability checks, managed-rule read-only enforcement, and managed policy surface locks.
- Still out of scope after this slice: delete/archive flows, hook/network/filesystem policy editors, provider/routing/settings editors, managed-policy mutation workflows, and browser end-to-end policy mutation scenarios.

Validation:
- Focused UI/static validation passed: `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against a temporary FastAPI server on `127.0.0.1:49688`: `/ui/` served the CLI policy editor markup and `/ui/app.js` served the edit/toggle helper code.

### Sprint 16 BL-010r CLI Policy Creation UI

Status: completed for the scoped first editable policy UX slice; Sprint 16 remains active for full chat workflows, full Codex-style AI-change diff review, broader editable settings and policy workflows, broader non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected local CLI policy rule creation as the next compact Sprint 16 editable-policy slice because the backend already exposes guarded create/list contracts and managed-lock enforcement.
- Completed: Explorer confirmed the required `POST /cli/policy/rules` payload, `cli` capability requirement, and `managed_policy_locks` 403 behavior.
- Completed: Developer added a dashboard CLI rule creation form for name, match type, pattern, permission mode, reason, agent roles, priority, and enabled state.
- Completed: Developer wired form submission to the existing CLI policy rule API, reset successful submissions, rendered success/error feedback, and refreshed policy lists plus summaries after creation.
- Completed: QA extended UI static contract tests for the new form markup, payload helper, POST wiring, submit binding, and CSS hooks.
- Completed: PM updated README, project status, usage, architecture, backlog, Agile plan, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can create local CLI policy rules through the existing backend policy route while preserving backend capability checks, validation, and managed-lock read-only enforcement.
- Still out of scope after this slice: editing existing CLI rules, hook/network/filesystem policy editors, provider/routing/settings editors, managed-policy mutation workflows, and browser end-to-end policy mutation scenarios.

Validation:
- Focused UI/static validation passed: `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live UI smoke passed against a temporary FastAPI server on `127.0.0.1:49671`: `/ui/` served the CLI policy form markup and `/ui/app.js` served the policy creation helper code.

### Sprint 16 BL-010q Settings, Policy, And Git Review Summary UI

Status: completed for the scoped read-only review-summary slice; Sprint 16 remains active for full chat workflows, full Codex-style AI-change diff review, editable settings and policy workflows, broader non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected a read-only settings, policy, and Git review summary slice because the existing `/settings/effective`, policy list, plugin list, recipe list, and Git checkpoint contracts already expose safe metadata.
- Completed: Explorer confirmed the UI can deepen settings/policy review and Git checkpoint review without backend endpoint expansion, while full raw diff review still needs a future backend diff contract.
- Completed: Developer grouped effective settings into runtime, security, policy-source, provider, memory/tool, execution-limit, and other sections with source, redaction, managed-field, managed-digest, and policy-lock summaries.
- Completed: Developer added a policy review summary for CLI rules, command recipes, hook policies, plugins, managed locks, and disabled records using existing list endpoints.
- Completed: Developer added a compact AI-change metadata summary to Git checkpoints using readiness, diff stats, changed-path count, evidence-line count, checkpoint digest, and action metadata already available to the UI.
- Completed: QA extended UI static contract tests for the new settings, policy, and Git review helpers, markup ids, and CSS hooks.
- Completed: PM updated README, project status, usage, architecture, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can review effective settings by domain, see managed settings and policy-lock summaries, see policy surface counts by source/status, and read a Git checkpoint AI-change metadata summary without exposing raw diffs or adding backend API scope.
- Still out of scope after this slice: full patch/diff review, accept/reject AI-change workflows, editable policy/settings forms, richer reviewer audit affordances, non-CLI execute UX, and browser end-to-end scenarios.

Validation:
- Focused UI/static validation passed: `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Live UI smoke passed against a temporary FastAPI server on `127.0.0.1:56938`: `/ui/` served the policy review summary markup and `/ui/app.js` served the settings and Git review helper code.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010p Command Recipe Action UI

Status: completed for the scoped command recipe action UI slice; Sprint 16 remains active for full chat workflows, Codex-style AI-change diff review, richer settings editors, broader non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected command recipe actions as the next compact Sprint 16 slice because backend recipe preview, approval, run, and execute contracts already exist.
- Completed: Developer added recipe action controls to the policy dashboard without adding backend endpoints.
- Completed: Developer wired recipe parameter inputs to existing `/cli/recipes/{recipe_id}/preview`, `/approvals`, `/runs`, and `/execute` routes, preserving backend CLI policy/approval enforcement.
- Completed: QA extended UI static contract tests for the recipe action panel, helper functions, parameter binding, endpoint wiring, and CSS hooks.
- Completed: PM updated README, project status, planning, architecture, setup, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can select an enabled command recipe, enter safe parameter values, preview the resolved command policy, create an approval, start an async CLI run, or attempt direct execution through existing recipe contracts.
- Still out of scope after this slice: command recipe create/edit forms, plugin command recipe install/disable controls, non-CLI filesystem/provider/tool direct execution UX, and browser end-to-end recipe scenarios.

Validation:
- Focused UI/static validation passed: `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Live UI smoke passed against a temporary FastAPI server on `127.0.0.1:8031`: `/ui/` and `/ui/app.js` served the recipe action panel and helper code.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010o Guided Orchestration Task Graph Builder

Status: completed for the scoped guided task graph builder slice; Sprint 16 remains active for full chat workflows, Codex-style AI-change diff review, richer settings editors, non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected guided orchestration task graph creation as the next user-facing Sprint 16 slice after BL-010n because the dashboard could create runs but required hand-authored JSON.
- Completed: Explorer recommended keeping the existing task JSON textarea as the canonical create contract and using a helper builder rather than adding backend/API scope.
- Completed: Developer added a non-nested task builder inside the existing New run form for task id, title, role, description, dependencies, declared write paths, expected output, validation, shared-memory tags, and retry limit.
- Completed: Developer kept the raw task JSON textarea visible and canonical; builder actions parse, mutate, and rewrite that JSON so manual edits remain available.
- Completed: QA extended UI static contract tests for builder markup, helper functions, canonical JSON serialization, and CSS hooks.
- Completed: PM updated README, project status, planning, architecture, setup, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can build orchestration task graph JSON from guided controls, preview/remove tasks, prune removed-task dependencies, and submit through the existing `POST /tasks/orchestrations` contract.
- Still out of scope after this slice: graph templates, drag-and-drop dependency editing, AI-assisted graph generation, and browser end-to-end builder scenarios.

Validation:
- Focused UI/static validation passed: `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- Live UI smoke passed against a temporary FastAPI server on `127.0.0.1:8030`: `/ui/` and `/ui/app.js` served the builder surface and helper code.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010n Memory And Tool Reliability Dashboard

Status: completed for the scoped memory/tool reliability dashboard slice; Sprint 16 remains active for full chat workflows, guided task graph builders beyond raw JSON, Codex-style AI-change diff review, richer settings editors, non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected read-only memory/tool reliability visibility as the next compact Sprint 16 slice because the backend already exposes memory metadata and SQL tool-registry reliability contracts.
- Completed: Developer added a Reliability dashboard panel for memory lifecycle/freshness and tool-registry reliability using existing `/api/v1/memory/metadata` and `/api/v1/tools/registry` APIs without backend expansion.
- Completed: Developer preserved fail-soft behavior when the current token lacks `memory` or `tools` capability or either backend surface is unavailable.
- Completed: QA extended UI static contract tests for the reliability panel, endpoint wiring, render helpers, score fields, and CSS hooks.
- Completed: PM updated README, project status, planning, architecture, setup, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` now shows read-only memory totals, active memory counts, stale or inactive memory records, registered tool totals, low-reliability tool counts, and top memory/tool reliability rows.
- Still out of scope after this slice: reliability drilldown actions, lifecycle/compression job control, tool deprecation mutation UX, and browser end-to-end reliability scenarios.

Validation:
- Focused UI/static validation passed: `uv run ruff format --check tests\test_ui.py`, `uv run ruff check tests\test_ui.py`, `node --check src\dgentic\ui\app.js`, and `uv run pytest tests\test_ui.py -q` with 3 tests.
- QA reviewer found no blockers for read-only API usage, auth token propagation, fail-soft unavailable panels, or static coverage.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010m Sub-Agent Graph Visibility

Status: completed for the scoped sub-agent graph visibility slice; Sprint 16 remains active for full chat workflows, guided task graph builders beyond raw JSON, Codex-style AI-change diff review, richer settings editors, non-CLI execution UX, memory/tool reliability dashboards, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected deeper sub-agent graph visibility as the next compact Sprint 16 slice because BL-010j already loads visible agent records and agent briefs include `parent_agent_id`.
- Completed: Developer added a compact parent-child agent graph for the selected orchestration run, deriving descendants client-side from the visible `/agents` list without adding backend endpoints.
- Completed: Developer preserved fail-soft behavior when the current token lacks the `agents` capability or visible agent records do not include the selected run's task agents.
- Completed: QA extended UI static contract tests for the graph renderer, parent-agent linkage, and graph CSS hooks.
- Completed: PM updated README, project status, planning, architecture, setup, and usage docs.

Feature tracking:
- Implemented in this slice: `/ui/` orchestration detail now renders a compact agent graph for task-linked agents and their visible child agents, including status, role, task id, and brief text.
- Still out of scope after this slice: interactive graph navigation, per-agent child endpoint drilldowns, graph filtering, and browser end-to-end graph scenario automation.

Validation:
- Focused UI static tests passed: `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010l Orchestration Creation UI

Status: completed for the scoped orchestration creation UI slice; Sprint 16 remains active for full chat workflows, guided task graph builders beyond raw JSON, Codex-style AI-change diff review, richer settings editors, non-CLI execution UX, deeper sub-agent graph visualization, memory/tool reliability dashboards, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected orchestration creation as the next user-facing Sprint 16 gap after BL-010k because the dashboard could inspect and operate runs but could not create them from the orchestration console.
- Completed: Developer added a compact New run form for objective, task graph JSON, required Definition of Done evidence keys, shared-memory tags, and owner/run reuse policy.
- Completed: Developer wired creation to the existing `POST /tasks/orchestrations` contract, selected the new run after creation, and refreshed the orchestration console without introducing backend scope.
- Completed: QA extended UI static contract tests for the create form, task JSON parsing, POST endpoint, DoD evidence, shared-memory tags, and shared-memory policy payload fields.
- Completed: PM updated README, project status, planning, architecture, setup, and usage docs.

Feature tracking:
- Implemented in this slice: `/ui/` can create orchestration runs from a valid task-spec JSON array and immediately select the created run for inspection and execution controls.
- Still out of scope after this slice: guided task graph builders, templates, drag-and-drop dependencies, AI-assisted graph generation, and browser end-to-end creation scenario automation.

Validation:
- Focused UI static tests passed: `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010k Orchestration Recovery And Closeout Controls

Status: completed for the scoped orchestration mutation UX slice; Sprint 16 remains active for full chat workflows, orchestration creation UI, Codex-style AI-change diff review, richer settings editors, non-CLI execution UX, deeper sub-agent graph visualization, memory/tool reliability dashboards, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected orchestration recovery and closeout controls as the next user-facing Sprint 16 slice because task update, recovery, blocker resolution, and closeout backend contracts already exist.
- Completed: Developer added dashboard forms for running-task completion/failure/blocking, blocked-task recovery, manual/security blocker resolution, and required Definition of Done evidence closeout without adding backend endpoints.
- Completed: Developer matched backend governance by showing task recovery only for `role_boundary` and `retry_exhausted` blockers, showing manual blocker resolution only for `blocked` and `security` blockers, and sending an intentionally empty `declared_write_paths` list when cleared.
- Completed: QA extended UI static contract tests for the new handlers, endpoint wiring, blocker-severity gates, closeout evidence binding, and CSS hooks.
- Completed: QA added API coverage proving beta-owned tokens cannot update or close another owner's run, while extra spoof fields such as `agent_id` and `requested_by` are rejected by the existing schemas.
- Completed: PM updated README, project status, planning, architecture, setup, and usage docs.

Feature tracking:
- Implemented in this slice: `/ui/` orchestration detail can mark running tasks completed, failed, or blocked through the existing `PATCH /tasks/orchestrations/{run_id}/tasks/{task_id}` contract.
- Implemented in this slice: `/ui/` can submit blocked-task recovery and admin blocker-resolution requests through the existing recovery and blocker resolution contracts.
- Implemented in this slice: `/ui/` can submit required Definition of Done evidence to close a completed run, while the backend still enforces incomplete-task, unresolved-blocker, and evidence gates.
- Still out of scope after this slice: orchestration creation forms, graphical sub-agent hierarchy visualization, non-CLI approved action execution flows, and end-to-end browser automation for recovery/closeout scenarios.

Validation:
- Focused UI/API tests passed: `uv run pytest tests\test_ui.py tests\test_api.py::test_orchestration_api_task_update_and_close_respect_owner_and_payload_schema -q` with 4 tests.
- Full regression passed: `uv run pytest -q` with 1,329 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010j Sub-Agent Detail In Orchestration Console

Status: completed for the scoped per-task sub-agent detail slice; Sprint 16 remains active for full chat workflows, orchestration creation/update/recovery/closeout UI, Codex-style AI-change diff review, richer settings editors, non-CLI execution UX, deeper sub-agent graph visualization, memory/tool reliability dashboards, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected richer sub-agent detail as the next compact user-facing Sprint 16 slice after BL-010i, keeping deeper backend Git expansion deferred rather than cancelled.
- Completed: Explorer confirmed existing backend contracts already expose `/agents`, `/agents/{agent_id}`, child-agent reads, and `AgentBrief` fields needed for dashboard detail.
- Completed: Developer joined orchestration task cards to visible `/agents` records and added expandable per-task agent briefs for role, status, parent, task id, timestamps, expected output, required data, and bounded context.
- Completed: Developer preserved fail-soft behavior when the current token lacks the `agents` capability or agent records are unavailable.
- Completed: QA extended UI static contract tests for `/agents` loading, list-shape guarding, `renderTaskAgentBrief`, and agent-brief CSS hooks.
- Completed: PM updated README, project status, planning, architecture, setup, and usage docs.

Feature tracking:
- Implemented in this slice: `/ui/` orchestration detail now shows expandable agent brief panels below task cards when a task has `agent_id` and the dashboard can read the corresponding visible agent record.
- Implemented in this slice: the dashboard still renders task/execution detail when `/agents` is unavailable and shows a scoped unavailable message instead of failing the orchestration panel.
- Still out of scope after this slice: graphical sub-agent hierarchy visualization, dedicated agent child tree navigation, task recovery/closeout forms, and API-backed browser scenario tests for capability-degraded agent detail.

Validation:
- Focused UI static tests passed: `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,328 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.

### Sprint 16 BL-010i Approval Source And Status Filtering

Status: completed for the scoped approval dashboard filtering slice; Sprint 16 remains active for non-CLI execution UX, reviewer audit affordances, full chat workflows, Codex-style AI-change diff review, richer settings editors, deeper sub-agent visualization, memory/tool reliability dashboards, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM selected richer approval filtering as the next compact user-facing Sprint 16 slice after BL-010h was committed and pushed.
- Completed: Developer added source filtering for CLI, filesystem, network, provider, and tool approvals plus status filtering for pending, approved, denied, executed, and all approval states without changing backend approval contracts.
- Completed: Developer added a filtered summary grid and clears stale review detail when filters change so operators do not accidentally review an item outside the current filter context.
- Completed: QA extended UI static contract tests for the new filter controls, summary renderer, approval scope metric, and CSS hooks.

Feature tracking:
- Implemented in this slice: `/ui/` approval inbox can narrow loaded approval endpoints by source and status, update the approval metric scope, and show loaded/error/breakdown counts for the current filter.
- Still out of scope after this slice: non-CLI approved action execution flows, richer reviewer audit affordances, approval scenario browser automation, and backend approval-contract expansion.

Validation:
- Focused UI static tests passed: `uv run pytest tests\test_ui.py -q` with 3 tests.
- Full regression passed: `uv run pytest -q` with 1,328 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live local UI asset smoke passed against a temporary FastAPI server on `127.0.0.1:8024`: `/ui/` exposed `approvalSourceInput` and `/ui/app.js` exposed `renderApprovalSummary`.

### Sprint 16 BL-010h Richer Orchestration Console

Status: completed for the scoped dashboard orchestration task/execution visibility slice; Sprint 16 remains active for full chat workflows, Codex-style AI-change diff review, richer settings editors, richer approval filtering/non-CLI execution UX, deeper sub-agent visualization, memory/tool reliability dashboards, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM reassessed the Sprint 16 backlog after BL-010g and used a read-only explorer pass to select richer task/orchestration UI as the highest-value feasible next user-facing slice because backend orchestration contracts already exist.
- Completed: Developer expanded the `/ui/` orchestration panel from summary-only status into an inspectable console with run selection, task graph/status counts, open blockers, follow-ups, execution records, and cycle/loop/background start/cancel controls.
- Completed: QA extended UI static contract tests for the orchestration detail container, action helpers, orchestration execution API calls, and responsive styling hooks.
- Completed: PM preserved true AI diff accept/reject review, richer Git approval UI, editable settings/policy surfaces, and deeper backend Git expansion as remaining backlog rather than cancelled scope.

Feature tracking:
- Implemented in this slice: `/ui/` now displays task status counts, scheduled task ids, required Definition of Done evidence, task role/agent/retry/dependency/write-path detail, open blockers, follow-ups, and recent background execution records for the selected orchestration run.
- Implemented in this slice: `/ui/` can call existing orchestration `cycle`, bounded `loop`, background execution start, and background execution cancel endpoints without introducing new backend mutation contracts.
- Still out of scope after this slice: orchestration creation through a structured UI form, task update/recovery/closeout controls, full chat transcript UX, native AI change accept/reject APIs, richer approval filtering, and end-to-end browser automation across multiple viewport sizes.

Validation:
- Focused UI static tests passed: `uv run pytest tests\test_ui.py -q` with 3 tests.
- Focused orchestration regression passed: `uv run pytest tests/test_orchestration.py tests/test_api.py::test_orchestration_api_cycle_respects_authenticated_task_owner -q` with 115 tests.
- Full regression passed: `uv run pytest -q` with 1,328 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live local UI/API smoke passed against a temporary FastAPI server on `127.0.0.1:8023`: `/ui/` and `/ui/app.js` returned 200, a temporary orchestration run was created, operations summary reported the run, and execution listing returned successfully. A first smoke attempt using PowerShell `Invoke-WebRequest` hit a local null-reference while fetching `/ui/`; the app assertion was retried with `curl.exe` and passed.

### Sprint 16 BL-010g Safe Project Activation And Root Switching

Status: completed for the scoped safe registered-project activation slice; Sprint 16 remains active for AI-change review, richer chat/task execution, editable policy/settings surfaces, memory/tool reliability dashboards, richer approval filtering/non-CLI execution UX, persistent or multi-worker project activation semantics, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: Architect kept the activation contract in-process and conservative, with DGentic JSON/SQLite state pinned to its pre-switch absolute data directory.
- Completed: Developer added runtime settings overrides, activation preflight and activate routes, active CLI/orchestration/approval blocker checks, a project-activation event, database cache reset after root switch, a root-switch HTTP request barrier for the local FastAPI process, and dashboard Open controls.
- Completed: QA added focused activation happy-path, anchored-state, old-root filesystem visibility, unexecuted approval blocker, active CLI run blocker, running orchestration task blocker, invalid root/archive handling, auth mapping, and UI wiring tests.
- Completed: Reviewer/Security confirmed activation is admin-gated, keeps existing rootDir filesystem checks intact, blocks stale approval/run/task state before switching, and records remaining scope as follow-up rather than silently widening it.

Feature tracking:
- Implemented in this slice: `POST /projects/{project_id}/activation/preflight` reports machine-readable checks, blockers, warnings, and whether a registered project can be opened safely.
- Implemented in this slice: `POST /projects/{project_id}/activate` switches the active runtime `root_dir` only for registered available project roots that still resolve to absolute existing non-symlink directories outside DGentic state.
- Implemented in this slice: relative `DGENTIC_DATA_DIR` is pinned to its current absolute path before switching so project registry, approvals, events, and SQLite state do not silently move under the newly opened project.
- Implemented in this slice: switching is blocked while CLI runs are starting/running, orchestration background executions are active, orchestration tasks are running, or CLI/filesystem/network/provider/tool approvals are pending or approved but not executed.
- Implemented in this slice: `/ui/` project records now show Open/Active controls, clear stale editor state after opening a project, reload settings/workspace/logs/projects, and render activation blockers plus warnings.
- Still out of scope after this slice: persisted restart-stable active project selection, multi-worker distributed activation locks, project-scoped state migration, non-CLI approval execution UX, and AI-change diff review.

Validation:
- Focused project/UI tests passed: `uv run pytest tests\test_projects.py tests\test_ui.py -q` with 12 tests.
- Focused auth mapping passed: `uv run pytest tests\test_auth.py -q` with 134 tests.
- Broader API/UI/auth regression passed: `uv run pytest tests\test_projects.py tests\test_ui.py tests\test_auth.py tests\test_api.py -q` with 356 tests.
- Broader CLI/orchestration regression passed: `uv run pytest tests\test_cli_runtime.py tests\test_orchestration.py -q` with 203 passed and 2 skipped.
- Full regression passed: `uv run pytest -q` with 1,328 passed and 2 skipped.
- Lint/static checks passed: `uv run ruff format --check .`, `uv run ruff check .`, `node --check src\dgentic\ui\app.js`, and `git diff --check`.
- Live local UI/API smoke passed against a temporary FastAPI server on `127.0.0.1:8022`: `/ui/` and `/ui/app.js` returned 200, project preflight/register/activate succeeded, effective `root_dir` switched to the registered project, and guarded filesystem listing showed the new project-only file without the old-root file.

### Sprint 16 BL-010f Project Registry And Root Preflight

Status: completed for the scoped project registry and root preflight slice; Sprint 16 remains active for true active-root switching, AI-change review, richer chat/task execution, editable policy/settings surfaces, memory/tool reliability dashboards, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: Architect selected a safe backend-only registry/preflight contract first because runtime `rootDir` switching affects filesystem, CLI, git, plugin, tool, approval, and persistence boundaries.
- Completed: Developer added admin-gated `/projects` preflight, register, list, detail, update, and active-root metadata endpoints, plus dashboard controls that preview/register project roots without activating them.
- Completed: QA added focused project registry, auth mapping, no-active-switch, and UI static wiring tests.
- Completed: Security/Reviewer confirmed this slice does not clear settings, reset database state, switch active `rootDir`, or weaken existing filesystem root checks.

Feature tracking:
- Implemented in this slice: project roots can be preflighted only when they are absolute existing directories, not symlink roots, and not inside the current DGentic data directory.
- Implemented in this slice: registered project records persist to `projects.json` with safe ids, redacted names, canonical root paths, marker summaries, status, timestamps, and active-root matching metadata.
- Implemented in this slice: `/ui/` can list registered projects, preview a root, add a root, and show that switching is not yet available.
- Still out of scope after this slice: runtime project activation, root switching transactions, stale approval invalidation, active CLI/orchestration quiescence checks, project-scoped state migration, and old-root editor/save invalidation.

Validation:
- Focused project tests passed: `python -m pytest -q tests\test_projects.py --maxfail=1 -x` with 4 tests.
- Focused UI tests passed: `python -m pytest -q tests\test_ui.py --maxfail=1 -x` with 3 tests.
- Focused auth mapping passed: `python -m pytest -q tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes --maxfail=1 -x` with 54 parameter cases.
- Focused lint/format/diff hygiene passed for touched source and tests, plus `node --check src\dgentic\ui\app.js` and `git diff --check`.
- Browser smoke passed with Edge/Playwright against `http://127.0.0.1:8021/ui/`: no page errors, no failed API responses, active root rendered as `C:\workspace\AI Agent`, project registry showed runtime root, and project preflight returned marker and no-switch warning output.

### Sprint 16 BL-010e Project Context And Git Checkpoint Review UI

Status: completed for the scoped active-root context and structured Git checkpoint review slice; Sprint 16 remains active for true project add/open and rootDir switching, AI-change review, richer chat/task execution, editable policy/settings surfaces, memory/tool reliability dashboards, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: Architect confirmed there is no first-class project/rootDir switching backend contract yet; the current safe boundary is the backend's configured `DGENTIC_ROOT_DIR`.
- Completed: Developer added active project/root context visibility to `/ui/` using the existing effective settings endpoint, plus root-reset workspace controls and a structured Git checkpoint review renderer.
- Completed: QA updated UI static tests for the new project context and Git checkpoint review wiring.
- Completed: PM updated README, architecture, setup, usage, backlog, project status, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` displays the active workspace root, root setting source, state directory, environment, auth state, and managed-settings indicator from `GET /settings/effective`.
- Implemented in this slice: the workspace panel can reset browsing to `.` from both the project context and workspace controls without changing backend state.
- Implemented in this slice: the Git checkpoint panel now renders branch, head, upstream, ahead/behind counts, staged/unstaged/untracked counts, diff-stat summary, blockers, warnings, changed paths, and a collapsible raw checkpoint payload.
- Still out of scope after this slice: project registry APIs, browser-side add/open/switch controls that mutate active `rootDir`, project-scoped state semantics, stale approval invalidation across project switches, and AI-change diff review.

Validation:
- Focused UI tests passed: `python -m pytest -q tests\test_ui.py --maxfail=1 -x` with 3 tests.
- Lint/format/diff hygiene passed: `python -m ruff check .`, `python -m ruff format --check .`, `git diff --check`, and `node --check src\dgentic\ui\app.js`.
- Browser smoke passed with Edge/Playwright against `http://127.0.0.1:8021/ui/`: no page errors, no failed API responses, active root rendered as `C:\workspace\AI Agent`, workspace root listed 17 rows, and Git checkpoint rendered the structured grid.

### Sprint 16 BL-010d Read-Only Policy And Plugin Visibility

Status: completed for the scoped read-only policy/plugin visibility slice; Sprint 16 remains active for editable settings/policy surfaces, project add/open and rootDir switching, AI-change review, richer approval filtering, memory/tool reliability dashboards, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: Developer added a Policy dashboard section for CLI policy rules, command recipes, hook policy rules, and plugin trust/discovery state.
- Completed: QA expanded UI static tests to assert read-only policy/plugin endpoint wiring and stylesheet coverage.
- Completed: PM updated README, architecture, setup, usage, backlog, project status, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` reads `GET /cli/policy/rules`, `GET /cli/recipes`, `GET /guardrails/hooks/rules`, and `GET /plugins` and renders bounded record summaries.
- Implemented in this slice: the policy section is read-only and does not add mutation controls, preserving existing backend capability gates and managed policy lock behavior.
- Still out of scope after this slice: editable policy/settings forms, plugin component install/disable controls, command recipe preview/execute UX, richer filtering/search, and end-to-end browser policy scenario tests.

Validation:
- Focused UI tests passed: `python -m pytest -q tests\test_ui.py --maxfail=1 -x` with 3 tests.
- Focused lint/format/diff hygiene passed: `python -m ruff check tests\test_ui.py src\dgentic\main.py`, `python -m ruff format --check tests\test_ui.py src\dgentic\main.py`, and `git diff --check`.
- Browser smoke passed in the Codex in-app browser against `http://127.0.0.1:8020/ui/`: policy section, CLI rules, and plugins panels rendered, and console error count was 0.
- Full lint/format/regression gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `python -m pytest -q --maxfail=1 -x` with 1,314 tests and 2 skipped.

### Sprint 16 BL-010c CLI Approval Execution And Run Output UI

Status: completed for the scoped CLI approval execution and run output visibility slice; Sprint 16 remains active for richer approval filtering, non-CLI execution UX, project add/open and rootDir switching, AI-change review, policy/settings editors, plugin and command-recipe views, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: Developer added a CLI Runs dashboard panel with recent run listing and output chunk polling through `GET /cli/runs` and `GET /cli/runs/{run_id}/output`.
- Completed: Developer added an execute action for already approved CLI approvals when the safe review contract does not require a separate bound execution request, using `POST /cli/approvals/{approval_id}/execute`.
- Completed: QA expanded UI static tests to assert approved CLI execution and CLI run output endpoint wiring.
- Completed: PM updated README, architecture, setup, usage, backlog, project status, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` lists recent CLI runs, shows run status/exit metadata, and renders redacted chunked stdout/stderr output from the backend output polling endpoint.
- Implemented in this slice: approved CLI approval reviews show an execute button only for CLI approvals with `status: approved`, and the button is disabled when `direct_execute_available` is false.
- Implemented in this slice: execution still goes through existing backend `cli` capability checks, cross-actor rules, workflow revalidation, and approval claim protections.
- Still out of scope after this slice: non-CLI direct execution UX, environment-bound execution request forms, richer run filtering/search, live output auto-refresh, and end-to-end browser approval scenario tests.

Validation:
- Focused UI tests passed: `python -m pytest -q tests\test_ui.py --maxfail=1 -x` with 3 tests.
- Focused lint/format/diff hygiene passed: `python -m ruff check tests\test_ui.py src\dgentic\main.py`, `python -m ruff format --check tests\test_ui.py src\dgentic\main.py`, and `git diff --check`.
- Browser smoke passed in the Codex in-app browser against `http://127.0.0.1:8020/ui/`: CLI Runs panel rendered and console error count was 0.
- Full lint/format/regression gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `python -m pytest -q --maxfail=1 -x` with 1,314 tests and 2 skipped.

### Sprint 16 BL-010b Current-Root Workspace Browser And Editor

Status: completed for the scoped current-root workspace UI slice; Sprint 16 remains active for project add/open and rootDir switching, AI-change diff review, richer task/chat execution, policy/settings editors, plugin and command-recipe views, direct approved-action execution UX, and broader browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: Architect confirmed the existing filesystem API contracts for list, read, and write against the configured backend `rootDir`.
- Completed: Developer added a workspace panel to `/ui/` with path navigation, parent navigation, directory listing, text-file opening, and text-file saving through existing guarded filesystem APIs.
- Completed: QA expanded UI static tests to assert filesystem endpoint wiring, bearer-token header wiring, and no browser-side `rootDir` switching field.
- Completed: PM updated README, architecture, setup, usage, backlog, project status, and this progress log.

Feature tracking:
- Implemented in this slice: `/ui/` can list directories with `POST /filesystem/list`, open text files with `POST /filesystem/read`, and save text files with `POST /filesystem/write`.
- Implemented in this slice: workspace requests rely on the same bearer-token session header logic as the rest of the dashboard and therefore preserve existing `filesystem` capability gates when auth is enabled.
- Implemented in this slice: the UI works against the backend's configured `DGENTIC_ROOT_DIR` only; rootDir/project switching is intentionally deferred to a dedicated backend contract.
- Still out of scope after this slice: project add/open, active rootDir switching, binary editing, diff/change review, approval-id entry for approval-required filesystem hooks, and Monaco-style editor integration.

Validation:
- Focused UI tests passed: `python -m pytest -q tests\test_ui.py --maxfail=1 -x` with 3 tests.
- Focused lint/format/diff hygiene passed: `python -m ruff check tests\test_ui.py src\dgentic\main.py`, `python -m ruff format --check tests\test_ui.py src\dgentic\main.py`, and `git diff --check`.
- Browser smoke passed in the Codex in-app browser against `http://127.0.0.1:8020/ui/`: workspace controls rendered, the current repository listed 17 file rows including `README.md`, and console error count was 0.
- Full lint/format/regression gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `python -m pytest -q --maxfail=1 -x` with 1,314 tests and 2 skipped.

### Sprint 16 BL-010a Same-Origin Web Dashboard Shell

Status: completed for the scoped first Sprint 16 dashboard slice; Sprint 16 remains active for richer chat/task execution workflows, sub-agent progress detail, policy/settings editors, plugin and command-recipe views, memory/tool reliability dashboards, direct approved-action execution UX, and broader responsive/browser validation.

Current story:
- BL-010: Cross-Platform Web UI, Dashboard, And Interactive Approval Experience.

Checklist:
- Completed: PM confirmed Sprint 15 is closed at the BL-009av safe backend security checkpoint, preserving remaining Sprint 15 backend security and Git expansion items as deferred follow-ups rather than cancelled scope.
- Completed: Architect mapped existing FastAPI contracts for auth, health, task planning, orchestration, approvals, logs, settings, providers/tools, memory, and Git workflow checkpoints.
- Completed: QA mapped the Python-only test strategy and confirmed no existing frontend toolchain was present.
- Completed: Developer added a same-origin static `/ui/` dashboard mount to the FastAPI app and implemented the first dashboard shell under `src/dgentic/ui/`.
- Completed: QA added focused `/ui/` static-serving and auth-boundary tests.
- Completed: PM updated README, architecture, setup, usage, backlog, project status, and this progress log.

Feature tracking:
- Implemented in this slice: `GET /ui/` serves a static browser dashboard from the FastAPI process without introducing a separate frontend build chain.
- Implemented in this slice: the dashboard includes bearer-token session entry, runtime health metrics, task plan creation, task/run history, orchestration operations summary, provider/tool summaries, effective settings, event log polling, and a Git workflow checkpoint panel.
- Implemented in this slice: the unified approval inbox loads CLI, filesystem, network, provider, and tool approval queues, opens the existing safe review endpoints, and submits approve or deny decisions through the existing backend approval APIs.
- Implemented in this slice: the dashboard shell is public so operators can load it in production, while protected API data and actions still require the existing bearer-token capability gates.
- Still out of scope after this slice: direct approved-action execution buttons, richer filtering and detail views, editable settings/policy surfaces, plugin/command-recipe/hook-policy dashboards, memory/tool reliability drilldowns, full chat UI, VS Code extension, dedicated CLI client, and broad cross-browser/mobile regression coverage.

Validation:
- Focused UI static-serving and auth-boundary tests passed: `python -m pytest -q tests\test_ui.py --maxfail=1 -x` with 3 tests.
- Focused UI/API smoke passed: `python -m pytest -q tests\test_ui.py tests\test_api.py -k "health or task_plan or logs or effective_settings" --maxfail=1 -x` with 14 tests and 199 deselected.
- Browser smoke passed in the Codex in-app browser against `http://127.0.0.1:8020/ui/`: dashboard title and main controls rendered, the approval inbox was present, and console error count was 0.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,314 tests and 2 skipped.

### Documentation Source-Of-Truth Cleanup

Status: completed for the scoped documentation navigation cleanup. Planned features were not removed or downsized.

Completed:
- Added `docs/project-status.md` as the PM control panel for the active sprint, priority order, safe Git stopping rule, remaining Sprint 15 follow-ups, Sprint 15 through Sprint 19 placement, and source-of-truth links.
- Updated the documentation index with a Start Here section and explicit source-of-truth rules.
- Added the project-status link to the root README documentation list.
- Preserved the backlog as the roadmap source of truth, including the Sprint 15 through Sprint 19 plan and Git workflow timeline.

Validation:
- `git diff --check` passed with no whitespace errors.
- Verified the Sprint 15 through Sprint 19 references and Git workflow timeline remain present in the docs.

### Chat Interface Documentation Clarification

Status: completed for the scoped documentation wording fix.

Completed:
- Clarified that the human-facing chat/web UI is not implemented yet and remains planned for Sprint 16.
- Clarified that current backend MVP task submission is through the HTTP API, with dedicated CLI and VS Code clients planned for Sprint 17.
- Preserved the chat interface as a planned feature rather than removing it from the roadmap.

### Sprint 16 Project Workspace UI Requirement

Status: added to the Sprint 16 roadmap.

Completed:
- Added project/workspace management to the chat interface scope, including adding a project or opening an existing folder as the active `rootDir`.
- Added project file explorer, in-browser code editor, and Codex-style AI-change diff/review requirements to BL-010 and Story 8.1.
- Preserved the existing BL-010a dashboard shell scope while making the richer project workspace UI the next Sprint 16 direction.

### Sprint 17 VS Code Chat Integration Requirement

Status: added to the Sprint 17 roadmap.

Completed:
- Clarified that the VS Code extension needs its own DGentic chat surface for task submission, status, approvals, logs, and follow-up instructions.
- Clarified that VS Code should not duplicate the web UI file explorer/code editor; it should integrate with native workspace folders, Explorer, editor, and diff review.
- Added native VS Code AI-change review requirements so proposed file edits can be inspected before acceptance or rejection.

## 2026-05-13

### Sprint 15 BL-009av Managed Network-Domain Policy Rule Records

Status: completed for the scoped managed network-domain policy rule record slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, additional secret-manager adapters beyond HashiCorp Vault KV v2, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, and broader managed policy-source controls beyond credential/CLI/hook/network/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM resumed Sprint 15 after BL-009au, pulled latest `origin/main`, confirmed role-boundary governance, and selected Full Sprint mode because managed network policy affects provider, web retrieval, generated-tool, and credential secret-manager egress.
- Completed: Security/Reviewer scout identified the safe slice as `managed_network_domain_policy_rules`, with managed-only loading, stable ids, strict validation, managed-before-local precedence, safe decision metadata, canonical policy drift binding, sanitized generated-tool handoff, and generic network guardrail response redaction.
- Completed: Developer added managed network-domain record parsing, effective policy merging, safe matched-rule source/id decision metadata, canonical effective network-policy revision digests for approval binding, generated-tool managed-rule handoff, and generic `/guardrails/network` URL/reason redaction.
- Completed: QA added managed-settings, network approval drift, provider runtime, generated-tool subprocess, and API redaction coverage.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `managed_network_domain_policy_rules` is honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, supports stable `id`, exact/wildcard `domain`, `mode`, optional non-secret `reason`, `enabled`, and `priority`, sorts exact domains ahead of wildcard rules at equal priority, and fails closed for malformed records, unknown fields, duplicate ids/domains, invalid domains or modes, invalid priorities/enabled flags, too many records, and secret-shaped text.
- Implemented in this slice: managed network rules evaluate before local/environment `network_domain_policy.rules`; unmatched hosts still fall through to existing local rules and default mode.
- Implemented in this slice: network decisions now expose safe `matched_rule_id` and `matched_rule_source` metadata, and network approval policy digests bind the canonical effective policy revision plus matched rule metadata so rule identity/mode/domain/reason/priority/enabled changes stale existing approvals.
- Implemented in this slice: generated-tool subprocess network policy handoff now includes managed-only policies, but still sends only default mode, domain/mode rules, and approved endpoints, with no managed ids, reasons, settings paths, or approval digests.
- Implemented in this slice: generic `/guardrails/network` responses now mirror web retrieval response safety by returning a sanitized URL preview and redacted reason text.
- Still out of scope after this slice: OS-level/non-Python egress isolation, mutable network policy APIs, and broader policy-source records for future executable plugin loading surfaces.

Validation:
- Focused managed network policy gate passed: `python -m pytest -q tests\test_managed_settings.py tests\test_network_policy.py -k "managed_network_domain_policy_rules or managed_network or network_domain_policy or network_policy" --maxfail=1 -x` with 27 tests and 82 deselected.
- Focused provider/tool/API managed network gate passed: `python -m pytest -q tests\test_provider_runtime.py tests\test_tool_runtime.py tests\test_api.py -k "managed_network_policy or guardrails_network_returns_policy_decision or network_domain_policy" --maxfail=1 -x` with 12 tests and 391 deselected.
- Affected suite gate passed: `python -m pytest -q tests\test_managed_settings.py tests\test_network_policy.py tests\test_provider_runtime.py tests\test_tool_runtime.py tests\test_api.py --maxfail=1 -x` with 512 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,311 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009au HashiCorp Vault KV Credential Adapter

Status: completed for the scoped HashiCorp Vault KV v2 credential adapter slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, additional secret-manager adapters beyond HashiCorp Vault KV v2, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, and broader managed policy-source controls beyond credential/CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM resumed Sprint 15 after BL-009at and selected Full Sprint mode because credential resolution and secret-manager egress are security-sensitive.
- Completed: Architect/Security scoped one first-class adapter for HashiCorp Vault KV v2 over HTTP, with metadata-only references, explicit base URL allowlists, network-policy checks, no redirects/proxies, no inherited token persistence, and no executable plugin/SDK loading.
- Completed: Developer added `secret_manager` credential references, `credential_secret_manager_adapters`, `credential_secret_manager_allowed_base_urls`, Vault KV v2 URL construction, bounded Vault response parsing, sanitized environment token lookup, and provider/runtime credential identity support.
- Completed: Security review found and Developer fixed three pre-commit issues: Vault egress now requires exact allowed base URLs plus deny/approval-required network-policy blocking before token lookup, secret-manager token lookup honors the caller-supplied sanitized environment mapping, and Vault mount/secret paths reject `.`/`..`/empty segments plus secret-shaped metadata.
- Completed: QA added managed-settings, credential API, and provider runtime coverage for local and managed secret-manager reference metadata, fail-closed adapter/reference validation, Vault request URL/header behavior, no raw token/secret persistence, provider approval preservation on credential failure, and policy-restricted Vault egress before token lookup.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `source_type: "secret_manager"` credential references persist only adapter id and safe secret-name metadata for local and deployment-managed records.
- Implemented in this slice: `credential_secret_manager_adapters` supports `hashicorp_vault_kv2` adapters with safe HTTPS/localhost base URLs, safe mount/field/token-env metadata, bounded timeouts, and bounded response size.
- Implemented in this slice: `credential_secret_manager_allowed_base_urls` must include the exact normalized Vault base URL before a Vault adapter can be used.
- Implemented in this slice: Vault KV v2 resolution happens at provider/runtime transport time, reads the Vault token only from the configured environment variable, calls `/v1/[mount]/data/[secret_name]`, expects `{"data":{"data":{"field":"secret"}}}`, rejects invalid or unsafe secret values, and never stores the Vault token or resolved secret in credential state, provider approvals, API responses, or audit events.
- Implemented in this slice: Vault HTTP transport blocks redirects, disables proxies, and fails closed when network policy denies or requires approval for the Vault host because credential resolution has no network approval context.
- Still out of scope after this slice: managed KMS custody, Vault token lifecycle management, Vault namespaces/enterprise features, cloud secret-manager adapters beyond HashiCorp Vault KV v2, OS-level egress isolation, and UI/CLI/VS Code client flows.

Validation:
- Focused secret-manager managed-settings gate passed: `python -m pytest tests\test_managed_settings.py -q -k "secret_manager or managed_credential_reference_records_fail_closed" --maxfail=1 -x` with 27 tests and 55 deselected.
- Focused secret-manager auth/API gate passed: `python -m pytest tests\test_auth.py -q -k "secret_manager_credential_reference" --maxfail=1 -x` with 1 test and 128 deselected.
- Focused secret-manager provider runtime gate passed: `python -m pytest tests\test_provider_runtime.py -q -k "secret_manager_credential" --maxfail=1 -x` with 8 tests and 125 deselected.
- Combined credential/settings/provider gate passed: `python -m pytest tests\test_managed_settings.py tests\test_auth.py tests\test_provider_runtime.py -q -k "secret_manager or credential_reference or managed_settings" --maxfail=1 -x` with 108 tests and 236 deselected.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Affected suite gate passed: `python -m pytest -q tests\test_managed_settings.py tests\test_auth.py tests\test_provider_runtime.py tests\test_api.py --maxfail=1 -x` with 554 tests.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,294 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009at Direct Git PR Runner

Status: completed for the scoped direct GitHub PR creation runner slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, and broader managed policy-source controls beyond credential/CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM resumed the active Sprint 15 git workflow automation lane, pulled latest from `origin/main`, confirmed role-boundary governance, and selected Full Sprint mode because direct PR creation is a public API path with networked GitHub CLI side effects.
- Completed: Architect/Security scoped the runner to direct PR creation only: fresh ready PR checkpoint digest, already-pushed/current-with-upstream branch, checkpoint-derived head branch, bounded PR title/body/base inputs, explicit GitHub CLI token environment, isolated `gh` config, strict safe PR URL extraction, no caller-supplied remote/head/flags/templates/reviewers, no raw command output, and no CLI approval creation.
- Completed: Developer added `GitPrRunRequest`, `GitPrRunResult`, `run_git_pr_workflow`, strict upstream-host-bound PR URL extraction, explicit token/isolated `GH_CONFIG_DIR` handling, safe PR-run audit metadata, and `POST /cli/git/pr-runs` under the existing `cli` capability mapping.
- Completed: Security review found and Developer fixed two medium issues before validation: PR URL extraction now requires a strict `/owner/repo/pull/<number>` URL from the checkpointed upstream host, and direct `gh` execution now requires explicit token env instead of ambient GitHub CLI login state.
- Completed: QA added direct PR runner coverage for success with exact fake `gh` argv, isolated `gh` environment, token-required rejection, stale digest rejection, dirty worktree rejection, no-upstream/unpushed/behind rejection, arbitrary payload rejection, secret-shaped and multiline PR text rejection, unrelated-host PR URL suppression, and auth/capability principal binding.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/pr-runs` re-runs a PR checkpoint and only invokes `gh pr create` when the supplied `checkpoint_digest` still matches a fresh ready PR checkpoint.
- Implemented in this slice: direct PR execution requires the branch to have a configured upstream remote URL digest, be pushed, and be current with upstream before `gh` is invoked.
- Implemented in this slice: direct PR execution uses shell-free argv `gh pr create --title ... --body ... --head [checkpoint-branch]` with optional `--base` and `--draft`; the request does not accept caller-supplied remote, head branch, arbitrary command, flags, labels, reviewers, projects, templates, or browser mode.
- Implemented in this slice: `gh` must resolve outside `rootDir`, receive an explicit GitHub token environment, run with `GH_PROMPT_DISABLED=1`, `NO_COLOR=1`, and a temporary isolated `GH_CONFIG_DIR`, and run without inherited `HOME`.
- Implemented in this slice: successful responses include repo/cwd, branch/upstream, remote name, remote URL digest, head SHA, checkpoint digest, title/body digests, head/base branch, draft flag, duration, requester/context metadata, and a sanitized PR URL only when exactly one safe URL from the checkpointed upstream host is emitted.
- Implemented in this slice: CLI audit metadata records safe PR-run facts plus title/body/URL digests without raw title, body, stdout, stderr, remote URLs, tokens, or approval records.
- Still out of scope after this slice: direct `gh` labels/reviewers/assignees/projects/templates, browser-based PR creation, remote fetch freshness checks beyond the local upstream tracking state, destructive branch cleanup, force operations, and UI/CLI/VS Code client flows.

Validation:
- Focused direct PR runner gate: `python -m pytest tests\test_git_workflows.py -q -k "pr_run" --maxfail=1 -x` passed with 9 tests and 41 deselected.
- Focused auth capability mapping gate: `python -m pytest tests\test_auth.py -q -k "capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution" --maxfail=1 -x` passed with 70 tests and 58 deselected.
- Combined git/auth gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py -q -k "git or capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution" --maxfail=1 -x` passed with 120 tests and 58 deselected.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Affected suite gate passed: `python -m pytest -q tests\test_git_workflows.py tests\test_auth.py tests\test_api.py --maxfail=1 -x` with 388 tests.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,267 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009as Direct Git Push Runner

Status: completed for the scoped direct configured-upstream git push runner slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond credential/CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks, and direct PR workflow runner beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected the direct configured-upstream push runner as the next bounded Sprint 15 git workflow automation slice after BL-009ar because push checkpoint and approval gates already provided upstream, ahead/behind, clean-worktree, protected-branch, and remote URL digest contracts.
- Completed: Architect/Security scoped the runner to `push` only, requiring a fresh ready push checkpoint digest, checkpoint-derived remote/refspec, no caller-supplied remote/refspec/flags, hook isolation, push GPG-signing disablement, no raw remote URL/output exposure, no approval creation, and no direct PR execution.
- Completed: Developer added `GitPushRunRequest`, `GitPushRunResult`, `run_git_push_workflow`, and `POST /cli/git/push-runs` under the existing `cli` capability mapping.
- Completed: QA added direct push runner coverage for success, stale digest rejection, dirty worktree rejection, no-upstream and no-ahead rejection, arbitrary remote/branch/flag payload rejection, secret-shaped remote URL non-exposure, pre-push hook isolation, and authenticated principal binding.
- Completed: Architect scout confirmed the direct push runner should derive the upstream target from the fresh checkpoint and leave direct PR execution out of scope.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/push-runs` re-runs a push checkpoint and only pushes when the supplied `checkpoint_digest` still matches a fresh ready push checkpoint.
- Implemented in this slice: direct push execution uses argv `git push --porcelain [remote] HEAD:refs/heads/[upstream-branch]`, where the remote and branch are derived from the checkpointed repository upstream.
- Implemented in this slice: the runner requires a clean non-protected branch, configured upstream remote URL digest, local commits ahead of upstream, and no remote-tracking commits behind.
- Implemented in this slice: successful responses include repo/cwd, branch/upstream, remote name, remote URL digest, head SHA, checkpoint digest, ahead/behind before/after, duration, requester/context metadata, and no raw remote URL or command output.
- Implemented in this slice: CLI audit metadata records safe push-run facts without raw remote URLs, stdout, stderr, caller refspecs, or approval records.
- Still out of scope after this slice: direct `gh pr create`, remote ref freshness checks that require a separate fetch, destructive branch cleanup, force operations, and UI/CLI/VS Code client flows.

Validation:
- Focused direct push runner gate: `python -m pytest tests\test_git_workflows.py -q -k "push_run" --maxfail=1 -x` passed with 8 tests and 33 deselected.
- Focused auth capability mapping gate: `python -m pytest tests\test_auth.py -q -k "capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution" --maxfail=1 -x` passed with 68 tests and 58 deselected.
- Combined git/auth gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py -q -k "git or capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution" --maxfail=1 -x` passed with 109 tests and 58 deselected.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Affected suite gate passed: `python -m pytest -q tests\test_git_workflows.py tests\test_auth.py tests\test_api.py --maxfail=1 -x` with 377 tests.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,256 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009ar Direct Git Commit Runner

Status: completed for the scoped direct local git commit runner slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond credential/CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks, and direct push/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected a direct local commit runner as the next bounded Sprint 15 git workflow automation slice after BL-009aq because the checkpoint/approval foundation already provided a safe readiness contract and local commit execution is lower risk than direct push or PR operations.
- Completed: Architect/Security scoped the runner to `commit` only, requiring a fresh ready checkpoint digest, a bounded single-line non-secret commit message, shell-free `git commit -m ...`, repository hook isolation, GPG-signing disablement, no push/PR execution, no approval creation, and safe audit metadata without raw commit messages or command output.
- Completed: Developer added `GitCommitRunRequest`, `GitCommitRunResult`, `run_git_commit_workflow`, and `POST /cli/git/commit-runs` under the existing `cli` capability mapping.
- Completed: QA added direct commit runner coverage for success, stale digest rejection, non-ready checkpoint rejection, protected-file and secret-shaped staged-addition blocking, secret-shaped and multiline commit-message rejection, hook isolation, no raw commit-message audit exposure, and authenticated principal binding.
- Completed: Reviewer scout found no blocking issues; Dev removed unused response output fields and QA added endpoint-specific commit-message rejection coverage for the two P3 follow-ups.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/commit-runs` re-runs a commit checkpoint and only commits when the supplied `checkpoint_digest` still matches a fresh ready commit checkpoint.
- Implemented in this slice: direct commit execution uses an argv `git commit -m ...` invocation with optional locks/prompts disabled, an empty temporary hooks path, and `commit.gpgsign=false`.
- Implemented in this slice: successful responses include action, repo/cwd, branch, head-before/head-after, checkpoint digest, commit-message digest, duration, requester/context metadata, and no raw stdout/stderr payload.
- Implemented in this slice: CLI audit metadata records safe commit-run facts and commit-message digests without storing the raw commit message or command output, and the runner does not create a CLI approval record.
- Still out of scope after this slice: direct `git push`, direct `gh pr create`, remote ref freshness checks that require network I/O, destructive branch cleanup, force operations, and UI/CLI/VS Code client flows.

Validation:
- Focused direct commit runner gate: `python -m pytest tests\test_git_workflows.py -q -k "commit_run" --maxfail=1 -x` passed with 7 tests and 26 deselected.
- Focused auth capability mapping gate: `python -m pytest tests\test_auth.py -q -k "capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution" --maxfail=1 -x` passed with 66 tests and 58 deselected.
- Combined git/auth gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py -q -k "git or capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution" --maxfail=1 -x` passed with 99 tests and 58 deselected.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Affected suite gate passed: `python -m pytest -q tests\test_git_workflows.py tests\test_auth.py tests\test_api.py --maxfail=1 -x` with 367 tests.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,246 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009aq Managed Credential Reference Records

Status: completed for the scoped managed credential reference record slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond credential/CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected managed credential reference records after BL-009ap because deployment-owned credential metadata was the next bounded managed policy-source control that could improve provider/runtime secret governance without adding KMS or cloud SDK dependencies.
- Completed: Architect/Security scoped records as read-only settings-file data for `env` and `external_process` sources only, with fail-closed validation, no raw secret values, no local JSON persistence, managed-over-local overlay, and local spoof filtering.
- Completed: Developer added `managed_credential_references` settings parsing, redacted effective-settings reporting, source-attributed credential views, managed/local overlay and resolution, read-only managed revoke rejection, and provider runtime compatibility through existing credential-reference configuration.
- Completed: QA added managed-settings, auth/API, and provider-runtime coverage for managed-only loading, parser failures, source attribution, auth capability gates, no secret echo, local id collision shadowing, local managed-source spoof filtering, read-only mutation behavior, provider use, and no local persistence.
- Completed: Reviewer/Security validated that managed records do not add local-vault/KMS semantics, do not expose raw secret material, and do not let local JSON rows impersonate managed deployment records.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` can declare `managed_credential_references` with stable ids, `env` or `external_process` source metadata, purpose, status, and optional labels.
- Implemented in this slice: `GET /credentials/references` returns managed credential records with `source: "managed"` ahead of non-shadowed local records, while local rows that spoof managed source are ignored.
- Implemented in this slice: managed credential references can be resolved by provider/runtime credential flows, including `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF`, without writing the managed id or secret metadata to `credential-references.json`.
- Implemented in this slice: managed credential records are read-only through local credential mutation APIs; local records cannot shadow managed ids, and managed records cannot use `local_vault` ciphertext.
- Still out of scope after this slice: managed KMS/local-vault ciphertext ownership, first-class cloud secret-manager adapters beyond the process adapter bridge, per-record policy-source controls beyond current managed records, direct git/PR runners, OS-level egress isolation, and executable plugin loading.

Validation:
- Focused managed credential settings gate: `python -m pytest tests\test_managed_settings.py -q -k "managed_credential_reference"` passed with 10 tests and 54 deselected.
- Focused managed credential auth/API gate: `python -m pytest tests\test_auth.py -q -k "managed_credential_reference or credential_reference_list_returns_managed"` passed with 2 tests and 120 deselected.
- Focused managed credential provider gate: `python -m pytest tests\test_provider_runtime.py -q -k "managed_env_credential_reference or managed_external_process"` passed with 2 tests and 123 deselected.
- Combined credential/provider/settings gate: `python -m pytest tests\test_managed_settings.py tests\test_auth.py tests\test_provider_runtime.py -q -k "credential_reference or credential or managed_settings"` passed with 96 tests and 215 deselected.
- Affected suite gate passed: `python -m pytest -q tests\test_managed_settings.py tests\test_auth.py tests\test_provider_runtime.py tests\test_api.py --maxfail=1 -x` with 521 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,237 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009ap Guarded Web Retrieval Fetch Runtime

Status: completed for the scoped guarded web retrieval fetch runtime slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected guarded web retrieval fetch runtime after BL-009ao because the transport-free `web_retrieval`/`fetch` guard contract already existed and the missing runtime was now a concrete bounded security gap.
- Completed: Architect/Security scoped the runtime to a single `POST /web-retrieval/fetch` endpoint with explicit host policy requirements, GET-only transport, no redirects, no caller headers/cookies/proxies, text-like content only, bounded/truncated responses, and existing single-use network approval binding.
- Completed: Developer added web retrieval timeout/byte-cap settings, fetch request/response schemas, `LogEventType.web_retrieval`, the guarded fetch service, redirect-disabled/proxy-disabled transport, safe text decoding, audit metadata, and the API route under the existing `network` capability prefix.
- Completed: QA added API/auth coverage for allow/audit success with mocked transport, denial and missing approval before transport, explicit policy requirements, approval-required single-use execution, wrong/reused approvals, stray approval ids, URL credentials/fragments, truncation, binary content rejection, redirect blocking, active-task context rejection, and response/log redaction.
- Completed: PM updated README, architecture, developer setup, usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /web-retrieval/fetch` executes one guarded GET request only after the target host matches an explicit network policy rule.
- Implemented in this slice: `approval_required` web retrieval fetches consume a single-use network approval bound to `surface: "web_retrieval"` and `action: "fetch"`; approval ids are rejected when the active host policy is `allow` or `audit`.
- Implemented in this slice: fetch transport blocks redirects, proxies, caller-supplied headers, cookies, request bodies, URL credentials, URL fragments, non-text-like content, and oversized reads beyond the configured cap plus one-byte truncation detection.
- Implemented in this slice: fetch responses include sanitized URL, host, status, content type, charset, SHA-256 digest, bounded redacted text, size, truncation state, policy metadata, and consumed approval id; audit events omit fetched body text and raw query strings.
- Still out of scope after this slice: crawling, HTML parsing, indexing, summarization, redirect re-authorization, caller-supplied headers/auth/cookies, OS-level/non-Python egress isolation, first-class secret-manager adapters, managed KMS, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused web retrieval API gate: `python -m pytest -q tests\test_api.py -k "web_retrieval" --maxfail=1 -x` passed with 13 tests and 197 deselected.
- Combined web retrieval/network/auth/settings gate: `python -m pytest -q tests\test_network_policy.py tests\test_auth.py tests\test_managed_settings.py -k "web_retrieval or network_approval or capability_for_path or managed_settings or effective_settings" --maxfail=1 -x` passed with 110 tests and 76 deselected.
- Affected suite gate passed: `python -m pytest -q tests\test_api.py tests\test_network_policy.py tests\test_auth.py tests\test_managed_settings.py --maxfail=1 -x` with 396 tests.
- Full lint/format hygiene gates passed: `python -m ruff check .` and `python -m ruff format --check .`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,223 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009ao Managed Plugin Component Records

Status: completed for the scoped managed plugin component record slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond CLI/hook/command-recipe/plugin-trust/plugin-component policy records and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected managed plugin component records after BL-009an because deployment-owned inert component provenance was the next bounded managed policy-source control before any future executable plugin loading.
- Completed: Architect/Security scoped records as read-only settings-file data with computed component ids, no local persistence, managed-over-local overlay, local spoof filtering, and `stale`/`drifted` provenance reporting.
- Completed: Developer added `managed_plugin_component_records` parsing, managed source attribution, managed overlay behavior in component listing, local spoof filtering, install/disable read-only enforcement for managed plugin ids, and stale/drifted managed status checks for manifest and component provenance.
- Completed: QA added managed-settings and API coverage for managed-only loading, fail-closed parser validation, list/source behavior, no local persistence, managed shadowing, read-only install/disable rejection, local managed-source spoof filtering, stale manifest reporting, digest drift, size drift, and missing component drift.
- Completed: Reviewer/QA scout identified the missing size/missing-file drift coverage and install read-only precedence risk; Developer and QA fixed both before final validation.
- Completed: PM updated README, architecture, usage, developer setup, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` can declare `managed_plugin_component_records` with plugin id, component type, component path, manifest digest, component digest, component size, optional name, and optional `installed` or `disabled` status.
- Implemented in this slice: `GET /plugins/{plugin_id}/components` lists source-attributed managed component records ahead of local component records and filters locally persisted rows that spoof `source: "managed"`.
- Implemented in this slice: managed component records shadow local records with the same computed component id, never write to `plugin-components.json`, and make component install/disable mutation read-only for managed plugin ids.
- Implemented in this slice: managed component list status reports `stale` when the plugin manifest digest no longer matches and `drifted` when the component is missing, resized, or digest-mismatched.
- Still out of scope after this slice: plugin hook-code/tool/agent/skill loading governance, managed KMS, first-class secret-manager adapters, full web retrieval/fetch runtime, OS-level/non-Python egress isolation, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused managed component settings gate: `python -m pytest -q tests\test_managed_settings.py -k "managed_plugin_component" --maxfail=1 -x` passed with 12 tests and 42 deselected.
- Focused managed/reference component API gate: `python -m pytest -q tests\test_api.py -k "managed_plugin_component or plugin_reference_component" --maxfail=1 -x` passed with 4 tests and 195 deselected.
- Combined managed/reference component and lock gate: `python -m pytest -q tests\test_managed_settings.py tests\test_api.py -k "managed_plugin_component or plugin_reference_component or managed_policy_locks" --maxfail=1 -x` passed with 18 tests and 235 deselected.
- Focused auth/plugin capability gate: `python -m pytest -q tests\test_auth.py -k "plugin" --maxfail=1 -x` passed with 12 tests and 107 deselected.
- Affected suite gate passed: `python -m pytest -q tests\test_managed_settings.py tests\test_api.py tests\test_auth.py --maxfail=1 -x` with 372 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,211 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009an Managed Command Recipes

Status: completed for the scoped managed command recipe slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond CLI/hook/command-recipe/plugin-trust policy records and coarse surface locks, managed plugin component records if needed before executable plugin loading, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected managed command recipes after BL-009am because deployment-owned command recipes were the next bounded managed policy-source control and could reuse the existing command recipe runtime.
- Completed: Architect/Security scoped the contract to read-only recipes loaded only from `DGENTIC_MANAGED_SETTINGS_FILE`, no local JSON persistence, managed-over-local visibility, and existing CLI preview/execute/approval/run paths.
- Completed: Developer added `managed_command_recipes` settings parsing, fail-closed schema validation, managed source attribution, managed/local merge behavior, managed ID collision protection for local and plugin recipe writes, managed usage audit events without local mutation, and local spoof filtering for persisted rows that claim `source: "managed"`.
- Completed: QA added managed-settings, command recipe, and API coverage for env-only ignore behavior, list/detail exposure, preview/execute/approval/run support, local/plugin mutation rejection, no local `command-recipes.json` writes, audit metadata, duplicate normalized fields and ids, and local managed-source spoof rows.
- Completed: Reviewer/Security validated runtime path reuse, read-only managed IDs, no managed persistence, circular import safety, and returned two hardening findings that were fixed in the same run.
- Completed: PM updated README, architecture, usage, developer setup, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` can declare `managed_command_recipes` using the normal command recipe schema fields.
- Implemented in this slice: `GET /cli/recipes` and `GET /cli/recipes/{recipe_id}` include source-attributed managed recipes, with managed records taking precedence over same-id local records.
- Implemented in this slice: managed recipes use existing recipe preview, synchronous execute, approval creation, and asynchronous run paths; usage produces CLI audit events without incrementing or persisting local usage state.
- Implemented in this slice: local recipe create/patch and plugin command recipe install cannot shadow managed recipe ids, and manually persisted local rows with `source: "managed"` are filtered or rejected rather than treated as deployment-owned records.
- Still out of scope after this slice: managed plugin component records, plugin hook-code/tool/agent/skill loading governance, managed KMS, first-class secret-manager adapters, full web retrieval/fetch runtime, OS-level/non-Python egress isolation, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused managed command recipe settings gate: `python -m pytest -q tests\test_managed_settings.py -k "managed_command_recipes" --maxfail=1 -x` passed with 9 tests and 33 deselected.
- Focused command recipe gate: `python -m pytest -q tests\test_command_recipes.py --maxfail=1 -x` passed with 10 tests.
- Focused managed command recipe API gate: `python -m pytest -q tests\test_api.py -k "managed_command_recipe" --maxfail=1 -x` passed with 2 tests and 195 deselected.
- Combined focused managed/plugin recipe gate: `python -m pytest -q tests\test_managed_settings.py tests\test_command_recipes.py tests\test_api.py -k "managed_command_recipe or managed_policy_locks or plugin_command_recipe" --maxfail=1 -x` passed with 16 tests and 233 deselected.
- Affected suite gate passed: `python -m pytest -q tests\test_managed_settings.py tests\test_command_recipes.py tests\test_api.py --maxfail=1 -x` with 249 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,197 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009am Generated-Tool Network Approval Consumption

Status: completed for the scoped generated-tool network approval consumption slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond CLI/hook/plugin-trust policy records and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected generated-tool network approval consumption after BL-009al because generated-tool `approval_required` socket policy still failed closed with no approval path.
- Completed: Architect/Security scoped the change to a Python runtime socket guardrail, with one single-use network approval bound to `surface: "generated_tool"`, `action: "socket_connect"`, exact host, and explicit port.
- Completed: Developer added `ToolExecutionRequest.network_approval_id`, API/runtime plumbing, parent-side approval claiming before subprocess launch, sanitized approved endpoint handoff to the child runner, result/audit metadata, and fail-closed rejection of network ids on tool approval creation.
- Completed: QA added focused runtime and API coverage for successful approval consumption, pending/wrong-surface/portless/reused/policy-drift rejection, tool approval mismatch preservation, result/log metadata, and API pass-through.
- Completed: Reviewer/Security validated that network approval remains separate from tool artifact approval, is not silently ignored on tool approval creation, and is documented as host/port socket approval rather than OS-level egress isolation.
- Completed: PM updated README, architecture, usage, developer setup, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/tools/{name}/execute` accepts `network_approval_id` and passes it to generated-tool execution without folding it into tool approval records.
- Implemented in this slice: generated-tool runtime claims approved network records only for the `generated_tool`/`socket_connect` surface/action, requires an explicit port, rejects non-origin path approvals, and preserves pending or wrong-surface records without consuming them.
- Implemented in this slice: generated-tool subprocesses receive only sanitized policy rules plus the claimed approved host and port; `deny` still blocks, while `approval_required` can proceed only for the approved endpoint or a resolver-derived address for the same approved port.
- Implemented in this slice: tool execution responses and audit events include the consumed `network_approval_id`.
- Still out of scope after this slice: OS-level/non-Python egress isolation, native-extension or spawned-binary network control, HTTP path/method/header/body enforcement, full web retrieval/fetch runtime, managed KMS, first-class secret-manager adapters, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused generated-tool network runtime gate: `python -m pytest -q tests\test_tool_runtime.py -k "network" --maxfail=1 -x` passed with 17 tests and 40 deselected.
- Focused generated-tool approval/network runtime gate: `python -m pytest -q tests\test_tool_runtime.py -k "network or approval" --maxfail=1 -x` passed with 25 tests and 33 deselected.
- Focused generated-tool API gate: `python -m pytest -q tests\test_api.py -k "generated_tool_execute_api" --maxfail=1 -x` passed with 9 tests and 186 deselected.
- Focused generated-tool API approval gate: `python -m pytest -q tests\test_api.py -k "generated_tool_execute_api or approval" --maxfail=1 -x` passed with 31 tests and 164 deselected.
- Focused network approval/web retrieval gate: `python -m pytest -q tests\test_network_policy.py -k "network_approval or web_retrieval" --maxfail=1 -x` passed with 8 tests and 4 deselected.
- Affected network/tool/API gate: `python -m pytest -q tests\test_tool_runtime.py tests\test_network_policy.py tests\test_api.py -k "network or generated_tool_execute_api or approval" --maxfail=1 -x` passed with 69 tests and 195 deselected.
- Focused auth approval gate: `python -m pytest -q tests\test_auth.py -k "network or tool or approval" --maxfail=1 -x` passed with 42 tests and 77 deselected.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Affected suite gate passed: `python -m pytest -q tests\test_tool_runtime.py tests\test_network_policy.py tests\test_api.py tests\test_auth.py --maxfail=1 -x` with 384 tests.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,182 tests and 2 skipped.

Next:
- Commit and push this stable Sprint 15 checkpoint, then continue Sprint 15 with the next highest-risk remaining item.

### Sprint 15 BL-009al Managed Plugin Trust Records

Status: completed for the scoped managed plugin trust record slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, broader managed policy-source controls beyond CLI/hook/plugin-trust policy records and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected managed plugin trust records after BL-009ak to extend deployment-owned policy-source controls beyond CLI and hook-policy records.
- Completed: Architect/Security scoped the contract to exact-manifest-digest managed trust/block records that override local trust for the same plugin id and become stale on manifest drift.
- Completed: Developer added `managed_plugin_trust_records` parsing, effective-settings source reporting, managed trust-source fields, managed-over-local discovery behavior, stale drift handling, and local trust mutation rejection for managed plugin ids.
- Completed: QA added managed-settings and API coverage for managed-only loading, fail-closed validation, trust-source reporting, local mutation rejection, no local trust persistence, and manifest drift staleness.
- Completed: Reviewer/Security validated that managed trust does not persist to `plugin-trust.json`, cannot silently trust changed plugin bytes, and remains read-only through local plugin trust mutation routes.
- Completed: PM updated README, architecture, usage, developer setup, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` can declare `managed_plugin_trust_records` with `plugin_id`, exact `manifest_digest`, `trusted` or `blocked` status, reason, and decider metadata.
- Implemented in this slice: `GET /plugins` and `GET /plugins/{plugin_id}` report `trust_source: "managed"` when a managed record controls the plugin id, return the managed trust decision only when the manifest digest matches, and return `stale` when the manifest bytes drift.
- Implemented in this slice: managed plugin trust records override local trust records for the same plugin id and reject `PATCH /plugins/{plugin_id}/trust` with a read-only error while leaving unmanaged plugin ids mutable unless `plugin_trust` is locked.
- Still out of scope after this slice: managed policy sources for command recipes or plugin component records, managed KMS, first-class secret managers, full web retrieval/fetch runtime, generated-tool network approval workflows, OS-level egress isolation, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused managed plugin trust settings gate: `python -m pytest -q tests\test_managed_settings.py -k "managed_plugin_trust"` passed with 6 tests.
- Focused managed plugin trust API gate: `python -m pytest -q tests\test_api.py -k "managed_plugin_trust or plugin_trust_persists or plugin_routes_require_tools_capability"` passed with 3 tests.
- Broader plugin API gate: `python -m pytest -q tests\test_api.py -k "plugin"` passed with 15 tests.
- Managed-settings file gate: `python -m pytest -q tests\test_managed_settings.py` passed with 33 tests.
- Source/test lint and format gates passed for touched source and tests.
- Affected suite gate passed: `python -m pytest -q tests\test_api.py tests\test_auth.py tests\test_managed_settings.py` with 346 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,176 tests and 2 skipped.

Next:
- Continue Sprint 15 with generated-tool network approval workflow design, OS-level/non-Python egress isolation, managed KMS/secret-manager hardening, richer production identity workflows, plugin loading governance from inert records, managed policy-source controls beyond CLI/hook/plugin trust, or direct git/PR workflow runners based on next risk.

### Sprint 15 BL-009ak Inert Plugin Reference Component Registry Governance

Status: completed for the scoped metadata-only plugin reference component registry contract; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes, hook policies, and inert reference records, managed policy-source controls beyond CLI/hook policy rules and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected metadata-only install/list/disable governance for plugin reference components after BL-009aj because future plugin loading should start from persisted provenance rather than raw manifest summaries.
- Completed: Architect/Security scoped the contract to inert records in `plugin-components.json` with no parsing, importing, indexing, loading, or executing referenced content.
- Completed: Developer added stable component ids, install/list/disable routes, persisted reference component records, activation events, and the managed `plugin_components` mutation lock surface.
- Completed: QA added API, managed-settings, and auth coverage for trusted-only install, list/disable/reinstall workflows, persisted metadata-only records, no component-content leakage, managed lock behavior, and route capability mapping.
- Completed: Reviewer/Security validated that install persists only provenance metadata and does not create generated tools, agents, skills, memory records, hook rules, command recipes, or runtime loaders.
- Completed: PM updated README, architecture, usage, developer setup, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /plugins/{plugin_id}/components/install` persists trusted current `agent_blueprints`, `skills`, `tools`, and `docs` references as inert `plugin-components.json` records with stable component ids, component paths, SHA-256 component digests, component sizes, manifest digests, status, actor, and timestamps.
- Implemented in this slice: `GET /plugins/{plugin_id}/components` lists installed or disabled inert reference component records, and `POST /plugins/{plugin_id}/components/disable` marks them disabled without deleting provenance.
- Implemented in this slice: `managed_policy_locks` accepts `plugin_components`, causing component install/disable mutation routes to fail closed while preserving plugin discovery, component preview, and component list access.
- Still out of scope after this slice: plugin hook-code loading, generated-tool import/install from plugins, agent blueprint activation, skill loading or prompt injection, component content exposure, OS-level plugin sandboxing, managed KMS, first-class secret managers, generated-tool network approval workflows, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused plugin component and managed-lock API gate: `python -m pytest -q tests\test_api.py -k "plugin_reference_component or managed_policy_locks"` passed with 3 tests.
- Focused managed-settings lock gate: `python -m pytest -q tests\test_managed_settings.py -k "managed_policy_locks"` passed with 1 test.
- Focused auth capability gate: `python -m pytest -q tests\test_auth.py -k "capability_for_path_maps_public_and_sensitive_routes"` passed with 47 tests.
- Broader plugin API gate: `python -m pytest -q tests\test_api.py -k "plugin"` passed with 14 tests.
- Managed-settings file gate: `python -m pytest -q tests\test_managed_settings.py` passed with 27 tests.
- Source/test lint and format gates passed for touched source and tests.
- Affected suite gate passed: `python -m pytest -q tests\test_api.py tests\test_auth.py tests\test_managed_settings.py` with 339 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,169 tests and 2 skipped.

Next:
- Continue Sprint 15 with generated-tool network approval workflow design, OS-level/non-Python egress isolation, managed KMS/secret-manager hardening, richer production identity workflows, plugin component loading governance from inert records, managed policy-source controls beyond CLI/hook policy rules, or direct git/PR workflow runners based on next risk.

### Sprint 15 BL-009aj Plugin Reference Component Preview Governance

Status: completed for the scoped non-executing plugin reference component preview contract; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill install and loading governance beyond declarative command recipes, hook policies, and inert previews, managed policy-source controls beyond CLI/hook policy rules and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/PO selected a bounded plugin governance slice after BL-009ai because plugin agent, skill, tool, and docs references were previously manifest-summary-only while executable loading remains too risky for an autonomous increment.
- Completed: Architect/Security scoped the contract to trusted-current-manifest-only, digest-only previews with no parsing, importing, indexing, installing, loading, or executing referenced content.
- Completed: Developer added manifest reference component declarations for `agent_blueprints`, `skills`, `tools`, and `docs`, plus `POST /plugins/{plugin_id}/components/preview` metadata responses backed by the existing bounded component reader.
- Completed: QA added API and auth coverage for trusted-only preview, digest/size metadata, no component-content leakage, duplicate-reference rejection, stale trust blocking, and `tools` capability mapping.
- Completed: Reviewer/Security validated that the route is metadata-only, writes no plugin activation state, and keeps future component loading as an explicit follow-up rather than an implicit side effect.
- Completed: PM updated README, architecture, usage, developer setup, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: plugin manifests may declare top-level `agent_blueprints`, `skills`, `tools`, and `docs` reference arrays with safe relative `path` values and optional redacted `name` metadata.
- Implemented in this slice: `POST /plugins/{plugin_id}/components/preview` requires a trusted current manifest digest, reads each referenced component with root-bound and symlink-rejected bounded reads, and returns component type, name, path, SHA-256 digest, size, manifest digest, and ready status.
- Implemented in this slice: component preview responses do not include component content and do not create or mutate `command-recipes.json`, `hook-policy-rules.json`, generated-tool records, agent records, skill registries, memory indexes, or plugin activation state.
- Still out of scope after this slice: plugin hook-code loading, plugin generated-tool import/install, plugin agent blueprint activation, plugin skill loading or prompt injection, component registry persistence, OS-level plugin sandboxing, managed KMS, first-class secret managers, generated-tool network approval workflows, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused plugin API gate: `python -m pytest -q tests\test_api.py -k "plugin_reference_component or plugin_routes_require_tools_capability or plugin_command_recipe_install or plugin_hook_policy_install"` passed with 7 tests.
- Focused auth capability gate: `python -m pytest -q tests\test_auth.py -k "capability_for_path_maps_public_and_sensitive_routes"` passed with 44 tests.
- Broader plugin API gate: `python -m pytest -q tests\test_api.py -k "plugin"` passed with 14 tests.
- Broader auth/plugin gate: `python -m pytest -q tests\test_auth.py -k "capability_for_path_maps_public_and_sensitive_routes or plugin"` passed with 44 tests.
- Source/test lint and format gates passed for touched source and tests.
- Affected suite gate passed: `python -m pytest -q tests\test_api.py tests\test_auth.py` with 309 tests.
- Full lint/format/diff hygiene gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,166 tests and 2 skipped.

Next:
- Continue Sprint 15 with generated-tool network approval workflow design, OS-level/non-Python egress isolation, managed KMS/secret-manager hardening, richer production identity workflows, plugin component registry/install governance, managed policy-source controls beyond CLI/hook policy rules, or direct git/PR workflow runners based on next risk.

### Sprint 15 BL-009ai Web Retrieval Network Guard Contract

Status: completed for the scoped transport-free web retrieval network guard contract; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, full web retrieval/fetch runtime beyond the guard contract, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes and hook policies, managed policy-source controls beyond CLI/hook policy rules and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected a bounded web retrieval guard contract after BL-009ah because the backlog calls out web retrieval network enforcement but the repo does not yet have a concrete fetcher/crawler runtime.
- Completed: Developer added `web_retrieval.py` with `web_retrieval`/`fetch`-scoped policy evaluation, approval creation, and approval-claim authorization helpers, plus API routes under `/web-retrieval/network/*` and `network` capability mapping.
- Completed: QA added network-policy, API, and auth coverage proving web retrieval approvals are surface/action-bound, single-use, sanitized, hook-policy aware, and protected by the `network` capability.
- Completed: Reviewer/Security validated that the slice does not implement outbound fetching, crawling, or HTML parsing, keeps approval binding on the existing network approval machinery, and avoids exposing URL query strings, fragments, or secret-shaped policy reasons in web-retrieval policy responses.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /web-retrieval/network/check` evaluates a URL through the normal network policy engine using the pinned `fetch` action for hook-policy escalation.
- Implemented in this slice: `POST /web-retrieval/network/approvals` creates a normal network approval pinned to `surface: "web_retrieval"` and `action: "fetch"` when policy requires approval.
- Implemented in this slice: `POST /web-retrieval/network/authorize` claims a matching approved network approval before a future retrieval client can fetch, and rejects missing, wrong-surface, expired, denied, stale, or already-executed approvals.
- Implemented in this slice: web retrieval policy responses use sanitized URL previews without query strings or fragments and redacted policy reasons, while persisted approval records keep existing digest-bound URL/policy binding.
- Still out of scope after this slice: actual web fetch/crawler transport, HTML/document parsing, content ingestion into memory, browser retrieval, generated-tool network approval workflows, OS-level egress isolation, managed KMS, first-class secret managers, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused web-retrieval network-policy gate: `python -m pytest -q tests\test_network_policy.py -k "web_retrieval or network_approval"` passed with 8 tests.
- Focused web-retrieval API gate: `python -m pytest -q tests\test_api.py -k "web_retrieval_network or network_approval_api or guardrails_network_returns_policy_decision"` passed with 5 tests.
- Focused auth capability gate: `python -m pytest -q tests\test_auth.py -k "capability_for_path_maps_public_and_sensitive_routes or capability_for_request_splits_approval_review_from_execution"` passed with 59 tests.
- Focused lint/format gates passed for touched source and tests.
- Affected suite gate passed: `python -m pytest -q tests\test_network_policy.py tests\test_api.py tests\test_auth.py tests\test_provider_runtime.py tests\test_tool_runtime.py` with 494 tests.
- Full lint and format gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,163 tests and 2 skipped.

Next:
- Continue Sprint 15 with generated-tool network approval workflows, OS-level/non-Python generated-tool egress isolation, managed KMS/secret-manager hardening, richer production identity workflows, plugin hook-code/tool/agent/skill loading governance, managed policy-source controls beyond CLI/hook policy rules, or direct git/PR workflow runners based on next risk.

### Sprint 15 BL-009ah Managed Hook-Policy Rule Precedence

Status: completed for the scoped managed hook-policy rule precedence slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes and hook policies, managed policy-source controls beyond CLI/hook policy rules and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected per-record managed hook-policy rule precedence as the next bounded Sprint 15 slice after BL-009ag because deployment-owned hook escalation policy should coexist with local and plugin hook rules without relying only on coarse surface locks.
- Completed: Developer added `managed_hook_policy_rules` managed-settings parsing, managed-source provenance on hook policy rules, managed-before-local/plugin rule merging, local/plugin ID collision hiding, API/runtime read-only enforcement for managed IDs, and plugin install collision rejection for managed IDs.
- Completed: QA added managed-settings parser, hook-policy service, API, and CLI approval runtime coverage for managed source attribution, precedence, fail-closed validation, local persistence isolation, local/plugin coexistence, read-only managed records, role scoping, disabled rules, and stale managed-hook approval binding.
- Completed: Reviewer/Security validated that managed hook rules are not persisted to local mutable state, cannot be patched through the API, sort before local/plugin rules, block plugin installation collisions by managed IDs, and keep approval-bound execution stale when managed hook identity changes.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` can declare `managed_hook_policy_rules` with bounded stable ids, rule names, surface/action/match/effect fields, reason, optional agent roles, enabled state, and priority.
- Implemented in this slice: managed hook policy rules are honored only from the managed settings file, fail closed for malformed, duplicate-id, unknown-field, missing-required, secret-shaped, or unsafe network-pattern input, and are reported with managed source in list responses.
- Implemented in this slice: `GET /guardrails/hooks/rules` returns managed, local, and plugin hook rules in evaluation order, with managed rules sorted first and source-attributed as `managed`.
- Implemented in this slice: managed hook rules participate in command/filesystem/network hook evaluation before local and plugin rules, remain excluded from `hook-policy-rules.json`, and cannot be modified through `/guardrails/hooks/rules/{rule_id}`.
- Implemented in this slice: local hook-rule creation/update and plugin hook-policy activation remain available when per-record managed rules exist unless `managed_policy_locks` includes the relevant surface.
- Implemented in this slice: CLI approval records that include hook-policy decisions fail bound execution validation after managed hook rule identity changes, preserving stale-approval safety.
- Still out of scope after this slice: managed KMS, first-class secret-manager adapters, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance, managed policy-source controls beyond CLI/hook policy rules, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused managed-settings hook gate: `python -m pytest -q tests\test_managed_settings.py -k "managed_hook_policy"` passed with 8 tests.
- Focused hook-policy managed gate: `python -m pytest -q tests\test_hook_policy.py -k "managed_hook_policy"` passed with 4 tests.
- Hook-policy file gate: `python -m pytest -q tests\test_hook_policy.py` passed with 7 tests.
- Managed-settings file gate: `python -m pytest -q tests\test_managed_settings.py` passed with 27 tests.
- Focused API hook gate: `python -m pytest -q tests\test_api.py -k "managed_hook_policy or hook_policy_rule_api"` passed with 4 tests.
- Broader API hook gate: `python -m pytest -q tests\test_api.py -k "hook_policy or managed_policy_locks"` passed with 10 tests.
- Focused CLI approval runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "changed_managed_hook_policy_rule"` passed with 1 test.
- Final lint and format gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Affected suite gate passed: `python -m pytest -q tests\test_hook_policy.py tests\test_managed_settings.py tests\test_api.py tests\test_cli_runtime.py` with 312 tests and 2 skipped.
- Full regression gate passed: `python -m pytest -q --maxfail=1 -x` with 1,155 tests and 2 skipped.

Next:
- Continue Sprint 15 with managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, richer production identity workflows, plugin hook-code/tool/agent/skill loading governance, managed policy-source controls beyond CLI/hook policy rules, or direct git/PR workflow runners based on next risk.

### Sprint 15 BL-009ag Managed CLI Policy Rule Precedence

Status: completed for the scoped managed CLI policy rule precedence slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes and hook policies, managed policy-source controls beyond CLI policy rules and coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected per-record managed CLI policy rule precedence as the next bounded Sprint 15 slice after BL-009af because deployment-owned command policy should be able to coexist with local workspace rules without relying only on coarse surface locks.
- Completed: Developer added `managed_cli_policy_rules` managed-settings parsing, managed-source provenance on CLI policy rules, managed-before-local rule merging, local ID collision hiding, and API/runtime read-only enforcement for managed rule IDs.
- Completed: QA added command-policy, managed-settings parser, API, and CLI approval runtime coverage for managed source attribution, precedence, fail-closed validation, local persistence isolation, local-rule coexistence, read-only managed records, hard-coded safety non-bypass, and stale managed-policy approval binding.
- Completed: Reviewer/Security validated that managed rules are not persisted to local mutable state, cannot be patched through the API, sort before local rules, and cannot downgrade hard-coded git, GitHub CLI, state-file, shell-wrapper, path-boundary, or startup-hardening protections.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` can declare `managed_cli_policy_rules` with bounded stable ids, rule names, match type/pattern, permission mode, reason, optional agent roles, enabled state, and priority.
- Implemented in this slice: managed CLI policy rules are honored only from the managed settings file, fail closed for malformed, duplicate-id, unknown-field, oversized, or secret-shaped input, and are reported as managed source in effective settings metadata.
- Implemented in this slice: `GET /cli/policy/rules` returns managed and local rules in evaluation order, with managed rules sorted first and source-attributed as `managed`; local rules remain source-attributed as `local`.
- Implemented in this slice: managed rules participate in command policy evaluation before local rules, remain excluded from `cli-command-policy-rules.json`, and cannot be modified through `/cli/policy/rules/{rule_id}`.
- Implemented in this slice: local CLI policy creation/update remains available when per-record managed rules exist unless `managed_policy_locks` includes `cli_policy`.
- Implemented in this slice: CLI approval records matched to managed rules fail bound execution validation after managed rule identity changes, preserving stale-approval safety.
- Still out of scope after this slice: managed KMS, first-class secret-manager adapters, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance, managed policy-source controls beyond CLI policy rules, direct git/PR runners, and UI/CLI/VS Code client flows.

Validation:
- Focused command-policy gate: `python -m pytest -q tests\test_command_policy.py -k "managed_cli_policy or managed_safe_cli_policy"` passed with 8 tests.
- Focused managed-settings gate: `python -m pytest -q tests\test_managed_settings.py -k "managed_cli_policy"` passed with 6 tests.
- Focused API gate: `python -m pytest -q tests\test_api.py -k "managed_cli_policy or cli_policy_rule_api"` passed with 2 tests.
- Focused CLI approval runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "changed_managed_policy_rule or approval"` passed with 25 tests.
- Combined focused gate: `python -m pytest -q tests\test_command_policy.py tests\test_managed_settings.py tests\test_api.py tests\test_cli_runtime.py -k "managed_cli_policy or managed_safe_cli_policy or cli_policy_rule_api or changed_managed_policy_rule or approval"` passed with 117 tests.
- Affected file gates passed: `python -m pytest -q tests\test_command_policy.py` with 322 tests, `python -m pytest -q tests\test_managed_settings.py` with 19 tests, `python -m pytest -q tests\test_cli_runtime.py` with 88 tests and 2 skipped, and `python -m pytest -q tests\test_api.py` with 188 tests. The first combined affected-file command exceeded its timeout without a usable result, so it was rerun in chunks.
- Full lint/format/diff gates passed: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1,141 tests and 2 skipped.

Next:
- Continue Sprint 15 with managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, richer production identity workflows, managed policy-source controls beyond CLI policy rules, plugin hook-code/tool/agent/skill loading governance, or direct git/PR workflow runners based on next risk.

### Sprint 15 BL-009af Trusted Declarative Plugin Hook-Policy Activation Governance

Status: completed for the scoped declarative plugin hook-policy activation slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook-code/tool/agent/skill loading governance beyond declarative command recipes and hook policies, per-record managed policy-source precedence beyond coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected trusted declarative plugin hook-policy activation as the next bounded Sprint 15 slice after BL-009ae because hook-policy activation should reuse the trusted-current-manifest model before any plugin hook-code loading is considered.
- Completed: Architect/Security scoped the slice to bounded JSON component reads, no plugin import/load/execution, trusted-current-manifest-only preview/install, plugin provenance, disable/reinstall semantics, manual plugin-owned mutation blocking, and `tools` plus `hooks` authorization.
- Completed: Developer added plugin hook-policy manifest component declarations, activation preview/install/disable services and routes, plugin provenance fields on hook-policy rules, plugin-owned hook-policy install/disable helpers, `plugin_hook_policies` managed locks, and evaluation skipping for disabled plugin-owned rules.
- Completed: QA added coverage for trusted-only preview/install, single-component list payloads, persisted provenance, command hook-policy evaluation, plugin-owned manual patch rejection, disable/reinstall behavior, blocked/stale/secret-shaped component rejection without leakage, `tools` plus `hooks` route authorization, plugin route capability mapping, and managed lock enforcement.
- Completed: Reviewer/Security validated that activation is declarative JSON-only, bounded and root-confined component reads are reused, plugin-owned rules cannot be patched through local hook-policy routes, auth requires both `tools` and `hooks` or `admin`, and lock behavior is consistent with plugin command recipe activation.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: trusted current plugin manifests may declare hook-policy components with relative JSON paths such as `{"hook_policies":[{"path":"hooks/deploy.json"}]}`.
- Implemented in this slice: hook-policy components may be one rule object or a list of rule objects; activation validates them through the normal hook-policy schema and rejects secret-shaped persisted match patterns.
- Implemented in this slice: installed plugin-owned hook-policy rules persist plugin id, manifest digest, component path, component digest, source type, and active/disabled activation status in `hook-policy-rules.json`.
- Implemented in this slice: plugin-owned hook-policy rules cannot be manually mutated through `/guardrails/hooks/rules/{rule_id}`, can be disabled/reinstalled through `/plugins/{plugin_id}/hook-policies/*`, and are skipped during evaluation when disabled.
- Implemented in this slice: plugin hook-policy activation routes require `tools` plus `hooks`, or `admin`, when auth is enabled; install/disable are covered by the new `plugin_hook_policies` managed policy lock surface.
- Still out of scope after this slice: loading plugin hook code, plugin tool/agent/skill loading, plugin dependency lifecycle management, direct git/PR runners, per-record managed policy-source precedence, managed KMS, first-class secret managers, web retrieval network enforcement, and OS-level/non-Python generated-tool egress isolation.

Validation:
- Focused plugin hook-policy gate: `python -m pytest -q tests\test_api.py -k "plugin_hook_policy or managed_policy_locks"` passed with 4 tests.
- Focused auth/settings gates: `python -m pytest -q tests\test_auth.py -k "capability_for_path_maps_public_and_sensitive_routes"` passed with 40 tests, and `python -m pytest -q tests\test_managed_settings.py` passed with 13 tests.
- Affected broad gate: `python -m pytest -q tests\test_api.py tests\test_auth.py tests\test_hook_policy.py tests\test_managed_settings.py tests\test_command_recipes.py tests\test_network_policy.py` passed with 330 tests.
- Full lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate was run in chunks after the one-shot shell command exceeded its timeout without a result: affected broad gate passed with 330 tests; CLI/runtime/policy/filesystem/git chunk passed with 431 tests and 2 skipped; orchestration/database/storage chunk passed with 141 tests; memory/retrieval/vector chunk passed with 27 tests; provider runtime chunk passed with 123 tests; tool runtime/registry chunk passed with 73 tests. This covers all 1,127 collected tests.

Next:
- Continue Sprint 15 with per-record managed policy-source precedence, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, richer production identity workflows, or plugin hook-code/tool/agent/skill loading governance based on next risk.

### Sprint 15 BL-009ae Checkpoint-Bound Guarded PR Approval Creation

Status: completed for the scoped PR-approval creation slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook/tool/agent/skill loading governance beyond declarative command recipes, per-record managed policy-source precedence beyond coarse surface locks, and direct git/PR workflow runners beyond approval-bound CLI execution.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected checkpoint-bound guarded PR approval creation as the next bounded Sprint 15 slice after BL-009ad because PR creation needs the same fresh repository-state binding as commit/push while keeping network execution inside the existing CLI approval path.
- Completed: Architect/Security scoped the slice to structured PR intent, fresh ready PR checkpoint digest matching, pending CLI approval creation, branch-already-pushed/current gates, and no direct `gh` or GitHub API execution during approval creation.
- Completed: Developer added `GitPrApprovalRequest`, PR approval request construction, PR title/body/base validation, upstream/current-with-upstream gates, PR workflow binding intent digests, execution-time PR workflow revalidation, `POST /cli/git/pr-approvals`, and command-policy hardening so broad configured-safe `gh` rules cannot downgrade GitHub CLI commands.
- Completed: QA added endpoint, auth, stale-digest, no-upstream, unpushed, behind-upstream, arbitrary-payload, secret-shaped PR text, workflow revalidation, and GitHub CLI command-policy regression coverage.
- Completed: Reviewer/Security/DevOps validated that PR approval creation is structured and side-effect-free, remote URLs remain digest-only, PR title/body raw text is not stored in workflow intent metadata, `gh` execution remains approval-bound, and no new deployment or migration requirement was introduced.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/pr-approvals` re-runs a PR checkpoint, requires the supplied `checkpoint_digest` to match the fresh ready state, requires a configured upstream remote URL digest, rejects branches ahead of or behind upstream, validates bounded single-line non-secret `title`, `body`, and optional `base_branch`, and queues a normal pending CLI approval for a constrained `gh pr create` command using the current branch as `--head`.
- Implemented hardening in this slice: PR workflow bindings include PR intent digests and branch/draft metadata, execution-time workflow validation now supports `pr`, and broad configured-safe `gh` policy rules cannot downgrade GitHub CLI commands to autopilot-safe.
- Still out of scope after this slice: direct PR runners, `gh` execution during approval creation, GitHub API calls, fetch/network freshness checks, PR labels/reviewers/assignees/projects/templates, browser-based PR creation, destructive branch cleanup, force operations, and UI/CLI/VS Code client flows.

Validation:
- Focused PR gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes tests\test_auth.py::test_capability_for_request_splits_approval_review_from_execution tests\test_command_policy.py::test_configured_safe_gh_rules_do_not_downgrade_github_cli_commands -q` passed with 81 tests.
- Broader focused gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py tests\test_cli_runtime.py tests\test_command_policy.py -q` passed with 536 tests and 2 skipped.
- Full lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1119 tests and 2 skipped.

Next:
- Continue Sprint 15 with per-record managed policy-source precedence, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, plugin hook/tool/agent/skill loading governance, or richer production identity workflows based on next risk.

### Sprint 15 BL-009ad Checkpoint-Bound Git Push Approval Creation

Status: completed for the scoped push-approval creation slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook/tool/agent/skill loading governance beyond declarative command recipes, per-record managed policy-source precedence beyond coarse surface locks, and guarded PR execution automation beyond checkpoints and commit/push approval creation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected checkpoint-bound git push approval creation as the next bounded Sprint 15 slice after BL-009ac because push approval needs stronger repository-state and network-target binding than a generic raw CLI approval.
- Completed: Architect/Security scoped the slice to structured push intent, fresh ready checkpoint digest matching, upstream remote URL digest binding, pending approval creation, and execution-time workflow revalidation before approval claim.
- Completed: Developer added `GitPushApprovalRequest`, push approval request construction, upstream/ahead/behind/remote URL digest gates, workflow-bound CLI approval metadata, git workflow revalidation before CLI approval claim, and `POST /cli/git/push-approvals`.
- Completed: QA added endpoint and auth coverage proving pending push approval creation does not push, stale checkpoint digests are rejected, no-upstream and no-ahead states are rejected, arbitrary remote/branch/flag payloads are rejected, authenticated principals override spoofed requesters, and approved commit/push workflow approvals revalidate state before execution.
- Completed: Reviewer/Security/DevOps validated that workflow binding is included in CLI approval digests, remote URLs are represented by digests only, approved workflow-bound executions fail closed after repository state changes, and no PR network behavior was introduced.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/push-approvals` re-runs a push checkpoint, requires the supplied `checkpoint_digest` to match the fresh ready state, requires a configured upstream remote URL digest and local commits ahead of upstream, rejects behind-upstream state, and queues a normal pending CLI approval for exactly `git push`.
- Implemented hardening in this slice: CLI approvals can carry workflow-bound metadata, include that metadata in approval HMAC digests, expose safe workflow-binding review metadata, and call the git workflow validator before claiming a workflow-bound approval for execution.
- Still out of scope after this slice: PR creation, direct git workflow runners beyond approval-bound CLI execution, remote server ref freshness checks that would require fetch/network I/O, destructive branch cleanup, force operations, and UI/CLI/VS Code client flows.

Validation:
- Focused git/auth/runtime/policy gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py tests\test_cli_runtime.py tests\test_command_policy.py -q` passed with 524 tests and 2 skipped.
- Touched lint/format gates: `python -m ruff check tests\test_git_workflows.py tests\test_auth.py src\dgentic\git_workflows.py src\dgentic\cli_runtime.py src\dgentic\api\routes.py src\dgentic\schemas.py` and matching `ruff format --check` passed.
- Full lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1107 tests and 2 skipped.

Next:
- Continue Sprint 15 with guarded PR approval creation, per-record managed policy-source precedence, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, or plugin hook/tool/agent/skill loading governance based on next risk.

### Sprint 15 BL-009ac Checkpoint-Bound Git Commit Approval Creation

Status: completed for the scoped commit-approval creation slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook/tool/agent/skill loading governance beyond declarative command recipes, per-record managed policy-source precedence beyond coarse surface locks, and guarded push/PR execution automation beyond checkpoints and commit approval creation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected checkpoint-bound git commit approval creation as the next bounded Sprint 15 slice after BL-009ab because guarded commit closeout is useful only when tied to a fresh ready checkpoint and the existing CLI approval lifecycle.
- Completed: Architect/Security scoped the slice to structured commit intent, fresh checkpoint digest matching, pending approval creation, and no new git execution runner.
- Completed: Developer added `GitCommitApprovalRequest`, commit-message validation, content-sensitive checkpoint digest inputs, generated `git commit -m ...` command request construction, and `POST /cli/git/commit-approvals`.
- Completed: QA added endpoint and auth coverage proving pending approval creation does not execute a commit, mismatched or non-ready checkpoints are rejected, secret-shaped commit messages are rejected without leakage, authenticated principals override spoofed requesters, and the route maps to `cli`.
- Completed: Reviewer/Security/DevOps validated that staged-content changes invalidate old checkpoint digests, raw diff content is not returned or logged, commit execution remains inside the existing CLI approval approve/execute flow, and no push/PR network behavior was introduced.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/commit-approvals` re-runs a commit checkpoint, requires the supplied `checkpoint_digest` to match the fresh ready state, validates a bounded single-line non-secret `commit_message`, and queues a normal pending CLI approval for the generated commit command.
- Still out of scope after this slice: direct git workflow runners, push approval creation, PR creation, network PR operations, destructive branch cleanup, force operations, and UI/CLI/VS Code client flows.

Validation:
- Focused git/auth gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py -q` passed with 116 tests.
- Broader focused gate: `python -m pytest tests\test_git_workflows.py tests\test_auth.py tests\test_cli_runtime.py -q` passed with 203 tests and 2 skipped.
- Full lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1098 tests and 2 skipped.

Next:
- Continue Sprint 15 with guarded push/PR approval creation, per-record managed policy-source precedence, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, or plugin hook/tool/agent/skill loading governance based on next risk.

### Sprint 15 BL-009ab Managed Policy Surface Locks

Status: completed for the scoped managed policy surface lock foundation; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook/tool/agent/skill loading governance beyond declarative command recipes, per-record managed policy-source precedence beyond coarse surface locks, and guarded git/PR execution automation beyond checkpoints.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected managed policy surface locks as the next bounded Sprint 15 slice after BL-009aa because deployment-owned policy surfaces need a coarse fail-closed mutation gate before richer per-record policy-source precedence exists.
- Completed: Architect/Security scoped the slice to API mutation locks only, preserving read, preview, evaluation, discovery, and git checkpoint access.
- Completed: Developer added `managed_policy_locks` to the managed settings allowlist, managed-only lock parsing, fail-closed unknown-surface validation, and mutation enforcement for CLI policy rules, command recipes, hook policy rules, plugin trust decisions, and plugin command recipe install/disable.
- Completed: QA added focused managed-settings and API coverage proving ordinary environment values do not enforce locks, managed values do enforce locks, unknown lock surfaces fail closed, representative mutation routes return `403`, and read routes remain available.
- Completed: Reviewer/Security validated that locks are effective only from `DGENTIC_MANAGED_SETTINGS_FILE`, do not expose secrets, and do not accidentally block policy inspection workflows.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `managed_policy_locks` accepts managed surfaces `cli_policy`, `command_recipes`, `hook_policy`, `plugin_trust`, and `plugin_command_recipes`.
- Implemented in this slice: lock values may be provided as a managed JSON list; unknown or non-string entries fail closed during settings load.
- Implemented in this slice: normal environment-provided `DGENTIC_MANAGED_POLICY_LOCKS` is reported as an environment setting but does not enforce mutation locks.
- Implemented in this slice: locked surfaces reject mutation routes with `403`, while read/preview/evaluation routes remain available for operator and UI inspection.
- Still out of scope after this slice: per-record policy source precedence, signed managed policy bundles, deployment-managed policy distribution, policy hot reload, and richer conflict resolution between managed and local policy records.

Validation:
- Focused managed policy lock gate: `python -m pytest tests\test_managed_settings.py tests\test_api.py::test_managed_policy_locks_block_mutable_policy_surfaces -q --maxfail=1 -x` passed with 14 tests.
- Touched lint/format gates: `python -m ruff check src\dgentic\settings.py src\dgentic\api\routes.py tests\test_managed_settings.py tests\test_api.py` and `python -m ruff format --check src\dgentic\settings.py src\dgentic\api\routes.py tests\test_managed_settings.py tests\test_api.py` passed.
- Full lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1091 tests and 2 skipped.

Next:
- Continue Sprint 15 with guarded git/PR execution automation, per-record managed policy-source precedence, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, or plugin hook/tool/agent/skill loading governance based on next risk.

### Sprint 15 BL-009aa Git Workflow Safety Checkpoints

Status: completed for the scoped read-only git workflow checkpoint foundation; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook/tool/agent/skill loading governance beyond declarative command recipes, richer managed policy-source controls across persisted policy surfaces, and guarded git/PR execution automation beyond checkpoints.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected git workflow safety checkpoints as the next bounded Sprint 15 slice after BL-009z because commit, push, and PR preparation need auditable readiness metadata before any future execution automation is safe.
- Completed: Architect/Security scoped this slice to shell-free read-only git inspection only, with no `git add`, `git commit`, `git push`, `gh`, PR creation, or network calls.
- Completed: Developer added `git_workflows.py`, the `POST /cli/git/checkpoints` API route, root-bounded git executable/cwd/repository inspection, readiness blockers/warnings, checkpoint digests, bounded audit metadata, and command-policy protection so configured-safe `git` rules cannot downgrade mutating git commands.
- Completed: QA added focused coverage for cwd/repo-root escape rejection, commit readiness, protected staged files, secret-shaped staged additions without leakage, push/PR branch and dirty-worktree blockers, no-network PR warnings, CLI capability mapping, authenticated requester binding, and configured-safe git downgrade regressions.
- Completed: Reviewer/Security validated that the checkpoint surface is metadata-only, secret-safe, root-bounded, and does not introduce commit/push/PR side effects.
- Completed: PM updated README, architecture, usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /cli/git/checkpoints` returns read-only readiness snapshots for `commit`, `push`, and `pr` actions with branch/head/upstream metadata, ahead/behind counts, staged/unstaged/untracked counts, redacted changed paths, diff stats, blockers, warnings, and a checkpoint digest.
- Implemented in this slice: checkpoint inspection resolves the system `git` executable outside `rootDir`, bounds requested cwd and repository root under `rootDir`, disables optional locks and prompts, and records only bounded metadata in CLI audit events.
- Implemented in this slice: commit checkpoints require staged changes and test evidence; push/PR checkpoints require test evidence, clean worktrees, and non-protected branches.
- Implemented in this slice: protected staged files and secret-shaped staged additions block readiness without returning raw diff or secret values.
- Implemented in this slice: broad configured-safe `git` policy rules can still allow recognized read-only inspections such as `git status`, but cannot downgrade mutating or ambiguous git subcommands, including shell-wrapped forms.
- Still out of scope after this slice: running `git add`, `git commit`, `git push`, branch cleanup, PR creation, GitHub API calls, checkpoint-bound execution approvals, UI presentation, CLI client workflow commands, and CI/observability around checkpoint freshness.

Validation:
- Focused git/policy/auth gate: `python -m pytest tests\test_git_workflows.py tests\test_command_policy.py tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes -q --maxfail=1 -x` passed with 352 tests.
- Touched lint/format gates: `python -m ruff check src\dgentic\git_workflows.py src\dgentic\api\routes.py src\dgentic\command_policy.py tests\test_git_workflows.py tests\test_command_policy.py tests\test_auth.py` and `python -m ruff format --check src\dgentic\git_workflows.py src\dgentic\api\routes.py src\dgentic\command_policy.py tests\test_git_workflows.py tests\test_command_policy.py tests\test_auth.py` passed.
- Full lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1088 tests and 2 skipped.

Next:
- Continue Sprint 15 with guarded git/PR execution automation, richer managed policy-source controls, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, or plugin hook/tool/agent/skill loading governance based on next risk.

### Sprint 15 BL-009z Plugin Command Recipe Activation Governance

Status: completed for the scoped backend plugin command recipe activation foundation; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin hook/tool/agent/skill loading governance, richer managed policy-source controls across persisted policy surfaces, and guarded git/PR workflow automation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected plugin command recipe activation governance as the next bounded Sprint 15 security slice after BL-009y because plugin trust and command recipes now exist but must not combine into unaudited component loading.
- Completed: Architect/Security scoped the slice to declarative command recipe JSON components only, with no plugin Python imports, scripts, hook loading, generated-tool loading, dependency loading, or new plugin runner.
- Completed: Developer added plugin manifest `command_recipes` component paths, trusted-current-manifest activation preview/install/disable services and routes, bounded root-confined component reads, component digest provenance, plugin-owned recipe mutation blocking, and recipe activation drift checks.
- Completed: QA added focused coverage for trusted-only activation, blocked/stale trust rejection, secret-shaped component rejection without leakage, plugin-owned recipe provenance, disable/reinstall behavior, component digest drift blocking, recipe-level `approved` bypass rejection, and `tools` plus `cli` activation authorization.
- Completed: Reviewer/Security/DevOps validated that activation remains declarative, digest-bound, reversible, and routed through existing command recipe plus CLI policy/approval/runtime contracts.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: trusted current plugin manifests may declare command recipe components with relative JSON paths such as `{"command_recipes":[{"path":"recipes/git-status.json"}]}`.
- Implemented in this slice: component reads are bounded, root-confined under `rootDir/plugins/[plugin_id]`, symlink-rejected, SHA-256 digested, and schema-validated as normal command recipe requests.
- Implemented in this slice: installed plugin-owned recipes persist plugin id, manifest digest, component path, component digest, source type, and active/disabled activation status in `command-recipes.json`.
- Implemented in this slice: plugin command recipe preview/install/disable routes are under `/plugins/{plugin_id}/command-recipes/*`; when auth is enabled they require `tools` plus `cli`, or `admin`.
- Implemented in this slice: plugin-owned command recipes cannot be manually mutated through `/cli/recipes/{recipe_id}`, and preview/execute/approval/run fail closed if plugin trust is blocked/stale, manifest digest changes, component digest changes, or activation is disabled.
- Still out of scope after this slice: plugin hook/tool/agent/skill loading, plugin Python execution, plugin dependency lifecycle, signed/marketplace distribution, plugin UI workflows, and multi-step plugin orchestration templates.

Validation:
- Focused plugin API gate: `python -m pytest -q tests\test_api.py -k "plugin"` passed with 9 tests and 174 deselected.
- Focused auth gate: `python -m pytest -q tests\test_auth.py -k "capability_for_path or capability_for_request"` passed with 46 tests and 56 deselected.
- Focused recipe gate: `python -m pytest -q tests\test_command_recipes.py` passed with 6 tests.
- Combined affected gate: `python -m pytest -q tests\test_api.py tests\test_command_recipes.py tests\test_auth.py tests\test_cli_runtime.py tests\test_command_policy.py -k "plugin or recipe or capability_for_path or capability_for_request or cli_approval or guarded_cli or approval or environment or shell_wrapper or path_argument"` passed with 226 tests and 459 deselected.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1074 tests and 2 skipped.

Next:
- Continue Sprint 15 with guarded git/PR workflow automation, richer managed policy-source controls, managed KMS/secret-manager hardening, web retrieval network enforcement, generated-tool OS-level egress isolation, or plugin hook/tool/agent/skill loading governance based on next risk.

### Sprint 15 BL-009y Command Recipe Execution Contracts

Status: completed for the scoped backend command-recipe execution contract; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin installation/loading/execution governance beyond manifest trust, plugin-backed recipe distribution/loading, richer managed policy-source controls across persisted policy surfaces, and guarded git/PR workflow automation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected command recipe execution contracts as the next bounded Sprint 15 security slice after BL-009x because UI, CLI, VS Code, and plugin surfaces need auditable repeated-command contracts without bypassing backend approvals.
- Completed: Architect/QA scoped recipes as a thin registry and resolver over existing CLI execution requests, leaving policy evaluation, approval binding, execution, cancellation, output redaction, and audit with CLI policy/runtime services.
- Completed: Developer added persisted command recipe models, safe placeholder validation, secret-shaped recipe text rejection, safe parameter value validation, preview expansion, usage audit events, and `/cli/recipes` CRUD/preview/execute/approvals/runs routes.
- Completed: QA added recipe registry, injection rejection, policy-preview, authenticated-principal binding, approval-required production flow, single-use approval replay, and route-capability coverage.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: command recipes persist in `command-recipes.json` with stable safe ids, redacted metadata, enable/disable state, tags, timestamps, and usage counts.
- Implemented in this slice: recipe templates use declared `{{parameter}}` placeholders only; unknown, duplicate, unused, unsafe, blank, or secret-shaped parameter/template values fail closed before command execution.
- Implemented in this slice: `POST /cli/recipes/{recipe_id}/preview` expands parameters, resolves cwd, evaluates command policy, and returns redacted command review metadata without executing the command.
- Implemented in this slice: recipe execute, approval, and async run routes build normal `CommandExecutionRequest` objects and reuse existing CLI approvals, policy, environment validation, runtime, run history, and output redaction.
- Implemented in this slice: recipe execution request bodies reject extra fields, including recipe-level `approved`; production/staging approval-required recipes must use the existing bound `approval_id` contract.
- Still out of scope after this slice: plugin-packaged recipe loading, multi-step backend recipe orchestration, recipe-specific approval record families, recipe UI surfaces, and managed policy-source ceilings for recipe/plugin/git policy records.

Validation:
- Focused recipe gate: `python -m pytest -q tests\test_command_recipes.py` passed with 6 tests.
- Focused auth gate: `python -m pytest -q tests\test_auth.py -k "capability_for_path or capability_for_request"` passed with 43 tests.
- Combined affected gate: `python -m pytest -q tests\test_command_recipes.py tests\test_auth.py tests\test_api.py tests\test_cli_runtime.py tests\test_command_policy.py -k "recipe or cli_approval or guarded_cli or capability_for_path or capability_for_request or approval or environment or shell_wrapper or path_argument"` passed with 214 tests and 465 deselected.
- Lint/format gates for touched implementation/tests passed with `python -m ruff check src\dgentic\command_recipes.py src\dgentic\api\routes.py tests\test_command_recipes.py tests\test_auth.py` and `python -m ruff format --check src\dgentic\command_recipes.py src\dgentic\api\routes.py tests\test_command_recipes.py tests\test_auth.py`.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1068 tests and 2 skipped.

Next:
- Continue Sprint 15 with plugin installation/loading governance, guarded git/PR workflow automation, richer managed policy-source controls, managed KMS/secret-manager hardening, web retrieval network enforcement, or generated-tool OS-level egress isolation based on next risk.

### Sprint 15 BL-009x Managed Settings Precedence Foundation

Status: completed for the scoped backend managed-settings precedence foundation; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin installation/loading/execution governance beyond manifest trust, command recipe execution contracts, richer managed policy-source controls across persisted policy surfaces, and guarded git/PR workflow automation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected managed settings precedence as the next bounded Sprint 15 security slice after BL-009w because remaining backend policy work needs auditable deployment-owned configuration before UI and extension surfaces expose it.
- Completed: Architect/QA mapped the existing env-only settings, auth startup, network policy, route capability, redaction, and approval-drift risks.
- Completed: Developer added an opt-in `DGENTIC_MANAGED_SETTINGS_FILE` resolver, supported-field allowlist, malformed/unknown/unsupported/oversized/secret-shaped fail-closed validation, managed-over-environment precedence, managed auth enablement over env disable, already-effective auth downgrade rejection, redacted source-attributed effective settings, and `GET /settings/effective`.
- Completed: QA added focused managed settings tests for precedence, fallback, malformed configs, unsupported bootstrap fields, secret-shaped rejection, auth fail-closed behavior, admin-only API access, redacted effective settings, and network policy decisions using managed values.
- Completed: Reviewer/Security/DevOps validated scope, with residual follow-up recorded for deeper managed policy-source ceilings across persisted command, plugin, hook, recipe, and git workflow policy surfaces.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_MANAGED_SETTINGS_FILE` points to a JSON file containing a top-level `settings` object.
- Implemented in this slice: supported managed runtime settings override `.env` and process environment values; unsupported bootstrap and secret fields such as `root_dir`, `data_dir`, `database_url`, `auth_tokens`, approval digest keys, and vault keys are rejected.
- Implemented in this slice: invalid JSON, missing `settings`, unknown fields, oversized files, duplicate normalized fields, and secret-shaped managed values fail closed during settings load.
- Implemented in this slice: managed `auth_enabled=true` can override an environment disable and trigger startup fail-closed behavior when no usable token exists; managed `auth_enabled=false` cannot disable already-effective auth.
- Implemented in this slice: `GET /settings/effective` returns redacted values, per-field source labels, managed field names, and the managed-file SHA-256 digest; the route is admin-only when auth is enabled.
- Still out of scope after this slice: signed/OS-managed distribution, runtime hot reload, managing state/bootstrap paths, raw secret delivery through managed files, and strict policy-source ceiling composition across persisted command/plugin/hook/recipe/git policy records.

Validation:
- Focused managed settings gate: `python -m pytest -q tests\test_managed_settings.py` passed with 11 tests.
- Focused auth/network gate: `python -m pytest -q tests\test_managed_settings.py tests\test_auth.py -k "managed_settings or effective_auth_enabled or capability_for_path"` passed with 41 tests, and `python -m pytest -q tests\test_network_policy.py -k "network_domain_policy"` passed with 4 tests.
- Affected broad API/auth/network gate: `python -m pytest -q tests\test_managed_settings.py tests\test_auth.py tests\test_network_policy.py tests\test_api.py -k "managed_settings or effective_settings or capability_for_path or capability_for_request or network_domain_policy or health"` passed with 61 tests.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1057 tests and 2 skipped.

Next:
- Continue Sprint 15 with command recipe execution contracts, plugin installation/loading governance, guarded git/PR workflow automation, richer managed policy-source controls, managed KMS/secret-manager hardening, web retrieval network enforcement, or generated-tool OS-level egress isolation based on next risk.

### Sprint 15 BL-009w Bound Filesystem Approval Records

Status: completed for the scoped backend filesystem approval-record slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin installation/loading/execution governance beyond manifest trust, command recipe execution contracts, managed settings precedence, and guarded git/PR workflow automation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected bound filesystem approval records as the next bounded Sprint 15 security slice after BL-009v because filesystem hook approval decisions were intentionally report-only until a bound approval flow existed.
- Completed: Architect/Reviewer mapped the filesystem guardrail, hook-policy, auth capability, and existing CLI/tool/network approval-binding patterns.
- Completed: Developer added persisted filesystem approval records, approval create/list/review/approve/deny routes, production/staging rejection of the old `approved: true` filesystem bypass, method-aware filesystem approval capability separation, hook-forced filesystem approval enforcement, and HMAC approval binding over action, path/target, payload, source/target state, options, policy, orchestration, hook, actor, and agent/task context.
- Completed: QA added focused filesystem approval tests for lifecycle, single-use claim, path/target/payload/state drift rejection, hook-forced write approval enforcement, and capability split coverage.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: filesystem approvals persist in `filesystem-approvals.json` and expose safe create/list/review/approve/deny API contracts.
- Implemented in this slice: approval records store redacted review metadata plus HMAC digests for logical paths, resolved paths, write payloads, source/target state, action options, policy decisions, and approval binding.
- Implemented in this slice: approval claims are single-use and re-run guardrails before execution; stale approvals fail after path, target, payload, state, hook-policy, orchestration, requester, or agent/task-context drift.
- Implemented in this slice: filesystem hook `approval_required` decisions now enforce approval for matching filesystem operations instead of remaining report-only.
- Implemented in this slice: creating filesystem approvals and executing bound filesystem operations use the `filesystem` capability, while list/review/approve/deny use the separate `approvals` capability.
- Still out of scope after this slice: interactive approval UI, persisted configurable filesystem policy rules, deeper platform-specific locked-file validation, OS-level filesystem isolation, and complete TOCTOU elimination against same-user workspace races.

Validation:
- Source sanity gate: `python -m ruff check src\dgentic\guardrails.py src\dgentic\api\routes.py src\dgentic\auth.py src\dgentic\schemas.py` and `python -m compileall -q src\dgentic` passed.
- Focused filesystem approval gate: `python -m pytest -q tests\test_filesystem_approvals.py` passed with 4 tests.
- Focused auth/hook gate: `python -m pytest -q tests\test_filesystem_approvals.py tests\test_hook_policy.py tests\test_auth.py -k "filesystem or capability_for_request or hook"` passed with 24 tests.
- Affected broad API/auth/hook gate: `python -m pytest -q tests\test_filesystem_approvals.py tests\test_api.py tests\test_auth.py tests\test_hook_policy.py` passed with 280 tests.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1045 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with managed settings precedence, command recipe execution contracts, plugin installation/loading governance, guarded git/PR workflow automation, or another remaining security-hardening slice based on risk.

## 2026-05-12

### Sprint 15 BL-009v Hook Policy Foundation

Status: completed for the scoped backend-only hook policy foundation; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin installation/loading/execution governance beyond manifest trust, command recipe execution contracts, managed settings precedence, bound filesystem approval records, and guarded git/PR workflow automation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected hook policy as the next bounded security slice after BL-009u, limited to persisted backend policy records and guardrail decision escalation.
- Completed: Architect/Security scoped no plugin hook loading or execution, escalation-only semantics, command/network approval binding, and report-only filesystem approval-required hook decisions until bound filesystem approvals exist.
- Completed: Developer added `src/dgentic/hook_policy.py`, hook policy schemas, `/guardrails/hooks/rules` route wiring, `hooks` capability mapping, command/filesystem/network decision integration, and CLI/network approval digest binding for hook decisions.
- Completed: QA added focused service, API, auth, CLI approval-binding, and network approval-binding regressions.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: hook rules persist in `hook-policy-rules.json`, evaluate by priority, can match command/filesystem/network decisions by `any`, `exact`, `contains`, or `prefix`, and can be scoped to agent roles.
- Implemented in this slice: `audit`, `approval_required`, and `blocked` effects attach redacted hook decisions to policy responses and hook audit events without storing secret-shaped match patterns.
- Implemented in this slice: hook-forced CLI approval-required decisions are included in CLI approval binding digests and stale approvals fail execution after hook policy drift.
- Implemented in this slice: hook-forced network approval-required decisions are included in network policy decision digests and stale network approvals fail claim after hook policy drift.
- Implemented in this slice: filesystem hook `blocked` decisions enforce immediately, while filesystem hook `approval_required` decisions remain visible/report-only until a bound filesystem approval-record model exists.
- Still out of scope after this slice: loading or executing plugin-provided hook code, generated-tool-specific hook surfaces, bound filesystem approval records, managed policy-source precedence, hook policy UI, and organization-managed settings distribution.

Validation:
- Focused hook service gate: `python -m pytest -q tests\test_hook_policy.py` passed with 3 tests.
- Focused API/auth/network hook gate: `python -m pytest -q tests\test_api.py -k "hook_policy or guardrails_network_returns_policy_decision or cli_approval_binding_includes_hook_policy_decision"`, `python -m pytest -q tests\test_network_policy.py -k "hook_policy or hook or network_approval"`, and `python -m pytest -q tests\test_auth.py -k "capability_for_path"` passed.
- Affected broad regression gate: `python -m pytest -q tests\test_api.py tests\test_auth.py tests\test_hook_policy.py tests\test_network_policy.py tests\test_cli_runtime.py tests\test_command_policy.py` passed with 671 tests and 2 skipped.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1035 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with managed settings precedence, command recipe contracts, or a bounded filesystem approval-record slice depending on remaining risk.

### Sprint 15 BL-009u Plugin Trust Foundation

Status: completed for the scoped backend-only plugin manifest discovery and trust foundation; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, plugin installation/loading/execution governance beyond manifest trust, command recipe execution contracts, hook policy enforcement, managed settings precedence, and guarded git/PR workflow automation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected plugin trust controls as the next bounded security slice after BL-009t, limited to backend-only manifest discovery and trust state.
- Completed: Security/Architect scoped direct-manifest discovery, no plugin execution/import/loading, digest-based trust, safe redaction, stale trust, and `tools` capability enforcement.
- Completed: Developer added `src/dgentic/plugins.py`, discovery/trust models, `plugin-trust.json` persistence, SHA-256 raw-manifest digests, stale trust calculation, trust audit events, `/plugins` route wiring, and `/plugins -> tools` capability mapping.
- Completed: QA added focused plugin API/auth tests for redacted discovery, trust persistence and stale status, malformed/oversized/id-mismatch manifests, symlinked manifest rejection, symlinked top-level plugin directory rejection, hidden extra-field rejection, secret-shaped error-path redaction, and production capability enforcement.
- Completed: Reviewer/Security found and Developer/QA closed review findings for top-level `plugins` symlink escape, opaque unreviewed manifest fields, bounded-read/TOCTOU risk, and secret-shaped path leakage in discovery errors.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `GET /plugins`, `GET /plugins/{plugin_id}`, and `PATCH /plugins/{plugin_id}/trust` expose safe plugin manifest summaries and explicit trust/block decisions.
- Implemented in this slice: discovery reads only direct `rootDir/plugins/[plugin_id]/dgentic-plugin.json` manifests, forbids unknown manifest fields, computes SHA-256 digests over exact manifest bytes, and never imports, loads, or executes plugin content.
- Implemented in this slice: symlinked plugin roots, symlinked plugin directories, symlinked manifests, out-of-root manifests, oversized manifests, malformed manifests, and id-mismatched manifests are rejected with safe redacted errors.
- Implemented in this slice: trust records are persisted in `plugin-trust.json`; trust becomes `stale` when manifest bytes change; trust reasons and audit metadata are redacted.
- Still out of scope after this slice: plugin package installation/loading/execution, command recipe execution, hook policy enforcement, managed settings precedence, signed plugin distribution, plugin dependency management, and plugin UI workflows.

Validation:
- Focused plugin gate: `python -m pytest -q tests\test_api.py -k "plugin"` passed with 6 tests and 169 deselected.
- Affected auth/API regression gate: `python -m pytest -q tests\test_api.py tests\test_auth.py` passed with 260 tests.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1024 tests and 2 skipped.
- Lint/format gates: `python -m ruff check .` and `python -m ruff format --check .` passed.

Next:
- Continue Sprint 15 with the next bounded security slice, likely hook policy or managed settings precedence foundations, before moving to Sprint 16 UI work.

### Sprint 15 BL-009t Local Credential Vault Key Rotation

Status: completed for the scoped supplied-key local credential-vault rotation slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, managed KMS integration beyond supplied-key local vault rotation, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, and OS-level/non-Python generated-tool egress isolation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected local vault key rotation as the next bounded secret-management slice after BL-009s because the local vault runtime already exists and web retrieval/OS egress work still lacks concrete runtimes.
- Completed: Security/Architect reviewed the intended supplied-key bulk rotation contract before implementation.
- Completed: Developer added source-only rotation models, `rotate_local_vault_credential_references`, counts-only audit metadata, and `POST /credentials/references/local-vault/rotate-key`.
- Completed: QA added focused tests for successful rotation, revoked local-vault records, skipped env/external-process references, wrong current key rollback, malformed ciphertext rollback, invalid/same new key generic failure, credentials capability enforcement, and no key/plaintext/ciphertext leakage in API or rotation event metadata.
- Completed: Reviewer/Security found no blocking issues for atomicity, leakage, route ordering, capability mapping, revoked-record behavior, or failure handling. Residual non-blocking gap: no explicit missing/overlong-key validation-error leak test; FastAPI's validation error shape does not echo supplied values.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /credentials/references/local-vault/rotate-key` accepts supplied `current_vault_key` and `new_vault_key`, requires the existing `credentials` capability, and returns only `rotated_count`, `skipped_count`, and `rotated_at`.
- Implemented in this slice: all persisted `local_vault` credential-reference ciphertext is re-encrypted in one JSON collection transaction, including revoked records, while env and external-process references are left semantically unchanged and counted as skipped.
- Implemented in this slice: wrong current keys, malformed stored ciphertext, invalid new keys, and same-key requests fail with generic `400` responses before partial writes or audit success events.
- Implemented in this slice: rotation audit events contain only counts and timestamp, avoiding supplied keys, plaintext, ciphertext, credential ids, labels, and secret names.
- Still out of scope after this slice: KMS-managed keys, key escrow/recovery, per-secret versioning UX, first-class secret-manager adapters, web retrieval enforcement, and OS-level/non-Python generated-tool egress isolation.

Validation:
- Focused rotation/credential gate: `python -m pytest -q tests\test_auth.py -k "local_vault_rotate_key or credential_reference"` passed with 11 tests and 72 deselected.
- Auth regression gate: `python -m pytest -q tests\test_auth.py` passed with 83 tests.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1016 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with the next bounded security slice: managed hook-policy/plugin trust foundations if backend contracts are ready, otherwise first-class secret-manager adapter design/implementation.

### Sprint 15 BL-009s Operator Group Capability Inheritance

Status: completed for the scoped operator group capability inheritance slice; Sprint 15 remains active for richer production identity workflows beyond persisted operators and operator groups, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, and OS-level/non-Python generated-tool egress isolation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected operator group inheritance as the next bounded identity slice after BL-009r.
- Completed: Developer added persisted `operator-groups.json` storage, operator group create/list/get/update APIs, operator `group_ids`, and computed `effective_capabilities`.
- Completed: Developer constrained token issuance, token rotation, usable-token startup checks, and persisted-token runtime authentication against the operator's current effective capabilities.
- Completed: QA added focused regressions for group lifecycle persistence, operator assignment validation, inherited token issuance, existing-token runtime shrinkage after group capability reduction/deactivation, unknown group rejection, and secret-shaped group metadata redaction.
- Completed: Reviewer/Security found no blocking authorization, route-ordering, redaction, compatibility, or stale-token issues; the only residual note was a non-blocking direct `/auth/operator-groups` non-auth-token test gap covered by shared `/auth` capability mapping.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/auth/operator-groups` create/list/get/update APIs manage persisted operator group capability bundles.
- Implemented in this slice: operators can carry `group_ids`, and operator responses expose `effective_capabilities` from direct assignments plus active group capabilities.
- Implemented in this slice: token create/rotate and runtime persisted-token authentication fail closed when requested or stored capabilities exceed the operator's current effective capabilities after group reduction or deactivation.
- Implemented in this slice: unknown operator group assignment returns `409`, and group display/description metadata is redacted in API responses, JSON state, and auth audit events.
- Still out of scope after this slice: full production identity lifecycle beyond operator groups, KMS-backed vault key rotation, first-class secret-manager adapters, web retrieval enforcement, and OS-level/non-Python generated-tool egress isolation.

Validation:
- Focused operator-group gate: `python -m pytest -q tests\test_auth.py -k "operator_group or group_capability"` passed with 4 tests and 74 deselected.
- Auth regression gate: `python -m pytest -q tests\test_auth.py` passed with 78 tests.
- Full regression gate after docs updates: `python -m pytest -q --maxfail=1 -x` passed with 1011 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with the next bounded security slice: managed hook-policy/plugin trust foundations if backend contracts are ready, otherwise design-first work for KMS/key rotation or first-class secret-manager adapters.

### Sprint 15 BL-009r Nested Shell Startup Hardening Checks

Status: completed for the scoped nested shell startup hardening slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, and OS-level/non-Python generated-tool egress isolation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected nested shell startup hardening as the next bounded CLI host-boundary slice after BL-009q.
- Completed: Developer added non-downgradable command-policy checks for nested `cmd` invocations that omit `/d` and nested PowerShell/pwsh invocations that omit `-NoProfile -NonInteractive`.
- Completed: Developer preserved existing blocked-command reasons so dangerous nested payloads still report the underlying blocked command before startup-hardening reasons.
- Completed: QA added configured-safe downgrade regressions for unsafe nested shell startup and compatibility regressions for explicitly hardened nested startup.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: configured safe rules cannot downgrade nested `cmd` payloads that omit `/d`.
- Implemented in this slice: configured safe rules cannot downgrade nested PowerShell/pwsh payloads that omit `-NoProfile -NonInteractive`.
- Implemented in this slice: nested shell payloads that explicitly include the hardening flags can still be allowed by configured safe rules when the rest of the payload is otherwise policy-safe.
- Still out of scope after this slice: full shell emulation, OS-level sandboxing, richer user/group identity workflows, KMS-backed key rotation, first-class secret-manager adapters, web retrieval enforcement, and OS-level/non-Python generated-tool egress isolation.

Validation:
- Focused nested-shell gate: `python -m pytest -q tests\test_command_policy.py -k "nested_shell_startup_hardening or hardened_nested_shell_startup or broader_windows_posix_shell_invocation_semantics or shell_command_prefixes"` passed with 51 tests.
- Command-policy regression gate: `python -m pytest -q tests\test_command_policy.py` passed with 305 tests.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1007 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed after formatting.

Next:
- Continue Sprint 15 with the next bounded security slice: managed hook-policy/plugin trust foundations if the backend shape is ready, otherwise design-first work for KMS/key rotation or first-class secret-manager adapters.

### Sprint 15 BL-009q Command Path Argument And CLI Launch Failure Hardening

Status: completed for the scoped command-specific path argument hardening slice and the BL-009p review follow-up; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, and nested shell startup hardening.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected command-specific path arguments as the next bounded CLI host-boundary slice after BL-009p, while prioritizing the review findings from the previous security checkpoint.
- Completed: Developer hardened direct command policy so configured-safe `git`, `npm`, `pnpm`, `yarn`, and `uv` rules cannot downgrade directory/path flags that resolve outside `rootDir`.
- Completed: Developer closed the BL-009p review findings by validating `cmd /c` inner bare executables before launch, always including Windows default PATHEXT candidates, and recording failed synchronous launch run records after approval claim.
- Completed: QA added command-policy regressions for out-of-root command path arguments plus inside-root configured-safe compatibility.
- Completed: QA added CLI runtime regressions for `cmd /c` inner bare executable blocking, malformed PATHEXT fallback behavior, and failed approved synchronous launch audit binding.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: configured-safe path arguments such as `git -C`, `npm --prefix`, `pnpm --dir`/`-C`, `yarn --cwd`, and `uv --directory`/`--project` fail closed when they resolve outside `rootDir`.
- Implemented in this slice: inside-root path arguments can still use configured safe policy rules, preserving normal workspace workflow configuration.
- Implemented in this slice: `cmd /c` bare inner commands now receive the same workspace executable trust preflight as direct bare commands.
- Implemented in this slice: Windows executable extension probing always includes the default `.com`, `.exe`, `.bat`, and `.cmd` candidates even when inherited PATHEXT is missing or malformed.
- Implemented in this slice: synchronous approval executions that fail during process launch now record a failed command run and bind the claimed approval to that run id.
- Still out of scope after this slice: nested shell startup hardening inside reviewed payloads, full shell emulation, OS-level sandboxing, richer user/group identity workflows, KMS-backed key rotation, and first-class secret-manager adapters.

Validation:
- Focused review-follow-up gate: `python -m pytest -q tests\test_cli_runtime.py::test_cmd_wrapped_compound_and_prefix_bare_workspace_commands_block_before_subprocess tests\test_command_policy.py::test_configured_safe_rules_do_not_downgrade_out_of_root_command_path_arguments tests\test_command_policy.py::test_command_path_argument_scan_respects_option_terminator_for_npm` passed with 13 tests.
- Focused command-policy gate: `python -m pytest -q tests\test_command_policy.py -k "command_path_arguments or configured_safe_rules_do_not_downgrade or option_terminator"` passed with 26 tests.
- Focused CLI runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "cmd_wrapped or pathext or launch_failure_records_failed_run"` passed with 6 tests.
- Broader affected suites: `python -m pytest -q tests\test_cli_runtime.py tests\test_command_policy.py` passed with 386 tests and 2 skipped.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 1001 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed after formatting.

Next:
- Continue Sprint 15 with nested shell startup hardening or managed hook-policy/plugin trust foundations; defer web retrieval enforcement until a concrete web retrieval runtime exists and defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009p Bare Executable Workspace/PATH Trust Checks

Status: completed for the scoped bare executable workspace/PATH trust slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, nested shell startup hardening, and command-specific path argument hardening for configured-safe tools.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected bare executable trust as the next bounded CLI host-boundary slice after BL-009o.
- Completed: Security/Explorer confirmed bare command names could be hijacked by workspace current-directory executables on Windows or by workspace directories placed on `PATH`.
- Completed: Developer added launch-time preflight after cwd/environment construction and before approval claims or subprocess launch.
- Completed: QA added CLI runtime regressions for workspace current-directory executable blocking, workspace `PATH` executable blocking, workspace `PATH` entry blocking even without a matching executable, and explicit inside-root executable path compatibility.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: bare executable launches fail closed when the executable would resolve from the workspace current directory on Windows.
- Implemented in this slice: bare executable launches fail closed when any `PATH` entry resolves inside `rootDir`, even if no matching executable exists yet, reducing time-of-check/time-of-use hijack risk.
- Implemented in this slice: explicit executable paths inside `rootDir` still flow through normal command policy and approval handling, keeping the executable location visible in review/audit records.
- Still out of scope after this slice: nested shell startup hardening inside reviewed payloads, command-specific path argument hardening for configured-safe tools, full shell emulation, and OS-level sandboxing.

Validation:
- Focused CLI runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "bare_command or workspace_path_entry or explicit_inside_root_executable_path"` passed with 4 tests.
- Broader affected suites: `python -m pytest -q tests\test_cli_runtime.py tests\test_command_policy.py` passed with 369 tests and 2 skipped.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 984 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed after formatting.

Next:
- Continue Sprint 15 with command-specific path argument hardening for configured-safe tools or managed hook-policy/plugin trust foundations; defer web retrieval enforcement until a concrete web retrieval runtime exists and defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009o CLI Shell Profile And AutoRun Launch Hardening

Status: completed for the scoped CLI shell profile/AutoRun launch hardening slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, nested shell startup hardening, bare executable PATH trust policy, and command-specific path argument hardening for configured-safe tools.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected shell profile/AutoRun launch hardening as the next bounded CLI host-boundary slice after BL-009n.
- Completed: Security/Explorer confirmed top-level `cmd` without `/d` can run Command Processor AutoRun hooks and PowerShell/pwsh can load profile scripts before the inspected payload.
- Completed: Developer added runtime-only argv hardening so reviewed command strings, approval review text, and approval digests remain bound to the user-requested command while the launched top-level shell gets stricter startup flags.
- Completed: QA added CLI runtime regressions for `cmd` `/d` launch arguments, PowerShell/pwsh `-NoProfile -NonInteractive` launch arguments, and command-policy regressions proving those hardening flags do not hide blocked or uninspectable payloads.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: top-level `cmd`/`cmd.exe` launches receive `/d` unless already present, suppressing Windows Command Processor AutoRun registry hooks.
- Implemented in this slice: top-level `powershell`, `powershell.exe`, `pwsh`, and `pwsh.exe` launches receive `-NoProfile -NonInteractive` unless equivalent switches are already present, reducing profile-script and prompt/hang risk for captured unattended runs.
- Implemented in this slice: policy/review/storage command strings are unchanged, so approval digests and audit review records remain tied to the submitted command rather than the hardened argv.
- Still out of scope after this slice: nested shell startup hardening inside reviewed payloads, bare executable PATH trust policy, command-specific path arguments for configured-safe tools, full shell emulation, and OS-level sandboxing.

Validation:
- Focused CLI runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "command_args or start_command_uses_translated_cmd_wrapper or power_shell_command_execution"` passed with 10 tests.
- Focused command-policy gate: `python -m pytest -q tests\test_command_policy.py -k "broader_windows_posix_shell_invocation_semantics"` passed with 17 tests.
- Broader affected suites: `python -m pytest -q tests\test_cli_runtime.py tests\test_command_policy.py` passed with 365 tests and 2 skipped.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 980 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed after formatting.

Next:
- Continue Sprint 15 with bare executable PATH trust policy, command-specific path argument hardening for configured-safe tools, or managed hook-policy/plugin trust foundations; defer web retrieval enforcement until a concrete web retrieval runtime exists and defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009n CLI Approval Reviewer Capability Separation

Status: completed for the scoped CLI approval reviewer capability separation slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, shell profile/AutoRun command-line hardening, bare executable PATH trust policy, and command-specific path argument hardening for configured-safe tools.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected CLI approval reviewer capability separation as a bounded Sprint 15 authorization hardening slice.
- Completed: Architect/Security confirmed CLI approval creation and approved-command execution should stay under `cli`, while list/review/approve/deny operations should require `approvals`, matching provider/tool approval boundaries.
- Completed: Developer added method-aware route capability resolution for `/cli/approvals` without changing CLI approval record shapes or API route handlers.
- Completed: QA added auth mapping and API regressions proving `cli` tokens can create/execute CLI approval work but cannot list/review/approve, while `approvals` tokens can list/review/approve but cannot create CLI approval work.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `require_route_capability` now uses method-aware capability mapping so `POST /cli/approvals` and `POST /cli/approvals/{approval_id}/execute` require `cli`, while `GET /cli/approvals`, `GET /cli/approvals/{approval_id}/review`, `POST /cli/approvals/{approval_id}/approve`, and `POST /cli/approvals/{approval_id}/deny` require `approvals`.
- Implemented in this slice: authenticated reviewer identity binding remains principal-derived; spoofed `decided_by` fields continue to be replaced by the authenticated approval principal.
- Still out of scope after this slice: interactive approval UI, shell profile/AutoRun command-line hardening, bare executable PATH trust policy, command-specific path arguments for configured-safe tools, and richer user/group identity workflows.

Validation:
- Focused auth capability gate: `python -m pytest -q tests\test_auth.py -k "capability_for_request or capability_for_path"` passed with 27 tests.
- Focused API gate: `python -m pytest -q tests\test_api.py -k "cli_approval_api_splits_requester_and_reviewer_capabilities or cli_approval_direct_execute_requires_bound_authenticated_requester"` passed with 2 tests.
- Broader affected suites: `python -m pytest -q tests\test_auth.py tests\test_api.py` passed with 243 tests after formatting.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 972 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed after formatting.

Next:
- Continue Sprint 15 with shell profile/AutoRun command-line hardening, bare executable PATH trust policy, or managed hook-policy/plugin trust foundations; defer web retrieval enforcement until a concrete web retrieval runtime exists and defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009m CLI Startup And Preload Environment Override Hardening

Status: completed for the scoped CLI startup/preload environment override hardening slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, shell profile/AutoRun command-line hardening, bare executable PATH trust policy, and command-specific path argument hardening for configured-safe tools.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected controlled CLI environment override hardening as the next bounded host-boundary slice after BL-009l.
- Completed: Security/Explorer identified shell startup hooks, dynamic-loader preloads/library paths, interpreter option/library injection variables, and exported Bash function names as a bounded risk because they can alter command behavior before a guarded command runs.
- Completed: Developer extended the existing blocked override mechanism without changing CLI API contracts or approval record shapes.
- Completed: QA added CLI runtime and API regressions for `BASH_ENV`, `ENV`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `DYLD_*`, `NODE_OPTIONS`, `RUBYOPT`, `PERL5LIB`, and `BASH_FUNC_` style overrides.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: CLI environment overrides reject common shell startup hook variables, dynamic-loader preload/library path variables, interpreter option/library injection variables, and dangerous prefixes such as `BASH_FUNC_` and `DYLD_`.
- Implemented in this slice: blocked environment override validation happens before subprocess launch and before approval-bound execution can proceed, preserving existing no-value persistence for allowed environment overrides.
- Still out of scope after this slice: PowerShell profile and Windows `cmd` AutoRun command-line hardening, bare executable PATH trust policy, command-specific path arguments for configured-safe tools, full shell emulation, and OS-level sandboxing.

Validation:
- Focused CLI runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "environment_blocks"` passed with 10 tests.
- Focused API gate: `python -m pytest -q tests\test_api.py -k "blocked_environment_override"` passed with 5 tests.
- Broader affected suites: `python -m pytest -q tests\test_cli_runtime.py tests\test_api.py` passed with 242 tests and 2 skipped.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 965 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed after formatting.

Next:
- Continue Sprint 15 with shell profile/AutoRun command-line hardening or managed hook-policy foundations; defer web retrieval enforcement until a concrete retrieval runtime exists and defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009l CLI Executable Path Host-Boundary Enforcement

Status: completed for the scoped CLI executable path host-boundary slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, shell startup-hook/preload environment hardening, bare executable PATH trust policy, and command-specific path argument hardening for configured-safe tools.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected executable path boundary enforcement as the next bounded Sprint 15 CLI host-boundary slice after BL-009k.
- Completed: Security/Explorer confirmed CLI cwd checks, read-only path operand checks, and shell-wrapper inspection already existed, while explicit executable paths such as `../tool`, `/bin/cat`, Windows absolute paths, and launcher payloads could be a bounded host-boundary gap.
- Completed: Developer preserved basename policy matching for normal commands while retaining the raw executable token for non-downgradable rootDir boundary checks.
- Completed: Developer blocked explicit executable paths that resolve outside `rootDir` for direct commands, common shell wrappers, and PowerShell launcher payloads before configured safe rules or approvals can permit execution.
- Completed: QA added command-policy, CLI runtime, and API regressions for direct path escapes, shell-wrapped path escapes, launcher payload path escapes, configured-safe downgrade attempts, and inside-root executable path compatibility.
- Completed: PM updated README, architecture, setup/usage docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: command policy stores the raw executable token alongside the normalized executable name so path-bearing executables can be checked against `rootDir` without breaking existing basename rule matching.
- Implemented in this slice: direct commands, shell-wrapped commands, and PowerShell `Start-Process`/launcher payloads fail closed when the executable path resolves outside `rootDir`.
- Implemented in this slice: configured `autopilot_safe` rules cannot downgrade explicit executable path escapes, while executable paths inside `rootDir` can still use normal policy rule behavior.
- Still out of scope after this slice: shell startup hook and preload environment hardening, bare executable PATH trust policy, command-specific path arguments such as configured-safe tool working-directory flags, full shell emulation, and OS-level sandboxing.

Validation:
- Focused command-policy gate: `python -m pytest -q tests\test_command_policy.py -k "executable_path or configured_safe_rules_do_not_downgrade_executable_path or inside_root_keep_normal or shell_command_name_escapes or start_process_payload_blocks or flow_tokens or priority_and_scope"` passed with 48 tests.
- Focused CLI runtime gate: `python -m pytest -q tests\test_cli_runtime.py -k "executable_path_escape"` passed with 1 test.
- Focused API gate: `python -m pytest -q tests\test_api.py -k "executable_paths_outside_root or executable_path_escape"` passed with 6 tests.
- Broader affected suites: `python -m pytest -q tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py` passed with 513 tests and 2 skipped.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 952 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with CLI startup-hook/preload environment hardening or managed hook-policy foundations; defer web retrieval enforcement until a concrete retrieval runtime exists and defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009k Local Encrypted Credential-Vault References

Status: completed for the scoped local encrypted credential-vault reference slice; Sprint 15 remains active for richer user/group identity workflows, vault key rotation or managed KMS integration beyond the operator-supplied local vault key, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, and broader CLI host-boundary enforcement.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected a bounded local credential-vault slice after BL-009j because there is no web retrieval runtime to guard yet and encrypted credential storage was the highest-value remaining Sprint 15 security gap.
- Completed: Architect/Security scope confirmed local vaulting is acceptable only with an explicit operator-provided Fernet key in `DGENTIC_CREDENTIAL_VAULT_KEY`; DGentic does not generate, persist, escrow, rotate, or recover the vault key in this slice.
- Completed: Developer added `cryptography`/Fernet support, `credential_vault_key` settings, and a `local_vault` credential source that stores ciphertext in `credential-references.json`.
- Completed: Developer preserved provider runtime's fail-fast ordering so credential decryption happens while building transport headers after approval/config/circuit gates and before provider approval claim.
- Completed: QA added credential API and provider runtime regressions for no plaintext persistence or response exposure, missing key create failure, transport-time vault use, wrong/missing/malformed key failure, and approval preservation before provider transport.
- Completed: Security review found one low API-detail issue around vault-key configuration errors; Developer changed credential-reference create failures to return a generic invalid-reference response and QA updated the regression.
- Completed: PM updated `.env.example`, README, architecture, setup/usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/credentials/references` supports `source_type: "local_vault"` with a create-only `secret_value` field encrypted by the operator-supplied `DGENTIC_CREDENTIAL_VAULT_KEY`.
- Implemented in this slice: credential views and audit metadata omit both raw secret values and vault ciphertext; persisted state stores only ciphertext plus safe metadata.
- Implemented in this slice: provider approval binding uses credential-reference identity digests, not plaintext; local-vault identities include the reference id and encrypted-secret digest.
- Implemented in this slice: missing, malformed, or wrong vault keys fail closed before provider transport and preserve approved provider approvals because approval claim still happens only after credential header construction succeeds.
- Still out of scope after this slice: DGentic-managed key generation, vault key rotation, key escrow/recovery, managed KMS integration, per-secret versioning UX, first-class external secret-manager APIs, richer user/group identity workflows, and non-provider network surfaces.

Validation:
- Focused credential API gate: `python -m pytest -q tests\test_auth.py -k "local_vault or credential_reference"` passed with 6 tests.
- Focused provider credential gate: `python -m pytest -q tests\test_provider_runtime.py -k "local_vault or credential_reference or process_credential or sanitized_environ"` passed with 13 tests.
- Broader auth/provider/API gates: `python -m pytest -q tests\test_auth.py tests\test_provider_runtime.py` passed with 188 tests; `python -m pytest -q tests\test_api.py -k "credential or external_provider or provider_generate"` passed with 46 tests.
- Lint/format gates: `python -m ruff check .` and `python -m ruff format --check .` passed before the final docs update.

Next:
- Continue Sprint 15 with broader CLI host-boundary policy, managed hook-policy foundations, or web retrieval network enforcement only after a concrete runtime surface exists; defer key rotation/KMS to a dedicated design slice.

### Sprint 15 BL-009j Generated-Tool Network Policy Guardrail

Status: completed for the scoped generated-tool Python socket network guardrail slice; Sprint 15 remains active for richer user/group identity workflows, encrypted local vaulting, first-class secret-manager adapters beyond the generic process-adapter bridge, web retrieval network enforcement, OS-level/non-Python generated-tool egress isolation, and broader CLI host-boundary enforcement.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected generated-tool outbound network policy enforcement as the next bounded Sprint 15 security slice after task-scoped orchestration context verification.
- Completed: Security/Reviewer scouting confirmed generated-tool Python socket egress was the main remaining non-provider network surface small enough to implement safely before encrypted local vault key-management design.
- Completed: Developer added parent-side network policy validation and sanitized subprocess handoff for generated-tool execution.
- Completed: Developer installed generated-tool runner guards before generated tool imports run, covering common Python socket connect, `connect_ex`, `create_connection`, and resolver APIs.
- Completed: QA added generated-tool runtime and API regressions for deny, approval-required, import-time egress, raw sockets, `connect_ex`, byte-string hosts, resolver-to-IP bypass attempts, allow/audit compatibility, invalid policy fail-fast behavior, and policy handoff redaction.
- Completed: Security review found bypasses around exposed original socket functions, `connect_ex`, resolver APIs, byte-string hosts, and allowed-hostname resolution under default-deny. Developer remediated each finding and QA locked the behaviors with focused regressions.
- Completed: PM updated README, architecture, setup/usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: generated-tool execution validates `DGENTIC_NETWORK_DOMAIN_POLICY` before subprocess launch and fails before usage counters change when the policy is invalid.
- Implemented in this slice: the generated-tool runner receives only sanitized `default_mode` plus rule `domain`/`mode` data, drops rule reasons and hostile inherited handoff variables from generated-tool visibility, and installs Python socket/resolver guards before importing generated tool code.
- Implemented in this slice: `allow` and `audit` network modes proceed for common generated-tool Python socket egress, while `deny` and `approval_required` fail the generated tool run and record it as a failed execution.
- Still out of scope after this slice: OS-level network sandboxing, native-code or subprocess egress isolation, web retrieval enforcement, `network_approval_id` support for generated-tool egress, port-scoped network approval precision, richer user/group identity workflows, encrypted local credential vaulting, first-class provider-specific secret-manager APIs, and broader CLI host-boundary enforcement.

Validation:
- Focused generated-tool network gate after security-review remediation: `python -m pytest -q tests\test_tool_runtime.py -k "network_domain_policy or network_policy or connect_ex or byte_hosts or resolver"` passed with 13 tests.
- Broader affected suites: `python -m pytest -q tests\test_tool_runtime.py tests\test_api.py tests\test_network_policy.py` passed with 220 tests.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 929 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with encrypted local credential vaulting only after a key-management design slice, or with web retrieval network enforcement / broader CLI host-boundary policy if those remain higher-risk and better bounded.

### Claude Code Repository Study And DGentic Incorporation Plan

Status: completed for planning and architecture incorporation; no Anthropic source code or plugin content was copied.

Completed:
- PM studied the public Claude Code repository structure, plugin examples, command workflow examples, settings examples, and license boundary.
- Architect mapped reusable product patterns into DGentic-native concepts: terminal-first command recipes, plugin bundles, hook-style safety policies, managed settings, specialized review workflows, and git/PR workflow automation.
- PM added `docs/architecture/claude-code-incorporation-study.md` to record the incorporation plan and license boundary.
- PM updated the Sprint 15 through Sprint 19 backlog so the patterns map into security policy, UI/settings, CLI/VS Code, CI/observability, and provider-adapter follow-up work.
- PM updated repository architecture planned layout with future `apps/cli`, `plugins`, and `config/managed-settings` areas.

Decisions:
- DGentic will not copy Claude Code implementation artifacts because the studied repository is marked all rights reserved.
- DGentic should implement original equivalents that fit its backend-first orchestration, approval, audit, auth, credential, network, and role-boundary model.
- The highest-leverage incorporation path is a DGentic-native plugin and command recipe layer, then UI/CLI/VS Code surfaces for those recipes and policies.

Next:
- Keep Sprint 15 focused on security follow-ups that enable hook policy records, managed settings, plugin trust controls, and pre-action safety checks.
- Use Sprint 16 and Sprint 17 to surface command recipes, plugins, hooks, managed settings, and git/PR workflow automation through the UI, dedicated CLI client, and VS Code extension.

### Sprint 15 BL-009i Task-Scoped Orchestration Agent Context Verification

Status: completed for the scoped active-task verification slice; Sprint 15 remains active for richer user/group identity workflows, encrypted local vaulting, first-class secret-manager adapters beyond the generic process-adapter bridge, non-provider network enforcement surfaces, and broader CLI host-boundary enforcement.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM selected task-scoped verification for caller-supplied orchestration agent context as the next bounded Sprint 15 security slice after provider network approval records.
- Completed: Architect/Security review confirmed CLI/tool active-context behavior was partially strict, while provider and network approval paths stored/digested `agent_id`, `agent_role`, and `task_id` without proving they matched a running orchestration task.
- Completed: Developer added a shared orchestration context verifier for CLI, generated-tool, provider, and network approval surfaces.
- Completed: Developer wired provider approval/generation/streaming and network approval create/validate/claim paths so partial or unmatched caller-supplied orchestration context fails closed while orchestration tasks are running.
- Completed: QA updated CLI/tool orchestration expectations and added provider, network approval, and API regressions for partial, mismatched, and matching active task context.
- Completed: Reviewer/Security found two P2 follow-ups: avoid broad API `PermissionError` catches on provider routes and document/test stale known-task CLI context. Developer introduced a dedicated orchestration-context authorization exception, preserved sanitized OS permission failures, and QA added stale known-task CLI regressions.
- Completed: PM updated README, architecture, setup/usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: a shared task-context authorization helper now requires complete `agent_id`, `agent_role`, and `task_id` when supplied context is evaluated during active orchestration work.
- Implemented in this slice: CLI, generated-tool, provider, and network approval surfaces reject partial or unmatched supplied orchestration context while any running orchestration task exists, and allow exact active task matches.
- Implemented in this slice: provider and network approval digests still bind request payloads to the supplied actor/task context, but approval creation and execution now also verify that active orchestration context before credential lookup, transport, or approval claim side effects.
- Still out of scope after this slice: deriving agent/task identity from server-side agent-scoped credentials instead of request bodies, richer user/group identity workflows, encrypted local credential vaulting, first-class provider-specific secret-manager APIs, non-provider network enforcement surfaces, and broader CLI host-boundary enforcement.

Validation:
- Focused active-context and reviewer-follow-up gates: `python -m pytest -q tests\test_orchestration.py -k "cli_binding or known_non_running or provider_and_network_context"`, `python -m pytest -q tests\test_command_policy.py -k "orchestration_context or known_non_running"`, `python -m pytest -q tests\test_cli_runtime.py -k "orchestration_context or known_non_running"`, and `python -m pytest -q tests\test_api.py -k "partial_active_orchestration_context or sanitizes_os_permission_errors"` passed with 29 focused tests.
- Broader affected suites: `python -m pytest -q tests\test_orchestration.py tests\test_command_policy.py tests\test_cli_runtime.py tests\test_tool_runtime.py tests\test_provider_runtime.py tests\test_network_policy.py` passed with 616 tests and 2 skipped; `python -m pytest -q tests\test_api.py` passed with 158 tests.
- Full regression gate: `python -m pytest -q --maxfail=1 -x` passed with 913 tests and 2 skipped after an earlier full-suite attempt timed out without pytest output.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with non-provider network enforcement surfaces or encrypted credential vaulting only after key-management design is ready.

### Sprint 15 BL-009h Network Approval Records

Status: completed for the scoped provider-call network approval record slice; Sprint 15 remains active for richer user/group identity workflows, encrypted local vaulting, first-class secret-manager adapters beyond the generic process-adapter bridge, non-provider network enforcement surfaces, task-scoped agent-context verification, and broader CLI host-boundary enforcement.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected network approval records as the next bounded Sprint 15 security slice after authenticated audit actor propagation.
- Completed: Architect and QA scouts confirmed the existing provider, CLI, and generated-tool approval families as the safest implementation pattern.
- Completed: Developer added `network-approvals.json` records with pending/approved/denied/executed states, redacted safe review metadata, HMAC URL/policy/approval digests, TTLs, list/review/approve/deny APIs, and authenticated requester/decider binding.
- Completed: Developer wired provider egress so `approval_required` network-domain decisions can proceed only with a bound single-use `network_approval_id`, while deny decisions and provider base URL allowlists still fail closed.
- Completed: QA added network approval lifecycle, redaction, drift/denied/expired, provider transport, API lifecycle, route capability, and authenticated actor-binding regressions.
- Completed: PM updated README, architecture, setup/usage, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: provider generation and streaming can now satisfy approval-required network-domain policy through a bound `network_approval_id` instead of treating the mode as unavailable.
- Implemented in this slice: network approval records persist only sanitized URL previews, digests, policy metadata, context, and decisions; URL query/fragment secrets and secret-shaped actor/reason text are redacted from persistence and responses.
- Still out of scope after this slice: non-provider network enforcement surfaces such as web retrieval and generated-tool outbound network access, richer user/group identity workflows, encrypted local credential vaulting, first-class provider-specific secret-manager APIs, and stronger verification for body-supplied orchestration agent context (`agent_id`, `agent_role`, `task_id`).

Validation:
- Focused network approval gate: `python -m pytest -q tests\test_network_policy.py tests\test_provider_runtime.py tests\test_api.py::test_network_approval_api_lifecycle_redacts_safe_metadata tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes tests\test_auth.py::test_persisted_token_uses_operator_id_for_approval_requesters_and_decisions` passed with 144 tests.
- Full regression gate: `python -m pytest -q` passed with 898 tests and 2 skipped.
- Lint/format/diff gates: `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with either task-scoped verification for caller-supplied orchestration agent context or non-provider network enforcement surfaces unless key-management design is ready for encrypted local credential vaulting.

## 2026-05-11

### Sprint 15 BL-009g Authenticated Audit Actor Propagation

Status: completed for the scoped authenticated audit actor propagation slice; Sprint 15 remains active for richer user/group identity workflows, encrypted local vaulting, first-class secret-manager adapters beyond the generic process-adapter bridge, network approval records, non-provider network surfaces, and task-scoped agent-context verification.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected audit actor propagation as the next bounded Sprint 15 security slice after credential resolver adapter plumbing.
- Completed: Security/Reviewer scouts identified spoofable direct execution/requester paths and audit events that still defaulted to `system`.
- Completed: Developer bound authenticated principals over body/query `requested_by` on direct CLI execution/runs, provider generation/streaming, and direct generated-tool execution while preserving unauthenticated development/test behavior.
- Completed: Developer added authenticated actor audit propagation for direct CLI approval execution, filesystem operations and policy checks, CLI command-policy rule creation/update/evaluation, provider generation/streaming, generated-tool approval/execution events, task execution, agent lifecycle/reconciliation, memory operations, tool registration/generation/governance, and session summaries.
- Completed: Developer blocked cross-principal direct CLI approval execution unless the authenticated principal has admin capability.
- Completed: QA added focused authenticated-spoofing regressions for CLI approval creation/decision/execution, direct CLI execution and async runs, filesystem audit events, CLI policy audit events, provider generation/streaming audit events, and generated-tool execution audit events.
- Completed: PM updated the backlog, README, setup/usage limitations, and this progress log.

Feature tracking:
- Implemented in this slice: authenticated principals now override caller-supplied requester metadata on high-risk direct execution/generation APIs before runtime binding and audit persistence.
- Implemented in this slice: audit `actor` fields now use the authenticated principal for the covered API-triggered filesystem, CLI, provider, tool, agent, memory, task, and session mutation surfaces.
- Still out of scope after this slice: richer user/group identity workflows, encrypted local credential vaulting, first-class provider-specific secret-manager APIs, network approval records, non-provider network surfaces, and stronger verification for body-supplied orchestration agent context (`agent_id`, `agent_role`, `task_id`).

Validation:
- Focused actor propagation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py::test_cli_approval_api_uses_authenticated_principal_as_reviewer tests\test_api.py::test_cli_approval_direct_execute_requires_bound_authenticated_requester tests\test_api.py::test_cli_execute_api_uses_authenticated_principal_over_body_requested_by tests\test_api.py::test_cli_runs_api_uses_authenticated_principal_over_body_requested_by tests\test_api.py::test_filesystem_api_uses_authenticated_principal_as_audit_actor tests\test_api.py::test_cli_policy_api_uses_authenticated_principal_as_audit_actor tests\test_api.py::test_external_provider_generate_api_uses_authenticated_principal_as_audit_actor tests\test_api.py::test_external_provider_generate_stream_api_uses_authenticated_principal_as_audit_actor tests\test_api.py::test_generated_tool_execute_api_uses_authenticated_principal_over_body_requested_by` passed with 9 tests.
- API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py` passed with 154 tests.
- Runtime/auth/policy gates: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py`, `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py`, `uv --cache-dir .uv-cache run pytest -q tests\test_command_policy.py`, and `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py` passed with 62 passed/2 skipped, 64 passed, 273 passed, and 38 passed respectively.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 892 tests and 2 skipped.
- Lint/format/diff gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with network approval records and non-provider network surfaces unless a dedicated key-management design is ready for encrypted local credential vaulting.

### Sprint 15 BL-009f Credential Resolver Adapter Plumbing

Status: completed for the scoped external credential resolver adapter slice; Sprint 15 remains active for richer user/group identity workflows, encrypted local vaulting, first-class secret-manager adapters beyond the generic process-adapter bridge, network approval records, non-provider network surfaces, and broader audit actor propagation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected process-adapter secret-manager plumbing instead of hand-rolled encrypted vaulting because local encryption needs a separate key-management design.
- Completed: Developer added credential `source_type` support with backward-compatible `env` references and new `external_process` references.
- Completed: Developer added bounded `DGENTIC_CREDENTIAL_PROCESS_ADAPTERS`, timeout, and max-output settings; process adapters run without a shell, require an absolute executable path, close stdin, receive a minimal environment, and get the reference `secret_name` appended as the final argument.
- Completed: Developer changed OpenAI-compatible provider runtime to resolve credential-reference secrets through the shared resolver only after pricing, configuration, circuit, and approval gates pass.
- Completed: QA added focused provider tests for process adapters running only at transport time, approval-required paths skipping adapter execution, revoked/wrong-purpose references skipping adapter execution, adapter failure preserving approvals, oversized stdout/stderr rejection, and no returned-secret persistence/logging.
- Completed: Security/Reviewer found a P2 buffering risk in the first `capture_output` implementation; Developer replaced it with bounded stream readers that kill the adapter when stdout or stderr exceeds the configured limit.
- Completed: Final Security/Reviewer found a P2 explicit-empty-environment fallback risk; Developer changed env-reference resolution to use host environment only when no mapping is supplied and QA added a sanitized-environment regression.
- Completed: PM updated environment, README, developer setup, usage, architecture, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: persisted credential references can now describe either an environment variable or a configured `external_process` adapter plus `secret_name`.
- Implemented in this slice: provider approval creation and provider listing validate external-process credential configuration without retrieving the secret; secret retrieval happens only while building transport headers after the provider request is otherwise eligible.
- Still out of scope after this slice: encrypted local credential vaulting, first-class provider-specific secret-manager APIs, credential version rotation UX, and broader audit actor propagation.

Validation:
- Focused credential API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py -k "external_process_credential_reference or credential_reference_lifecycle"` passed with 2 tests and 62 deselected.
- Focused provider adapter gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py -k "process_credential or external_process_reference_validation or external_generation_uses_configured_credential_reference or external_approval_rejects"` passed with 8 tests and 103 deselected.
- Final provider hardening gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py -k "sanitized_environ or process_credential"` passed with 6 tests and 108 deselected.
- Focused provider full file: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py` passed with 114 tests.
- Focused auth full file: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py` passed with 64 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 883 tests and 2 skipped.
- Lint/format/diff gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with broader audit actor propagation or network approval records unless encrypted local vault key-management design is ready to split into a dedicated architecture slice.

### Sprint 15 BL-009e Identity And Credential Metadata Redaction

Status: completed for the scoped cross-surface identity, auth-token, and credential-reference metadata redaction slice; Sprint 15 remains active for richer user/group identity workflows, encrypted local vaulting or external secret-manager adapters beyond env references, network approval records, non-provider network surfaces, and broader audit actor propagation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM kept the work in Full Sprint mode because the slice changes security-sensitive identity, credential, response, audit, and persistence behavior.
- Completed: Developer added source-only redaction for operator display/role fields, auth-token labels, and credential-reference labels on request validation, record load, view generation, audit metadata, and mutation persistence paths.
- Completed: QA added tests-only coverage for new metadata writes and legacy JSON state containing secret-shaped operator display/role values, auth-token labels, and credential-reference labels.
- Completed: Security/Reviewer found and Developer remediated the legacy persisted auth/operator metadata leak where request-only validators were insufficient.
- Completed: Reviewer confirmed no remaining implementation leak and flagged a P3 test sequencing gap; QA split legacy token list/rotate/revoke/expire checks so each mutation starts from raw legacy state.
- Completed: PM updated README, developer setup, usage, architecture, refined backlog, and this progress log.

Feature tracking:
- Implemented in this slice: operator display names and roles, generated auth-token labels, and credential-reference labels redact common secret-shaped values before API responses and audit metadata.
- Implemented in this slice: new writes and mutation rewrites persist redacted metadata for those fields; legacy read-only list/get responses are redacted without requiring a destructive migration.
- Still out of scope after this slice: encrypted local credential vaulting, external secret-manager adapters beyond environment references, network approval records, non-provider network surfaces, richer user/group identity workflows, and full audit actor propagation.

Validation:
- Focused metadata gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py -k "legacy_persisted_auth_metadata or legacy_credential_reference_label or credential_reference_label or redacts_secret_shaped_values"` passed with 4 tests and 59 deselected.
- Focused auth suite: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py` passed with 63 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 875 tests and 2 skipped.
- Lint/format/diff gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with encrypted local credential vaulting or external secret-manager adapter design unless broader audit actor propagation becomes the higher-risk blocker.

### Sprint 15 BL-009d Persisted Operator Identity And Assignment

Status: completed for the scoped persisted operator identity and capability-assignment slice; Sprint 15 remains active for richer identity workflows, encrypted local vaulting or external secret-manager adapters beyond env references, network approval records, non-provider network surfaces, audit propagation, and cross-surface no-secret-response validation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected persisted operator profiles and assignment-limited token issuance as the next bounded Sprint 15 slice after provider-call network guardrails.
- Completed: Architect/Security and QA read-only scouts recommended a tight identity slice before encrypted vaulting or network approval records.
- Completed: Developer added persisted operator records in `operators.json`, `/auth/operators` create/list/get/update APIs, role/display metadata, active/inactive status, and capability normalization.
- Completed: Developer changed new persisted token creation to require an active operator and reject requested capabilities outside that operator's assignment.
- Completed: Developer changed persisted token authentication and rotation to respect linked operator status and current assignment while preserving legacy persisted tokens that predate operator profiles.
- Completed: QA updated focused auth/API tests for operator lifecycle, duplicate/unknown-capability rejection, assignment-limited token issuance, deactivated-operator token rejection, capability reduction, legacy persisted-token compatibility, existing token lifecycle behavior, credential capability gates, approval actor binding, and capability mapping.
- Completed: PM updated README, setup/usage docs, repository architecture, backlog status, and this progress log.

Feature tracking:
- Implemented in this slice: operators can be created, listed, retrieved, updated, and deactivated through auth-protected APIs.
- Implemented in this slice: operator capabilities are normalized and become the assignment source for new persisted token issuance.
- Implemented in this slice: new tokens cannot be issued for missing or inactive operators and cannot exceed assigned operator capabilities.
- Implemented in this slice: deactivating an operator fails closed for linked persisted tokens and token rotation.
- Implemented in this slice: legacy persisted tokens without operator profiles remain compatible to avoid upgrade lockout.
- Implemented in this slice: operator lifecycle audit events record safe metadata without raw bearer token values.

Remaining Sprint 15 work:
- Richer user/group identity workflows beyond persisted operator profiles.
- Encrypted local credential vaulting or external secret-manager adapters beyond environment-variable references.
- Network approval records and enforcement expansion to non-provider surfaces such as web retrieval and generated-tool network access.
- Broader audit actor propagation and cross-surface no-secret-response validation.

Validation:
- Focused auth suite: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py` passed with 59 tests.
- Focused auth/API security gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py tests\test_api.py -k "auth or token or operator or credential or approval"` passed with 86 tests and 119 deselected.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 871 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .` and `uv --cache-dir .uv-cache run ruff format --check .` passed.

Next:
- Continue Sprint 15 with encrypted/external secret-manager support beyond env references unless audit propagation becomes the higher-risk blocker.

### Sprint 15 BL-009c Network Domain Guardrails

Status: completed for the scoped provider-call network/domain guardrail slice; Sprint 15 remains active for broader identity, encrypted local vaulting or external secret-manager adapters beyond env references, network approval records, non-provider network surfaces, audit propagation, and cross-surface no-secret-response validation.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected network/domain guardrails as the next bounded Sprint 15 slice after external credential references.
- Completed: Developer added `DGENTIC_NETWORK_DOMAIN_POLICY`, a network policy evaluator, and `POST /guardrails/network`.
- Completed: Developer wired provider egress through the shared provider validator so runtime generation, provider health/list display, and configured provider base URL validation all honor the network policy before outbound transport.
- Completed: Developer added a dedicated `network` capability for `/guardrails/network`.
- Completed: QA added focused tests for default allow behavior, exact/wildcard/default policy decisions, approval-required decisions, malformed config rejection, provider fail-closed behavior before transport, audit-mode transport allowance, guardrail API responses, and auth capability mapping.
- Completed: PM updated `.env.example`, README, setup/usage docs, repository architecture, backlog status, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_NETWORK_DOMAIN_POLICY` accepts JSON with `default_mode` and ordered `rules`.
- Implemented in this slice: network rules support exact domains and wildcard subdomains such as `*.example.test`.
- Implemented in this slice: network policy modes are `allow`, `deny`, `approval_required`, and `audit`; `allow` and `audit` proceed, while `deny` and `approval_required` fail closed for provider calls until a future network approval workflow exists.
- Implemented in this slice: `/guardrails/network` returns safe network policy decisions without making outbound network requests.
- Implemented in this slice: provider generation fails before transport when network policy denies or requires approval for the configured provider host.

Remaining Sprint 15 work:
- Broader persisted operator identity records and assignment workflows.
- Encrypted local credential vaulting or external secret-manager adapters beyond environment-variable references.
- Network approval records and enforcement expansion to non-provider surfaces such as web retrieval and generated-tool network access.
- Broader audit actor propagation and cross-surface no-secret-response validation.

Validation:
- Focused network/provider/auth/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_provider_generation_rejects_network_domain_policy_before_transport tests\test_provider_runtime.py::test_provider_generation_audit_network_domain_policy_allows_transport tests\test_api.py::test_guardrails_network_returns_policy_decision tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes tests\test_network_policy.py` passed with 27 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 865 tests and 2 skipped.
- Lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed after formatting `tests\test_network_policy.py`.
- Diff hygiene gate: `git diff --check` passed.

Next:
- Continue Sprint 15 with the highest-risk remaining production-security item: broader identity assignment workflows or encrypted/external secret-manager support beyond env references.

### Sprint 15 BL-009b External Credential References

Status: completed for the scoped external credential-reference slice; Sprint 15 remains active for broader identity, encrypted local vaulting, secret-manager adapters, audit propagation, and network/domain guardrails.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected external credential references as the next bounded Sprint 15 slice after persisted auth-token lifecycle.
- Completed: Security/Architect read-only assessment recommended an external secret-reference strategy instead of local encrypted credential storage without a key-management story.
- Completed: Developer added persisted credential-reference records for externally managed credential locations, currently environment variables, with create/list/revoke APIs and a dedicated `credentials` capability.
- Completed: Developer added credential audit events and `credential-references.json` local state without storing raw secret values.
- Completed: Developer added `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF` and wired OpenAI-compatible provider approvals/execution to bind a credential reference identity while resolving the actual secret only at transport time.
- Completed: Developer changed config-only provider listing, health, and routing to treat credential references as configured without reading secret values.
- Completed: QA added focused coverage for credential-reference capability gates, no raw secret persistence/echo, provider approval/execution through a configured credential reference, revoked-reference fail-closed behavior, and config-only provider/routing checks without secret-value lookup.
- Completed: PM updated `.env.example`, README, usage docs, developer setup, repository architecture, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `/credentials/references` creates and lists safe references to external credential locations.
- Implemented in this slice: `/credentials/references/{credential_ref_id}/revoke` disables a reference so provider approval and execution fail closed before secret lookup.
- Implemented in this slice: external OpenAI-compatible provider configuration can use `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF` while preserving the legacy env-var setting.
- Implemented in this slice: provider approval binding digests cover the configured credential reference identity, not the raw secret, and provider configuration rejects credential references created for non-provider purposes.
- Implemented in this slice: provider listing, health, and routing remain config-only and do not need to read credential values.

Remaining Sprint 15 work:
- Broader persisted operator identity records and assignment workflows.
- Encrypted local credential vaulting or external secret-manager adapters beyond env references.
- Network/domain guardrail policy with allow, deny, approval-required, and audit modes.
- Broader audit actor propagation and cross-surface no-secret-response validation.

Validation:
- Focused credential-reference/provider gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py tests\test_provider_runtime.py -k "credential_reference or external_generation_uses_configured_credential_reference or revoked_credential_reference or runtime_purpose or capability_for_path"` passed with 22 tests and 133 deselected.
- Focused API credential-reference gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "credential_reference or configured_external_provider_with_credential_reference or configured_external_provider_health"` passed with 2 tests and 143 deselected.
- Broad auth/provider/API security gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py tests\test_provider_runtime.py tests\test_api.py -k "auth or credential or provider or routing or approval"` passed with 237 tests and 63 deselected.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 856 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 15 with network/domain guardrail policy unless a broader persisted identity slice becomes the higher-risk blocker.

### Sprint 15 BL-009a Persisted Auth Token Lifecycle

Status: completed for the scoped persisted auth-token lifecycle slice; Sprint 15 remains active for broader identity, secrets, and network guardrails.

Current story:
- BL-009: Production Identity, Secret Management, And Network Guardrails.

Checklist:
- Completed: PM/Architect selected persisted generated bearer-token lifecycle as the first bounded Sprint 15 slice after Sprint 14 closed.
- Completed: Developer added persisted `auth-tokens.json` records with salted PBKDF2 token hashes, one-time raw token return on create/rotate, token listing without raw values or hashes, rotation, revocation, expiry, active-token startup bootstrap, and `DGENTIC_AUTH_TOKENS` compatibility.
- Completed: Developer added an `auth` capability group, auth-token management API routes, auth audit events, persisted-token operator-id actor binding, UTC normalization for token datetimes, inactive-token rotation rejection, nonblank operator-id validation, and expiry preservation on rotation unless a new expiry is explicitly supplied.
- Completed: Developer bound authenticated approval creation requesters and approval decisions to the authenticated principal actor while preserving caller-supplied requester fallbacks for no-auth/local paths.
- Completed: QA added focused coverage for persisted token hashing/restart/bootstrap, rotation/revocation/expiry, inactive rotation rejection, explicit expire endpoint behavior, auth-token management capability checks, env-token coexistence, no raw-token log/response echo, and operator-id binding for CLI/provider/tool approval requesters plus CLI decisions.
- Completed: Read-only QA found spoofable approval creation `requested_by` and inactive-token rotation revival risks; Developer and QA remediated both before checkpoint.
- Completed: PM updated README, usage docs, developer setup, repository architecture, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: persisted bearer tokens are generated by the server, stored only as salted PBKDF2 hashes, and returned raw only in create/rotate responses.
- Implemented in this slice: persisted tokens can be listed, rotated, revoked, and expired through protected auth-token management endpoints; inactive tokens cannot be rotated back to active.
- Implemented in this slice: production/staging startup can proceed with active persisted tokens after bootstrap environment tokens are removed.
- Implemented in this slice: persisted tokens carry an `operator_id` used as the request actor for approval requester/decision paths and orchestration/memory owner scoping.
- Implemented in this slice: auth lifecycle events record safe metadata without raw bearer values.

Remaining Sprint 15 work:
- Broader persisted operator identity records and assignment workflows.
- Encrypted credential storage or external secret-manager integration for provider/runtime secrets.
- Network/domain guardrail policy with allow, deny, approval-required, and audit modes.
- Broader audit actor propagation and cross-surface no-secret-response validation.

Validation:
- Focused auth lifecycle gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py` passed with 50 tests.
- Focused approval/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "approval or authenticated or owner or token"` passed with 26 tests and 118 deselected.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 850 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .` and `uv --cache-dir .uv-cache run ruff format --check .` passed.

Next:
- Continue Sprint 15 with the next highest-risk production-security slice: encrypted credential storage or external secret-manager integration, then network/domain guardrails.

### Sprint 14 BL-008q Scheduler Lease And Fencing Hardening

Status: completed for the backend MVP scope; Sprint 14 autonomous agent orchestration is closed.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected production scheduling lease/fencing as the final Sprint 14 blocker after detached worker restart adoption.
- Completed: Developer added a JSON-backed run-level scheduler lease collection with private lease tokens, public execution lease ids, lease acquisition/release/renewal helpers, and active background execution conflict handling for foreground advance/cycle/loop scheduling.
- Completed: Developer changed scheduling to persist pending-to-running task claims with fixed agent ids before spawning agents, repair missing agent rows with the persisted id, and roll back unspawned claims when agent spawn fails.
- Completed: Developer added stale-update conflict detection for scheduling mutations and moved agent terminal updates until after the guarded run write succeeds.
- Completed: Developer required background-owned task updates to hold the current scheduler lease, preflighted detached execution start against active foreground leases, released queued-execution leases on cancellation, and finalized executions that lost their scheduler lease as stale instead of leaving active records wedged.
- Completed: QA added focused service/API coverage for concurrent scheduler fencing, foreground scheduler conflicts during detached execution, detached start rejection during active foreground scheduling, stale background write rejection, lost-lease stale finalization, startup adoption with scheduler leasing, spawn-failure rollback/retry, and API non-exposure of private scheduler lease tokens.
- Completed: Reviewer/Security/DevOps findings were remediated for stale background writes, background-start conflict behavior, lost-lease finalization, pre-persist agent mutation, and stale `run_cycle` overwrites.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: scheduler passes now acquire a durable run-level lease before claiming ready tasks.
- Implemented in this slice: ready tasks transition to `running` with fixed agent ids in persisted run state before agent spawn occurs, preventing duplicate spawn from stale snapshots.
- Implemented in this slice: if a scheduler crashes after claim but before agent persistence, the next leased scheduler repairs by spawning the same persisted agent id.
- Implemented in this slice: if agent spawn fails before an agent row exists, the task claim rolls back to pending and the private lease is released so retry can proceed.
- Implemented in this slice: detached workers hold and renew private scheduler leases; foreground advance/cycle/loop calls return conflict while a detached execution owns the run.
- Implemented in this slice: stale background workers that lose the scheduler lease cannot persist task completions/failures, and lost-lease finalization marks the execution stale.
- Implemented in this slice: execution API records expose `scheduler_lease_id` only; private lease tokens stay in the local scheduler-lease collection.

Remaining Sprint 14 work:
- None for the backend MVP orchestration scope.

Validation:
- Focused scheduler lease service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "scheduler_lease or background_execution_start_rejects or background_task_update_requires or finalize_marks_lost or task_update_during_detached"` passed with 7 tests.
- Focused scheduler lease API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "background_execution_cancel_starting or background_execution_start_poll_and_list or advance_and_cycle_reject_active_background_execution"` passed with 3 tests.
- Broader orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 109 tests.
- Broader orchestration/background API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration or background_execution"` passed with 35 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 837 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Initiate Sprint 15 for production identity, secrets, and network guardrails.

### Sprint 14 BL-008p Detached Worker Restart Adoption

Status: completed for the scoped detached worker restart adoption/resume slice; Sprint 14 remains active for production scheduling/lease hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected detached worker restart adoption/resume as the next bounded Sprint 14 slice after shared-memory policy and exposure hardening.
- Completed: Developer changed orchestration service startup to adopt expired prior-supervisor `starting` and `running` background executions for open runs instead of marking every expired active record stale.
- Completed: Developer preserved the original execution id and request, transferred supervisor ownership, refreshed heartbeat metadata, and resumed the existing bounded loop through the normal worker path.
- Completed: Developer finalized expired `cancelling` records as `cancelled`, skipped closed/non-resumable runs as `stale`, skipped duplicate stale records for the same run, and finalized adoption start failures as redacted `failed` records.
- Completed: QA added focused restart-adoption tests for expired running adoption, expired cancellation finalization, no duplicate agent spawn for already-running tasks, closed-run skip behavior, and adoption start-failure recovery.
- Completed: DevOps review confirmed production scheduler leases/fencing remain the final Sprint 14 hardening blocker.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: process startup can resume an abandoned detached orchestration execution once the previous supervisor heartbeat is expired.
- Implemented in this slice: adopted executions keep their existing execution id and request, then continue through the normal bounded loop and finalization machinery.
- Implemented in this slice: already-running tasks keep their existing `agent_id` during adoption, avoiding duplicate sub-agent spawn on restart.
- Implemented in this slice: stale `cancelling` executions become terminal `cancelled`, while closed-run or duplicate stale executions are not resumed.
- Implemented in this slice: adoption worker start failures are persisted as failed records with redacted errors and no pinned active execution.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.

Validation:
- Focused background execution service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "background_execution"` passed with 20 tests.
- Focused background execution API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "background_execution or operations_summary"` passed with 8 tests.
- Broader orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 101 tests.
- Broader orchestration/background API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration or background_execution or operations_summary"` passed with 34 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 828 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 14 with production scheduling lease/fencing hardening.

### Sprint 14 BL-008o Shared-Memory Reuse Policy And Exposure Hardening

Status: completed for the scoped shared-memory reuse policy and API exposure hardening slice; BL-008p later completed detached worker restart adoption/resume, and Sprint 14 remains active for production scheduling/lease hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected shared-memory reuse policy hardening as the next bounded Sprint 14 slice after operations summary surfacing.
- Completed: Developer added `shared_memory_policy` to orchestration create/run contracts with backward-compatible default `owner` behavior and stricter `run` behavior.
- Completed: Developer preserved same-run shared-memory reuse under `run` policy while blocking cross-run reuse if either the source run or consumer run is run-scoped.
- Completed: Security review found shared-memory context exposure through unscoped agent/memory reads and public `orchestration_context` metadata writes; Developer remediated with owner/admin-scoped orchestration agent and shared-memory metadata reads, public create/patch/delete blocking for `orchestration_context`, tampered service-row exclusion, and bulk mutation guardrails for non-admin callers.
- Completed: QA added service/API tests for source-side and consumer-side run-policy blocking, default/explicit API contract behavior, invalid policy validation, tampered metadata exclusion, public metadata write blocking, owner-scoped agent reads, and owner-scoped shared-memory metadata reads.
- Completed: Reviewer reported no implementation blockers after reviewing default compatibility, persistence defaults, same-run in-flight reuse, and missing-source fail-closed behavior.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `shared_memory_policy="owner"` remains the default and preserves same-owner cross-run reuse after provenance, lifecycle, tag, and owner checks pass.
- Implemented in this slice: `shared_memory_policy="run"` confines reuse to the same orchestration run when either the producer or consumer run chooses that policy.
- Implemented in this slice: same-run memory reuse works against the current in-flight run state instead of a stale persisted run snapshot.
- Implemented in this slice: shared-memory provenance validation now rejects tampered rows whose tags or description no longer match the completed source task.
- Implemented in this slice: public metadata create/patch/delete routes reject `category="orchestration_context"` so orchestration shared-memory rows remain service-authored.
- Implemented in this slice: when auth is enabled, non-admin `/agents` and `/api/v1/memory/*` reads only expose orchestration agent/shared-memory context owned by the authenticated actor; admin tokens retain all-run visibility.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Detached worker restart adoption/resume was completed later in BL-008p.

Validation:
- Focused shared-memory service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "shared_memory"` passed with 9 tests.
- Focused shared-memory/security API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "shared_memory or orchestration_metadata or agent_reads"` passed with 8 tests.
- Broader orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 96 tests.
- Broader API memory/orchestration/agent gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration or shared_memory or memory or agent"` passed with 38 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 823 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 14 with production scheduling/lease hardening.

### Sprint 14 BL-008n Orchestration Operations Summary

Status: completed for the scoped operations summary slice; BL-008o later completed shared-memory reuse policy and API exposure hardening, BL-008p later completed detached worker restart adoption/resume, and Sprint 14 remains active for production scheduling/lease hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected owner-scoped operations surfacing as the next bounded Sprint 14 slice after detached execution cancellation.
- Completed: Developer added an `OrchestrationOperationsSummary` contract, service-level summary aggregation, and `GET /tasks/orchestrations/operations/summary`.
- Completed: Developer kept summary output to counts and ids only, avoiding objective, output, error, resolution, or secret-bearing text.
- Completed: QA added service/API tests for run/task/execution status counts, active/stale execution ids, blocker/follow-up totals, and owner/admin scoping.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: operators can retrieve visible orchestration run counts, task counts, execution counts, active/stale execution ids, unresolved blocker totals, and open follow-up totals from one endpoint.
- Implemented in this slice: summary access follows the same owner/admin visibility model as orchestration run listing.
- Implemented in this slice: the summary route is registered before `{run_id}` lookup to avoid path capture by the dynamic route.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Shared-memory reuse policy and API exposure hardening was completed later in BL-008o.
- Detached worker restart adoption/resume was completed later in BL-008p.

Validation:
- Focused summary service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "operations_summary"` passed with 2 tests.
- Focused summary API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "operations_summary"` passed with 1 test.
- Broader orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 93 tests.
- Broader orchestration API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration"` passed with 28 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 814 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 14 with production scheduling/lease hardening.

### Sprint 14 BL-008m Detached Orchestration Execution Cancellation

Status: completed for the scoped detached-execution cancellation slice; BL-008n later completed operations summary surfacing, BL-008o later completed shared-memory reuse policy and API exposure hardening, BL-008p later completed detached worker restart adoption/resume, and Sprint 14 remains active for production scheduling/lease hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected detached execution cancellation as the next bounded Sprint 14 slice after owner/provenance-scoped shared memory.
- Completed: Developer added `cancelling` and `cancelled` execution states, a cooperative cancel service flow, loop cancellation checks, and a cancel API endpoint.
- Completed: Developer kept `cancelling` records active until owning-worker finalization so duplicate detached executions and foreground loops remain blocked during cancellation.
- Completed: QA added service/API coverage for queued cancellation, running cancellation, terminal conflict behavior, owner/admin API scoping, retry after queued cancellation, and preserving task/agent work when the detached execution is cancelled.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: API callers can cancel detached orchestration executions with `POST /tasks/orchestrations/{run_id}/executions/{execution_id}/cancel`.
- Implemented in this slice: queued `starting` executions can move directly to `cancelled` and allow a retry execution.
- Implemented in this slice: running executions move to `cancelling`, remain active for conflict checks, and finalize as `cancelled` when the cooperative loop observes the request.
- Implemented in this slice: cancelling a detached execution stops only the detached orchestration loop; it does not cancel spawned tasks or agents.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.
- Shared-memory reuse policy and API exposure hardening was completed later in BL-008o.
- Detached worker restart adoption/resume was completed later in BL-008p.

Validation:
- Focused cancellation service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "background_execution_cancel"` passed with 5 tests.
- Focused cancellation API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "background_execution_cancel"` passed with 3 tests.
- Broader orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 91 tests.
- Broader orchestration API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration"` passed with 27 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 811 tests and 2 skipped.
- Lint/format gates: `uv --cache-dir .uv-cache run ruff check .`, `uv --cache-dir .uv-cache run ruff format --check .`, and `git diff --check` passed.

Next:
- Continue Sprint 14 with production scheduling/lease hardening.

### Sprint 14 BL-008l Opt-In Orchestration Shared Memory

Status: completed for the scoped explicit-tag, owner/provenance-scoped shared-memory slice; BL-008n later completed operations summary surfacing, BL-008o later completed shared-memory reuse policy and API exposure hardening, BL-008p later completed detached worker restart adoption/resume, and Sprint 14 remains active for production scheduling/lease hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected explicit-tag SQL shared memory as the next safe Sprint 14 slice after detached background execution.
- Completed: Developer added `shared_memory_tags` to orchestration create/run/task contracts, SQL metadata upsert by entity id, metadata tag filtering, completed-task memory publishing, and bounded matching memory summaries in spawned agent context.
- Completed: Reviewer/Security identified global tag-namespace leakage risk; Developer remediated with completed-task provenance checks, owner-scope filtering, stricter tag authorization, and duplicate-resilient metadata upsert behavior.
- Completed: Developer made shared-memory publish/retrieval fail soft with redacted audit events so scheduling and task updates are not blocked by SQL metadata issues.
- Completed: QA added tests for durable tagged memory publish/reuse, no-tag behavior, inactive-memory exclusion, API-visible agent context, metadata tag filtering, owner scoping, spoofed metadata exclusion, fail-soft SQL behavior, duplicate upsert behavior, and secret redaction.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: orchestration runs and tasks can opt into shared context with explicit `shared_memory_tags`.
- Implemented in this slice: completing a tagged task upserts one deterministic SQL metadata record with category `orchestration_context` and a redacted, bounded task-output summary.
- Implemented in this slice: later tagged tasks receive up to three active matching shared-memory summaries in spawned agent brief context after objective/dependency context.
- Implemented in this slice: shared-memory context injection requires completed orchestration-task provenance, the same authenticated orchestration owner or local `system` owner, active lifecycle state, and consumer tags that cover all stored record tags.
- Implemented in this slice: archived or soft-pruned SQL metadata is excluded by default through active lifecycle filtering.
- Implemented in this slice: the metadata list API accepts `tags` query parameters for tag-filter verification and consumers.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.
- Shared-memory reuse policy and API exposure hardening was completed later in BL-008o.
- Detached worker restart adoption/resume was completed later in BL-008p.

Validation:
- Focused shared-memory gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "shared_memory"` passed with 6 tests.
- Focused API shared-memory gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "shared_memory"` passed with 2 tests.
- Broader orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 86 tests.
- Broader API/memory gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration or memory"` passed with 27 tests.
- Metadata/memory adjacent gate: `uv --cache-dir .uv-cache run pytest -q tests\test_memory_lifecycle_service.py tests\test_retrieval_service.py tests\test_database.py tests\test_metadata_service.py` passed with 35 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\schemas.py src\dgentic\memory\metadata_service.py src\dgentic\memory\models.py src\dgentic\api\memory_routes.py tests\test_orchestration.py tests\test_api.py` passed.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 803 tests and 2 skipped.

Next:
- Continue Sprint 14 with production scheduling/lease hardening.

### Sprint 14 BL-008k Detached Background Orchestration Execution

Status: completed for the scoped detached process-local execution slice; BL-008n later completed operations summary surfacing, BL-008o later completed shared-memory policy/exposure hardening, BL-008p later completed detached worker restart adoption/resume, and Sprint 14 remains active for production scheduling/lease hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected detached background orchestration execution as the next Sprint 14 slice after bounded synchronous loops and generated project-document sync.
- Completed: Developer added persisted orchestration execution records, process-local detached worker launch, start/list/get API endpoints, and active execution conflict handling.
- Completed: Developer hardened execution claims through JSON collection transactions, owner/status-conditional running/finalization updates, stale-supervisor reconciliation, launch/pre-run failure finalization, and heartbeat renewal for live detached workers.
- Completed: QA added service/API tests for lifecycle polling, duplicate active rejection, owner scoping, stale reconciliation, stale/foreign finalization preservation, launch/pre-run failure cleanup, foreground-loop conflict rejection, heartbeat freshness, and error redaction.
- Completed: Reviewer/Security identified stale polling, launch failure, heartbeat, and foreground-loop race risks; Developer/QA remediated them and re-review found no blockers.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /tasks/orchestrations/{run_id}/executions` starts a detached process-local bounded orchestration loop and returns a persisted execution record with `202 Accepted`.
- Implemented in this slice: `GET /tasks/orchestrations/{run_id}/executions` and `GET /tasks/orchestrations/{run_id}/executions/{execution_id}` list and poll detached execution records.
- Implemented in this slice: execution records persist request, result, requester, supervisor id, status reason, redacted error, start/completion timestamps, and heartbeat timestamp.
- Implemented in this slice: a run rejects duplicate active detached executions and rejects foreground `/loop` execution while a detached execution is active.
- Implemented in this slice: stale foreign-supervisor active records are reconciled on start and poll after the heartbeat timeout, while live process-local workers renew heartbeat during execution.
- Implemented in this slice: launch and pre-run failures finalize as failed records with redacted errors instead of pinning a same-supervisor active execution.
- Implemented in this slice: finalization is conditional on active status and matching supervisor ownership so stale or foreign-owned records are not overwritten.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.
- Durable shared-memory coordination was completed later in BL-008l.
- Shared-memory policy/exposure hardening was completed later in BL-008o.
- Detached worker restart adoption/resume was completed later in BL-008p.

Validation:
- Focused detached execution gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py -k "background_execution or detached"` passed with 14 tests.
- Focused orchestration/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py` passed with 211 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\api\routes.py src\dgentic\schemas.py src\dgentic\storage.py tests\test_orchestration.py tests\test_api.py README.md docs\planning\backlog-needs-to-be-done.md docs\architecture\repository-architecture.md docs\how-to\using-dgentic.md` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\api\routes.py src\dgentic\schemas.py src\dgentic\storage.py tests\test_orchestration.py tests\test_api.py` passed with 6 files already formatted.
- Diff whitespace gate: `git diff --check` passed with only Git LF/CRLF working-copy warnings.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 795 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 58 files already formatted.

Next:
- Continue Sprint 14 with production scheduling/lease hardening.

### Sprint 14 BL-008j Generated Orchestration Document Sync

Status: completed for the scoped generated project-document sync slice; later BL-008k/BL-008l/BL-008p slices completed detached background execution, durable shared-memory coordination, and detached restart adoption/resume, so Sprint 14 remains active for production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected a narrow generated-document slice for automatic progress/backlog updates without claiming full autonomous backlog management.
- Completed: Developer added generated orchestration document sync for `docs/progress/orchestration-runs.md` and `docs/planning/orchestration-follow-ups.md`.
- Completed: Developer scoped generated docs to fixed repository paths, redacted secret-shaped text, rejected symlinked generated-document paths, used atomic same-directory replacement, added a shared document-sync lock, and made sync failures audited/non-fatal after orchestration state persistence.
- Completed: Developer added direct task-update audit events for status transitions, retry counts, new blocker/follow-up ids, scheduled task ids, redacted errors, and output keys.
- Completed: QA added tests for generated docs, open follow-up/blocker filtering, completed/resolved item removal, secret redaction, task-update audit metadata, symlinked parent/target failure audit, persistence after sync failure, and outside-write prevention.
- Completed: Reviewer/Security found doc-sync failure, audit, concurrency, and role-boundary/governance risks; Developer/PM remediated with non-fatal audit handling, task-update events, a sync lock, symlink hardening, and an explicit runtime-generated document exception in role-boundary governance.
- Completed: PM updated README, docs index, backlog, architecture docs, usage docs, role-boundary governance, and this progress log.

Feature tracking:
- Implemented in this slice: every orchestration persistence path attempts to regenerate the run-status and follow-up backlog documents from persisted orchestration state.
- Implemented in this slice: generated progress docs list run objective, status, timestamps, requester, scheduled tasks, task states, unresolved blockers, and DoD evidence.
- Implemented in this slice: generated follow-up docs list open follow-ups and unresolved blockers for non-completed runs, while resolved blockers and completed runs are excluded from the open backlog.
- Implemented in this slice: generated-document content is redacted for common secret-shaped values and strips line breaks from persisted text fields before writing Markdown.
- Implemented in this slice: generated-document sync uses fixed PM-owned paths, rejects symlinked path components, writes through temporary files, serializes sync through a lock, and audits success or failure.
- Implemented in this slice: task update transitions now have direct audit events rather than relying on generic document sync records.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Detached background execution was completed later in BL-008k.
- Durable shared-memory coordination was completed later in BL-008l.
- Operations summary surfacing was completed later in BL-008n.
- Detached restart adoption/resume was completed later in BL-008p.

Validation:
- Focused generated-doc/reviewer remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "task_update_records_redacted_audit_metadata or generated_document_symlink_failures or generated_documents or create_run_syncs_generated_project_documents"` passed with 7 tests.
- Full orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py` passed with 70 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\orchestration_documents.py src\dgentic\schemas.py tests\test_orchestration.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\orchestration_documents.py src\dgentic\schemas.py tests\test_orchestration.py` passed with 4 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 781 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 58 files already formatted.

Next:
- Continue Sprint 14 with production scheduling/lease hardening.

### Sprint 14 BL-008i Bounded Autonomous Orchestration Loop

Status: completed for the scoped synchronous loop slice; later slices completed detached background execution, project-document mutation, durable shared memory coordination, operations surfacing, and detached restart adoption/resume, so Sprint 14 remains active for production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected a bounded synchronous loop as the next Sprint 14 slice because it advances autonomous execution without claiming a detached worker/lease system exists yet.
- Completed: Developer updated production source only for the loop request/result schemas, orchestration loop service, `/tasks/orchestrations/{run_id}/loop`, loop audit metadata, and implementation docs.
- Completed: QA updated tests only for waiting-agent stop behavior, max-iteration behavior, blocker stop behavior, and API loop behavior.
- Completed: Reviewer found a blocker where pre-existing blockers could still allow another cycle to schedule work before stopping, plus an optional-body ergonomics issue.
- Completed: Developer remediated by checking loop stop conditions before the first cycle, accepting omitted API bodies through schema defaults, and ensuring ready pending work still schedules when no blocker is present.
- Completed: QA added regressions for pre-existing blockers preventing scheduling, optional body defaults, and ready pending task scheduling.
- Completed: Security/DevOps re-review found no blockers.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /tasks/orchestrations/{run_id}/loop` repeatedly runs orchestration cycles within `max_iterations`.
- Implemented in this slice: loop results include the final run, iteration count, progress flag, stop reason, running task ids, pending task ids, and unresolved blocker ids.
- Implemented in this slice: loop execution stops on waiting agents, unresolved blockers when configured, all-complete state, quiescence, or max-iteration exhaustion.
- Implemented in this slice: pre-existing blockers stop the loop before any additional scheduling when `stop_on_blocked` is enabled.
- Implemented in this slice: loop access uses existing authenticated owner/admin orchestration scoping and closed-run mutation rejection.
- Implemented in this slice: loop bounds are explicit and default to a small synchronous API workload rather than a detached background worker.

Remaining Sprint 14 work:
- Harden production multi-agent scheduling and lease semantics.
- Detached background execution was completed later in BL-008k.
- Automatic backlog/progress document mutation was completed later in BL-008j.
- Durable shared memory coordination was completed later in BL-008l.
- Operations summary surfacing was completed later in BL-008n.
- Detached restart adoption/resume was completed later in BL-008p.

Validation:
- Focused loop service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "loop or cycle"` passed with 11 tests.
- Focused loop API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration_api_loop or orchestration_api_cycle"` passed with 3 tests.
- Focused orchestration/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py` passed with 188 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\schemas.py src\dgentic\orchestration.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\schemas.py src\dgentic\orchestration.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 774 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.

Next:
- Continue Sprint 14 with project document mutation or detached-worker production hardening.

### Sprint 14 BL-008h Shared Dependency Context Handoff

Status: completed for the scoped dependency context handoff slice; Sprint 14 remains active for fully autonomous background execution, project-document mutation, durable shared memory coordination, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected shared dependency context handoff as the next contained Sprint 14 slice after manual/security blocker resolution.
- Completed: Developer updated production source only for orchestration scheduling context construction, objective redaction, dependency-output summary redaction, bounded dependency context rendering, and sanitized spawned `AgentBrief` fields before persistence/API exposure.
- Completed: QA updated tests only for service-level dependent agent context, API-visible spawned agent context, preserved dependency ids, redacted sibling fields, value-suppressed dependency output, and raw secret non-exposure.
- Completed: Reviewer/Security found blocker risk where spawned `AgentBrief` sibling fields and raw scalar dependency output could leak through `/agents/{id}`.
- Completed: Developer remediated by creating sanitized agent briefs, bounding text fields, redacting sibling fields, and summarizing output scalar values as redacted/type placeholders.
- Completed: Security re-review found no blockers.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: spawned dependent agent briefs include the run objective plus completed dependency output summaries in `context`.
- Implemented in this slice: objective, task title, task id, role, constraints, expected output, dependency ids, and dependency output summaries are redacted and bounded before spawned agent persistence or API exposure through agent detail endpoints.
- Implemented in this slice: dependency output scalar values are suppressed into redacted/type placeholders so unlabeled secrets are not copied into spawned agent context.
- Implemented in this slice: dependency output context is bounded to prevent oversized spawned-agent briefs.
- Implemented in this slice: dependency ids remain in `required_data` so downstream agents keep machine-readable traceability.

Remaining Sprint 14 work:
- Add a fully autonomous background execution loop beyond explicit cycle calls.
- Add automatic backlog/progress document mutation from orchestration events.
- Add durable shared memory coordination across runs and agents.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused context service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "shared_context or dependency_agent or schedules_parallel or cycle"` passed with 8 tests.
- Focused context API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "dependency_context or orchestration_api_cycle"` passed with 3 tests.
- Focused reviewer/security remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "shared_context or dependency_agent"` passed with 1 test and `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "dependency_context"` passed with 1 test.
- Focused orchestration/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py` passed with 184 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py tests\test_orchestration.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py tests\test_orchestration.py tests\test_api.py` passed with 3 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 768 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.

Next:
- Continue Sprint 14 with background execution or project document mutation.

### Sprint 14 BL-008g Manual/Security Blocker Resolution

Status: completed for the scoped manual/security blocker resolution slice; Sprint 14 remains active for fully autonomous background execution, project-document mutation, shared context/memory coordination, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected manual/security blocker resolution as the next Sprint 14 slice because BL-008e intentionally preserved manual blockers for explicit review instead of recovery bypass.
- Completed: Developer updated production source only for blocker resolution schema fields, `resolve_blocker`, unresolved-blocker close semantics, and `/tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve`.
- Completed: Developer updated implementation docs for the manual/security blocker resolution contract.
- Completed: QA updated tests only for manual blocker resolution, security blocker resolution, system blocker rejection, repeated resolution rejection, non-blank resolution validation, pending task state when `reschedule=false`, API admin-only access, audit redaction, rescheduling, and closeout over resolved blocker history.
- Completed: Reviewer/Security identified a stranded-run blocker where resolving the final blocker with `reschedule=false` left the task blocked, plus low-risk stale-output and audit scheduling accuracy follow-ups.
- Completed: Developer remediated by unblocking the task to pending when the final unresolved blocker is resolved, clearing stale output, and logging actual task rescheduling after the scheduling pass.
- Completed: QA added regressions for `reschedule=false` pending-task recovery, stale output clearing, and requested-versus-actual reschedule audit metadata.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve` resolves manual or security blockers with a non-blank resolution note.
- Implemented in this slice: resolved blockers remain in run history with `status`, `resolved_at`, `resolved_by`, and redacted `resolution` metadata.
- Implemented in this slice: role-boundary and retry-exhaustion blockers are rejected from the manual review path and remain on the task recovery path.
- Implemented in this slice: resolving the final unresolved blocker clears task error/follow-ups and moves the task to pending unless immediate rescheduling is requested.
- Implemented in this slice: `reschedule=true` schedules the unblocked task immediately when dependencies are satisfied.
- Implemented in this slice: closeout ignores resolved blocker history but still rejects any unresolved blockers.
- Implemented in this slice: the API route requires admin authority when authentication is enabled, while preserving development-mode no-auth behavior.

Remaining Sprint 14 work:
- Add a fully autonomous background execution loop beyond explicit cycle calls.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused blocker service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "resolve or blocker or recovery"` passed with 12 tests after the reviewer follow-ups.
- Focused blocker API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration_api_resolves or orchestration_api_recovery or owner"` passed with 4 tests.
- Focused orchestration/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py` passed with 181 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 766 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.

Next:
- Continue Sprint 14 with the autonomous background execution loop or automatic project document mutation slice, depending on architecture and risk review.

### Sprint 14 BL-008f Agent Lifecycle Reconciliation Cycle

Status: completed for the scoped explicit-cycle slice; Sprint 14 remains active for fully autonomous background execution, project-document mutation, shared context/memory coordination, manual/security blocker resolution workflow, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected explicit orchestration cycles as the next smallest Sprint 14 autonomous execution-loop slice after blocked task recovery.
- Completed: Developer updated production source only for `run_cycle`, `/tasks/orchestrations/{run_id}/cycle`, scheduling metadata reset, terminal agent reconciliation, and terminal agent audit preservation.
- Completed: Developer updated implementation docs for the cycle contract.
- Completed: QA updated tests only for completed-agent reconciliation, multi-agent dependency scheduling, failed-agent retry and blocker behavior, cancelled-agent blocking, closed-run cycle rejection, API cycle behavior, and owner/admin cycle scoping.
- Completed: Reviewer/Security found blockers where cycle reconciliation could overwrite terminal agent timestamps and where multi-update cycles could lose earlier scheduled task ids.
- Completed: Developer remediated by skipping lifecycle rewrites for already-terminal agents and accumulating every task scheduled across one cycle.
- Completed: QA added regressions for terminal `completed_at` preservation and multiple independent downstream schedules in one cycle.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /tasks/orchestrations/{run_id}/cycle` reconciles terminal spawned-agent statuses back into running orchestration tasks.
- Implemented in this slice: completed agents mark tasks completed and schedule newly dependency-ready tasks.
- Implemented in this slice: failed agents use existing retry and retry-exhaustion blocker behavior.
- Implemented in this slice: cancelled agents block their task without overwriting the agent's cancelled lifecycle state.
- Implemented in this slice: cycle reconciliation preserves terminal agent audit timestamps instead of rewriting them.
- Implemented in this slice: multi-task cycles retain all tasks scheduled during the cycle in `scheduled_task_ids`.
- Implemented in this slice: cycle access follows existing authenticated owner/admin orchestration scoping and rejects closed runs.

Remaining Sprint 14 work:
- Add a fully autonomous background execution loop beyond explicit cycle calls.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Add manual/security blocker resolution workflow.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused cycle service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "cycle or retry"` passed with 8 tests and 43 deselected.
- Focused cycle API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration_api_cycle or agent_lifecycle"` passed with 3 tests and 121 deselected.
- Focused orchestration/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py` passed with 175 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed with 4 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 759 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.

Next:
- Continue Sprint 14 with automatic project document mutation from orchestration events or shared context/memory coordination, depending on risk and implementation surface.

### Sprint 14 BL-008e Blocked Orchestration Task Recovery

Status: completed for the scoped recoverable-blocker slice; Sprint 14 remains active for autonomous execution, project-document mutation, shared context/memory coordination, manual/security blocker resolution workflow, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected blocked task recovery as the next Sprint 14 slice because the control plane already created blockers/follow-ups but could not safely requeue corrected blocked work.
- Completed: Developer updated production source only for the recovery schema, orchestration service recovery behavior, and `/tasks/orchestrations/{run_id}/tasks/{task_id}/recover`.
- Completed: Developer updated implementation docs for the new recovery contract.
- Completed: QA updated tests only for service-level recovery, retry recovery, dependency-gated rescheduling, invalid recovery rejection, manual blocker preservation, closed-run mutation rejection, API persistence, owner/admin access, and recovery audit redaction.
- Completed: Reviewer found no blockers and requested closed-run and non-blank resolution coverage.
- Completed: Security found a blocker where recovery could clear arbitrary task blockers; Developer remediated by limiting recovery to system-generated `role_boundary` and `retry_exhausted` blockers, preserving manual blockers, using generic unsafe-recovery denials, and adding redacted before/after audit metadata.
- Completed: QA added regressions for manual blocker preservation, non-blank resolution, closed-run recovery rejection, and audit metadata redaction.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: blocked orchestration tasks can be recovered through `POST /tasks/orchestrations/{run_id}/tasks/{task_id}/recover`.
- Implemented in this slice: recovery requires a non-blank resolution note and revalidates role-boundary policy before any task is requeued.
- Implemented in this slice: recovery can correct task role and declared write paths for role-boundary-blocked tasks.
- Implemented in this slice: retry-exhausted tasks can be recovered and optionally reset retry count before rescheduling.
- Implemented in this slice: recovery clears only system-generated role-boundary and retry-exhaustion blockers for the task; manual blockers remain unresolved for separate review.
- Implemented in this slice: recovered tasks reset to pending and are rescheduled only when dependencies are completed.
- Implemented in this slice: recovery follows existing authenticated owner/admin orchestration scoping and rejects closed runs.
- Implemented in this slice: recovery audit events redact secret-shaped resolution text and include safe before/after role and declared-path metadata.

Remaining Sprint 14 work:
- Add a real autonomous execution loop beyond scheduling briefs.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Add manual/security blocker resolution workflow.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused recovery service gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py -k "recover or recovery or retry or close"` passed with 9 tests and 37 deselected.
- Focused recovery API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "orchestration_api and (recover or recovery or lifecycle or owner)"` passed with 4 tests and 118 deselected.
- Focused orchestration/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py` passed with 168 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\schemas.py src\dgentic\orchestration.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\schemas.py src\dgentic\orchestration.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 752 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.
- Whitespace gate: `git diff --check` passed with only LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 14 with the autonomous execution loop or automatic progress/backlog update slice, depending on risk and implementation surface.

### Sprint 14 BL-008d Orchestration-Bound Generated Tool Actions

Status: completed for the scoped generated-tool runtime-binding slice; Sprint 14 remains active for autonomous execution, project-document mutation, shared context/memory coordination, blocked-run recovery, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected generated-tool action binding as the next Sprint 14 runtime-binding slice after filesystem and CLI binding.
- Completed: Developer updated production source only for tool orchestration authorization, generated-tool approval/result metadata, and tool audit metadata.
- Completed: QA updated tests only for orchestration authorization, generated-tool runtime enforcement, approval creation, approved execution recheck, API serialization, and fail-closed active context behavior.
- Completed: Reviewer/Security found stale known context, role-only partial context, and denial-reason redaction blockers.
- Completed: Developer remediated stale known context and role-only active context fail-closed behavior, and redacted orchestration denial reasons before tool runtime/API surfacing.
- Completed: QA added regressions for role-only active context, pending/completed/terminal known context, approved execution after task completion, denial reason redaction, and approval event orchestration metadata redaction.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: generated-tool approval and execution paths now enforce orchestration-bound active task context when `agent_id`, `agent_role`, or `task_id` references a running orchestration task.
- Implemented in this slice: omitted generated-tool orchestration context preserves existing non-orchestrated behavior.
- Implemented in this slice: legacy agent/task context with no active running orchestration task remains backward-compatible.
- Implemented in this slice: partial or mismatched context that references a running orchestration task blocks before approval creation, approval claim, or subprocess execution.
- Implemented in this slice: exact active `agent_id`, `agent_role`, and `task_id` context is required when a generated-tool action is bound to a running orchestration task.
- Implemented in this slice: tool approvals, approval review responses, execution results, API responses, and tool audit events serialize the orchestration decision.

Remaining Sprint 14 work:
- Add a real autonomous execution loop beyond scheduling briefs.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Add richer blocked-run recovery or reassignment semantics.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused generated-tool binding gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_tool_runtime.py tests\test_api.py -k "tool or orchestration"` passed with 102 tests and 96 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\tool_runtime.py tests\test_orchestration.py tests\test_tool_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\tool_runtime.py tests\test_orchestration.py tests\test_tool_runtime.py tests\test_api.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 744 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.
- Whitespace gate: `git diff --check` passed with only LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 14 with the autonomous execution loop or event-driven project progress/backlog update slice, depending on review and full-gate results.

### Sprint 14 BL-008c Orchestration-Bound CLI Actions

Status: completed for the scoped CLI runtime-binding slice; Sprint 14 remains active for autonomous execution, project-document mutation, tool action binding, blocked-run recovery, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect kept the story in Full Sprint mode because command execution and orchestration role binding are runtime- and security-sensitive.
- Completed: Developer updated production source only for CLI orchestration authorization, command-policy integration, and command decision schema metadata.
- Completed: QA updated tests only for orchestration authorization, command policy serialization, API guardrail metadata, and synchronous/asynchronous CLI runtime enforcement.
- Completed: Reviewer/Security found no blockers and called out optional approval/async-path hardening.
- Completed: QA added explicit fail-closed regressions for `/cli/execute`, `/cli/runs`, CLI approval creation, and direct approved-command execution when active orchestration context is partial.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: command policy decisions now include orchestration action metadata.
- Implemented in this slice: omitted CLI orchestration context preserves existing non-orchestrated CLI behavior.
- Implemented in this slice: legacy agent/task context with no active running orchestration task remains backward-compatible.
- Implemented in this slice: partial or mismatched context that references a running orchestration task blocks before CLI policy execution.
- Implemented in this slice: exact active `agent_id`, `agent_role`, and `task_id` context is required when a CLI action is bound to a running orchestration task.
- Implemented in this slice: `/guardrails/commands`, `/cli/execute`, and `/cli/runs` serialize or persist the orchestration decision through the existing command policy/runtime flow.

Remaining Sprint 14 work:
- Add a real autonomous execution loop beyond scheduling briefs.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Add runtime binding for tool actions.
- Add richer blocked-run recovery or reassignment semantics.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused CLI-binding gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py -k "orchestration or command_policy or cli or guardrails"` passed with 390 tests, 2 skipped, and 91 deselected.
- Focused security-hardening gate: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py tests\test_api.py -k "orchestration or cli_runtime_blocks or execute_approved_cli or approved_command_rechecks or create_approval_fails or start_run_fails or command_policy_serializes"` passed with 13 tests and 167 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\command_policy.py src\dgentic\schemas.py tests\test_orchestration.py tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\command_policy.py src\dgentic\schemas.py tests\test_orchestration.py tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py` passed with 7 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 719 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.
- Whitespace gate: `git diff --check` passed with only LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 14 with tool runtime binding or the event-driven autonomous execution loop, depending on review and full-gate results.

### Sprint 14 BL-008b Orchestration-Bound Filesystem Actions

Status: completed for the scoped filesystem runtime-binding slice; Sprint 14 remains active for autonomous execution, project-document mutation, CLI/tool action binding, and production scheduling hardening.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected filesystem action binding as the next smallest useful Sprint 14 slice after the backend orchestration control plane.
- Completed: Developer updated production source only for filesystem request context fields, orchestration action decisions, filesystem policy integration, and task declared-path authorization.
- Completed: QA updated tests only for backward-compatible omitted context, partial/mismatched context fail-closed behavior, declared write-path enforcement, read-only bound task allowance, and API log serialization.
- Completed: PM updated README, backlog, usage docs, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: filesystem requests can optionally include `agent_id`, `agent_role`, and `task_id`.
- Implemented in this slice: omitted orchestration context preserves existing filesystem behavior.
- Implemented in this slice: partial or mismatched orchestration context blocks filesystem actions.
- Implemented in this slice: write, binary-write, delete, move, copy, and rename actions must target the running task's declared write paths when orchestration context is supplied.
- Implemented in this slice: read-only actions are allowed for a matching running bound task.
- Implemented in this slice: filesystem policy audit metadata serializes the orchestration action decision.

Remaining Sprint 14 work:
- Add a real autonomous execution loop beyond scheduling briefs.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Add runtime binding for CLI and tool actions.
- Add richer blocked-run recovery or reassignment semantics.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.

Validation:
- Focused filesystem-binding gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py -k "orchestration or orchestration_api or filesystem"` passed with 33 tests and 103 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\schemas.py src\dgentic\guardrails.py tests\test_orchestration.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\schemas.py src\dgentic\guardrails.py tests\test_orchestration.py tests\test_api.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 695 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.
- Whitespace gate: `git diff --check` passed with only LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 14 with CLI/tool runtime action binding or the event-driven autonomous execution loop, depending on risk review.

### Sprint 14 BL-008a Backend Orchestration Control Plane

Status: completed for the first autonomous-agent orchestration foundation slice; Sprint 14 remains active for end-to-end autonomous execution and automatic project-document updates.

Current story:
- BL-008: Agent Orchestration Autonomy.

Checklist:
- Completed: PM/Architect selected the backend orchestration control plane as the smallest useful Sprint 14 slice after Sprint 13 closeout.
- Completed: Developer updated production source only for orchestration schemas, the orchestration service, and `/tasks/orchestrations` API routes.
- Completed: QA updated tests only for orchestration scheduling, dependency ordering, invalid graphs, role-boundary blocking, retry escalation, DoD close gates, and API lifecycle behavior.
- Completed: PM/Developer-docs updated README, backlog, usage docs, repository architecture, and this progress log.
- Completed: Reviewer/Security found pre-commit blockers around non-canonical role paths, mutable closed runs, and server-owned task state exposure; Developer remediated them before checkpoint.
- Completed: Reviewer/Security/DevOps validation found no remaining blocking correctness, role-boundary, secret-exposure, deployment, or runtime concerns for the scoped backend MVP slice.

Feature tracking:
- Implemented in this slice: persisted orchestration runs stored in `orchestrations.json`.
- Implemented in this slice: DAG validation rejects duplicate task ids, unknown dependencies, self-dependencies, and cycles.
- Implemented in this slice: dependency-ready tasks are scheduled into sub-agent briefs while dependent tasks wait for prerequisite completion, with each scheduling pass bounded to limit authorized fan-out.
- Implemented in this slice: declared write paths are canonicalized and checked against role-boundary policy, with blockers and follow-ups for out-of-bound or non-canonical work.
- Implemented in this slice: create requests accept client-owned task specs only, rejecting server-owned lifecycle fields such as task status and agent ids.
- Implemented in this slice: authenticated non-admin task principals see only their own orchestration runs, while admin principals retain full run visibility.
- Implemented in this slice: failed tasks can retry up to their configured limit, then escalate to blockers and follow-ups.
- Implemented in this slice: closeout requires completed tasks, no unresolved blockers, and required Definition of Done evidence, after which run mutation is rejected.

Remaining Sprint 14 work:
- Add a real autonomous execution loop beyond scheduling briefs.
- Add automatic backlog/progress document mutation from orchestration events.
- Add shared context/memory coordination across running agents.
- Harden production multi-agent scheduling and lease semantics.
- Operations summary surfacing was completed later in BL-008n.
- Add runtime binding between orchestration role decisions and filesystem, CLI, and tool actions.
- Add richer blocked-run recovery or reassignment semantics.

Validation:
- Focused orchestration gate: `uv --cache-dir .uv-cache run pytest -q tests\test_orchestration.py tests\test_api.py -k "orchestration or orchestration_api"` passed with 18 tests and 109 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\orchestration.py src\dgentic\schemas.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\orchestration.py src\dgentic\schemas.py src\dgentic\api\routes.py tests\test_orchestration.py tests\test_api.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 686 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 57 files already formatted.
- Whitespace gate: `git diff --check` passed with only LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 14 with the autonomous execution loop and event-driven project progress/backlog update slice.

### Sprint 13 Memory Production Lifecycle Closeout

Status: closed for the scoped backend MVP memory-production contract.

Current story:
- BL-007: Memory And Retrieval Production Lifecycle.

Checklist:
- Completed: PM reviewed BL-007a through BL-007d and confirmed the backend MVP now has migration-backed lifecycle metadata, lifecycle preview/apply, vector backend abstraction, baseline retrieval performance smoke coverage, deterministic metadata compression execution, and retrieval attribution/score explanations.
- Completed: PM reclassified remaining memory work so Sprint 13 can close without pulling in heavier infrastructure dependencies.
- Completed: pgvector production backend integration remains later production-hardening work because it needs PostgreSQL/pgvector dependency, migration, deployment, and test strategy decisions.
- Completed: Scheduled lifecycle/compression jobs remain later orchestration/deployment work because no backend scheduler/job framework exists yet.
- Completed: Full-content or LLM summarization remains future memory/provider work; Sprint 13 deliberately shipped no-LLM deterministic metadata-description compression.
- Completed: Broader retrieval performance validation, deeper provenance, and configurable scoring policy remain future quality/production-hardening work.
- Completed: README and backlog were updated to reflect Sprint 13 closeout and Sprint 14 as the next planned sprint.

Validation:
- Sprint 13 final BL-007d checkpoint `8dd495a` passed `uv --cache-dir .uv-cache run pytest -q` with 668 tests and 2 skipped.
- Sprint 13 final BL-007d checkpoint passed `uv --cache-dir .uv-cache run ruff check .`.
- Sprint 13 final BL-007d checkpoint passed `uv --cache-dir .uv-cache run ruff format --check .`.
- Sprint 13 final BL-007d checkpoint passed `git diff --check` with only existing LF-to-CRLF working-copy warnings.

Next:
- Start Sprint 14: Autonomous Agent Orchestration, beginning with backend-managed sprint task graph and role-boundary enforcement assessment.

### Sprint 13 BL-007d Retrieval Attribution And Score Reasons

Status: completed for the scoped additive retrieval attribution slice; remaining pgvector integration, scheduled lifecycle/compression jobs, full-content or LLM summarization, broader performance validation, deeper provenance, and configurable scoring policy were moved to follow-up backlog at Sprint 13 closeout.

Current story:
- BL-007: Memory And Retrieval Production Lifecycle.

Checklist:
- Completed: PM/Architect selected retrieval attribution as the next smallest safe slice after compression, deferring pgvector and scheduling because those need broader infrastructure decisions.
- Completed: Developer updated production source only for additive retrieval result fields and deterministic attribution/score reason generation while preserving existing score formulas and result ordering.
- Completed: QA updated tests only for hybrid metadata-text fallback attribution, hybrid stored-vector attribution, vector attribution, metadata-only attribution, inactive retrieval preservation, and API serialization.
- Completed: PM updated README, backlog, usage docs, setup docs, memory architecture, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: retrieval results now include `source_type`, `source_id`, `matched_fields`, and `score_reasons`.
- Implemented in this slice: hybrid retrieval identifies stored-vector versus metadata-text fallback matches and records filter fields that contributed.
- Implemented in this slice: vector and metadata-only retrieval include deterministic source ids and score reason strings.
- Preserved in this slice: `similarity_score`, `metadata_relevance`, `combined_score`, `source`, ranking formulas, inactive exclusion defaults, and response compatibility.

Validation:
- Focused attribution gate: `uv --cache-dir .uv-cache run pytest -q tests\test_retrieval_service.py tests\test_api.py -k "retrieval or metadata_attribution or attribution"` passed with 10 tests and 108 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\memory\retrieval_service.py src\dgentic\memory\schemas.py tests\test_retrieval_service.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\memory\retrieval_service.py src\dgentic\memory\schemas.py tests\test_retrieval_service.py tests\test_api.py` passed with 4 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 668 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 55 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 13 with either a safe pgvector integration plan or a scheduled lifecycle/compression execution slice, depending on PM/Architect risk review.

### Sprint 13 BL-007c Deterministic Memory Compression

Status: completed for the scoped deterministic metadata-description compression slice; remaining pgvector integration, scheduled lifecycle/compression jobs, full-content or LLM summarization, broader performance validation, and source-attribution/scoring improvements were moved to follow-up backlog at Sprint 13 closeout.

Current story:
- BL-007: Memory And Retrieval Production Lifecycle.

Checklist:
- Completed: PM selected deterministic metadata compression after BL-007b because lifecycle candidate detection and vector reindexing boundaries were stable enough for a safe execution slice.
- Completed: Architect/QA read-only review recommended a no-LLM extractive compression workflow, separate from lifecycle policy apply, with protected-retention exclusions and stale-embedding replacement.
- Completed: Developer updated production source only for compression schemas, compression preview/apply service, compression routes, embedding reindexing on apply, and memory package exports.
- Completed: QA updated tests only for compression preview/apply behavior, protected retention, inactive/default filtering, idempotence, stale embedding replacement, API contract, and retrieval after compression.
- Completed: PM updated README, backlog, usage docs, setup docs, memory architecture, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /api/v1/memory/compression/preview` returns deterministic compression candidates without mutation.
- Implemented in this slice: `POST /api/v1/memory/compression/apply` shortens eligible metadata descriptions, preserves lifecycle state, records lifecycle audit fields and `last_compacted_at`, and replaces existing stored embeddings.
- Implemented in this slice: compression is extractive/word-boundary based and does not call external models or invent new content.
- Implemented in this slice: manual/permanent retention records remain protected, inactive records are excluded by default, and recently compacted records do not immediately requalify.

Validation:
- Focused compression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_memory_compression_service.py tests\test_api.py tests\test_memory_lifecycle_service.py tests\test_retrieval_service.py -k "compression or lifecycle or retrieval or memory"` passed with 20 tests and 104 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\memory src\dgentic\api\memory_routes.py tests\test_memory_compression_service.py tests\test_api.py` passed.
- Focused format gate after formatting two files: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\memory src\dgentic\api\memory_routes.py tests\test_memory_compression_service.py tests\test_api.py` passed with 12 files already formatted.
- Focused final compression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_memory_compression_service.py` passed with 4 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 666 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 55 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 13 with either pgvector production backend integration or scheduled lifecycle/compression job execution, depending on PM/Architect risk assessment.

### Sprint 13 BL-007b Vector Backend Abstraction And Retrieval Baseline

Status: completed for the scoped vector-backend abstraction and baseline performance smoke slice; remaining pgvector integration, scheduled lifecycle jobs, broader performance validation, and source-attribution/scoring improvements were moved to follow-up backlog at Sprint 13 closeout.

Current story:
- BL-007: Memory And Retrieval Production Lifecycle.

Checklist:
- Completed: PM/Architect selected vector backend abstraction as the next smallest Sprint 13 slice after lifecycle policy, deferring compression until embedding reindexing and backend boundaries are stable.
- Completed: Developer updated production source only for a vector backend contract, SQLite/JSON default vector backend, embedding-service backend delegation, retrieval-service backend use, and memory package exports.
- Completed: QA updated tests only for backend store/fetch/search/delete behavior, retrieval use of the configured backend, lifecycle-aware retrieval behavior preservation, and a deterministic 75-record retrieval performance smoke.
- Completed: PM updated README, backlog, memory architecture, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: `SQLiteVectorBackend` preserves the current dependency-light JSON vector storage while hiding direct retrieval coupling to `VectorEmbedding` rows.
- Implemented in this slice: `RetrievalService.vector_search()` now searches through the configured vector backend and applies lifecycle filtering after backend results.
- Implemented in this slice: hybrid retrieval fetches stored embedding values through the backend and keeps the existing metadata-text fallback when no vector is stored.
- Implemented in this slice: the baseline smoke validates top-10 vector retrieval over 75 deterministic embeddings within a generous non-flaky timing budget.

Validation:
- Focused vector backend gate: `uv --cache-dir .uv-cache run pytest -q tests\test_vector_backend.py tests\test_retrieval_service.py` passed with 9 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\memory tests\test_vector_backend.py tests\test_retrieval_service.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\memory tests\test_vector_backend.py tests\test_retrieval_service.py` passed with 10 files already formatted.
- Focused post-doc gate: `uv --cache-dir .uv-cache run pytest -q tests\test_vector_backend.py tests\test_retrieval_service.py tests\test_memory_lifecycle_service.py tests\test_api.py -k "vector or retrieval or lifecycle or memory"` passed with 17 tests and 104 deselected.
- Final focused gate: `uv --cache-dir .uv-cache run pytest -q tests\test_vector_backend.py tests\test_retrieval_service.py` passed with 9 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 661 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 53 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 13 with either pgvector production backend integration design/implementation or compression/summarization execution once backend reindexing behavior is defined.

### Sprint 13 BL-007a Memory Lifecycle Policy Foundation

Status: completed for the scoped SQL-backed lifecycle policy slice; later vector productionization, compression scheduling, lifecycle jobs, performance validation, and source-attribution/scoring improvements were handled by later Sprint 13 slices or moved to follow-up backlog.

Current story:
- BL-007: Memory And Retrieval Production Lifecycle.

Checklist:
- Completed: PM selected a conservative lifecycle foundation after current-state assessment instead of pulling in an external vector database or LLM summarization before storage contracts were stable.
- Completed: Developer updated production source only for lifecycle metadata fields, additive `0002_memory_lifecycle_metadata` migration, dialect-aware lifecycle DDL, lifecycle preview/apply service behavior, API endpoints, metadata filters, retrieval inactive-state exclusion, and memory package exports.
- Completed: QA updated tests only for lifecycle decisions, idempotent archive/promote behavior, non-mutating compression candidates, inactive retrieval defaults and opt-in behavior, API lifecycle contracts, and upgrading a pre-lifecycle database.
- Completed: Reviewer read-only feedback identified compression-candidate mutation and PostgreSQL DDL risk; Developer remediated both and QA added regression coverage.
- Completed: PM updated README, backlog, usage docs, setup docs, memory architecture, repository architecture, and this progress log.

Feature tracking:
- Implemented in this slice: memory metadata now tracks lifecycle state/reason/timestamps, expiry, freshness score, and last-compacted timestamp.
- Implemented in this slice: `POST /api/v1/memory/lifecycle/preview` returns deterministic keep/promote/archive/soft-prune/compress-candidate decisions without mutation.
- Implemented in this slice: `POST /api/v1/memory/lifecycle/apply` mutates only promote/archive/soft-prune decisions; compression remains advisory until a real compression workflow exists.
- Implemented in this slice: hybrid, vector, and metadata retrieval exclude archived and soft-pruned metadata by default, with explicit `include_inactive` opt-in.

Validation:
- Focused memory lifecycle gate: `uv --cache-dir .uv-cache run pytest -q tests\test_memory_lifecycle_service.py tests\test_retrieval_service.py tests\test_database.py tests\test_api.py -k "memory or metadata or retrieval or lifecycle or migration"` passed with 24 tests and 107 deselected.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 657 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 51 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Next:
- Continue Sprint 13 with production vector backend selection/integration or the smallest compression/summarization execution slice after PM/Architect scope review.

### Sprint 12 Provider Productionization Closeout

Status: closed for the scoped backend MVP provider-production contract.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM reviewed BL-006a through BL-006l and confirmed Sprint 12 exit criteria are met for secure external-provider support, protected credentials, streaming, retry/rate-limit behavior, circuit breaking, routing, and no-secret telemetry.
- Completed: PM reclassified remaining provider-adjacent work so Sprint 12 can close without pulling in later-sprint dependencies.
- Completed: Encrypted credential storage or secret-manager integration remains tracked under BL-009/Sprint 15.
- Completed: Durable multi-worker provider circuit state remains tracked under BL-012/Sprint 18 deployment and observability work.
- Completed: Named provider-specific adapters beyond the generic OpenAI-compatible adapter are tracked under new BL-013/Sprint 19 after a concrete provider target is selected.
- Completed: Provider-specific billing reconciliation beyond advisory estimates remains future operations/provider-specific work.
- Completed: README and backlog were updated to reflect Sprint 12 closeout and Sprint 13 as the next planned sprint.

Validation:
- Sprint 12 final BL-006l checkpoint `f621e70` passed `uv --cache-dir .uv-cache run pytest -q` with 648 tests and 2 skipped.
- Sprint 12 final BL-006l checkpoint passed `uv --cache-dir .uv-cache run ruff check .`.
- Sprint 12 final BL-006l checkpoint passed `uv --cache-dir .uv-cache run ruff format --check .`.
- Sprint 12 final BL-006l checkpoint passed `git diff --check` with only existing LF-to-CRLF working-copy warnings.

Next:
- Start Sprint 13: Memory Production Lifecycle, beginning with a current-state assessment of memory storage, retrieval contracts, migrations, lifecycle gaps, and the smallest safe production-memory slice.

### Sprint 12 BL-006l Provider Role Routing Policy

Status: completed for the scoped provider role-routing policy; stable checkpoint committed and pushed.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected a bounded routing-policy slice after BL-006k because `RoutingRequest.role` existed in the API contract but provider routing did not yet use it, while encrypted secrets and durable circuit state remain Sprint 15/18 dependencies.
- Completed: Architect/PM read-only review recommended either Sprint 12 closeout or a narrow provider slice; Dev/QA read-only review recommended role-to-provider/model routing as the smallest useful code slice that does not expand external-adapter semantics.
- Completed: Developer updated production source only for `DGENTIC_PROVIDER_ROLE_ROUTING`, bounded role-route parsing, role-aware provider/model selection, invalid route-target fail-closed behavior before health probes, and credential-env-name validation for provider approvals without reading credential values.
- Completed: QA updated tests only for role-routed provider/model selection, privacy and provider/model-specific max-cost eligibility blocking without fallback, invalid role routing before probes, unknown role provider before probes, unavailable configured models, and provider approval credential-env-name validation without secret lookup.
- Completed: Reviewer found that role routes initially reused provider-level first-model cost for max-cost gating; Developer remediated model-specific route cost checks and QA added regression coverage.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.
- Completed: Full regression/lint/format/whitespace gates.
- Completed: Stable checkpoint committed and pushed.

Feature tracking:
- Implemented in this slice: `DGENTIC_PROVIDER_ROLE_ROUTING` accepts a bounded JSON object keyed by exact agent role, with each entry naming a `provider_id` and `model`.
- Implemented in this slice: configured role routes still honor normal provider eligibility: provider enabled state, privacy policy, required capabilities, routed-model max cost, and model availability.
- Implemented in this slice: blocked configured role routes fail clearly instead of silently falling back to another provider.
- Implemented in this slice: invalid role-routing JSON and unsupported provider ids fail closed before provider health probes.
- Implemented in this slice: provider approval creation/validation requires the credential environment variable name, while continuing not to read the credential value until transport-eligible execution.

Validation:
- Focused role-routing gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "routing" tests\test_provider_runtime.py::test_provider_approval_requires_credential_env_name_without_secret_lookup` passed with 16 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\provider_routing.py src\dgentic\providers.py src\dgentic\provider_runtime.py src\dgentic\settings.py src\dgentic\api\routes.py tests\test_api.py tests\test_provider_runtime.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\provider_routing.py src\dgentic\providers.py src\dgentic\provider_runtime.py src\dgentic\settings.py src\dgentic\api\routes.py tests\test_api.py tests\test_provider_runtime.py` passed with 7 files already formatted after formatting the new routing module and provider registry.
- Broad provider/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 207 tests.
- Full test gate: `uv --cache-dir .uv-cache run pytest -q` passed with 648 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 49 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Residual risks:
- Role routes are exact preferences, not weighted policies; richer fallback/priority behavior remains future routing work if operators need it.
- Encrypted credential storage, provider-specific external adapters, durable multi-worker circuit state, and provider billing reconciliation remain follow-up work outside this slice.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/provider_routing.py`, `src/dgentic/provider_runtime.py`, `src/dgentic/providers.py`, and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Decide whether Sprint 12 can close with provider-specific adapters deferred until a concrete provider requirement exists.

### Sprint 12 BL-006k External Credential-Resolution Ordering Hardening

Status: completed for the scoped external-provider credential-resolution ordering contract; stable checkpoint committed and pushed.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected a narrow security hardening slice after BL-006j because encrypted credential storage belongs with Sprint 15 identity/secrets, while current Sprint 12 external-provider runtime still needed stronger fail-fast ordering around credential lookup, approval claims, and outbound transport.
- Completed: Reviewer/Security read-only review confirmed the implementation shape and requested additional runtime/API coverage for streaming, boolean-bypass rejection, open-circuit, approval drift/denied/expired, and reused approval paths.
- Completed: Developer updated production source only to build configured external provider requests without Authorization headers, run pricing/config/circuit/approval gates first, resolve credential headers only after transport is eligible, and claim bound approvals immediately before outbound transport.
- Completed: QA updated tests only to prove fail-fast runtime/API paths do not read credential values or hit transport, while successful external transport resolves the credential exactly once and missing credentials do not claim the bound approval.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.
- Completed: Full regression/lint/format/whitespace gates.
- Completed: Stable checkpoint committed and pushed.

Feature tracking:
- Implemented in this slice: external non-streaming and streaming request builders now return payloads without credential headers.
- Implemented in this slice: external pricing validation, base URL/model configuration checks, circuit-open checks, and approval authorization run before API-key env-value lookup or Authorization header construction.
- Implemented in this slice: bound provider approvals are validated before credential lookup, but claimed only after credential/header resolution succeeds and immediately before outbound transport.
- Implemented in this slice: approval, configuration, pricing, circuit-open, drift, denied, expired, reused-approval, and missing-credential fail-fast paths avoid outbound transport; the paths that should avoid credential lookup now have explicit blocking-env regressions.

Validation:
- Focused provider/API ordering gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py -k "external_generation or external_streaming or external_provider_generate_api or external_provider_generate_stream_api or bound_provider_approval"` passed with 42 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\provider_runtime.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\provider_runtime.py tests\test_provider_runtime.py tests\test_api.py` passed with 3 files already formatted.
- Broad provider/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 199 tests.
- Full test gate: `uv --cache-dir .uv-cache run pytest -q` passed with 640 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 48 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.
- Reviewer/Security review: read-only reviewer reported no implementation path that resolves `_external_headers()` before fail-fast checks and requested the coverage gaps QA then added.

Residual risks:
- Credential values are still environment-referenced secrets, not encrypted DGentic-managed secrets; encrypted credential storage or secret-manager integration remains Sprint 15/BL-009 work.
- Circuit state remains in-process and non-durable across workers; durable multi-worker circuit state remains deployment follow-up work.
- Provider-specific billing reconciliation and non-OpenAI-compatible external adapters remain future work.

Role boundary:
- Developer-owned files: `src/dgentic/provider_runtime.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Continue Sprint 12 by reassessing whether the next safest slice is provider-specific adapters or deferring remaining provider work to Sprint 15/18 dependencies.

### Sprint 12 BL-006j Provider Pricing Catalog And Cost Estimation

Status: completed for the scoped advisory provider/model pricing contract; stable checkpoint committed and pushed.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected pricing catalog work after BL-006i because encrypted credential storage overlaps Sprint 15 identity/secrets, provider-specific external adapters expand outbound semantics, and durable circuit state depends on deployment persistence decisions.
- Completed: Architect/QA read-only explorers recommended a narrow exact provider/model pricing catalog for the configured OpenAI-compatible adapter, with advisory estimates only and no provider billing API calls.
- Completed: Developer updated production source only for `DGENTIC_PROVIDER_PRICING_CATALOG`, bounded pricing-catalog parsing, exact provider/model request estimates for routing, usage-based generation/streaming estimates, invalid-catalog fail-closed behavior before provider listing/health probes, and invalid-catalog fail-closed behavior before generation request/header construction or outbound transport.
- Completed: QA updated tests only for configured non-streaming cost, streaming usage-chunk cost using the request model, invalid pricing rejection before transport/probes/listing/health checks, routing max-cost behavior, API cost output, and no-content/no-secret logs.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.
- Completed: Reviewer/Security found invalid pricing could still allow provider listing/health probes and that generation validated pricing after request/header construction; Developer remediated both and QA added focused coverage.
- Completed: Stable checkpoint committed and pushed.

Feature tracking:
- Implemented in this slice: `DGENTIC_PROVIDER_PRICING_CATALOG` accepts a bounded JSON object keyed by exact provider id and model, with `prompt_usd_per_1k_tokens`, `completion_usd_per_1k_tokens`, and optional `request_estimate_usd`.
- Implemented in this slice: configured OpenAI-compatible generation and streaming use normalized prompt/completion usage metadata plus the requested model to calculate advisory `estimated_cost_usd`.
- Implemented in this slice: routing uses the configured first-model `request_estimate_usd` for external max-cost decisions before provider usage is known.
- Implemented in this slice: malformed, negative, non-finite, partial, oversized, or unsupported pricing catalog entries fail closed before provider transport, provider listing/health probes, or routing probes.

Validation:
- Focused pricing gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_external_generation_uses_configured_model_pricing tests\test_provider_runtime.py::test_external_generation_rejects_invalid_pricing_before_transport tests\test_provider_runtime.py::test_external_streaming_uses_request_model_pricing_for_usage_chunk tests\test_api.py::test_routing_uses_configured_external_model_request_price tests\test_api.py::test_routing_rejects_invalid_pricing_catalog_before_probes tests\test_api.py::test_external_provider_generate_stream_api_returns_configured_model_cost tests\test_api.py::test_external_provider_generate_api_returns_configured_model_cost tests\test_api.py::test_external_provider_generate_api_rejects_invalid_pricing_before_transport` passed with 11 tests.
- Focused remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py::test_provider_listing_and_health_reject_invalid_pricing_before_probes tests\test_api.py::test_routing_rejects_invalid_pricing_catalog_before_probes tests\test_api.py::test_external_provider_generate_api_rejects_invalid_pricing_before_transport tests\test_provider_runtime.py::test_external_generation_rejects_invalid_pricing_before_transport tests\test_provider_runtime.py::test_external_generation_uses_configured_model_pricing tests\test_provider_runtime.py::test_external_streaming_uses_request_model_pricing_for_usage_chunk` passed with 10 tests.
- Broad provider/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 194 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\settings.py src\dgentic\provider_pricing.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\settings.py src\dgentic\provider_pricing.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py tests\test_provider_runtime.py tests\test_api.py` passed with 7 files already formatted.
- Reviewer/Security recheck: final read-only review and Security/DevOps recheck reported no blockers after pricing validation ordering remediation.
- Full test gate: `uv --cache-dir .uv-cache run pytest -q` passed with 635 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 48 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Residual risks:
- Pricing estimates are advisory controls and telemetry, not authoritative billing records.
- The current routing request estimate applies to the configured first model; richer model-specific routing remains future work.
- Encrypted credential storage, provider billing reconciliation, durable multi-worker circuit state, and provider-specific external adapters remain future Sprint 12/15/18 follow-up work.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/provider_pricing.py`, `src/dgentic/provider_runtime.py`, `src/dgentic/providers.py`, and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Continue Sprint 12 with the credential-resolution ordering hardening slice, then reassess remaining encrypted credential strategy and provider-specific adapter scope.


### Sprint 12 BL-006i Provider Circuit Breaker

Status: completed for the scoped in-process provider circuit-breaker contract; Sprint 12 remains open for encrypted credential storage or secret-manager integration, provider-specific external adapters, durable multi-worker circuit state, and provider-specific pricing/billing tables.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected circuit breaker behavior after BL-006h because retry/backoff existed but repeated exhausted failures could still repeatedly hit the same unhealthy provider.
- Completed: Architect scoped the breaker as in-process per-provider state with configurable threshold/cooldown, explicitly deferring durable multi-worker breaker state to production deployment work.
- Completed: Developer updated production source only for circuit-breaker settings, per-provider/base-URL in-memory state, retry-exhausted failure counting, fail-fast open-circuit checks before transport, single half-open cooldown probes, success reset, stream-open cleanup, approval-preserving external fail-fast ordering, pathful external base-URL keying, and API `503` mapping through provider configuration errors.
- Completed: QA updated tests only for open/fail-fast behavior, cooldown probe/reset, provider isolation, base-URL isolation, pathful external base isolation, single half-open probe behavior, half-open concurrent rejection locking, half-open stream close cleanup, external approval preservation, and API `503` no-transport mapping.
- Completed: Reviewer/Security found provider-id-only circuit scope, cooldown thundering-herd, half-open fail-fast latch mutation, streaming half-open close pinning, external approval consumption, and external pathful-keying risks; Developer remediated them and QA added focused coverage.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD` controls retry-exhausted failures needed before a provider circuit opens.
- Implemented in this slice: `DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS` controls when an open circuit allows a new probe attempt.
- Implemented in this slice: provider circuits are keyed by provider id plus effective normalized base URL, reset on successful generation/stream completion, and do not block other providers or healthy alternate endpoints.
- Implemented in this slice: expired open circuits allow a single half-open probe while concurrent callers continue to fail fast and stream iterator close/client disconnect reopens the circuit without pinning the probe latch.
- Implemented in this slice: open circuits fail fast before outbound provider transport, preserve unexecuted bound external provider approvals, and API callers receive `503` with generic provider-circuit detail.

Validation:
- Focused circuit gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_provider_generation_opens_circuit_after_retry_exhaustion_and_fails_fast tests\test_provider_runtime.py::test_provider_generation_circuit_cooldown_allows_probe_and_reset tests\test_provider_runtime.py::test_provider_generation_circuit_is_per_provider tests\test_api.py::test_provider_generate_api_maps_open_circuit_to_503_without_transport` passed with 4 tests.
- Focused remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_provider_generation_circuit_is_per_base_url tests\test_provider_runtime.py::test_provider_generation_open_circuit_allows_single_half_open_probe tests\test_provider_runtime.py::test_provider_generation_opens_circuit_after_retry_exhaustion_and_fails_fast tests\test_provider_runtime.py::test_provider_generation_circuit_cooldown_allows_probe_and_reset tests\test_api.py::test_provider_generate_api_maps_open_circuit_to_503_without_transport` passed with 5 tests.
- Focused final remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_external_generation_circuit_is_per_configured_base_url_path tests\test_provider_runtime.py::test_external_generation_open_circuit_preserves_bound_approval_id tests\test_provider_runtime.py::test_provider_generation_circuit_is_per_base_url tests\test_provider_runtime.py::test_provider_stream_half_open_close_reopens_and_allows_next_probe tests\test_api.py::test_provider_generate_api_maps_open_circuit_to_503_without_transport` passed with 5 tests.
- Broad provider/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 181 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\settings.py src\dgentic\provider_runtime.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\settings.py src\dgentic\provider_runtime.py tests\test_provider_runtime.py tests\test_api.py` passed with 4 files already formatted after formatting `src\dgentic\provider_runtime.py`.
- Reviewer/Security recheck: final read-only review and Security/DevOps delta check reported no blockers after the pathful external base-URL keying fix.
- Full test gate: `uv --cache-dir .uv-cache run pytest -q` passed with 622 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.
- Whitespace gate: `git diff --check` passed with only existing LF-to-CRLF working-copy warnings.

Residual risks:
- Circuit state is process-local and resets on restart; durable multi-worker circuit state remains future deployment work.
- The breaker counts retry-exhausted/rate-limit generation failures only; health probes remain single-attempt and do not mutate circuit state.

Role boundary:
- Developer-owned files: `src/dgentic/provider_runtime.py` and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Commit/push the stable BL-006i checkpoint, then continue Sprint 12 with encrypted credential strategy or provider-specific external adapters depending on risk priority.

### Sprint 12 BL-006h Provider Usage And Cost Metadata

Status: completed for the scoped normalized usage and static request-cost metadata contract; Sprint 12 remains open for encrypted credential storage or secret-manager integration, provider-specific external adapters, circuit breakers, and provider-specific pricing/billing tables beyond static request estimates.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected usage/cost metadata after BL-006g because provider logs already carried latency and retry evidence but lacked a normalized token/cost surface.
- Completed: Architect scoped cost as static request-level estimates from existing provider configuration, not provider-specific billing tables.
- Completed: Developer updated production source only for provider result/event usage and cost fields, completion log usage/cost metadata, normalized Ollama/OpenAI-compatible token extraction, OpenAI-compatible usage-only streaming chunks, and hard finite/non-negative `max_cost_usd` routing ceilings.
- Completed: QA updated tests only for local/external non-streaming usage/cost metadata, Ollama streaming terminal usage/cost metadata, OpenAI-compatible usage-only streaming chunks, provider log usage/cost metadata, over-budget routing rejection, and invalid max-cost policy rejection.
- Completed: Reviewer/Security found usage-only stream chunk and non-finite max-cost blockers; Developer remediated them and QA added focused coverage.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `ProviderGenerationResult` now includes `usage_metadata` and `estimated_cost_usd`.
- Implemented in this slice: `ProviderStreamEvent` now includes `usage_metadata` and `estimated_cost_usd` where a chunk carries usable token metadata or a request-level estimate applies.
- Implemented in this slice: provider completion logs include normalized usage metadata and static request-level cost estimates without raw prompts, completions, credentials, provider ids, or provider-controlled model strings.
- Implemented in this slice: Ollama `prompt_eval_count`/`eval_count` normalize to `prompt_tokens`/`completion_tokens`/`total_tokens`; OpenAI-compatible `usage` normalizes matching numeric token counters.
- Implemented in this slice: OpenAI-compatible usage-only streaming chunks with empty choices now emit a metadata event instead of a sanitized error event.
- Implemented in this slice: `max_cost_usd` now rejects non-finite/negative values and excludes providers above the requested ceiling instead of applying only a score penalty.

Validation:
- Focused usage/cost gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_ollama_generation_posts_chat_payload_and_returns_content tests\test_provider_runtime.py::test_lm_studio_generation_posts_chat_completions_payload tests\test_provider_runtime.py::test_external_openai_compatible_generation_posts_authorized_chat_completion tests\test_provider_runtime.py::test_ollama_streaming_posts_chat_payload_and_emits_ordered_chunks tests\test_api.py::test_routing_rejects_provider_above_max_cost tests\test_api.py::test_external_provider_generate_api_sends_authorization_and_redacts_logs tests\test_api.py::test_provider_generate_api_returns_safe_metadata_and_logs tests\test_api.py::test_provider_generate_stream_api_emits_ollama_ndjson_and_safe_logs` passed with 10 tests.
- Focused remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py::test_routing_rejects_provider_above_max_cost tests\test_api.py::test_routing_rejects_invalid_max_cost_before_scoring tests\test_api.py::test_provider_generate_api_returns_safe_metadata_and_logs tests\test_provider_runtime.py::test_provider_generation_handles_malformed_or_untrusted_success_payloads tests\test_provider_runtime.py::test_lm_studio_streaming_emits_ordered_chunks_and_safe_logs` passed with 11 tests.
- Broad provider/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 170 tests.
- Final Reviewer recheck: no blockers after usage-only stream chunk remediation.
- Final Security recheck: no blockers after finite/non-negative max-cost validation and bounded non-negative usage metadata remediation.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\schemas.py src\dgentic\provider_runtime.py src\dgentic\providers.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\schemas.py src\dgentic\provider_runtime.py src\dgentic\providers.py tests\test_provider_runtime.py tests\test_api.py` passed with 5 files already formatted after formatting touched files.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 611 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.
- Whitespace gate: `git diff --check` passed.

Residual risks:
- Cost estimates are static request-level estimates, not provider-specific billing calculations.
- Usage metadata is provider-reported telemetry and must not be treated as authoritative billing evidence until provider-specific verification exists.
- Circuit breaker behavior, encrypted credential storage, and provider-specific external adapters remain future Sprint 12 work.

Role boundary:
- Developer-owned files: `src/dgentic/provider_runtime.py`, `src/dgentic/providers.py`, and `src/dgentic/schemas.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Complete final Reviewer/Security rechecks, run final full gates, commit/push the stable BL-006h checkpoint, then continue Sprint 12 with circuit breakers, encrypted credential strategy, or provider-specific external adapters depending on risk priority.

### Sprint 12 BL-006g Provider Payload Validation

Status: completed for the scoped provider request and upstream response payload-validation contract; Sprint 12 remains open for encrypted credential storage or secret-manager integration, provider-specific external adapters, circuit breakers, and cost accounting.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected payload validation as the next Sprint 12 slice after BL-006f because it closes a documented provider-runtime hardening gap without expanding credential storage or external-adapter scope.
- Completed: Developer updated production source only for bounded provider request validation, sanitized request-validation errors, supported chat-role enforcement, JSON-compatible bounded options, provider-specific malformed success-payload rejection, OpenAI-compatible streaming error-object rejection, safe metadata narrowing, and generic sanitized upstream failure behavior.
- Completed: QA updated tests only for invalid request-shape rejection, API 422-before-transport no-echo behavior, malformed non-streaming success payload failures, malformed streaming success chunk failures, huge-number metadata handling, and no-secret API/log behavior.
- Completed: Reviewer/Security found validation-error echo, untrusted metadata, non-string stream content, empty stream choices, and huge-integer metadata blockers; Developer remediated them and QA added focused coverage.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: provider generation requests now require nonblank provider/model identifiers, 1-64 messages, supported chat roles, nonblank bounded message content, 0.0-2.0 temperature, positive bounded `max_tokens`, positive bounded timeout, and bounded JSON-compatible options.
- Implemented in this slice: provider options reject too many keys, oversize serialized option payloads, non-string or blank keys, too-deep nesting, oversize lists, non-finite numbers, and non-JSON-compatible values.
- Implemented in this slice: Ollama and OpenAI-compatible non-streaming success responses now reject `error` objects, missing/malformed message objects, missing/non-string content, and malformed/empty choices instead of returning silent empty completions.
- Implemented in this slice: API request-validation failures omit rejected input and context fields so invalid prompts/options are not echoed in 422 responses.
- Implemented in this slice: safe provider metadata is narrowed to booleans, bounded numeric counters, known finish reasons, known message roles, and known usage counters; provider-controlled ids, model names, unsafe usage fields, and oversized numbers are dropped.
- Implemented in this slice: OpenAI-compatible streaming chunks now reject upstream `error` objects, empty choices, malformed delta objects, and non-string content with sanitized provider failures.

Validation:
- Focused security-remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_provider_generation_request_rejects_invalid_payload_shape tests\test_provider_runtime.py::test_provider_generation_handles_malformed_or_untrusted_success_payloads tests\test_provider_runtime.py::test_openai_compatible_streaming_rejects_malformed_success_chunks tests\test_api.py::test_provider_generate_api_returns_422_for_invalid_payload_before_transport tests\test_api.py::test_provider_generate_api_maps_malformed_success_payload_to_bad_gateway tests\test_api.py::test_provider_generate_stream_api_maps_malformed_success_chunk_to_bad_gateway` passed with 26 tests.
- Broad provider/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 166 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\main.py src\dgentic\provider_runtime.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\main.py src\dgentic\provider_runtime.py tests\test_provider_runtime.py tests\test_api.py` passed with 4 files already formatted after formatting `src\dgentic\provider_runtime.py`.
- Final Reviewer recheck: no blockers after huge-integer metadata remediation.
- Final Security recheck: no blockers after 422 sanitization, metadata narrowing, streaming non-string rejection, and huge-integer metadata remediation.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 607 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.
- Whitespace gate: `git diff --check` passed.

Residual risks:
- Provider request validation is intentionally conservative for the current text-chat contract; tool-call-specific response payloads remain out of scope until the provider stream/result schema supports tool-call events.
- Encrypted credential storage, provider-specific external adapters, circuit breakers, and cost accounting remain future Sprint 12 work.

Role boundary:
- Developer-owned files: `src/dgentic/main.py` and `src/dgentic/provider_runtime.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Run final full quality gates, commit/push the stable BL-006g checkpoint, then continue Sprint 12 with circuit-breaker/cost work, encrypted credential strategy, or provider-specific external adapters depending on risk priority.

### Sprint 12 BL-006f Ollama Streaming Generation

Status: completed for the scoped Ollama streaming contract; Sprint 12 remains open for encrypted credential storage or secret-manager integration, provider-specific external adapters, circuit breakers, cost accounting, and broader payload validation.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected Ollama streaming as the next Sprint 12 slice after BL-006e because it closed the remaining local-provider streaming capability gap without expanding credential scope.
- Completed: Architect/QA read-only explorers recommended adding an Ollama NDJSON parser under the existing stream endpoint, preserving OpenAI-compatible parsing for LM Studio/external providers, advertising Ollama streaming support, and covering safe log behavior.
- Completed: Developer updated production source only for Ollama stream request construction, `application/x-ndjson` accept headers, Ollama NDJSON stream parsing, safe Ollama stream metadata, upstream Ollama error-object handling, and provider streaming capability advertisement.
- Completed: QA updated tests only for Ollama stream request payloads, ordered chunk emission, terminal finish reasons, safe logs with prompt/delta sentinels, malformed stream failures, Ollama error-object handling before and after emitted chunks, API NDJSON output, provider listing support, and external-placeholder rejection.
- Completed: Reviewer/Security found an Ollama error-object handling blocker; Developer remediated it and QA added focused runtime/API coverage.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /providers/generate/stream` now supports Ollama `/api/chat` streaming and returns downstream `application/x-ndjson` `ProviderStreamEvent` rows.
- Implemented in this slice: Ollama stream requests map `temperature` and `max_tokens` into Ollama `options.temperature` and `options.num_predict`, preserve caller options, and send `Accept: application/x-ndjson`.
- Implemented in this slice: Ollama NDJSON chunks emit text deltas from `message.content`; terminal chunks emit a final event with `done_reason` as `finish_reason`.
- Implemented in this slice: malformed Ollama stream data and Ollama stream `error` objects fail safely before the first chunk, or produce a sanitized terminal error event after content has already been emitted.
- Implemented in this slice: Ollama advertises `supports_streaming=True` and the `streaming` capability.

Validation:
- Focused Ollama runtime gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py::test_ollama_streaming_posts_chat_payload_and_emits_ordered_chunks tests\test_provider_runtime.py::test_ollama_streaming_malformed_first_chunk_raises_safe_error tests\test_provider_runtime.py::test_ollama_streaming_error_first_chunk_raises_safe_error tests\test_provider_runtime.py::test_ollama_streaming_failure_after_first_chunk_emits_sanitized_error_event tests\test_provider_runtime.py::test_ollama_streaming_error_after_first_chunk_emits_sanitized_error_event` passed with 5 tests.
- Focused Ollama API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py::test_provider_generate_stream_api_emits_ollama_ndjson_and_safe_logs tests\test_api.py::test_provider_generate_stream_api_maps_ollama_error_first_chunk_to_bad_gateway tests\test_api.py::test_provider_generate_stream_api_emits_sanitized_error_for_ollama_post_chunk_error` passed with 3 tests.
- Broad provider regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py` passed with 140 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\provider_runtime.py src\dgentic\providers.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\provider_runtime.py src\dgentic\providers.py tests\test_provider_runtime.py tests\test_api.py` passed with 4 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 581 tests and 2 skipped after rerunning a transient CLI cancellation timing failure that passed in isolation.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.
- Whitespace gate: `git diff --check` passed.

Residual risks:
- Ollama tool-call streaming chunks are not surfaced as tool-call events; the current stream contract emits text deltas and finish/error events only.
- Encrypted credential storage, provider-specific external adapters, circuit breakers, cost accounting, and broader payload validation remain future Sprint 12 work.

Role boundary:
- Developer-owned files: `src/dgentic/provider_runtime.py` and `src/dgentic/providers.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Run final full quality gates, commit/push the stable BL-006f checkpoint, then continue Sprint 12 with encrypted credential strategy, circuit-breaker/cost work, payload validation, or provider-specific external adapters depending on risk priority.

### Sprint 12 BL-006e Bound Provider Approval Records

Status: completed for the scoped bound external provider approval-record contract; Sprint 12 remains open for encrypted credential storage or secret-manager integration, provider-specific external adapters, Ollama streaming, circuit breakers, cost accounting, and broader payload validation.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected bound provider approval records as the next Sprint 12 slice after BL-006d because configured external generation still had no staging/production execution path.
- Completed: Architect/QA read-only explorers recommended mirroring generated-tool approval records, binding stream and non-stream requests separately, using request/config HMAC digests, exposing safe review contracts, and enforcing the `approvals` capability for approval artifacts.
- Completed: Developer updated production source only for provider approval models, create/list/review/approve/deny lifecycle helpers, approval-bound external generation and streaming, provider approval API routes, approval-capability routing, and inter-process locked JSON reads/item updates for approval decisions/claims.
- Completed: QA updated tests only for development/test boolean bypass preservation, staging/production boolean rejection, bound non-streaming and streaming external approval execution, request drift, denied/expired/non-pending lifecycle states, provider approval API flow, approval capability separation, and JSON collection update transactions.
- Completed: Reviewer/Security found and Developer remediated approval-capability and cross-process claim/decision blockers; final read-only review reported no remaining blockers for the provider approval lifecycle.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /providers/{provider_id}/approvals`, `GET /providers/approvals`, `GET /providers/approvals/{approval_id}/review`, `POST /providers/approvals/{approval_id}/approve`, and `POST /providers/approvals/{approval_id}/deny`.
- Implemented in this slice: configured external OpenAI-compatible non-streaming and streaming generation can execute in staging/production with a single-use bound `approval_id`; `approved: true` remains limited to development/test.
- Implemented in this slice: provider approvals bind provider id, model, stream mode, messages, generation options, timeout, configured base URL, credential environment name, model allowlist, requester, and agent/task context through HMAC digests.
- Implemented in this slice: provider approval records and review responses store safe message metadata and digests without raw prompt content, credential values, or upstream response content.
- Implemented in this slice: provider approval create/list/review/approve/deny routes require the `approvals` capability when auth is enabled; generation remains under the `providers` capability.
- Implemented in this slice: JSON collection reads and item updates now support inter-process locking; provider approval decisions and execution claims use locked read/mutate/write transactions.

Validation:
- Focused provider approval runtime gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py -k "external and approval"` passed with 3 tests and 49 deselected.
- Focused provider API approval gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k "provider and approval"` passed with 5 tests and 76 deselected.
- Focused auth capability gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py -k "capability_for_path"` passed with 16 tests and 21 deselected.
- Focused lifecycle/storage remediation gates passed for provider bound lifecycle, provider approval capability separation, and `tests\test_storage.py`.
- Broad touched-surface regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py tests\test_auth.py tests\test_tool_runtime.py tests\test_storage.py` passed with 210 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\storage.py src\dgentic\provider_runtime.py src\dgentic\api\routes.py src\dgentic\auth.py tests\test_storage.py tests\test_provider_runtime.py tests\test_api.py tests\test_auth.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\storage.py src\dgentic\provider_runtime.py src\dgentic\api\routes.py src\dgentic\auth.py tests\test_storage.py tests\test_provider_runtime.py tests\test_api.py tests\test_auth.py` passed with 8 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 574 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.
- Whitespace gate: `git diff --check` passed.

Residual risks:
- Provider approvals are consumed before outbound provider transport begins; this is conservative for single-use security, but transient network failures require a new approval.
- Approval records bind the configured credential environment variable name, not the secret value or a dedicated credential version; encrypted credential storage or secret-manager integration remains follow-up work.
- Ollama streaming, provider-specific external adapters, circuit breakers, cost accounting, and broader payload validation remain future Sprint 12 work.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/auth.py`, `src/dgentic/provider_runtime.py`, and `src/dgentic/storage.py`.
- QA-owned files: `tests/test_api.py`, `tests/test_auth.py`, `tests/test_provider_runtime.py`, and `tests/test_storage.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Run final full quality gates, commit/push the stable BL-006e checkpoint, then continue Sprint 12 with encrypted credential strategy, Ollama streaming, circuit-breaker/cost work, payload validation, or provider-specific external adapters depending on risk priority.

### Sprint 12 BL-006d OpenAI-Compatible Streaming Generation Contract

Status: completed for the scoped OpenAI-compatible streaming contract; Sprint 12 remains open for bound provider approval records, encrypted credential storage or secret-manager integration, provider-specific external adapters, Ollama streaming, circuit breakers, cost accounting, and broader payload validation.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected streaming as the next Sprint 12 slice after the stable BL-006c checkpoint, keeping encrypted credentials, circuit breakers, cost accounting, and Ollama streaming out of scope.
- Completed: Architect/QA read-only explorer recommended upstream OpenAI-compatible SSE parsing with downstream NDJSON, pre-stream HTTP error mapping, sanitized post-chunk error events, no retry after bytes begin flowing, and focused runtime/API coverage.
- Completed: Developer updated production source only for streaming transport open/retry behavior, OpenAI-compatible stream request construction, streaming event parsing, safe stream metadata/logging, `POST /providers/generate/stream`, and provider streaming capability advertisement.
- Completed: QA updated tests only for LM Studio streaming payloads and ordered deltas, external streaming authorization/no-leak behavior, unsupported-provider rejection, malformed first chunk mapping, post-chunk sanitized error events, stream-open retry, NDJSON API responses, provider listing support, and external stream approval/config errors.
- Completed: PM updated README, architecture docs, usage docs, developer setup docs, backlog, and this progress log.

Feature tracking:
- Implemented in this slice: `POST /providers/generate/stream` returns `application/x-ndjson` chunk events for LM Studio and configured external OpenAI-compatible providers.
- Implemented in this slice: upstream `data:` server-sent event chunks are parsed for OpenAI-compatible `choices[].delta.content` and `finish_reason`, with `[DONE]` ending the stream.
- Implemented in this slice: streaming reuses provider-scoped egress policy, HTTPS-only external credentials, model allowlists, and external approval checks from BL-006c.
- Implemented in this slice: stream-open retry/backoff works for retryable failures before a response stream starts; malformed data before the first chunk maps to a safe provider failure, while malformed data after emitted content yields a sanitized terminal error event.
- Implemented in this slice: provider completion logs record chunk counts, content length, finish reasons, retry metadata, and safe response metadata without raw streamed deltas, prompts, or credentials.
- Implemented in this slice: LM Studio and configured external OpenAI-compatible providers advertise `supports_streaming=True` and a `streaming` capability; Ollama and placeholder providers remain non-streaming.

Validation:
- Focused stream gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py -k "stream"` passed with 20 tests and 103 deselected.
- Focused provider gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py -k "provider"` passed with 76 tests and 47 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\provider_transport.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\provider_transport.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py tests\test_provider_runtime.py tests\test_api.py` passed with 6 files already formatted.
- Broad touched-surface regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py tests\test_tool_runtime.py tests\test_auth.py` passed with 185 tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 560 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.

Residual risks:
- Streaming is implemented only for OpenAI-compatible chunk shapes; Ollama streaming remains future Sprint 12 work.
- Bound provider approval records are not implemented; development/test can use the explicit `approved: true` external-generation bypass, while staging/production rejects that bypass.
- No encrypted credential storage, circuit breaker, cost accounting, or provider-specific external adapter work is included.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/provider_runtime.py`, `src/dgentic/provider_transport.py`, and `src/dgentic/providers.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Review, commit/push the stable BL-006d checkpoint, then continue Sprint 12 with provider approval records, credential strategy, or circuit-breaker/cost work depending on risk priority.

### Sprint 12 BL-006c OpenAI-Compatible External Adapter Boundary

Status: completed for the scoped non-streaming OpenAI-compatible external adapter boundary; Sprint 12 remains open for encrypted credential storage, provider-specific external adapters, circuit breakers, cost accounting, broader payload validation, and streaming generation.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected a conservative external adapter boundary after BL-006b, explicitly excluding credential persistence, credential APIs, streaming, circuit breakers, and cost accounting.
- Completed: Architect read-only explorer recommended a disabled-by-default OpenAI-compatible adapter using base URL, model allowlist, and an API-key environment variable reference.
- Completed: QA read-only explorer recommended fake-transport tests for adapter success, missing config, credential no-leak behavior, external routing, privacy routing, and API mappings.
- Completed: Developer updated production source only for external adapter settings, provider-scoped allowlist validation, OpenAI-compatible payload/header construction, HTTPS-only credentialed base URL validation, explicit external-generation approval checks, model allowlist checks, config-only external health, external routing eligibility, and safe API mapping for missing config and caller policy errors.
- Completed: QA updated tests only for configured adapter success, missing config before transport, runtime base URL rejection, credential redaction, external routing, privacy local routing, config-only external health, model allowlist rejection, local-provider bypass prevention, plain-HTTP credential blocking, approval-required generation, and caller-error API mappings.
- Completed: Reviewer/Security found a provider-scoped allowlist blocker; fixes were routed through Dev and QA.
- Completed: Follow-up Reviewer/Security found plain-HTTP credential transport, approval-contract, and caller-error API mapping blockers; fixes were routed through Dev and QA.
- Completed: Final review found the provider-scoped allowlist had dropped documented `DGENTIC_PROVIDER_ALLOWED_BASE_URLS` support for local runtime overrides and that the shared policy helper still treated external configured URLs as globally allowed; Dev restored local extra trusted endpoints, scoped the shared helper by provider, removed external URLs from the global helper, and QA added runtime/API/policy regressions.

Feature tracking:
- Implemented in this slice: `external-openai-compatible` provider id for non-streaming OpenAI-compatible chat completions.
- Implemented in this slice: adapter is disabled unless HTTPS base URL, model allowlist, credential env-var name, and referenced credential value are all present.
- Implemented in this slice: actual API key values are read from the named process environment variable and sent only as outbound `Authorization` headers to HTTPS external endpoints.
- Implemented in this slice: direct external generation requires explicit approval; the current `approved: true` bypass is limited to development/test mode until provider approval records are implemented.
- Implemented in this slice: request-level `base_url` overrides and model names outside the configured allowlist are rejected before transport with caller-policy API status codes.
- Implemented in this slice: provider-scoped allowlist validation prevents local provider ids from targeting the external configured URL.
- Implemented in this slice: local providers can still use operator-declared extra trusted base URLs from `DGENTIC_PROVIDER_ALLOWED_BASE_URLS`.
- Implemented in this slice: `/providers/{external}/health` is config-only and does not perform live authenticated network probes.
- Implemented in this slice: routing can select the configured external provider for non-private external-capability requests, while privacy-required routing scores external providers as unavailable.

Validation:
- Focused provider gate after final review remediation: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py -k "provider"` passed with 61 tests and 47 deselected.
- Broad touched-surface regression gate after final review remediation: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py tests\test_tool_runtime.py tests\test_auth.py` passed with 170 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\provider_policy.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py src\dgentic\settings.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\provider_policy.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py src\dgentic\settings.py tests\test_provider_runtime.py tests\test_api.py` passed with 7 files already formatted.
- Full regression gate after final review remediation: `uv --cache-dir .uv-cache run pytest -q` passed with 545 tests and 2 skipped.
- Full lint gate after final review remediation: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate after final review remediation: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.

Residual risks:
- This slice does not add encrypted credential storage, rotation, or secret-manager integration; it only references an existing environment variable by name.
- Bound provider approval records are not implemented; development/test can use the explicit `approved: true` external-generation bypass, while staging/production rejects that bypass.
- Exact provider allowlists still trust operator-provided host configuration; broader DNS/IP/network guardrails remain future security work.
- No streaming, circuit breaker, global retry budget, cost accounting, or provider-specific external adapters beyond the generic OpenAI-compatible contract are included.

Role boundary:
- Developer-owned files: `.env.example`, `src/dgentic/api/routes.py`, `src/dgentic/provider_policy.py`, `src/dgentic/provider_runtime.py`, `src/dgentic/providers.py`, and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Commit/push the stable BL-006c checkpoint, then continue Sprint 12 with credential strategy or streaming depending on risk priority.

### Sprint 12 BL-006b Provider Transport Retry And Backoff

Status: completed for the scoped non-streaming provider transport/retry slice; Sprint 12 remains open for production external adapters, credential handling, circuit breakers, cost accounting, and streaming generation.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected a bounded follow-up after BL-006a to add shared transport and deterministic retry/backoff without introducing external credentials or public retry controls.
- Completed: Architect read-only explorer recommended `provider_transport.py`, shared JSON transport contracts, retry metadata in event logs only, and single-attempt health probes.
- Completed: QA read-only explorer recommended fake transport/sleep tests for `429`, upstream `5xx`, exhausted retries, retry-after handling, non-retry 4xx, safe logs, and API status mapping.
- Completed: Developer updated production source only for shared transport contracts, bounded generation retry/backoff settings, safe transport error metadata, API `429` mapping for exhausted provider rate limits, non-retry health probes, and safer provider response shape handling.
- Completed: QA updated tests only for retry success, retry exhaustion, `Retry-After` capping/invalid/non-finite cases, no retry for ordinary 4xx including `408`, no retry for malformed JSON, API `429`/`502` mappings, health no-retry behavior, and no real sleeps/network.
- Completed: Reviewer/Security found blockers for `408` retry and non-finite `Retry-After`; fixes were routed through Dev and QA.
- Completed: Final remediation review found no blockers.

Feature tracking:
- Implemented in this slice: `ProviderRetryPolicy`, `ProviderTransportRequest`, `ProviderTransportResult`, and `send_provider_json_request` centralize JSON provider transport behavior.
- Implemented in this slice: generation retries bounded retryable failures, currently `429` and upstream `500/502/503/504`, with default delays of `0.2s`, `0.4s`, capped at `2.0s`.
- Implemented in this slice: numeric `Retry-After` is honored and capped; invalid, `NaN`, and infinity values fall back to deterministic backoff.
- Implemented in this slice: provider `400/401/403/404/408`, policy failures, unsupported features, and malformed upstream JSON are not retried.
- Implemented in this slice: provider health/model probes use the shared transport with `max_attempts=1`.
- Implemented in this slice: provider completion/failure logs expose safe attempt/retry/status metadata without raw upstream response bodies or prompt/completion content.

Validation:
- Focused provider retry gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py -k "provider"` passed with 38 tests and 45 deselected.
- Broad touched-surface regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py tests\test_tool_runtime.py tests\test_auth.py` passed with 145 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\provider_transport.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py src\dgentic\settings.py tests\test_provider_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\provider_transport.py src\dgentic\provider_runtime.py src\dgentic\providers.py src\dgentic\api\routes.py src\dgentic\settings.py tests\test_provider_runtime.py tests\test_api.py` passed with 7 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 520 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 47 files already formatted.

Residual risks:
- Retry amplification is bounded but still per-request; global retry budgets, jitter, and circuit breakers remain future production work.
- This slice does not add external provider adapters, credential storage, cost accounting, or streaming.
- Negative `Retry-After` clamps to immediate retry, safely bounded by max attempts.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/provider_runtime.py`, `src/dgentic/provider_transport.py`, `src/dgentic/providers.py`, and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Commit/push the stable BL-006b checkpoint, then continue Sprint 12 with the provider adapter boundary and credential strategy.

### Sprint 12 BL-006a Provider Egress Policy And Safe Telemetry

Status: completed for the scoped provider endpoint-policy and telemetry-hardening slice; Sprint 12 remains open for production external adapters, credentials, retry/rate-limit handling, and streaming generation.

Current story:
- BL-006: Provider System Productionization.

Checklist:
- Completed: PM selected a Full Sprint security/API slice because provider endpoints, outbound network behavior, and logs are security-sensitive.
- Completed: Architect and QA read-only explorers recommended starting with provider egress policy, disabled external placeholder routing, and safe telemetry before adding real external credentials.
- Completed: Developer updated production source only for shared provider endpoint policy, redirect blocking, generation/health allowlist enforcement, safe configured URL display, disabled external placeholder behavior, safe provider metadata, and generic upstream JSON failure mapping.
- Completed: QA updated tests only for provider allowlist rejection before network calls, unsupported streaming, external placeholder rejection, safe metadata/log behavior, redirect blocking, health-probe policy enforcement, no configured URL credential leaks, malformed upstream JSON mapping, and no-capable-provider routing.
- Completed: Reviewer/Security found initial blockers for redirect egress, health probes outside policy, and malformed JSON status mapping; these were routed back through Dev and QA.
- Completed: Final Reviewer/Security read-only pass found no blockers.

Feature tracking:
- Implemented in this slice: provider generation accepts only exact configured or explicitly allowlisted base URLs, strips query/fragment/userinfo, blocks disallowed overrides before network calls, and rejects redirects through a shared provider opener.
- Implemented in this slice: provider health/model discovery uses the same endpoint policy path as generation.
- Implemented in this slice: `/providers` displays only normalized safe base URLs, suppressing malformed or credential-bearing configured URLs.
- Implemented in this slice: `external-placeholder` is disabled, non-routable, and returns an explicit not-implemented response if generation is requested.
- Implemented in this slice: provider completion events omit raw prompt/completion content and persist only safe metadata such as duration, content length, finish reasons, and numeric usage counters.
- Implemented in this slice: malformed upstream JSON is wrapped as a provider failure and mapped to generic `502` API detail instead of a client `400`.

Validation:
- Focused provider gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py -k "provider"` passed with 16 tests and 45 deselected.
- Broad touched-surface regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_provider_runtime.py tests\test_api.py tests\test_tool_runtime.py tests\test_auth.py` passed with 123 tests.
- Focused source lint/format gates passed for provider policy/runtime/catalog/API/schema/settings/redaction files.
- Focused QA lint/format gates passed for provider/API tests.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 498 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 46 files already formatted.

Residual risks:
- This slice does not add production external provider adapters or credentials.
- Retry, backoff, rate-limit, circuit-breaker, cost accounting, and streaming support remain future Sprint 12 work.
- Provider response shape validation is still lightweight beyond malformed JSON handling.
- The allowlist is exact and conservative; misconfigured provider base URLs fail closed.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/provider_policy.py`, `src/dgentic/provider_runtime.py`, `src/dgentic/providers.py`, `src/dgentic/redaction.py`, `src/dgentic/schemas.py`, and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_provider_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Commit/push the stable BL-006a checkpoint, then continue Sprint 12 with retry/backoff and provider adapter-boundary work.

### Sprint 11 BL-005g Generated-Tool Version Migration Policy

Status: completed for the scoped no-migration version policy slice; Sprint 11 remains open for full OS/filesystem/network sandbox isolation and production package/dependency lifecycle management.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM selected bounded same-name version migration as the next Sprint 11 slice after the pushed BL-005f checkpoint.
- Completed: Architect read-only explorer recommended a no-schema-migration slice because the current SQL registry intentionally has one unique row per tool name and runtime selection is name-based.
- Completed: QA read-only explorer recommended deterministic version-policy tests for same-version conflicts, newer-version overwrite requirements, successful migration, and SQL lifecycle reset.
- Completed: Developer updated production source only for monotonic generated-tool version policy, in-place SQL registry update/reset behavior, and precise API conflict handling.
- Completed: QA updated tests only for generated-tool version migration conflicts, accepted newer-version migration, no file rewrites on conflict, JSON/SQL manifest consistency, and registry lifecycle reset.
- Completed: Focused and full regression, lint, and format gates for this Sprint 11 slice.

Feature tracking:
- Implemented in this slice: same-name generated-tool regeneration requires `overwrite=true` and a strictly newer version than both the local JSON manifest and SQL registry row.
- Implemented in this slice: same-version, older-version, or missing-overwrite regeneration conflicts are rejected before generated files are rewritten.
- Implemented in this slice: different tool names with duplicate SQL interface signatures are still blocked before file writes.
- Implemented in this slice: accepted same-name migrations update `tool.py`, `manifest.json`, README, local JSON state, and the existing SQL registry row.
- Implemented in this slice: the SQL registry row id remains stable during bounded migration, while version, interface signature, permission, tags, description, and created-by-agent metadata update.
- Implemented in this slice: SQL usage counters, reliability score, last-used timestamp, and deprecation flag reset for the new generated artifact version.

Validation:
- Focused version gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py::test_dynamic_tool_generation_requires_newer_overwrite_for_version_migration tests\test_tool_registry.py::TestToolRegistry::test_update_tool_registration_resets_version_runtime_state` passed with 2 tests.
- Focused tool/API/registry gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py tests\test_tool_registry.py tests\test_tool_runtime.py -k "tool or registry or version or duplicate or reliability"` passed with 60 tests and 34 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\tools\__init__.py src\dgentic\tools\registry_service.py src\dgentic\api\routes.py tests\test_api.py tests\test_tool_registry.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\tools\__init__.py src\dgentic\tools\registry_service.py src\dgentic\api\routes.py tests\test_api.py tests\test_tool_registry.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 487 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.

Residual risks:
- This slice keeps one SQL registry row per generated tool name; true parallel multi-version rows would require a dedicated migration, `(tool_name, version)` uniqueness, active/latest selection semantics, runtime version selection, and likely versioned artifact paths.
- Version comparison is intentionally lightweight for DGentic-generated version strings; strict packaging-version validation remains future hardening if external publishing semantics become necessary.
- Full OS/filesystem/network sandbox isolation remains open.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/tools/__init__.py`, and `src/dgentic/tools/registry_service.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_tool_registry.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- No untracked files are present.

Next:
- Continue with explicit sandbox design or move to the next backlog sprint if PM accepts the remaining sandbox/package lifecycle items as future production-hardening work after this stable checkpoint is pushed.

### Sprint 11 BL-005f Generated-Tool Process Cleanup Hardening

Status: completed for the scoped generated-tool process cleanup slice; Sprint 11 remains open for full OS/filesystem/network sandbox isolation, production package/dependency lifecycle management, and richer version migration policy.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM selected process cleanup hardening as the next Sprint 11 slice after the pushed BL-005e checkpoint because it improves timeout/process boundaries without claiming a full OS sandbox.
- Completed: QA read-only explorer recommended deterministic fake-process coverage for launch isolation, timeout cleanup, POSIX process-group cleanup, and Windows taskkill fallback.
- Completed: Developer updated production source only to replace one-shot `subprocess.run` generated-tool execution with controlled `Popen`, process-group/new-process-group startup where supported, timeout cleanup, partial-output drain after timeout, and Windows taskkill failure fallback.
- Completed: QA updated tests only for controlled `Popen` launch args/env/pipe wiring, timeout cleanup delegation, host process-tree termination behavior, Windows taskkill timeout fallback, and timeout redaction regression.
- Completed: Focused and full regression, lint, and format gates for this Sprint 11 slice.

Feature tracking:
- Implemented in this slice: generated-tool execution uses explicit `Popen` launch controls instead of one-shot `subprocess.run`.
- Implemented in this slice: POSIX hosts launch generated tools with a new session/process group; Windows hosts use `CREATE_NEW_PROCESS_GROUP` when available.
- Implemented in this slice: timed-out generated tools invoke process-tree cleanup, preserve available partial stdout/stderr, append the timeout message, and still record the run as a failed reliability attempt.
- Implemented in this slice: POSIX timeout cleanup attempts process-group TERM then KILL when the first wait expires.
- Implemented in this slice: Windows timeout cleanup calls `taskkill /PID <pid> /T /F` and falls back to `process.kill()` if taskkill fails or times out.
- Implemented in this slice: execution audit metadata marks generated-tool process isolation as `process-group`.

Validation:
- Focused cleanup gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py::test_tool_subprocess_does_not_inherit_host_python_environment tests\test_tool_runtime.py::test_timed_out_tool_terminates_process_tree tests\test_tool_runtime.py::test_terminate_tool_process_tree_uses_host_tree_termination tests\test_tool_runtime.py::test_windows_taskkill_failure_falls_back_to_process_kill tests\test_tool_runtime.py::test_timed_out_tool_redacts_partial_output_and_records_audit_event` passed with 5 tests.
- Focused tool/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_api.py -k "tool or approval or dependency or timeout"` passed with 49 tests and 24 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\tool_runtime.py tests\test_tool_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\tool_runtime.py tests\test_tool_runtime.py tests\test_api.py` passed with 3 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 485 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.

Residual risks:
- This is process cleanup hardening, not a full sandbox; generated tools still run as local Python subprocesses under the same operating-system user.
- The runtime still does not enforce filesystem, network, syscall, CPU, or memory isolation for generated tools.
- SQL registry versioning remains conservative: one row per generated tool name instead of parallel version rows or migrations.

Role boundary:
- Developer-owned files: `src/dgentic/tool_runtime.py`.
- QA-owned files: `tests/test_tool_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- No untracked files are present after the BL-005e checkpoint; previous backup files are no longer in the working tree.

Next:
- Completed checkpoint commit and push for this Sprint 11 slice as `1c69e19`; continue Sprint 11 with richer version migration policy or explicit full sandbox design.

### Sprint 11 BL-005e Per-Tool Local Dependency Import Isolation

Status: completed for the scoped local dependency import isolation slice; Sprint 11 remains open for OS/process sandboxing, production package/dependency lifecycle management, and richer version migration policy.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM selected local-only dependency import isolation as the next Sprint 11 slice after the pushed BL-005d checkpoint because it is a bounded safety improvement before heavier OS/process sandboxing.
- Completed: Architect/Dev read-only explorer reviewed the generated-tool creation/runtime path and recommended finishing manifest dependency paths, isolated Python launch flags, explicit fail-closed dependency path validation, and generation persistence.
- Completed: QA read-only explorer mapped the smallest high-value dependency isolation regressions.
- Completed: Developer updated production source only for manifest/generation dependency paths, isolated generated-tool subprocess import semantics, host Python/virtualenv/library path environment stripping, standard tool-local dependency directories, dependency path audit metadata, and explicit dependency path fail-closed behavior.
- Completed: QA updated tests only for app runtime dependency non-inheritance, explicit and standard local dependency import success, symlink escape blocking before execution, missing explicit dependency path blocking before usage counters increment, generated manifest dependency path persistence, and subprocess environment inheritance.
- Completed: Focused and full regression, lint, format, and diff hygiene gates for this Sprint 11 slice.

Feature tracking:
- Implemented in this slice: generated tool manifests and generation requests can carry validated `dependency_paths` that must be relative paths under the generated tool directory.
- Implemented in this slice: generated tools execute with Python isolated import semantics using `-I`, `-S`, and UTF-8 mode, then the runner injects only the tool directory plus validated tool-local dependency directories.
- Implemented in this slice: host Python import environment variables such as `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `CONDA_PREFIX`, `LD_LIBRARY_PATH`, and `DYLD_LIBRARY_PATH` are not inherited by generated-tool subprocesses.
- Implemented in this slice: standard local dependency directories such as `vendor` are supported when present, while explicit dependency paths fail closed when missing, absolute, non-directory, escaping, or symlinked.
- Implemented in this slice: dependency path blocks happen before the subprocess starts and before generated-tool usage counters increment.
- Implemented in this slice: execution audit metadata records local-only dependency isolation and dependency paths relative to the generated tool directory.

Validation:
- Focused dependency/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_api.py -k "dependency or dynamic_tool_generation or generated_tool_execute_api_updates_reliability"` passed with 10 tests and 60 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\schemas.py src\dgentic\tool_runtime.py src\dgentic\tools\__init__.py tests\test_tool_runtime.py tests\test_api.py` passed.
- Focused format gate after formatting: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\schemas.py src\dgentic\tool_runtime.py src\dgentic\tools\__init__.py tests\test_tool_runtime.py tests\test_api.py` passed with 5 files already formatted.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 482 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.

Residual risks:
- This is import/dependency-path isolation, not a full OS/process sandbox; generated tools still run as local Python subprocesses under the same operating-system user.
- DGentic still does not install, lock, update, or vulnerability-scan per-tool packages; operators must vendor dependencies into tool-local directories for this slice.
- SQL registry versioning remains conservative: one row per generated tool name instead of parallel version rows or migrations.

Role boundary:
- Developer-owned files: `src/dgentic/schemas.py`, `src/dgentic/tool_runtime.py`, and `src/dgentic/tools/__init__.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_tool_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Completed checkpoint commit and push for this Sprint 11 slice as `0735678`; continue Sprint 11 with process hardening or richer version migration policy.

### Sprint 11 BL-005d Runtime Reliability Policy Automation

Status: completed for the scoped runtime reliability policy slice; Sprint 11 remains open for sandboxing, dependency isolation, and richer version migration policy.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM selected reliability-score policy automation as the next Sprint 11 slice after the pushed BL-005c checkpoint.
- Completed: Architect explorer reviewed current JSON/SQL reliability tracking and recommended evidence-gated policy thresholds plus SQL registry usage sync for actual tool executions.
- Completed: Developer updated production source only for runtime reliability policy actions, SQL registry usage sync, SQL deprecation sync for very low-reliability generated tools, and reliability policy audit metadata.
- Completed: QA updated tests only for warning, automatic disable, automatic deprecation, SQL usage sync, and SQL deprecation sync behavior.
- Completed: Final full regression, lint, format, and diff hygiene gates for this Sprint 11 slice.
- Completed: Checkpoint commit and push for this Sprint 11 slice as `3aaf992`.

Feature tracking:
- Implemented in this slice: actual generated-tool executions sync usage, success, failure, and reliability score into the SQL registry row when one exists.
- Implemented in this slice: reliability policy waits for at least five runtime attempts before warning or disabling a tool, so a single bad run does not trigger governance automation.
- Implemented in this slice: tools with low but still usable reliability emit warning audit events while remaining active.
- Implemented in this slice: repeatedly weak tools are automatically disabled in the JSON manifest and rejected on later execution.
- Implemented in this slice: very low-reliability tools with enough history are automatically deprecated in the JSON manifest and the SQL registry row is marked deprecated when present.
- Implemented in this slice: pre-execution blocks such as rejected approvals, deprecated tools, permission conflicts, and missing tools still do not increment reliability counters.

Validation:
- Focused reliability gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py::test_reliability_policy_warns_without_disabling_low_score_tool tests\test_tool_runtime.py::test_reliability_policy_deprecates_consistently_weak_tool tests\test_tool_runtime.py::test_reliability_policy_disables_repeatedly_failing_tool tests\test_tool_runtime.py::test_execute_tool_syncs_sql_registry_usage_and_deprecation` passed with 4 tests.
- Focused tool/API/registry gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_api.py -k "tool or approval or reliability"` passed with 39 tests and 25 deselected; `uv --cache-dir .uv-cache run pytest -q tests\test_tool_registry.py` passed with 19 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\tool_runtime.py tests\test_tool_runtime.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\tool_runtime.py tests\test_tool_runtime.py` passed.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 476 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.
- Diff hygiene gate: `git diff --check` passed with Windows line-ending warnings only.

Residual risks:
- Runtime reliability automation is scoped to actual generated-tool execution; manual SQL registry `/usage` calls still record counters without applying the same JSON tool governance action.
- Tool execution remained a local Python subprocess without OS/process sandboxing or per-tool dependency isolation at BL-005d close; per-tool local dependency import isolation was completed later in BL-005e.
- SQL registry versioning remains conservative: one row per generated tool name instead of parallel version rows or migrations.

Role boundary:
- Developer-owned files: `src/dgentic/tool_runtime.py`.
- QA-owned files: `tests/test_tool_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Continue Sprint 11 with sandbox hardening, dependency isolation, or richer version migration policy.

### Sprint 11 BL-005c Bound Tool Approval Records

Status: completed for the scoped bound-approval slice; Sprint 11 remained open for sandboxing, dependency isolation, and reliability policy automation, with reliability policy automation completed later in BL-005d.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM selected bound generated-tool approvals as the next Sprint 11 slice after the pushed BL-005b checkpoint because caller-supplied approval remained the largest execution-safety gap.
- Completed: Architect explorer reviewed the CLI approval implementation and recommended a tool-specific JSON approval store with redacted review payloads, HMAC binding digests, single-use claims, and UI-safe review endpoints.
- Completed: Developer updated production source only for tool approval records, payload/full-artifact-tree/approval digests, approval create/list/review/approve/deny APIs, production/staging rejection of `approved: true`, and single-process approval claiming before subprocess execution.
- Completed: QA updated tests only for production rejection of caller-supplied approval, bound approval creation/review/approval/execution, payload mismatch rejection, single-use execution in the local JSON runtime, redacted persisted payloads and decision reasons, denied/expired approval rejection, and generated helper artifact drift invalidation.
- Completed: Final read-only reviewer found helper/import artifact drift, missing reviewer capability boundary, unredacted identity/context fields, and a multi-process JSON claim caveat; Developer and QA resolved the first three and recorded the multi-process caveat as residual risk.
- Completed: Final full regression, lint, format, and diff hygiene gates for this Sprint 11 slice.
- Completed: Checkpoint commit and push for this Sprint 11 slice.

Feature tracking:
- Implemented in this slice: approval-required generated tools need an approved `approval_id` outside development/test mode.
- Implemented in this slice: tool approval records store redacted payload previews plus HMAC digests for payload, full generated artifact tree, and approval binding rather than raw payload values.
- Implemented in this slice: approval binding covers tool name, version, status, selected entrypoint, generated artifact tree digest, timeout, requester, agent/task context, permission mode, and payload digest.
- Implemented in this slice: generated tool approval APIs create, list, review, approve, and deny approval records using the existing safe decision-reason redaction and authenticated-decider helper; approve/deny routes require the separate `approvals` capability when auth is enabled.
- Implemented in this slice: approval records are claimed before subprocess launch in the local JSON runtime, making them single-use for a single backend process even when tool execution fails or times out after claim.
- Implemented in this slice: requester, agent, task, and reviewer identity/context fields are redacted before persisted approval records or API responses expose them.

Validation:
- Focused reviewer-remediation gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py::test_production_approval_required_tool_requires_bound_approval tests\test_tool_runtime.py::test_bound_tool_approval_rejects_artifact_drift tests\test_tool_runtime.py::test_bound_tool_approval_rejects_denied_and_expired_records tests\test_api.py::test_tool_approval_approve_api_requires_approvals_capability tests\test_api.py::test_generated_tool_execute_api_requires_bound_approval_in_production tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes` passed with 19 tests.
- Focused bound approval gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py::test_production_approval_required_tool_requires_bound_approval tests\test_tool_runtime.py::test_bound_tool_approval_rejects_artifact_drift tests\test_api.py::test_generated_tool_execute_api_requires_bound_approval_in_production` passed with 3 tests.
- Focused tool/API approval regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_api.py -k "tool or approval"` passed with 33 tests and 25 deselected.
- Focused registry/policy regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_registry.py tests\test_command_policy.py` passed with 284 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\tool_runtime.py src\dgentic\api\routes.py src\dgentic\schemas.py tests\test_tool_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\tool_runtime.py src\dgentic\api\routes.py src\dgentic\schemas.py tests\test_tool_runtime.py tests\test_api.py` passed.
- Focused reviewer-remediation regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_api.py -k "tool or approval" tests\test_auth.py::test_capability_for_path_maps_public_and_sensitive_routes` passed with 37 tests and 37 deselected.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 472 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.
- Diff hygiene gate: `git diff --check` passed with Windows line-ending warnings only.

Residual risks:
- Tool execution is still a local Python subprocess without OS/process sandboxing or per-tool dependency isolation.
- Approval records are local JSON MVP state, not migration-managed production SQL records.
- Approval claiming uses process-local JSON locking; production multi-worker process-safe single-use claims still need durable SQL or file-lock-backed compare-and-set semantics.
- Development/test mode still permits `approved: true` for local smoke checks.

Role boundary:
- Developer-owned files: `src/dgentic/auth.py`, `src/dgentic/schemas.py`, `src/dgentic/tool_runtime.py`, and `src/dgentic/api/routes.py`.
- QA-owned files: `tests/test_api.py`, `tests/test_auth.py`, and `tests/test_tool_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Continue Sprint 11 with runtime reliability policy automation, sandbox hardening, dependency isolation, or richer version migration policy.

### Sprint 11 BL-005b Tool Execution Redaction And Audit Events

Status: completed for the scoped tool-output redaction and audit slice; Sprint 11 remained open for bound approvals, sandboxing, dependency isolation, and reliability policy automation.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM selected the next Sprint 11 slice after the pushed BL-005a checkpoint, prioritizing data-exposure reduction before heavier sandbox/dependency work.
- Completed: Developer updated production source only for redacting tool stdout, stderr, parsed JSON output, and recording tool execution audit metadata without raw output or payload content.
- Completed: Developer fixed a shared redaction edge case where a secret-like flag following another secret assignment could leave the flag value visible.
- Completed: QA3 updated tests only for direct `execute_tool` redaction/audit behavior and `/tools/{name}/execute` API redaction/audit behavior.
- Completed: Read-only reviewer found JSON, colon-label, and authorization-header shaped stderr leak risks plus missing failure/timeout coverage; Developer and QA resolved those findings before checkpointing.
- Completed: Final read-only reviewer found a non-Bearer authorization-header tail leak; Developer separated authorization-header redaction from generic label redaction, and QA pinned Bearer, Basic, token, and proxy authorization header cases.
- Completed: Final full regression, lint, format, and diff hygiene gates for this Sprint 11 slice.
- Completed: Checkpoint commit and push for this Sprint 11 slice.

Feature tracking:
- Implemented in this slice: tool stdout and stderr are redacted before being returned through runtime/API responses.
- Implemented in this slice: stderr redaction covers common assignment, CLI flag, JSON line, JSON field, colon-label, and authorization-header secret shapes, including Bearer, Basic, token, API-key, and proxy authorization schemes.
- Implemented in this slice: parsed JSON tool output is recursively redacted with the shared metadata redaction helper, including sensitive keys such as token/password and secret-shaped string values.
- Implemented in this slice: successful and failed tool executions record a tool audit event with status, exit code, duration, and output byte counts rather than raw payload/output content.
- Implemented in this slice: shared redaction no longer treats the suffix of a prior secret value as a secret-like flag prefix, which fixes cases such as `SECRET=value --api-key key-value`.

Validation:
- Focused leak regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py::test_failed_tool_execution_tracks_failure_and_captured_output tests\test_tool_runtime.py::test_execute_tool_redacts_secret_outputs_and_records_audit_event tests\test_tool_runtime.py::test_timed_out_tool_redacts_partial_output_and_records_audit_event tests\test_api.py::test_generated_tool_execute_api_redacts_secret_outputs_and_audits tests\test_api.py::test_generated_tool_execute_api_redacts_failed_tool_secret_outputs_and_audits tests\test_api.py::test_generated_tool_execute_api_redacts_timed_out_tool_outputs_and_audits` passed with 6 tests.
- Focused tool/API regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_api.py -k "tool or redacts"` passed with 22 tests and 33 deselected.
- Focused shared redaction regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py -k redacts tests\test_command_policy.py::test_command_policy_event_metadata_redacts_substitution_secret_values` passed with 3 tests and 56 deselected.
- Focused registry/policy regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_registry.py tests\test_command_policy.py` passed with 284 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\redaction.py src\dgentic\tool_runtime.py tests\test_api.py tests\test_tool_runtime.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\redaction.py src\dgentic\tool_runtime.py tests\test_api.py tests\test_tool_runtime.py` passed.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 466 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.
- Diff hygiene gate: `git diff --check` passed with Windows line-ending warnings only.

Residual risks:
- Redaction is still heuristic and cannot guarantee removal of arbitrary unlabeled secrets.
- Approval-required tool execution used the MVP caller-supplied `approved` flag in this slice; bound tool approval records were completed later in BL-005c.
- Tool execution is still a local Python subprocess without OS/process sandboxing or per-tool dependency isolation.

Role boundary:
- Developer-owned files: `src/dgentic/redaction.py` and `src/dgentic/tool_runtime.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_tool_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Commit and push this stable Sprint 11 checkpoint, then continue Sprint 11 with bound tool approvals, dependency isolation, or sandbox hardening.

### Sprint 11 BL-005a Tool Registry Integration And Execution Permission Hardening

Status: completed for the scoped registry-integration slice; Sprint 11 remains open for sandbox, dependency isolation, output redaction, and bound tool approvals.

Current story:
- BL-005: Tool Runtime Safety And Registry Integration.

Checklist:
- Completed: PM initiated Sprint 11 after the pushed Sprint 9/10 checkpoint.
- Completed: Read-only explorer assessed tool generation/runtime/registry gaps and recommended starting with SQL registry integration before sandbox work.
- Completed: Developer main lane updated generated-tool creation to preflight SQL registry duplicates, compute stable interface signatures, auto-register generated tools in the SQLAlchemy registry, and preserve the one-registry-row-per-tool-name policy.
- Completed: Dev2 updated production source so tool execution consults the SQL registry when present, blocks deprecated registry rows, fails closed on invalid or conflicting registry permission levels, preserves legacy JSON-only execution when no SQL row exists, and reduces inherited subprocess environment keys.
- Completed: QA2 updated tests only for generated-tool SQL registry auto-registration, SQL duplicate preflight with no file writes, deprecated registry execution blocking, and permission conflict fail-closed behavior.
- Completed: Final full regression, lint, format, and diff hygiene gates.
- Completed: Checkpoint commit and push for this Sprint 11 slice.

Feature tracking:
- Implemented in this slice: `/tools/generate` registers generated tools in both local JSON state and the SQLAlchemy-backed tool registry.
- Implemented in this slice: generated-tool duplicate checks now include SQL registry exact-name and interface-signature preflight before files are written.
- Implemented in this slice: generated-tool creation keeps a conservative one SQL registry row per generated tool name; richer multi-version registry semantics remain future work.
- Implemented in this slice: `execute_tool` fails closed if an existing SQL registry row is deprecated, has an invalid permission level, or conflicts with the local manifest permission mode.
- Implemented in this slice: generated tool subprocesses inherit a smaller environment allowlist while still setting `PYTHONIOENCODING`, `PYTHONDONTWRITEBYTECODE`, and tool-scoped `PYTHONPATH`.

Validation:
- Focused new tests: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py::test_dynamic_tool_generation_registers_sql_registry_row tests\test_api.py::test_dynamic_tool_generation_sql_duplicate_prevents_file_writes tests\test_tool_runtime.py::test_sql_registry_deprecated_tool_does_not_run tests\test_tool_runtime.py::test_sql_registry_permission_conflict_fails_closed` passed with 4 tests.
- Focused tool regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_tool_runtime.py tests\test_tool_registry.py tests\test_api.py -k "tool"` passed with 35 tests and 34 deselected.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\tools\__init__.py src\dgentic\tool_runtime.py tests\test_api.py tests\test_tool_runtime.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\tools\__init__.py src\dgentic\tool_runtime.py tests\test_api.py tests\test_tool_runtime.py` passed.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 461 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.
- Diff hygiene gate: `git diff --check` passed.

Residual risks:
- Approval-required tool execution still used the MVP caller-supplied `approved` flag in this slice; bound tool approval records were completed later in BL-005c, while interactive UI remains future work.
- Tool execution is still a local Python subprocess, not an OS/process sandbox.
- Tool output and stderr redaction were completed later in BL-005b through the shared redaction helper and tool execution audit events.
- Per-tool dependency isolation is not implemented; tools still run with the application interpreter.
- SQL registry versioning remains conservative: one row per generated tool name instead of parallel version rows or migrations.

Role boundary:
- Developer-owned files: `src/dgentic/tools/__init__.py` and `src/dgentic/tool_runtime.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_tool_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Run final full quality gates, commit and push this stable Sprint 11 checkpoint, then continue Sprint 11 with tool approval binding, output redaction, or dependency isolation.

### Sprint 10 BL-004a Filesystem Runtime Completion

Status: completed for the scoped MVP backend filesystem runtime; Sprint 10 is closed.

Current story:
- BL-004: Filesystem Runtime Completion.

Checklist:
- Completed: PM/Architect assessed the current filesystem runtime and kept the work in Full Sprint mode because file delete/move/copy operations are destructive and security-sensitive.
- Completed: Read-only explorer confirmed existing support was limited to guarded UTF-8 text read/write plus coarse read/write/delete policy checks.
- Completed: Developer updated production source only for binary read/write, metadata, list, delete, move, copy, rename, source/target rootDir checks, protected state-file checks, symlink escape handling, payload-size limits, no-overwrite defaults, recursive directory safeguards, and filesystem audit events.
- Completed: QA updated tests only for binary roundtrip, list/metadata, audit evidence, destructive approval gating, unsafe target blocking, symlink escape blocking, large-payload rejection, missing-file responses, and auth capability mapping.
- Completed: PM updated README, architecture, setup, usage, backlog, and this progress log.
- Completed: Final full regression, lint, format, and diff hygiene gates after docs.

Feature tracking:
- Implemented in this slice: `POST /filesystem/read-binary` and `POST /filesystem/write-binary` move binary payloads as base64 with configurable byte limits.
- Implemented in this slice: `POST /filesystem/list` and `POST /filesystem/metadata` expose safe directory and metadata workflows.
- Implemented in this slice: `POST /filesystem/delete`, `POST /filesystem/move`, `POST /filesystem/copy`, and `POST /filesystem/rename` require explicit destructive-operation approval, default to no overwrite, and record audit metadata.
- Implemented in this slice: policy evaluation covers operation names for text, binary, directory, metadata, delete, move, copy, and rename actions, including source and target path checks.
- Implemented in this slice: rootDir escape attempts, protected `.dgentic` state access, and symlink escapes are blocked before operation execution.
- Implemented in this slice: filesystem payload size is configurable with `DGENTIC_MAX_FILESYSTEM_BYTES`.

Validation:
- Focused filesystem API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py -k filesystem` passed with 6 tests.
- Focused auth mapping gate: `uv --cache-dir .uv-cache run pytest -q tests\test_auth.py -k filesystem` passed with 2 tests.
- Focused API/auth regression gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py tests\test_auth.py` passed with 73 tests.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\guardrails.py src\dgentic\schemas.py src\dgentic\api\routes.py src\dgentic\settings.py tests\test_api.py tests\test_auth.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\guardrails.py src\dgentic\schemas.py src\dgentic\api\routes.py src\dgentic\settings.py tests\test_api.py tests\test_auth.py` passed.
- Full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 457 tests and 2 skipped.
- Full lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Full format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.
- Diff hygiene gate: `git diff --check` passed.

Residual risks:
- Destructive filesystem operations use an explicit MVP `approved` request flag rather than bound filesystem approval records; the interactive approval UI and approval identity binding remain later backlog work.
- Filesystem policy is operation-specific and root/state-bound, but not yet a persisted configurable file-policy rule system.
- Locked-file behavior is handled through normal OS exceptions and conflict responses where applicable, but deeper platform-specific locked-file validation remains follow-up work.
- Guardrails are application-level checks, not an OS-level filesystem sandbox; TOCTOU and same-user filesystem races remain future hardening work.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/guardrails.py`, `src/dgentic/schemas.py`, and `src/dgentic/settings.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_auth.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Run final full quality gates, then proceed autonomously to Sprint 11 tool runtime safety and registry integration.

### Sprint 9 BL-002f Conservative Orphan Termination After Restart

Status: completed for the scoped single-worker restart recovery slice; Sprint 9 is closed for the MVP CLI runtime hardening scope.

Current story:
- BL-002: CLI Streaming And Restart-Resilient Supervision.

Checklist:
- Completed: PM kept the work in Full Sprint mode because post-restart CLI process handling can terminate host processes and therefore remains security- and operations-sensitive.
- Completed: Architect/DevOps recommendation kept the implementation conservative: do not attempt true process adoption because persisted records cannot recover `Popen`, pipes, return code, wait handles, or durable stdout/stderr.
- Completed: Developer updated production source only for persisted process identity metadata, orphan termination status fields, single-worker prior-supervisor termination checks, POSIX process-group termination, Windows `taskkill /T /F` termination, and stale lifecycle recording.
- Completed: QA updated tests only for missing identity skips, identity mismatch skips, matching orphan termination, POSIX and Windows termination shape, Windows taskkill timeout failure handling, and API termination metadata.
- Completed: Reviewer, Security, and DevOps gates accepted the single-worker restart-only scope with production multi-worker leases explicitly moved out of Sprint 9.
- Completed: PM updated README current status, architecture/how-to docs, backlog, and this progress log.
- Completed: Final post-doc full regression, lint, format, and diff hygiene gates in this resumed closeout.

Feature tracking:
- Implemented in this slice: async command runs persist process id, process group id where available, process identity, process start metadata, and orphan termination audit metadata.
- Implemented in this slice: reconciliation and orphan cancellation mark previous-supervisor running records stale after recording a conservative termination attempt.
- Implemented in this slice: termination is skipped for non-running records, missing supervisor/process metadata, missing process identity, and live process identity mismatches.
- Implemented in this slice: missing live processes are recorded as `not_found`, successful termination as `terminated`, and termination exceptions or timeouts as `failed` while the run still becomes stale.
- Implemented in this slice: POSIX termination targets the process group with TERM then KILL after identity recheck; Windows termination uses `taskkill /PID <pid> /T /F`.
- Still out of scope after this slice: true process adoption, durable/resumable output after backend restart, production multi-worker lease safety, and JSON-store atomic cross-process ownership.

Validation:
- Focused new termination tests: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py tests\test_api.py -k "orphan or terminate_orphaned_process or taskkill"` passed with 9 tests and 1 skipped.
- Focused CLI/API gate: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py tests\test_api.py` passed with 91 tests and 2 skipped.
- Pre-doc full gate: `uv --cache-dir .uv-cache run pytest -q` passed with 451 tests and 2 skipped.
- Final post-doc full regression gate: `uv --cache-dir .uv-cache run pytest -q` passed with 452 tests and 2 skipped.
- Final post-doc lint gate: `uv --cache-dir .uv-cache run ruff check .` passed.
- Final post-doc format gate: `uv --cache-dir .uv-cache run ruff format --check .` passed with 45 files already formatted.
- Final post-doc diff hygiene gate: `git diff --check` passed.

Review, security, and operations findings handled:
- Remediated: Windows `taskkill` timeout could escape orphan termination handling; timeout failures now record `termination_status=failed` and still mark the orphaned record stale.
- Accepted scope decision: true live process adoption was rejected for this slice because persisted JSON run records cannot safely reconstruct the process handle, pipes, output stream, or reliable return-code lifecycle after restart.

Residual risks:
- Conservative orphan termination is scoped to single-worker restart recovery. A real multi-worker deployment needs DB-backed ownership leases or an explicit single-worker deployment constraint before enabling this behavior at scale.
- The implementation does not make command output durable across backend restarts; output already persisted before restart remains available, but live stream adoption is still future work.
- PID and process-group reuse risk is narrowed by process identity checks, but cannot be reduced to zero without stronger OS/job-control integration and durable process ownership.
- JSON state remains local-file persistence without atomic cross-process leases.

Role boundary:
- Developer-owned files: `src/dgentic/cli_runtime.py`.
- QA-owned files: `tests/test_cli_runtime.py` and `tests/test_api.py`.
- Reviewer, Security, Architect, and DevOps were read-only for this slice.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Start Sprint 10 with filesystem runtime completion, while keeping full process adoption/resumable output and production multi-worker CLI leases in follow-up backlog for persistence/deployment hardening.

### Sprint 9 BL-003c Windows/POSIX Shell Semantics Hardening

Status: completed for the scoped shell-semantics slice; final Reviewer and Security gates approved with residual risks recorded.

Current story:
- BL-003: CLI Parsing And Approval Review UX Contracts.

Checklist:
- Completed: PM kept the work in Full Sprint mode because CLI shell parsing, launcher payload inspection, protected state-file checks, and secret redaction are security-sensitive.
- Completed: Developer updated production source only for shell flag parsing, context-specific escape handling, launcher payload policy evaluation, protected state-file path decoding, PowerShell flow-token scanning, safe-rule downgrade prevention, and PowerShell backtick secret redaction.
- Completed: QA updated tests only for Windows/POSIX wrapper semantics, command-name escape decoding, `cmd` combined `/c` forms, POSIX `sh`/`bash -c` script boundaries, PowerShell script blocks, Start-Process blocked/approval payloads, escaped `.dgentic` state paths, and backtick-escaped secret values.
- Completed: Reviewer and Security findings were routed back through explicit Developer and QA lanes until all blocking findings were cleared.
- Completed: PM updated README current status, backlog, and this progress log.
- Completed: Final post-doc DevOps full-suite, lint, format, and diff hygiene gates.

Feature tracking:
- Implemented in this slice: command policy recognizes PowerShell `/Command`, `/C`, inline `-Command:`/`-Command=`, and abbreviated `-Com`/`/Com` forms.
- Implemented in this slice: command policy recognizes `cmd` combined switch forms such as `/d/s/c`, `/d/s/cdel`, and `/c=del`, including nested launcher cases.
- Implemented in this slice: POSIX `sh`/`bash -c` inspection treats only the next argument as the shell script, preserving `$0`/positional arguments as data.
- Implemented in this slice: context-specific escape handling now distinguishes POSIX backslash, Windows cmd caret, and PowerShell backtick semantics, including line continuations and single-quote behavior.
- Implemented in this slice: shell command-name decoding covers POSIX quote-splitting, ANSI-C `$'...'` hex/octal/unicode escapes, cmd caret escapes, and PowerShell backtick escapes.
- Implemented in this slice: Start-Process/launcher payloads are evaluated before configured safe-rule fallback, including blocked commands, approval-required opaque payloads, and read-only path rootDir violations.
- Implemented in this slice: protected DGentic state-file checks decode common shell escape forms before matching `.dgentic` and data-dir paths.
- Implemented in this slice: approval/log redaction covers PowerShell backtick-escaped unquoted secret values.

Validation:
- Focused policy gate: `uv --cache-dir .uv-cache run pytest -q tests\test_command_policy.py` passed with 265 tests.
- Focused API/runtime gate: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py tests\test_api.py` passed with 86 tests and 1 skipped.
- Combined focused gate: `uv --cache-dir .uv-cache run pytest -q tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py` passed with 351 tests and 1 skipped.
- Focused lint gate: `uv --cache-dir .uv-cache run ruff check src\dgentic\command_policy.py src\dgentic\redaction.py tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py` passed.
- Focused format gate: `uv --cache-dir .uv-cache run ruff format --check src\dgentic\command_policy.py src\dgentic\redaction.py tests\test_command_policy.py tests\test_cli_runtime.py tests\test_api.py` passed.
- Full DevOps gate: `uv --cache-dir .uv-cache run pytest -q` passed with 447 tests and 1 skipped.
- `uv --cache-dir .uv-cache run ruff check .` passed.
- `uv --cache-dir .uv-cache run ruff format --check .` passed.
- `git diff --check` passed.

Review and security findings handled:
- Remediated: Start-Process payload inspection could miss read-only path rootDir violations and allow broad configured safe rules to downgrade them.
- Remediated: protected DGentic state-file checks did not decode cmd caret or PowerShell backtick escaped path tokens before matching `.dgentic` paths.
- Remediated: one escaped-control test expectation was Windows-specific and conflicted with POSIX-translated `cmd` wrapper semantics.
- Remediated: PowerShell script-block constructs such as `try`, `catch`, `finally`, `switch`, and `trap` could hide blocked commands behind approval-required flow tokens.
- Remediated: configured safe rules could downgrade Start-Process payloads that should remain approval-required, such as opaque PowerShell encoded commands or approval-required executables.
- Remediated: shared redaction could leave suffixes of PowerShell backtick-escaped secret values visible in approval review or log contexts.

Residual risks:
- The command policy remains tokenizer-based rather than a complete cmd, PowerShell, or POSIX shell parser; future edge cases should continue to be handled with explicit regressions.
- CLI execution remains policy/cwd-bound rather than OS-sandboxed; path TOCTOU races and non-built-in command behavior remain future hardening work.
- Redaction logic is still duplicated between command-policy event metadata and shared redaction helpers; future changes should consolidate this to avoid drift.
- True post-restart process adoption/resumable output and production multi-worker lease semantics remain future DevOps/persistence hardening work; conservative safe termination was completed later in BL-002f.

Role boundary:
- Developer-owned files: `src/dgentic/command_policy.py` and `src/dgentic/redaction.py`.
- QA-owned files: `tests/test_command_policy.py`, `tests/test_cli_runtime.py`, and `tests/test_api.py`.
- Reviewer and Security were read-only.
- PM-owned files: `README.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Superseded by BL-002f conservative orphan termination closeout; continue next with Sprint 10 while tracking full process adoption/resumable output and production multi-worker leases as follow-up backlog.

## 2026-05-10

### Sprint 9 BL-002e JSON State Quarantine And Repair

Status: completed for the scoped storage-hardening slice; final Reviewer, Security, and DevOps gates approved with residual risks recorded.

Current story:
- BL-002: CLI Streaming And Restart-Resilient Supervision.

Checklist:
- Completed: PM kept the work in Full Sprint mode because JSON state supports CLI approvals/runs, logs, tasks, agents, memory, tools, and sessions.
- Completed: Architect/PM scoped the slice to corrupt JSON quarantine and restore helpers instead of broader database migration or multi-worker locking.
- Completed: Developer updated production source only for malformed/invalid JSON collection quarantine, restore helpers, pre-restore active backups, safe restore path resolution, active symlink quarantine, broken symlink handling, and exclusive temp-file save replacement.
- Completed: QA updated tests only for malformed JSON, invalid records, upsert repair, restore from quarantine, external restore rejection, symlink quarantine rejection, active symlink list/upsert handling, broken active symlink handling, planted temp symlink handling, and default relative restore paths.
- Completed: Reviewer and Security findings were routed back through explicit Developer and QA lanes until all in-scope blockers were cleared.
- Completed: DevOps validation passed focused storage, focused API/CLI, repository lint/format, and full regression gates.
- Completed: PM updated README, architecture, setup, backlog, and progress docs.

Feature tracking:
- Implemented in this slice: `JsonCollection` quarantines malformed JSON, non-list JSON, invalid model records, active collection symlinks, and broken active symlinks by moving the original path to a timestamped quarantine and repairing the active collection to an empty array.
- Implemented in this slice: `list_quarantined_files()` and `restore_quarantine()` support operator/test repair workflows for valid quarantined files, while rejecting external paths and symlinked quarantine files.
- Implemented in this slice: restoring a quarantine preserves the current active file first as a `pre-restore` quarantine to reduce accidental data loss.
- Implemented in this slice: normal saves use exclusive temp-file creation and replace the active path, avoiding writes through planted temp symlinks or active symlinks.
- Still out of scope after this slice: cross-process file locking, full no-follow filesystem primitives, JSON-to-database migration, true process adoption or safe termination after restart, and production multi-worker lease semantics.

Validation:
- Focused storage gate: `uv --cache-dir .uv-cache run pytest -q tests\test_storage.py -vv` passed with 11 tests.
- Focused API/CLI gate: `uv --cache-dir .uv-cache run pytest -q tests\test_api.py tests\test_cli_runtime.py` passed with 84 tests and 1 skipped.
- Full DevOps gate: `uv --cache-dir .uv-cache run pytest -q` passed with 391 tests and 1 skipped.
- `uv --cache-dir .uv-cache run ruff check .` passed.
- `uv --cache-dir .uv-cache run ruff format --check .` passed.

Review and security findings handled:
- Remediated: default restore path bypassed the explicit path safety checks and could select unsafe symlink candidates.
- Remediated: explicit restore path handling failed for default relative data-dir paths and absolute paths returned from quarantine listing.
- Remediated: restore could overwrite current active state without first preserving it.
- Remediated: active collection symlinks could be followed on normal list/upsert/save flows.
- Remediated: broken active symlinks remained in place because `exists()` was checked before `is_symlink()`.
- Remediated: timestamped temp saves could follow a planted temp symlink.

Residual risks:
- JSON state remains best-effort local file persistence with per-instance locking only; concurrent processes, malicious same-directory writers, or filesystem races can still cause TOCTOU or lost-update issues.
- Quarantined files preserve raw bytes and may contain historical secrets; operators should protect and clean `.corrupt-*` and `.pre-restore-*` files as local state.

Role boundary:
- Developer-owned files: `src/dgentic/storage.py`.
- QA-owned files: `tests/test_storage.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Next:
- Continue Sprint 9 with broader Windows/POSIX shell semantics validation, or split true restart process recovery and production multi-worker lease semantics into a later persistence/DevOps hardening sprint.

### Sprint 9 BL-003b Approval Review Backend Contract

Status: completed for the scoped backend/API slice; Sprint 9 remains open for remaining CLI hardening items.

Current story:
- BL-003: CLI Parsing And Approval Review UX Contracts.

Checklist:
- Completed: PM kept the work in Full Sprint mode because approval review, CLI execution, audit logs, and secret redaction are security-sensitive.
- Completed: Developer updated production source only for `CommandApprovalReview`, `GET /cli/approvals/{approval_id}/review`, approve/deny decision reason persistence, shared redaction helpers, event-log response redaction, legacy reason sanitization, and direct-execute digest validation.
- Completed: QA updated tests only for safe review contracts, decision reason auditing, decision reason redaction, legacy persisted approval reason redaction, legacy event-log metadata redaction, structured sensitive key redaction, legacy digest direct-execute blocking, and deterministic launch-failure record selection.
- Completed: Reviewer and Security findings were routed back through explicit Developer and QA lanes until in-scope blockers were cleared.
- Completed: DevOps validation passed focused runtime/API, repository lint/format, and full regression gates.
- Completed: PM updated README, architecture, how-to, backlog, and progress docs.

Feature tracking:
- Implemented in this slice: approval reviewers can call `GET /cli/approvals/{approval_id}/review` for a safe UI-facing contract containing redacted command text, cwd, timeout, permission mode, policy reason, requester, agent/task context, environment key names, matched policy metadata, HMAC digest identifiers, bound-execution warnings, direct-execute availability, decision actor/reason fields, run id, and timestamps.
- Implemented in this slice: approve and deny decisions persist a redacted `decision_reason`; deny also preserves redacted `denial_reason`; authenticated API approval continues to prefer the authenticated principal over caller-supplied `decided_by`.
- Implemented in this slice: shared redaction now covers common secret assignments, secret-like flags, balanced shell-substitution values, structured sensitive metadata keys, and legacy log response fields for `/logs`.
- Implemented in this slice: direct approval execution no longer advertises or allows execution for legacy/invalid binding digests, while redacted-command and environment-bound approvals steer users to bound `/cli/execute` or `/cli/runs` requests.
- Still out of scope after this slice: interactive approval UI, broader Windows/POSIX shell semantics validation, true post-restart process adoption or safe termination, production multi-worker lease semantics, and non-heuristic secret detection.

Validation:
- Focused QA/DevOps gate: `uv --cache-dir .uv-cache run pytest -q tests\test_cli_runtime.py tests\test_api.py` passed with 84 tests and 1 skipped.
- Full DevOps gate: `uv --cache-dir .uv-cache run pytest -q` passed with 380 tests and 1 skipped.
- `uv --cache-dir .uv-cache run ruff check .` passed.
- `uv --cache-dir .uv-cache run ruff format --check .` passed.

Review and security findings handled:
- Remediated: decision reasons could persist raw secret-shaped text.
- Remediated: legacy persisted approval `decision_reason` or `denial_reason` values could leak through approval list/review consumers.
- Remediated: legacy approval audit-log metadata could leak through `/logs`.
- Remediated: event-log redaction initially missed balanced shell substitutions, structured sensitive metadata keys, plural/camelCase secret keys, and legacy free-text event fields.
- Remediated: `direct_execute_available` could overpromise for legacy approvals with invalid binding digests, and direct `/cli/approvals/{approval_id}/execute` could execute them without the same digest check.
- Remediated: a launch-failure approval regression test selected the first persisted run/approval instead of the records for the approval under test.

Residual risks:
- Secret redaction is still heuristic; arbitrary unlabeled secrets, private key material, and novel secret field names remain best handled by avoiding raw secret writes and restricting log access.
- Current auth is route/capability-level, not per-approval separation-of-duties.
- Interactive approval UI remains scheduled for BL-010/Sprint 16 and should use the safe review contract rather than raw approval records.

Role boundary:
- Developer-owned files: `src/dgentic/api/routes.py`, `src/dgentic/cli_runtime.py`, `src/dgentic/events.py`, and `src/dgentic/redaction.py`.
- QA-owned files: `tests/test_api.py` and `tests/test_cli_runtime.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/how-to/developer-setup.md`, `docs/how-to/using-dgentic.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs under `docs/agentic-workflows/` were followed but not modified.

Workspace hygiene:
- `main` is up to date with `origin/main` at the start of this slice.
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Next:
- Continue Sprint 9 with broader Windows/POSIX shell semantics validation, or split true restart process recovery and production multi-worker lease semantics into a later persistence/DevOps hardening sprint.

### Sprint 9 BL-002d CLI Supervision Metadata And Lifecycle Accuracy

Status: completed for the scoped slice; final Reviewer, Security, and DevOps gates approved with residual risks recorded.

Current story:
- BL-002: CLI Streaming And Restart-Resilient Supervision.

Checklist:
- Completed: PM kept the work in Full Sprint mode because CLI runtime supervision, cancellation, approvals, and command policy boundaries are security-sensitive.
- Completed: Developer updated production source only for asynchronous CLI launch intent persistence, supervisor metadata, timeout metadata, starting and failed lifecycle states, failed-launch persistence, async nonzero failed status, stale reason reporting, cancellation race guards, POSIX cancellation escalation, raw shell-wrapper tail preservation, and monotonic output chunk sequencing after retention trimming.
- Completed: QA updated tests only for supervision metadata, failed launch persistence and redaction, approval binding on failed launch, timeout/output state, async nonzero failure status, orphan cancellation, stale reconciliation reasons, output cursor retention, starting/cancel race behavior, terminal finalization race behavior, SIGTERM-ignoring cancellation, quoted-space path operands, and API timeout/orphan cancellation behavior.
- Completed: Reviewer, Security, and DevOps blocker sets were routed back through explicit Developer and QA lanes until all in-scope blockers were cleared.
- Completed: PM updated README, architecture, backlog, and progress docs without modifying `docs/agentic-workflows`.

Feature tracking:
- Implemented in this slice: async CLI runs persist a `starting` launch-intent record before process spawn; successful spawns transition to `running` with `supervisor_id`, `supervisor_pid`, `timeout_at`, `last_heartbeat_at`, and `status_reason`; failed launches persist as `failed`; async nonzero exits finalize as `failed`; timeouts, cancellations, stale runs, and failed runs carry auditable status reasons; orphaned prior-supervisor runs can be marked stale on reconciliation or cancellation; same-supervisor starting/running finalization races fail closed instead of being incorrectly marked stale; output chunk sequence cursors remain monotonic after retention trimming.
- Security-adjacent hardening handled during this slice: launch-failure `status_reason` is sanitized before persistence/log metadata, POSIX active cancellation escalates from `SIGTERM` to `SIGKILL`, and quoted path operands with spaces remain inspectable inside common shell wrappers before read-only rootDir boundary checks.
- Still out of scope after this slice: true process adoption or safe termination after backend restart, production multi-worker lease semantics, corrupt JSON quarantine/repair tooling, OS sandboxing, and complete Windows/POSIX shell semantic parity.

Validation:
- Focused blocker regressions passed.
- Targeted post-remediation gate: `python -m pytest -q tests/test_command_policy.py tests/test_cli_runtime.py tests/test_api.py` passed with 288 tests.
- Final full gate: `python -m pytest -q` passed with 373 tests.
- `python -m ruff check .` passed.
- `python -m ruff format --check .` passed.
- `git diff --check` passed.

Review and security findings handled:
- Remediated: cancelling a `starting` same-supervisor run could mark it stale, then launch completion could overwrite the terminal stale state.
- Remediated: cancelling with a stale pre-registration run snapshot could overwrite registered process metadata.
- Remediated: cancelling with no active process could stale an already-finalized run snapshot.
- Remediated: quoted path operands with spaces could bypass read-only rootDir checks, including inside `cmd`, PowerShell, and `pwsh` wrappers.
- Remediated: POSIX cancellation could report success before a SIGTERM-ignoring process was dead.
- Remediated: failed launch `status_reason` could persist unredacted exception text.

Residual risks:
- Restart recovery remains stale-only; prior-supervisor OS processes are not adopted or killed by stored PID.
- Production multi-worker process ownership needs a real lease/heartbeat strategy before scale-out deployment.
- CLI execution is still policy/cwd-bound rather than sandboxed, so path TOCTOU races remain possible.
- Corrupt JSON state can still require manual repair; quarantine/repair tooling remains a production persistence follow-up.
- Workspace hygiene update: stale earlier note about an untracked empty `QA` file is no longer current; the remaining untracked files are `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Role boundary:
- Developer-owned files: `src/dgentic/cli_runtime.py` and `src/dgentic/command_policy.py`.
- QA-owned files: `tests/test_api.py`, `tests/test_cli_runtime.py`, and `tests/test_command_policy.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs were not modified in this BL-002d closeout pass.

Next:
- Keep Sprint 9 open for the remaining broader Windows/POSIX shell semantics validation and approval review UI contracts, or split production-grade process recovery and multi-worker supervision into a later persistence/DevOps hardening sprint.

### PM Project Current-State Assessment

Status: completed; PM assessed the docs, codebase, architecture, test health, and security posture, then recorded follow-up backlog detail for newly confirmed delivery risks.

Checklist:
- Completed: Reviewed the core project docs in `README.md`, `docs/DGentic-goal.md`, `docs/README.md`, `docs/planning/`, `docs/architecture/`, and `docs/progress/`.
- Completed: Compared the documented current state against the backend source tree under `src/dgentic/` and test coverage under `tests/`.
- Completed: Used focused agent assessments for architecture, codebase readiness, and security posture.
- Completed: Ran validation in a temporary local environment because the current shell did not have `uv` or the dev modules preinstalled.
- Completed: Updated the refined backlog with explicit cross-platform CLI, tool-execution, provider-network, and audit-identity follow-up items.

Current-state summary:
- DGentic is a real backend-first FastAPI MVP with strong CLI policy work, route capability auth, local provider integration, generated-tool/runtime contracts, metadata/tool registry persistence slices, and well-maintained planning/progress documentation.
- The codebase is healthy enough to keep building on, but it is still firmly in MVP-hardening mode rather than production-ready mode.
- The largest architecture gaps remain durable orchestration, unified persistence, external provider productionization, production memory lifecycle, UI surfaces, deployment/CI/CD, and operational observability.

Validation:
- Temporary environment setup under `/tmp/dgentic-assess` completed successfully.
- `python -m pytest -q` in that temporary environment passed 291 tests and failed 2 tests.
- `python -m ruff check .` passed.
- `python -m ruff format --check .` passed.
- The two failing tests are `tests/test_api.py` cases that expect `cmd /c ...` to execute successfully on this POSIX host, which confirms a current Sprint 9 cross-platform CLI execution gap rather than a broad backend regression.

Security findings recorded:
- CLI execution is currently `cwd`-bound, but file-path arguments are not yet constrained to `rootDir`, so the real host boundary is weaker than the docs imply.
- Generated-tool execution still behaves more like guarded local Python execution than a hardened sandbox and still relies on a caller-supplied `approved` boolean.
- Provider requests still need outbound network/domain policy, stricter endpoint control, and production-safe response/logging boundaries.
- Approval and audit identity remain partially caller-supplied in some request flows instead of fully principal-bound.

Role boundary:
- PM-only planning/progress update. No production source or QA-owned tests were modified.

Next:
- Keep Sprint 9 focused on the CLI/runtime hardening gap that is already in flight.
- After Sprint 9, prioritize persistence/audit unification plus tool/provider security hardening before expanding into UI or broader autonomous execution.

### PM Workflow Tuning: Faster Dev-QA Pre-Review Loop

Status: completed; workflow guidance now prefers a paired Dev-QA lane before review when source and tests both need updates.

Checklist:
- Completed: Updated autonomous-mode instructions to prefer an explicit same-run `Dev -> QA` lane before review.
- Completed: Added governance guidance for pre-review formatting, local validation evidence, and bundled Dev-QA handoffs.
- Completed: Updated Fast Path and Sprint Lifecycle workflow docs so the faster Dev-QA loop applies across lightweight and standard workflows.
- Completed: Updated Developer and QA role docs with review-readiness and validation-evidence expectations.

Why this change:
- Review turnaround was slowed by avoidable pre-review churn between Developer, QA, and Reviewer.
- Most of that churn belongs in the Dev-QA lane, especially formatting, targeted validation, and coverage clarification.
- Making the first Reviewer pass wait for a review-ready Dev-QA bundle should reduce avoidable review failures without weakening role boundaries.

Role boundary:
- PM-only process documentation update. No production source or QA-owned test files were modified.

Validation:
- Documentation consistency review completed across `docs/agentic-workflows/Autonomous-mode.md`, `docs/agentic-workflows/governance/coordination-and-learning.md`, `docs/agentic-workflows/workflows/fast-path.md`, `docs/agentic-workflows/workflows/sprint-lifecycle.md`, `docs/agentic-workflows/roles/developer.md`, and `docs/agentic-workflows/roles/qa.md`.

Next:
- Use the paired Dev-QA lane by default when a story needs both source and test changes and the selected workflow mode still fits.

### Sprint 9 CLI Runtime Boundary Hardening Slice

Status: completed for the current slice; final Reviewer and Security gates approved with residual risks recorded.

Current stories:
- BL-002: CLI Streaming And Restart-Resilient Supervision.
- BL-003: CLI Parsing And Approval Review UX Contracts.

Checklist:
- Completed: PM kept the work in Full Sprint mode because CLI command execution and rootDir boundaries are security-sensitive.
- Completed: Developer updated production source only for POSIX `cmd /c` and `cmd.exe /c` execution parity, shared inner-shell parsing, cwd-aware policy evaluation, approval creation policy cwd binding, read-only path operand rootDir checks, shell expansion checks, tilde path checks, shell assignment prefix handling, Bash quoted path handling, brace expansion handling, glob/symlink checks, Windows env expansion checks, Windows caret escape checks, Windows drive-relative path checks, Windows absolute/backslash path handling, Windows absolute-path traversal normalization, and Windows slash-switch context handling.
- Completed: QA updated tests only for POSIX wrapper execution, async wrapper execution, API blocking of out-of-root read-only paths, cwd-relative policy behavior, symlink escapes, shell-variable and parameter-expansion paths, tilde-user paths, shell assignment prefixes, Bash quoted paths, brace expansion, glob/symlink escapes, Windows/delayed-expansion paths, Windows env vars with parentheses, CMD caret escapes, Windows drive-relative paths, Windows absolute-path traversal, POSIX slash-switch context, configured-rule precedence, and cwd-aware approval creation.
- Completed: Reviewer and Security blocker set was routed back through explicit Developer and QA role lanes.
- Completed: PM updated README, architecture, backlog, and progress docs for the completed implementation slice without modifying `docs/agentic-workflows`.
- Completed: Final Reviewer approved the remediated workspace.
- Completed: Final Security spot-check approved the Windows absolute-path traversal fix.

Feature tracking:
- Implemented in this slice: policy-approved `cmd /c` and `cmd.exe /c` wrappers execute on POSIX through `sh -c`; command policy evaluation uses resolved cwd; approval creation evaluates policy with the requested cwd; built-in read-only commands block operands resolving or shell-expanding outside `rootDir`; shell assignments, Bash path quotes, brace expansion, globs, symlink escapes, Windows env expansion, CMD caret escapes, Windows drive-relative paths, Windows absolute/backslash path forms, and Windows absolute paths with `..` segments are handled conservatively; Windows slash switches are only allowed in a Windows command context.
- Still partially implemented after this slice: full restart-resilient process supervision beyond stale marking, production multi-worker process ownership, broader Windows/POSIX shell semantics beyond the current hardened matrix, interactive approval UI contracts, and automated CI/pre-commit enforcement.

Validation:
- Focused post-remediation gate: `python -m pytest -q tests/test_command_policy.py tests/test_cli_runtime.py tests/test_api.py` passed with 265 tests.
- Full post-remediation gate: `python -m pytest -q` passed with 350 tests when run with the validation environment on `PATH`.
- `python -m ruff check .` passed.
- `python -m ruff format --check .` passed.
- `git diff --check` passed.
- DevOps note: direct venv Python without the venv `bin` directory on `PATH` can fail tests that intentionally execute bare `python`; use `uv run` or an activated/known venv PATH for official validation.

Review and security findings handled:
- Remediated: shell parameter expansions such as `${HOME:-/tmp}`, `${VAR#prefix}`, and `${!VAR}` bypassed read-only path rootDir checks.
- Remediated: tilde-user paths such as `~root/.ssh/config` bypassed read-only path rootDir checks.
- Remediated: approval creation evaluated command policy before resolving/passing request cwd.
- Remediated: Windows slash switches such as `dir /b` and `type /?` were treated as root paths.
- Remediated: shell assignment prefixes such as `HOME=/tmp cat ...` bypassed the read-only path operand checker.
- Remediated: Bash `$'...'` path words and brace-expanded path operands could synthesize outside-root paths.
- Remediated: delayed Windows expansion modifiers, Windows variables with parentheses, and CMD caret escapes could hide outside-root paths or wildcard operands.
- Remediated: Windows drive-relative paths such as `C:..\secret.txt` were previously treated as safe literals.
- Remediated: Windows absolute paths containing traversal segments such as `C:\workspace\..\secret.txt` could pass raw-prefix checks before path normalization.
- Remediated: shell glob operands could expand to symlinks that resolve outside `rootDir`.

Residual risks:
- Custom configured safe rules remain trusted-policy surface and should stay admin-controlled.
- A normal filesystem time-of-check/time-of-use race remains possible if workspace paths are swapped between policy evaluation and subprocess start.
- POSIX `cmd /c` translation is simple wrapper parity, not a full Windows CMD emulator.
- Formatting is manually/process enforced through Ruff gates; repository-level CI/pre-commit enforcement remains future DevOps work.
- Workspace hygiene update: stale earlier note about an untracked empty `QA` file is no longer current; the remaining untracked files are `docs/DGentic-goal.md.bak` and `docs/DGentic-goal.md.bak2`.

Role boundary:
- Developer-owned files: `src/dgentic/cli_runtime.py`, `src/dgentic/command_policy.py`, and `src/dgentic/schemas.py`.
- QA-owned files: `tests/test_api.py`, `tests/test_cli_runtime.py`, and `tests/test_command_policy.py`.
- PM-owned files: `README.md`, `docs/architecture/repository-architecture.md`, `docs/planning/backlog-needs-to-be-done.md`, and this progress log.
- Workflow docs were not modified in this closeout pass.

Next:
- Leave Sprint 9 open only for the remaining restart-resilient supervision, broader shell semantics, Windows CI matrix confirmation, and approval UI contract work.

## 2026-05-08

### Sprint 9 Next Slice Planning: BL-003a

Status: in progress; explicit role handoff started.

Selected slice:
- BL-003a: Windows/POSIX command parsing matrix and approval review contract refinement.

Rationale:
- Sprint 9 already completed output polling, stale-run reconciliation, and bound approval IDs.
- Cross-platform parser validation and approval review metadata are narrower and lower-risk than full restart-resilient process recovery.
- This slice improves operator trust before UI approval surfaces and production multi-worker supervision work.

Scope:
- Expand command policy parsing validation across common Windows and POSIX commands, shell wrappers, quoting patterns, and argument matching.
- Clarify and, if needed, extend safe approval review fields for UI consumers.
- Preserve no-secret persistence for environment values.
- Keep source, tests, and PM docs separated by role ownership.

Role handoff checklist:
- Completed: Architect confirmed parser/review-contract scope and documented the BL-003a architecture handoff in `docs/architecture/repository-architecture.md`.
- Completed: Developer implemented production-source changes only for parser normalization and additive redacted approval `review_command`.
- Completed: QA added parser matrix and approval review behavior tests only, then verified focused CLI policy/runtime/API coverage.
- In progress: Reviewer and Security perform read-only review of BL-003a source/test changes.
- Pending: DevOps runs full quality gates.
- Pending: PM updates backlog/progress/status docs after verification.

Out of scope for this slice:
- Full restart-resilient process recovery beyond stale marking.
- Production multi-worker process supervision.
- Interactive approval UI implementation.

Role boundary:
- PM/Architect documentation-only work so far. Developer source-only work is delegated separately.

Autonomous mode coordination:
- Spawned Developer Agent Mendel for source-only ownership of `src/dgentic/command_policy.py`, `src/dgentic/schemas.py`, and `src/dgentic/cli_runtime.py`.
- Developer completed source-only work and handed off expected parser/review coverage to QA without editing tests.
- Spawned QA Agent Kierkegaard for tests-only ownership under `tests/`.
- QA completed focused verification: `python -m pytest -q tests/test_command_policy.py tests/test_cli_runtime.py` passed with 48 tests, and the targeted CLI approval/API subset passed with 4 tests and 22 deselected.
- Spawned Reviewer Agent Pasteur and Security Agent Raman for read-only BL-003a review.
- Reviewer and Security found blocking issues in shell-wrapper inspection, approval ID claim timing, environment value binding, and raw approval command exposure.
- Developer and QA remediated the first blocker set, then full DevOps gates passed with 166 tests plus ruff check and format check.
- Follow-up Reviewer Agent Chandrasekhar found two remaining P1 blockers: quoted/multi-word secret redaction leakage and shell command-substitution bypasses inside wrappers.
- Follow-up Security Agent Nash also found that custom persisted policy rules were not applied to inner shell segments and flag-style secrets could still appear in approval review text.
- Developer and QA remediated command substitution, inner configured rules, and flag/quoted redaction; full DevOps gates then passed with 171 tests plus ruff check and format check.
- Final Reviewer Agent Lorentz found remaining edge blockers: nested command substitutions, additional flag-secret spellings, and configured `autopilot_safe` inner shell rules being ignored.
- Developer and QA remediated nested substitutions, additional flag-secret spellings, inner safe rules, and command result/run redaction; full DevOps gates then passed with 175 tests plus ruff check and format check.
- Final Security Agent Hegel found one remaining P1 redaction blocker for unquoted POSIX escaped-whitespace secret values such as `--token abc\ 123`.
- Developer and QA remediated escaped-whitespace redaction; full DevOps gates then passed with 175 tests plus ruff check and format check.
- Final Security Agent Confucius found no remaining issues in the escaped-whitespace remediation.
- Final Reviewer Agent Volta found remaining blockers: broad configured `autopilot_safe` rules can still preempt shell-wrapper inspection, substitution-bearing flag values can leak suffixes in redacted approval text, and escaped nested backtick substitutions downgrade blocked inner commands to generic approval.
- Current optimized workflow mode: Full Sprint because remaining BL-003a work touches security-sensitive command policy and approval redaction behavior.
- Developer and QA remediated broad safe-rule preemption, substitution-bearing secret values, and escaped nested backticks; isolated full DevOps gates then passed with 177 tests plus ruff check and format check.
- Final Reviewer Agent Laplace found no remaining issues.
- Final Security Agent Descartes found two remaining P1 blockers: substitution secret values containing shell separators can still leak suffixes, and broad configured `approval_required` rules can still preempt blocked inner shell commands.
- Current handoff: Developer owns substitution-value redaction and shell-wrapper rule-precedence source fixes; QA owns regression coverage after source remediation.
- Developer and QA remediated substitution secret values with shell separators and outer shell-wrapper configured rule precedence; isolated full DevOps gates then passed with 178 tests plus ruff check and format check.
- Final Reviewer Agent Archimedes found one remaining P1 blocker where a configured safe or approval rule matching the blocked inner segment itself can downgrade built-in blocked commands, plus a P2 gap for direct policy-log redaction coverage.
- Current handoff: Developer owns built-in blocked inner command precedence; QA owns configured-rule override and policy-log redaction regressions.
- Final Security Agent Godel independently confirmed the configured non-blocking inner-rule downgrade and also found that configured blocked rules targeting the outer shell wrapper can be skipped when the inspected inner command is safe.
- Current handoff: Developer owns final shell-wrapper configured-rule precedence fixes; QA owns inner/outer precedence and policy-log redaction regressions.
- Developer and QA remediated built-in blocked inner command precedence, configured blocked outer wrapper enforcement, and direct policy-log redaction coverage; isolated full DevOps gates then passed with 182 tests plus ruff check and format check.
- Final Reviewer Agent Ampere found no remaining issues.
- Final Security Agent Heisenberg found two additional shell parser bypasses: Bash process substitutions such as `<(rm -rf important)` can hide blocked commands, and grouped shell blocks such as `{ rm -rf important; }` can downgrade blocked commands to generic approval.
- Current handoff: Developer owns process-substitution and grouped-block parser source fixes; QA owns focused regressions.
- Developer and QA remediated direct process substitutions and grouped blocks; isolated full DevOps gates then passed with 187 tests plus ruff check and format check.
- Final Reviewer Agent Locke found PowerShell dot-sourced script blocks and nested Bash process substitutions could still hide blocked commands.
- Final Security Agent Kant confirmed nested process substitutions and also found shell keyword/script-block forms plus plain redirection could be classified too safely.
- Current handoff: Developer owns conservative complex shell construct detection; QA owns regressions for dot-sourced blocks, nested process substitution, keyword script blocks, CMD `if`, and redirection.
- Developer and QA remediated dot-sourced/script-block forms, nested process substitution, shell keyword blocks, and spaced redirection; isolated full DevOps gates then passed with 195 tests plus ruff check and format check.
- Final Security Agent Sartre found attached redirection syntax such as `echo owned>file` and POSIX source/dot-source execution still classified too safely.
- Final Reviewer Agent Turing confirmed attached redirection and also found the conservative script-token scan can false-positive blocked command names used as data, such as `echo rm`.
- Current handoff: Developer owns attached redirection, POSIX source/dot-source approval, and script-token false-positive source fixes; QA owns focused regressions.
- Developer and QA remediated attached redirection, POSIX source/dot-source approval, and data-token false positives; isolated full DevOps gates then passed with 203 tests plus ruff check and format check.
- Final Reviewer Agent Nietzsche found POSIX source execution can still be routed through shell builtins such as `builtin source` or `command .`.
- Final Security Agent Galileo found POSIX command-prefix builtins such as `command`, `exec`, and `time` can hide blocked inner commands.
- Current handoff: Developer owns command-prefix/source wrapper handling; QA owns focused regressions.
- PM adopted the updated optimized `docs/agentic-workflows` flow: BL-003a remains in Full Sprint mode because command policy and approval handling are security-sensitive, with explicit role blocks and strict write ownership.
- DevOps smoke validation with an isolated data directory confirmed current source classifies `command rm`, `exec rm`, and `time rm` as blocked, `builtin source` and `command .` as approval-required, and `echo rm` as safe; current handoff is QA-owned regression coverage followed by focused/full gates.

---

### PM Backlog Extension For Not-Yet-Implemented Items

Status: completed; PM mapped all current root README not-yet-implemented items into planned backlog and sprint coverage.

Checklist:
- Completed: Reviewed the root README not-yet-implemented list.
- Completed: Confirmed generic external AI provider adapter productionization is covered by BL-006 / Sprint 12; named provider-specific adapter expansion is now tracked separately under BL-013 / Sprint 19.
- Completed: Confirmed full autonomous backlog management and sprint execution are covered by BL-008 / Sprint 14.
- Completed: Added BL-009 for production identity, secret management, encrypted credentials, token rotation, and network/domain guardrails.
- Completed: Added BL-010 for cross-platform web UI, dashboard, settings, and interactive approval UI.
- Completed: Added BL-011 for VS Code extension and dedicated CLI client.
- Completed: Added BL-012 for production deployment, CI/CD, observability, monitoring, alerting, and rollback.
- Completed: Extended the proposed sprint sequence through Sprint 19.
- Completed: Updated the Agile task plan with the extended sprint sequence and dedicated CLI client story.
- Completed: Updated the root README not-yet-implemented list with planned sprint coverage.

Sprint coverage decisions:
- Sprint 12: Provider productionization with a generic OpenAI-compatible external adapter.
- Sprint 19: Provider-specific external adapter expansion after a concrete provider target is selected.
- Sprint 14: Full autonomous backlog management and sprint execution.
- Sprint 15: Production identity, secrets, and network guardrails.
- Sprint 16: Cross-platform UI, dashboard, settings, and interactive approval experience.
- Sprint 17: VS Code extension and dedicated CLI client.
- Sprint 18: Deployment, CI/CD, observability, alerting, and rollback.

Role boundary:
- PM-only planning update. No production source or QA test changes were made for this planning step.

Verification:
- Documentation-only planning change; runtime tests not required.

---

### Sprint 9 Bound Approval ID Slice

Status: completed; BL-002b bound approval IDs implemented and verified.

Current stories:
- BL-002: CLI streaming and restart-resilient supervision.
- BL-003: CLI parsing and approval review UX contracts.

Checklist:
- Completed: Dev added `approval_id` to command execution requests.
- Completed: Dev bound approval records to command digest, cwd, timeout, requester, agent/task context, environment keys, policy metadata, and expiry.
- Completed: Dev limited broad `approved: true` execution to development/test mode while requiring approved single-use approval IDs outside development/test mode.
- Completed: Dev consumed approvals after synchronous execution or asynchronous run start and preserved no-secret environment value storage.
- Completed: QA added focused service/API coverage for production-mode approval ID enforcement, single-use execution, environment-key binding, mismatch rejection, and expiry behavior.
- Completed: PM updated README, setup/usage, architecture, Agile plan, backlog, and progress docs.
- Completed: Run full quality gates.

Feature tracking:
- Implemented before slice: CLI approval queue, approve/deny/execute endpoints, approval review metadata, context/environment-key audit fields, async run polling, output chunks, stale reconciliation, and development/test boolean approval bypass.
- Implemented in this slice: production/staging-style bound approval IDs, approval digest/expiry metadata, single-use approval consumption, direct `/cli/execute` and `/cli/runs` approval ID support, and environment-key-only approval binding.
- Still partially implemented after this slice: full restart-resilient process supervision beyond stale marking, broader Windows/POSIX parsing validation, explicit approval review UI contracts, and richer reviewer decision metadata.

Focused verification:
- `uv --cache-dir .uv-cache run pytest tests\test_cli_runtime.py tests\test_api.py -q` passed with 43 tests.

Full verification:
- `uv --cache-dir .uv-cache run pytest -q` passed with 133 tests.
- `uv --cache-dir .uv-cache run ruff check .` passed.
- `uv --cache-dir .uv-cache run ruff format --check .` passed.

Process correction:
- Recorded: This slice was executed in one combined pass that modified production source, QA-owned tests, and PM-owned documentation without explicit role handoffs.
- Impact: Technical verification passed, but the execution flow did not strictly follow `docs/agentic-workflows/governance/role-boundaries.md`.
- Corrective action: Future Sprint 9 work must use explicit role transitions. Developer work modifies production source only, QA work modifies tests only, and PM work modifies planning/progress/status documentation only.
- PM note: This correction is documentation-only and does not modify source or tests.

---

### Sprint 9 CLI Runtime Hardening Kickoff

Status: in progress; BL-002a output polling and stale reconciliation slice implemented and under verification.

Current stories:
- BL-002: CLI streaming and restart-resilient supervision.
- BL-003: CLI parsing and approval review UX contracts.

Sprint goal:
- Make long-running CLI execution observable and safer across backend restarts while preparing approval records for UI review consumers.

Checklist:
- Completed: PM initiated Sprint 9 from the refined production completion backlog.
- Completed: Architect selected BL-002a as the first slice because command observability and stale reconciliation are prerequisites for stronger supervision.
- Completed: Dev implemented source-only chunked async CLI output polling.
- Completed: Dev implemented source-only stale-running reconciliation for orphaned persisted runs.
- Completed: Dev added source-only matched policy metadata on approval records.
- Completed: QA added tests only for output chunk polling, redaction, stale reconciliation, approval metadata, and API output polling.
- Completed: PM updated README, setup/usage, architecture, backlog/progress docs, and current feature status.
- Completed: Run full quality gates.
- Completed: Commit and push Sprint 9 initiation slice.

Feature tracking:
- Implemented before sprint: CLI approvals, policy rules, status polling, cancellation, context-aware policy, environment controls, and run persistence.
- Implemented in this slice: redacted output chunks, output sequence polling, stale-running reconciliation, and matched policy review metadata.
- Still partially implemented after this slice: bound approval ID enforcement, full restart-resilient process supervision, broader Windows/POSIX parsing validation, and approval review UI contracts.

Verification:
- `uv run pytest tests\test_cli_runtime.py` passed with 14 tests.
- `uv run pytest tests\test_api.py -q` passed with 24 tests.
- `uv run pytest tests\test_cli_runtime.py tests\test_api.py -q` passed with 38 tests.
- `uv run ruff check src\dgentic\cli_runtime.py src\dgentic\api\routes.py tests\test_cli_runtime.py tests\test_api.py` passed.
- `uv run pytest` passed with 128 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Role boundary:
- Dev owns production source only.
- QA owns tests only.
- PM owns sprint checklist, backlog/progress, README, and documentation updates.

---

### Sprint 8 Production Security And Persistence Foundation

Status: completed; Sprint 8 is closed with follow-up hardening moved to the refined backlog.

Current stories:
- BL-000: Authentication, authorization, and security baseline.
- BL-001: Production persistence foundation.

Sprint goal:
- Add the first production-mode security gate for sensitive backend routes and the persistence foundation needed for migration-managed state while preserving explicit local development usability.

Checklist:
- Completed: PM initiated Sprint 8 from the refined production completion backlog.
- Completed: Architect/Security, QA, and ReleaseManager refinement agents were assembled for implementation guidance.
- Completed: Dev implemented source-only production-mode auth and capability enforcement.
- Completed: QA added tests only for public routes, missing token, invalid token, missing capability, allowed capability, admin access, settings helpers, and no token leakage.
- Completed: Dev implemented source-only migration-managed persistence baseline.
- Completed: QA added tests only for database URL resolution, migration ledger creation/idempotence, reset behavior, SQLite file creation, and restart persistence.
- Completed: Dev implemented source-only auth startup fail-closed validation when auth is enabled without usable tokens.
- Completed: QA added tests only for auth configuration validation and production create-app fail-closed behavior.
- Completed: Dev implemented source-only file-backed SQLite backup/restore helpers.
- Completed: QA added tests only for SQLite backup/restore round trip and non-SQLite backup rejection.
- Completed: PM updated README, developer setup, usage, architecture, backlog/progress docs, and current feature status for BL-001a.
- Completed: Commit and push BL-000 auth baseline slice.
- Completed: Commit and push BL-001a persistence baseline slice.
- Completed: PM updated README, developer setup, usage, architecture, backlog/progress docs, and current feature status for Sprint 8 closeout.

Feature tracking:
- Implemented before sprint: policy-enforced CLI/filesystem/tool/provider/memory route contracts, but no production auth gate.
- Partially implemented before sprint: production security baseline and production persistence existed only as backlog/refinement documentation plus SQLite-compatible service prototypes.
- Implemented by Sprint 8 close: route-level authentication, capability authorization, startup fail-closed token validation, database URL override, migration ledger baseline, restart persistence smoke coverage, and local SQLite backup/restore smoke helpers.
- Still partially implemented after Sprint 8: actor-bound audit propagation, persisted identity, token lifecycle, repository migration strategy, production PostgreSQL packaging, expanded migrations, concurrency/indexing hardening, and scheduled/remote backup automation.

Current slice boundary:
- In scope: dependency-light bearer token auth, configurable development bypass, route capability grouping, 401/403 behavior, startup token validation, migration baseline, local SQLite backup/restore smoke path, and documentation.
- Out of scope for this slice: full production database migrations, external secret manager integration, interactive user management, PostgreSQL backup automation, and frontend approval UX.

Completed in this slice:
- Added `src/dgentic/auth.py` with bearer-token parsing, route capability mapping, public path handling, admin/wildcard capability support, and 401/403 responses.
- Added production/staging auth-on default through `effective_auth_enabled`, while preserving development auth-off by default and explicit override support.
- Attached authenticated principals to `request.state.principal` for future audit actor propagation.
- Wired auth dependency at the FastAPI app level.
- Added startup fail-closed validation when auth is enabled without a usable `DGENTIC_AUTH_TOKENS` map.
- Added focused auth tests in `tests/test_auth.py`.
- Updated `.env.example`, README, developer setup, usage, architecture, backlog, and progress docs.

Completed in BL-001a:
- Added `DGENTIC_DATABASE_URL` and default SQLAlchemy URL resolution under `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db`.
- Updated the database session helper to build engines from the configured URL, use SQLite-specific connect args only for SQLite, create local SQLite parent directories, and expose `reset_database_state()`.
- Added `src/dgentic/migrations.py` with an idempotent `schema_migrations` ledger and baseline id `0001_metadata_tool_registry_baseline`.
- Added `list_applied_migrations()` for deterministic migration visibility.
- Added focused database tests in `tests/test_database.py`.
- Recorded the persistence decision that SQLite remains local/dev/test default while PostgreSQL remains the production target pending driver packaging and broader migration work.
- Added file-backed SQLite backup/restore helpers and focused smoke tests.

Follow-up backlog after Sprint 8 closure:
- BL-000 production hardening follow-ups: persisted identity, token hashing at rest, token rotation/expiry, full audit actor propagation, bound approval identities, and secret manager integration.
- BL-001 production persistence follow-ups: production PostgreSQL driver packaging, explicit ordered migrations beyond the baseline, critical JSON-store repository migration, auth/approval/audit persistence, concurrency/indexing hardening, scheduled/remote backup automation, retention cleanup, and failure rollback tests for future migrations.

Verification:
- `uv run pytest tests\test_auth.py` passed with 33 tests.
- `uv run pytest tests\test_database.py` passed with 12 tests.
- `uv run pytest` passed with 124 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Role boundary:
- Dev owns production source only.
- QA owns tests only.
- PM owns sprint checklist, backlog/progress, README, and documentation updates.

---

### Release Distribution 0.2.6

Status: DGentic 0.2.6 release distribution created and git tag prepared.

Completed:
- Bumped package, API, backend `__version__`, lockfile, and generated tool default version metadata to `0.2.6`.
- Added release notes in `docs/releases/0.2.6.md`.
- Built source distribution: `dist/dgentic-0.2.6.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.2.6-py3-none-any.whl`.
- Updated artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.2.6.zip`.
- Updated README, documentation index, release distribution guide, and progress log.

Verification:
- `uv run pytest` passed with 124 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.2.6-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8016.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.2.6.tar.gz`: `0199059AE52BE935BB8356BF3CB16D7D04F0FB263CDAD576FF2911CF9FC4AF9D`
- `dgentic-0.2.6-py3-none-any.whl`: `53B6A600E371E08190DCA3C30AC89D26FB131FA31CD98C55514A69146D80774C`
- `dgentic-0.2.6.zip`: `B57291B808FF5F6CA7C326B3F74D0D3D177B60C91222B51A8F4BD574552E1689`

Blocker:
- GitHub Release asset upload still requires GitHub CLI, a GitHub token, or the GitHub plugin in the execution environment.

---

## 2026-05-07

### Backlog Refinement For Production Feature Completion

Status: completed.

Current story:
- PM backlog refinement for completing all partially implemented feature groups.

Checklist:
- Completed: Captured partially implemented feature gaps from the root README.
- Completed: Collaborated with PO, Architect/Security, and QA/ReleaseManager perspectives.
- Completed: Created `docs/planning/backlog-needs-to-be-done.md` as the refined backlog source.
- Completed: Added production completion sprint sequencing to the Agile task plan.
- Completed: Updated root README and documentation index links.
- Completed: Tracked follow-up work for Sprint 8 and later production completion sprints.

Refined backlog items:
- BL-000: Authentication, authorization, and security baseline.
- BL-001: Production persistence foundation.
- BL-002: CLI streaming and restart-resilient supervision.
- BL-003: CLI parsing and approval review UX contracts.
- BL-004: Filesystem runtime completion.
- BL-005: Tool runtime safety and registry integration.
- BL-006: Provider system productionization.
- BL-007: Memory and retrieval production lifecycle.
- BL-008: Agent orchestration autonomy.

Sprint sequence:
- Sprint 8: Production Security And Persistence Foundation.
- Sprint 9: CLI Runtime Hardening.
- Sprint 10: Filesystem Runtime Completion.
- Sprint 11: Tool Runtime Safety And Registry Integration.
- Sprint 12: Provider Productionization.
- Sprint 13: Memory Production Lifecycle.
- Sprint 14: Autonomous Agent Orchestration.

Key refinement decisions:
- Auth/security and persistence must lead before expanding runtime power.
- CLI approval-required commands need bound approval IDs instead of broad boolean approval.
- Tool runtime sandboxing is a high-risk dependency before production autonomous reuse.
- Agent orchestration remains last because it depends on policy-enforced CLI, filesystem, tool, provider, memory, and persistence foundations.

Verification:
- Documentation-only planning change; runtime tests not required.

---

### Sprint 7 Semantic Retrieval Kickoff

Status: completed.

Current story:
- Story 6.2: Build Hybrid Retrieval.

Sprint goal:
- Make semantic and hybrid retrieval testable without requiring model downloads or heavyweight embedding dependencies.

Checklist:
- Completed: PM created sprint checklist and tracked implemented, partially implemented, and not-yet-implemented features.
- Completed: Dev added dependency-light embedding generation and retrieval fallback behavior.
- Completed: QA added service and API tests for semantic retrieval.
- Completed: PM updated README, Agile task plan, architecture/usage docs, and progress log.
- Completed: Ran quality gates.
- Completed: Commit and push completed sprint slice.

Feature tracking:
- Implemented before sprint: metadata-only retrieval route contracts and retrieval service scaffolding.
- Partially implemented before sprint: semantic/vector retrieval route contracts without tested dependency-light behavior.
- Not yet implemented before sprint: production vector backend, migrations, compression/summarization workflow, and performance validation.

Completed in this sprint slice:
- Added deterministic `dgentic-hash-embedding-v1` embeddings so semantic retrieval works without model downloads or heavyweight embedding dependencies.
- Added hybrid retrieval fallback scoring from metadata text when a stored vector embedding is not available.
- Added service tests for deterministic embeddings, hybrid metadata fallback, and stored vector retrieval.
- Added API regression coverage for `/api/v1/memory/retrieve/hybrid` using default hash embeddings.

Current feature status:
- Implemented: metadata index CRUD, metadata-only retrieval, dependency-light hybrid retrieval, stored vector retrieval, and focused service/API coverage.
- Partially implemented: production memory backend, optional external embedding model operations, migrations, compression/summarization, and performance validation.
- Not yet implemented: production vector backend selection/integration and long-term memory lifecycle policy.

Focused verification:
- `uv run pytest tests\test_retrieval_service.py tests\test_api.py` passed with 26 tests.

Full verification:
- `uv run pytest` passed with 79 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Sprint close decision:
- Story 6.2 is complete for the MVP dependency-light retrieval acceptance criteria.
- Follow-up backlog remains open for production vector backend selection, migrations, optional external embedding packaging, compression/summarization, and retrieval performance validation.

---

### Agent Checklist And Progress Governance Update

Status: agent workflow rules updated.

Checklist:
- Completed: Added mandatory checklist creation to autonomous coordination rules.
- Completed: Added mandatory progress update rule for work completion, blockers, handoffs, and follow-up backlog items.
- Completed: Updated PM responsibilities so sprint closure requires a completed checklist and updated progress documentation.
- Completed: Updated autonomous mode, sprint lifecycle, workflow index, and agent response template.
- Completed: Updated README current status to mention checklist/progress governance.

Verification:
- Documentation-only governance change; no runtime tests required.

---

### Sprint 6 Reconciliation And PM Handoff

Status: repository reconciled; PM has initiated the next active sprint around memory and tool registry foundations.

Assessment:
- New memory and tool registry files were present after the `v0.2.5` release but were not yet reconciled with the existing backend package layout.
- `src/dgentic/memory/` and `src/dgentic/tools/` packages collided with existing `src/dgentic/memory.py` and `src/dgentic/tools.py` modules.
- The root README had been replaced with inaccurate production-ready claims and had lost the required implemented/partial/not-yet-implemented status format.
- New dependency changes pulled in heavyweight embedding and database packages that were not required for the tested MVP slice.
- Initial `uv run pytest` failed during collection before reconciliation.

Completed:
- Reconciled `dgentic.memory` package exports so existing `add_memory` and `search_memory` API imports continue working.
- Reconciled `dgentic.tools` package exports so existing local tool generation, listing, governance, and runtime imports continue working.
- Added SQLAlchemy-backed metadata models and services for Story 6.1.
- Added SQLAlchemy-backed tool registry service for Story 7.1.
- Added SQLite-compatible local database session helper for MVP metadata-backed services.
- Added metadata and tool registry API routes under `/api/v1/memory/...` and `/api/v1/tools/registry...`.
- Added API tests for metadata CRUD and tool registry duplicate/usage/deprecation workflows.
- Kept semantic embedding generation optional so normal installs do not require downloading sentence-transformers or model dependencies.
- Reduced required new dependency scope to `sqlalchemy>=2.0.0,<3.0.0`.
- Restored README accuracy and preserved the required current status sections.
- Added focused tests for metadata CRUD/access tracking and tool registry duplicate/security/reliability behavior.
- Rebuilt `.venv` so the documented `uv run pytest` command sees the updated dependency set.

Verification:
- `uv run pytest` passed with 75 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

PM next sprint focus:
- Complete Story 6.2 by adding tested semantic retrieval behavior with a production dependency strategy.
- Decide whether the production database target is SQLite-first, PostgreSQL, or PostgreSQL plus pgvector before adding migrations.
- Continue Story 5.3 remaining CLI work after the metadata/tool registry foundation is stabilized.

Remaining risks:
- Semantic vector generation is currently optional and not covered by full integration tests.
- SQLAlchemy services are MVP-local and do not yet include production migrations or concurrency policy.
- Existing legacy module files `src/dgentic/memory.py` and `src/dgentic/tools.py` remain in the tree while package exports provide the active import path.

---

### Release Distribution 0.2.5

Status: DGentic 0.2.5 git release distribution created.

Completed:
- Bumped package, API, backend `__version__`, and generated tool default version metadata to `0.2.5`.
- Added release notes in `docs/releases/0.2.5.md`.
- Built source distribution: `dist/dgentic-0.2.5.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.2.5-py3-none-any.whl`.
- Updated artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.2.5.zip`.
- Updated README, documentation index, release distribution guide, and progress log.

Verification:
- `uv run pytest` passed with 46 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.2.5-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8015.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.2.5.tar.gz`: `852308F97DFE70944202FCD4CCF6F84717994B4BDA8E90D1F75E98B68D95613F`
- `dgentic-0.2.5-py3-none-any.whl`: `37906AC92927AF96016EB6CCAE2EABBC2FF91F9E151C7FD981F1B54D5F954B27`
- `dgentic-0.2.5.zip`: `13D4077924452B7348914E9C9E1217A9E513BD789C484CD622469E7BB98CB562`

Blocker:
- GitHub Release asset upload still requires GitHub CLI, a GitHub token, or the GitHub plugin in the execution environment.

---

### Release Distribution 0.2.4

Status: DGentic 0.2.4 release distribution created.

Completed:
- Bumped package, API, backend `__version__`, and generated tool default version metadata to `0.2.4`.
- Added release notes in `docs/releases/0.2.4.md`.
- Built source distribution: `dist/dgentic-0.2.4.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.2.4-py3-none-any.whl`.
- Updated artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.2.4.zip`.
- Updated README, documentation index, release distribution guide, and progress log.

Verification:
- `uv run pytest` passed with 46 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.2.4-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8014.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.2.4.tar.gz`: `0F6533ABA481F2412E33B7FA4EC3E5F3A445696A13BBB4411E52DEC0EA15B23B`
- `dgentic-0.2.4-py3-none-any.whl`: `74BB4BA3EA9FE1652016FB8755055B6FDF139F0A53B729AF634CD22843C06CCE`
- `dgentic-0.2.4.zip`: `136F48C5F3F1A7BC49A2322C3B5350B7C2FD5B9E982C9C27583C3755938B3788`

---

### CLI Context And Environment Control Pass

Status: Story 5.3 advanced with agent-aware CLI permissions and controlled command environments.

Completed:
- Added optional `agent_role`, `agent_id`, and `task_id` context to command policy checks and command execution requests.
- Added agent-role scoped CLI policy rules so configured allow, approval, or block rules can apply only to matching roles.
- Added controlled command environment construction with a small inherited baseline and explicit caller overrides.
- Blocked sensitive runtime environment overrides such as `PATH`, `PYTHONPATH`, `SYSTEMROOT`, `COMSPEC`, `PATHEXT`, `PYTHONHOME`, `HOME`, and `VIRTUAL_ENV`.
- Added environment-key auditing to command execution results, run history, approvals, and CLI event metadata without persisting environment values in approval records.
- Added API error handling for invalid command environment requests.
- Added focused runtime, policy, and API tests.
- Updated README, architecture documentation, usage guide, developer setup guide, Agile task plan, and progress log.

Verification:
- `uv run pytest tests/test_cli_runtime.py tests/test_command_policy.py tests/test_api.py -q` passed with 36 tests.

Remaining production work:
- Add streaming command output.
- Add restart-resilient process supervision and stale-running reconciliation.
- Broaden safe parsing validation across Windows and POSIX execution modes.
- Add a user-facing approval and environment review UX.

---

### PM Project Evaluation And Release Coordination

Status: project evaluated and release coordination completed for latest unreleased governance work.

Completed:
- Reviewed git state, latest tags, Agile task plan, and progress log.
- Confirmed latest release tag before this pass was `v0.2.2`.
- Identified unreleased work on `main`: autonomous agent role boundary governance from commit `8be444e`.
- Determined the governance update is release-worthy because it changes autonomous workflow operating rules.
- Coordinated Release Manager work for patch release `0.2.3`.

Findings:
- Story 5.3 remains partially open for streaming command output, restart-resilient process supervision, agent/context-aware CLI permissions, controlled command environments, and broader parsing validation.
- Role boundary enforcement is currently documentation-governed and still needs future backend policy enforcement.
- Existing backup files remain untracked and were not included: `docs/DGentic-goal.md.bak`, `docs/DGentic-goal.md.bak2`.

---

### Release Distribution 0.2.3

Status: DGentic 0.2.3 release distribution created.

Completed:
- Bumped package, API, and backend `__version__` metadata to `0.2.3`.
- Added release notes in `docs/releases/0.2.3.md`.
- Built source distribution: `dist/dgentic-0.2.3.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.2.3-py3-none-any.whl`.
- Updated artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.2.3.zip`.
- Updated README, documentation index, release distribution guide, and progress log.

Verification:
- `uv run pytest` passed with 40 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.2.3-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8013.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.2.3.tar.gz`: `56717B6D10B903FEC8E0E66A63A83C4EB753640174B2617E746C21DA634A0DAF`
- `dgentic-0.2.3-py3-none-any.whl`: `A920F86919B1531DC01F578066853D9F0C48B40E185D37DE2EFCB0F1999F09B5`
- `dgentic-0.2.3.zip`: `71508B1A9E97E819B326FF14DB2E19D0FAC8745E36910BF252DEAC4C8658C109`

---

### Agent Role Boundary Governance Update

Status: strict write ownership rules added for autonomous agents.

Completed:
- Added `docs/agentic-workflows/governance/role-boundaries.md`.
- Updated Developer Agent rules so Dev owns production implementation and must not create or modify tests.
- Updated QA Agent rules so QA owns tests and must not create or modify production source.
- Updated the sprint lifecycle so test creation and unit testing are QA-owned.
- Updated autonomous mode rules to require cross-role handoff when source or test changes belong to another role.
- Updated the agent response template with a required `Write Scope Used` section.
- Updated README, documentation index, and agentic workflow index.

Verification:
- Documentation-only change; no runtime tests required.

Remaining production work:
- Enforce these role boundaries in backend agent orchestration APIs when machine-readable workflow enforcement is implemented.

---

### Release Distribution 0.2.2

Status: DGentic 0.2.2 release distribution created.

Completed:
- Bumped package, API, and backend `__version__` metadata to `0.2.2`.
- Added release notes in `docs/releases/0.2.2.md`.
- Built source distribution: `dist/dgentic-0.2.2.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.2.2-py3-none-any.whl`.
- Updated artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.2.2.zip`.
- Updated release distribution documentation.

Verification:
- `uv run pytest` passed with 40 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.2.2-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8012.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.2.2.tar.gz`: `E9018A01F03A2E0E73782292D2FD276A7890E8B0AA87974CC6A55C1683CA0F2F`
- `dgentic-0.2.2-py3-none-any.whl`: `2216092DB89ED7A1A5830676DA9911CD3F9B57D74C20917C45C1D4687C556376`
- `dgentic-0.2.2.zip`: `80EEF95E4837BEFC0B77368800CF8EAEABE01EE5A4DB6395729D60B0BBC9EB8A`

---

### CLI Async Run And Cancellation Pass

Status: asynchronous CLI run polling and process-local cancellation are implemented for the backend MVP.

Completed:
- Added `CommandRunStatus` with `running`, `completed`, `timed_out`, and `cancelled` states.
- Added asynchronous CLI command start using persisted run records before process execution.
- Added command polling by run id.
- Added process-local cancellation for running commands.
- Added API endpoints: `POST /cli/runs`, `GET /cli/runs/{run_id}`, and `POST /cli/runs/{run_id}/cancel`.
- Hardened default command policy so common shell wrappers such as `cmd /c`, `sh -c`, and PowerShell command invocations are inspected for blocked inner commands.
- Preserved existing synchronous `/cli/execute` behavior.
- Added tests for asynchronous completion, polling, cancellation, API cancellation, and shell-wrapped blocked command detection.
- Updated README, architecture documentation, usage guide, developer setup guide, Agile task plan, and progress log.

Verification:
- `uv run pytest tests/test_cli_runtime.py tests/test_command_policy.py tests/test_api.py -q` passed with 30 tests.

Remaining production work:
- Add streaming command output.
- Add restart-resilient process supervision and stale-running reconciliation.
- Add agent/context-aware CLI permissions.
- Add controlled and auditable command environment variables.
- Broaden safe parsing validation across Windows and POSIX execution modes.

---

### Release Distribution 0.2.1

Status: DGentic 0.2.1 release distribution created.

Completed:
- Bumped package, API, and backend `__version__` metadata to `0.2.1`.
- Added release notes in `docs/releases/0.2.1.md`.
- Built source distribution: `dist/dgentic-0.2.1.tar.gz`.
- Built wheel distribution: `dist/dgentic-0.2.1-py3-none-any.whl`.
- Updated artifact checksums in `dist/SHA256SUMS.txt`.
- Created release bundle: `releases/dgentic-0.2.1.zip`.
- Updated release distribution documentation.

Verification:
- `uv run pytest` passed with 36 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv build` created both wheel and source distribution.
- Clean virtual environment install from `dist/dgentic-0.2.1-py3-none-any.whl` succeeded.
- Packaged `dgentic-server` command started successfully on port 8011.
- Packaged `/health` endpoint returned `status: ok`.

Artifact hashes:
- `dgentic-0.2.1.tar.gz`: `CB58CC46824F96D25470315C5F993395F160ACB539943A0FBD8FAA3E6B06C092`
- `dgentic-0.2.1-py3-none-any.whl`: `A11B3E418D9D6ECC513089E5934D433648DD1FF7D88EA464DC48FB1ACA53D33B`
- `dgentic-0.2.1.zip`: `16183EEC508197244A52E0A63591AB9CC249E10FFC164AFE750C93235113D200`

---

### CLI Command Policy Configuration Pass

Status: configurable command policy storage and argument-aware matching are implemented for the backend MVP.

Completed:
- Added persisted CLI command policy rule schemas with executable, exact-command, contains, and argument-substring match types.
- Added rule priority, enabled/disabled state, permission mode, reason, and matched-rule metadata on command policy decisions.
- Added persisted local state collection: `cli-command-policy-rules.json`.
- Added `POST /cli/policy/rules`, `GET /cli/policy/rules`, and `PATCH /cli/policy/rules/{rule_id}`.
- Integrated configured rules into guarded command checks, CLI approvals, and CLI execution while preserving built-in defaults.
- Added tests for default override behavior, argument-aware blocking, disabling rules, CLI runtime enforcement, and API rule persistence.
- Updated README, architecture documentation, usage guide, developer setup guide, Agile task plan, and progress log.

Verification:
- `uv run pytest tests/test_command_policy.py tests/test_api.py -q` passed with 20 tests.

Remaining production work:
- Add streaming command output and restart-resilient process supervision.
- Add agent/context-aware CLI permissions.
- Add controlled and auditable command environment variables.
- Broaden safe parsing validation across Windows and POSIX execution modes.

---

### Agentic Workflow Documentation Update

Status: autonomous multi-agent Agile organization documentation added.

Completed:
- Added `docs/agentic-workflows/` as the source for agentic tasking and workflows.
- Added role files for PO, PM, Architect, Developer, QA, Reviewer, Security, DevOps, and Release Manager agents.
- Added sprint lifecycle and release management workflow documents.
- Added governance documents for story statuses, Definition of Done, coordination, continuous learning, and risk management.
- Added the required agent response format template.
- Updated the root README and documentation index.

Next steps:
- Connect these workflow definitions to future backend agent orchestration APIs.
- Add machine-readable workflow/status schemas when the orchestration layer needs enforcement.

---

### Parallel Backend Hardening Pass

Status: multiple backend workers completed independent slices and the API integration is wired.

Completed:
- Added CLI approval queue and persisted command run history.
- Added CLI approve, deny, execute-approved, list approvals, and list run history API endpoints.
- Added CLI output redaction and truncation for sensitive `TOKEN=`, `PASSWORD=`, and `SECRET=` assignments.
- Added local provider chat generation runtime for Ollama and LM Studio.
- Added provider generation API endpoint.
- Added generated tool execution runtime with JSON input/output handling.
- Added tool permission enforcement for approval-required, blocked, disabled, and deprecated tools.
- Added tool reliability tracking from execution runs: usage, success, failure, last-used, and reliability score.
- Added agent detail, child-agent listing, and lifecycle status update APIs.
- Added parent agent and task relationship fields to agent briefs.
- Added focused worker tests for CLI runtime, provider runtime, and tool runtime.
- Added API tests for CLI approvals, provider generation errors, generated tool execution, and agent lifecycle tracking.
- Updated README, architecture documentation, usage guide, developer setup, Agile task plan, and progress log.

Verification:
- `uv run pytest` passed with 32 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Remaining production work:
- Add streaming command output and restart-resilient process supervision.
- Add agent/context-aware CLI permissions and controlled command environments.
- Add external provider adapters and credential management.
- Add stronger tool sandbox isolation.
- Add UI surfaces for approvals, agents, tools, and provider activity.

---

### CLI Integration Backlog Update

Status: production CLI integration has been added as explicit required work.

Completed:
- Added Story 5.3 to the Agile task plan for completing production CLI integration.
- Captured approval records, approve/deny endpoints, persisted command run history, configurable command policy, argument-aware rules, safe parsing, output truncation/redaction, streaming or polling, cancellation, agent-aware permissions, environment controls, root boundary enforcement, tests, and documentation requirements.

Next steps:
- Add streaming command output and restart-resilient process supervision.
- Add agent/context-aware CLI permissions and controlled command environments.
- Broaden safe parsing validation across Windows and POSIX execution modes.

---

### Sprint 6 Dynamic Tool Creation Pass

Status: dynamic local tool generation and governance are implemented for the backend MVP.

Completed:
- Added tool trigger source and governance status schemas.
- Expanded tool manifests with interface, status, usage, success, failure, reliability, last-used, and deprecation metadata.
- Added `POST /tools/generate` to create `rootDir/localmcp/[tool_name]/` directories.
- Generated `tool.py`, `wrapper.py`, `manifest.json`, and `README.md` for generated tools.
- Added duplicate detection by name, matching tags plus description, and interface signature.
- Added permission validation so blocked tools cannot be generated.
- Registered generated tools in persisted local state.
- Indexed generated tools as memory artifacts for reuse lookup.
- Added `PATCH /tools/{name}/governance` for active, deprecated, and disabled status updates.
- Added tests for generation, file creation, duplicate detection, memory indexing, blocked permissions, and deprecation.
- Updated README, architecture documentation, usage guide, developer setup, Agile task plan, and progress log.

Verification:
- `uv run pytest` passed with 12 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Remaining production work:
- Add sandboxed generated tool execution.
- Add usage, success, failure, and reliability updates from actual tool runs.
- Add richer duplicate detection using code/interface similarity.
- Add multi-version storage where multiple versions of the same tool can coexist.
- Add UI and approval flow for tool generation and deprecation.

---

### Dynamic Tool Creation Backlog Update

Status: full Dynamic Tool Creation has been added as explicit required work.

Completed:
- Added Story 7.3 to the Agile task plan for fully implementing Dynamic Tool Creation and Self-Extensibility.
- Captured trigger sources, tool generation, `rootDir/localmcp/[tool_name]/` storage, registry and memory indexing, permission inheritance, duplicate detection, versioning, usage/reliability tracking, deprecation, reuse, and test requirements.

Next steps:
- Implement `POST /tools/generate`.
- Generate tool directories with source, manifest, wrapper, and README files.
- Add governance metadata, duplicate detection, version policy, memory indexing, and deprecation controls.

---

### Sprint 5 Provider Routing And Guarded CLI Pass

Status: local provider discovery, scored routing, and guarded command execution are implemented for the backend MVP.

Completed:
- Added `DGENTIC_OLLAMA_BASE_URL` and `DGENTIC_LM_STUDIO_BASE_URL` settings.
- Added live Ollama health/model discovery through `/api/tags`.
- Added live LM Studio health/model discovery through `/v1/models`.
- Added provider capability, latency, and cost metadata.
- Replaced first-enabled routing with scored provider routing and candidate score reporting.
- Added guarded CLI execution inside `rootDir`.
- Added blocked-command denial, approval-required command denial, explicit approved execution, timeouts, stdout/stderr capture, exit code capture, duration tracking, and audit logging.
- Added API endpoint: `POST /cli/execute`.
- Added tests for scored local routing and CLI policy enforcement.
- Bumped package and API version to `0.2.0`.
- Updated README, documentation index, architecture documentation, usage guide, developer setup, release distribution guide, release notes, and progress log.

Verification:
- `uv run pytest` passed with 10 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Remaining production work:
- Add chat/completion calls for Ollama and LM Studio.
- Add external provider adapters with secure credential handling and rate-limit metadata.
- Add a real approval queue/UI instead of the current `approved: true` API field.
- Add streaming command output and restart-resilient process supervision policies.
- Add agent/context-aware CLI permissions and controlled command environments.

---

### Sprint 4 Guarded Filesystem Operations Pass

Status: guarded text file read and write operations are available behind root boundary checks.

Completed:
- Added file read and write request/response schemas.
- Added guarded UTF-8 text file read service that rejects paths outside `rootDir`.
- Added guarded UTF-8 text file write service with optional parent directory creation.
- Added audit log events for guarded file reads and writes.
- Added API endpoints: `POST /filesystem/read` and `POST /filesystem/write`.
- Added tests for allowed writes, allowed reads, blocked outside-root access, and approval-required delete policy.
- Updated README, architecture documentation, usage guide, developer setup, and progress log.

Verification:
- `uv run pytest` passed with 9 tests.
- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.

Remaining production work:
- Add explicit approval workflow for delete, move, overwrite, and sensitive write operations.
- Add binary file handling and size limits.
- Add richer error contracts for filesystem operations.
- Add file operation history views and export support.

---

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
