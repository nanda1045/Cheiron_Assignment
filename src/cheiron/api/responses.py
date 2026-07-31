"""Reusable JSON construction for typed public API errors."""

from uuid import UUID

from fastapi.responses import JSONResponse

from cheiron.domain.response import ErrorDetail, ErrorResponse
from cheiron.domain.visualization import ScalarValue


def error_response(
    status_code: int,
    request_id: UUID,
    *,
    code: str,
    message: str,
    retryable: bool = False,
    context: dict[str, ScalarValue] | None = None,
) -> JSONResponse:
    """Serialize the versioned error envelope with the requested HTTP status."""

    response = ErrorResponse(
        request_id=request_id,
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            context=context or {},
        ),
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )
