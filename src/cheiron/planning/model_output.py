"""Strict structured-output envelope returned by a model-backed planner."""

from typing import Literal

from pydantic import Field

from cheiron.domain.answer import SemanticPlan
from cheiron.domain.base import DomainModel


class ModelPlanDecision(DomainModel):
    """A complete semantic plan ready for application-side validation."""

    status: Literal["planned"] = "planned"
    plan: SemanticPlan
    warnings: list[str] = Field(default_factory=list, max_length=5)


class ModelClarificationDecision(DomainModel):
    """A focused question when safe plan construction would require guessing."""

    status: Literal["clarification_required"] = "clarification_required"
    question: str = Field(min_length=3, max_length=500)
    missing_fields: list[str] = Field(default_factory=list, max_length=10)
    suggestions: list[str] = Field(default_factory=list, max_length=5)


class ModelUnsupportedDecision(DomainModel):
    """A request outside safe ClinicalTrials.gov metadata analysis."""

    status: Literal["unsupported"] = "unsupported"
    reason: str = Field(min_length=3, max_length=500)
    suggestions: list[str] = Field(default_factory=list, max_length=5)


ModelPlannerDecision = ModelPlanDecision | ModelClarificationDecision | ModelUnsupportedDecision


class ModelPlannerEnvelope(DomainModel):
    """Object-root wrapper compatible with strict Structured Outputs."""

    decision: ModelPlannerDecision
