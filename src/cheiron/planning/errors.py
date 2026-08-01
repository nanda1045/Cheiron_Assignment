"""Typed planner failures suitable for conversion into public API responses."""

from dataclasses import dataclass


class PlanningError(Exception):
    """Base class for failures before deterministic query execution."""


class ModelPlanningError(PlanningError):
    """The model-backed planner could not return a usable structured decision."""


class PlannerConfigurationError(ModelPlanningError):
    """The selected model provider is missing or rejected its credentials."""


class ModelProviderError(ModelPlanningError):
    """The model provider could not be reached or returned a transient failure."""


class ModelRequestError(ModelPlanningError):
    """The model provider rejected the application's planner request."""


class ModelOutputError(ModelPlanningError):
    """The model provider responded without a usable structured decision."""


class ModelPlanRejectedError(ModelPlanningError):
    """The parsed model plan contradicted authoritative request controls."""


@dataclass(frozen=True, slots=True)
class UnsupportedQuestion(PlanningError):
    """The question asks for a conclusion outside supported source-data analysis."""

    reason: str
    suggestions: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ClarificationNeeded(PlanningError):
    """The request is safe to retry after the user supplies missing intent."""

    question: str
    missing_fields: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.question
