# Coordination And Continuous Learning Rules

## Autonomous Coordination Rules

Agents must:

- Collaborate automatically.
- Maintain shared context.
- Track dependencies.
- Escalate blockers.
- Prevent duplicated work.
- Stay inside the write scope defined in `governance/role-boundaries.md`.
- Hand off work to the owning role instead of editing out-of-scope files.
- Continuously update statuses.
- Create backlog items automatically.
- Learn from previous sprint failures.

## Cross-Role Handoff Rule

An agent must request a handoff when the next required change belongs to another role.

Examples:

- QA finds a source defect: QA writes or updates the failing test, then sends the defect to Developer.
- Developer finds missing test coverage: Developer sends the expected behavior and coverage need to QA.
- Reviewer finds poor implementation quality: Reviewer sends the finding to Developer.
- Security finds missing security coverage: Security sends the source fix to Developer or the coverage request to QA.

## Continuous Learning System

The organization must continuously improve by:

- Learning from retrospectives.
- Tracking recurring failures.
- Tracking architecture issues.
- Improving sprint planning.
- Improving estimation quality.
- Improving security posture.
- Reducing technical debt.

## Backlog Management Rule

Any defect, blocker, risk, missing capability, or technical debt discovered by an agent must become a tracked backlog item unless it is fixed in the current sprint.
