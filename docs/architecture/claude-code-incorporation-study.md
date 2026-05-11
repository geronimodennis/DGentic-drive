# Claude Code Incorporation Study

Date created: 2026-05-12

## Purpose

This note records what DGentic should learn from the public Claude Code repository study and how those patterns should be incorporated into DGentic's roadmap without copying Anthropic source code or plugin content.

Source studied:
- `https://github.com/anthropics/claude-code/tree/main`

License boundary:
- The studied repository declares `All rights reserved`.
- DGentic may use the public product and architecture ideas as competitive research, but implementation must be original DGentic code, tests, docs, schemas, and UX.
- Do not vendor, copy, translate, or lightly rewrite Claude Code commands, plugins, hooks, agents, settings examples, or scripts.

## Useful Patterns

### Terminal-First Command Center

Claude Code is centered on a terminal agent workflow with natural language requests, command shortcuts, and routine git automation. DGentic should keep its backend API surface, but Sprint 17 should make the dedicated CLI client a first-class daily workflow instead of a thin API wrapper.

DGentic adaptation:
- Add a `dgentic` CLI command tree for tasks, orchestrations, approvals, CLI runs, providers, memory, tools, logs, and sessions.
- Add safe workflow aliases for common operator actions such as review pending approvals, run a focused sprint, summarize active agents, prepare a commit, push a branch, and draft a PR.
- Keep all commands backed by existing API capability gates and safe review contracts.

### Plugin Bundles

Claude Code plugins bundle commands, agents, skills, hooks, and optional tool configuration under a recognizable manifest structure. DGentic already has generated tools, skills, agents, and orchestration. The missing product layer is a portable plugin package that combines those pieces into a reusable workflow bundle.

DGentic adaptation:
- Add a DGentic plugin manifest design for local/team packages.
- Support plugin components such as command recipes, agent blueprints, skills, generated-tool references, MCP/tool adapters, approval policy hints, and documentation.
- Keep installation explicit, auditable, capability-gated, and reversible.
- Add plugin trust metadata, versioning, compatibility checks, and source/provenance fields before marketplace-style distribution.

### Hook-Style Safety Rules

Claude Code examples show hook-style safety checks around tool use, command execution, file edits, and session lifecycle. DGentic already has guardrails, command policies, approval records, and orchestration-bound action checks. The next step is to expose these as operator-configurable rules with predictable events.

DGentic adaptation:
- Add backend hook policy records for command, filesystem, generated-tool, provider, network, prompt/task submission, and stop/closeout events.
- Support warn, block, approval-required, and audit actions.
- Require safe review metadata and secret redaction for all hook decisions.
- Route hook configuration through Sprint 16 settings UI and Sprint 17 CLI commands.

### Specialized Review Workflows

Claude Code's plugin set emphasizes specialized review agents for feature development, code review, PR review, tests, comments, type design, error handling, and simplification. DGentic already has role-bounded orchestration and agents; it should turn these patterns into reusable orchestration templates.

DGentic adaptation:
- Add orchestration templates for feature development, PR review, release readiness, security review, test-gap review, and git closeout.
- Allow templates to spawn parallel Developer, QA, Reviewer, Security, and DevOps tasks with declared write paths and Definition of Done evidence.
- Persist template runs as ordinary orchestration runs so the current scheduler, blockers, approvals, and progress docs continue to apply.

### Managed Settings And Enterprise Policy

Claude Code includes managed settings examples for stricter organization-level behavior. DGentic should add a managed settings layer for enterprise deployments instead of scattering operator policy across environment variables only.

DGentic adaptation:
- Add managed settings for auth mode, command policy, network policy, plugin trust, hook enablement, marketplace sources, provider availability, and approval strictness.
- Define precedence between environment variables, local settings files, managed settings, and persisted admin configuration.
- Audit policy source and effective settings without leaking secrets.

### Git And PR Workflow Automation

Claude Code includes command-level git workflow automation for commit, push, PR creation, branch cleanup, and review. DGentic should implement original equivalents as guarded CLI workflows because this directly supports the user's requested project-safety behavior.

DGentic adaptation:
- Add safe git workflow commands in the Sprint 17 CLI client.
- Add a project policy that can require commit and push at stable milestones.
- Require dirty-worktree review, secret-file checks, test evidence, and user-visible summary before commit or push actions.
- Keep destructive branch cleanup approval-gated.

## Roadmap Mapping

### Sprint 15

Relevant follow-up:
- Hook-style command/filesystem/network policy controls.
- Managed settings precedence and policy-source auditing.
- Broader CLI host-boundary enforcement.
- Non-provider network enforcement surfaces.

### Sprint 16

Relevant follow-up:
- Approval dashboard for hook-triggered and plugin-triggered actions.
- Settings UI for managed policies, plugin trust, command recipes, provider controls, network policy, and approval strictness.
- Dashboard panels for plugin health, hook decisions, review workflow outcomes, and git safety checkpoints.

### Sprint 17

Relevant follow-up:
- Dedicated terminal-first DGentic CLI client.
- CLI command recipes for task/orchestration, approval review, provider status, memory/tool operations, git commit/push/PR, branch cleanup, and sprint closeout.
- VS Code command palette and sidebar views that expose the same command recipes and approval contracts.
- Portable DGentic plugin package format for commands, agent blueprints, skills, hooks, generated-tool references, and docs.

### Sprint 18

Relevant follow-up:
- CI gates for plugin validation, hook policy validation, CLI smoke tests, PR review automation, and release-readiness workflows.
- Enterprise managed settings deployment guidance.
- Observability for hook decisions, plugin execution, CLI workflow success rates, PR review outcomes, and git checkpoint freshness.

### Sprint 19

Relevant follow-up:
- Provider-specific adapters should be deliverable as DGentic plugin packages when feasible.
- Adapter plugins must preserve provider policy, network approval, credential reference, routing, telemetry, streaming, and no-secret guarantees.

## First Implementation Recommendation

The highest leverage next implementation after the current Sprint 15 security slice is not provider-specific adapters. It is a DGentic-native command and plugin layer:

1. Define a minimal DGentic plugin manifest schema.
2. Add read-only plugin discovery for local plugin folders.
3. Add CLI command recipe specs that call existing backend APIs.
4. Add hook policy records that evaluate before dangerous command/filesystem/generated-tool/network actions.
5. Surface all of the above in the Sprint 16 UI and Sprint 17 CLI/VS Code clients.

This gives DGentic a strong Claude Code-like workflow feel while preserving DGentic's stronger backend-first orchestration, approval, audit, and multi-agent governance model.
