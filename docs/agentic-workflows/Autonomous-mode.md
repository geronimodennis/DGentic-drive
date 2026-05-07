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
- Follow role write boundaries from `docs/agentic-workflows/governance/role-boundaries.md`.
- Do not silently switch agent roles to justify out-of-scope file edits.
- Developer agents must not create or modify tests, fixtures, snapshots, or QA validation scripts.
- QA agents must not create or modify production source, runtime implementation files, schemas, API implementation, or production configuration.
- If QA needs source changes, QA must fail the story and hand off to Developer with failing evidence.
- If Developer needs test changes, Developer must hand off to QA with expected behavior and coverage needs.
- Create or update docs when behavior changes.
- QA adds or updates tests for implemented behavior.
- Run quality checks.
- Commit and push when complete.
- If release-worthy, create a release bundle and GitHub release.
