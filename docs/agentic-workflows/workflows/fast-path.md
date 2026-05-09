# Fast-Path Workflow

The fast path is the default workflow for clear, low-risk work. It keeps accountability while avoiding the overhead of a full sprint ceremony for small changes.

## Entry Criteria

Use Fast Path when all are true:

- Acceptance criteria are clear or can be stated in one short checklist.
- Complexity, security, deployment, and dependency risk are all `1` or `2`.
- The task does not change authentication, authorization, secrets, database migrations, public APIs, CI/CD, deployment, or release packaging.
- The work can be validated with targeted checks or documentation review.

Escalate to Standard or Full Sprint when any entry criterion is no longer true.

## Required Steps

## 1. PM Triage

The PM or active coordinator must:

- State the task goal.
- Pick Fast Path and record why it is safe.
- Create a compact checklist.
- Identify the expected write scopes.

## 2. Implementation Or Documentation Update

The owning role performs the work:

- Developer for production behavior.
- QA for tests and validation assets.
- PM or documentation owner for planning and process docs.
- Release Manager for release artifacts.

If work crosses ownership boundaries, switch roles explicitly and list the write scope for each role block.

## 3. Targeted Validation

Run the smallest useful validation set:

- Documentation-only change: spelling, link, and consistency review.
- Narrow code change: focused test or command covering the touched behavior.
- Cross-module behavior change: related unit or integration tests.

Record skipped checks with a short reason.

## 4. Brief Review

Review only the changed surface for:

- Requirement fit.
- Regression risk.
- Security or deployment escalation triggers.
- Missing follow-up work.

## 5. Completion

To close Fast Path work:

- Mark checklist items complete or blocked.
- Record validation results.
- Add follow-up backlog items only when useful.
- Escalate instead of closing if new risk appears.

## Fast-Path Response Shape

Use the compact response format unless a full audit trail is needed:

```text
[PM/Dev/QA/etc.]
Mode: Fast Path
Task: <task name>
Checklist: <done/pending/blockers>
Changes: <files or none>
Validation: <checks run or skipped reason>
Next: <complete, handoff, or escalation>
```
