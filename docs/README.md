# DGentic Documentation

This folder contains the source documentation for the DGentic project.

## Start Here

- [Project status](project-status.md): Current sprint, priority order, safe stopping rules, and source-of-truth links.

## Source Of Truth

- Current state and active priority: [Project status](project-status.md).
- Roadmap, backlog, and sprint placement: [Backlog list and needs to be done](planning/backlog-needs-to-be-done.md).
- Agile epics, stories, and release gates: [Agile task plan](planning/agile-task-plan.md).
- Historical implementation log: [Project progress log](progress/project-progress-log.md).
- Architecture and backend contracts: [Repository architecture](architecture/repository-architecture.md).
- Setup and usage: [Developer setup](how-to/developer-setup.md) and [How to use DGentic](how-to/using-dgentic.md).

## Core Documents

- [DGentic goal](DGentic-goal.md): Product vision, capabilities, architecture, and configuration requirements.
- [Project status](project-status.md): Current PM control panel for active sprint, priority, and safe stopping rules.
- [Agentic tasking and workflows](agentic-workflows/README.md): Autonomous multi-agent Agile engineering organization, roles, workflows, role boundaries, governance, and response templates.
- [Agile task plan](planning/agile-task-plan.md): Implementation backlog organized by Agile epics, stories, acceptance criteria, and milestones.
- [Backlog list and needs to be done](planning/backlog-needs-to-be-done.md): Refined backlog, completion stories, and sprint sequence for partially implemented feature groups.
- [Generated orchestration follow-up backlog](planning/orchestration-follow-ups.md): Generated open orchestration follow-up and blocker list.
- [Project progress log](progress/project-progress-log.md): Running project history, decisions, completed work, blockers, and next steps.
- [Generated orchestration run status](progress/orchestration-runs.md): Generated orchestration run status from backend state.
- [How to use DGentic](how-to/using-dgentic.md): Current and future usage guidance for the platform.
- [Developer setup](how-to/developer-setup.md): Local backend setup, run, test, and lint commands.
- [Repository architecture](architecture/repository-architecture.md): Current monorepo layout and architecture decisions.
- [Sprint 6 memory architecture](architecture/sprint-6/memory-architecture.md): Metadata index, retrieval, and tool registry architecture draft.
- [Release distribution](how-to/release-distribution.md): Build and verify release artifacts.
- [0.2.6 release notes](releases/0.2.6.md): Sprint 8 production security and persistence foundation release notes.
- [0.2.5 release notes](releases/0.2.5.md): README status policy and implementation status release notes.
- [0.2.4 release notes](releases/0.2.4.md): CLI context-aware permissions and controlled environment release notes.
- [0.2.3 release notes](releases/0.2.3.md): Autonomous agent role boundary governance release notes.
- [0.2.2 release notes](releases/0.2.2.md): Asynchronous CLI runs, polling, cancellation, and shell-wrapper policy hardening release notes.
- [0.2.1 release notes](releases/0.2.1.md): Configurable CLI policy rules and agentic workflow documentation release notes.
- [0.2.0 release notes](releases/0.2.0.md): Provider probes, scored routing, guarded CLI execution, persistence, and filesystem release notes.
- [0.1.0 release notes](releases/0.1.0.md): First backend foundation release notes.

## Suggested Documentation Structure

- `planning/`: Roadmaps, sprint plans, backlog grooming notes, release plans.
- `progress/`: Project logs, status reports, decision records.
- `architecture/`: Technical architecture, diagrams, interface contracts, security model.
- `how-to/`: Setup, usage, operations, and troubleshooting guides.
- `agentic-workflows/`: Agent roles, role write boundaries, sprint lifecycle, release workflow, coordination rules, risk management, and agent response templates.

## Documentation Practice

Update the README and relevant documentation whenever implementation changes behavior, API contracts, setup, release artifacts, or project status. Update [Project status](project-status.md) when the active sprint, priority order, safe stopping rule, or next action changes. Update the progress log whenever the project meaningfully changes. Add new documents to the documentation index so future contributors can find the current source of truth quickly.

For backend API changes, update at least:

- Root `README.md`
- `docs/architecture/repository-architecture.md`
- `docs/how-to/using-dgentic.md`
- `docs/progress/project-progress-log.md`
