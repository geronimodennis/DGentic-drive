# Story Statuses And Definition Of Done

## Story Status States

Each story must maintain one of the following states:

- `TODO`
- `READY`
- `IN_ANALYSIS`
- `IN_ARCHITECTURE`
- `IN_PROGRESS`
- `IN_UNIT_TEST`
- `IN_QA`
- `QA_FAILED`
- `IN_REVIEW`
- `REVIEW_FAILED`
- `IN_SECURITY_REVIEW`
- `SECURITY_FAILED`
- `IN_INTEGRATION_TEST`
- `IN_DEPLOYMENT_VALIDATION`
- `READY_FOR_RELEASE`
- `RELEASED`
- `DONE`
- `BLOCKED`
- `MOVED_TO_BACKLOG`

## Definition Of Done

A story is considered `DONE` only if all applicable gates for the selected workflow mode are complete:

- Implementation completed.
- Unit tests passed.
- QA approved.
- Reviewer approved.
- Security review passed.
- Integration testing passed.
- Deployment validation passed.
- Documentation updated.
- Release validation completed.

For Fast Path work, non-applicable gates may be marked `N/A` with a short reason. For example, documentation-only work can mark implementation, unit tests, deployment validation, and release validation as `N/A` when no product behavior changes.

## Enforcement Rule

If any applicable Definition of Done item is missing, the story must not be marked `DONE`.

Skipped gates must be justified. If the justification becomes invalid, the story must return to the correct status and use the heavier workflow mode.
