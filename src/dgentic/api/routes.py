from fastapi import APIRouter

from dgentic.planner import create_initial_plan
from dgentic.schemas import HealthResponse, TaskPlan, TaskRequest
from dgentic.settings import get_settings

router = APIRouter()


@router.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@router.post("/tasks/plan", response_model=TaskPlan, status_code=201)
def plan_task(request: TaskRequest) -> TaskPlan:
    return create_initial_plan(request)
