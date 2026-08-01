"""HTTP contract tests for the versioned query endpoint."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cheiron.application.query_service import QueryService
from cheiron.clinical_trials.errors import (
    ClinicalTrialsRequestError,
    ClinicalTrialsTransientError,
    QueryTooBroadError,
)
from cheiron.clinical_trials.models import CohortRetrieval, DatasetVersion
from cheiron.clinical_trials.query_compiler import CompiledQuery
from cheiron.config import Settings
from cheiron.domain.request import QueryRequest
from cheiron.domain.response import SuccessResponse
from cheiron.main import create_app
from cheiron.planning.errors import (
    ModelOutputError,
    ModelProviderError,
    ModelRequestError,
    PlannerConfigurationError,
)
from cheiron.planning.rules import RuleBasedPlanner


class EndpointGateway:
    def __init__(
        self,
        studies: list[dict[str, Any]],
        *,
        failure: Exception | None = None,
    ) -> None:
        self._studies = tuple(studies)
        self._failure = failure
        self.fetch_calls = 0

    async def get_version(self) -> DatasetVersion:
        if self._failure is not None:
            raise self._failure
        return DatasetVersion(
            api_version="2.0.5",
            data_timestamp=datetime(2026, 7, 31, 9, 0, tzinfo=UTC),
        )

    async def fetch_studies(
        self,
        query: CompiledQuery,
        *,
        max_studies: int,
    ) -> CohortRetrieval:
        self.fetch_calls += 1
        if len(self._studies) > max_studies:
            raise QueryTooBroadError(len(self._studies), max_studies)
        return CohortRetrieval(
            cohort_id=query.cohort_id,
            studies=self._studies,
            matched_count=len(self._studies),
            pages_retrieved=1,
            retrieved_at=datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
            query_params=query.params,
        )


class CrashingQueryService(QueryService):
    def __init__(self) -> None:
        pass

    async def execute(
        self,
        request: QueryRequest,
        *,
        request_id: UUID,
    ) -> SuccessResponse:
        del request, request_id
        raise RuntimeError("sensitive implementation detail")


class FailingQueryService(QueryService):
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    async def execute(
        self,
        request: QueryRequest,
        *,
        request_id: UUID,
    ) -> SuccessResponse:
        del request, request_id
        raise self._failure


def query_app(gateway: EndpointGateway, *, max_studies: int = 20_000) -> FastAPI:
    service = QueryService(
        planner=RuleBasedPlanner(),
        clinical_trials=gateway,
        source_endpoint="https://clinicaltrials.gov/api/v2",
        max_studies=max_studies,
    )
    settings = Settings(
        _env_file=None,
        planner_provider="rules",
        max_studies=max(1_000, max_studies),
    )
    return create_app(settings=settings, query_service=service)


@pytest.mark.asyncio
async def test_query_endpoint_returns_versioned_visualization(
    first_page: dict[str, Any],
    second_page: dict[str, Any],
) -> None:
    app = query_app(EndpointGateway([*first_page["studies"], *second_page["studies"]]))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={
                "query": "Show melanoma trials by phase",
                "filters": {"conditions": ["Melanoma"]},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["status"] == "ok"
    UUID(payload["request_id"])
    assert payload["visualization"]["type"] == "bar_chart"
    assert payload["meta"]["record_counts"]["used"] == 2
    assert len(payload["provenance"]["citations"]) == 2


@pytest.mark.asyncio
async def test_query_endpoint_returns_clarification_without_calling_source() -> None:
    gateway = EndpointGateway([])
    app = query_app(gateway)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Summarize melanoma clinical trials"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "clarification_required"
    assert response.json()["clarification"]["missing_fields"] == ["dimension"]
    assert gateway.fetch_calls == 0


@pytest.mark.asyncio
async def test_query_endpoint_returns_typed_unsupported_response_without_source_call() -> None:
    gateway = EndpointGateway([])
    app = query_app(gateway)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Which is the best treatment for melanoma?"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert "medical advice" in response.json()["reason"]
    assert response.json()["suggestions"] == [
        "Show recruiting melanoma trials by phase.",
        "Show melanoma trials by intervention type.",
        "Which sponsors lead melanoma trials?",
    ]
    assert gateway.fetch_calls == 0


@pytest.mark.asyncio
async def test_query_endpoint_maps_study_cap_to_typed_422(
    first_page: dict[str, Any],
    second_page: dict[str, Any],
) -> None:
    app = query_app(
        EndpointGateway([*first_page["studies"], *second_page["studies"]]),
        max_studies=1,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Show trials for melanoma by phase"},
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "query_too_broad"
    assert payload["error"]["context"] == {
        "matched_count": 2,
        "max_studies": 1,
    }


@pytest.mark.asyncio
async def test_query_endpoint_maps_transient_source_failure_to_retryable_503() -> None:
    app = query_app(
        EndpointGateway(
            [],
            failure=ClinicalTrialsTransientError("temporary failure"),
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Show trials for melanoma by phase"},
        )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "source_unavailable",
        "message": "ClinicalTrials.gov is temporarily unavailable.",
        "retryable": True,
        "context": {"provider": "ClinicalTrials.gov"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status_code", "code", "retryable"),
    [
        (
            PlannerConfigurationError("missing key"),
            503,
            "planner_not_configured",
            False,
        ),
        (ModelProviderError("timeout"), 503, "planner_unavailable", True),
        (ModelRequestError("bad request"), 502, "planner_request_rejected", False),
        (ModelOutputError("no output"), 502, "planner_invalid_response", True),
    ],
)
async def test_query_endpoint_distinguishes_planner_failure_types(
    failure: Exception,
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    settings = Settings(_env_file=None, planner_provider="rules")
    app = create_app(
        settings=settings,
        query_service=FailingQueryService(failure),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Show melanoma trials by phase"},
        )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is retryable
    assert response.json()["error"]["context"] == {"provider": "OpenAI"}


@pytest.mark.asyncio
async def test_source_rejection_discloses_provider_and_upstream_status() -> None:
    settings = Settings(_env_file=None, planner_provider="rules")
    app = create_app(
        settings=settings,
        query_service=FailingQueryService(ClinicalTrialsRequestError(400, "bad query")),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Show melanoma trials by phase"},
        )

    assert response.status_code == 502
    assert response.json()["error"]["context"] == {
        "provider": "ClinicalTrials.gov",
        "upstream_status": 400,
    }


@pytest.mark.asyncio
async def test_request_validation_uses_versioned_error_envelope() -> None:
    app = query_app(EndpointGateway([]))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/query", json={"query": "x"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "invalid_request"
    assert payload["error"]["context"]["error_count"] == 1


@pytest.mark.asyncio
async def test_unexpected_error_is_logged_but_not_exposed() -> None:
    settings = Settings(_env_file=None, planner_provider="rules")
    app = create_app(
        settings=settings,
        query_service=CrashingQueryService(),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "Show trials for melanoma by phase"},
        )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "internal_error"
    assert "sensitive implementation detail" not in payload["error"]["message"]
