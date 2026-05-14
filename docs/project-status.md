# DGentic Project Status

Last updated: 2026-05-14.

Use this page as the current PM control panel. It does not replace the backlog or progress log; it points to the right source of truth so work can move faster without losing planned features.

## Current Sprint

- Active sprint: Sprint 15, Production Identity, Secrets, And Network Guardrails.
- Latest stable implementation checkpoint: BL-009a through BL-009av are implemented and validated.
- Latest completed slice: BL-009av, Managed Network-Domain Policy Rule Records.
- Current objective: stop Sprint 15 only at a safe validated checkpoint, then move primary delivery focus to user-facing Sprint 16 UI work and Sprint 17 VS Code/CLI work.

## Priority Order

1. Close the remaining Sprint 15 security work at the safest checkpoint.
2. Start Sprint 16: cross-platform web UI, approval dashboard, settings, and user-facing Git workflow visibility.
3. Start Sprint 17: VS Code extension and dedicated CLI client, including safe Git workflow commands.
4. Continue Sprint 18: deployment, CI/CD, observability, rollback, and Git workflow telemetry.
5. Continue Sprint 19: provider-specific external adapter expansion after a concrete provider target is selected.

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

- Richer production identity workflows beyond persisted operators and operator groups.
- Managed KMS integration beyond supplied-key local vault rotation.
- Additional secret-manager adapters beyond HashiCorp Vault KV v2.
- OS-level and non-Python generated-tool egress isolation.
- Plugin hook-code, tool, agent, and skill loading governance beyond declarative command recipes, hook policies, and inert reference records.
- Broader managed policy-source controls beyond credential, CLI, hook, network, command-recipe, plugin-trust, and plugin-component policy records plus coarse surface locks.

## Sprint Placement

- Sprint 15: production identity, secrets, network guardrails, and the already implemented backend Git safety foundation.
- Sprint 16: cross-platform UI and approval dashboard, including Git checkpoint, approval, run history, blocker, and freshness surfaces.
- Sprint 17: VS Code extension and dedicated CLI client, including Git checkpoint, commit, push, PR, review, and status flows.
- Sprint 18: deployment, CI/CD, observability, rollback, and Git usage telemetry.
- Sprint 19: provider-specific external adapter expansion after a concrete provider target is selected.

## Source Of Truth

- Current state and priority: this file.
- Roadmap, backlog, and sprint placement: [planning/backlog-needs-to-be-done.md](planning/backlog-needs-to-be-done.md).
- Agile epics, stories, and release gates: [planning/agile-task-plan.md](planning/agile-task-plan.md).
- Historical implementation log: [progress/project-progress-log.md](progress/project-progress-log.md).
- Architecture and backend contracts: [architecture/repository-architecture.md](architecture/repository-architecture.md).
- Setup and usage: [how-to/developer-setup.md](how-to/developer-setup.md) and [how-to/using-dgentic.md](how-to/using-dgentic.md).
