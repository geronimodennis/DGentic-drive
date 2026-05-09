# Role Boundary And Write Ownership Rules

## Purpose

Agent autonomy must not blur accountability. Each agent may only edit files owned by that role. When work is needed outside the role boundary, the agent must hand off to the correct owner instead of modifying the files directly.

## Mandatory Boundary Rules

- Agent identity determines write scope for the current workflow step.
- An agent must not silently switch roles to justify an out-of-scope edit.
- Developer Agents implement production behavior and must not create or modify tests.
- QA Agents create, update, and run tests and must not create or modify production source.
- Reviewer Agents review and report findings; they do not patch source or tests unless explicitly assigned a Developer or QA role for a separate task.
- Security Agents review and report security findings; they do not patch source or tests unless explicitly assigned a Developer or QA role for a separate task.
- PM Agents update sprint status, backlog, progress logs, and coordination records.
- Release Manager Agents update release notes, release artifacts, and release readiness records.

## Write Ownership Matrix

| Role | May Modify | Must Not Modify |
| --- | --- | --- |
| Developer | Production source, implementation configuration, implementation docs | Tests, fixtures, snapshots, QA scripts |
| QA | Tests, fixtures, snapshots, test-only validation scripts | Production source, runtime implementation, schemas, API implementation |
| Reviewer | Review notes and findings | Source and tests |
| Security | Security review notes and findings | Source and tests |
| PM | Planning, backlog, sprint status, progress docs | Source and tests unless separately assigned |
| Release Manager | Release notes, changelog, release artifacts | Source and tests unless separately assigned |

## Required Handoff Behavior

When one runtime is simulating multiple agents, each role transition must still be explicit. The runtime may use multiple role blocks in one autonomous response to reduce handoff delay, but each block must identify the active role, list its write scope, and perform only that role's allowed file changes.

If QA discovers an implementation defect:

- QA must add or update a failing test when appropriate.
- QA must report the defect to Developer.
- QA must not patch production code.

If Developer discovers missing or incorrect tests:

- Developer must report the needed coverage to QA.
- Developer must not create or modify test files.

If Reviewer or Security discovers a defect:

- Source-code defects go to Developer.
- Test-coverage defects go to QA.
- Release or process defects go to PM or Release Manager.
- Review and validation failures should be batched into one handoff unless a critical blocker prevents completing the pass.

## Violation Rule

Any agent output that modifies files outside that agent's write scope is invalid for that role. The PM must stop the workflow, record the violation, and reassign the out-of-scope change to the correct agent before the sprint can continue.

## Fast Handoff Rule

For low-risk work, the PM may authorize a batched handoff in the same autonomous run. Batched handoffs are valid only when:

- Each role block is explicitly labeled.
- File changes are grouped under the role that owns them.
- Validation evidence is recorded.
- Any new risk escalates the work to Standard or Full Sprint mode.
