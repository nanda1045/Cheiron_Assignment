"""Tests for strict OpenAI planning, plan guards, and narrow failover."""

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from openai import (
    APIConnectionError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
)
from pydantic import ValidationError

from cheiron.domain.answer import ScalarAnswerPlan
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
    ModelOutputError,
    ModelRequestError,
    PlannerConfigurationError,
    UnsupportedQuestion,
)
from cheiron.planning.guarded import GuardedPlanner
from cheiron.planning.model_output import (
    ModelClarificationDecision,
    ModelPlanDecision,
    ModelPlannerEnvelope,
)
from cheiron.planning.openai_planner import (
    PLANNER_INSTRUCTIONS,
    REPAIR_INSTRUCTIONS,
    OpenAIPlanner,
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
) -> tuple[AsyncOpenAI, AsyncMock]:
    client = MagicMock(spec=AsyncOpenAI)
    parser = AsyncMock(
        side_effect=error,
        return_value=SimpleNamespace(output_parsed=output, status="completed"),
    )
    client.responses.parse = parser
    return cast(AsyncOpenAI, client), parser


def invalid_comparison_error() -> ValidationError:
    payload = distribution_plan().model_dump(mode="json")
    payload["intent"] = AnalysisIntent.COMPARISON.value
    payload["visualization"] = VisualizationType.GROUPED_BAR_CHART.value
    with pytest.raises(ValidationError) as captured:
        ModelPlannerEnvelope.model_validate(
            {"decision": {"status": "planned", "plan": payload}}
        )
    return captured.value


@pytest.mark.asyncio
async def test_openai_planner_uses_strict_responses_parse_contract() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Melanoma"]),
    )
    envelope = ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    client, parser = mock_client(envelope)

    result = await OpenAIPlanner(client, model="gpt-5.4-mini").plan(request)

    assert result.mode is PlannerMode.OPENAI
    assert result.model == "gpt-5.4-mini"
    assert result.capability_limited is False
    parser.assert_awaited_once()
    arguments = parser.await_args.kwargs
    assert arguments["instructions"] == PLANNER_INSTRUCTIONS
    assert arguments["text_format"] is ModelPlannerEnvelope
    assert arguments["max_output_tokens"] == 4_000
    assert arguments["store"] is False
    assert arguments["input"] == [{"role": "user", "content": request.model_dump_json()}]


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
                "created_at": 1_700_000_000,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "model": "gpt-5.4-mini",
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
                                "logprobs": [],
                            }
                        ],
                    }
                ],
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 10,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 20,
                },
            },
        )
    )

    async with AsyncOpenAI(api_key="test-key", max_retries=0) as client:
        result = await OpenAIPlanner(client).plan(request)

    assert result.plan == distribution_plan()
    payload = json.loads(route.calls.last.request.content)
    assert payload["max_output_tokens"] == 4_000
    assert payload["store"] is False
    assert payload["input"] == [{"role": "user", "content": request.model_dump_json()}]
    schema = payload["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert "anyOf" in schema["properties"]["decision"]
    assert "oneOf" not in schema["properties"]["decision"]


@pytest.mark.asyncio
async def test_model_plan_guard_failure_is_repaired_once() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        filters=QueryFilters(conditions=["Lung Cancer"]),
    )
    invalid_envelope = ModelPlannerEnvelope(
        decision=ModelPlanDecision(plan=distribution_plan(condition="Melanoma"))
    )
    repaired_envelope = ModelPlannerEnvelope(
        decision=ModelPlanDecision(plan=distribution_plan(condition="Lung Cancer"))
    )
    client, parser = mock_client()
    parser.side_effect = [
        SimpleNamespace(output_parsed=invalid_envelope, status="completed"),
        SimpleNamespace(output_parsed=repaired_envelope, status="completed"),
    ]

    result = await OpenAIPlanner(client).plan(request)

    assert result.plan == distribution_plan(condition="Lung Cancer")
    assert parser.await_count == 2
    repair_arguments = parser.await_args_list[1].kwargs
    assert repair_arguments["instructions"] == REPAIR_INSTRUCTIONS
    repair_payload = json.loads(repair_arguments["input"][0]["content"])
    assert repair_payload["request"] == request.model_dump(mode="json")
    assert repair_payload["validation_issues"] == [
        {
            "location": "plan_guard",
            "message": "model plan changed structured condition values",
        }
    ]


@pytest.mark.asyncio
async def test_invalid_structured_plan_is_repaired_once() -> None:
    request = QueryRequest(query="Compare trials by phase")
    repaired = ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    client, parser = mock_client()
    parser.side_effect = [
        invalid_comparison_error(),
        SimpleNamespace(output_parsed=repaired, status="completed"),
    ]

    result = await OpenAIPlanner(client).plan(request)

    assert result.plan == distribution_plan()
    assert parser.await_count == 2
    repair_payload = json.loads(parser.await_args_list[1].kwargs["input"][0]["content"])
    assert any(
        "comparison intent requires at least two cohorts" in issue["message"]
        for issue in repair_payload["validation_issues"]
    )


@pytest.mark.asyncio
async def test_repeated_invalid_plan_becomes_actionable_clarification() -> None:
    client, parser = mock_client(error=invalid_comparison_error())

    with pytest.raises(ClarificationNeeded) as captured:
        await OpenAIPlanner(client).plan(QueryRequest(query="Compare trials by phase"))

    assert parser.await_count == 2
    assert captured.value.missing_fields == ("comparison_groups",)
    assert len(captured.value.suggestions) == 2


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
async def test_scalar_answer_routes_without_expanding_openai_schema() -> None:
    client, parser = mock_client()

    result = await OpenAIPlanner(client).plan(
        QueryRequest(query="How many recruiting melanoma trials are there?")
    )

    assert isinstance(result.plan, ScalarAnswerPlan)
    parser.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_question_routes_without_calling_openai() -> None:
    client, parser = mock_client()

    with pytest.raises(UnsupportedQuestion) as captured:
        await OpenAIPlanner(client).plan(QueryRequest(query="What is the best treatment?"))

    assert captured.value.suggestions
    parser.assert_not_awaited()


def test_openai_schema_excludes_non_visual_plan_contracts() -> None:
    schema = json.dumps(ModelPlannerEnvelope.model_json_schema())

    assert "scalar_answer" not in schema
    assert '"unsupported"' not in schema


@pytest.mark.asyncio
async def test_missing_parsed_output_is_a_typed_model_failure() -> None:
    client, _ = mock_client(None)

    with pytest.raises(ModelOutputError, match="no parsed structured output"):
        await OpenAIPlanner(client).plan(QueryRequest(query="Show trials by phase"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error_type", "expected_error"),
    [
        (AuthenticationError, PlannerConfigurationError),
        (BadRequestError, ModelRequestError),
    ],
)
async def test_openai_provider_errors_keep_actionable_failure_type(
    provider_error_type: type[AuthenticationError] | type[BadRequestError],
    expected_error: type[PlannerConfigurationError] | type[ModelRequestError],
) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401, request=request)
    provider_error = provider_error_type("provider rejected request", response=response, body=None)
    client, _ = mock_client(error=provider_error)

    with pytest.raises(expected_error):
        await OpenAIPlanner(client).plan(QueryRequest(query="Show trials by phase"))


@pytest.mark.asyncio
async def test_repeated_preferred_visualization_violation_requests_clarification() -> None:
    request = QueryRequest(
        query="Show melanoma trials by phase",
        options=QueryOptions(preferred_visualization=VisualizationType.GROUPED_BAR_CHART),
    )
    client, parser = mock_client(
        ModelPlannerEnvelope(decision=ModelPlanDecision(plan=distribution_plan()))
    )

    with pytest.raises(ClarificationNeeded) as captured:
        await OpenAIPlanner(client).plan(request)

    assert parser.await_count == 2
    assert captured.value.missing_fields == ("preferred_visualization",)


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
