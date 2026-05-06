"""Example workflows for DGentic."""
from core.types import Workflow, WorkflowStep, AgentRole
from datetime import datetime


def create_code_review_workflow():
    """Create a code review workflow."""
    steps = [
        WorkflowStep(
            id="plan",
            name="Plan Code Review",
            description="Plan the code review process",
            agent_role=AgentRole.PLANNER,
            previous_steps=[],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="review_1",
            name="Initial Code Review",
            description="Perform initial code quality check",
            agent_role=AgentRole.CODER,
            previous_steps=["plan"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="review_2",
            name="Security Review",
            description="Check for security vulnerabilities",
            agent_role=AgentRole.VALIDATOR,
            previous_steps=["review_1"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="validate",
            name="Final Validation",
            description="Validate all findings",
            agent_role=AgentRole.VALIDATOR,
            previous_steps=["review_2"],
            parallel_execution=False,
        ),
    ]
    
    workflow = Workflow(
        id="code_review_wf",
        name="Code Review Workflow",
        description="Comprehensive code review process",
        steps=steps,
        version="1.0.0",
    )
    
    return workflow


def create_research_workflow():
    """Create a research workflow."""
    steps = [
        WorkflowStep(
            id="research_plan",
            name="Plan Research",
            description="Plan research methodology",
            agent_role=AgentRole.PLANNER,
            previous_steps=[],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="literature_review",
            name="Literature Review",
            description="Search and review existing literature",
            agent_role=AgentRole.RESEARCHER,
            previous_steps=["research_plan"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="data_collection",
            name="Data Collection",
            description="Collect relevant data",
            agent_role=AgentRole.RESEARCHER,
            previous_steps=["literature_review"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="analysis",
            name="Analysis",
            description="Analyze collected data",
            agent_role=AgentRole.CODER,
            previous_steps=["data_collection"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="synthesis",
            name="Synthesize Findings",
            description="Synthesize findings into conclusions",
            agent_role=AgentRole.RESEARCHER,
            previous_steps=["analysis"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="validation",
            name="Validate Results",
            description="Validate research results",
            agent_role=AgentRole.VALIDATOR,
            previous_steps=["synthesis"],
            parallel_execution=False,
        ),
    ]
    
    workflow = Workflow(
        id="research_wf",
        name="Research Workflow",
        description="End-to-end research process",
        steps=steps,
        version="1.0.0",
    )
    
    return workflow


def create_software_development_workflow():
    """Create a software development workflow."""
    steps = [
        WorkflowStep(
            id="requirements",
            name="Analyze Requirements",
            description="Plan and analyze requirements",
            agent_role=AgentRole.PLANNER,
            previous_steps=[],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="design",
            name="Design Architecture",
            description="Design system architecture",
            agent_role=AgentRole.PLANNER,
            previous_steps=["requirements"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="coding",
            name="Code Implementation",
            description="Implement the design",
            agent_role=AgentRole.CODER,
            previous_steps=["design"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="testing",
            name="Unit Testing",
            description="Create and run unit tests",
            agent_role=AgentRole.CODER,
            previous_steps=["coding"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="code_review",
            name="Code Review",
            description="Review code for quality",
            agent_role=AgentRole.VALIDATOR,
            previous_steps=["testing"],
            parallel_execution=False,
        ),
        WorkflowStep(
            id="deployment",
            name="Prepare Deployment",
            description="Prepare for deployment",
            agent_role=AgentRole.VALIDATOR,
            previous_steps=["code_review"],
            parallel_execution=False,
        ),
    ]
    
    workflow = Workflow(
        id="dev_wf",
        name="Software Development Workflow",
        description="Full software development lifecycle",
        steps=steps,
        version="1.0.0",
    )
    
    return workflow


# Registry of workflows
workflows = {
    "code_review": create_code_review_workflow(),
    "research": create_research_workflow(),
    "software_dev": create_software_development_workflow(),
}


def get_workflow(workflow_name: str):
    """Get a workflow by name."""
    return workflows.get(workflow_name)


def list_workflows():
    """List all available workflows."""
    return list(workflows.keys())


if __name__ == "__main__":
    print("Available Example Workflows:")
    for name, wf in workflows.items():
        print(f"\\n  {name.upper()}: {wf.name}")
        print(f"  Description: {wf.description}")
        print(f"  Steps: {len(wf.steps)}")
        for step in wf.steps:
            print(f"    - {step.name}")
