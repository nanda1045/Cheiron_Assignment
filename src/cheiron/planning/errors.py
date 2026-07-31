"""Typed planner failures suitable for conversion into public API responses."""

from dataclasses import dataclass


class PlanningError(Exception):
    """Base class for failures before deterministic query execution."""


class OpenAIPlanningError(PlanningError):
    """The model-backed planner could not return a usable structured decision."""


class ModelPlanRejectedError(OpenAIPlanningError):
    """The parsed model plan contradicted authoritative request controls."""


@dataclass(frozen=True, slots=True)
class ClarificationNeeded(PlanningError):
    """The request is safe to retry after the user supplies missing intent."""

    question: str
    missing_fields: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.question
