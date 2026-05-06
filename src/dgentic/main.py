from fastapi import FastAPI

from dgentic.api.routes import router
from dgentic.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        summary="DGentic autonomous AI agent platform API.",
    )
    app.include_router(router)
    return app


app = create_app()
