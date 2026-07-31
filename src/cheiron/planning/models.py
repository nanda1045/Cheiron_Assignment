"""Planner output and metadata shared by rule and model-backed planners."""

from dataclasses import dataclass

from cheiron.domain.enums import PlannerMode
from cheiron.domain.plan import AnalysisPlan


@dataclass(frozen=True, slots=True)
class PlanningResult:
    """Validated plan plus disclosure about how it was produced."""

    plan: AnalysisPlan
    mode: PlannerMode
    model: str | None = None
    capability_limited: bool = False
    warnings: tuple[str, ...] = ()
