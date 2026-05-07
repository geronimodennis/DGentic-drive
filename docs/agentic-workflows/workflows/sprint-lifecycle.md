# Complete Sprint Lifecycle

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

Boundary:

- QA reports defects and maintains tests only.
- QA does not patch implementation defects directly.

## 7. Code Review

Owner: Reviewer

- Validate implementation quality.
- Review architecture consistency.
- Review maintainability.

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
