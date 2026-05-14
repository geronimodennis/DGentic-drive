# DGentic Project Status

Last updated: 2026-05-14.

Use this page as the current PM control panel. It does not replace the backlog or progress log; it points to the right source of truth so work can move faster without losing planned features.

## Current Sprint

- Active sprint: Sprint 16, Cross-Platform UI And Approval Dashboard.
- Latest stable implementation checkpoint: BL-010i richer approval filtering is implemented and full-regression clean.
- Latest completed slice: BL-010i, dashboard approval source/status filters, filtered summary counts, safe review reset on filter change, UI contract tests, and static JS validation.
- Current objective: continue deepening the Sprint 16 user-facing UI, with AI-change review, richer settings editors, non-CLI execution UX, richer sub-agent detail, and broader browser validation next, while keeping remaining Sprint 15 backend security and Git expansion work deferred, not cancelled.

## Priority Order

1. Continue Sprint 16: richer task/chat UI, project add/open and rootDir switching, active project context controls, Codex-style AI-change review, approval dashboard, settings, plugin/command-recipe views, and Git workflow visibility.
2. Start Sprint 17: VS Code chat extension and dedicated CLI client, including native VS Code Explorer/editor/diff integration and safe Git workflow commands.
3. Continue Sprint 18: deployment, CI/CD, observability, rollback, and Git workflow telemetry.
4. Continue Sprint 19: provider-specific external adapter expansion after a concrete provider target is selected.
5. Return to deferred Sprint 15/backend Git hardening when it directly enables user-facing flows or after Sprint 16/17 surfaces are stable.

## Safe Stopping Rule For Git

- Do not stop Git work in the middle of a dependent feature chain.
- Stop only after the active Git slice or sprint checkpoint is validated, documented, committed, pushed, and its remaining work is recorded as deferred rather than cancelled.
- Do not downsize the planned backend Git workflow feature set.
- Move most new backend Git expansion after the Sprint 16 UI and Sprint 17 VS Code/CLI surfaces unless a backend Git item directly blocks those user-facing flows.

Current implemented Git foundation:

- Read-only Git workflow checkpoints.
- Checkpoint-bound commit, push, and PR approval creation.
- Direct checkpoint-bound local commit, configured-upstream push, and GitHub PR creation runners.
- Authenticated actor binding, protected branch/file checks, secret-shaped staged-addition checks, workflow revalidation, and safe audit metadata.

Remaining Git roadmap:

- Branch cleanup.
- PR labels, reviewers, assignees, projects, and templates.
- Remote fetch freshness.
- Rollback and revert workflows.
- Allowed remote and branch policies.
- Destructive branch operation approval.
- Richer Git audit, observability, and provider integrations.

## Remaining Sprint 15 Follow-Ups

Sprint 15 is closed at the BL-009av safe backend security checkpoint. These items remain deferred follow-ups, not cancelled scope:

- Richer production identity workflows beyond persisted operators and operator groups.
- Managed KMS integration beyond supplied-key local vault rotation.
- Additional secret-manager adapters beyond HashiCorp Vault KV v2.
- OS-level and non-Python generated-tool egress isolation.
- Plugin hook-code, tool, agent, and skill loading governance beyond declarative command recipes, hook policies, and inert reference records.
- Broader managed policy-source controls beyond credential, CLI, hook, network, command-recipe, plugin-trust, and plugin-component policy records plus coarse surface locks.

## Sprint Placement

- Sprint 15: production identity, secrets, network guardrails, and the already implemented backend Git safety foundation. Closed at BL-009av for the current backend security checkpoint.
- Sprint 16: cross-platform UI and approval dashboard, including chat, project add/open, file explorer, code editor, orchestration task/execution detail, AI-change review, Git checkpoint, approval, run history, blocker, and freshness surfaces. Active with BL-010a through BL-010i implemented.
- Sprint 17: VS Code chat extension and dedicated CLI client, including native VS Code workspace-folder `rootDir` binding, Explorer/editor integration, AI-change diff review, Git checkpoint, commit, push, PR, review, and status flows.
- Sprint 18: deployment, CI/CD, observability, rollback, and Git usage telemetry.
- Sprint 19: provider-specific external adapter expansion after a concrete provider target is selected.

## Source Of Truth

- Current state and priority: this file.
- Roadmap, backlog, and sprint placement: [planning/backlog-needs-to-be-done.md](planning/backlog-needs-to-be-done.md).
- Agile epics, stories, and release gates: [planning/agile-task-plan.md](planning/agile-task-plan.md).
- Historical implementation log: [progress/project-progress-log.md](progress/project-progress-log.md).
- Architecture and backend contracts: [architecture/repository-architecture.md](architecture/repository-architecture.md).
- Setup and usage: [how-to/developer-setup.md](how-to/developer-setup.md) and [how-to/using-dgentic.md](how-to/using-dgentic.md).
