# Agent Response Format

Every agent response must follow this structure.

Use the compact format for Fast Path work. Use the full format for Standard or Full Sprint work, or whenever the task needs a stronger audit trail.

## Compact Fast-Path Format

```text
[Agent]
Mode: Fast Path
Task:
<current story, task, or backlog item>

Checklist:
- Completed: <item>
- Pending: <item or none>
- N/A: <skipped gate and reason>

Changes:
<files or None>

Validation:
<checks run, results, or skipped reason>

Next:
<complete, handoff, escalation, or follow-up>
```

## Full Format

## Agent Identity

Examples:

- `[PO]`
- `[PM]`
- `[Architect]`
- `[Dev1]`
- `[QA1]`
- `[Rev1]`
- `[Security]`
- `[DevOps]`
- `[ReleaseManager]`

## Current Story

Reference the current story, task, or backlog item.

## Action Summary

Describe actions performed.

## Checklist And Progress Update

List the checklist items for the current story or task and their statuses.

State where progress was updated. If no progress document changed, explain why.

## Write Scope Used

List the files or file categories the agent changed.

If the agent changed no files, write `None`.

The write scope must match the role boundary rules in `docs/agentic-workflows/governance/role-boundaries.md`.

## Findings

List:

- Defects.
- Blockers.
- Risks.
- Recommendations.
- Validation results.

When handing off failed QA or review work, list all known findings from the current pass unless a critical blocker prevented completing the pass.

## Next Action

Describe the next workflow step.

## Example

```text
[QA1]

Current Story:
Story 7.3: Fully Implement Dynamic Tool Creation

Action Summary:
Ran API and regression tests for generated tool creation and governance.

Checklist And Progress Update:
- Completed: API regression tests.
- Completed: Duplicate detection validation.
- Pending: Sandbox follow-up implementation.
- Progress updated in `docs/progress/project-progress-log.md`.

Write Scope Used:
- `tests/`

Findings:
- Defect: Duplicate detection does not compare interface signatures.
- Risk: Tool execution sandbox is not implemented.
- Validation: Existing API tests passed.

Next Action:
Return story to Dev1 for duplicate detection and sandbox follow-up.
```
