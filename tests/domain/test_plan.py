"""Validation tests for constrained analysis plans."""

import pytest
from pydantic import ValidationError

from cheiron.domain.answer import ScalarAnswerPlan
from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    FilterField,
    FilterOperator,
    MeasureField,
    VisualizationType,
)
from cheiron.domain.plan import (
    AnalysisPlan,
    CohortSpec,
    DimensionSpec,
    FilterClause,
    MeasureSpec,
)


def make_measure() -> MeasureSpec:
    return MeasureSpec(
        field=MeasureField.NCT_ID,
        aggregation=Aggregation.COUNT_DISTINCT,
        label="Trial count",
        unit="trials",
    )


def test_valid_distribution_plan() -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.DISTRIBUTION,
        interpretation="Count unique melanoma trials by phase.",
        cohorts=[CohortSpec(id="melanoma", label="Melanoma")],
        dimensions=[DimensionSpec(field=DimensionField.PHASE)],
        measure=make_measure(),
        visualization=VisualizationType.BAR_CHART,
    )

    assert plan.measure.aggregation is Aggregation.COUNT_DISTINCT


def test_comparison_requires_two_cohorts() -> None:
    with pytest.raises(ValidationError, match="at least two cohorts"):
        AnalysisPlan(
            intent=AnalysisIntent.COMPARISON,
            interpretation="Compare phases across treatments.",
            cohorts=[CohortSpec(id="treatment-a", label="Treatment A")],
            dimensions=[DimensionSpec(field=DimensionField.PHASE)],
            measure=make_measure(),
            visualization=VisualizationType.GROUPED_BAR_CHART,
        )


def test_relationship_requires_relationship_details() -> None:
    with pytest.raises(ValidationError, match="relationship details"):
        AnalysisPlan(
            intent=AnalysisIntent.RELATIONSHIP,
            interpretation="Show sponsor and intervention relationships.",
            cohorts=[CohortSpec(id="all", label="All studies")],
            measure=make_measure(),
            visualization=VisualizationType.NETWORK_GRAPH,
        )


def test_numeric_filter_rejects_non_integer_threshold() -> None:
    with pytest.raises(ValidationError, match="must be integers"):
        FilterClause(
            field=FilterField.START_YEAR,
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            values=["recent"],
        )


@pytest.mark.parametrize(
    ("field", "human_value", "canonical_value"),
    [
        (FilterField.PHASE, "Phase 3", "PHASE3"),
        (FilterField.PHASE, "Phase III", "PHASE3"),
        (FilterField.PHASE, "Not Applicable", "NA"),
        (FilterField.STATUS, "Active, not recruiting", "ACTIVE_NOT_RECRUITING"),
        (FilterField.STUDY_TYPE, "Expanded Access", "EXPANDED_ACCESS"),
        (FilterField.SPONSOR_CLASS, "Federal", "FED"),
        (FilterField.SPONSOR_CLASS, "Other Government", "OTHER_GOV"),
    ],
)
def test_categorical_filters_use_clinical_trials_vocabulary(
    field: FilterField,
    human_value: str,
    canonical_value: str,
) -> None:
    clause = FilterClause(
        field=field,
        operator=FilterOperator.EQUALS,
        values=[human_value],
    )

    assert clause.values == [canonical_value]


def test_categorical_filter_rejects_unknown_source_value() -> None:
    with pytest.raises(ValidationError, match="unsupported phase value"):
        FilterClause(
            field=FilterField.PHASE,
            operator=FilterOperator.EQUALS,
            values=["Late stage"],
        )


def test_free_text_filter_values_are_not_rewritten() -> None:
    clause = FilterClause(
        field=FilterField.CONDITION,
        operator=FilterOperator.CONTAINS,
        values=["HER2-positive Breast Cancer"],
    )

    assert clause.values == ["HER2-positive Breast Cancer"]


def test_scatter_plan_rejects_aggregated_measure() -> None:
    with pytest.raises(ValidationError, match="unaggregated enrollment"):
        AnalysisPlan(
            intent=AnalysisIntent.SCATTER,
            interpretation="Compare year and enrollment.",
            cohorts=[CohortSpec(id="all", label="All trials")],
            dimensions=[DimensionSpec(field=DimensionField.START_YEAR)],
            measure=MeasureSpec(
                field=MeasureField.ENROLLMENT,
                aggregation=Aggregation.AVERAGE,
                label="Enrollment",
            ),
            visualization=VisualizationType.SCATTER_PLOT,
        )


def test_measure_rejects_incompatible_aggregation() -> None:
    with pytest.raises(ValidationError, match="sum is not supported for nct_id"):
        MeasureSpec(
            field=MeasureField.NCT_ID,
            aggregation=Aggregation.SUM,
            label="Invalid total",
        )


def test_scalar_answer_rejects_unaggregated_enrollment() -> None:
    with pytest.raises(ValidationError, match="scalar answers require"):
        ScalarAnswerPlan(
            interpretation="Return one enrollment value.",
            cohorts=[CohortSpec(id="all", label="All trials")],
            measure=MeasureSpec(
                field=MeasureField.ENROLLMENT,
                aggregation=Aggregation.NONE,
                label="Enrollment",
            ),
        )
