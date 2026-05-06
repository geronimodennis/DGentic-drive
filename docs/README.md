# DGentic Documentation

This folder contains the source documentation for the DGentic project.

## Core Documents

- [DGentic goal](DGentic-goal.md): Product vision, capabilities, architecture, and configuration requirements.
- [Agile task plan](planning/agile-task-plan.md): Implementation backlog organized by Agile epics, stories, acceptance criteria, and milestones.
- [Project progress log](progress/project-progress-log.md): Running project history, decisions, completed work, blockers, and next steps.
- [How to use DGentic](how-to/using-dgentic.md): Current and future usage guidance for the platform.
- [Developer setup](how-to/developer-setup.md): Local backend setup, run, test, and lint commands.
- [Repository architecture](architecture/repository-architecture.md): Current monorepo layout and architecture decisions.
- [Release distribution](how-to/release-distribution.md): Build and verify release artifacts.
- [0.1.0 release notes](releases/0.1.0.md): First backend foundation release notes.

## Suggested Documentation Structure

- `planning/`: Roadmaps, sprint plans, backlog grooming notes, release plans.
- `progress/`: Project logs, status reports, decision records.
- `architecture/`: Technical architecture, diagrams, interface contracts, security model.
- `how-to/`: Setup, usage, operations, and troubleshooting guides.

## Documentation Practice

Update the README and relevant documentation whenever implementation changes behavior, API contracts, setup, release artifacts, or project status. Update the progress log whenever the project meaningfully changes. Add new documents to the documentation index so future contributors can find the current source of truth quickly.

For backend API changes, update at least:

- Root `README.md`
- `docs/architecture/repository-architecture.md`
- `docs/how-to/using-dgentic.md`
- `docs/progress/project-progress-log.md`
