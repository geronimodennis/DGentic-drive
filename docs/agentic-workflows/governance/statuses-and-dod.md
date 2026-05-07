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

A story is considered `DONE` only if:

- Implementation completed.
- Unit tests passed.
- QA approved.
- Reviewer approved.
- Security review passed.
- Integration testing passed.
- Deployment validation passed.
- Documentation updated.
- Release validation completed.

## Enforcement Rule

If any Definition of Done item is missing, the story must not be marked `DONE`.
