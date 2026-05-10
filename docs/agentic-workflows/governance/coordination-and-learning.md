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
- Update statuses at meaningful workflow transitions.
- Create and maintain a visible checklist for every sprint, story, or delegated task, sized to the selected workflow mode.
- Update the project progress record when work is completed, blockers are found, handoffs occur, follow-up work is created, or a sprint closes.
- Create backlog items automatically.
- Learn from previous sprint failures.

## Checklist And Progress Rule

Every agent must create a checklist before executing meaningful work. The checklist should be as small as the selected workflow mode allows.

The checklist must:

- Identify the current sprint, story, or task.
- Show required workflow gates for the agent's role and mark skipped gates as `N/A` with a short reason.
- Be updated as work moves from pending to in progress to completed.
- Record blockers, handoffs, validation results, and follow-up backlog items.

The PM Agent owns the shared sprint checklist, but each agent owns the checklist for its assigned work. Agents may batch small checklist changes into one progress entry. Progress updates must be recorded in `docs/progress/project-progress-log.md` or the active sprint/progress document before a story is considered ready for closure.

## Cross-Role Handoff Rule

An agent must request a handoff when the next required change belongs to another role.

Examples:

- QA finds source defects: QA writes or updates failing tests when appropriate, then sends the collected defect bundle to Developer.
- Developer finds missing test coverage: Developer sends the expected behavior and coverage need to QA.
- Reviewer finds poor implementation quality: Reviewer sends the collected review finding bundle to Developer.
- Security finds missing security coverage: Security sends the source fix to Developer or the coverage request to QA.

## Batch-First Handoff Rule

QA and Reviewer Agents should batch all known findings from the current validation or review pass into one handoff. Findings should be grouped by severity, owning role, and affected file or behavior when possible.

Send one finding at a time only when a critical blocker prevents completing the rest of the validation or review.

Developer Agents should address the full handoff bundle in one implementation pass when the fixes are related and safe to combine.

After two failed Dev-QA-Review handoff cycles for the same story, the PM must triage the remaining issues and decide whether to continue, split scope, block the story, or move non-critical items to the backlog.

## Dev-QA Pre-Review Fast Loop

When a story needs both production and test changes, Developer and QA should prefer consecutive explicit role blocks in the same autonomous run before engaging Reviewer.

The preferred sequence is:

- Developer completes the source change, formats touched source when the repository has an established formatter, and records the smallest useful local validation.
- Developer hands QA the expected behavior, affected files or workflows, edge cases, and any known coverage needs.
- QA updates tests, runs targeted validation, and either returns one bundled defect handoff to Developer or sends QA-approved work to Reviewer with the validation evidence.

Trivial review-readiness issues such as missing formatting, skipped basic local validation without reason, or incomplete coverage expectations should be corrected in the Dev-QA loop before Reviewer time is used.

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

## Speed Rule

The organization should optimize for the smallest safe workflow:

- Use Fast Path for low-risk work.
- Combine adjacent handoffs into one autonomous run when role transitions are explicit.
- Prefer a paired `Dev -> QA` pre-review loop over separate turns when source and tests both need updates.
- Run targeted checks before broad suites unless risk requires a full run.
- Escalate immediately when a skipped gate becomes relevant.
