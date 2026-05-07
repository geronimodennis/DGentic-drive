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
- Create and maintain a visible checklist for every sprint, story, or delegated task.
- Update the project progress record whenever checklist status changes, work is completed, blockers are found, or follow-up work is created.
- Create backlog items automatically.
- Learn from previous sprint failures.

## Checklist And Progress Rule

Every agent must create a checklist before executing meaningful work.

The checklist must:

- Identify the current sprint, story, or task.
- Show required workflow gates for the agent's role.
- Be updated as work moves from pending to in progress to completed.
- Record blockers, handoffs, validation results, and follow-up backlog items.

The PM Agent owns the shared sprint checklist, but each agent owns the checklist for its assigned work. Progress updates must be recorded in `docs/progress/project-progress-log.md` or the active sprint/progress document before a story is considered ready for closure.

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
