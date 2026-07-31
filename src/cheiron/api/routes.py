"""Versioned query endpoint and typed boundary-error mapping."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from cheiron.analysis.errors import AnalysisError
from cheiron.api.dependencies import get_query_service
from cheiron.api.responses import error_response
from cheiron.application.query_service import QueryService
from cheiron.clinical_trials.errors import (
    ClinicalTrialsRequestError,
    ClinicalTrialsResponseError,
    ClinicalTrialsTransientError,
    PaginationError,
    QueryTooBroadError,
)
from cheiron.domain.request import QueryRequest
from cheiron.domain.response import (
    Clarification,
    ClarificationResponse,
    ErrorResponse,
    QueryResponse,
)
from cheiron.planning.errors import ClarificationNeeded, OpenAIPlanningError

router = APIRouter(tags=["queries"])
QueryServiceDependency = Annotated[QueryService, Depends(get_query_service)]


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def query_trials(
    request: QueryRequest,
    service: QueryServiceDependency,
) -> QueryResponse | JSONResponse:
    """Convert a natural-language request into a sourced visualization spec."""

    request_id = uuid4()
    try:
        return await service.execute(request, request_id=request_id)
    except ClarificationNeeded as error:
        return ClarificationResponse(
            request_id=request_id,
            clarification=Clarification(
                question=error.question,
                missing_fields=list(error.missing_fields),
                suggestions=list(error.suggestions),
            ),
        )
    except QueryTooBroadError as error:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            request_id,
            code="query_too_broad",
            message=str(error),
            context={
                "matched_count": error.matched_count,
                "max_studies": error.max_studies,
            },
        )
    except OpenAIPlanningError:
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            request_id,
            code="planner_unavailable",
            message="The configured planner is temporarily unavailable.",
            retryable=True,
        )
    except ClinicalTrialsTransientError:
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            request_id,
            code="source_unavailable",
            message="ClinicalTrials.gov is temporarily unavailable.",
            retryable=True,
        )
    except ClinicalTrialsRequestError:
        return error_response(
            status.HTTP_502_BAD_GATEWAY,
            request_id,
            code="source_rejected_query",
            message="ClinicalTrials.gov rejected the compiled query.",
        )
    except (ClinicalTrialsResponseError, PaginationError):
        return error_response(
            status.HTTP_502_BAD_GATEWAY,
            request_id,
            code="source_contract_error",
            message="ClinicalTrials.gov returned an incomplete or invalid response.",
            retryable=True,
        )
    except AnalysisError:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            request_id,
            code="analysis_failed",
            message="The requested analysis could not be executed safely.",
        )
