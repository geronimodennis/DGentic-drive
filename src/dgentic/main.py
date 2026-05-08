from fastapi import Depends, FastAPI

from dgentic.api.memory_routes import router as memory_router
from dgentic.api.routes import router
from dgentic.auth import require_route_capability
from dgentic.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.5",
        summary="DGentic autonomous AI agent platform API.",
        dependencies=[Depends(require_route_capability)],
    )
    app.include_router(router)
    app.include_router(memory_router)
    return app


app = create_app()
