from uuid import uuid4

from dgentic.schemas import PlanStep, TaskPlan, TaskRequest


def create_initial_plan(request: TaskRequest) -> TaskPlan:
    """Create a deterministic starter plan before model-backed planning exists."""
    clarification_questions: list[str] = []
    if len(request.objective.strip()) < 12:
        clarification_questions.append("What outcome should DGentic optimize for?")

    acceptance_criteria = request.acceptance_criteria or [
        "The final output directly satisfies the requested objective.",
        "Any guarded filesystem, CLI, network, or provider action is auditable.",
        "The response includes validation notes and unresolved risks.",
    ]

    steps = [
        PlanStep(
            id="step-1",
            title="Clarify objective and constraints",
            description=(
                "Confirm the requested outcome, available context, permission boundaries, "
                "and acceptance criteria."
            ),
            agent_role="orchestrator",
            validation="Objective, constraints, and success criteria are explicit.",
        ),
        PlanStep(
            id="step-2",
            title="Assess context and required capabilities",
            description=(
                "Identify required model providers, tools, memory sources, files, CLI commands, "
                "and network access."
            ),
            agent_role="orchestrator",
            dependencies=["step-1"],
            validation="Required capabilities and risks are captured before execution.",
        ),
        PlanStep(
            id="step-3",
            title="Choose routing and delegation strategy",
            description=(
                "Select local or external models and decide whether specialized sub-agents "
                "are needed."
            ),
            agent_role="router",
            dependencies=["step-2"],
            validation=(
                "Routing decision explains cost, latency, privacy, reliability, "
                "and complexity tradeoffs."
            ),
        ),
        PlanStep(
            id="step-4",
            title="Execute guarded work",
            description=(
                "Run approved actions within configured filesystem, CLI, provider, network, "
                "and tool boundaries."
            ),
            agent_role="executor",
            dependencies=["step-3"],
            validation="Each action emits status, output, errors, and audit metadata.",
        ),
        PlanStep(
            id="step-5",
            title="Validate and summarize result",
            description=(
                "Check outputs against acceptance criteria, reconcile conflicts, "
                "and produce a final session summary."
            ),
            agent_role="reviewer",
            dependencies=["step-4"],
            validation=(
                "Final output includes validation notes, changed artifacts, memory updates, "
                "and next steps."
            ),
        ),
    ]

    return TaskPlan(
        id=f"plan-{uuid4()}",
        objective=request.objective,
        constraints=request.constraints,
        acceptance_criteria=acceptance_criteria,
        clarification_questions=clarification_questions,
        steps=steps,
    )
