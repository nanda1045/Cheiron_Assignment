"""Typed plans and public output for deterministic scalar answers."""

from typing import Literal

from pydantic import Field, model_validator

from cheiron.domain.base import DomainModel
from cheiron.domain.enums import Aggregation, MeasureField
from cheiron.domain.plan import AnalysisPlan, CohortSpec, MeasureSpec


class ScalarAnswerPlan(DomainModel):
    """One aggregate fact over one explicitly filtered trial cohort."""

    schema_version: Literal["1.0"] = "1.0"
    output_type: Literal["scalar_answer"] = "scalar_answer"
    interpretation: str = Field(min_length=3, max_length=500)
    cohorts: list[CohortSpec] = Field(min_length=1, max_length=1)
    measure: MeasureSpec

    @model_validator(mode="after")
    def validate_scalar_measure(self) -> "ScalarAnswerPlan":
        allowed = {
            MeasureField.NCT_ID: {Aggregation.COUNT, Aggregation.COUNT_DISTINCT},
            MeasureField.ENROLLMENT: {Aggregation.SUM, Aggregation.AVERAGE},
        }
        if self.measure.aggregation not in allowed[self.measure.field]:
            raise ValueError("scalar answers require count, total, or average aggregation")
        return self


SemanticPlan = AnalysisPlan | ScalarAnswerPlan


class ScalarAnswer(DomainModel):
    """Application-worded answer with evidence references for its exact value."""

    kind: Literal["scalar"] = "scalar"
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=500)
    value: int | float | None
    unit: str | None = Field(default=None, max_length=40)
    citation_ids: list[str] = Field(default_factory=list)
