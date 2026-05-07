Run this task in Autonomous Mode using docs/agentic-workflows.

Follow the full multi-agent Agile workflow:
- PO defines business goal and acceptance criteria.
- PM creates/updates the sprint task.
- Architect validates design and contracts.
- Dev implements the change.
- QA validates acceptance criteria and regression risk.
- Reviewer checks code quality and maintainability.
- Security reviews security risk.
- DevOps validates runtime/deployment concerns.
- Release Manager prepares release notes if release-worthy.
- PM updates backlog/progress and closes the sprint only if Definition of Done is met.

Use the required agent response format from:
docs/agentic-workflows/templates/agent-response-format.md

Task:
[describe the work here]

Rules:
- Work autonomously.
- Create or update docs when behavior changes.
- Add tests for implemented behavior.
- Run quality checks.
- Commit and push when complete.
- If release-worthy, create a release bundle and GitHub release.
