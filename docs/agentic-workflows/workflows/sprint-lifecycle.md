# Complete Sprint Lifecycle

Use this full lifecycle for high-risk stories, release work, deployment changes, security-sensitive work, migrations, or broad architecture changes. For low-risk work, use [Fast Path](fast-path.md). For normal feature work, use only the applicable gates and mark non-applicable gates as `N/A` with a short reason.

## Lifecycle Routing

Before starting, the PM must choose:

- `Fast Path`: low-risk and clear scope.
- `Standard`: behavior changes or normal feature work.
- `Full Sprint`: high-risk, release-worthy, deployment, migration, security, or architecture-heavy work.

The workflow may escalate to a heavier mode at any point. It must not downgrade after high risk is discovered unless the PM records why the risk no longer applies.

## 1. Backlog Grooming

Owners: PO + PM

- Refine backlog.
- Clarify requirements.
- Prioritize stories.
- Estimate complexity.
- Identify dependencies.

## 2. Sprint Planning

Owners: PM + Architect

- Define sprint goals.
- Select stories.
- Assign priorities.
- Define risks.
- Assign responsibilities.
- Create the sprint checklist and define progress update locations.

## 3. Architecture Design

Owner: Architect

- Validate technical feasibility.
- Define architecture.
- Define APIs and contracts.
- Design databases and services.

## 4. Development

Owner: Developer

- Implement stories.
- Update implementation documentation when behavior changes.
- Format touched source when the repository has an established formatter.
- Run existing checks as needed.
- Submit implementation.

Boundary:

- Developer must not create or modify tests, fixtures, snapshots, or QA validation scripts.
- If tests need to change, Developer returns the story to QA with the expected behavior and coverage need.

## 5. Test Creation And Unit Testing

Owner: QA

- Create or update tests for implemented behavior.
- Run automated tests.
- Validate local correctness through test results.
- Ensure acceptance criteria and regression coverage.

Boundary:

- QA must not create or modify production source, runtime implementation, application schemas, or production configuration.
- If implementation must change, QA fails the story and returns it to Developer with failing evidence.

## 6. QA Validation

Owner: QA

- Validate requirements.
- Execute tests.
- Detect missing implementation.
- Validate edge cases.
- Batch all known failed validation findings from the current pass into one handoff unless a critical blocker prevents completing validation.

Boundary:

- QA reports defects and maintains tests only.
- QA does not patch implementation defects directly.

## Preferred Pre-Review Lane

- When the story needs both source and tests, Developer and QA should prefer adjacent explicit role blocks in the same autonomous run before Code Review.
- Developer should hand QA review-ready source plus formatter or local-check results, or explain why they are `N/A`.
- QA should either return one bundled defect handoff to Developer or send QA-approved work to Reviewer with the validation evidence.

## 7. Code Review

Owner: Reviewer

- Validate implementation quality.
- Review architecture consistency.
- Review maintainability.
- Batch all known failed review findings from the current pass into one handoff unless a critical blocker prevents completing review.

Loop control:

- After two failed Dev-QA-Review cycles for the same story, PM must triage the remaining issues and decide whether to continue, split scope, block the story, or move non-critical items to the backlog.

## 8. Security Review

Owner: Security

- Run vulnerability analysis.
- Validate security practices.
- Scan dependencies.

## 9. Integration Testing

Owners: QA + DevOps

- Validate integrations.
- Validate APIs.
- Validate services.
- Validate databases.

## 10. Deployment Validation

Owner: DevOps

- Deploy to staging.
- Execute smoke tests.
- Validate runtime behavior.

## 11. Sprint Review

Owners: PM + PO

- Validate completed work.
- Verify sprint goals.
- Approve completed features.

## 12. Release Management

Owner: Release Manager

- Prepare milestone release.
- Generate release notes.
- Validate deployment readiness.
- Coordinate release deployment.

## 13. Sprint Retrospective

Owners: All Agents

- Analyze failures.
- Identify bottlenecks.
- Improve workflows.
- Learn from defects.
- Improve future sprint efficiency.

## 14. Backlog Update

Owner: PM

- Create follow-up backlog items.
- Record technical debt.
- Schedule future improvements.
- Update the sprint checklist final state.
- Update progress documentation before closing the sprint.
