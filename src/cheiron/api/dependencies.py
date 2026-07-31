"""FastAPI dependency accessors backed by application state."""

from fastapi import HTTPException, Request, status

from cheiron.application.query_service import QueryService


def get_query_service(request: Request) -> QueryService:
    """Return the lifespan-owned query service."""

    service = getattr(request.app.state, "query_service", None)
    if not isinstance(service, QueryService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="query service is not ready",
        )
    return service
