"""FastAPI application entry point and dependency lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from cheiron import __version__
from cheiron.api.responses import error_response
from cheiron.api.routes import router as query_router
from cheiron.application.query_service import QueryService
from cheiron.application.runtime import build_runtime
from cheiron.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    query_service: QueryService | None = None,
) -> FastAPI:
    """Create the FastAPI application without import-time side effects."""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if query_service is not None:
            application.state.query_service = query_service
            yield
            return
        runtime = build_runtime(resolved_settings)
        application.state.query_service = runtime.query_service
        application.state.effective_planner = runtime.effective_planner
        try:
            yield
        finally:
            await runtime.aclose()

    application = FastAPI(
        title="Cheiron API",
        summary="ClinicalTrials.gov query-to-visualization agent",
        version=__version__,
        lifespan=lifespan,
    )
    if query_service is not None:
        application.state.query_service = query_service
    application.state.effective_planner = _effective_planner(resolved_settings)

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            uuid4(),
            code="invalid_request",
            message="The request payload failed validation.",
            context={"error_count": len(error.errors())},
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        del request
        request_id = uuid4()
        LOGGER.exception("Unhandled query API error", extra={"request_id": str(request_id)})
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            request_id,
            code="internal_error",
            message="An unexpected internal error occurred.",
            retryable=True,
        )

    @application.get("/health", tags=["operations"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved_settings.service_name,
            "version": __version__,
        }

    @application.get("/ready", tags=["operations"])
    async def readiness() -> JSONResponse:
        effective_planner = application.state.effective_planner
        payload = {
            "status": "not_ready" if effective_planner == "unavailable" else "ready",
            "environment": resolved_settings.environment,
            "planner_provider": resolved_settings.planner_provider,
            "effective_planner": effective_planner,
            "openai_configured": resolved_settings.openai_api_key is not None,
        }
        return JSONResponse(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if effective_planner == "unavailable"
                else status.HTTP_200_OK
            ),
            content=payload,
        )

    application.include_router(query_router, prefix=resolved_settings.api_prefix)
    return application


def _effective_planner(settings: Settings) -> str:
    if settings.planner_provider == "rules":
        return "rules"
    if settings.openai_api_key is None:
        return "unavailable" if settings.planner_provider == "openai" else "rules"
    return "openai" if settings.planner_provider == "openai" else "openai_with_rules_fallback"


app = create_app()
