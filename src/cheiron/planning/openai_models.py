"""Strict structured-output envelope returned by the OpenAI planner."""

from typing import Literal

from pydantic import Field

from cheiron.domain.base import DomainModel
from cheiron.domain.plan import AnalysisPlan


class ModelPlanDecision(DomainModel):
    """A complete semantic plan ready for application-side validation."""

    status: Literal["planned"] = "planned"
    plan: AnalysisPlan
    warnings: list[str] = Field(default_factory=list, max_length=5)


class ModelClarificationDecision(DomainModel):
    """A focused question when safe plan construction would require guessing."""

    status: Literal["clarification_required"] = "clarification_required"
    question: str = Field(min_length=3, max_length=500)
    missing_fields: list[str] = Field(default_factory=list, max_length=10)
    suggestions: list[str] = Field(default_factory=list, max_length=5)


ModelPlannerDecision = ModelPlanDecision | ModelClarificationDecision


class ModelPlannerEnvelope(DomainModel):
    """Object-root wrapper compatible with strict Structured Outputs."""

    decision: ModelPlannerDecision
