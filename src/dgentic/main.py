import asyncio
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from dgentic.api.memory_routes import router as memory_router
from dgentic.api.routes import router
from dgentic.auth import require_route_capability, validate_auth_configuration
from dgentic.settings import get_settings

UI_ASSETS_DIR = Path(__file__).with_name("ui")
_HTTP_RUNTIME_ROOT_SWITCH_LOCK = asyncio.Lock()


def create_app() -> FastAPI:
    settings = get_settings()
    validate_auth_configuration(settings)
    app = FastAPI(
        title=settings.app_name,
        version="0.2.6",
        summary="DGentic autonomous AI agent platform API.",
        dependencies=[Depends(require_route_capability)],
    )
    app.add_exception_handler(RequestValidationError, _request_validation_exception_handler)
    app.middleware("http")(_runtime_root_switch_middleware)
    app.include_router(router)
    app.include_router(memory_router)
    if UI_ASSETS_DIR.exists():
        app.mount("/ui", StaticFiles(directory=UI_ASSETS_DIR, html=True), name="ui")
    return app


async def _request_validation_exception_handler(
    _request,
    exc: RequestValidationError,
) -> JSONResponse:
    sanitized_errors = [
        {
            "loc": list(error.get("loc", [])),
            "msg": str(error.get("msg", "Invalid request.")),
            "type": str(error.get("type", "value_error")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": sanitized_errors})


async def _runtime_root_switch_middleware(request, call_next):
    async with _HTTP_RUNTIME_ROOT_SWITCH_LOCK:
        return await call_next(request)


app = create_app()
