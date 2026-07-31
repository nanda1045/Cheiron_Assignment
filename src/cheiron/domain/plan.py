"""Constrained semantic plan produced by a planner and executed deterministically."""

from typing import Literal

from pydantic import Field, model_validator

from cheiron.domain.base import DomainModel
from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    FilterField,
    FilterOperator,
    MeasureField,
    RelationshipEntity,
    SortDirection,
    TimeGranularity,
    VisualizationType,
)

PlanValue = str | int


class FilterClause(DomainModel):
    """One allow-listed predicate in a cohort definition."""

    field: FilterField
    operator: FilterOperator
    values: list[PlanValue] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_operator_arity(self) -> "FilterClause":
        expected_count = 2 if self.operator is FilterOperator.BETWEEN else 1
        if (
            self.operator
            in {
                FilterOperator.GREATER_THAN_OR_EQUAL,
                FilterOperator.LESS_THAN_OR_EQUAL,
                FilterOperator.CONTAINS,
                FilterOperator.EQUALS,
            }
            and len(self.values) != expected_count
        ):
            raise ValueError(f"{self.operator.value} requires exactly {expected_count} value")
        if self.operator is FilterOperator.BETWEEN and len(self.values) != expected_count:
            raise ValueError("between requires exactly two values")
        return self


class CohortSpec(DomainModel):
    """Named trial population; comparisons are represented as multiple cohorts."""

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    label: str = Field(min_length=1, max_length=120)
    filters: list[FilterClause] = Field(default_factory=list, max_length=20)


class DimensionSpec(DomainModel):
    """Field used to group or position aggregated values."""

    field: DimensionField
    granularity: TimeGranularity | None = None

    @model_validator(mode="after")
    def validate_granularity(self) -> "DimensionSpec":
        if self.granularity is not None and self.field is not DimensionField.START_YEAR:
            raise ValueError("time granularity is only valid for start_year")
        return self


class MeasureSpec(DomainModel):
    """Deterministic measure to calculate over normalized study records."""

    field: MeasureField
    aggregation: Aggregation
    label: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=40)


class SortSpec(DomainModel):
    field: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    direction: SortDirection = SortDirection.ASCENDING


class RelationshipSpec(DomainModel):
    source: RelationshipEntity
    target: RelationshipEntity
    minimum_weight: int = Field(default=1, ge=1)
    max_nodes: int = Field(default=30, ge=2, le=100)


class AnalysisPlan(DomainModel):
    """Planner output contract; no API parameter or arbitrary field can pass through it."""

    schema_version: Literal["1.0"] = "1.0"
    intent: AnalysisIntent
    interpretation: str = Field(min_length=3, max_length=500)
    cohorts: list[CohortSpec] = Field(min_length=1, max_length=5)
    dimensions: list[DimensionSpec] = Field(default_factory=list, max_length=2)
    measure: MeasureSpec
    visualization: VisualizationType
    sort: SortSpec | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    relationship: RelationshipSpec | None = None

    @model_validator(mode="after")
    def validate_shape_for_intent(self) -> "AnalysisPlan":
        is_relationship = self.intent is AnalysisIntent.RELATIONSHIP
        if is_relationship != (self.relationship is not None):
            raise ValueError("relationship details are required only for relationship intent")
        if is_relationship and self.visualization is not VisualizationType.NETWORK_GRAPH:
            raise ValueError("relationship intent requires a network_graph visualization")
        if not is_relationship and not self.dimensions:
            raise ValueError("at least one dimension is required for non-relationship analyses")
        if self.intent is AnalysisIntent.COMPARISON and len(self.cohorts) < 2:
            raise ValueError("comparison intent requires at least two cohorts")
        return self
