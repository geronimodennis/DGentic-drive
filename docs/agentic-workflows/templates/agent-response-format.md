# Agent Response Format

Every agent response must follow this structure.

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

## Findings

List:

- Defects.
- Blockers.
- Risks.
- Recommendations.
- Validation results.

## Next Action

Describe the next workflow step.

## Example

```text
[QA1]

Current Story:
Story 7.3: Fully Implement Dynamic Tool Creation

Action Summary:
Ran API and regression tests for generated tool creation and governance.

Findings:
- Defect: Duplicate detection does not compare interface signatures.
- Risk: Tool execution sandbox is not implemented.
- Validation: Existing API tests passed.

Next Action:
Return story to Dev1 for duplicate detection and sandbox follow-up.
```
