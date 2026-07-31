"""Validation tests for constrained analysis plans."""

import pytest
from pydantic import ValidationError

from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    MeasureField,
    VisualizationType,
)
from cheiron.domain.plan import AnalysisPlan, CohortSpec, DimensionSpec, MeasureSpec


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
