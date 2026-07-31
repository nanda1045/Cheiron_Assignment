"""Tests for strict Claude planning, plan guards, and narrow failover."""

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from anthropic import APIConnectionError, AsyncAnthropic

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
from cheiron.planning.claude_planner import PLANNER_INSTRUCTIONS, ClaudePlanner
from cheiron.planning.errors import (
    ClarificationNeeded,
    ModelPlanningError,
    ModelPlanRejectedError,
)
from cheiron.planning.guarded import GuardedPlanner
from cheiron.planning.model_output import (
    ModelClarificationDecision,
    ModelPlanDecision,
    ModelPlannerEnvelope,
)
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
) -> tuple[AsyncAnthropic, AsyncMock]:
    client = MagicMock(spec=AsyncAnthropic)
    parser = AsyncMock(
        side_effect=error,
        return_value=SimpleNamespace(parsed_output=output, stop_reason="end_turn"),
    )
    client.messages.parse = parser
    return cast(AsyncAnthropic, client), parser


@pytest.mark.asyncio
async def test_claude_planner_uses_strict_messages_parse_contract() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Melanoma"]),
    )
    envelope = ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    client, parser = mock_client(envelope)

    result = await ClaudePlanner(client, model="claude-sonnet-5").plan(request)

    assert result.mode is PlannerMode.CLAUDE
    assert result.model == "claude-sonnet-5"
    assert result.capability_limited is False
    parser.assert_awaited_once()
    arguments = parser.await_args.kwargs
    assert arguments["system"] == PLANNER_INSTRUCTIONS
    assert arguments["output_format"] is ModelPlannerEnvelope
    assert arguments["max_tokens"] == 4_000
    assert arguments["messages"] == [{"role": "user", "content": request.model_dump_json()}]


@pytest.mark.asyncio
@respx.mock
async def test_installed_sdk_serializes_and_parses_the_strict_schema() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Melanoma"]),
    )
    envelope = ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [
                    {
                        "type": "text",
                        "text": envelope.model_dump_json(),
                    }
                ],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10},
            },
        )
    )

    async with AsyncAnthropic(api_key="test-key", max_retries=0) as client:
        result = await ClaudePlanner(client).plan(request)

    assert result.plan == distribution_plan()
    payload = json.loads(route.calls.last.request.content)
    assert payload["max_tokens"] == 4_000
    assert payload["messages"] == [{"role": "user", "content": request.model_dump_json()}]
    schema = payload["output_config"]["format"]["schema"]
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
        await ClaudePlanner(client).plan(request)


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

    result = await ClaudePlanner(client).plan(request)

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
        await ClaudePlanner(client).plan(QueryRequest(query="Compare trials by phase"))

    assert captured.value.missing_fields == ("filters.interventions",)
    assert captured.value.suggestions == ("Pembrolizumab versus nivolumab",)


@pytest.mark.asyncio
async def test_missing_parsed_output_is_a_typed_model_failure() -> None:
    client, _ = mock_client(None)

    with pytest.raises(ModelPlanningError, match="no parsed structured output"):
        await ClaudePlanner(client).plan(QueryRequest(query="Show trials by phase"))


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
        await ClaudePlanner(client).plan(request)


@pytest.mark.asyncio
async def test_guarded_planner_falls_back_only_for_expected_claude_failures() -> None:
    connection_error = APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    client, _ = mock_client(error=connection_error)
    planner = GuardedPlanner(ClaudePlanner(client), RuleBasedPlanner())

    result = await planner.plan(QueryRequest(query="Show trials for melanoma by phase"))

    assert result.mode is PlannerMode.RULES
    assert result.capability_limited is True
    assert result.warnings[0].startswith("Claude planning was unavailable")


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
    planner = GuardedPlanner(ClaudePlanner(client), fallback)

    with pytest.raises(ClarificationNeeded):
        await planner.plan(QueryRequest(query="Show a trial chart"))

    fallback.plan.assert_not_awaited()
