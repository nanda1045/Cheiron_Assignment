"""FastAPI application entry point."""

from typing import Any

from fastapi import FastAPI

from cheiron import __version__
from cheiron.config import get_settings


def create_app() -> FastAPI:
    """Create the FastAPI application without import-time side effects."""

    settings = get_settings()
    application = FastAPI(
        title="Cheiron API",
        summary="ClinicalTrials.gov query-to-visualization agent",
        version=__version__,
    )

    @application.get("/health", tags=["operations"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name, "version": __version__}

    @application.get("/ready", tags=["operations"])
    async def readiness() -> dict[str, Any]:
        return {
            "status": "ready",
            "environment": settings.environment,
            "planner_provider": settings.planner_provider,
        }

    return application


app = create_app()
