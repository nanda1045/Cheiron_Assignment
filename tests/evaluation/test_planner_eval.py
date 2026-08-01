"""Tests for deterministic scoring around live planner observations."""

from pathlib import Path

import pytest

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
from cheiron.domain.request import QueryRequest
from cheiron.evaluation.planner import (
    ExpectedDecision,
    ExpectedFilter,
    PlannerEvalCase,
    evaluate_planner,
    load_planner_cases,
)
from cheiron.planning.errors import ClarificationNeeded, UnsupportedQuestion
from cheiron.planning.models import PlanningResult


class StaticPlanner:
    def __init__(
        self,
        result: PlanningResult | ClarificationNeeded | UnsupportedQuestion,
    ) -> None:
        self._result = result

    async def plan(self, request: QueryRequest) -> PlanningResult:
        del request
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def melanoma_phase_result(*, condition: str = "Melanoma") -> PlanningResult:
    plan = AnalysisPlan(
        intent=AnalysisIntent.DISTRIBUTION,
        interpretation="Count matching trials by phase.",
        cohorts=[
            CohortSpec(
                id="matching",
                label="Matching trials",
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
        measure=MeasureSpec(
            field=MeasureField.NCT_ID,
            aggregation=Aggregation.COUNT_DISTINCT,
            label="Unique trials",
            unit="trials",
        ),
        visualization=VisualizationType.BAR_CHART,
    )
    return PlanningResult(plan=plan, mode=PlannerMode.OPENAI, model="test-model")


def distribution_case(*, forbidden_condition: str | None = None) -> PlannerEvalCase:
    forbidden = (
        [ExpectedFilter(field=FilterField.CONDITION, values=[forbidden_condition])]
        if forbidden_condition
        else []
    )
    return PlannerEvalCase(
        id="distribution-case",
        category="distribution",
        request=QueryRequest(query="Show melanoma trials by phase"),
        expected=ExpectedDecision(
            route="visualization",
            intent=AnalysisIntent.DISTRIBUTION,
            visualization=VisualizationType.BAR_CHART,
            dimensions=[DimensionField.PHASE],
            measure_field=MeasureField.NCT_ID,
            aggregation=Aggregation.COUNT_DISTINCT,
            cohort_count=1,
            filters=[ExpectedFilter(field=FilterField.CONDITION, values=["melanoma"])],
            forbidden_filters=forbidden,
        ),
    )


def test_curated_dataset_is_valid_and_unique() -> None:
    cases = load_planner_cases(Path("evals/planner_cases.json"))

    assert len(cases) == 16
    assert len({case.id for case in cases}) == len(cases)
    assert {case.expected.route for case in cases} == {
        "visualization",
        "scalar_answer",
        "clarification",
        "unsupported",
    }


@pytest.mark.asyncio
async def test_semantic_subset_and_forbidden_filter_checks_pass() -> None:
    report = await evaluate_planner(
        StaticPlanner(melanoma_phase_result()),
        [distribution_case(forbidden_condition="lung cancer")],
        model="test-model",
    )

    assert report.pass_rate == 1
    assert report.check_pass_rate == 1
    assert report.cases[0].passed is True
    assert report.cases[0].actual_route == "visualization"


@pytest.mark.asyncio
async def test_semantic_mismatch_records_expected_and_actual_values() -> None:
    case = distribution_case()
    case.expected.visualization = VisualizationType.GROUPED_BAR_CHART

    report = await evaluate_planner(
        StaticPlanner(melanoma_phase_result()),
        [case],
        model="test-model",
    )

    assert report.pass_rate == 0
    failure = next(check for check in report.cases[0].checks if not check.passed)
    assert failure.name == "visualization"
    assert failure.expected == "grouped_bar_chart"
    assert failure.actual == "bar_chart"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "expected_route"),
    [
        (
            ClarificationNeeded(question="Which condition?"),
            "clarification",
        ),
        (
            UnsupportedQuestion(reason="Outside registered metadata."),
            "unsupported",
        ),
    ],
)
async def test_non_plan_routes_are_scored_without_wording_matches(
    exception: ClarificationNeeded | UnsupportedQuestion,
    expected_route: str,
) -> None:
    case = PlannerEvalCase(
        id=f"{expected_route}-case",
        category=expected_route,
        request=QueryRequest(query="Evaluate this question"),
        expected=ExpectedDecision.model_validate({"route": expected_route}),
    )

    report = await evaluate_planner(StaticPlanner(exception), [case], model="test-model")

    assert report.pass_rate == 1
    assert report.cases[0].checks[0].name == "route"
