Run this task in Autonomous Mode using docs/agentic-workflows.

Use the fastest safe workflow mode:
- Fast Path for clear, low-risk docs, small fixes, and local-only changes.
- Standard for normal feature work, behavior changes, or multi-file changes.
- Full Sprint for releases, migrations, deployment changes, security-sensitive work, or high-risk stories.

Escalate to a heavier mode as soon as the task touches security, deployment, public APIs, data migration, broad architecture, release packaging, or unresolved ambiguity.

When Full Sprint is required, follow the full multi-agent Agile workflow:
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
- Prefer the shortest valid workflow mode.
- Follow role write boundaries from `docs/agentic-workflows/governance/role-boundaries.md`.
- Do not silently switch agent roles to justify out-of-scope file edits; make role transitions explicit.
- A single autonomous run may contain multiple explicit role blocks when that reduces handoff delay.
- Developer role blocks must not create or modify tests, fixtures, snapshots, or QA validation scripts.
- QA role blocks must not create or modify production source, runtime implementation files, schemas, API implementation, or production configuration.
- If QA needs source changes, QA must fail the story and hand off to Developer with failing evidence.
- If Developer needs test changes, Developer must hand off to QA with expected behavior and coverage needs.
- Always create a checklist sized to the selected workflow mode before execution.
- Update checklist status at meaningful transitions.
- Update the project progress record when work completes, blockers appear, handoffs happen, follow-up backlog items are created, or a sprint closes.
- Create or update docs when behavior changes.
- QA adds or updates tests for implemented behavior when test changes are needed.
- Run the smallest useful quality checks for the selected mode and risk level.
- Commit and push only when explicitly requested or required by the active release workflow.
- If release-worthy, create a release bundle and GitHub release.
