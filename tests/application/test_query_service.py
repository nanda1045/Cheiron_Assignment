"""Tests for complete planner-to-visualization query orchestration."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from cheiron.application.query_service import QueryService
from cheiron.clinical_trials.errors import QueryTooBroadError
from cheiron.clinical_trials.models import CohortRetrieval, DatasetVersion
from cheiron.clinical_trials.query_compiler import CompiledQuery
from cheiron.domain.enums import CompletenessStatus, PlannerMode
from cheiron.domain.request import QueryFilters, QueryOptions, QueryRequest
from cheiron.planning.rules import RuleBasedPlanner


class RecordedGateway:
    def __init__(self, studies: list[dict[str, Any]]) -> None:
        self._studies = tuple(studies)
        self.limits: list[int] = []

    async def get_version(self) -> DatasetVersion:
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
        self.limits.append(max_studies)
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


@pytest.mark.asyncio
async def test_query_service_builds_complete_sourced_response(
    first_page: dict[str, Any],
    second_page: dict[str, Any],
) -> None:
    studies = [*first_page["studies"], *second_page["studies"]]
    gateway = RecordedGateway(studies)
    service = QueryService(
        planner=RuleBasedPlanner(),
        clinical_trials=gateway,
        source_endpoint="https://clinicaltrials.gov/api/v2",
        max_studies=20_000,
    )

    response = await service.execute(
        QueryRequest(
            query="Show melanoma trials by phase",
            filters=QueryFilters(conditions=["Melanoma"]),
        ),
        request_id=uuid4(),
    )

    assert response.status == "ok"
    assert response.meta.planner.mode is PlannerMode.RULES
    assert response.meta.record_counts.model_dump() == {
        "matched": 2,
        "retrieved": 2,
        "used": 2,
        "excluded": 0,
    }
    assert response.meta.completeness.status is CompletenessStatus.COMPLETE
    assert response.meta.completeness.is_complete is True
    assert response.meta.completeness.pages_retrieved == 1
    assert response.provenance.source.api_version == "2.0.5"
    assert response.provenance.source.data_timestamp.year == 2026
    assert str(response.provenance.source.endpoint).endswith("/api/v2/studies")
    assert len(response.provenance.citations) == 2
    assert gateway.limits == [20_000]


@pytest.mark.asyncio
async def test_query_service_enforces_study_cap_across_comparison_cohorts(
    first_page: dict[str, Any],
) -> None:
    gateway = RecordedGateway(first_page["studies"])
    service = QueryService(
        planner=RuleBasedPlanner(),
        clinical_trials=gateway,
        source_endpoint="https://clinicaltrials.gov/api/v2",
        max_studies=1,
    )

    with pytest.raises(QueryTooBroadError) as captured:
        await service.execute(
            QueryRequest(query="Compare pembrolizumab versus nivolumab by phase"),
            request_id=uuid4(),
        )

    assert captured.value.matched_count == 2
    assert captured.value.max_studies == 1
    assert gateway.limits == [1, 0]


@pytest.mark.asyncio
async def test_server_cap_is_disclosed_in_response_warnings(
    first_page: dict[str, Any],
) -> None:
    gateway = RecordedGateway(first_page["studies"])
    service = QueryService(
        planner=RuleBasedPlanner(),
        clinical_trials=gateway,
        source_endpoint="https://clinicaltrials.gov/api/v2",
        max_studies=10,
    )

    response = await service.execute(
        QueryRequest(
            query="Show melanoma trials by phase",
            filters=QueryFilters(conditions=["Melanoma"]),
            options=QueryOptions(max_studies=100),
        ),
        request_id=uuid4(),
    )

    assert gateway.limits == [10]
    assert any("server cap" in warning for warning in response.meta.warnings)


@pytest.mark.asyncio
async def test_query_service_builds_deterministic_scalar_answer(
    first_page: dict[str, Any],
    second_page: dict[str, Any],
) -> None:
    gateway = RecordedGateway([*first_page["studies"], *second_page["studies"]])
    service = QueryService(
        planner=RuleBasedPlanner(),
        clinical_trials=gateway,
        source_endpoint="https://clinicaltrials.gov/api/v2",
        max_studies=20_000,
    )

    response = await service.execute(
        QueryRequest(query="How many recruiting melanoma trials are there?"),
        request_id=uuid4(),
    )

    assert response.result_type == "scalar_answer"
    assert response.visualization is None
    assert response.answer is not None
    assert response.answer.value == 1
    assert len(response.answer.citation_ids) == 1
    assert response.meta.record_counts.used == 1
    assert response.meta.record_counts.excluded == 1
