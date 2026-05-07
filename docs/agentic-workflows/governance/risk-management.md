# Risk Management System

Each story or task must contain:

- Complexity score.
- Risk score.
- Security score.
- Deployment risk score.
- Dependency risk score.

## Suggested Scale

Use a `1` to `5` scale:

- `1`: Low risk or complexity.
- `2`: Minor risk or complexity.
- `3`: Moderate risk or complexity.
- `4`: High risk or complexity.
- `5`: Critical risk or complexity.

## Required Risk Handling

For each score of `4` or `5`, agents must document:

- Why the risk is high.
- Which agent owns mitigation.
- What validation is required.
- Whether the story can proceed or must be blocked.

## Escalation Rule

Stories with unresolved security, deployment, or dependency risk of `5` must be marked `BLOCKED` until mitigated or explicitly approved.
