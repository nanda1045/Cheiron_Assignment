"""Behavioral tests for the deterministic natural-language fallback planner."""

import pytest

from cheiron.domain.answer import ScalarAnswerPlan
from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    FilterField,
    FilterOperator,
    MeasureField,
    PlannerMode,
    RelationshipEntity,
    SortDirection,
    VisualizationType,
)
from cheiron.domain.plan import FilterClause
from cheiron.domain.request import QueryFilters, QueryOptions, QueryRequest
from cheiron.planning.errors import ClarificationNeeded, UnsupportedQuestion
from cheiron.planning.rules import RuleBasedPlanner


def filters_by_field(clauses: list[FilterClause]) -> dict[FilterField, FilterClause]:
    return {clause.field: clause for clause in clauses}


@pytest.mark.asyncio
async def test_distribution_infers_common_filters_and_condition() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(
            query=("Show recruiting interventional trials for melanoma by phase since 2018")
        )
    )

    plan = result.plan
    clauses = filters_by_field(plan.cohorts[0].filters)
    assert result.mode is PlannerMode.RULES
    assert result.capability_limited is True
    assert plan.intent is AnalysisIntent.DISTRIBUTION
    assert plan.visualization is VisualizationType.BAR_CHART
    assert plan.dimensions[0].field is DimensionField.PHASE
    assert clauses[FilterField.CONDITION].values == ["melanoma"]
    assert clauses[FilterField.STATUS].values == ["RECRUITING"]
    assert clauses[FilterField.STUDY_TYPE].values == ["INTERVENTIONAL"]
    assert clauses[FilterField.START_YEAR].operator is FilterOperator.GREATER_THAN_OR_EQUAL
    assert clauses[FilterField.START_YEAR].values == [2018]


@pytest.mark.asyncio
async def test_comparison_builds_one_exact_cohort_per_intervention() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Compare pembrolizumab versus nivolumab for melanoma by phase")
    )

    plan = result.plan
    assert plan.intent is AnalysisIntent.COMPARISON
    assert plan.visualization is VisualizationType.GROUPED_BAR_CHART
    assert [cohort.label for cohort in plan.cohorts] == [
        "Pembrolizumab",
        "Nivolumab",
    ]
    for cohort, intervention in zip(
        plan.cohorts,
        ("pembrolizumab", "nivolumab"),
        strict=True,
    ):
        clauses = filters_by_field(cohort.filters)
        assert clauses[FilterField.INTERVENTION].values == [intervention]
        assert clauses[FilterField.CONDITION].values == ["melanoma"]


@pytest.mark.asyncio
async def test_structured_interventions_override_query_comparison_terms() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(
            query="Compare pembrolizumab versus nivolumab by phase",
            filters=QueryFilters(interventions=["Drug A", "Drug B"]),
        )
    )

    assert [cohort.label for cohort in result.plan.cohorts] == ["Drug A", "Drug B"]


@pytest.mark.asyncio
async def test_comparison_over_time_supports_between_and_wording() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Compare trends over time between pembrolizumab and nivolumab")
    )

    assert result.plan.visualization is VisualizationType.TIME_SERIES
    assert result.plan.dimensions[0].field is DimensionField.START_YEAR
    assert [cohort.label for cohort in result.plan.cohorts] == [
        "Pembrolizumab",
        "Nivolumab",
    ]


@pytest.mark.asyncio
async def test_structured_year_filter_takes_precedence_over_query_year() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(
            query="Show trial trends over time since 2010",
            filters=QueryFilters(start_year_from=2020),
        )
    )

    plan = result.plan
    year_filter = filters_by_field(plan.cohorts[0].filters)[FilterField.START_YEAR]
    assert plan.intent is AnalysisIntent.TREND
    assert plan.visualization is VisualizationType.TIME_SERIES
    assert plan.dimensions[0].field is DimensionField.START_YEAR
    assert year_filter.values == [2020]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "intent", "visualization", "dimension"),
    [
        (
            "Show an enrollment histogram for melanoma trials",
            AnalysisIntent.HISTOGRAM,
            VisualizationType.HISTOGRAM,
            DimensionField.ENROLLMENT,
        ),
        (
            "Scatter enrollment versus start year for melanoma trials",
            AnalysisIntent.SCATTER,
            VisualizationType.SCATTER_PLOT,
            DimensionField.START_YEAR,
        ),
        (
            "Show the top 10 countries for melanoma trials",
            AnalysisIntent.GEOGRAPHIC,
            VisualizationType.BAR_CHART,
            DimensionField.COUNTRY,
        ),
    ],
)
async def test_special_chart_shapes_are_deterministic(
    query: str,
    intent: AnalysisIntent,
    visualization: VisualizationType,
    dimension: DimensionField,
) -> None:
    result = await RuleBasedPlanner().plan(QueryRequest(query=query))

    assert result.plan.intent is intent
    assert result.plan.visualization is visualization
    assert result.plan.dimensions[0].field is dimension
    condition_filter = filters_by_field(result.plan.cohorts[0].filters)[FilterField.CONDITION]
    assert condition_filter.values == ["melanoma"]


@pytest.mark.asyncio
async def test_explicit_involving_phrase_is_an_intervention_filter() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Show trials involving pembrolizumab for melanoma by phase")
    )

    clauses = filters_by_field(result.plan.cohorts[0].filters)
    assert clauses[FilterField.INTERVENTION].values == ["pembrolizumab"]
    assert clauses[FilterField.CONDITION].values == ["melanoma"]


@pytest.mark.asyncio
async def test_top_n_adds_deterministic_descending_sort() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Show the top 10 countries for melanoma trials")
    )

    assert result.plan.limit == 10
    assert result.plan.sort is not None
    assert result.plan.sort.field == "trial_count"
    assert result.plan.sort.direction is SortDirection.DESCENDING


@pytest.mark.asyncio
async def test_relationship_query_selects_ordered_entities() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(
            query="Build a relationship network between sponsors and interventions",
            filters=QueryFilters(conditions=["Melanoma"]),
        )
    )

    assert result.plan.relationship is not None
    assert result.plan.relationship.source is RelationshipEntity.SPONSOR
    assert result.plan.relationship.target is RelationshipEntity.INTERVENTION
    assert result.plan.dimensions == []
    clauses = filters_by_field(result.plan.cohorts[0].filters)
    assert clauses[FilterField.CONDITION].values == ["Melanoma"]


@pytest.mark.asyncio
async def test_network_top_n_controls_node_budget_not_tabular_limit() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Show a top 12 sponsor and intervention network")
    )

    assert result.plan.relationship is not None
    assert result.plan.relationship.max_nodes == 12
    assert result.plan.limit is None


@pytest.mark.asyncio
async def test_top_n_is_rejected_when_it_would_truncate_chart_semantics() -> None:
    with pytest.raises(ClarificationNeeded, match="not well-defined"):
        await RuleBasedPlanner().plan(
            QueryRequest(query="Show a top 10 enrollment histogram for melanoma trials")
        )


@pytest.mark.asyncio
async def test_bar_graph_wording_is_not_misclassified_as_relationship() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Show a bar graph of melanoma trials by phase")
    )

    assert result.plan.intent is AnalysisIntent.DISTRIBUTION
    assert result.plan.visualization is VisualizationType.BAR_CHART
    clauses = filters_by_field(result.plan.cohorts[0].filters)
    assert clauses[FilterField.CONDITION].values == ["melanoma"]


@pytest.mark.asyncio
async def test_leading_condition_is_separated_from_status_and_study_type() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Show recruiting interventional melanoma trials by phase")
    )

    clauses = filters_by_field(result.plan.cohorts[0].filters)
    assert clauses[FilterField.CONDITION].values == ["melanoma"]
    assert clauses[FilterField.STATUS].values == ["RECRUITING"]
    assert clauses[FilterField.STUDY_TYPE].values == ["INTERVENTIONAL"]


@pytest.mark.asyncio
async def test_overlapping_status_phrase_does_not_add_recruiting() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="Show active not recruiting trials by phase")
    )

    clause = filters_by_field(result.plan.cohorts[0].filters)[FilterField.STATUS]
    assert clause.values == ["ACTIVE_NOT_RECRUITING"]


@pytest.mark.asyncio
async def test_missing_grouping_returns_actionable_clarification() -> None:
    with pytest.raises(ClarificationNeeded) as captured:
        await RuleBasedPlanner().plan(QueryRequest(query="Summarize melanoma clinical trials"))

    assert captured.value.missing_fields == ("dimension",)
    assert "phase" in captured.value.suggestions


@pytest.mark.asyncio
async def test_incompatible_visualization_preference_requires_confirmation() -> None:
    with pytest.raises(ClarificationNeeded, match="incompatible"):
        await RuleBasedPlanner().plan(
            QueryRequest(
                query="Show trial trends over time",
                options=QueryOptions(preferred_visualization=VisualizationType.NETWORK_GRAPH),
            )
        )


@pytest.mark.asyncio
async def test_single_count_question_routes_to_scalar_answer() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="How many recruiting Phase 3 breast cancer trials are there?")
    )

    assert isinstance(result.plan, ScalarAnswerPlan)
    assert result.plan.measure.field is MeasureField.NCT_ID
    clauses = filters_by_field(result.plan.cohorts[0].filters)
    assert clauses[FilterField.CONDITION].values == ["breast cancer"]
    assert clauses[FilterField.STATUS].values == ["RECRUITING"]
    assert clauses[FilterField.PHASE].values == ["PHASE3"]


@pytest.mark.asyncio
async def test_average_enrollment_question_routes_to_scalar_answer() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="What is the average enrollment for melanoma trials?")
    )

    assert isinstance(result.plan, ScalarAnswerPlan)
    assert result.plan.measure.field is MeasureField.ENROLLMENT
    assert result.plan.measure.aggregation is Aggregation.AVERAGE


@pytest.mark.asyncio
async def test_grouped_count_still_routes_to_visualization() -> None:
    result = await RuleBasedPlanner().plan(
        QueryRequest(query="How many melanoma trials are there by phase?")
    )

    assert not isinstance(result.plan, ScalarAnswerPlan)
    assert result.plan.visualization is VisualizationType.BAR_CHART


@pytest.mark.asyncio
async def test_medical_conclusion_is_explicitly_unsupported() -> None:
    with pytest.raises(UnsupportedQuestion, match="medical advice") as captured:
        await RuleBasedPlanner().plan(
            QueryRequest(query="What is the best treatment for melanoma?")
        )

    assert captured.value.suggestions == (
        "Show recruiting melanoma trials by phase.",
        "Show melanoma trials by intervention type.",
        "Which sponsors lead melanoma trials?",
    )


@pytest.mark.asyncio
async def test_unsupported_pivot_respects_authoritative_condition_filter() -> None:
    with pytest.raises(UnsupportedQuestion) as captured:
        await RuleBasedPlanner().plan(
            QueryRequest(
                query="What is the most effective treatment?",
                filters=QueryFilters(conditions=["Glioblastoma"]),
            )
        )

    assert captured.value.suggestions[0] == (
        "Show recruiting Glioblastoma trials by phase."
    )


@pytest.mark.asyncio
async def test_unsupported_pivot_uses_generic_suggestions_without_a_condition() -> None:
    with pytest.raises(UnsupportedQuestion) as captured:
        await RuleBasedPlanner().plan(
            QueryRequest(query="Which treatment is most effective?")
        )

    assert captured.value.suggestions == (
        "Count recruiting trials for a condition.",
        "Show trials grouped by phase.",
    )
