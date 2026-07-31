"""Tests for strict OpenAI planning, plan guards, and narrow failover."""

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from openai import APIConnectionError, AsyncOpenAI

from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    FilterField,
    FilterOperator,
    MeasureField,
    PlannerMode,
    VisualizationType,
)
from cheiron.domain.plan import (
    AnalysisPlan,
    CohortSpec,
    DimensionSpec,
    FilterClause,
    MeasureSpec,
)
from cheiron.domain.request import QueryFilters, QueryOptions, QueryRequest
from cheiron.planning.errors import (
    ClarificationNeeded,
    ModelPlanRejectedError,
    OpenAIPlanningError,
)
from cheiron.planning.guarded import GuardedPlanner
from cheiron.planning.openai_models import (
    ModelClarificationDecision,
    ModelPlanDecision,
    ModelPlannerEnvelope,
)
from cheiron.planning.openai_planner import PLANNER_INSTRUCTIONS, OpenAIPlanner
from cheiron.planning.rules import RuleBasedPlanner


def trial_count_measure() -> MeasureSpec:
    return MeasureSpec(
        field=MeasureField.NCT_ID,
        aggregation=Aggregation.COUNT_DISTINCT,
        label="Unique trial count",
        unit="trials",
    )


def distribution_plan(*, condition: str = "Melanoma") -> AnalysisPlan:
    return AnalysisPlan(
        intent=AnalysisIntent.DISTRIBUTION,
        interpretation="Count distinct matching trials by phase.",
        cohorts=[
            CohortSpec(
                id="melanoma",
                label="Melanoma",
                filters=[
                    FilterClause(
                        field=FilterField.CONDITION,
                        operator=FilterOperator.CONTAINS,
                        values=[condition],
                    )
                ],
            )
        ],
        dimensions=[DimensionSpec(field=DimensionField.PHASE)],
        measure=trial_count_measure(),
        visualization=VisualizationType.BAR_CHART,
    )


def mock_client(
    output: ModelPlannerEnvelope | None = None,
    *,
    error: Exception | None = None,
) -> tuple[AsyncOpenAI, AsyncMock]:
    client = MagicMock(spec=AsyncOpenAI)
    parser = AsyncMock(
        side_effect=error,
        return_value=SimpleNamespace(output_parsed=output),
    )
    client.responses.parse = parser
    return cast(AsyncOpenAI, client), parser


@pytest.mark.asyncio
async def test_openai_planner_uses_strict_responses_parse_contract() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Melanoma"]),
    )
    envelope = ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    client, parser = mock_client(envelope)

    result = await OpenAIPlanner(client, model="gpt-5.6-sol").plan(request)

    assert result.mode is PlannerMode.OPENAI
    assert result.model == "gpt-5.6-sol"
    assert result.capability_limited is False
    parser.assert_awaited_once()
    arguments = parser.await_args.kwargs
    assert arguments["instructions"] == PLANNER_INSTRUCTIONS
    assert arguments["text_format"] is ModelPlannerEnvelope
    assert arguments["store"] is False
    assert arguments["input"] == request.model_dump_json()


@pytest.mark.asyncio
@respx.mock
async def test_installed_sdk_serializes_and_parses_the_strict_schema() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Melanoma"]),
    )
    envelope = ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    route = respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1_800_000_000,
                "status": "completed",
                "model": "gpt-5.6-sol",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": envelope.model_dump_json(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )
    )

    async with AsyncOpenAI(api_key="test-key", max_retries=0) as client:
        result = await OpenAIPlanner(client).plan(request)

    assert result.plan == distribution_plan()
    payload = json.loads(route.calls.last.request.content)
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    schema = payload["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert "anyOf" in schema["properties"]["decision"]
    assert "oneOf" not in schema["properties"]["decision"]


@pytest.mark.asyncio
async def test_model_plan_cannot_override_structured_filters() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Lung Cancer"]),
    )
    envelope = ModelPlannerEnvelope(
        decision=ModelPlanDecision(plan=distribution_plan(condition="Melanoma"))
    )
    client, _ = mock_client(envelope)

    with pytest.raises(ModelPlanRejectedError, match="structured condition"):
        await OpenAIPlanner(client).plan(request)


@pytest.mark.asyncio
async def test_model_plan_accepts_authoritative_filters_partitioned_by_comparison() -> None:
    request = QueryRequest(
        query="Compare pembrolizumab and nivolumab by phase",
        filters=QueryFilters(interventions=["Pembrolizumab", "Nivolumab"]),
    )
    cohorts = [
        CohortSpec(
            id="pembrolizumab",
            label="Pembrolizumab",
            filters=[
                FilterClause(
                    field=FilterField.INTERVENTION,
                    operator=FilterOperator.CONTAINS,
                    values=["Pembrolizumab"],
                )
            ],
        ),
        CohortSpec(
            id="nivolumab",
            label="Nivolumab",
            filters=[
                FilterClause(
                    field=FilterField.INTERVENTION,
                    operator=FilterOperator.CONTAINS,
                    values=["Nivolumab"],
                )
            ],
        ),
    ]
    plan = AnalysisPlan(
        intent=AnalysisIntent.COMPARISON,
        interpretation="Compare two interventions by phase.",
        cohorts=cohorts,
        dimensions=[DimensionSpec(field=DimensionField.PHASE)],
        measure=trial_count_measure(),
        visualization=VisualizationType.GROUPED_BAR_CHART,
    )
    client, _ = mock_client(ModelPlannerEnvelope(decision=ModelPlanDecision(plan=plan)))

    result = await OpenAIPlanner(client).plan(request)

    assert result.plan == plan


@pytest.mark.asyncio
async def test_model_clarification_is_preserved() -> None:
    decision = ModelClarificationDecision(
        question="Which interventions should be compared?",
        missing_fields=["filters.interventions"],
        suggestions=["Pembrolizumab versus nivolumab"],
    )
    client, _ = mock_client(ModelPlannerEnvelope(decision=decision))

    with pytest.raises(ClarificationNeeded) as captured:
        await OpenAIPlanner(client).plan(QueryRequest(query="Compare trials by phase"))

    assert captured.value.missing_fields == ("filters.interventions",)
    assert captured.value.suggestions == ("Pembrolizumab versus nivolumab",)


@pytest.mark.asyncio
async def test_missing_parsed_output_is_a_typed_openai_failure() -> None:
    client, _ = mock_client(None)

    with pytest.raises(OpenAIPlanningError, match="no parsed structured output"):
        await OpenAIPlanner(client).plan(QueryRequest(query="Show trials by phase"))


@pytest.mark.asyncio
async def test_preferred_visualization_is_enforced_after_model_parsing() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        options=QueryOptions(preferred_visualization=VisualizationType.GROUPED_BAR_CHART),
    )
    client, _ = mock_client(
        ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    )

    with pytest.raises(ModelPlanRejectedError, match="preferred visualization"):
        await OpenAIPlanner(client).plan(request)


@pytest.mark.asyncio
async def test_guarded_planner_falls_back_only_for_expected_openai_failures() -> None:
    connection_error = APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )
    client, _ = mock_client(error=connection_error)
    planner = GuardedPlanner(OpenAIPlanner(client), RuleBasedPlanner())

    result = await planner.plan(QueryRequest(query="Show trials for melanoma by phase"))

    assert result.mode is PlannerMode.RULES
    assert result.capability_limited is True
    assert result.warnings[0].startswith("OpenAI planning was unavailable")


@pytest.mark.asyncio
async def test_guarded_planner_does_not_hide_model_clarification() -> None:
    client, _ = mock_client(
        ModelPlannerEnvelope(
            decision=ModelClarificationDecision(
                question="Which condition should I use?",
                missing_fields=["filters.conditions"],
            )
        )
    )
    fallback = MagicMock(spec=RuleBasedPlanner)
    fallback.plan = AsyncMock()
    planner = GuardedPlanner(OpenAIPlanner(client), fallback)

    with pytest.raises(ClarificationNeeded):
        await planner.plan(QueryRequest(query="Show a trial chart"))

    fallback.plan.assert_not_awaited()
