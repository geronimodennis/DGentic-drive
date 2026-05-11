from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dgentic.api.memory_routes import router as memory_router
from dgentic.api.routes import router
from dgentic.auth import require_route_capability, validate_auth_configuration
from dgentic.settings import get_settings


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
    app.include_router(router)
    app.include_router(memory_router)
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


app = create_app()
