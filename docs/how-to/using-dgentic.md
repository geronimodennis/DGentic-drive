# How To Use DGentic

Date created: 2026-05-07

DGentic is currently in the backend foundation phase. This guide explains how to use the repository now and how the platform is expected to be used as implementation continues.

## Use The Repository Today

### 1. Read The Goal

Start with `docs/DGentic-goal.md`. This is the source specification for the platform vision, required capabilities, architecture, security model, memory system, tool runtime, interfaces, and configuration settings.

### 2. Plan Work From The Agile Backlog

Use `docs/planning/agile-task-plan.md` to choose the next implementation work. The plan is organized into:

- Epics
- User stories
- Acceptance criteria
- Engineering tasks
- Milestones
- Initial Sprint 1 backlog

### 3. Record Progress

Update `docs/progress/project-progress-log.md` whenever meaningful work is completed. Each entry should include:

- Date
- Status
- Completed work
- Decisions
- Blockers
- Next steps

### 4. Keep Documentation Organized

Use these documentation folders:

- `docs/planning/` for Agile plans, roadmaps, sprint plans, and backlog notes.
- `docs/progress/` for progress logs, status reports, and decisions.
- `docs/architecture/` for system diagrams, technical designs, contracts, and security models.
- `docs/how-to/` for setup, usage, operations, and troubleshooting.

### 5. Run The Current Backend Foundation

Use `docs/how-to/developer-setup.md` to install dependencies, run the FastAPI service, call the starter task planning endpoint, and run verification commands.

## Future Platform Usage

Once implemented, DGentic should support this workflow:

### 1. Start The Backend

Run the DGentic backend orchestrator. The backend will own task planning, execution state, provider routing, agent lifecycle, tool execution, memory access, and audit logs.

### 2. Configure Model Providers

Configure local and external model providers:

- Local runtimes: Ollama and LM Studio.
- External providers: OpenAI, Google AI, DeepSeek, Anthropic, Copilot, or other supported services.
- Routing rules: Cost, latency, reliability, privacy, role-to-model mapping, and task complexity.

### 3. Set Security Boundaries

Configure strict operating boundaries before running autonomous tasks:

- Workspace `rootDir`
- Filesystem read, write, and delete permissions
- CLI execution mode
- Command blacklist or approval policy
- Network policy and domain rules
- Tool creation and execution permissions

### 4. Submit A Task

Submit work through a supported interface:

- Unified chat interface
- API
- CLI
- VS Code extension

DGentic should respond with a task plan, required context, proposed tools, model routing decisions, and any actions requiring approval.

### 5. Review Agent Work

During execution, inspect:

- Orchestrator status
- Sub-agent task progress
- CLI and filesystem action logs
- Provider usage
- Tool runs
- Validation results
- Approval prompts

### 6. Review Final Output

At task completion, DGentic should provide:

- Final answer or artifact
- Steps performed
- Files changed
- Tools created or reused
- Memory updates
- Known risks or unresolved issues
- Suggested next steps

### 7. Resume Later

DGentic should persist session state so future sessions can resume with context, memory, task history, and relevant project decisions.

## Current Limitations

- DGentic has only the first backend API foundation.
- Backend, frontend, extension, memory, routing, and tool execution components still need to be built.
- Commands for the current backend are documented in `docs/how-to/developer-setup.md`.
